"""Build the participant guides from shared Markdown fragments.

The team competition and the single-robot competition are separate events, so
every participant receives exactly one self-contained guide: ``team.md`` or
``robot-<slot>.md``. Shared rules live once in docs/agent_guides/source/<lang>/;
level tables and robot hardware are read from config/rules.json so they cannot
drift from the engine.

Fragment syntax:
    {{name}}             variable
    {{> path}}           include source/<lang>/<path>.md (variables expand first)
    {{#flag}}..{{/flag}}  keep only when flag is true; {{^flag}} inverts

RMUC 2027 guides are built from source/<lang>/2027/ into docs/agent_guides/<lang>/2027/;
they share the task, practice and communication fragments with 2026.

    python scripts/build_agent_guides.py          # rewrite docs/agent_guides/<lang>/
    python scripts/build_agent_guides.py --check  # exit 1 when outputs are stale
"""
import argparse
import json
import copy
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
GUIDES = ROOT / "docs/agent_guides"
SLOTS = (1, 2, 3, 4, 6, 7)
LANGS = ("zh", "en")
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from rmuc_arena.models import initial_model_stats
ROLES = {1: "hero", 2: "engineer", 3: "infantry", 4: "infantry", 6: "aerial", 7: "infantry"}
SLOTS_2027 = (1, 3, 4, 6, 7)
ROLES_2027 = {1: "heavy", 3: "infantry", 4: "infantry", 6: "aerial", 7: "sentry"}
SEASONS = ("2026", "2027")

VARIABLE = re.compile(r"\{\{(\w+)\}\}")
INCLUDE = re.compile(r"\{\{>\s*([\w/-]+)\s*\}\}")
SECTION = re.compile(r"\{\{([#^])(\w+)\}\}(.*?)\{\{/\2\}\}", re.S)
MARK = "\x00"

TEXT = {
    "zh": {
        "level": "等级", "xp": "累计经验", "hp": "血量", "power": "功率 W", "heat": "热量上限", "cooling": "冷却 /s",
        "ranged": "远程型", "melee": "近战型", "chassis_hp": "血量优先底盘", "chassis_power": "功率优先底盘",
        "weapon_cooling": "冷却优先发射机构", "weapon_burst": "爆发优先发射机构",
        "slot": "编号", "design": "设计", "mass": "质量 kg", "size": "底盘 m", "speed": "参考速度 m/s",
        "vision": "视距 m", "yaw": "云台水平转速 rad/s", "armor": "装甲中心高 m", "muzzle": "炮口高 m",
        "item": "项目", "value": "数值", "focus": "定位", "pitch": "俯仰范围（相对底盘）",
        "weapon": "发射机构", "none": "—", "times": " × ",
        "roles": {"hero": "英雄", "engineer": "工程", "infantry": "步兵", "aerial": "空中机器人"},
        "weapons": {"hero": "42mm", "engineer": "无", "infantry": "17mm", "aerial": "17mm"},
        "titles": {1: "1 号英雄", 2: "2 号工程", 3: "3 号步兵 · 双轮足", 4: "4 号步兵 · 爆发型",
                   6: "6 号空中机器人", 7: "7 号步兵 · 稳健型"},
        "designs": {1: ("H42 重型英雄", "重型平台，42mm 远程支援"), 2: ("E35 搬运工程", "载重、升降伸缩机械臂与扶正"),
                    3: ("W3 双轮足步兵", "主动平衡、可调腿长、跳跃越障与飞坡，不能横移"), 4: ("I4 突击步兵", "较大弹仓，短时火力爆发"),
                    7: ("I7 稳健步兵", "低重心、低装甲、抓地好，可降低云台"), 6: ("A13 护罩四旋翼", "电动飞行，17mm 空中支援")},
    },
    "en": {
        "level": "Level", "xp": "Total XP", "hp": "HP", "power": "Power W", "heat": "Heat cap", "cooling": "Cooling /s",
        "ranged": "Ranged", "melee": "Melee", "chassis_hp": "HP chassis", "chassis_power": "Power chassis",
        "weapon_cooling": "Cooling launcher", "weapon_burst": "Burst launcher",
        "slot": "Slot", "design": "Design", "mass": "Mass kg", "size": "Chassis m", "speed": "Ref. speed m/s",
        "vision": "Vision m", "yaw": "Turret yaw rad/s", "armor": "Armor center height m", "muzzle": "Muzzle height m",
        "item": "Item", "value": "Value", "focus": "Role", "pitch": "Pitch range (relative to chassis)",
        "weapon": "Launcher", "none": "—", "times": " × ",
        "roles": {"hero": "hero", "engineer": "engineer", "infantry": "infantry", "aerial": "aerial robot"},
        "weapons": {"hero": "42mm", "engineer": "none", "infantry": "17mm", "aerial": "17mm"},
        "titles": {1: "Slot 1 Hero", 2: "Slot 2 Engineer", 3: "Slot 3 Infantry · Wheel-Legged",
                   4: "Slot 4 Infantry · Burst", 6: "Slot 6 Aerial Robot", 7: "Slot 7 Infantry · Steady"},
        "designs": {1: ("H42 Heavy Hero", "heavy platform, 42mm long-range support"),
                    2: ("E35 Carrier Engineer", "payload, lift-and-boom manipulator arm, righting tipped robots"),
                    3: ("W3 Wheel-Legged Infantry", "self-balancing, adjustable legs, jumps steps and fly-slopes, cannot strafe"),
                    4: ("I4 Assault Infantry", "large magazine, short bursts of fire"),
                    7: ("I7 Steady Infantry", "low center of mass, low armor, strong grip, lowerable turret"),
                    6: ("A13 Guarded Quadrotor", "electric flight, 17mm air support")},
    },
}


