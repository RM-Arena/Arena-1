# Robot Strategy Battle · Team Competition Guide

This guide contains the complete rules and interface for the Team Competition. You write one Python program that **controls all six robots on your side at once** and plays against another team that is also controlled by a program. No language model is called during a match; your code makes every decision in real time.

## At a Glance

| Item | Details |
| --- | --- |
| Deliverable | `strategy.py`, defining `act(observation, state)` |
| You control | Your slots 1, 2, 3, 4, 6 and 7 — six robots (there is no slot 5) |
| Decision rate | `act` is called every 0.1 s and must return within 200 ms |
| Match length | 420 s; ends early only when a base is destroyed |
| Development time | 90 minutes by default, started by the organizer; reading, coding, practice and submitting all count |
| Entry | Your last successful submission before the deadline |

{{> common/quickstart}}

{{> common/task}}

{{> common/overview}}

{{> team/information}}

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

Deployment, assembly and air support each belong to a single role. The infantry-only abilities (starting the power rune, holding a fortress) are covered in "Zone Buffs and Terrain Crossings" and "Power Rune".{{#c_s7}} A selected I7 model can also lower its turret (`crouch`, see "Interface Reference").{{/c_s7}}

{{> mechanics/hero}}

{{> mechanics/engineer}}

{{> mechanics/aerial}}

{{> common/interface}}

{{> common/practice}}

{{> team/starter}}

{{> team/levels}}

{{> common/pitfalls}}
