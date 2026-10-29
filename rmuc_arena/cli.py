"""Command-line matches, parallel evaluation and persistent training actors."""
import argparse
import signal
import threading
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import sys

from . import __version__, seasons
from .paths import ROOT, data_path
from .replays import verify_replay


def emit(value, pretty=False):
    print(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2 if pretty else None),flush=True)


def _field_options(parser):
    parser.add_argument('--season',choices=['2027','2026'])
    parser.add_argument('--map',choices=['rmuc2027','rmuc2026'])
    parser.add_argument('--duration',type=int,default=420,help='1..420 simulation seconds; short runs are unranked')
    parser.add_argument('--lineup',help='Shared slot-to-model JSON object or JSON file')
    parser.add_argument('--settings',help='Battle settings JSON object or exported JSON file')


def _policy_options(parser):
    parser.add_argument('--trusted-local',action='store_true',help='Run your trusted strategy code locally; default: Docker isolation')
    parser.add_argument('--timeout',type=float,default=.2,help='Per-policy decision deadline in seconds (default: .2)')


def _run_options(parser, command):
    _field_options(parser); _policy_options(parser)
    parser.add_argument('--red',help='Submission directory or saved strategy key')
    parser.add_argument('--blue',help='Submission directory or saved strategy key')
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--games',type=int,help='Number of consecutive seeds (batch default: 4; otherwise 1)')
    group.add_argument('--seeds',type=int,nargs='+',help='Explicit reproducible seeds')
    parser.add_argument('--seed',type=int,default=42,help='First seed for --games')
    parser.add_argument('--swap-sides',action='store_true',help='Play every seed/configuration in both orientations')
    parser.add_argument('-j','--workers',type=int,default=1 if command == 'match' else min(4,os.cpu_count() or 1),help='Maximum simultaneous match processes')
    parser.add_argument('--output',type=Path,help='Run directory, or a single .json replay filename')
    parser.add_argument('--replays',choices=['none','all','errors'],help='Recording policy; default: none for parallel runs, all for legacy single-match output')
    parser.add_argument('--no-replay',action='store_true',help='Alias for --replays none')
    parser.add_argument('--resume',action='store_true',help='Skip completed games in an identical run; retry failed/incomplete jobs')
    parser.add_argument('--fail-fast',action='store_true',help='Stop scheduling after the first failed game or policy error')
    parser.add_argument('--match-timeout',type=float,help='Wall-clock limit per job, including policy startup')
    parser.add_argument('--jobs',type=Path,help='JSON list of heterogeneous match configurations')
    parser.add_argument('--mode',choices=['standard','deck'],default='standard')
    for team in ('red','blue'):
        parser.add_argument('--'+team+'-deck',help='JSON array/file of adaptive strategy keys; duplicates allowed')
        parser.add_argument('--'+team+'-control',choices=['independent','team'],default='independent')
        parser.add_argument('--'+team+'-team-strategy')
    parser.add_argument('--progress',action='store_true',help='Write human-readable progress to stderr; stdout remains JSONL')