def number(value, digits=2):
    text = f"{value:.{digits}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def numeric(cell):
    try:
        float(str(cell))
        return True
    except ValueError:
        return str(cell) == "—"


def table(header, rows):
    # Right-align purely numeric columns after the first; text columns stay left.
    align = ["---:" if i and all(numeric(row[i]) for row in rows) else "---" for i in range(len(header))]
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(align) + " |"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def counts(lang, size):
    """Team-size words used by the fragments both seasons share."""
    words = {"zh": {5: "五", 6: "六", 4: "四"}, "en": {5: "five", 6: "six", 4: "four"}}[lang]
    slots = SLOTS if size == 6 else SLOTS_2027
    listed = ("、" if lang == "zh" else ",").join(map(str, slots))
    return {"count_sources": words[size] + ("份" if lang == "zh" else ""), "count_others": words[size - 1], "slot_list": listed}


def shared_variables(lang, rules):
    t, official = TEXT[lang], rules["official"]
    profiles, designs = official["profiles"], rules["robot_designs"]
    vision = rules["simulation_assumptions"]["vision_range_m"]
    levels = range(10)
    thresholds = official["experience"]["thresholds"]
    hero, chassis, weapon = profiles["hero"], profiles["infantry_chassis"], profiles["infantry_weapon"]
    hardware = []
    roster=[]
    for slot in SLOTS:
        d, role = designs[str(slot)], ROLES[slot]
        stats=initial_model_stats(d,rules)
        name=d['name'] if lang=='zh' else d.get('name_en',t['designs'][slot][0])
        focus=d['focus'] if lang=='zh' else d.get('focus_en',t['designs'][slot][1])
        roster.append([slot,t['roles'][role],name+' · '+focus,t['weapons'][role],t['none'] if role=='aerial' else stats['hp'],stats['ammo']])
        hardware.append([slot, (d["name"] if lang=="zh" else d.get("name_en",t["designs"][slot][0])), number(d["mass_kg"]),
            number(d["chassis_size_m"][0]) + t["times"] + number(d["chassis_size_m"][1]), number(d["speed_reference_mps"], 1),
            number(vision[role], 0), t["none"] if role == "engineer" else number(d["turret_yaw_rate_rad_s"], 1),
            t["none"] if role == "aerial" else number(d["armor_center_z_m"], 3), t["none"] if role == "engineer" else number(d["muzzle_z_m"], 3)])
    return {
        **counts(lang, len(SLOTS)),
        'roster_table':table(['编号','兵种','所选构型与定位','弹丸','初始血量','初始弹量'] if lang=='zh' else ['Slot','Role','Selected model and focus','Projectile','Initial HP','Initial ammo'],roster),
        "xp_table": table([t["level"]] + [str(i + 1) for i in levels], [[t["xp"]] + [number(v, 0) for v in thresholds]]),
        "hero_levels": table([t["level"], f"{t['ranged']} {t['hp']}", t["power"], t["heat"], t["cooling"],
                              f"{t['melee']} {t['hp']}", t["power"], t["heat"], t["cooling"]],
            [[i + 1] + [number(hero[p][i][k], 0) for p in ("ranged", "melee") for k in ("hp", "power_w", "max_heat", "cooling")] for i in levels]),
        "infantry_chassis_levels": table([t["level"], f"{t['chassis_hp']} {t['hp']}", t["power"], f"{t['chassis_power']} {t['hp']}", t["power"]],
            [[i + 1] + [number(chassis[p][i][k], 0) for p in ("hp", "power") for k in ("hp", "power_w")] for i in levels]),
        "infantry_weapon_levels": table([t["level"], f"{t['weapon_cooling']} {t['heat']}", t["cooling"], f"{t['weapon_burst']} {t['heat']}", t["cooling"]],
            [[i + 1] + [number(weapon[p][i][k], 0) for p in ("cooling", "burst") for k in ("max_heat", "cooling")] for i in levels]),
        "aerial_levels": table([t["level"], t["heat"], t["cooling"]],
            [[i + 1, number(profiles["aerial"][i]["max_heat"], 0), number(profiles["aerial"][i]["cooling"], 0)] for i in levels]),
        "ground_fov_horizontal":number(rules["simulation_assumptions"]["ground_camera_fov_deg"]["horizontal"],0),
        "ground_fov_vertical":number(rules["simulation_assumptions"]["ground_camera_fov_deg"]["vertical"],0),
        "hardware_table": table([t["slot"], t["design"], t["mass"], t["size"], t["speed"], t["vision"], t["yaw"], t["armor"], t["muzzle"]], hardware),
    }


def robot_variables(lang, rules, slot):
    t, d = TEXT[lang], rules["robot_designs"][str(slot)]
    role=d["role"];base=root_model(rules,slot)
    pitch = [round(v * 180 / 3.141592653589793) for v in d["pitch_limits_rad"]]
    rows = [[t["design"], (d["name"] if lang=="zh" else d.get("name_en",t["designs"][base][0]))], [t["focus"], d["focus"] if lang=="zh" else d.get("focus_en",t["designs"][base][1])],
            [t["mass"], number(d["mass_kg"])], [t["size"], number(d["chassis_size_m"][0]) + t["times"] + number(d["chassis_size_m"][1])],
            [t["speed"], number(d["speed_reference_mps"], 1)], [t["vision"], number(rules["simulation_assumptions"]["vision_range_m"][role], 0)],
            [t["weapon"], t["weapons"][role]]]
    if role != "engineer":
        rows += [[t["yaw"], number(d["turret_yaw_rate_rad_s"], 1)], [t["pitch"], f"{pitch[0]}° ~ +{pitch[1]}°"], [t["muzzle"], number(d["muzzle_z_m"], 3)]]
    if role != "aerial":
        rows.append([t["armor"], number(d["armor_center_z_m"], 3)])
    return {"slot": str(slot), "role": role, "role_name": t["roles"][role], "robot_title": t["titles"][base],
            "vision": number(rules["simulation_assumptions"]["vision_range_m"][role], 0),
            "own_hardware": table([t["item"], t["value"]], rows),
            "profile_code": json.dumps({"chassis": d["chassis_profile"], "weapon": d["weapon_profile"]})}


