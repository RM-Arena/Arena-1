"""Run one RMUC 2027 match and print a compact diagnostic trace.

Development aid: shows, per robot, where it is, whether it is moving, its health,
ammunition and which buff cards it currently activates, so a strategy's positioning
and logistics can be read without opening a replay.
"""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('red', type=Path)
    parser.add_argument('blue', type=Path)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--duration', type=int, default=120)
    parser.add_argument('--every', type=float, default=10.0)
    parser.add_argument('--teams', default='red,blue')
    args = parser.parse_args()
    from rmuc_arena.runner import Battle
    from rmuc_arena.submissions import load_submission
    from rmuc_arena.seasons import default_lineup

    lineup = None
    for path in (args.red, args.blue):
        manifest, _ = load_submission(path)
        lineup = lineup or manifest.get('team_lineup') or default_lineup('2027')
    watched = set(args.teams.split(','))
    previous = {}
    next_report = 0.0
    with Battle(str(args.red), str(args.blue), args.seed, args.duration, 'rmuc2027', 'trusted-local', .2,
                team_lineup=lineup, practice_lineup=True) as battle:
        while battle.match.status != 'finished':
            frame = battle.step()
            if frame['time'] < next_report:
                continue
            next_report = frame['time'] + args.every
            teams = {t: frame['teams'][t] for t in ('red', 'blue')}
            print(f"--- t={frame['time']:6.1f} control {teams['red']['control']:6.1f}/{teams['blue']['control']:6.1f} "
                  f"damage {teams['red']['attack_damage']:6.0f}/{teams['blue']['attack_damage']:6.0f} "
                  f"base {frame['bases']['red']['hp']:6.0f}/{frame['bases']['blue']['hp']:6.0f}")
            for name, snapshot in frame['positions'].items():
                print(f"      {name:13s} {snapshot['controller']:5s} {snapshot['control']:9s} p={snapshot.get('progress', 0):.1f}")
            for r in frame['robots']:
                if r['team'] not in watched:
                    continue
                last = previous.get(r['id'])
                step = 0.0 if not last else ((r['x'] - last[0]) ** 2 + (r['y'] - last[1]) ** 2) ** .5
                previous[r['id']] = (r['x'], r['y'])
                cards = ','.join(sorted(r.get('last_raw_zones', []))) or '-'
                drones = ''
                if r.get('drones'):
                    drones = ' drones[' + ' '.join(f"{d['state'][:4]}:{d['battery_wh']:.1f}" for d in r['drones']) + ']'
                print(f"   {r['team'][0]}{r['slot']:>2} {r['role'][:8]:8s} ({r['x']:5.1f},{r['y']:5.1f}) z{r['z']:.2f} "
                      f"hp{r['hp']:5.0f} am{r['ammo']:3d} heat{r['heat']:5.1f} "
                      f"{'ALIVE' if r['alive'] else 'DEAD ':5s} {'TIPPED' if r.get('tipped') else '      '} "
                      f"mv{step:4.1f} {'+'.join(r.get('last_raw_zones', [])) or '-':32s} "
                      f"{str(r.get('launcher') or '-'):10s} {str(r.get('posture') or '-'):7s}{drones}")
            for event in frame['events']:
                if event['type'] in ('destroy', 'outpost_destroyed', 'outpost_rebuilt', 'assembly_success',
                                     'launcher_installed', 'base_armor_opened', 'policy_error', 'drone_strike'):
                    print(f"   event {event['type']:20s} {event}")
        result = battle.result()
        print(f"=== winner={result['winner']} reason={result['reason']} time={result['time']}")
        print(f"    red  {result['teams']['red']}")
        print(f"    blue {result['teams']['blue']}")


if __name__ == '__main__':
    main()
