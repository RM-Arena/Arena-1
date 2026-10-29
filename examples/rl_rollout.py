"""Minimal vector rollout loop; replace policy() with your batched learner.

python examples/rl_rollout.py --envs 4 --steps 100 --duration 10
python examples/rl_rollout.py --envs 4 --opponent claude_opus55_xhigh_2027_hold --trusted-local
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rmuc_arena.catalog import resolve_strategy
from rmuc_arena.vector_env import VectorArena


def policy(observation):
    # These are normal SDK actions. Batch observations here for GPU inference.
    return {slot:{'move':[0,0],'fire':False} for slot in observation['controlled_ids']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--envs',type=int,default=4)
    parser.add_argument('--steps',type=int,default=100)
    parser.add_argument('--duration',type=int,default=10)
    parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--opponent')
    parser.add_argument('--trusted-local',action='store_true')
    args=parser.parse_args()
    seeds=list(range(args.seed,args.seed+args.envs));next_seed=args.seed+args.envs
    with VectorArena(args.envs,duration=args.duration,compact=True,
                     opponent=str(resolve_strategy(args.opponent)) if args.opponent else None,
                     sandbox='trusted-local' if args.trusted_local else 'docker') as envs:
        states=envs.reset(seeds)
        for _ in range(args.steps):
            actions=[{team:policy(state['observations'][team]) for team in state['info']['external_teams']} for state in states]
            transitions=envs.step(actions)
            # learner.update(states, actions, transitions) can consume the terminal
            # observations before these actors are reset. Resets never happen implicitly.
            finished=[i for i,t in enumerate(transitions) if t['terminated'] or t['truncated']]
            for i in finished:
                print(json.dumps({'env_id':i,'seed':transitions[i]['info']['seed'],
                                  'winner':transitions[i]['info']['winner'],'reward':transitions[i]['rewards']}),flush=True)
            resets=envs.reset(range(next_seed,next_seed+len(finished)),env_ids=finished) if finished else []
            next_seed+=len(finished)
            states=transitions
            for i,state in zip(finished,resets):states[i]=state


if __name__=='__main__':main()