def root_model(rules, slot):
    """The 2026 base slot a derived design descends from (2027 designs derive from 2026 ones)."""
    base = rules["robot_designs"][str(slot)].get("base_model", slot)
    while base not in SLOTS and str(base) in rules["robot_designs"] and rules["robot_designs"][str(base)].get("base_model", base) != base:
        base = rules["robot_designs"][str(base)]["base_model"]
    return base


def flags_for(slot=None, distributed=False, adaptive=False, role=None, base=None):
    role = role or ROLES.get(slot)
    base=slot if base is None else base
    flags = {"team": slot is None, "robot": slot is not None}
    flags["adaptive"] = adaptive
    flags["distributed"] = distributed
    flags["independent"] = slot is not None or distributed
    for name in ("hero", "engineer", "infantry", "aerial"):
        flags[name] = role == name
        flags["c_" + name] = slot is None or role == name
    for s in SLOTS:
        flags[f"s{s}"] = base == s
    flags["c_s7"] = base in (None, 7)
    flags["c_s3"] = base in (None, 3)
    flags["c_17mm"] = slot is None or role in ("infantry", "aerial")
    flags["c_shooter"] = role != "engineer"
    flags["c_ground"] = role != "aerial"
    flags["c_buyer"] = slot is None or role in ("hero", "infantry")
    return flags


def expand(name, lang, variables, depth=0):
    if depth > 8:
        raise ValueError(f"Include depth exceeded at {name}")
    path = GUIDES / "source" / lang / f"{name}.md"
    text = path.read_text(encoding="utf-8")

    # Unknown names stay put: they may sit in a section dropped for this guide,
    # and resolve_sections rejects any tag that survives.
    text = VARIABLE.sub(lambda m: variables.get(m.group(1), m.group(0)), text)
    return INCLUDE.sub(lambda m: expand(m.group(1), lang, variables, depth + 1).rstrip("\n"), text)


def resolve_sections(text, flags):
    def section(match):
        if match.group(2) not in flags:
            raise KeyError(f"Unknown section flag {match.group(2)}")
        keep = flags[match.group(2)] == (match.group(1) == "#")
        return MARK + match.group(3) + MARK if keep else MARK

    while True:
        updated = SECTION.sub(section, text)
        if updated == text:
            break
        text = updated
    if "{{" in text:
        raise ValueError("Unresolved template tag: " + text[text.index("{{"):][:60])
    text = re.sub(r"(?m)^\x00+\n", "", text).replace(MARK, "")
    return re.sub(r"\n{3,}", "\n\n", text)


def number_headings(text):
    lines, chapter, section, numbered, fenced = [], 0, 0, False, False
    for line in text.split("\n"):
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("## "):
            title = line[3:]
            numbered = not title.startswith(("速览", "附录", "At a Glance", "Appendix"))
            if numbered:
                chapter, section = chapter + 1, 0
                line = f"## {chapter}. {title}"
        elif not fenced and numbered and line.startswith("### "):
            section += 1
            line = f"### {chapter}.{section} {line[4:]}"
        lines.append(line)
    return "\n".join(lines)


def model_controls(lang,d):
    if lang=="zh":
        text=f"### 本型号的机构能力\n\n驱动：`{d['chassis_type']}`；机械臂：{d.get('arm_count',0)}只；部署：{'支持' if d.get('deploy_allowed') else '不支持'}。\n"
        if d.get('transform_allowed'):text+="使用 `transform=True` 折叠炮塔，`transform_progress` 到1后才可穿越250mm隧道；`transform=False` 展开，顶上有障碍时会停止展开。变形中不能射击；折叠状态的仰角限制为8°。\n"
        if d.get('arm_count')==2:text+="`arm` 和 `arm2` 分别控制两只真实机械臂；`pickup_arm=0/1`选择夹取手臂，可一手救援、另一手夹取。使用 `sdk.resource_pickup_point(robot, arena)` 获得适合其伸展范围的资源区接近点。\n"
        if d['chassis_type']=="wheel_legged":text+="支持 `leg_height`、`jump`、`lean`；双轮足不能直接横移。无部署机构的英雄即使选择ranged性能也无法部署。\n"
        if d.get('leg_type')=="serial":text+="串联腿的髋关节可整周旋转：通电时翻倒、侧躺或车身倒扣会自动翻身（约1–2秒，`self_righting` 为真时不响应移动，`hip_angle` 为当前髋角），无需工程救援。侧装甲中心高见 `armor_side_center_z_m`。\n"
    else:
        text=f"### Model capabilities\n\nDrive: `{d['chassis_type']}`; arms: {d.get('arm_count',0)}; deployment: {'supported' if d.get('deploy_allowed') else 'unavailable'}.\n"
        if d.get('transform_allowed'):text+="Use `transform=True` to fold; wait for `transform_progress==1` before entering the 250mm tunnel. `transform=False` unfolds unless a ceiling blocks it. Transformation disables firing; folded pitch is capped at8 degrees.\n"
        if d.get('arm_count')==2:text+="`arm` and `arm2` independently control two physical manipulators; `pickup_arm=0/1` selects a gripper. One can rescue while the other picks up. `sdk.resource_pickup_point(robot, arena)` returns a reachable resource approach point.\n"
        if d['chassis_type']=="wheel_legged":text+="Supports `leg_height`, `jump` and `lean`, without direct strafing. Heroes without deployment hardware cannot deploy even with the ranged performance profile.\n"
        if d.get('leg_type')=="serial":text+="Serial legs have full-turn hip joints: a powered robot that lands on its side, nose or roof flips itself back upright in about 1-2 s (`self_righting` is true and movement is ignored meanwhile; `hip_angle` reports the hips), with no engineer rescue. Side plates sit at `armor_side_center_z_m`.\n"
    return text


