## Referee Penalties and Launcher Locks

Referee decisions use a separate interface from robot actions. Contestants cannot issue cards or change penalty state. The organizer judges subjective fouls; ordinary collisions do not randomly generate yellow cards. Invalid action input is rejected without becoming a yellow card.

### Yellow Cards

- A single-team yellow deducts 15% of the offender's maximum HP and 5% from each other living ground teammate. Damage is rounded to an integer, stops at 1 HP, and bypasses defence and invulnerability.
- Another individual yellow less than 30 s after the previous one doubles that robot's deduction ratio. At 30 s or later it returns to 15%; teammates still lose 5% each.
- The offender's camera is obscured for 5 s and teammates' cameras for 2 s. Consecutive durations stack. An obscured camera provides no enemy positions, vision lists or rune target positions; public referee telemetry remains available, and movement and firing remain possible.
- An engineer's second yellow, or any other robot's third yellow, immediately also issues a red card.
- A simultaneous yellow deducts 5% from every living ground robot on both teams and obscures every camera for 2 s. It changes neither individual card counts nor individual repeated-penalty ratios.

### Red Cards and Forfeits

- A ground robot receiving red has 0 HP, loses chassis power and cannot revive naturally or buy a revival for the remainder of the match. Its wreck stays on the field.
- An aerial robot receiving red stops support and firing, returns automatically to its pad and cannot restart support.
- Penalty HP loss counts toward the opposing team's attack damage without granting robot XP or kill rewards. A referee forfeit sets the losing team's base HP to 0 and immediately ends the match.
- Own status is in `yellow_cards`, `red_card` and `fpv_blocked_until`; public `referee.robots` also shows both teams' card counts and red-card states.

### Excess Muzzle Speed

Fixed hardware determines muzzle speed; contestants cannot request a different speed. The sensor measures speed relative to the launcher, excluding inherited chassis motion.

- 17mm: exceeding 25 m/s by less than 5 m/s locks firing for 15 s; an excess from 5 to less than 10 m/s locks it for 20 s; an excess of at least 10 m/s permanently locks it for this match.
- 42mm: exceeding the current limit (12 m/s; 16.5 m/s when deployed) by up to 1.1 times the limit locks for 15 s; above 1.1 and up to 1.2 times the limit locks for 20 s. Actual speed above 18 m/s permanently locks firing; this absolute boundary takes priority.
- Unsupported undeployed 42mm hardware speeds strictly above 14.4 and up to 18 m/s are rejected before firing; the undefined sanction band is not invented.
- Muzzle-speed and heat locks are independent. Clearing one does not clear the other; revival cannot remove a permanent lock.
- Status is in `overspeed_locked`, `overspeed_lock_until`, `overspeed_permanent_lock`, `heat_permanent_lock` and `launcher_fault`; `sdk.can_fire` checks these locks.
