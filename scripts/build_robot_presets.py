"""Build the two extra policies per model; existing adaptive entries stay balanced.

Every preset directory (balanced, assault and guard) also gets its display sidecars,
showcase.json and profile.json, generated from the role x tactic cards below.

RMUC 2027 presets (official_2027_adaptive_<model>[_assault|_guard]) cover every model
legal in 2027; all three come from scripts/robot_policy_2027.py with its TACTIC set, and
their cards live in scripts/robot_cards_2027.py.
"""
import argparse
import json
from pathlib import Path
import importlib.util
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rmuc_arena.models import model_ids, robot_models
from rmuc_arena import seasons as season_rules
from rmuc_arena.robot_presets import PROFILES, PROFILES_2027, TACTICS, preset_key
from rmuc_arena.showcase import PROFILE_FILE, SHOWCASE_FILE, SHOWCASE_FORMAT, parse_showcase, validate_profile
from rmuc_arena.submissions import load_submission, save_submission

# Own-side metres (own base on the left). The balanced policy is the official baseline
# (examples/official_adaptive_*/strategy.py); assault and guard come from
# scripts/robot_preset_template.py. Each card describes what that code really does.
HERO_START, ENGINEER_START, INFANTRY_START, AERIAL_PAD = [1.6, 6.05], [1.6, 8.95], [3.93, 7.5], [1.4, 1.85]
RESOURCE, ASSEMBLY = [0.98, 13.12], [13.59, 7.09]
OPENING = {"from": 0, "to": 30, "title": "出发", "goal": "离开出生点，开往本套路的站位", "focus": "attack"}
LATE_REVIVE = "300 秒后阵亡不再花金币买活"
REVIVE_RULE = {"when": "阵亡且比赛未到 300 秒", "then": "金币够就立即买活"}

