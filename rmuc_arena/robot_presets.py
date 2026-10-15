"""Display metadata for the three organizer-owned policies of each model."""

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


def preset_key(model, tactic):
    suffix = "" if tactic == "balanced" else "_" + tactic
    return f"official_adaptive_{model}{suffix}"


def preset_metadata(key, model, role):
    for tactic in TACTICS:
        if key == preset_key(model, tactic):
            name, description = PROFILES[role][tactic]
            return {"id": tactic, "name": name, "description": description}
    return None
