"""Materialize the RMUC 2027 Claude Opus 5.5 team examples from scripts/robot_policy_2027.py.

    official_2027_team         team mode, balanced (the default red strategy)
    official_2027_hold         team mode, guard (the default blue strategy)
    official_2027_squad        squad mode: one copy of the balanced policy per robot
    official_2027_distributed  distributed mode: one self-contained policy per slot
    official_2027_adaptive     template for adaptive workspaces (no manifest)

Per-model deck presets are built by scripts/build_robot_presets.py.

    python scripts/build_examples_2027.py          # rewrite the examples
    python scripts/build_examples_2027.py --check  # exit 1 when they are stale
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rmuc_arena import seasons as season_rules
from rmuc_arena.showcase import PROFILE_FILE, SHOWCASE_FILE, SHOWCASE_FORMAT, example_agent, parse_showcase, validate_profile
from rmuc_arena.submissions import save_submission

SEASON = "2027"
EXAMPLES = ROOT / "examples"
POLICY = ROOT / "scripts/robot_policy_2027.py"
SLOTS = season_rules.slots(SEASON)

DISTRIBUTED_TAIL = '''

# One author provides five self-contained strategies; each process owns one slot and
# reports what it sees to its teammates every second.
_team_act = act


def act(obs, state):
    slot = "{slot}"
    assert obs["controlled_ids"] == [slot]
    commands, new_state = _team_act(obs, state)
    new_state["reports"] = obs["messages"][-4:]
    if obs["tick"] % 20 == 0:
        commands.setdefault(slot, action())["messages"] = [message({{
            "intent": "report", "slot": slot,
            "seen": [enemy["id"] for enemy in obs["enemies"][:3]],
        }})]
    return commands, new_state
'''


def cards():
    spec = importlib.util.spec_from_file_location("robot_cards_2027", ROOT / "scripts/robot_cards_2027.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def team_showcase(tactic):
    c = cards()
    units = []
    for role, name in (("heavy", "1号重型"), ("infantry", "步兵组（3、4号）"), ("aerial", "6号空中机器人系统"), ("sentry", "7号哨兵")):
        card = c.CARDS[(role, tactic)]
        units.append({"name": name, **card["unit"]})
    if tactic == "balanced":
        return {
            "format": SHOWCASE_FORMAT, "title": "基线策略 2027",
            "tagline": "空中机器人开局拆前哨，步兵夺控制点，重型升满科技后装炮，哨兵守卡",
            "summary": "RMUC 2027 默认阵容的基线策略。空中机器人开局按装甲转速定时冲撞敌方前哨站，前哨倒下且敌方失去前哨控制点的完全控制后改撞基地。编号小的步兵占领敌方中央高地卡夺取敌方前哨控制点（控制度每秒 +1），180 秒后进攻敌方堡垒；另一台步兵打敌方前哨并在己方控制点吃紧时回防。哨兵常驻己方中央高地卡守住己方控制点，按战况切换进攻、防御、移动姿态。重型搬运能量单元完成 1–4 级装配（收入、步兵等级上限、全队防御），解锁后在工作台装上 42mm，再从中央高地炮位炮击。",
            "style": {"aggression": 60, "defense": 45, "economy": 70, "objective": 90, "teamwork": 55, "adaptability": 45},
            "phases": [{"from": 0, "to": 30, "title": "开局", "goal": "空中机器人冲撞敌方前哨；步兵与哨兵上中央高地；重型取能量单元", "focus": "attack"},
                       {"from": 30, "to": 180, "title": "控制点与科技", "goal": "夺取敌方前哨控制点、守住己方控制点；重型完成 1–3 级装配", "focus": "objective"},
                       {"from": 180, "to": 300, "title": "装炮与堡垒", "goal": "重型装炮、做 4 级；步兵进攻敌方堡垒打开基地装甲", "focus": "objective"},
                       {"from": 300, "to": 420, "title": "残局", "goal": "保持控制度领先，炮击与冲撞可受伤的敌方基地", "focus": "attack"}],
            "units": units,
            "rules": [{"when": "敌方前哨站还在", "then": "空中机器人定时冲撞前哨装甲"},
                      {"when": "己方控制双方前哨控制点", "then": "控制度每秒 +1，继续守卡"},
                      {"when": "己方前哨控制点只剩临时控制且哨兵不在", "then": "一台步兵回防己方中央高地卡"},
                      {"when": "发射机构解锁", "then": "重型回工作台装 42mm"},
                      {"when": "已过 180 秒且控制着敌方前哨控制点", "then": "步兵进攻敌方堡垒"},
                      {"when": "阵亡且比赛未到 330 秒", "then": "金币够就立即复活"}],
            "priorities": ["控制度", "敌方前哨站", "科技装配", "失去无敌的敌方基地"],
            "strengths": ["开局就用空中机器人拆掉敌方前哨", "直接争夺决定到时胜负的控制度", "科技收益完整"],
            "weaknesses": ["不打能量机关", "重型往返公路很慢，42mm 火力 3 分钟后才到位", "哨兵独自守卡，被集火时控制点会失守"],
        }
    return {
        "format": SHOWCASE_FORMAT, "title": "守势策略 2027",
        "tagline": "守住己方前哨控制点，科技升满，空中机器人只清前哨",
        "summary": "RMUC 2027 默认阵容的守势基线。两台步兵分别守己方中央高地卡与前哨卡，哨兵常驻己方中央高地卡并默认防御姿态，敌方难以夺取己方前哨控制点。重型完成 1–4 级装配与装炮后守在己方前哨一侧。空中机器人只冲撞前哨站，300 秒后才冲撞可受伤的敌方基地。",
        "style": {"aggression": 25, "defense": 90, "economy": 75, "objective": 55, "teamwork": 50, "adaptability": 35},
        "phases": [{"from": 0, "to": 30, "title": "就位", "goal": "步兵与哨兵上中央高地守卡；重型取件；空中机器人冲撞敌方前哨", "focus": "defense"},
                   {"from": 30, "to": 300, "title": "守控制点", "goal": "守住己方前哨控制点；重型升科技、装炮", "focus": "defense"},
                   {"from": 300, "to": 420, "title": "终局", "goal": "空中机器人冲撞可受伤的敌方基地", "focus": "attack"}],
        "units": units,
        "rules": [{"when": "7 m 内出现敌人", "then": "守卡步兵开火"},
                  {"when": "没有目标", "then": "哨兵保持防御姿态"},
                  {"when": "已过 300 秒且敌方基地可受伤", "then": "空中机器人冲撞基地"}],
        "priorities": ["己方前哨控制点", "科技装配", "敌方前哨站"],
        "strengths": ["己方控制点与基地无敌很难被打破", "科技收益完整"],
        "weaknesses": ["几乎不争取控制度，到时判定吃亏", "不进攻敌方堡垒"],
    }


def profile(tactic, name, description):
    return validate_profile({"agent": example_agent(SEASON), "tactic": tactic,
                             "tags": ["aerial", "assembly", "outpost_rush"] if tactic != "guard" else ["aerial", "assembly"],
                             "display_name": name, "description": description})


def dump(data):
    text = json.dumps(data, ensure_ascii=False, indent=2)
    text = re.sub(r"\[\s*(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)\s*\]", r"[\1, \2]", text)
    return (text + "\n").encode()


def submission(name, mode, sources, team_lineup=None):
    """Files of a submission saved through the normal path: {filename: bytes}."""
    with tempfile.TemporaryDirectory() as temporary:
        entries = {}
        for key, text in sources.items():
            path = Path(temporary) / f"{key}.py"
            path.write_text(text, encoding="utf-8")
            entries[key] = path
        output = Path(temporary) / "submission"
        save_submission(output, mode, entries, team_lineup=team_lineup, season=SEASON)
        return {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}


def outputs():
    policy = POLICY.read_text(encoding="utf-8")
    balanced, guard = policy, policy.replace('TACTIC = "balanced"', 'TACTIC = "guard"')
    lineup = season_rules.default_lineup(SEASON)
    built = {}
    team = submission("team", "team", {"team": balanced}, lineup)
    hold = submission("hold", "team", {"team": guard}, lineup)
    squad = submission("squad", "squad", {str(s): balanced for s in SLOTS})
    distributed = submission("distributed", "distributed", {str(s): balanced + DISTRIBUTED_TAIL.format(slot=s) for s in SLOTS})
    for name, files, tactic, title, text in (
            ("official_2027_team", team, "balanced", "基线策略 2027", "RMUC 2027 基线全队策略：空中机器人拆前哨，步兵夺控制点，重型升科技后装炮，哨兵守卡。"),
            ("official_2027_hold", hold, "guard", "守势策略 2027", "RMUC 2027 守势全队策略：守住己方前哨控制点，科技升满，空中机器人只清前哨。"),
            ("official_2027_squad", squad, "balanced", "单机组队 2027", "RMUC 2027 基线策略的单机组队版本：每台机器人运行同一份策略、只控制自己。"),
            ("official_2027_distributed", distributed, "balanced", "多机协同 2027", "RMUC 2027 基线策略的多机协同版本：每台一份独立策略，每秒向队友报告所见敌人。")):
        showcase = team_showcase(tactic)
        if name != "official_2027_team" and name != "official_2027_hold":
            showcase = dict(showcase, title=title)
        showcase["generated_by"] = example_agent(SEASON)
        files = dict(files)
        files[SHOWCASE_FILE] = dump(showcase)
        files[PROFILE_FILE] = dump(profile("guard" if tactic == "guard" else "balanced", title, text))
        for key, data in files.items():
            built[EXAMPLES / name / key] = data
    built[EXAMPLES / "official_2027_adaptive" / "strategy.py"] = balanced.encode()
    return built


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = []
    for path, data in outputs().items():
        if path.name == SHOWCASE_FILE:
            parse_showcase(data)
        if path.is_file() and path.read_bytes() == data:
            continue
        stale.append(path.relative_to(ROOT))
        if not args.check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    if args.check and stale:
        sys.exit("Stale 2027 examples (run scripts/build_examples_2027.py): " + ", ".join(map(str, stale)))
    print("Wrote " + ", ".join(map(str, stale)) if stale else "2027 examples are current")


if __name__ == "__main__":
    main()
