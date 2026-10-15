# Robot Strategy Battle · Team Competition Guide (RMUC 2027)

This guide is the complete rules and interface reference for the team competition under the **RMUC 2027 rules**. You write one Python program that **controls all five of your robots at once** against another team that is also controlled by a program. No language model is called during a match; your code makes every decision in real time.

## At a Glance

| Item | Details |
| --- | --- |
| Deliverable | `strategy.py`, defining `act(observation, state)` |
| You control | Slot 1 heavy robot, slots 3/4 infantry, slot 6 aerial robot system and slot 7 sentry: five robots (no slots 2 or 5) |
| Decision rate | `act` is called every 0.1 s and must return within 200 ms |
| Match length | 420 s; ends early when either base is destroyed |
| Development time | 90 minutes by default, started by the organizer; reading, coding, testing and submitting all count |
| Entry | The last successful submission before the deadline |

{{> 2027/quickstart}}

{{> common/task}}

{{> 2027/overview}}

{{> 2027/information}}

{{> 2027/rules}}

{{> 2027/robots}}

{{> 2027/interface}}

{{> common/practice}}

{{> 2027/starter}}