def selected_team_hardware(lang,rules,lineup):
    header="# 已锁定的双方共同阵容" if lang=="zh" else "# Locked symmetric team lineup"
    rows=[];sections=[]
    for slot,model in lineup.items():
        d=rules["robot_designs"].get(str(model),rules["robot_designs"][str(slot)])
        rows.append([slot,model,d['name'] if lang=="zh" else d.get('name_en',d['name']),d['chassis_type'],d.get('arm_count',0),d.get('deploy_allowed',False)])
        sections.append(model_controls(lang,d).replace("### 本型号的机构能力",f"### {slot} 号 · {d['name']}").replace("### Model capabilities",f"### Slot {slot} · {d.get('name_en',d['name'])}"))
    note="用户已经确认下表阵容；这是你开发策略时已知的完整出战阵容，红蓝双方相同。开发、练习、提交后均不可换型。不同阵容需要新建开发工作区。`lineup.json`和这些硬件参考受保护。" if lang=="zh" else "The user has confirmed the complete lineup below before strategy development. You know all six deployed models, and both sides use the same lineup. Development, practice and submission preserve it; use a new workspace for another lineup. lineup.json and hardware references are protected."
    return header+"\n\n"+note+"\n\n"+table(["编号","型号","名称","驱动","机械臂","部署"] if lang=="zh" else ["Slot","Model","Name","Drive","Arms","Deploy"],rows)+"\n\n"+"\n".join(sections)


def team_task_context(lang,rules,lineup,season="2026"):
    """Injected into the participant task only after a concrete lineup is selected."""
    if str(season)=="2027":
        return team_task_context_2027(lang,rules,lineup)
    rows=[]
    for slot,model in lineup.items():
        d=rules['robot_designs'][str(model)];stats=initial_model_stats(d,rules)
        rows.append([slot,model,d['name'] if lang=='zh' else d.get('name_en',d['name']),
            '—' if d['role']=='aerial' else stats['hp'],stats['power_w'],d['battery_wh']])
    if lang=='zh':
        header='## 用户已确认的出战阵容'
        note='开发开始前，用户已选定以下六台机器人。你可以确定完整上场阵容，并据此设计分工和协同；红蓝双方使用相同型号。比赛编号与型号分开：动作使用编号，硬件由 model_slot 指定。阵容在开发、练习和提交期间保持固定，lineup.json 是受保护的记录。'
        columns=['比赛编号','型号','机器人','预选1级HP','底盘功率 W','电池 Wh']
    else:
        header='## User-confirmed competition lineup'
        note='The user selected these six robots before development. You know the complete deployed lineup and can plan roles and coordination around it. Both teams use identical models. Actions address competition slots; model_slot identifies hardware. This lineup remains fixed throughout development, practice and submission; lineup.json is its protected record.'
        columns=['Competition slot','Model','Robot','Preselected L1 HP','Chassis power W','Battery Wh']
    return header+'\n\n'+note+'\n\n'+table(columns,rows)+'\n'


def render(lang, slot=None, distributed=False, adaptive=False, team_lineup=None, season="2026"):
    if str(season) == "2027":
        return render_2027(lang, slot, distributed, adaptive, team_lineup)
    rules = json.loads((ROOT / "config/rules.json").read_text(encoding="utf-8"))
    unselected_team=slot is None and not distributed and not adaptive and team_lineup is None
    catalog_rules=rules
    if team_lineup is not None:
        original=rules["robot_designs"].copy();rules=copy.deepcopy(rules)
        for number,model in team_lineup.items():rules["robot_designs"][str(number)]=copy.deepcopy(original[str(model)])
    variables = shared_variables(lang, rules)
    if unselected_team:
        pending='用户确认阵容后，工作区会动态生成六个位置的型号、性能和机构能力。当前通用规则不指定出战型号。' if lang=='zh' else 'After the user confirms a lineup, the workspace dynamically receives the selected models, performance and capabilities. These general rules do not select deployed models.'
        variables['roster_table']=pending
        variables['hardware_table']=pending
    variables["source_files"] = ", ".join(f"`robot_{s}.py`" for s in SLOTS) if distributed else "`strategy.py`"
    variables["source_summary"] = ("六份策略源码" if lang == "zh" else "six strategy source files") if distributed else "strategy.py"
    if slot is not None:
        variables.update(robot_variables(lang, rules, slot))
        if adaptive and slot not in SLOTS:
            d=rules['robot_designs'][str(slot)]
            variables['robot_title']=f"{slot} · "+(d['name'] if lang=='zh' else d.get('name_en',d['name']))
    template = "adaptive" if adaptive else "distributed" if distributed else "team" if slot is None else "robot"
    flags = flags_for(slot, distributed, adaptive, rules["robot_designs"][str(slot)]["role"] if slot is not None else None,root_model(rules,slot) if slot is not None else None)
    active=[] if unselected_team else [rules["robot_designs"][str(slot)]] if slot is not None else [rules["robot_designs"][str(s)] for s in SLOTS]
    flags["c_s3"]=any(d["chassis_type"]=="wheel_legged" for d in active)
    flags["c_s7"]=any(d["slot"]==7 for d in active)
    text = resolve_sections(expand(template, lang, variables), flags)
    result=number_headings(text).strip()+"\n"
    if team_lineup is not None:result=selected_team_hardware(lang,catalog_rules,team_lineup)+"\n"+result
    elif adaptive and slot is not None:result+="\n"+model_controls(lang,rules["robot_designs"][str(slot)])
    return result