def build_parser():
    parser=argparse.ArgumentParser(prog='rmuc-arena',description='Arena-1: strategy tools, parallel matches and reinforcement-learning actors')
    parser.add_argument('--version',action='version',version=__version__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('serve',help='Start the local API and 3D spectator')
    p.add_argument('--port',type=int,default=8765)
    p.add_argument('--submissions',default=str(data_path('submissions')))
    p.add_argument('--trusted-local',action='store_true')
    for command in ('run','batch','headless','match'):
        _run_options(sub.add_parser(command,help='Parallel match scheduler' if command != 'match' else 'Run and record one match'),command)
    p=sub.add_parser('env',help='Persistent parallel RL environments over stdin/stdout JSONL')
    _field_options(p); _policy_options(p)
    p.add_argument('-n','--num-envs',type=int,default=1)
    p.add_argument('--action-repeat',type=int,default=2,help='Even number of physics ticks per learner action')
    p.add_argument('--reward',choices=['terminal','score'],default='terminal')
    p.add_argument('--score-scale',type=float,default=.001)
    p.add_argument('--max-steps',type=int,help='Truncate an episode after this many learner decisions')
    p.add_argument('--lineups',help='Separate red/blue deployment lists (free-battle training)')
    p.add_argument('--record',action='store_true',help='Enable explicit save_replay requests')
    p.add_argument('--compact',action='store_true',help='Send static arena/rule summaries only on reset')
    p.add_argument('--full-state',action='store_true',help='Include privileged simulator state in info for centralized training')
    p.add_argument('--opponent',help='Optional saved opponent strategy; default: both teams controlled externally')
    p.add_argument('--team',choices=['red','blue'],default='red',help='Learner side when --opponent is supplied')
    p.add_argument('--rpc-timeout',type=float,default=60)
    p=sub.add_parser('strategies',help='Discover or inspect saved strategies without opening the GUI')
    choices=p.add_subparsers(dest='action',required=True)
    q=choices.add_parser('list');q.add_argument('--season',choices=['2026','2027']);q.add_argument('--mode',choices=['team','squad','distributed','adaptive','robot']);q.add_argument('--search',default='');q.add_argument('--source',choices=['bundled','remote','local'])
    q=choices.add_parser('show');q.add_argument('strategy')
    q=choices.add_parser('sync',help='Check and install one verified strategy-library update');q.add_argument('--cache',type=Path,default=data_path('.arena_data/strategy-library'))
    p=sub.add_parser('models',help='Inspect legal robot models and the default lineup')
    p.add_argument('--season',choices=['2026','2027'],default='2027');p.add_argument('--role',choices=['hero','heavy','engineer','infantry','aerial','sentry']);p.add_argument('--model',type=int)
    p=sub.add_parser('settings',help='Export the shipped defaults and parameter ranges')
    p.add_argument('--season',choices=['2026','2027'],default='2027');p.add_argument('--schema',action='store_true');p.add_argument('--output',type=Path)
    p=sub.add_parser('validate',help='Validate a saved submission and its source checksums');p.add_argument('strategy')
    p=sub.add_parser('replay',help='Inspect or verify a replay');p.add_argument('action',choices=['info','verify']);p.add_argument('path')
    p=sub.add_parser('verify-replay',help='Alias for replay verify');p.add_argument('replay')
    sub.add_parser('doctor',help='Report runtime paths and available backends as JSON')
    p=sub.add_parser('new-agent',help='Create a strategy development workspace');p.add_argument('output')
    p.add_argument('--mode',choices=['team','robot','distributed','adaptive'],default='team');p.add_argument('--robot',type=int)
    p.add_argument('--lineup');p.add_argument('--season',choices=['2027','2026']);p.add_argument('--minutes',type=int,default=90);p.add_argument('--training-url',default='http://127.0.0.1:8765')
    p=sub.add_parser('start-training',help='Start a development workspace clock');p.add_argument('workspace')
    p=sub.add_parser('refresh-agent',help='Refresh a workspace SDK and references');p.add_argument('workspace')
    p=sub.add_parser('submit',help='Validate and freeze a workspace submission');p.add_argument('workspace');p.add_argument('output')
    p=sub.add_parser('assemble',help='Assemble fixed-slot robot submissions');p.add_argument('output');p.add_argument('robots',nargs='+')
    return parser


def run_matches(args):
    from .batch import execute_jobs
    from .cli_options import make_spec, swap_spec
    from .catalog import strategy_index
    defaults={k:getattr(args,k) for k in ('red','blue','seed','duration','season','map','lineup','settings','trusted_local','timeout','mode','red_deck','blue_deck','red_control','blue_control','red_team_strategy','blue_team_strategy')}
    index=strategy_index()
    specs=[]
    if args.jobs:
        if args.games is not None or args.seeds is not None:
            raise ValueError('--jobs cannot be combined with --games or --seeds')
        entries=json.loads(args.jobs.read_text(encoding='utf-8'))
        if not isinstance(entries,list) or not entries:
            raise ValueError('--jobs requires a nonempty JSON list')
        allowed=set(defaults)|{'swap_sides'}
        for i,entry in enumerate(entries):
            if not isinstance(entry,dict) or set(entry)-allowed:
                raise ValueError(f'Invalid keys in job {i}')
            if 'swap_sides' in entry and not isinstance(entry['swap_sides'],bool):
                raise ValueError('swap_sides must be a JSON boolean')
            spec=make_spec({**defaults,'seed':args.seed+i,**entry},base=args.jobs.resolve().parent,index=index)
            specs.append(spec)
            if entry.get('swap_sides',args.swap_sides):specs.append(swap_spec(spec))
    else:
        games=args.games if args.games is not None else 4 if args.command == 'batch' else 1
        if not 1 <= games <= 10000:
            raise ValueError('games must be in [1,10000]')
        seeds=args.seeds if args.seeds is not None else range(args.seed,args.seed+games)
        if len(seeds)>10000:
            raise ValueError('At most 10000 seeds may be scheduled')
        template=make_spec({**defaults,'seed':seeds[0]},index=index)
        for seed in seeds:
            if isinstance(seed,bool) or not isinstance(seed,int) or not -(2**31)<=seed<2**31:
                raise ValueError('seed must be a signed 32-bit integer')
            spec={'options':{**template['options'],'seed':seed},'swapped':False}
            specs.append(spec)
            if args.swap_sides:specs.append(swap_spec(spec))
    output=args.output
    if output is None:
        legacy=len(specs)==1 and args.command in ('match','headless') and not args.no_replay and args.replays in (None,'all')
        output=Path('replays/match.json' if legacy else 'replays/'+args.command)
    single=output.suffix.lower()=='.json'
    if single and len(specs)!=1:
        raise ValueError('Multiple games require an output directory, not one .json file')
    if args.no_replay and args.replays not in (None,'none'):
        raise ValueError('--no-replay conflicts with --replays')
    replays='none' if args.no_replay else args.replays or ('all' if single else 'none')
    if single:
        if replays!='all':
            raise ValueError('A .json output filename requires --replays all; use a run directory for unrecorded games')
        if output.exists() and not args.resume:
            raise ValueError('Replay output exists; choose a new filename')
        specs[0]['replay_path']=str(output.resolve())
        output=output.with_suffix('.run')
    def completed(result):
        emit(result)
        if args.progress:
            print(f"[job {result['job_id']}] seed={result['seed']} swap={result['swapped']} {result['status']}",file=sys.stderr,flush=True)
    summary=execute_jobs(specs,output,workers=args.workers,replays=replays,resume=args.resume,
                         fail_fast=args.fail_fast,match_timeout=args.match_timeout,on_result=completed)
    if not (single and args.command in ('match','headless')):
        emit(summary)
    return 130 if summary['cancelled'] else 1 if summary['failed'] or summary['policy_errors'] or summary['completed']<summary['games'] or summary.get('error') else 0


def _main(argv=None):
    parser=build_parser();args=parser.parse_args(argv)
    try:
        if args.command in ('run','batch','headless','match'):
            return run_matches(args)
        if args.command=='serve':
            from .server import serve
            serve(args.port,'trusted-local' if args.trusted_local else 'docker',args.submissions)
        elif args.command=='env':
            from .cli_options import json_value
            from .catalog import resolve_strategy
            from .vector_env import serve_jsonl
            season=args.season or (seasons.season_of_map(args.map) if args.map else None)
            if args.map and seasons.season_of_map(args.map)!=season:raise ValueError('season and map disagree')
            serve_jsonl(args.num_envs,rpc_timeout=args.rpc_timeout,season=season,duration=args.duration,
                        team_lineup=json_value(args.lineup),lineups=json_value(args.lineups),battle_settings=json_value(args.settings),
                        action_repeat=args.action_repeat,reward=args.reward,score_scale=args.score_scale,max_steps=args.max_steps,
                        record=args.record,compact=args.compact,full_state=args.full_state,
                        opponent=str(resolve_strategy(args.opponent)) if args.opponent else None,team=args.team,
                        sandbox='trusted-local' if args.trusted_local else 'docker',timeout=args.timeout)
        elif args.command=='strategies':
            from .catalog import strategy_index, resolve_strategy, describe_strategy
            if args.action=='show':emit(describe_strategy(resolve_strategy(args.strategy)),True)
            elif args.action=='sync':
                from .strategy_library import StrategyLibrary
                library=StrategyLibrary(args.cache)
                library.enabled=True  # Explicit manual sync is independent of the background-update preference.
                try:status=library.sync()
                finally:library.shutdown()
                emit(status,True)
                return 1 if status.get('error') else 0
            else:
                entries=[]
                for item in strategy_index().values():
                    if args.season and item['season']!=args.season or args.mode and item['mode']!=args.mode or args.source and item['source']!=args.source:continue
                    value={**item,'path':str(item['path'])}
                    if args.search.casefold() not in json.dumps(value,ensure_ascii=False).casefold():continue
                    entries.append(value)
                emit(sorted(entries,key=lambda item:item['key']),True)
        elif args.command=='models':
            from .models import model_catalog
            models=model_catalog()
            selected={k:v for k,v in models.items() if seasons.legal(int(k),args.season) and (not args.role or v['role']==args.role) and (args.model is None or int(k)==args.model)}
            if args.model is not None and not selected:raise ValueError('Model is unavailable for this season/role')
            emit({'season':args.season,'default_lineup':seasons.default_lineup(args.season),'models':selected},True)
        elif args.command=='settings':
            from .battle_settings import defaults,schema
            value={'season':args.season,'fields':schema(args.season),'defaults':defaults(args.season)} if args.schema else defaults(args.season)
            if args.output:
                if args.output.exists():raise ValueError('Settings output already exists')
                args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            else:emit(value,True)
        elif args.command=='validate':
            from .catalog import resolve_strategy
            from .submissions import load_submission
            path=resolve_strategy(args.strategy);manifest,_=load_submission(path)
            emit({'valid':True,'path':str(path),'manifest':manifest},True)
        elif args.command in ('replay','verify-replay'):
            path=args.replay if args.command=='verify-replay' else args.path
            if args.command=='verify-replay' or args.action=='verify':emit(verify_replay(path),True)
            else:
                value=json.loads(Path(path).read_text(encoding='utf-8'))
                emit({k:v for k,v in value.items() if k not in ('frames','actions','static')},True)
        elif args.command=='doctor':
            from .engine import binary_path
            from .video_export import ffmpeg_executable
            try:binary=str(binary_path())
            except RuntimeError:binary=None
            emit({'version':__version__,'python':sys.executable,'engine':binary,'docker':shutil.which('docker'),
                  'mp4_encoder':ffmpeg_executable(),'cpus':os.cpu_count(),'seasons':seasons.summary()},True)
        else:
            from .submissions import assemble,scaffold,submit,start_training,refresh_workspace
            from .cli_options import json_value
            if args.command=='new-agent':
                lineup=json_value(args.lineup);season=args.season or (None if lineup else '2027')
                print(scaffold(args.output,args.mode,args.robot,minutes=args.minutes,training_url=args.training_url,team_lineup=lineup,season=season))
            elif args.command=='start-training':emit(start_training(args.workspace),True)
            elif args.command=='refresh-agent':print(refresh_workspace(args.workspace))
            elif args.command=='submit':emit(submit(args.workspace,args.output),True)
            elif args.command=='assemble':emit(assemble(args.robots,args.output,'2026' if len(args.robots)==6 else '2027'),True)
        return 0
    except KeyboardInterrupt:
        print('Interrupted',file=sys.stderr)
        return 130
    except (RuntimeError,ValueError,OSError,KeyError,TypeError) as exc:
        print(f'Error: {exc}',file=sys.stderr)
        return 1


@contextmanager
def _termination_signals():
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous=signal.getsignal(signal.SIGTERM)
    def interrupt(*args):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,interrupt)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM,previous)


def main(argv=None):
    with _termination_signals():
        return _main(argv)


if __name__=='__main__':
    raise SystemExit(main())
