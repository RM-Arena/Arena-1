## Your Robot: Slot 2 Engineer

### Role

You cannot shoot and earn no XP, so you stay at level 1. Your value is economy and technology: every successful tech-core assembly gives the whole team a lasting coin income and unlocks higher level caps and defense buffs — the foundation for the other five robots to get stronger.

{{own_hardware}}

- 250 HP and 120 W chassis power, independent of level; no profile choice.
- Protection: 50% defense throughout the first 180 s; invulnerable in your resource zone; invulnerable in your assembly zone (at most 180 s per match in total).
- You cannot buy ammo or heal remotely, but you can heal in the supply zone. After death you respawn naturally, or revive instantly for coins (`revive=True`; the level term of the price uses level 1).
- You rebuild the outpost after only **5 s** in a row in your outpost zone (hero and infantry need 10 s); see "Base and Outpost".

{{> mechanics/engineer}}

### Tips

- The resource zone (0.98, 13.08) and the assembly zone (13.34, 6.84) are about 14 m apart in a straight line (red coordinates); the round trip is your main cost. Carry 2 units at a time to save trips.
- Difficulty 1 is available from 0 s, and the sooner it succeeds, the sooner the income starts: +50 team coins every 10 s after the first success.
- Difficulties 2 and 3 unlock at 60 and 120 s. Completing them on time raises the team level cap to 7 and 10, and difficulty 3 also gives the team 25% defense.
- Difficulty 4 needs 2 units, two cores within 45 s, and no more than 3 s between the two confirms. The reward is large (50% defense, +2000 base HP), but a failure locks it for 90 s, and failing an interrupting attempt costs even more.
- Repeating a difficulty still pays (+5/+10/+15 every 10 s for repeats of levels 1/2/3), so keep assembling after the main line is done.
- The assembly zone is near the field center, where enemies pass by; its invulnerability lasts only 180 s per match. The technology-core pedestal and the rune gantry posts in the middle are solid and split the assembly platform into a red and a blue half.
- A tipped teammate cannot drive, and respawning does not right it: righting it with `rescue` is often worth more than waiting for its respawn (see "Righting a tipped teammate" under the engineer).
- The arm blocks sight and shots: when escorting a deploying hero or covering a teammate at the supply area, hold it toward the threat (`arm={"tip": ...}`).
