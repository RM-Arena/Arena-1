# Robot Strategy Battle · Single-Robot Competition Guide (RMUC 2027 · {{robot_title}})

This guide is the complete rules and interface reference for the single-robot competition under the **RMUC 2027 rules**. You write one Python program that **controls only your slot {{slot}} {{role_name}}**. Programs written independently by other participants control your four teammates: you share coins and the result, and you can talk through team messages. No language model is called during a match; code makes every decision in real time.

## At a Glance

| Item | Details |
| --- | --- |
| Deliverable | `strategy.py`, defining `act(observation, state)` |
| You control | Your slot {{slot}} {{role_name}} (`controlled_ids == ["{{slot}}"]`) |
| Teammates | Your other four robots, run by other participants' programs, with team messages |
| Decision rate | `act` is called every 0.1 s and must return within 200 ms |
| Match length | 420 s; ends early when either base is destroyed |
| Development time | 90 minutes by default, started by the organizer; reading, coding, testing and submitting all count |
| Entry | The last successful submission before the deadline |

{{> 2027/quickstart}}

{{> common/task}}

{{> 2027/overview}}

## Your Robot

{{own_hardware}}

{{> 2027/information}}

{{> 2027/rules}}

{{> 2027/robots}}

{{> 2027/interface}}

{{> common/practice}}

{{> 2027/starter}}