def legal_models(season):
    designs = json.loads((ROOT / "config/rules.json").read_text(encoding="utf-8"))["robot_designs"]
    return sorted(int(k) for k, d in designs.items() if d.get("seasons", {}).get(season, {}).get("legal", season == "2026"))


def outputs():
    for lang in LANGS:
        yield GUIDES / lang / "team.md", render(lang)
        yield GUIDES / lang / "distributed.md", render(lang, distributed=True)
        for slot in SLOTS:
            yield GUIDES / lang / f"robot-{slot}.md", render(lang, slot)
        for model in legal_models("2026"):
            yield GUIDES / lang / f"adaptive-robot-{model}.md", render(lang, model, adaptive=True)
        folder = GUIDES / lang / "2027"
        yield folder / "team.md", render_2027(lang)
        yield folder / "distributed.md", render_2027(lang, distributed=True)
        for slot in SLOTS_2027:
            yield folder / f"robot-{slot}.md", render_2027(lang, slot)
        for model in legal_models("2027"):
            yield folder / f"adaptive-robot-{model}.md", render_2027(lang, model, adaptive=True)


# ---- RMUC 2027 -------------------------------------------------------------------------

TEXT_2027 = {
    "zh": {"roles": {"heavy": "重型机器人", "infantry": "步兵", "aerial": "空中机器人系统", "sentry": "哨兵"},
           "weapons": {"heavy": "42mm（模块化，需解锁并安装）", "infantry": "17mm", "aerial": "无（撞击）", "sentry": "17mm"},
           "titles": {1: "1 号重型机器人", 3: "3 号步兵", 4: "4 号步兵", 6: "6 号空中机器人系统", 7: "7 号哨兵"},
           "drones": "空中机器人", "drone_mass": "单机质量 kg", "drone_size": "外形 m", "battery": "电池 Wh", "integrity": "护罩耐撞次数",
           "count": "数量", "stage": "阶段", "after": {"start": "开局", "assembly_1": "完成 1 级装配", "assembly_2": "完成 2 级装配", "assembly_3_or_launcher": "完成 3 级装配或装上发射模块"},
           "level": "等级", "posture": "姿态", "normal": "常态", "decayed": "衰减后（该姿态累计 180 s）", "enhanced": "强化（15 s 预算）",
           "postures": {"attack": "进攻", "defense": "防御", "move": "移动"}},
    "en": {"roles": {"heavy": "heavy robot", "infantry": "infantry", "aerial": "aerial robot system", "sentry": "sentry"},
           "weapons": {"heavy": "42mm (modular; unlock and install first)", "infantry": "17mm", "aerial": "none (impact)", "sentry": "17mm"},
           "titles": {1: "Slot 1 Heavy Robot", 3: "Slot 3 Infantry", 4: "Slot 4 Infantry", 6: "Slot 6 Aerial Robot System", 7: "Slot 7 Sentry"},
           "drones": "Aerial robots", "drone_mass": "Each kg", "drone_size": "Size m", "battery": "Battery Wh", "integrity": "Guard strikes",
           "count": "Count", "stage": "Stage", "after": {"start": "start", "assembly_1": "level-1 assembly", "assembly_2": "level-2 assembly", "assembly_3_or_launcher": "level-3 assembly or launcher fitted"},
           "level": "Level", "posture": "Posture", "normal": "normal", "decayed": "decayed (180 s in that posture)", "enhanced": "enhanced (15 s budget)",
           "postures": {"attack": "attack", "defense": "defense", "move": "move"}},
}


def lineup_designs_2027(rules, lineup=None):
    lineup = lineup or rules["seasons"]["2027"]["default_lineup"]
    return {int(slot): rules["robot_designs"][str(model)] for slot, model in lineup.items()}


def design_name(lang, d):
    return d["name"] if lang == "zh" else d.get("name_en", d["name"])


