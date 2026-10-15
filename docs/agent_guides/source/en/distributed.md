# Robot Strategy Battle · Mode C Guide

This guide contains the complete rules and interface for Mode C. One development agent writes six strategies. During a match each strategy runs in its own process, **controls one robot and maintains private state**, coordinating through team messages. No language model is called during a match; code makes every decision in real time.

## At a Glance

| Item | Details |
| --- | --- |
| Deliverable | {{source_files}}, each defining `act(observation, state)` |
| You control | Each strategy controls its own slot; together slots 1,2,3,4,6,7 (no slot 5) |
| Decision rate | Each process calls `act` every 0.1 s and must return within 200 ms |
| Match length | 420 s; ends early only when a base is destroyed |
| Development time | 90 minutes by default, started by the organizer; reading, coding, practice and submitting all count |
| Entry | Your last successful submission before the deadline |

{{> common/quickstart}}

{{> common/task}}

{{> common/overview}}

{{> distributed/information}}

{{> rules/combat}}

{{> rules/penalties}}

{{> rules/economy}}

{{> rules/growth}}

{{> rules/power}}

{{> rules/structures}}

{{> rules/zones}}

{{> rules/rune}}

{{> mechanics/chassis}}

## Role-Specific Mechanics

Deployment, assembly and air support each belong to a single role. The infantry-only abilities (starting the power rune, holding a fortress) are covered in "Zone Buffs and Terrain Crossings" and "Power Rune". The default I7 model can also lower its turret (`crouch`, see "Interface Reference").

{{> mechanics/hero}}

{{> mechanics/engineer}}

{{> mechanics/aerial}}

{{> common/interface}}

{{> common/practice}}



{{> team/levels}}

{{> common/pitfalls}}
