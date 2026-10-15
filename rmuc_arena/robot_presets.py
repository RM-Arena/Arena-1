"""Display metadata for the three organizer-owned policies of each model and season."""

TACTICS = ("balanced", "assault", "guard")
PROFILES = {
    "hero": {
        "balanced": ("均衡推进", "兼顾交战与补给，逐步推进敌方建筑。"),
        "assault": ("重炮攻坚", "优先攻击前哨站和基地，保持远程炮击距离。"),
        "guard": ("后场守卫", "驻守己方前哨附近，优先拦截接近的敌人。"),
    },
    "infantry": {
        "balanced": ("均衡推进", "优先交战，兼顾推进、补给与生存。"),
        "assault": ("前线突击", "主动向敌方前哨推进，优先清理前进路线上的敌人。"),
        "guard": ("阵地防守", "守住己方前哨，拦截附近敌人，较早回补。"),
    },
    "engineer": {
        "balanced": ("综合保障", "就近救援倒地队友，随后拾取资源并完成科技装配。"),
        "assault": ("科技优先", "优先拾取资源与完成科技装配，空闲时再救援。"),
        "guard": ("救援优先", "主动救援倒地队友，无人待救时跟随前线提供保障。"),
    },
    "aerial": {
        "balanced": ("前线支援", "前移至航道前端，攻击可见敌人并提供空中支援。"),
        "assault": ("空中压制", "保持航道前端位置，优先压制敌方前哨和基地。"),
        "guard": ("后场掩护", "保持航道后段位置，拦截接近己方阵地的敌人。"),
    },
}
# RMUC 2027 presets come from scripts/robot_policy_2027.py.
PROFILES_2027 = {
    "heavy": {
        "balanced": ("科技重炮", "取能量单元完成 1–4 级装配，装上 42mm 后从中央高地炮击建筑。"),
        "assault": ("速攻重炮", "完成 1–3 级装配后立即装炮，不做 4 级，尽早炮击敌方前哨与基地。"),
        "guard": ("守势重炮", "完成装配与装炮后守在己方前哨一侧，优先拦截来犯之敌。"),
    },
    "infantry": {
        "balanced": ("控制点争夺", "夺取敌方前哨控制点，180 秒后进攻敌方堡垒；己方控制点失守时回防。"),
        "assault": ("前哨突击", "直扑敌方前哨卡与中央高地，压制敌方前哨站。"),
        "guard": ("控制点守备", "守住己方中央高地与前哨卡，只拦截附近敌人，较早回补。"),
    },
    "sentry": {
        "balanced": ("中央高地哨卫", "占住己方中央高地卡守住前哨控制点，按战况切换进攻、防御、移动姿态。"),
        "assault": ("前压哨兵", "己方夺得敌方前哨控制点后前压到敌方中央高地卡。"),
        "guard": ("固守哨兵", "常驻己方中央高地卡，默认防御姿态。"),
    },
    "aerial": {
        "balanced": ("撞击编队", "空中机器人对准旋转装甲定时冲撞敌方前哨，之后撞击失去无敌的敌方基地。"),
        "assault": ("全程突袭", "持续撞击前哨与基地，不保留编队。"),
        "guard": ("前哨清障", "只撞击前哨站（含被对方重建为其所有的前哨），300 秒后才撞击基地。"),
    },
}


def preset_key(model, tactic, season="2026"):
    suffix = "" if tactic == "balanced" else "_" + tactic
    prefix = "official_adaptive" if str(season) == "2026" else f"official_{season}_adaptive"
    return f"{prefix}_{model}{suffix}"


def preset_metadata(key, model, role, season=None):
    for current in ((season,) if season else ("2026", "2027")):
        table = PROFILES if str(current) == "2026" else PROFILES_2027
        for tactic in TACTICS:
            if key == preset_key(model, tactic, current) and role in table:
                name, description = table[role][tactic]
                return {"id": tactic, "name": name, "description": description}
    return None