def shared_variables_2027(lang, rules, designs):
    t, t27 = TEXT[lang], TEXT_2027[lang]
    o, specs = rules["official_2027"], rules["seasons"]["2027"]["specs"]
    roster, hardware, aerial = [], [], []
    for slot, d in sorted(designs.items()):
        role = d["role"]
        stats = initial_model_stats(d, rules, "2027")
        roster.append([slot, t27["roles"][role], design_name(lang, d) + " · " + (d["focus"] if lang == "zh" else d.get("focus_en", d["focus"])),
                       t27["weapons"][role], t["none"] if role == "aerial" else number(stats["hp"], 0), stats["ammo"]])
        if role == "aerial":
            dr = d["drone"]
            aerial.append([slot, design_name(lang, d), d.get("drone_count", 0), number(dr["mass_kg"], 3), number(dr["size_m"], 3),
                           number(dr["speed_reference_mps"], 1), number(dr["battery_wh"], 1), number(dr["impact_integrity"], 0)])
            continue
        hardware.append([slot, design_name(lang, d), number(d["mass_kg"]), number(d["chassis_size_m"][0]) + t["times"] + number(d["chassis_size_m"][1]),
                         number(d["speed_reference_mps"], 1), number(specs[role]["vision"], 0), number(d["turret_yaw_rate_rad_s"], 1),
                         number(d["armor_center_z_m"], 3), number(d["muzzle_z_m"], 3)])
    thresholds = o["experience"]["thresholds"]
    chassis, weapon = o["profiles"]["infantry_chassis"], o["profiles"]["infantry_weapon"]
    posture = o["sentry"]["posture"]

    def describe(name, values):
        parts = []
        zh = lang == "zh"
        if "cooling_multiplier" in values: parts.append(("冷却 ×" if zh else "cooling x") + number(values["cooling_multiplier"]))
        if "cooling_ratio" in values: parts.append(("冷却 ×" if zh else "cooling x") + number(values["cooling_ratio"]))
        if values.get("no_heat"): parts.append("射击不加热量" if zh else "no heat per shot")
        if "defense" in values: parts.append(("防御 " if zh else "defense ") + f"{round(values['defense'] * 100)}%")
        if "vulnerability" in values: parts.append(("易伤 +" if zh else "vulnerability +") + f"{round(values['vulnerability'] * 100)}%")
        if "power_ratio" in values: parts.append(("底盘功率 ×" if zh else "chassis power x") + number(values["power_ratio"]))
        if "power_multiplier" in values: parts.append(("底盘功率 ×" if zh else "chassis power x") + number(values["power_multiplier"]))
        if "power_w" in values: parts.append(("底盘功率 " if zh else "chassis power ") + number(values["power_w"], 0) + " W")
        return ("；" if zh else "; ").join(parts)

    heavy = o["heavy"]["stages"]
    stage_rows = [[t27["after"][s["after"]], number(s["hp"], 0), number(s["power_w"], 0),
                   number(s.get("max_heat", 0), 0) if s.get("max_heat") else t["none"], number(s.get("cooling", 0), 0) if s.get("cooling") else t["none"]] for s in heavy]
    locations = location_rows_2027(lang, rules["maps"]["rmuc2027"])
    return {
        **counts(lang, 5),
        "roster_table": table(["编号", "兵种", "所选构型与定位", "弹丸", "初始血量", "初始弹量"] if lang == "zh" else ["Slot", "Role", "Selected model and focus", "Projectile", "Initial HP", "Initial ammo"], roster),
        "hardware_table": table([t["slot"], t["design"], t["mass"], t["size"], t["speed"], t["vision"], t["yaw"], t["armor"], t["muzzle"]], hardware),
        "aerial_table": table([t["slot"], t["design"], t27["count"], t27["drone_mass"], t27["drone_size"], t["speed"], t27["battery"], t27["integrity"]], aerial) if aerial else "",
        "xp_table": table([t["level"]] + [str(i + 1) for i in range(10)], [[t["xp"]] + [number(v, 0) for v in thresholds]]),
        "infantry_chassis_levels": table([t["level"], f"{t['chassis_hp']} {t['hp']}", t["power"], f"{t['chassis_power']} {t['hp']}", t["power"]],
            [[i + 1] + [number(chassis[p][i][k], 0) for p in ("hp", "power") for k in ("hp", "power_w")] for i in range(10)]),
        "infantry_weapon_levels": table([t["level"], f"{t['weapon_cooling']} {t['heat']}", t["cooling"], f"{t['weapon_burst']} {t['heat']}", t["cooling"]],
            [[i + 1] + [number(weapon[p][i][k], 0) for p in ("cooling", "burst") for k in ("max_heat", "cooling")] for i in range(10)]),
        "heavy_stages": table([t27["stage"], t["hp"], t["power"], t["heat"], t["cooling"]], stage_rows),
        "sentry_postures": table([t27["posture"], t27["normal"], t27["decayed"], t27["enhanced"]],
            [[t27["postures"][k]] + [describe(k, posture[k][state]) for state in ("normal", "decayed", "enhanced")] for k in ("attack", "defense", "move")]),
        "location_table": locations,
        "ground_fov_horizontal": number(rules["simulation_assumptions"]["ground_camera_fov_deg"]["horizontal"], 0),
        "ground_fov_vertical": number(rules["simulation_assumptions"]["ground_camera_fov_deg"]["vertical"], 0),
    }


def location_rows_2027(lang, arena):
    zones = {z["id"]: z for z in arena["zones"]}
    fixtures = arena["field_geometry"]["fixtures"]
    bench = next(f for f in fixtures if f["kind"] == "workbench" and f["team"] == "red")
    hangar = arena["hangars"]["red"]
    point = lambda x, y: f"({x:.2f}, {y:.2f})"
    z = lambda key: point(zones[key]["x"], zones[key]["y"])
    zh = lang == "zh"
    rows = [
        ["基地" if zh else "Base", point(*arena["bases"]["red"]), "被击毁即输；己方前哨控制点被己方完全控制时无敌" if zh else "destroyed = defeat; invulnerable while you fully control your outpost position"],
        ["堡垒增益点" if zh else "Fortress card", z("red_fortress"), "基地控制点的一部分" if zh else "part of the base position"],
        ["前哨站" if zh else "Outpost", point(*arena["outposts"]["red"]), "旋转三块中层装甲；前哨控制点的一部分" if zh else "three rotating middle plates; part of the outpost position"],
        ["中央高地增益点" if zh else "Central highland card", z("red_central"), "高 0.3 m 的中央高地上，靠己方一侧；前哨控制点的另一部分" if zh else "on the 0.3 m central highland, own side; the other card of the outpost position"],
        ["补给区" if zh else "Supply zone", z("red_supply"), "回血、复活、就地兑换；对方禁入" if zh else "healing, respawn, local exchange; closed to the enemy"],
        ["资源岛" if zh else "Resource hub", z("red_resource"), "重型机器人拾取能量单元（共 6 枚）" if zh else "the heavy robot picks energy units (6 in stock)"],
        ["工作台" if zh else "Workbench", point(*bench["dock_point"]), "重型机器人停靠安装 42mm 发射模块" if zh else "the heavy robot docks here to fit its 42 mm launcher"],
        ["装配区" if zh else "Assembly zone", z("red_assembly"), "中央高地装配台上；对方禁入" if zh else "on the central assembly plinth; closed to the enemy"],
        ["机库" if zh else "Hangar", point(hangar["x"], hangar["y"]), f"空中机器人起降，高 {hangar['z']:.2f} m" if zh else f"aerial robots launch and dock, {hangar['z']:.2f} m high"],
        ["制高点" if zh else "High point", z("red_high_point"), "高 0.8 m，三级台阶；防御增益与就地兑换" if zh else "0.8 m high with three steps; defense buff and local exchange"],
        ["能量机关" if zh else "Power rune", point(arena["rune"]["x"], arena["rune"]["y"]), f"中心高约 {arena['rune']['z']:.1f} m，红蓝两面共轴" if zh else f"centre about {arena['rune']['z']:.1f} m high; coaxial red and blue faces"],
    ]
    return table(["地点", "红方坐标", "说明"] if zh else ["Place", "Red coordinates", "Notes"], rows)


