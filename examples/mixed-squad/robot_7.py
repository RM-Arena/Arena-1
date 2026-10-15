"""Aggressive team or single-robot baseline. Only this file is submitted."""
import math
from sdk import action, aim_at, distance, nearest_enemy, navigate


def act(obs, state):
    actions = {}
    sign = 1 if obs["team"] == "red" else -1
    enemy_base = obs["bases"]["blue" if sign == 1 else "red"]
    for r in obs["robots"]:
        if str(r["slot"]) not in obs["controlled_ids"] or not r["alive"]:
            continue
        target = nearest_enemy(r, obs)
        if target:
            d = distance(r, target)
            move = navigate(r, (target["x"], target["y"]), obs["arena"]) if d > 6 else (0, 0)
            if r["hp"] < r["max_hp"] * 0.28:
                move = navigate(r, (obs["bases"][obs["team"]]["x"] + sign * 2.5, r["y"]), obs["arena"])
            aim, fire = aim_at(r, target), True
        else:
            # Spread the team along lanes, then pressure the enemy base.
            lane = 3.0 + (r["slot"] - 1) * 3.0
            goal = (30 if sign == 1 else 10, lane)
            if abs(r["x"] - goal[0]) < 2:
                goal = (enemy_base["x"] - sign * 4.0, enemy_base["y"] + (r["slot"] - 4) * 0.9)
            move = navigate(r, goal, obs["arena"])
            aim, fire = aim_at(r, enemy_base), distance(r, enemy_base) < 14
        actions[str(r["slot"])] = action(move, aim, fire, r["hp"] < r["max_hp"] * 0.7)
    return actions, {"decisions": (state or {}).get("decisions", 0) + 1}
