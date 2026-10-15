### Hero Deployment

Only a **ranged** hero with deployment hardware (`deploy_allowed=True`) can deploy. A deployed hero becomes a fixed gun, suited to hitting structures from range in your own half.

- **Start**: inside your own half (red x < 14, blue x > 14), send `deploy=True`; deployment takes effect 2 s later (`deploy_at` is when it takes effect, `deployed` tells whether it has).
- **While deployed**:
  - the chassis is powered off and **cannot move**;
  - 25% defense;
  - 42mm muzzle speed rises to 16.5 m/s;
  - attack buff 1.5 against the **base**;
  - 100 extra XP for each damaging hit;
  - **no first-person view** — the hero no longer reveals enemies{{#robot}}, and your `enemies` stays empty{{/robot}}.
- **Cancel**: `deploy=False` ends deployment immediately. Dying also ends it.
- Heat rules still apply, and so does the rule that 42mm rounds in flight stop dealing damage once the hero has not fired for 4 s.

```python
action(deploy=True)    # inside your own half; takes effect after 2 s
action(deploy=False)   # cancel immediately
```

A deployed hero cannot see enemies, but base and outpost positions are fixed public information and can be targeted directly (see "Base and Outpost").
