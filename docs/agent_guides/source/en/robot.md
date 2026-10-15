# Robot Strategy Battle · Single-Robot Competition Guide ({{robot_title}})

This guide contains the complete rules and interface for the Single-Robot Competition. You write one Python program that **controls only your team's slot {{slot}} {{role_name}}**. Each of the other five robots on your side runs an independent program written by another participant: you share coins and the result, and can communicate through team messages. No language model is called during a match; code makes every decision in real time.

## At a Glance

| Item | Details |
| --- | --- |
| Deliverable | `strategy.py`, defining `act(observation, state)` |
| You control | Your slot {{slot}} {{role_name}} (`controlled_ids == ["{{slot}}"]`) |
| Teammates | Your other five robots, each run by another participant's program; team messaging supported |
| Decision rate | `act` is called every 0.1 s and must return within 200 ms |
| Match length | 420 s; ends early only when a base is destroyed |
| Development time | 90 minutes by default, started by the organizer; reading, coding, practice and submitting all count |
| Entry | Your last successful submission before the deadline |

{{> common/quickstart}}

{{> common/task}}

{{> common/overview}}

{{> robots/robot-{{slot}}}}

{{> robot/teammates}}

{{> robot/information}}

{{> rules/combat}}

{{> rules/penalties}}

{{> rules/economy}}

{{> rules/growth}}

{{> rules/power}}

{{> rules/structures}}

{{> rules/zones}}

{{> rules/rune}}

{{#c_ground}}
{{> mechanics/chassis}}
{{/c_ground}}

{{> common/interface}}

{{> common/practice}}

{{> starters/{{role}}}}

{{> common/pitfalls}}