def robot_variables_2027(lang, rules, d, slot=None):
    t, t27 = TEXT[lang], TEXT_2027[lang]
    role = d["role"]
    specs = rules["seasons"]["2027"]["specs"]
    rows = [[t["design"], design_name(lang, d)], [t["focus"], d["focus"] if lang == "zh" else d.get("focus_en", d["focus"])],
            [t["weapon"], t27["weapons"][role]]]
    if role == "aerial":
        dr = d["drone"]
        rows += [[t27["count"], d.get("drone_count", 0)], [t27["drone_mass"], number(dr["mass_kg"], 3)], [t27["drone_size"], number(dr["size_m"], 3)],
                 [t["speed"], number(dr["speed_reference_mps"], 1)], [t27["battery"], number(dr["battery_wh"], 1)], [t27["integrity"], number(dr["impact_integrity"], 0)]]
    else:
        pitch = [round(v * 180 / 3.141592653589793) for v in d["pitch_limits_rad"]]
        rows += [[t["mass"], number(d["mass_kg"])], [t["size"], number(d["chassis_size_m"][0]) + t["times"] + number(d["chassis_size_m"][1])],
                 [t["speed"], number(d["speed_reference_mps"], 1)], [t["vision"], number(specs[role]["vision"], 0)],
                 [t["yaw"], number(d["turret_yaw_rate_rad_s"], 1)], [t["pitch"], f"{pitch[0]}° ~ +{pitch[1]}°"],
                 [t["muzzle"], number(d["muzzle_z_m"], 3)], [t["armor"], number(d["armor_center_z_m"], 3)]]
        if role == "heavy":
            rows += [["发射模块质量 kg" if lang == "zh" else "Launcher module kg", number(d["launcher_module_kg"], 1)],
                     ["安装时间 s" if lang == "zh" else "Fitting time s", number(d["launcher_install_s"], 1)],
                     ["机械臂" if lang == "zh" else "Arms", d.get("arm_count", 0)],
                     ["额定出膛速度 m/s" if lang == "zh" else "Muzzle speed m/s", number(d["muzzle_speed_mps"], 1)]]
    slot = slot if slot is not None else d["slot"]
    title = t27["titles"].get(slot) if slot in t27["titles"] else f"{slot} · {design_name(lang, d)}"
    return {"slot": str(slot), "role": role, "role_name": t27["roles"][role], "robot_title": title,
            "vision": number(specs[role]["vision"], 0), "own_hardware": table([t["item"], t["value"]], rows),
            "profile_code": json.dumps({"chassis": d["chassis_profile"], "weapon": d["weapon_profile"]})}


def flags_2027(slot=None, distributed=False, adaptive=False, role=None, designs=()):
    flags = {"team": slot is None, "robot": slot is not None, "adaptive": adaptive, "distributed": distributed,
             "independent": slot is not None or distributed}
    for name in ("heavy", "infantry", "aerial", "sentry"):
        flags[name] = role == name
        flags["c_" + name] = slot is None or role == name
    # Fragment flags the shared 2026 sections also read.
    for name in ("hero", "engineer"):
        flags[name] = False
        flags["c_" + name] = False
    flags["c_shooter"] = role != "aerial"
    flags["c_ground"] = role != "aerial"
    flags["c_buyer"] = slot is None or role in ("heavy", "infantry", "sentry")
    flags["c_17mm"] = slot is None or role in ("infantry", "sentry")
    flags["c_s3"] = any(d["chassis_type"] == "wheel_legged" for d in designs)
    flags["c_fold"] = any(d.get("transform_allowed") for d in designs)
    flags["c_s7"] = False
    for s in (1, 2, 3, 4, 6, 7):
        flags[f"s{s}"] = False
    return flags


def render_2027(lang, slot=None, distributed=False, adaptive=False, team_lineup=None):
    rules = json.loads((ROOT / "config/rules.json").read_text(encoding="utf-8"))
    designs = lineup_designs_2027(rules, team_lineup)
    unselected_team = slot is None and not distributed and not adaptive and team_lineup is None
    variables = shared_variables_2027(lang, rules, designs)
    if unselected_team:
        pending = "用户确认阵容后，工作区会动态生成五个位置的型号、性能和机构能力。当前通用规则不指定出战型号。" if lang == "zh" else \
            "After the user confirms a lineup, the workspace dynamically receives the selected models, performance and capabilities. These general rules do not select deployed models."
        variables["roster_table"] = variables["hardware_table"] = pending
        variables["aerial_table"] = ""
    variables["source_files"] = ", ".join(f"`robot_{s}.py`" for s in SLOTS_2027) if distributed else "`strategy.py`"
    variables["source_summary"] = ("五份策略源码" if lang == "zh" else "five strategy source files") if distributed else "strategy.py"
    own = None
    if slot is not None:
        own = rules["robot_designs"][str(slot)] if adaptive else designs[slot]
        variables.update(robot_variables_2027(lang, rules, own, None if adaptive else slot))
    template = "2027/" + ("adaptive" if adaptive else "distributed" if distributed else "team" if slot is None else "robot")
    active = [] if unselected_team else [own] if own is not None else list(designs.values())
    flags = flags_2027(slot, distributed, adaptive, own["role"] if own else None, active)
    if unselected_team:
        flags["c_s3"] = flags["c_fold"] = True
    text = resolve_sections(expand(template, lang, variables), flags)
    result = number_headings(text).strip() + "\n"
    if team_lineup is not None:
        result = selected_team_hardware_2027(lang, rules, team_lineup) + "\n" + result
    elif adaptive and own is not None:
        result += "\n" + model_controls_2027(lang, own)
    return result


