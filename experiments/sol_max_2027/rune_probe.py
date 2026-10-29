import json,os,sys,types
from pathlib import Path
from unittest.mock import patch
PROJECT=Path(__file__).resolve().parents[2]
RUNTIME=Path(os.environ.get('RMUC_EVAL_RUNTIME',PROJECT))
sys.path.insert(0,str(RUNTIME))
from rmuc_arena import sdk
from rmuc_arena.engine import Match
from rmuc_arena.models import mirrored_lineups
p=types.ModuleType('rune_probe')
with patch.dict(sys.modules,{'sdk':sdk}):exec((PROJECT/'examples/gpt61_sol_max_2027/strategy.py').read_text(),p.__dict__)
exec((Path(__file__).with_name('rune_control.py')).read_text(),p.__dict__)
lineup=json.loads((PROJECT/'examples/gpt61_sol_max_2027/manifest.json').read_text())['team_lineup']
states={t:{} for t in ('red','blue')};records=[];commands={};events=[]
with Match(211,205,'rmuc2027',lineups=mirrored_lineups(lineup,'2027')) as m:
 while m.status!='finished':
  if m.tick%2==0:
   commands={}
   for team,state in states.items():
    o=m.observation(team);c=p.Context(o,state);commands[team]={}
    for r in o['robots']:
     if r['slot'] in (1,6):f=p.decide(r,c)
     elif r['slot'] in (3,4,7):
      f=p.highland_entry(r,c) if o['time']<15 else None
      if f is None:f=p.max_hold(r,p.max_local(c,(10.6,6.2) if r['slot']==4 and o['time']>=165. else (10.8,9.25) if r['slot']==4 else (11.5,9.7) if r['slot']==3 else (12.,9.6)),c)
      f.update(p.max_logistics(r,c));f.update(fire=False)
      if o['tick']==0 and r['role']=='infantry':f['profile']={'chassis':'hp','weapon':'cooling'}
      if r['slot']==4 and o['time']>=178.:f.update(p.rune_trial_fields(r,c))
     else:continue
     commands[team][str(r['slot'])]=sdk.action(**f)
    if m.tick%20==0 and o['time']>=178.:
     r=next(r for r in o['robots'] if r['slot']==4)
     records.append({'team':team,'time':o['time'],'arena_rune':o['arena']['rune'],'runes':o['runes'],'robot':{k:r.get(k) for k in ('x','y','z','aim','pitch','hp','ammo','level','heat','max_heat','cooling_rate')},'engine_hash':m.snapshot()['engine_hash']})
  frame=m.step(commands);events.extend(e for e in frame['events'] if e['type'] in ('rune_hit','rune_activated','rune_failed','invalid_action'))
print(json.dumps({'records':records,'events':events,'controller_sha256':__import__('hashlib').sha256((Path(__file__).with_name('rune_control.py')).read_bytes()).hexdigest()},indent=2))
