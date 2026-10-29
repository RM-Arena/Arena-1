"""Spawn-based persistent actor processes and a JSON-lines training protocol."""
import json
import multiprocessing
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

from .catalog import StrategySnapshots
from .engine import DT
from .env import ArenaEnv


class VectorEnvError(RuntimeError):
    def __init__(self, responses):
        self.responses = responses
        failed = [r for r in responses if not r['ok']]
        super().__init__('; '.join(f"env {r['env_id']}: {r['error']}" for r in failed))


def _actor(connection, options):
    if os.name != 'nt':
        os.setsid()
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    def terminate(*args):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, terminate)
    environment = None
    try:
        environment = ArenaEnv(**options)
        connection.send({'ok':True})
        while True:
            try:
                operation, payload = connection.recv()
            except EOFError:
                break
            try:
                if operation == 'close':
                    connection.send({'ok':True,'result':None})
                    break
                if operation == 'reset':
                    result = environment.reset(**payload)
                elif operation == 'step':
                    result = environment.step(payload)
                elif operation == 'save_replay':
                    result = environment.save_replay(payload['path'])
                else:
                    raise ValueError('Unknown environment operation')
                connection.send({'ok':True,'result':result})
            except Exception as exc:
                connection.send({'ok':False,'error':f'{type(exc).__name__}: {exc}'})
    except (EOFError, BrokenPipeError):
        pass
    except Exception as exc:
        try:
            connection.send({'ok':False,'error':f'{type(exc).__name__}: {exc}'})
        except (EOFError, BrokenPipeError):
            pass
    finally:
        if environment:
            environment.close()
        connection.close()


