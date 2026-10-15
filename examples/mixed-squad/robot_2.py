"""A control-point baseline that kites toward its team's half."""
from sdk import action, aim_at, distance, nearest_enemy, navigate


def act(obs, state):
    actions = {}
    sign = 1 if obs["team"] == "red" else -1
    base = obs["bases"][obs["team"]]
    for r in obs["robots"]:
        if str(r["slot"]) not in obs["controlled_ids"] or not r["alive"]:
            continue
        zone = obs["arena"]["zones"][(r["slot"] - 1) % 3]
        offset = (r["slot"] // 3 - 1) * 1.0
        goal = (zone["x"] - sign * 0.7, zone["y"] + offset)
        enemy = nearest_enemy(r, obs)
        if r["hp"] < r["max_hp"] * 0.25:
            goal = (base["x"] + sign * 2.3, base["y"] + (r["slot"] - 4) * 1.2)
        elif enemy and distance(r, enemy) < 5:
            goal = (r["x"] - sign * 3, r["y"])
        move = navigate(r, goal, obs["arena"]) if abs(r["x"] - goal[0]) + abs(r["y"] - goal[1]) > 0.35 else (0, 0)
        aim = aim_at(r, enemy) if enemy else (0 if sign == 1 else 3.141592653589793)
        actions[str(r["slot"])] = action(move, aim, enemy is not None,
                                         r["role"] == "engineer" or r["hp"] < r["max_hp"] * 0.6)
    return actions, {"ticks": (state or {}).get("ticks", 0) + 1}
