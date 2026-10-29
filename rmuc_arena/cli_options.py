"""Validate CLI run specifications without starting a match or a policy process."""
import json
from pathlib import Path

from . import seasons
from .battle_settings import normalize
from .catalog import resolve_strategy, strategy_index
from .models import normalize_team_lineup
from .submissions import load_submission, manifest_season

DEFAULTS = {'2027':('claude_opus55_xhigh_2027_team','claude_opus55_xhigh_2027_hold'),
            '2026':('claude_opus55_xhigh_team','claude_opus55_xhigh_hold')}


def json_value(value, base=None):
    if value is None or isinstance(value,(dict,list)):
        return value
    value = str(value)
    if value.lstrip().startswith(('{','[')):
        return json.loads(value)
    path = Path(value).expanduser()
    if not path.is_absolute() and base:
        path = Path(base)/path
    return json.loads(path.read_text(encoding='utf-8'))


def resolve(value, index, base):
    if base and not Path(value).is_absolute() and (Path(base)/value).is_dir():
        value = str(Path(base)/value)
    return str(resolve_strategy(value,index))


def make_spec(values, *, base=None, index=None):
    index = strategy_index() if index is None else index
    if 'trusted_local' in values and not isinstance(values['trusted_local'],bool):
        raise ValueError('trusted_local must be a JSON boolean')
    mode = values.get('mode') or 'standard'
    if mode not in ('standard','deck'):
        raise ValueError('mode must be standard or deck')
    duration, seed = values.get('duration',420), values.get('seed',42)
    timeout = values.get('timeout',.2)
    if isinstance(seed,bool) or not isinstance(seed,int) or not -(2**31) <= seed < 2**31:
        raise ValueError('seed must be a signed 32-bit integer')
    if isinstance(duration,bool) or not isinstance(duration,int) or not 1 <= duration <= 420:
        raise ValueError('duration must be an integer in [1,420]')
    if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not .01 <= timeout <= 5:
        raise ValueError('timeout must be in [.01,5]')
    paths = {t:resolve(values[t],index,base) for t in ('red','blue') if values.get(t)}
    decks = None
    controllers = {}
    if mode == 'deck':
        decks = {}
        for team in ('red','blue'):
            cards = json_value(values.get(team+'_deck'),base)
            if not isinstance(cards,list) or not cards or not all(isinstance(p,str) for p in cards):
                raise ValueError('Deck mode needs red_deck and blue_deck lists of saved adaptive strategies')
            decks[team] = [resolve(path,index,base) for path in cards]
            controller = values.get(team+'_control','independent')
            if controller not in ('independent','team'):
                raise ValueError('Free-battle control must be independent or team')
            if controller == 'team':
                name = values.get(team+'_team_strategy') or values.get(team)
                if not name:
                    raise ValueError(f'{team} team control requires a saved team strategy')
                controllers[team] = resolve(name,index,base)
    elif any(values.get(k) for k in ('red_deck','blue_deck','red_team_strategy','blue_team_strategy')) or any(values.get(t+'_control','independent') != 'independent' for t in ('red','blue')):
        raise ValueError('Deck options require --mode deck')
    sources = list(paths.values())+list(controllers.values())+[p for cards in (decks or {}).values() for p in cards]
    found = {manifest_season(load_submission(path)[0]) for path in sources}
    season = values.get('season')
    map_name = values.get('map')
    if map_name:
        field_season = seasons.season_of_map(map_name)
        if season and season != field_season:
            raise ValueError('season and map disagree')
        season = field_season
    season = season or (next(iter(found)) if len(found) == 1 else seasons.DEFAULT_SEASON)
    if season not in seasons.seasons() or found-set([season]):
        raise ValueError('All strategies and the field must use the same season')
    settings = normalize(json_value(values.get('settings'),base) or {},season)
    lineup = json_value(values.get('lineup'),base)
    if mode == 'deck' and lineup is not None:
        raise ValueError('Free battle has separate lineups; do not supply --lineup')
    if mode == 'standard':
        for team, default in zip(('red','blue'),DEFAULTS[season]):
            if team not in paths:
                paths[team] = resolve(default,index,base)
        lineup = normalize_team_lineup(lineup,season) if lineup is not None else None
    options = {'red':paths.get('red') if mode == 'standard' else None,
               'blue':paths.get('blue') if mode == 'standard' else None,
               'seed':seed,'duration':duration,'map_name':seasons.map_of(season),
               'sandbox':'trusted-local' if values.get('trusted_local') else 'docker','timeout':timeout,
               'team_lineup':lineup,'battle_settings':settings}
    if decks:
        options.update(decks=decks,free_team_strategies=controllers)
    return {'options':options,'swapped':False}


def swap_spec(spec):
    options = dict(spec['options'])
    options['red'], options['blue'] = options['blue'], options['red']
    if options.get('decks'):
        options['decks'] = {'red':options['decks']['blue'],'blue':options['decks']['red']}
    if options.get('free_team_strategies'):
        options['free_team_strategies'] = {'blue' if team == 'red' else 'red':path for team,path in options['free_team_strategies'].items()}
    return {'options':options,'swapped':True}
