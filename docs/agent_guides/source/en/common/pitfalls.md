## Appendix: Common Mistakes

{{#team}}
- Looping over 1–7 or assuming contiguous slots instead of using `controlled_ids`.
{{/team}}
{{#robot}}
- Putting any slot other than `"{{slot}}"` into `actions`, which disables your program.
{{/robot}}
- `act` raising an exception or timing out, which disables your program for the whole match. Catch exceptions inside `act` and check your worst-case decision time.
{{#c_buyer}}
- Forgetting to buy ammo: ground robots start with 0 rounds, so `fire=True` does nothing. Coins arrive at 1 s, so buying at `tick == 0` fails.
- Buying an amount that is not a whole multiple of the batch (e.g. local 17mm must be a multiple of 10, remote 17mm of 100, remote 42mm of 10); the request is silently ignored.
- Setting `profile` after `tick == 0`, when it no longer has any effect.
{{/c_buyer}}
{{#c_17mm}}
- Too little heat margin for 17mm: one decision may fire 2 rounds, and going over the cap means waiting until heat is back to 0.
{{/c_17mm}}
{{#c_shooter}}
- Aiming at an outpost without `kind="outpost"`, so `aim_pitch` uses the wrong height.
- Building aiming targets from `referee["robots"]`, which has no positions.
{{/c_shooter}}
{{#c_ground}}
- Requesting more than the power cap for too long; once the buffer is empty the chassis is cut off for 5 s.
{{/c_ground}}
{{#c_s7}}
- Sending `crouch=True` in only one action: once a later action omits it, the turret rises again.
{{/c_s7}}
{{#c_aerial}}
- Leaving air support on all the time: after the free time it costs the team 1 coin per second.
{{/c_aerial}}
- Assuming that losing every ground robot loses the match: only a destroyed base ends a match early.
{{#c_ground}}
- Expecting a destroyed or unpowered robot to stop at once: it slides on its momentum, and its wreck blocks paths and sight lines.
- Sending `move` to a tipped robot: its wheels are off the ground; wait for the engineer to right it, or (wheel-legged models) stand up from the front or back.
{{/c_ground}}
{{#c_s3}}
- Treating a wheel-legged model like a mecanum robot and sending sideways `move`: it turns first and then drives, so routes bend more than expected.
- Sending `jump` repeatedly: it has a 0.8 s cooldown and triggers only on the ground; there is no double jump.
{{/c_s3}}
{{#c_engineer}}
- Sending `move` during `rescue`: moving after the grip drags the teammate away or loses the grip.
{{/c_engineer}}
- Letting {{source_files}} depend on files in `practice/`, the network or wall-clock time.
- Submitting for the first time right before the deadline.
