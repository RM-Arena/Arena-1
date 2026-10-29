"""Bounded multi-process match scheduling with resumable JSONL results."""
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from contextlib import contextmanager
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import signal
import tempfile
import time

from . import __version__
from .catalog import StrategySnapshots
from .engine import Match
from .paths import ROOT
from .platform_support import file_lock
from .runner import Battle

_STOP = None


def _initialize(stop):
    global _STOP
    _STOP = stop
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def _play(job):
    started = time.monotonic()
    wall_started = time.time()
    identity = {k: job[k] for k in ('job_id', 'index', 'seed', 'swapped')}
    try:
        options = dict(job['options'])
        record = job['replays'] != 'none'
        timeout = job.get('match_timeout')
        with Battle(**options, record=record, stop_event=_STOP,
                    deadline=started+timeout if timeout else None) as battle:
            result = battle.run()
            status = 'policy_error' if result['policy_errors'] else 'ok'
            if result['reason'] == 'stopped':
                status = 'cancelled' if _STOP is not None and _STOP.is_set() else 'timeout'
            replay = None
            if record and (job['replays'] == 'all' or result['policy_errors'] or status != 'ok'):
                replay = job['replay']
                battle.save(replay)
            a_side = 'blue' if job['swapped'] else 'red'
            outcome = 'draw' if result['winner'] is None else 'win' if result['winner'] == a_side else 'loss'
            return {'type': 'match', **identity, 'status': status, 'outcome': outcome,
                    **result, 'replay': replay, 'metadata': battle.metadata,
                    'started_at': wall_started, 'finished_at': time.time(),
                    'wall_seconds': time.monotonic()-started, 'worker_pid': os.getpid()}
    except Exception as exc:
        return {'type': 'match', **identity, 'status': 'cancelled' if _STOP is not None and _STOP.is_set() else 'timeout' if job.get('match_timeout') and time.monotonic()-started >= job['match_timeout'] else 'error',
                'error': f'{type(exc).__name__}: {exc}', 'started_at':wall_started, 'finished_at':time.time(), 'wall_seconds': time.monotonic()-started,
                'worker_pid': os.getpid(), 'replay': None}


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'), sort_keys=True, default=lambda v: str(v) if isinstance(v,Path) else (_ for _ in ()).throw(TypeError('Not JSON serializable')))


def _atomic_json(path, value):
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(_json(value)+'\n', encoding='utf-8')
    temporary.replace(path)


def _summary(results, total, started, workers, cancelled):
    valid = [r for r in results.values() if r['status'] == 'ok' and not r.get('policy_errors')]
    return {'type': 'summary', 'format': 'arena-batch-v1', 'games': total,
            'completed': len(results), 'succeeded': sum(r['status'] == 'ok' for r in results.values()),
            'failed': sum(r['status'] in ('error', 'timeout', 'policy_error') for r in results.values()),
            'cancelled': cancelled, 'unfinished': total-len(results), 'valid_games': len(valid),
            'strategy_a_wins': sum(r['outcome'] == 'win' for r in valid),
            'strategy_b_wins': sum(r['outcome'] == 'loss' for r in valid),
            'draws': sum(r['outcome'] == 'draw' for r in valid),
            'policy_errors': sum(r.get('policy_errors', 0) for r in results.values()),
            'workers': workers, 'wall_seconds': time.monotonic()-started}


def execute_jobs(specs, output, *, workers=1, replays='none', resume=False,
                 fail_fast=False, match_timeout=None, on_result=lambda result: None):
    """Stream completion-order results; workers never share simulator or policy state."""
    if not specs or len(specs) > 10000:
        raise ValueError('A run requires 1..10000 match jobs')
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 128:
        raise ValueError('workers must be in [1,128]')
    if replays not in ('none', 'all', 'errors'):
        raise ValueError('replays must be none, all or errors')
    if match_timeout is not None and (not isinstance(match_timeout, (int, float)) or not 0 < match_timeout <= 86400):
        raise ValueError('match timeout must be in (0,86400]')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Separate invocations cannot append to the same run journal at once.
    with file_lock(output/'.run.lock'):
        return _execute(specs, output, workers, replays, resume, fail_fast, match_timeout, on_result)


