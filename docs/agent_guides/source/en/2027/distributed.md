# Robot Strategy Battle · Mode C Guide (RMUC 2027)

This guide is the complete rules and interface reference for mode C under the **RMUC 2027 rules**. One agent writes five strategies during development; in a match each strategy runs in its own process, **controls only its own robot and keeps its own state**, and coordinates through team messages. No language model is called during a match; your code makes every decision in real time.

## At a Glance

| Item | Details |
| --- | --- |
| Deliverable | {{source_files}}, each defining `act(observation, state)` |
| You control | Each strategy controls its own slot; together slots 1, 3, 4, 6 and 7 |
| Decision rate | Each process's `act` is called every 0.1 s and must return within 200 ms |
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
