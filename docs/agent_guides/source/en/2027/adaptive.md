# Mode D · Adaptive Single-Robot Strategy (RMUC 2027 · model {{robot_title}})

You develop the Python strategy for one **{{robot_title}}** robot under the RMUC 2027 rules. **The final lineup, team size and teammate models are not disclosed during development**; users freely pick deployed robots in the web deck builder, and the same model and strategy may be deployed more than once (at most one aerial robot system per team). Every deployment has its own process, random seed and private `state`; strategy files cannot share memory.

Once the match starts, `observation["robots"]` lists the complete current own lineup, so you can read it and adapt to your teammates, but you may only return an action for your own instance in `controlled_ids`. Never treat a hardware model as a deployment slot, and never assume a fixed number of teammates.

## At a Glance

| Item | Details |
| --- | --- |
| Deliverable | `strategy.py`, defining `act(observation, state)` |
| Controls | One deployed {{robot_title}} instance; its slot is `controlled_ids[0]` in the match |
| Teammates | Not disclosed during development; the full own lineup is readable in the match |
| Decisions | Every 0.1 s, at most 200 ms each; control only yourself |
| Team messages | Broadcast or address a deployed instance; delivered next decision |
| Match | 420 s; ends early when a base is destroyed; deck battles are stored separately and do not affect the official Elo |

{{> common/task}}

{{> 2027/overview}}

## Your Robot

{{own_hardware}}

{{> 2027/rules}}

{{> 2027/robots}}

{{> 2027/interface}}

### Slots and messages in mode D

`robot["model_slot"]` is the hardware model and `robot["slot"]` the deployment slot of this match; duplicated models have different slots. `TEAM_SLOTS_2027` describes fixed lineups and must not be used to infer this match's team size. Read the actual lineup from the observation.

```python
from sdk import action, message

def act(obs, state):
    slot = obs["controlled_ids"][0]
    own = next(r for r in obs["robots"] if str(r["slot"]) == slot)
    teammates = [r for r in obs["robots"] if str(r["slot"]) != slot]
    outgoing = [message({"intent": "cover", "model": own["model_slot"]})]
    return {slot: action(messages=outgoing)}, {"teammates": [r["id"] for r in teammates]}
```

Send at most 4 messages per decision; each `data` is a JSON value of at most 512 bytes and counts toward your 1 KiB action limit. `to="all"` broadcasts to your current teammates; otherwise give a teammate's deployment slot string (not a model). A message sent now arrives once in `obs["messages"]` at the next decision (0.1 s later).

## Practice and Submission

Practice uses varying teammate counts and models; they are only samples, so do not assume the real lineup matches them.

{{> common/practice}}