def _execute(specs, output, workers, replays, resume, fail_fast, match_timeout, on_result):
    started, cancelled, results = time.monotonic(), False, {}
    run_error = None
    workers = min(workers, len(specs))
    with tempfile.TemporaryDirectory(prefix='arena-batch-') as temporary:
        snapshots = StrategySnapshots(temporary)
        jobs = []
        for i, spec in enumerate(specs):
            options = dict(spec['options'])
            for team in ('red', 'blue'):
                if options.get(team):
                    options[team] = str(snapshots.freeze(options[team]))
            for key in ('decks', 'free_team_strategies'):
                if options.get(key):
                    options[key] = {team: [str(snapshots.freeze(p)) for p in paths] if key == 'decks'
                                    else str(snapshots.freeze(paths)) for team, paths in options[key].items()}
            jobs.append({'job_id': f'{i:06d}', 'index': i, 'seed': options['seed'],
                         'swapped': spec.get('swapped', False), 'options': options,
                         'replays': replays, 'replay': spec.get('replay_path',str(output/'replays'/f'{i:06d}.json')),
                         'match_timeout': match_timeout})
        # Fingerprints reflect the exact engine/rules/SDK, configuration and frozen sources.
        with Match(duration=1, map_name=specs[0]['options']['map_name']) as probe:
            frame = probe.snapshot()
        config = {'format': 'arena-batch-v1', 'client_version': __version__, 'jobs': specs,
                  'sources': snapshots.metadata(), 'rules_hash': frame['rules_hash'],
                  'engine_hash': frame['engine_hash'],
                  'sdk_hash': hashlib.sha256((ROOT/'rmuc_arena/sdk.py').read_bytes()).hexdigest(),
                  'runtime_hash': hashlib.sha256(b''.join((ROOT/'rmuc_arena'/name).read_bytes() for name in ('runner.py','worker.py','communication.py','action_protocol.py','decks.py'))).hexdigest(),
                  'replays': replays, 'match_timeout': match_timeout}
        fingerprint = hashlib.sha256(_json(config).encode()).hexdigest()
        manifest = {**config, 'fingerprint': fingerprint}
        manifest_path, journal = output/'run.json', output/'results.jsonl'
        known_jobs={job['job_id']:job for job in jobs}
        if manifest_path.exists():
            if not resume:
                raise ValueError('Output already contains a run; choose another directory or use --resume')
            previous = json.loads(manifest_path.read_text(encoding='utf-8'))
            if previous.get('fingerprint') != fingerprint:
                raise ValueError('Cannot resume: jobs, strategies, settings, SDK or engine changed')
            if journal.exists():
                # A crash can leave one partial final line. Repair only that tail before appending.
                raw = journal.read_bytes()
                complete = raw[:raw.rfind(b'\n')+1]
                if complete != raw:
                    journal.write_bytes(complete)
                for line in complete.splitlines():
                    row = json.loads(line)
                    if row['job_id'] not in known_jobs:
                        raise ValueError('Journal contains an unknown job')
                    job=known_jobs[row['job_id']]
                    if any(row.get(key)!=job[key] for key in ('index','seed','swapped')):
                        raise ValueError('Journal job identity does not match the run manifest')
                    results[row['job_id']] = row
        else:
            if resume:
                raise ValueError('Cannot resume: run.json does not exist')
            if journal.exists():
                raise ValueError('Output already contains a result journal')
            _atomic_json(manifest_path, manifest)
        # Failed/interrupted jobs are retried on resume; successful jobs are never replayed.
        pending = iter(job for job in jobs if results.get(job['job_id'], {}).get('status') != 'ok')
        context = multiprocessing.get_context('spawn')
        stop = context.Event()
        executor = ProcessPoolExecutor(max_workers=workers, mp_context=context,
                                       initializer=_initialize, initargs=(stop,))
        active = {}
        with journal.open('a', encoding='utf-8', newline='\n') as stream:
            def submit_next():
                job = next(pending, None)
                if job is not None:
                    active[executor.submit(_play, job)] = job
            try:
                for _ in range(workers):
                    submit_next()
                while active:
                    done, _ = wait(active, timeout=.2, return_when=FIRST_COMPLETED)
                    for future in done:
                        job = active.pop(future)
                        try:
                            result = future.result()
                        except Exception as exc:
                            result = {'type': 'match', **{k:job[k] for k in ('job_id','index','seed','swapped')},
                                      'status': 'error', 'error': f'Worker failed: {exc}', 'replay': None}
                        results[result['job_id']] = result
                        stream.write(_json(result)+'\n'); stream.flush()
                        on_result(result)
                        if fail_fast and (result['status'] != 'ok' or result.get('policy_errors')):
                            stop.set()
                        if not stop.is_set():
                            submit_next()
            except KeyboardInterrupt:
                cancelled = True
                stop.set()
                for future in active:
                    future.cancel()
            except Exception as exc:
                run_error = f'{type(exc).__name__}: {exc}'
                stop.set()
            finally:
                stop.set()
                executor.shutdown(wait=True, cancel_futures=True)
        summary = _summary(results, len(jobs), started, workers, cancelled)
        if run_error:
            summary['error'] = run_error
        _atomic_json(output/'summary.json', summary)
        return summary
