"""Public hardware catalog and immutable, mirrored team lineups."""
import json
from pathlib import Path

SLOTS=(1,2,3,4,6,7)
ROLES={1:'hero',2:'engineer',3:'infantry',4:'infantry',6:'aerial',7:'infantry'}
DEFAULT_TEAM_LINEUP={str(s):s for s in SLOTS}
from .paths import ROOT

def robot_models():
    return json.loads((ROOT/'config/rules.json').read_text(encoding="utf-8"))['robot_designs']

def model_ids():
    return tuple(sorted(int(k) for k in robot_models()))

def initial_model_stats(design,rules):
    """Level-one preselected referee performance, using the engine's public tables."""
    role=design['role'];profiles=rules['official']['profiles'];stats=dict(rules['specs'][role])
    if role=='hero':stats.update(profiles['hero'][design['hero_profile']][0])
    elif role=='infantry':
        stats.update(profiles['infantry_chassis'][design['chassis_profile']][0])
        stats.update(profiles['infantry_weapon'][design['weapon_profile']][0])
    elif role=='aerial':stats.update(profiles['aerial'][0])
    else:stats.update(profiles['engineer'])
    return {key:stats[key] for key in ('hp','power_w','max_heat','cooling','damage','ammo')}

def model_catalog():
    rules=json.loads((ROOT/'config/rules.json').read_text(encoding="utf-8"))
    return {key:{**d,'initial_stats':initial_model_stats(d,rules)} for key,d in rules['robot_designs'].items()}

def normalize_team_lineup(lineup=None):
    value=dict(DEFAULT_TEAM_LINEUP if lineup is None else lineup)
    value={str(k):v for k,v in value.items()}
    if set(value)!=set(DEFAULT_TEAM_LINEUP):
        raise ValueError('Team lineup must select exactly slots 1,2,3,4,6,7')
    models=robot_models()
    for slot,model in value.items():
        if isinstance(model,bool) or not isinstance(model,int) or str(model) not in models:
            raise ValueError(f'Unknown robot model for slot {slot}')
        if models[str(model)]['role']!=ROLES[int(slot)]:
            raise ValueError(f'Slot {slot} requires a {ROLES[int(slot)]} model')
    return {str(s):value[str(s)] for s in SLOTS}

def mirrored_lineups(lineup):
    value=normalize_team_lineup(lineup)
    return {team:[{'slot':s,'model':value[str(s)]} for s in SLOTS] for team in ('red','blue')}
