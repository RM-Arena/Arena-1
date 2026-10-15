# Mode D · Adaptive Single-Robot Policy ({{robot_title}} model)

Develop one Python policy for the **{{robot_title}} model**. **The final lineup, teammate count and models are not disclosed during development.** The user chooses deployments through the Web deck builder and can deploy the same model or policy repeatedly. Each deployment has a separate process, random seed and private `state`.

During the match, `observation["robots"]` exposes the full actual own lineup so the policy can adapt. Return actions only for your own instance in `controlled_ids`. Never confuse hardware model numbers with deployment IDs or assume a fixed teammate count.

## At a Glance

| Item | Details |
| --- | --- |
| Deliverable | `strategy.py`, defining `act(observation, state)` |
| Controlled robot | One {{robot_title}} model instance; use `controlled_ids[0]` at match time |
| Teammates | Unannounced during development; the actual own lineup is available during the match |
| Decisions | Every 0.1 s, at most 200 ms per call, control self only |
| Communication | Broadcast or address teammate instances; delivered next decision |
| Match | 420 s; ends early on base destruction; deck games are recorded separately and unranked |

{{> common/task}}

## Match and Own Hardware

The arena is 28 by 15 metres. Each side has a base, outpost, tech core and rune. Coins and team buffs are shared. Timeout compares base HP, outpost destruction history, outpost HP, attack damage and surviving ground HP in that order.

{{own_hardware}}

{{> rules/combat}}
{{> rules/penalties}}
{{> rules/economy}}
{{> rules/growth}}
{{> rules/power}}
{{> rules/structures}}
{{> rules/zones}}
{{> rules/rune}}
{{#c_ground}}{{> mechanics/chassis}}{{/c_ground}}
{{#hero}}{{> mechanics/hero}}{{/hero}}
{{#engineer}}{{> mechanics/engineer}}{{/engineer}}
{{#aerial}}{{> mechanics/aerial}}{{/aerial}}

{{> common/interface}}

### Mode D Instance IDs and Messages

`robot["model_slot"]` identifies the hardware model; `robot["slot"]` is the deployment ID. Duplicates have different IDs. `TEAM_SIZE` and `TEAM_SLOTS` are legacy helpers for fixed lineups and do not determine this match's team size. Read the actual lineup from the observation.

```python
from sdk import action, message

def act(obs, state):
    slot = obs["controlled_ids"][0]
    own = next(r for r in obs["robots"] if str(r["slot"]) == slot)
    teammates = [r for r in obs["robots"] if str(r["slot"]) != slot]
    outgoing = [message({"intent": "cover", "model": own["model_slot"]})]
    # Address a teammate with message(data, to=str(teammates[0]["slot"]))
    return {slot: action(messages=outgoing)}, {"teammates": [r["id"] for r in teammates]}
```

Send at most four messages per decision. Each data payload is JSON of at most 512 bytes, and all messages plus physical operations must fit the robot action's total 1 KiB limit. `to="all"` broadcasts to current teammates; a slot string addresses an instance, not a model. Delivery is own-team only; nonexistent destinations receive nothing. Messages arrive once through `obs["messages"]` at the next decision, 0.1 s later, with `from`, `to`, `tick`, `delivery_tick` and `data`. Private state stays isolated and enemy vision is not automatically merged.

## Practice and Submission

Practice varies the teammate count and models. These are practice examples and do not specify the final competition lineup. Adapt using the actual match observation.

{{> common/practice}}
