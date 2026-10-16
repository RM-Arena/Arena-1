"""Step 5 dev harness: build submissions from strategy sources and run evaluation matches."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rmuc_arena.runner import Battle
from rmuc_arena.submissions import save_submission, load_submission
from rmuc_arena.seasons import default_lineup

LINEUP = default_lineup('2027')
BUILD = ROOT / 'build' / 'step5'


def minimal_showcase(title, tagline):
    return {
        "format": "rmuc-showcase-v1",
        "title": title,
        "tagline": tagline,
        "summary": "Step 5 Preview development entry.",
        "style": {"aggression": 50, "defense": 50, "economy": 50, "objective": 50,
                  "teamwork": 50, "adaptability": 50},
        "phases": [{"from": 0, "to": 420, "title": "整局", "goal": "控制度优先", "focus": "objective"}],
        "units": [],
        "rules": [],
        "priorities": [],
        "strengths": [],
        "weaknesses": [],
        "generated_by": {"provider": "unknown", "model": "Step 5 Preview"},
    }


def build(source, name):
    """Create a submission directory from a strategy.py source path."""
    out = BUILD / 'subs' / name
    if out.exists():
        import shutil
        shutil.rmtree(out)
    save_submission(out, 'team', {'team': Path(source)}, team_lineup=LINEUP,
                    showcase=minimal_showcase(name, 'dev'), season='2027')
    return out


def play(candidate, opponent, seed, duration, side='red'):
    red, blue = (candidate, opponent) if side == 'red' else (opponent, candidate)
    me = 'red' if side == 'red' else 'blue'
    other = 'blue' if side == 'red' else 'red'
    started = time.monotonic()
    with Battle(red, blue, seed, duration, 'rmuc2027', 'trusted-local', .2,
                team_lineup=LINEUP, practice_lineup=True) as battle:
        battle.run()
        result = battle.result()
        errors = result['policy_errors']
        valid = not battle.diagnostics
    wall = time.monotonic() - started
    a, b = result['teams'][me], result['teams'][other]
    return {
        'opponent': Path(opponent).name, 'seed': seed, 'side': side,
        'outcome': 'win' if result['winner'] == me else 'draw' if result['winner'] is None else 'loss',
        'reason': result['reason'], 'time': result['time'],
        'control': round(a['control'], 1), 'control_opp': round(b['control'], 1),
        'damage': round(a['attack_damage']), 'damage_opp': round(b['attack_damage']),
        'base_hp': round(a.get('base_lowest_hp', 0)), 'base_hp_opp': round(b.get('base_lowest_hp', 0)),
        'policy_errors': errors, 'valid': valid, 'wall': round(wall, 1),
    }


def _play_job(job):
    cand, opp, seed, duration, side = job
    rec = play(cand, opp, seed, duration, side)
    rec['candidate'] = Path(cand).name
    return rec


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('candidates', nargs='+', help='strategy.py paths or names in build/step5/src')
    p.add_argument('--opponents', nargs='+', required=True)
    p.add_argument('--seeds', nargs='+', type=int, default=[42])
    p.add_argument('--sides', nargs='+', default=['red', 'blue'])
    p.add_argument('--duration', type=int, default=120)
    p.add_argument('--tag', default='dev')
    p.add_argument('--jobs', type=int, default=3)
    args = p.parse_args()

    src_dir = BUILD / 'src'
    candidates = []
    for c in args.candidates:
        path = Path(c)
        if not path.is_file():
            path = src_dir / (c if c.endswith('.py') else c + '.py')
        candidates.append(build(path, path.stem))

    opponents = []
    for o in args.opponents:
        path = Path(o)
        if not path.is_dir():
            path = ROOT / 'examples' / o
        opponents.append(path)

    records = []
    jobs = [(cand, opp, seed, args.duration, side)
            for cand in candidates for opp in opponents
            for seed in args.seeds for side in args.sides]
    if args.jobs > 1:
        from concurrent.futures import ProcessPoolExecutor
        import multiprocessing
        with ProcessPoolExecutor(max_workers=args.jobs,
                                 mp_context=multiprocessing.get_context('spawn')) as pool:
            for rec in pool.map(_play_job, jobs):
                records.append(rec)
                print(f"{rec['candidate']:28s} vs {rec['opponent']:28s} seed={rec['seed']:4d} {rec['side']:4s} "
                      f"{rec['outcome']:4s} ctrl={rec['control']:6.1f}/{rec['control_opp']:6.1f} "
                      f"dmg={rec['damage']:5.0f}/{rec['damage_opp']:5.0f} err={rec['policy_errors']} "
                      f"wall={rec['wall']}s", flush=True)
    else:
        for job in jobs:
            rec = _play_job(job)
            records.append(rec)
            print(f"{rec['candidate']:28s} vs {rec['opponent']:28s} seed={rec['seed']:4d} {rec['side']:4s} "
                  f"{rec['outcome']:4s} ctrl={rec['control']:6.1f}/{rec['control_opp']:6.1f} "
                  f"dmg={rec['damage']:5.0f}/{rec['damage_opp']:5.0f} err={rec['policy_errors']} "
                  f"wall={rec['wall']}s", flush=True)
    out = BUILD / f'eval-{args.tag}.json'
    out.write_text(json.dumps(records, ensure_ascii=False, indent=1))
    summary = {}
    for rec in records:
        key = (rec['candidate'], rec['opponent'])
        s = summary.setdefault(key, {'win': 0, 'draw': 0, 'loss': 0, 'invalid': 0})
        s[rec['outcome']] += 1
        s['invalid'] += 0 if rec['valid'] else 1
    print('\n=== summary ===')
    for (cand, opp), s in sorted(summary.items()):
        print(f"{cand:28s} vs {opp:28s} W{s['win']}-D{s['draw']}-L{s['loss']} invalid={s['invalid']}")
    print(f'\nsaved {out}')


if __name__ == '__main__':
    main()
