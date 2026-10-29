"""Freeze reproducible role-counter opponents for an internal Sol Max league."""
import argparse
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from rmuc_arena.submissions import load_submission,save_submission
from rmuc_arena.showcase import load_profile,load_showcase

LAYER='''
# Internal league role counter; shares mechanics, uses a separate allocation.
_POOL_FIGHTER=max_fighter
_POOL_HOLD=max_hold
_POOL_MODE={mode!r}

def pool_goal(robot,ctx):
    slot=robot['slot']
    if _POOL_MODE=='wave':
        goal=max_local(ctx,(17.1,{{3:6.2,4:7.7,7:9.1}}[slot]))
    elif _POOL_MODE=='double_raid':
        goal=max_local(ctx,(10.8,9.25) if slot==4 else (23.9,7.8) if slot==3 else (27.,6.4))
    elif _POOL_MODE=='split_guard':
        goal=max_local(ctx,(10.8,9.25) if slot==3 else (17.1,8.1) if slot==4 else (27.,6.4))
    elif _POOL_MODE=='encirclement':
        goal=max_local(ctx,(10.8,9.25) if slot==4 else (23.9,7.8) if slot==3 else (27.2,5.4))
    else:
        home=ctx.controls(f'{{ctx.team}}_outpost')
        front=ctx.controls(f'{{ctx.enemy}}_outpost')
        if slot==4:goal=max_local(ctx,(10.8,9.25))
        elif slot==3 and not home:goal=outpost_card_spot(ctx,ctx.team)
        elif slot==7 and home and front and ctx.enemy not in ctx.positions[f'{{ctx.enemy}}_base']['active']:
            goal=max_local(ctx,(27.,6.4))
        else:goal=max_local(ctx,(17.1,9.1 if slot==3 else 7.7))
    return goal

def max_hold(robot,goal,ctx,tolerance=.18):
    if robot['role'] in ('infantry','sentry') and not robot.get('weak') \
            and not ctx.state.get('max_recovery',{{}}).get(str(robot['slot'])) \
            and (ctx.time>=25 or leg_memory(robot,ctx.obs,ctx.memory).get('entry_done')):
        goal=pool_goal(robot,ctx)
    return _POOL_HOLD(robot,goal,ctx,tolerance)

def pool_fighter(robot,ctx):
    # Allocate the destination before navigation. Calling a second navigator
    # after the parent corrupts jump locks and stall history in a strong counter.
    fields=_POOL_FIGHTER(robot,ctx)
    if robot.get('weak') or ctx.state.get('max_recovery',{{}}).get(str(robot['slot'])):
        return fields
    goal=pool_goal(robot,ctx)
    if robot['role']=='sentry' and ctx.time >= (robot.get('posture_ready_at') or 0):
        threatened=ctx.time-robot.get('last_damage_time',-99)<2.
        close=any(e['alive'] and not e.get('invulnerable') and distance(e,(robot['x'],robot['y']))<6. for e in ctx.obs['enemies'])
        fields['posture']='attack' if close and robot['hp']>robot['max_hp']*.5 else 'defense' if threatened or distance(robot,goal)<1. else 'move'
    return fields

ROLES.update(infantry=pool_fighter,sentry=pool_fighter)
'''


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--base',type=Path,default=ROOT/'examples/gpt61_sol_max_2027')
 p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();manifest,entries=load_submission(a.base)
 policy=entries['team'].read_text()
 with tempfile.TemporaryDirectory(prefix='sol-max-league-') as temp:
  for mode in ('wave','double_raid','split_guard','rotation','encirclement'):
   name='sol_max_'+mode
   path=a.output/name
   if path.exists():raise ValueError('Opponent snapshots are immutable: '+str(path))
   source=Path(temp)/(name+'.py');source.write_text(policy+'\n'+LAYER.format(mode=mode))
   profile,showcase=load_profile(a.base),load_showcase(a.base)
   profile.update(author='GPT-6.1-Sol-Max internal league',display_name='内部对手 · '+mode,
       description='Frozen role counter derived from '+manifest['version']+'. Not a separate external model.')
   showcase.update(title=profile['display_name'],summary=profile['description'])
   save_submission(path,'team',{'team':source},team_lineup=manifest['team_lineup'],season='2027',profile=profile,showcase=showcase)
   print(name,load_submission(path)[0]['version'])

if __name__=='__main__':main()
