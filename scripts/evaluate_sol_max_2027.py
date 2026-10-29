"""Evaluate RMUC 2027 controllers on a selected runtime and both sides.

Uses the normal isolated policy workers and their 200 ms decision deadline.
Reports control degree first, then damage, stability and reproducible build hashes.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import inspect
import json
import multiprocessing
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

PROJECT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get('RMUC_EVAL_RUNTIME', PROJECT)).resolve()
sys.path.insert(0, str(ROOT))


def play(job):
    stop_file=os.environ.get('RMUC_EVAL_STOP_FILE')
    stop_file=Path(stop_file) if stop_file else None
    if stop_file is not None and stop_file.exists():raise SystemExit(143)
    policies=[]
    def terminate(signum,frame):
        # Battle.close may ask an already stopped engine for its digest before
        # closing workers. Reap only this job's registered policy processes
        # first, including policies still in their initialization handshake.
        for policy in policies:
            process=getattr(policy,'process',None)
            if process is not None:
                try:
                    if process.poll() is None:os.killpg(process.pid,signal.SIGTERM)
                    process.wait(timeout=3.)
                except (OSError,subprocess.TimeoutExpired):
                    try:process.kill();process.wait(timeout=3.)
                    except (OSError,subprocess.TimeoutExpired):pass
        raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM,terminate)
    from rmuc_arena import runner
    from rmuc_arena.runner import Battle
    original_policy=runner.Policy
    class RegisteredPolicy(original_policy):
        def __init__(self,*args,**kwargs):
            policies.append(self)
            super().__init__(*args,**kwargs)
    runner.Policy=RegisteredPolicy
    from rmuc_arena.submissions import load_submission
    from rmuc_arena.seasons import default_lineup
    candidate, opponent, seed, side, duration, lineup, native = job
    manifest, _ = load_submission(candidate)
    lineup = lineup or manifest.get('team_lineup') or default_lineup('2027')
    red, blue = (candidate, opponent) if side == 'red' else (opponent, candidate)
    other = 'blue' if side == 'red' else 'red'
    started = time.monotonic()
    timeline, events, activity, decision_ms, action_errors = [], [], {}, [], []
    opponent_manifest, _ = load_submission(opponent)
    last_positions = {}
    options={'record':False} if 'record' in inspect.signature(Battle).parameters else {}
    try:
        battle=Battle(red, blue, seed, duration, 'rmuc2027', 'trusted-local', .2,
                      team_lineup=lineup, practice_lineup=True, **options)
    finally:
        runner.Policy=original_policy
    with battle:
        actual_lineups = None
        if native:
            from rmuc_arena.engine import Match
            sources = {side: manifest, other: opponent_manifest}
            actual_lineups = {team: [{'slot': int(slot), 'model': model} for slot, model in m['team_lineup'].items()]
                              for team, m in sources.items()}
            # Unranked native-hardware test: replace only the initial world,
            # before any observation or decision, and keep the normal workers,
            # scheduler, rules, timers and actions untouched.
            battle.match.close()
            battle.match = Match(seed, duration, 'rmuc2027', lineups=actual_lineups)
            battle.frames[0] = battle.match.snapshot()
            battle.metadata.pop('team_lineup', None)
            battle.metadata.update(lineups=actual_lineups, test_match=True, match_mode='native-hardware-validation')
            for team, units in actual_lineups.items():
                observed = {r['slot']: r['model_slot'] for r in battle.match.robots if r['team'] == team}
                assert observed == {u['slot']: u['model'] for u in units}
        for team, _, policy in battle.policies:
            if team == side:
                decide = policy.decide
                def measured(obs, decide=decide):
                    begin = time.perf_counter()
                    result = decide(obs)
                    decision_ms.append((time.perf_counter() - begin) * 1000)
                    return result
                policy.decide = measured
        while battle.match.status != 'finished':
            if stop_file is not None and stop_file.exists():raise SystemExit(143)
            frame = battle.step()
            for r in frame['robots']:
                if r['team'] != side or r['role'] == 'aerial':
                    continue
                a = activity.setdefault(str(r['slot']), {'tipped_s': 0., 'dead_s': 0., 'empty_s': 0.,
                    'enemy_half_s': 0., 'healthy_enemy_half_s': 0., 'healthy_s': 0., 'distance_m': 0.,
                    'jumps': 0, 'terrain_buffs': {}, 'self_righted': 0, 'weak_s': 0., 'objective_s': 0.})
                forward = r['x'] > 14 if side == 'red' else r['x'] < 14
                healthy = r['alive'] and not r.get('weak') and r['hp'] >= r['max_hp'] * .55
                a['weak_s'] += .05 * bool(r['alive'] and r.get('weak'))
                a['objective_s'] += .05 * bool(r['alive'] and any(r['id'] in z.get('occupants',[]) for k,z in frame.get('zones',{}).items() if k.endswith(('_central','_outpost','_base','_fortress'))))
                a['enemy_half_s'] += .05 * bool(r['alive'] and forward)
                a['healthy_enemy_half_s'] += .05 * bool(healthy and forward)
                a['healthy_s'] += .05 * bool(healthy)
                previous = last_positions.get(r['id'])
                if previous and previous[2] and r['alive']:
                    step = ((r['x'] - previous[0]) ** 2 + (r['y'] - previous[1]) ** 2) ** .5
                    if step < 1.:  # Exclude revive teleports from distance.
                        a['distance_m'] += step
                last_positions[r['id']] = (r['x'], r['y'], r['alive'])
                a['tipped_s'] += .05 * bool(r['alive'] and r.get('tipped'))
                a['dead_s'] += .05 * (not r['alive'])
                a['empty_s'] += .05 * bool(r['alive'] and r['ammo'] == 0)
            for event in frame['events']:
                if event['type']=='invalid_action':action_errors.append(event)
                unit = next((r for r in frame['robots'] if r['id'] == event.get('robot') and r['team'] == side), None)
                a = activity.get(str(unit['slot'])) if unit else None
                if a is not None:
                    if event['type'] == 'jump':
                        a['jumps'] += 1
                    elif event['type'] == 'self_righted':
                        a['self_righted'] += 1
                    elif event['type'] == 'terrain_buff':
                        kind = event['kind']
                        a['terrain_buffs'][kind] = a['terrain_buffs'].get(kind, 0) + 1
                if event['type'] in ('assembly_success', 'destroy', 'outpost_rebuilt', 'rune_activated',
                                     'base_armor_opened', 'drone_strike', 'launcher_installed', 'policy_error',
                                     'jump', 'terrain_buff', 'self_righted', 'control_changed', 'invalid_action'):
                    events.append(event)
            if frame['tick'] % 400 == 0 or frame['status'] == 'finished':
                timeline.append({'time': frame['time'], 'positions': frame.get('positions'),
                    'teams': {t: {k: frame['teams'][t].get(k) for k in
                        ('control', 'attack_damage', 'resources', 'completed_difficulties')} for t in ('red', 'blue')},
                    'robots': [{k: r.get(k) for k in ('id', 'slot', 'role', 'x', 'y', 'z', 'hp', 'ammo', 'heat',
                        'alive', 'tipped', 'launcher', 'damage', 'level', 'carried_units', 'posture', 'drones',
                        'crossing_firsts', 'defense_buff', 'weak', 'heading', 'vx', 'vy')}
                        for r in frame['robots']],
                    'outposts': {t: {k: frame['outposts'][t].get(k) for k in ('hp', 'owner')} for t in ('red', 'blue')}})
                if frame['tick'] % 1200 == 0:
                    print(f"progress {Path(candidate).name} {side} seed={seed} t={frame['time']:.0f} "
                          f"control={frame['teams'][side]['control']:.0f}/{frame['teams'][other]['control']:.0f}", flush=True)
                    progress = PROJECT / 'build/sol-max-v2/progress'
                    progress.mkdir(parents=True, exist_ok=True)
                    (progress / f'{Path(candidate).name}-{Path(opponent).name}-{seed}-{side}-{frame["engine_hash"][:8]}-{native}.json').write_text(
                        json.dumps({'timeline': timeline, 'events': events, 'diagnostics': battle.diagnostics}))
        result = battle.result()
        timings = sorted(decision_ms)
        record = {'opponent': Path(opponent).name, 'seed': seed, 'side': side,
            'outcome': 'win' if result['winner'] == side else 'draw' if result['winner'] is None else 'loss',
            'time': result['time'], 'reason': result['reason'], 'candidate': result['teams'][side],
            'opponent_final': result['teams'][other], 'policy_errors': result['policy_errors'],
            'valid': not battle.diagnostics and not action_errors, 'action_errors': action_errors,
            'diagnostics': battle.diagnostics, 'timeline': timeline, 'events': events,
            'activity': activity, 'digest': result['digest'], 'lineup': lineup,
            'versions': {t: battle.metadata['teams'][t]['version'] for t in ('red', 'blue')},
            'agents': {t: battle.metadata['teams'][t].get('agent') for t in ('red', 'blue')},
            'engine_hash': frame['engine_hash'], 'rules_hash': frame['rules_hash'],
            'sdk_hash': hashlib.sha256((ROOT / 'rmuc_arena/sdk.py').read_bytes()).hexdigest(),
            'decision_ms': {'max': max(timings, default=0), 'p99': timings[min(len(timings)-1, int(len(timings)*.99))] if timings else 0},
            'wall_seconds': time.monotonic() - started, 'native_hardware': native, 'actual_lineups': actual_lineups, 'replay_recording': getattr(battle,'record',True)}
    record['logs'] = {t: list(p.logs) for t, _, p in battle.policies if p.logs}
    return record


def main():
    from rmuc_arena.submissions import load_submission, save_submission, manifest_season
    from rmuc_arena.showcase import load_profile, load_showcase
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('candidate', type=Path)
    p.add_argument('opponents', nargs='+', type=Path)
    p.add_argument('--seeds', nargs='+', type=int, default=[17, 43, 91])
    p.add_argument('--sides', nargs='+', choices=['red', 'blue'], default=['red', 'blue'])
    p.add_argument('--duration', type=int, choices=range(1, 421), default=420, metavar='1..420')
    p.add_argument('--lineup', type=json.loads)
    p.add_argument('--native', action='store_true', help='Unranked test with both registered native lineups')
    p.add_argument('--resume', action='store_true', help='Skip already recorded opponent/seed/side/version jobs')
    p.add_argument('--jobs', type=int, choices=[1, 2, 4], default=1)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = json.loads(args.output.read_text()) if args.resume and args.output.exists() else {'candidate': str(args.candidate), 'duration': args.duration, 'matches': []}
    if args.resume and report['matches']:
        if report.get('runtime')!=str(ROOT) or report.get('native_hardware')!=args.native or report['duration']!=args.duration:
            raise ValueError('Cannot resume with changed runtime, hardware mode or duration')
    report['runtime'] = str(ROOT)
    report['native_hardware'] = args.native
    report['evaluation_host_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='arena-2027-eval-') as temporary:
        def snapshot(path):
            manifest, entries = load_submission(path)
            if manifest_season(manifest) != '2027':
                raise ValueError('Only RMUC 2027 submissions are supported')
            target = Path(temporary) / (path.name + '-' + manifest['version'])
            if not target.exists():
                save_submission(target, manifest['mode'], entries, manifest.get('robot'),
                    team_lineup=manifest.get('team_lineup'), season='2027',
                    showcase=load_showcase(path), profile=load_profile(path))
            return str(target)
        candidate = snapshot(args.candidate)
        opponents = [snapshot(path) for path in args.opponents]
        done={(r['opponent'],r['seed'],r['side'],r['versions'][r['side']]) for r in report['matches'] if r['valid']}
        version=load_submission(candidate)[0]['version']
        if any(r['versions'][r['side']]!=version for r in report['matches']):
            raise ValueError('Cannot mix candidate versions in a resumed report')
        report['candidate_version']=version
        jobs = [(candidate, opponent, seed, side, args.duration, args.lineup, args.native)
                for opponent in opponents for seed in args.seeds for side in args.sides
                if (Path(opponent).name,seed,side,version) not in done]
        with ProcessPoolExecutor(max_workers=args.jobs, mp_context=multiprocessing.get_context('spawn'),
                                 max_tasks_per_child=1) as pool:
            for future in as_completed([pool.submit(play, job) for job in jobs]):
                record = future.result()
                report['matches'].append(record)
                a, b = record['candidate'], record['opponent_final']
                print(f"{record['opponent']} seed={record['seed']} {record['side']} {record['outcome']} "
                      f"control={a['control']:.1f}/{b['control']:.1f} damage={a['attack_damage']:.0f}/{b['attack_damage']:.0f} "
                      f"errors={record['policy_errors']} wall={record['wall_seconds']:.1f}s", flush=True)
                report['summary'] = {key: sum(r['outcome'] == key and r['valid'] for r in report['matches']) for key in ('win', 'draw', 'loss')}
                report['summary']['valid_games'] = sum(r['valid'] for r in report['matches'])
                report['summary']['invalid_games'] = sum(not r['valid'] for r in report['matches'])
                report['summary']['policy_errors'] = sum(r['policy_errors'] for r in report['matches'])
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report.get('summary', {})), flush=True)


if __name__ == '__main__':
    main()