CARDS = {
    ("hero", "balanced"): {
        "tactic": "balanced", "tags": ["outpost_rush"],
        "tagline": "直奔敌方前哨站前 4 m 开炮，见人先打人，前哨倒下转攻基地",
        "summary": "沿用官方基线：开局选择远程弹道，开到敌方前哨站前约 4 m 处，射程内有可命中的敌人就先打人，否则炮击前哨站；前哨倒下后移到敌方基地前约 4 m 继续。血量低于 25% 或虚弱时回补给区，弹药打空回基地补弹；阵亡后金币够且未到 300 秒就立即买活。",
        "style": {"aggression": 65, "defense": 20, "economy": 15, "objective": 70, "teamwork": 20, "adaptability": 35},
        "phases": [OPENING,
                   {"from": 30, "to": 300, "title": "拆前哨 · 攻基地", "goal": "在敌方前哨站前约 4 m 开火，射程内出现敌人时先打人；前哨倒下后前移到敌方基地前约 4 m", "focus": "objective"},
                   {"from": 300, "to": 420, "title": "残局", "goal": "继续炮击；" + LATE_REVIVE, "focus": "attack"}],
        "unit": {"role": "前压炮手", "task": "开到敌方前哨站前约 4 m 炮击，射程内有敌人先打人；前哨倒下后转到敌方基地前约 4 m",
                 "route": [HERO_START, [13.0, 3.6], [21.6, 7.5]], "anchor": [13.0, 3.6]},
        "rules": [{"when": "射程内有可命中的敌人", "then": "先打最近的敌人，按其速度提前量瞄准"},
                  {"when": "敌方前哨站倒下", "then": "炮位前移到敌方基地前约 4 m"},
                  {"when": "虚弱或血量低于 25%", "then": "撤回己方补给区"},
                  {"when": "弹药打空", "then": "回己方基地补弹"}, REVIVE_RULE],
        "priorities": ["射程内最近的敌人", "敌方前哨站", "敌方基地"],
        "strengths": ["开局就压到敌方前哨站前，火力到位快", "看到敌人会先自卫，不会只顾打建筑"],
        "weaknesses": ["不使用部署模式，站在前哨前方容易被集火", "只能在基地或补给区就地补弹，打空后要长途往返", "不利用能量机关、增益点和队友信息"],
    },
    ("hero", "assault"): {
        "tactic": "assault", "tags": ["outpost_rush", "base_rush"],
        "tagline": "只认建筑：在敌方前哨站前 4.5 m 架炮，前哨倒下直取基地",
        "summary": "开到敌方前哨站前约 4.5 m 处，炮口始终对准前哨站，前哨倒下后转到敌方基地前约 4.5 m 继续炮击，不主动与机器人交火。血量低于 22%、虚弱或弹药打空时撤回补给区；阵亡后金币够且未到 300 秒就立即买活。",
        "style": {"aggression": 75, "defense": 10, "economy": 10, "objective": 90, "teamwork": 15, "adaptability": 20},
        "phases": [OPENING,
                   {"from": 30, "to": 300, "title": "专打建筑", "goal": "只炮击敌方前哨站，前哨倒下后转到基地前继续，不理会机器人", "focus": "objective"},
                   {"from": 300, "to": 420, "title": "残局强攻", "goal": "继续炮击敌方基地；" + LATE_REVIVE, "focus": "attack"}],
        "unit": {"role": "攻城炮", "task": "在敌方前哨站前约 4.5 m 炮击前哨站，前哨倒下后转到敌方基地前约 4.5 m 炮击基地",
                 "route": [HERO_START, [12.5, 3.6], [21.1, 7.5]], "anchor": [12.5, 3.6]},
        "rules": [{"when": "敌方前哨站还在", "then": "只瞄准前哨站开火"},
                  {"when": "敌方前哨站倒下", "then": "前移到敌方基地前约 4.5 m，改打基地"},
                  {"when": "血量低于 22%、虚弱或弹药打空", "then": "撤回补给区补给"}, REVIVE_RULE],
        "priorities": ["敌方前哨站", "敌方基地"],
        "strengths": ["火力全部倾泻在建筑上，拆前哨效率高", "撤退线清晰，残血就回补给区"],
        "weaknesses": ["被敌方机器人贴近也不还击", "不使用部署模式，站位暴露", "只在补给区补弹，来回路程长"],
    },
    ("hero", "guard"): {
        "tactic": "guard", "tags": [],
        "tagline": "守在己方前哨站后方，只打 8 m 内的来犯之敌",
        "summary": "驻守己方前哨站后方约 1.5 m 处；己方前哨被毁后退到己方基地后方。只攻击 8 m 内的敌人，不主动打建筑。血量低于 50%、虚弱或弹药打空就回补给区；阵亡后金币够且未到 300 秒就立即买活。",
        "style": {"aggression": 15, "defense": 80, "economy": 10, "objective": 15, "teamwork": 25, "adaptability": 30},
        "phases": [{"from": 0, "to": 30, "title": "就位", "goal": "开到己方前哨站后方的守位", "focus": "defense"},
                   {"from": 30, "to": 300, "title": "守前哨", "goal": "拦截 8 m 内的敌人，半血就回补给区", "focus": "defense"},
                   {"from": 300, "to": 420, "title": "残局", "goal": "继续驻守；己方前哨若已倒下则守在基地后方", "focus": "defense"}],
        "unit": {"role": "后场守卫", "task": "守在己方前哨站后方，8 m 内出现敌人才开火；己方前哨被毁后退到己方基地后方",
                 "route": [HERO_START, [9.5, 11.4], [0.9, 7.5]], "anchor": [9.5, 11.4]},
        "rules": [{"when": "8 m 内出现敌人", "then": "按提前量瞄准开火"},
                  {"when": "敌人在 8 m 外", "then": "不开火，守住站位"},
                  {"when": "己方前哨站被毁", "then": "退守己方基地后方"},
                  {"when": "血量低于 50%、虚弱或弹药打空", "then": "回补给区"}, REVIVE_RULE],
        "priorities": ["8 m 内的敌人"],
        "strengths": ["站位离补给区近，续航好", "半血即撤，不容易阵亡"],
        "weaknesses": ["英雄火力不参与拆前哨和攻基地", "8 m 外的敌人一概不打，远程消耗吃亏", "前哨倒下后退到基地后方，让出中场"],
    },
    ("engineer", "balanced"): {
        "tactic": "balanced", "tags": ["assembly", "rescue"],
        "tagline": "先扶起 8 m 内翻倒的队友，再往返资源区与装配区升科技",
        "summary": "8 m 内有翻倒的队友（能自行翻身的串联腿除外）时，先赶过去用机械臂扶正；否则在己方资源区取件，开到装配区停稳装配，选择已解锁的最高难度：0 秒 1 级、60 秒 2 级、120 秒 3 级、180 秒 4 级（需两份资源）。阵亡后金币够且未到 300 秒就立即买活。",
        "style": {"aggression": 5, "defense": 30, "economy": 80, "objective": 40, "teamwork": 70, "adaptability": 45},
        "phases": [{"from": 0, "to": 60, "title": "1 级科技", "goal": "取件后开上中央高地装配 1 级科技，途中优先扶起 8 m 内翻倒的队友", "focus": "economy"},
                   {"from": 60, "to": 180, "title": "2–3 级科技", "goal": "60 秒、120 秒解锁后继续取件装配", "focus": "economy"},
                   {"from": 180, "to": 420, "title": "4 级与保障", "goal": "备齐两份资源装配 4 级，之后继续往返并随时救援", "focus": "support"}],
        "unit": {"role": "科技与救援", "task": "资源区取件、装配区停稳装配，按时间升到 4 级；8 m 内有队友翻倒先去扶正",
                 "route": [ENGINEER_START, RESOURCE, ASSEMBLY], "anchor": ASSEMBLY},
        "rules": [{"when": "8 m 内有翻倒的队友且自身未虚弱", "then": "先开到队友旁用机械臂扶正"},
                  {"when": "手里资源不够当前难度", "then": "回资源区取件，4 级需要两份"},
                  {"when": "资源到手", "then": "到装配区停稳，插入、平移、旋转并确认"}, REVIVE_RULE],
        "priorities": ["8 m 内翻倒的队友", "已解锁的最高科技等级"],
        "strengths": ["科技与救援兼顾，翻倒的队友能很快回到战场", "装配前先停稳对位，兑换稳定"],
        "weaknesses": ["不避战，往返路线上容易被拦截", "救援范围只有 8 m，远处的队友顾不上", "不重建己方前哨站"],
    },
    ("engineer", "assault"): {
        "tactic": "economy", "tags": ["assembly"],
        "tagline": "整场只做一件事：取件、装配、升科技",
        "summary": "不停往返于己方资源区与装配区：取到足够资源就开到装配区停稳，选择已解锁的最高难度装配，0、60、120、180 秒依次解锁 1–4 级，4 级备齐两份资源。由于随时都有可做的装配，实战中不会停下来救援队友。阵亡后金币够且未到 300 秒就立即买活。",
        "style": {"aggression": 0, "defense": 15, "economy": 95, "objective": 35, "teamwork": 30, "adaptability": 25},
        "phases": [{"from": 0, "to": 60, "title": "抢 1 级", "goal": "开局直奔资源区取件，上中央高地装配 1 级科技", "focus": "economy"},
                   {"from": 60, "to": 180, "title": "连升 2–3 级", "goal": "60 秒、120 秒解锁后马上装配下一级", "focus": "economy"},
                   {"from": 180, "to": 420, "title": "冲 4 级", "goal": "备齐两份资源装配 4 级，之后继续往返装配", "focus": "economy"}],
        "unit": {"role": "科技核心", "task": "在资源区与装配区之间往返，每次停稳后装配已解锁的最高难度",
                 "route": [ENGINEER_START, RESOURCE, ASSEMBLY], "anchor": ASSEMBLY},
        "rules": [{"when": "手里资源不够当前难度", "then": "回资源区取件，4 级需要两份"},
                  {"when": "资源到手", "then": "开到装配区停稳完成装配"},
                  {"when": "更高一级科技解锁", "then": "立即改做更高一级"}, REVIVE_RULE],
        "priorities": ["已解锁的最高科技等级"],
        "strengths": ["科技节奏最快，经济收益稳定", "不分心，路线固定"],
        "weaknesses": ["实战中从不救援翻倒的队友", "不避战，往返途中容易被拦截", "不重建己方前哨站"],
    },
    ("engineer", "guard"): {
        "tactic": "guard", "tags": ["rescue"],
        "tagline": "专职救援：哪里有人翻倒就去哪里，平时跟在前线身后",
        "summary": "场上有翻倒的队友（能自行翻身的串联腿除外）就赶去用机械臂扶正，不限距离；没人需要救援时跟在最靠前的英雄或步兵身后约 1.5 m，前线没人时停在己方堡垒旁。这一套路完全不做科技装配。阵亡后金币够且未到 300 秒就立即买活。",
        "style": {"aggression": 5, "defense": 45, "economy": 5, "objective": 10, "teamwork": 90, "adaptability": 50},
        "phases": [{"from": 0, "to": 300, "title": "随队保障", "goal": "跟在最靠前的队友身后，有队友翻倒就立即赶去扶正", "focus": "support"},
                   {"from": 300, "to": 420, "title": "残局保障", "goal": "继续随队救援；" + LATE_REVIVE, "focus": "support"}],
        "unit": {"role": "随队救援", "task": "队友翻倒就赶去扶正；平时跟在最靠前的英雄或步兵身后约 1.5 m，前线没人时停在己方堡垒旁",
                 "route": [ENGINEER_START, [5.4, 7.5]]},
        "rules": [{"when": "有翻倒的队友且自身未虚弱", "then": "不限距离赶去，用机械臂扶正"},
                  {"when": "没人需要救援", "then": "跟在最靠前的英雄或步兵身后约 1.5 m"},
                  {"when": "前线没有存活的英雄和步兵", "then": "停在己方堡垒旁待命"}, REVIVE_RULE],
        "priorities": ["翻倒的队友", "最靠前的队友"],
        "strengths": ["救援不限距离，翻倒的队友能很快回到战场", "始终贴近前线，随时可以施救"],
        "weaknesses": ["完全不做科技装配，经济和等级落后", "跟随前线时自身容易被集火", "不重建己方前哨站"],
    },
    ("aerial", "balanced"): {
        "tactic": "balanced", "tags": ["aerial"],
        "tagline": "飞到航道前端，全程开启空中支援，打最近的敌人",
        "summary": "从停机坪起飞，沿己方航道飞到前端，以 1.9 m 高度悬停并全程开启空中支援，对最近的可见敌人按提前量射击。不打能量机关，也不会为节省金币关闭支援。",
        "style": {"aggression": 60, "defense": 25, "economy": 10, "objective": 30, "teamwork": 40, "adaptability": 30},
        "phases": [{"from": 0, "to": 20, "title": "起飞", "goal": "开启支援，从停机坪飞往航道前端", "focus": "support"},
                   {"from": 20, "to": 420, "title": "空中火力", "goal": "在航道前端悬停，持续攻击最近的可见敌人", "focus": "attack"}],
        "unit": {"role": "空中火力", "task": "在己方航道前端 1.9 m 高度悬停，射击最近的可见敌人",
                 "route": [AERIAL_PAD, [13.0, 1.85]], "anchor": [13.0, 1.85]},
        "rules": [{"when": "发现可见敌人", "then": "瞄准最近的一个，按其速度提前量开火"},
                  {"when": "整场比赛", "then": "保持空中支援开启，1.9 m 高度悬停"}],
        "priorities": ["最近的可见敌人"],
        "strengths": ["空中视角覆盖敌方前哨一侧", "开局就能提供火力"],
        "weaknesses": ["支援全程开启，超出免费时长后持续耗费金币", "不打能量机关", "不挑目标价值，弹药可能浪费在高血量目标上"],
    },
    ("aerial", "assault"): {
        "tactic": "assault", "tags": ["aerial", "outpost_rush"],
        "tagline": "悬停航道最前端，弹幕只倾泻在敌方前哨站和基地上",
        "summary": "飞到己方航道最前端，以 1.9 m 高度悬停并全程开启空中支援；敌方前哨站在弹道范围内就持续射击，前哨倒下后改打敌方基地，不与机器人交火。",
        "style": {"aggression": 70, "defense": 10, "economy": 5, "objective": 85, "teamwork": 30, "adaptability": 15},
        "phases": [{"from": 0, "to": 20, "title": "起飞", "goal": "开启支援，从停机坪飞往航道最前端", "focus": "support"},
                   {"from": 20, "to": 420, "title": "压制建筑", "goal": "前哨站在就打前哨站，倒下后改打敌方基地", "focus": "objective"}],
        "unit": {"role": "空中炮台", "task": "在己方航道最前端悬停，只射击敌方前哨站，前哨倒下后改打敌方基地",
                 "route": [AERIAL_PAD, [13.2, 1.85]], "anchor": [13.2, 1.85]},
        "rules": [{"when": "敌方前哨站还在且在弹道范围内", "then": "持续射击前哨站"},
                  {"when": "敌方前哨站倒下", "then": "改打敌方基地"},
                  {"when": "目标不在弹道范围内", "then": "停火待命"}],
        "priorities": ["敌方前哨站", "敌方基地"],
        "strengths": ["从空中持续压制敌方前哨站", "不被地面交火分心"],
        "weaknesses": ["敌方基地护甲关闭时只有 42mm 能造成伤害，此时打基地是白耗弹药", "支援全程开启，持续耗费金币", "不拦截来犯的敌方机器人"],
    },
    ("aerial", "guard"): {
        "tactic": "guard", "tags": ["aerial"],
        "tagline": "守在航道后段的停机坪上空，只打 8 m 内的来犯者",
        "summary": "开启空中支援后停在己方航道后段、停机坪附近，以 1.9 m 高度悬停；只攻击 8 m 内的敌人，平时不开火。全程保持支援开启。",
        "style": {"aggression": 15, "defense": 70, "economy": 10, "objective": 10, "teamwork": 35, "adaptability": 20},
        "phases": [{"from": 0, "to": 420, "title": "后场警戒", "goal": "在停机坪上空悬停，8 m 内出现敌人才开火", "focus": "defense"}],
        "unit": {"role": "后场哨兵", "task": "在己方航道后段悬停，只射击 8 m 内的敌人",
                 "route": [AERIAL_PAD, [1.3, 1.85]], "anchor": [1.3, 1.85]},
        "rules": [{"when": "8 m 内出现敌人", "then": "按提前量射击"},
                  {"when": "敌人在 8 m 外", "then": "不开火，保存弹药"}],
        "priorities": ["8 m 内的敌人"],
        "strengths": ["守住己方后场与停机坪一带", "很少消耗弹药"],
        "weaknesses": ["远离主战场，火力利用率低", "支援全程开启，持续耗费金币", "不打能量机关和敌方建筑"],
    },
    ("infantry", "balanced"): {
        "tactic": "balanced", "tags": ["outpost_rush"],
        "tagline": "跟进到敌方前哨站前 3 m 交火，控热射击，残血回补给",
        "summary": "沿用官方基线：开到敌方前哨站前约 3 m 处（按编号上下错开），射程内有可命中的敌人先打人，否则打前哨站；前哨倒下后推进到敌方基地前约 3 m。射击时留出 20 点热量余量。血量低于 25% 或虚弱回补给区，弹药打空回基地补弹；阵亡后金币够且未到 300 秒就立即买活。",
        "style": {"aggression": 65, "defense": 25, "economy": 15, "objective": 60, "teamwork": 25, "adaptability": 35},
        "phases": [OPENING,
                   {"from": 30, "to": 300, "title": "压前哨 · 推基地", "goal": "在敌方前哨站前约 3 m 交火；前哨倒下后推进到敌方基地前约 3 m", "focus": "attack"},
                   {"from": 300, "to": 420, "title": "残局", "goal": "继续交火；" + LATE_REVIVE, "focus": "attack"}],
        "unit": {"role": "前线步兵", "task": "在敌方前哨站前约 3 m 交火，见人先打人；前哨倒下后推进到敌方基地前约 3 m",
                 "route": [INFANTRY_START, [14.0, 3.6], [22.6, 7.5]], "anchor": [14.0, 3.6]},
        "rules": [{"when": "射程内有可命中的敌人", "then": "先打最近的敌人"},
                  {"when": "热量离上限不足 20", "then": "暂停射击散热"},
                  {"when": "敌方前哨站倒下", "then": "推进到敌方基地前约 3 m"},
                  {"when": "虚弱或血量低于 25%", "then": "撤回补给区"},
                  {"when": "弹药打空", "then": "回己方基地补弹"}, REVIVE_RULE],
        "priorities": ["射程内最近的敌人", "敌方前哨站", "敌方基地"],
        "strengths": ["控热射击，不会打到超热", "见人先打人，交火积极"],
        "weaknesses": ["直线压上，容易被敌方英雄和守军消耗", "敌方基地护甲关闭时仍对基地开火，17mm 打不动", "不会占领堡垒或启动能量机关"],
    },
    ("infantry", "assault"): {
        "tactic": "assault", "tags": ["outpost_rush", "base_rush"],
        "tagline": "顶到敌方前哨站前 2.6 m，见人打人，看不到敌人就打建筑",
        "summary": "开到敌方前哨站前约 2.6 m 处（按编号上下错开）；视野内有敌人就瞄准最近的一个（弹道够不着则暂不开火），看不到敌人时才打前哨站，前哨倒下后推进到敌方基地前约 2.6 m。血量低于 22%、虚弱或弹药打空时回补给区；阵亡后金币够且未到 300 秒就立即买活。",
        "style": {"aggression": 80, "defense": 15, "economy": 10, "objective": 70, "teamwork": 20, "adaptability": 30},
        "phases": [OPENING,
                   {"from": 30, "to": 300, "title": "贴身突击", "goal": "在敌方前哨站前约 2.6 m 交火，前哨倒下后推进到敌方基地前", "focus": "attack"},
                   {"from": 300, "to": 420, "title": "残局", "goal": "继续突击；" + LATE_REVIVE, "focus": "attack"}],
        "unit": {"role": "突击步兵", "task": "顶到敌方前哨站前约 2.6 m，先打视野内最近的敌人，看不到敌人就打建筑；前哨倒下后推进到敌方基地前",
                 "route": [INFANTRY_START, [14.4, 3.6], [23.0, 7.5]], "anchor": [14.4, 3.6]},
        "rules": [{"when": "视野内有敌人", "then": "瞄准最近的一个，弹道够得着才开火"},
                  {"when": "视野内没有敌人", "then": "射击敌方前哨站，前哨倒下后射击基地"},
                  {"when": "敌方前哨站倒下", "then": "推进到敌方基地前约 2.6 m"},
                  {"when": "血量低于 22%、虚弱或弹药打空", "then": "撤回补给区"}, REVIVE_RULE],
        "priorities": ["视野内最近的敌人", "敌方前哨站", "敌方基地"],
        "strengths": ["站位最靠前，对敌方前哨和来援机器人压力大", "看不到敌人时也持续输出建筑"],
        "weaknesses": ["不留热量余量，连射容易超热", "血量低于 22% 才撤退，往往来不及撤就被击毁", "敌方基地护甲关闭时仍对基地开火，17mm 打不动"],
    },
    ("infantry", "guard"): {
        "tactic": "guard", "tags": [],
        "tagline": "守在己方前哨站后方，只打 8 m 内的敌人，半血就回补",
        "summary": "驻守己方前哨站后方约 1.5 m 处（按编号上下错开），己方前哨被毁后退到己方基地后方。只攻击 8 m 内的敌人，不主动推进。血量低于 50%、虚弱或弹药打空就回补给区；阵亡后金币够且未到 300 秒就立即买活。",
        "style": {"aggression": 20, "defense": 85, "economy": 10, "objective": 15, "teamwork": 30, "adaptability": 30},
        "phases": [{"from": 0, "to": 30, "title": "就位", "goal": "开到己方前哨站后方的守位", "focus": "defense"},
                   {"from": 30, "to": 300, "title": "守前哨", "goal": "拦截 8 m 内的敌人，半血就回补给区", "focus": "defense"},
                   {"from": 300, "to": 420, "title": "残局", "goal": "继续驻守；己方前哨若已倒下则守在基地后方", "focus": "defense"}],
        "unit": {"role": "阵地步兵", "task": "守在己方前哨站后方，只打 8 m 内的敌人；己方前哨被毁后退到己方基地后方",
                 "route": [INFANTRY_START, [9.5, 11.4], [0.9, 7.5]], "anchor": [9.5, 11.4]},
        "rules": [{"when": "8 m 内出现敌人", "then": "按提前量开火"},
                  {"when": "敌人在 8 m 外", "then": "不开火，守住站位"},
                  {"when": "己方前哨站被毁", "then": "退守己方基地后方"},
                  {"when": "血量低于 50%、虚弱或弹药打空", "then": "回补给区"}, REVIVE_RULE],
        "priorities": ["8 m 内的敌人"],
        "strengths": ["靠近补给区，半血即撤，存活率高", "守住己方前哨站一侧通道"],
        "weaknesses": ["不参与进攻，拆不了敌方建筑", "8 m 外的敌人一概不打", "己方前哨倒下后退得太深，让出中场"],
    },
}
CHASSIS = {"mecanum": "麦轮底盘", "swerve": "舵轮底盘", "omni": "全向轮底盘", "wheel_legged": "轮足底盘", "quadrotor": "旋翼", "hangar": "机库"}