def _stop_actor(process):
    if not process.is_alive():
        return
    if os.name == 'nt':
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL,timeout=10)
    else:
        try:
            if os.getpgid(process.pid) == process.pid:
                os.killpg(process.pid,signal.SIGTERM)
            else:
                process.terminate()
        except ProcessLookupError:
            pass
    process.join(2)
    if process.is_alive():
        if os.name != 'nt':
            try:
                if os.getpgid(process.pid) == process.pid:
                    os.killpg(process.pid,signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.join(2)


class VectorArena:
    """Concurrent reset/step over isolated, persistent actors, in stable env-id order.

    There is no automatic reset: terminal observations remain available to the
    trainer. Subset reset accepts explicit env_ids and seeds. A failed actor does
    not stop its peers; VectorEnvError.responses retains every response.
    """
    def __init__(self, num_envs=1, *, rpc_timeout=60, **options):
        if isinstance(num_envs,bool) or not isinstance(num_envs,int) or not 1 <= num_envs <= 128:
            raise ValueError('num_envs must be in [1,128]')
        if not isinstance(rpc_timeout,(int,float)) or not 0 < rpc_timeout <= 3600:
            raise ValueError('rpc_timeout must be in (0,3600]')
        self.num_envs, self.rpc_timeout, self.closed = num_envs, rpc_timeout, False
        self.connections, self.processes, self.broken = [], [], set()
        self.temporary = tempfile.TemporaryDirectory(prefix='arena-actors-')
        if options.get('opponent'):
            options = {**options,'opponent':str(StrategySnapshots(self.temporary.name).freeze(options['opponent']))}
        context = multiprocessing.get_context('spawn')
        try:
            for _ in range(num_envs):
                parent, child = context.Pipe()
                process = context.Process(target=_actor,args=(child,options),daemon=False)
                process.start()
                child.close()
                self.connections.append(parent); self.processes.append(process)
            errors = []
            deadline = time.monotonic()+rpc_timeout
            for i, connection in enumerate(self.connections):
                if not connection.poll(max(0,deadline-time.monotonic())):
                    errors.append({'env_id':i,'ok':False,'error':'Actor startup timed out'})
                else:
                    result = connection.recv()
                    if not result['ok']:
                        errors.append({'env_id':i,**result})
            if errors:
                raise VectorEnvError(errors)
        except BaseException:
            self.close()
            raise

    def _ids(self, env_ids):
        ids = list(range(self.num_envs)) if env_ids is None else list(env_ids)
        if len(set(ids)) != len(ids) or any(isinstance(i,bool) or not isinstance(i,int) or not 0 <= i < self.num_envs for i in ids):
            raise ValueError('env_ids must be unique valid environment indices')
        return ids

    def request(self, operation, payloads, env_ids=None):
        if self.closed:
            raise ValueError('Vector environment is closed')
        if operation not in ('reset','step','save_replay'):
            raise ValueError('Unsupported vector operation')
        ids = self._ids(env_ids)
        if len(payloads) != len(ids):
            raise ValueError('Supply one payload for each selected environment')
        results = {}
        for i, payload in zip(ids,payloads):
            if i in self.broken:
                results[i] = {'env_id':i,'ok':False,'error':'Actor is unavailable; recreate the vector environment'}
                continue
            try:
                self.connections[i].send((operation,payload))
            except (OSError,EOFError) as exc:
                self.broken.add(i)
                results[i] = {'env_id':i,'ok':False,'error':f'Actor disconnected: {exc}'}
        deadline = time.monotonic()+self.rpc_timeout
        for i in ids:
            if i in results:
                continue
            try:
                if not self.connections[i].poll(max(0,deadline-time.monotonic())):
                    raise TimeoutError('Actor response timed out')
                results[i] = {'env_id':i,**self.connections[i].recv()}
            except (OSError,EOFError,TimeoutError) as exc:
                self.broken.add(i)
                _stop_actor(self.processes[i])
                results[i] = {'env_id':i,'ok':False,'error':f'{type(exc).__name__}: {exc}'}
        return [results[i] for i in ids]

    @staticmethod
    def _values(responses):
        if any(not r['ok'] for r in responses):
            raise VectorEnvError(responses)
        return [r['result'] for r in responses]

    def reset(self, seeds=None, env_ids=None, scenarios=None):
        ids = self._ids(env_ids)
        seeds = [42+i for i in ids] if seeds is None else list(seeds)
        scenarios = [None]*len(ids) if scenarios is None else list(scenarios)
        if len(seeds) != len(ids) or len(scenarios) != len(ids):
            raise ValueError('Supply one seed and scenario for each selected environment')
        return self._values(self.request('reset',[{'seed':s,'scenario':c} for s,c in zip(seeds,scenarios)],ids))

    def step(self, actions, env_ids=None):
        return self._values(self.request('step',list(actions),env_ids))

    def save_replay(self, paths, env_ids=None):
        return self._values(self.request('save_replay',[{'path':str(p)} for p in paths],env_ids))

    def close(self):
        if self.closed:
            return
        self.closed = True
        for i, connection in enumerate(self.connections):
            if i not in self.broken:
                try:
                    connection.send(('close',{}))
                except (OSError,EOFError):
                    pass
        deadline = time.monotonic()+5
        for process in self.processes:
            process.join(max(0,deadline-time.monotonic()))
            _stop_actor(process)
        for connection in self.connections:
            connection.close()
        self.temporary.cleanup()

    def __enter__(self):
        return self

    def __exit__(self,*args):
        self.close()


def serve_jsonl(num_envs=1, rpc_timeout=60, **options):
    """Local stdin/stdout RPC. Each input line receives exactly one response."""
    write = lambda value: print(json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')),flush=True)
    with VectorArena(num_envs,rpc_timeout=rpc_timeout,**options) as environments:
        write({'type':'ready','protocol':'arena-env-v1','num_envs':num_envs,
               'dt':DT,'action_repeat':options.get('action_repeat',2)})
        maximum = 16*1024*1024
        while True:
            raw = sys.stdin.buffer.readline(maximum+1)
            if not raw:
                break
            request_id = None
            try:
                if len(raw) > maximum:
                    while raw and not raw.endswith(b'\n'):
                        raw = sys.stdin.buffer.readline(maximum+1)
                    raise ValueError('Request exceeds 16 MiB')
                request = json.loads(raw,parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite JSON')))
                if not isinstance(request,dict):
                    raise ValueError('Request must be a JSON object')
                request_id = request.get('id')
                if request_id is not None and (isinstance(request_id,bool) or not isinstance(request_id,(str,int))):
                    request_id = None
                    raise ValueError('id must be a string or integer')
                operation = request.get('op')
                if operation == 'close':
                    write({'id':request_id,'ok':True,'type':'close'})
                    break
                ids = environments._ids(request.get('env_ids'))
                if operation == 'reset':
                    seeds = request.get('seeds',[42+i for i in ids])
                    if not isinstance(seeds,list):
                        raise ValueError('seeds must be a list')
                    scenarios = request.get('scenarios',[None]*len(ids))
                    if not isinstance(scenarios,list) or len(scenarios) != len(ids) or len(seeds) != len(ids):
                        raise ValueError('Supply one seed and scenario per selected environment')
                    payloads = [{'seed':seed,'scenario':scenario} for seed,scenario in zip(seeds,scenarios)]
                elif operation == 'step':
                    payloads = request.get('actions')
                    if not isinstance(payloads,list):
                        raise ValueError('actions must be a list in selected env-id order')
                elif operation == 'save_replay':
                    paths = request.get('paths')
                    if not isinstance(paths,list) or not all(isinstance(p,str) for p in paths):
                        raise ValueError('paths must be a list of filenames')
                    payloads = [{'path':p} for p in paths]
                else:
                    raise ValueError('op must be reset, step, save_replay or close')
                responses = environments.request(operation,payloads,ids)
                write({'id':request_id,'type':operation,'ok':all(r['ok'] for r in responses),'results':responses})
            except (ValueError,TypeError,KeyError) as exc:
                write({'id':request_id,'ok':False,'type':'error','error':str(exc)})
