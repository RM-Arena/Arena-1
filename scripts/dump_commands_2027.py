"""Dump the raw per-tick commands one side issues, next to its resulting motion.

Development aid for movement problems: prints the action fields the strategy returns
and how far the chassis actually moved, so a stall can be attributed to a command
rather than guessed from a replay.
"""
import argparse
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('red', type=Path)
    parser.add_argument('blue', type=Path)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--duration', type=int, default=40)
    parser.add_argument('--slots', default='')
    parser.add_argument('--from', dest='start', type=float, default=0.0)
    parser.add_argument('--every', type=int, default=2, help='decisions between reports')
    args = parser.parse_args()
    from rmuc_arena.runner import Battle
    from rmuc_arena.submissions import load_submission
    from rmuc_arena.seasons import default_lineup

    lineup = None
    for path in (args.red, args.blue):
        manifest, _ = load_submission(path)
        lineup = lineup or manifest.get('team_lineup') or default_lineup('2027')
    slots = set(args.slots.split(',')) if args.slots else None
    with Battle(str(args.red), str(args.blue), args.seed, args.duration, 'rmuc2027', 'trusted-local', .2,
                team_lineup=lineup, practice_lineup=True) as battle:
        positions, count = {}, 0
        while battle.match.status != 'finished':
            commands = battle.held_commands['red']
            frame = battle.step()
            if frame['time'] < args.start:
                continue
            count += 1
            if count % args.every:
                continue
            for r in frame['robots']:
                if r['team'] != 'red':
                    continue
                slot = str(r['slot'])
                if slots and slot not in slots:
                    continue
                action = commands.get(slot) or {}
                move = action.get('move') or (0, 0)
                last = positions.get(r['id'])
                step = 0.0 if not last else math.hypot(r['x'] - last[0], r['y'] - last[1])
                positions[r['id']] = (r['x'], r['y'])
                print(f"t={frame['time']:6.2f} r{slot} ({r['x']:5.2f},{r['y']:5.2f}) z{r['z']:.2f} "
                      f"v={math.hypot(r['vx'], r['vy']):4.2f} step={step:4.2f} "
                      f"cmd=({move[0]:+.2f},{move[1]:+.2f}) head={action.get('heading') if action.get('heading') is None else round(action['heading'], 2)} "
                      f"pow={action.get('power')} zones={','.join(r.get('last_raw_zones', [])) or '-'} "
                      f"hp{r['hp']:.0f} am{r['ammo']}")
        print('finished', battle.result()['winner'], battle.result()['reason'])


if __name__ == '__main__':
    main()