def cards_2027():
    spec = importlib.util.spec_from_file_location("robot_cards_2027", ROOT / "scripts/robot_cards_2027.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.CARDS


def legal_models(season):
    return [model for model in model_ids() if season_rules.legal(model, season)]


def sidecars(model, tactic, season="2026"):
    """showcase.json and profile.json contents for one preset."""
    design = robot_models()[str(model)]
    role = design["role"]
    card = (CARDS if season == "2026" else cards_2027())[(role, tactic)]
    name = f'{design["name"]} · {(PROFILES if season == "2026" else PROFILES_2027)[role][tactic][0]}'
    if season != "2026":
        name = f"[2027] {name}"
    weaknesses = list(card["weaknesses"])
    if design.get("chassis_type") == "wheel_legged":
        weaknesses.append("不使用本型号的跳跃能力，台阶与飞坡只能靠寻路绕行" if season == "2026" else
                          "不主动利用跳跃登阶抄近路，只沿公路与端坡寻路")
    if design.get("transform_allowed"):
        weaknesses.append("不会变形穿越隧道，拿不到隧道冷却增益")
    summary = f'{design["name"]}（{CHASSIS.get(design.get("chassis_type"), "底盘")}）：{card["summary"]}'
    showcase = {"format": SHOWCASE_FORMAT, "title": name, "tagline": card["tagline"], "summary": summary,
                "style": card["style"], "phases": card["phases"], "units": [{"name": "本机", **card["unit"]}],
                "rules": card["rules"], "priorities": card["priorities"], "strengths": card["strengths"],
                "weaknesses": weaknesses}
    profile = validate_profile({"agent": {"provider": "official"}, "tactic": card["tactic"], "tags": card["tags"],
                                "display_name": name, "description": summary})
    return {SHOWCASE_FILE: showcase, PROFILE_FILE: profile}


def dump(data):
    """Stable, readable JSON: two-space indent with [x, y] points kept on one line."""
    text = json.dumps(data, ensure_ascii=False, indent=2)
    text = re.sub(r"\[\s*(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)\s*\]", r"[\1, \2]", text)
    return (text + "\n").encode()


def write_sidecars(destination, model, tactic, check, season="2026"):
    for name, data in sidecars(model, tactic, season).items():
        expected = dump(data)
        if name == SHOWCASE_FILE:
            parse_showcase(expected)
        elif validate_profile(json.loads(expected)) != data:
            raise SystemExit(f"Profile does not round-trip: {destination / name}")
        if check:
            if not (destination / name).is_file() or (destination / name).read_bytes() != expected:
                raise SystemExit(f"Outdated preset: {destination / name}")
        else:
            (destination / name).write_bytes(expected)


def materialize(destination, source_text, model, check, season):
    """strategy.py and manifest.json of one preset, built through the normal submission path."""
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / 'source.py'
        source.write_text(source_text)
        output = Path(temporary) / 'submission'
        save_submission(output, 'adaptive', {str(model): source}, model, season=season)
        for name in ('strategy.py', 'manifest.json'):
            expected = (output / name).read_bytes()
            if check:
                if not (destination / name).is_file() or (destination / name).read_bytes() != expected:
                    raise SystemExit(f'Outdated preset: {destination / name}')
            else:
                destination.mkdir(exist_ok=True)
                (destination / name).write_bytes(expected)


def build(check=False):
    template = (ROOT / 'scripts/robot_preset_template.py').read_text()
    baseline = (ROOT / 'examples/official_adaptive/strategy.py').read_text()
    for model in legal_models('2026'):
        balanced = ROOT / 'examples' / preset_key(model, 'balanced')
        if (balanced / 'manifest.json').is_file():
            load_submission(balanced)
        else:
            # Models added after the original presets (2027 infantry legal in 2026) get the baseline.
            materialize(balanced, baseline, model, check, '2026')
        for tactic in ('assault', 'guard'):
            materialize(ROOT / 'examples' / preset_key(model, tactic),
                        template.replace('TACTIC = "assault"', f'TACTIC = "{tactic}"'), model, check, '2026')
        for tactic in TACTICS:
            write_sidecars(ROOT / 'examples' / preset_key(model, tactic), model, tactic, check)
    policy = (ROOT / 'scripts/robot_policy_2027.py').read_text()
    for model in legal_models('2027'):
        for tactic in TACTICS:
            destination = ROOT / 'examples' / preset_key(model, tactic, '2027')
            materialize(destination, policy.replace('TACTIC = "balanced"', f'TACTIC = "{tactic}"'), model, check, '2027')
            write_sidecars(destination, model, tactic, check, '2027')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    build(parser.parse_args().check)
