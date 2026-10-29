"""Persistent multi-agent training environments using the same Rust referee and physics."""
from concurrent.futures import ThreadPoolExecutor
import json
import copy
import math
import os
from pathlib import Path

from .action_protocol import validate_actions
from .battle_settings import normalize
from .communication import TeamCommunication
from .engine import Match, DT, POLICY_INTERVAL
from .models import mirrored_lineups, normalize_team_lineup
from .replays import write_replay
from .runner import FrameLog, Policy
from .submissions import load_submission, manifest_season
from . import seasons

TEAMS = ('red', 'blue')


class ArenaEnv:
    """One episode at a time; reset reuses its Rust process and resets policy state.

    Actions are {team: {slot: SDK-action}}. Both teams are externally controlled
    unless an opponent submission is supplied. Rewards are zero-sum; a completed
    game pays +/-1 and a draw pays zero. Optional score shaping is additive.
    """
    def __init__(self, *, season=None, duration=420, team_lineup=None, lineups=None,
                 action_repeat=POLICY_INTERVAL, reward='terminal', score_scale=.001,
                 max_steps=None, record=False, compact=False, full_state=False,
                 battle_settings=None, opponent=None, team='red', sandbox='docker', timeout=.2):
        opponent_manifest = load_submission(opponent)[0] if opponent else None
        season = season or (manifest_season(opponent_manifest) if opponent_manifest else seasons.DEFAULT_SEASON)
        if team_lineup is None and lineups is None and opponent_manifest:
            team_lineup = opponent_manifest.get('team_lineup')
        if season not in seasons.seasons() or isinstance(duration, bool) or not isinstance(duration, int) or not 1 <= duration <= 420:
            raise ValueError('Use season 2026/2027 and duration in [1,420]')
        if isinstance(action_repeat, bool) or not isinstance(action_repeat, int) or not 2 <= action_repeat <= 200 or action_repeat % POLICY_INTERVAL:
            raise ValueError('action_repeat must be an even integer in [2,200]')
        if reward not in ('terminal', 'score') or not math.isfinite(score_scale) or score_scale < 0:
            raise ValueError('Use terminal/score rewards and a finite nonnegative score_scale')
        if max_steps is not None and (isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 1):
            raise ValueError('max_steps must be a positive integer')
        if team not in TEAMS or sandbox not in ('docker', 'trusted-local') or not .01 <= timeout <= 5:
            raise ValueError('Invalid team, sandbox or policy timeout')
        if lineups is not None and team_lineup is not None:
            raise ValueError('Choose a shared team_lineup or separate free-battle lineups')
        self.season, self.duration, self.action_repeat = season, duration, action_repeat
        self.free = lineups is not None
        self.team_lineup = None if self.free else normalize_team_lineup(team_lineup, season)
        self.lineups = copy.deepcopy(lineups) if self.free else mirrored_lineups(self.team_lineup, season)
        if not isinstance(self.lineups, dict) or set(self.lineups) != set(TEAMS):
            raise ValueError('Lineups require red and blue')
        for deployments in self.lineups.values():
            if not isinstance(deployments, list) or not deployments:
                raise ValueError('Each lineup needs at least one robot')
            if any(not isinstance(d, dict) or set(d) != {'slot', 'model'} or
                   any(isinstance(d[k], bool) or not isinstance(d[k], int) for k in ('slot','model')) for d in deployments):
                raise ValueError('Deployments contain integer slot and model fields')
        self.reward_mode, self.score_scale, self.max_steps = reward, score_scale, max_steps
        self.record, self.compact, self.full_state = record, compact, full_state
        self.settings = normalize(battle_settings or {}, season)
        self.opponent, self.team, self.sandbox, self.timeout = opponent, team, sandbox, timeout
        self.match, self.pool, self.frames = None, None, None
        self.policies, self.actions, self.diagnostics = [], [], []
        self.episode, self.steps, self.closed, self.ready = 0, 0, False, False
        if opponent:
            manifest = opponent_manifest
            if manifest.get('api_version') != 3 or manifest.get('rules_profile') != seasons.rules_profile(season) or manifest['mode'] not in ('team','squad','distributed'):
                raise ValueError('Opponent must be a team, squad or distributed strategy from this season')
            if self.free and manifest['mode'] != 'team':
                raise ValueError('Free-battle external environments require a whole-team opponent')
            if not self.free and normalize_team_lineup(manifest.get('team_lineup'), season) != self.team_lineup:
                raise ValueError('Opponent and learner must use the same registered team lineup')

    def _close_policies(self):
        if self.pool:
            self.pool.shutdown(wait=True, cancel_futures=True)
            self.pool = None
        for _, policy in self.policies:
            policy.close()
        self.policies = []

    def reset(self, seed=42, scenario=None):
        if self.closed:
            raise ValueError('Environment is closed')
        if isinstance(seed, bool) or not isinstance(seed, int) or not -(2**31) <= seed < 2**31:
            raise ValueError('seed must be a signed 32-bit integer')
        self.ready = False
        self._close_policies()
        options = dict(seed=seed, duration=self.duration, map_name=seasons.map_of(self.season),
                       lineups=self.lineups, battle_settings=self.settings, training_scenario=scenario)
        if self.match is None or self.match.closed or self.match.process.poll() is not None:
            if self.match is not None:
                self.match.close()
            self.match = Match(**options)
        else:
            self.match.reset(**options)
        if self.frames is not None:
            self.frames.file.close()
        frame = self.match.snapshot()
        self.frames = FrameLog(frame) if self.record else None
        self.actions, self.diagnostics, self.steps = [], [], 0
        self.episode += 1
        rosters = {t: [str(r['slot']) for r in frame['robots'] if r['team'] == t] for t in TEAMS}
        self.communication = TeamCommunication(rosters)
        self.metadata = {'api_version':3, 'engine':'rust', 'season':self.season,
                         'rules':seasons.rules_profile(self.season), 'seed':seed, 'duration':self.duration,
                         'map':seasons.map_of(self.season), 'dt':DT, 'test_match':True,
                         'match_mode':'deck' if self.free else 'standard', 'lineups':self.lineups,
                         'team_lineup':self.team_lineup, 'battle_settings':self.settings,
                         'training':{'action_repeat':self.action_repeat,'reward':self.reward_mode,
                                     'score_scale':self.score_scale,'max_steps':self.max_steps},
                         'engine_hash':frame['engine_hash'], 'rules_hash':frame['rules_hash'],
                         'teams':{t:{'name':f'external-{t}','version':'external-v1','mode':'team'} for t in TEAMS}}
        if scenario is not None:
            self.metadata['training_scenario'] = copy.deepcopy(scenario)
        if self.opponent:
            manifest, entries = load_submission(self.opponent)
            other = 'blue' if self.team == 'red' else 'red'
            self.metadata['teams'][other] = {'name':Path(self.opponent).name, 'version':manifest['version'], 'mode':manifest['mode']}
            self.pool = ThreadPoolExecutor(max_workers=len(entries))
            try:
                for key, path in sorted(entries.items()):
                    slots = None if manifest['mode'] == 'team' else [int(key)]
                    policy = Policy(path, seed*100+(0 if other=='red' else 10)+(int(key) if slots else 0),
                                    self.sandbox, self.timeout, expected_digest=manifest['hashes'][path.name],
                                    dynamic_messages=self.free)
                    self.policies.append((slots, policy))
            except BaseException:
                self._close_policies()
                raise
        self.ready = True
        return self._transition(0.0, [], reset=True, frame=frame)

    def _observation(self, team, slots=None):
        observation = self.match.observation(team, slots)
        inboxes = {slot:self.communication.inboxes[team][slot] for slot in observation['controlled_ids']}
        observation['message_inboxes'] = inboxes
        observation['messages'] = [message for inbox in inboxes.values() for message in inbox]
        return observation

    def step(self, actions):
        if self.closed or self.match is None or not self.ready:
            raise ValueError('Call reset before step')
        if self.match.status == 'finished':
            raise ValueError('Episode has ended; reset this environment before stepping')
        if not isinstance(actions, dict) or not set(actions) <= set(TEAMS):
            raise ValueError('Actions must be keyed only by red and blue')
        actions = json.loads(json.dumps(actions, allow_nan=False))
        for team in TEAMS:
            validate_actions(actions.get(team, {}), self.communication.rosters[team], dynamic=self.free)
        other = 'blue' if self.team == 'red' else 'red'
        if self.opponent and actions.get(other):
            raise ValueError('Cannot override the saved opponent strategy')
        score = lambda teams,t: teams[t].get('attack_damage', teams[t]['score'])
        previous_score = score(self.match.teams,'red')-score(self.match.teams,'blue')
        events, held = [], {t:{} for t in TEAMS}
        for tick in range(self.action_repeat):
            communication = []
            failures = []
            if self.match.tick % POLICY_INTERVAL == 0:
                outgoing = []
                held = {t:{} for t in TEAMS}
                for team in TEAMS:
                    if self.opponent and team == other:
                        futures = [(slots,p,self.pool.submit(p.decide,self._observation(team,slots))) for slots,p in self.policies]
                        for slots, policy, future in futures:
                            chosen, error = future.result()
                            held[team].update(chosen)
                            if error:
                                detail={'type':'policy_error','id':f'policy:{team}:{slots}:{self.match.tick}',
                                        'team':team,'slots':slots,'tick':self.match.tick,'time':self.match.time,
                                        'message':error,'disabled':policy.disabled}
                                self.diagnostics.append(detail); failures.append(detail)
                    else:
                        held[team] = {slot:dict(action) for slot,action in actions.get(team,{}).items()}
                        # An action is held, but its message is sent once per learner decision.
                        if tick:
                            for action in held[team].values():
                                action.pop('messages',None)
                    for slot, action in held[team].items():
                        messages = action.pop('messages',[])
                        if messages:
                            outgoing.append((team,slot,messages))
                communication = self.communication.route(outgoing,self.match.tick,self.match.tick+POLICY_INTERVAL)
            frame = self.match.step(held)
            frame['events'].extend(failures)
            events.extend(frame['events'])
            if self.record:
                self.actions.append({**held,'communication':communication} if communication else held)
                self.frames.append(frame,None if failures else self.match.raw_frame)
            if frame['status'] == 'finished':
                break
        self.steps += 1
        if self.max_steps is not None and self.steps >= self.max_steps and self.match.status != 'finished':
            self.match.finish(None,'stopped')
            frame = self.match.snapshot()
            if self.record:
                self.frames[-1] = self.match.snapshot()
        current = frame
        terminal = 0 if self.match.status != 'finished' or self.match.winner is None else 1 if self.match.winner == 'red' else -1
        dense = (score(current['teams'],'red')-score(current['teams'],'blue')-previous_score)*self.score_scale
        reward = terminal+(dense if self.reward_mode == 'score' else 0)
        return self._transition(reward, events, frame=current)

    def _transition(self, reward, events, reset=False, frame=None):
        frame = self.match.snapshot() if frame is None else frame
        done = frame['status'] == 'finished'
        observations = {t:self._observation(t) for t in TEAMS}
        if self.compact and not reset:
            for observation in observations.values():
                for key in ('arena','rulebook_rules','simulation_assumptions'):
                    observation.pop(key,None)
        info = {'seed':frame['seed'],'episode':self.episode,'step':self.steps,'tick':frame['tick'],
                'time':frame['time'],'action_repeat':self.action_repeat,'winner':frame['winner'],'reason':frame['reason'],
                'engine_hash':frame['engine_hash'],'rules_hash':frame['rules_hash'],
                'policy_errors':len(self.diagnostics),'events':events,
                'worker_pid':os.getpid(),'simulator_pid':self.match.process.pid,
                'external_teams':[self.team] if self.opponent else list(TEAMS)}
        if done:
            info['digest'] = self.match.digest()
        if self.full_state:
            info['state'] = copy.deepcopy(frame)
        return {'observations':observations,'rewards':{'red':reward,'blue':-reward},
                'terminated':done and frame['reason'] != 'stopped',
                'truncated':done and frame['reason'] == 'stopped','info':info}

    def save_replay(self, path):
        if self.frames is None:
            raise ValueError('Enable record to export an environment replay')
        result={'winner':self.match.winner,'reason':self.match.reason,'time':self.match.time,
                'digest':self.match.digest(),'policy_errors':len(self.diagnostics),
                'teams':self.match.snapshot()['teams']}
        write_replay(path,self.metadata,self.frames,self.actions,self.diagnostics,result)
        return {'path':str(Path(path).resolve()),'ticks':len(self.actions)}

    def close(self):
        if self.closed:
            return
        self.closed = True
        self._close_policies()
        if self.match:
            self.match.close()
        if self.frames:
            self.frames.file.close()

    def __enter__(self):
        return self

    def __exit__(self,*args):
        self.close()
