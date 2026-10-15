"""V2 baseline: role assignments, target leading, ballistic aim, heat control."""
import math
from sdk import action, aim_at, aim_pitch, distance, intercept, navigate


def line_of_fire(robot, target, arena):
    dx, dy = target["x"] - robot["x"], target["y"] - robot["y"]
    for wall in arena["obstacles"]:
        lo, hi = 0., 1.
        for p,d,a,b in ((robot["x"],dx,wall["x"],wall["x"]+wall["w"]),
                        (robot["y"],dy,wall["y"],wall["y"]+wall["h"])):
            if abs(d) < 1e-9:
                if p<a or p>b: lo=2;break
            else:
                aa,bb=sorted(((a-p)/d,(b-p)/d));lo,hi=max(lo,aa),min(hi,bb)
        if lo<=hi and lo<1 and hi>0:
            height=robot.get("z",0)+.78+(target.get("z",0)+.55-robot.get("z",0)-.78)*lo
            if height<wall.get("height",2): return False
    return True


def act(obs, state):
    commands = {}
    sign = 1 if obs["team"] == "red" else -1
    enemy_base = obs["bases"]["blue" if sign == 1 else "red"]
    base = obs["bases"][obs["team"]]
    friends = [r for r in obs["robots"] if r["alive"]]
    state = state or {"enemy_memory": {}}
    for e in obs["enemies"]:
        state["enemy_memory"][e["id"]] = {"x": e["x"], "y": e["y"], "tick": obs["tick"]}
    state["enemy_memory"] = {key:e for key,e in state["enemy_memory"].items() if obs["tick"]-e["tick"]<80}
    for r in friends:
        slot = str(r["slot"])
        if slot not in obs["controlled_ids"]:
            continue
        spec = obs["specs"][r["role"]]
        targets = [e for e in obs["enemies"] if distance(r,e)<spec["range"] and line_of_fire(r,e,obs["arena"])]
        target = min(targets, key=lambda e: (distance(r,e)+e["hp"]*.005,e["id"]),default=None)
        zone = obs["arena"]["zones"][{"3":0,"4":1,"5":2,"6":0,"7":1}.get(slot,0)]
        goal = (zone["x"] - sign * .6, zone["y"] + (.6 if slot in ("6","7") else 0))
        if r["role"] == "hero":
            goal = (enemy_base["x"] - sign*7,enemy_base["y"]+sign*3)
        if r["role"] == "engineer":
            wounded = min(friends,key=lambda f:f["hp"]/f["max_hp"])
            goal = (wounded["x"] - sign*.9,wounded["y"]+.8)
        if r["hp"] < r["max_hp"]*.25:
            goal = (base["x"] + sign*2.5,base["y"]+(r["slot"]-4)*.7)
        elif target and distance(r,target)<5:
            goal = (r["x"]-sign*2,r["y"]+(.7 if r["slot"]%2 else -.7))
        target = intercept(r,target,spec["projectile_speed"]) if target else None
        if not target and r["role"] == "hero" and distance(r,enemy_base)<spec["range"] and line_of_fire(r,enemy_base,obs["arena"]):
            target = {**enemy_base,"z":.9}
        aim = aim_at(r,target) if target else None
        aligned = aim is not None and abs((aim-r["aim"]+math.pi)%(2*math.pi)-math.pi)<.22
        skill = r["energy"]>=50 and (r["hp"]<r["max_hp"]*.65 or r["role"]=="engineer" and any(f["hp"]<f["max_hp"]-25 and distance(r,f)<3.5 for f in friends))
        move = navigate(r,goal,obs["arena"]) if math.hypot(r["x"]-goal[0],r["y"]-goal[1])>.4 else (0,0)
        branch = "armor" if r["role"]=="sentry" else "mobility" if r["role"]=="scout" else "damage"
        commands[slot] = action(move,aim,aligned and r["heat"]<88,skill,
                                pitch=aim_pitch(r,target,spec["projectile_speed"]) if target else .04,upgrade=branch)
    return commands,state