def model_controls_2027(lang, d):
    zh = lang == "zh"
    text = (f"### 本型号的机构能力\n\n驱动：`{d['chassis_type']}`；机械臂：{d.get('arm_count', 0)}只。\n" if zh else
            f"### Model capabilities\n\nDrive: `{d['chassis_type']}`; arms: {d.get('arm_count', 0)}.\n")
    if d["role"] == "heavy":
        text += ("模块化 42mm 发射机构：解锁后在己方工作台停稳并持续发送 `install_launcher=True` 安装。" if zh else
                 "Modular 42 mm launcher: once unlocked, park at your workbench and keep sending `install_launcher=True`.")
        if d.get("arm_count") == 2:
            text += ("双臂可在 4 级装配中用 `assembly_core=2` 同时操作两个科技核心。" if zh else
                     " Two arms work both level-4 cores at once with `assembly_core=2`.")
        text += "\n"
    if d["role"] == "aerial":
        text += (f"机库搭载 {d.get('drone_count', 0)} 架全自动空中机器人，用 `drones` 字段指挥。\n" if zh else
                 f"The hangar carries {d.get('drone_count', 0)} fully automatic aerial robots, commanded through `drones`.\n")
    if d.get("transform_allowed"):
        text += ("使用 `transform=True` 折叠炮塔，`transform_progress` 到 1 后才可钻过 0.25 m 的隧道；变形中不能射击。\n" if zh else
                 "Use `transform=True` to fold; wait for `transform_progress==1` before entering a 0.25 m tunnel. Firing is disabled while transforming.\n")
    if d["chassis_type"] == "wheel_legged":
        text += ("支持 `leg_height`、`jump`、`lean`；不能直接横移。" if zh else "Supports `leg_height`, `jump` and `lean`, without direct strafing.")
        if d.get("step_climb_m"):
            text += (f"可登上 {d['step_climb_m']:.2f} m 台阶（制高点三级台阶）。" if zh else f" Climbs {d['step_climb_m']:.2f} m steps (the high-point stairs).")
        text += "\n"
    if d.get("leg_type") == "serial":
        text += ("串联腿翻倒后会自动翻身（约 1–2 s）。\n" if zh else "Serial legs right the robot after a fall in about 1-2 s.\n")
    return text


def selected_team_hardware_2027(lang, rules, lineup):
    zh = lang == "zh"
    rows, sections = [], []
    for slot, model in lineup.items():
        d = rules["robot_designs"][str(model)]
        rows.append([slot, model, design_name(lang, d), d["chassis_type"], d.get("arm_count", 0), d.get("drone_count", 0)])
        heading = f"### {slot} 号 · {d['name']}" if zh else f"### Slot {slot} · {design_name(lang, d)}"
        sections.append(model_controls_2027(lang, d).replace("### 本型号的机构能力", heading).replace("### Model capabilities", heading))
    header = "# 已锁定的双方共同阵容（RMUC 2027）" if zh else "# Locked symmetric team lineup (RMUC 2027)"
    note = ("用户已经确认下表阵容；这是你开发策略时已知的完整出战阵容，红蓝双方相同。开发、练习、提交后均不可换型。不同阵容需要新建开发工作区。`lineup.json`和这些硬件参考受保护。" if zh else
            "The user has confirmed the complete lineup below before strategy development. You know all five deployed models, and both sides use the same lineup. Development, practice and submission preserve it; use a new workspace for another lineup. lineup.json and hardware references are protected.")
    columns = ["编号", "型号", "名称", "驱动", "机械臂", "空中机器人"] if zh else ["Slot", "Model", "Name", "Drive", "Arms", "Aerial robots"]
    return header + "\n\n" + note + "\n\n" + table(columns, rows) + "\n\n" + "\n".join(sections)


def team_task_context_2027(lang, rules, lineup):
    rows = []
    for slot, model in lineup.items():
        d = rules["robot_designs"][str(model)]
        stats = initial_model_stats(d, rules, "2027")
        rows.append([slot, model, design_name(lang, d), "—" if d["role"] == "aerial" else number(stats["hp"], 0), stats["ammo"], d["battery_wh"]])
    if lang == "zh":
        header = "## 用户已确认的出战阵容（RMUC 2027）"
        note = "开发开始前，用户已选定以下五台机器人。你可以确定完整上场阵容，并据此设计分工和协同；红蓝双方使用相同型号。比赛编号与型号分开：动作使用编号，硬件由 model_slot 指定。阵容在开发、练习和提交期间保持固定，lineup.json 是受保护的记录。"
        columns = ["比赛编号", "型号", "机器人", "初始 HP", "初始弹量", "电池 Wh"]
    else:
        header = "## User-confirmed competition lineup (RMUC 2027)"
        note = "The user selected these five robots before development. You know the complete deployed lineup and can plan roles and coordination around it. Both teams use identical models. Actions address competition slots; model_slot identifies hardware. This lineup remains fixed throughout development, practice and submission; lineup.json is its protected record."
        columns = ["Competition slot", "Model", "Robot", "Initial HP", "Initial ammo", "Battery Wh"]
    return header + "\n\n" + note + "\n\n" + table(columns, rows) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true", help="Report stale guides without writing")
    args = parser.parse_args()
    stale = []
    for path, text in outputs():
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            continue
        stale.append(path.relative_to(ROOT))
        if not args.check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    if args.check and stale:
        sys.exit("Stale agent guides (run scripts/build_agent_guides.py): " + ", ".join(map(str, stale)))
    print("Wrote " + ", ".join(map(str, stale)) if stale else "Agent guides are current")


if __name__ == "__main__":
    main()
