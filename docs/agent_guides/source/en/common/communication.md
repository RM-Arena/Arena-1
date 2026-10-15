### Team Communication

Every control mode supports robot-addressed communication. Each robot may set `messages` in its own action, sending at most four per decision. Delivery happens at the next decision, 0.1 s later, independently of distance, camera visibility or whether the robot is alive.

{{#team}}{{^distributed}}
Whole-team mode still runs one process and retains shared `state`. `obs["message_inboxes"][slot_string]` is that robot's inbox. `obs["messages"]` combines the controlled inboxes, so a broadcast may appear as several envelopes with different recipients.

```python
from sdk import action, message

def act(obs, state):
    actions = {}
    inboxes = obs["message_inboxes"]
    for slot in obs["controlled_ids"]:
        received = inboxes[slot]
        detected = obs["vision"].get(slot, {}).get("enemies", [])
        actions[slot] = action(messages=[message({"seen": detected})])
    return actions, state
```
{{/distributed}}{{/team}}
{{#independent}}
An independent process continues to receive its addressed messages in `obs["messages"]`. `obs["message_inboxes"][obs["controlled_ids"][0]]` exposes the same inbox.

```python
from sdk import action, message

def act(obs, state):
    slot = obs["controlled_ids"][0]
    received = obs["messages"]
    return {slot: action(messages=[message({"intent": "advance"})])}, {"received": received}
```
{{/independent}}

- `message(data)` broadcasts to the other robots in your actual lineup. `message(data, to="2")` addresses an own deployment slot: 1,2,3,4,6,7 in fixed lineups, or the actual instance IDs in free battle. Never address yourself or opponents. The host authenticates the sender from the action's robot slot.
- The raw format is `{"to": "all" or a teammate slot string, "data": JSON value}`. Encoded data is at most 512 bytes. Messages and physical operations must together fit each robot's 1 KiB action budget. The four-message limit is per robot, including whole-team mode.
- Received envelopes are `{"from": "red-1", "to": "red-2", "tick": 0, "delivery_tick": 2, "data": ...}`. Inboxes start empty; each envelope appears once at the next decision. Keep useful reports in `state`.
- Ordering follows sender instance number and message-list order, regardless of action-dictionary or process completion order. Missing free-battle recipients receive nothing. Disabled programs no longer send or process messages.
- Messages do not modify visual `enemies` or automatically share private independent-process state. Report sightings, targets and intentions explicitly, with timestamps and appropriate handling of stale reports.
- Replay decision steps store sends in `actions[i]["communication"]`, with sender, recipient list, send/delivery ticks and data. Messages never enter physics or resend during the held-action simulation step.
