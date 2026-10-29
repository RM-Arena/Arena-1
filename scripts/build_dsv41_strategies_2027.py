"""Publish the DeepSeek V4.1 Flash Max RMUC 2027 policies.

The controller lives in scripts/dsv41_policy_2027.py and is embedded verbatim in
every submission, so each published entry is self-contained and content addressed.
STYLE selects the tactical variant, LINEUPS the hardware for the lineup entries.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rmuc_arena.strategy_sources import authoring_examples

from rmuc_arena import seasons
from rmuc_arena.models import robot_models
from rmuc_arena.showcase import validate_profile, validate_showcase
from rmuc_arena.submissions import save_submission

AGENT = {'provider': 'deepseek', 'model': 'deepseek-v4.1-flash-max'}
# The adaptive entries are built on request only: they bind other hardware, and this
# controller was measured on the default 2027 lineup.
PUBLISH_ADAPTIVE = False

# One published entry: every STYLE hook was folded into the shared mechanism layer
# during development, so shipping four names for one controller would misdescribe it.
ENTRY = ('dsv41_2027_control', '锁点控制', 'siege',
         '用一台地面机器人常驻己方前哨卡、一台争夺敌方前哨卡，靠两点同时控制积累控制度；'
         '重型先做 1-3 级科技并安装 42mm，空中系统全程冲撞敌方前哨装甲。')

ROLE_TEXT = {
    'heavy': ('科技与经济', '先拾取能量单元完成 1-3 级科技提高全队收入，在工作台安装模块化 42mm，再从装配台附近用 42mm 打击建筑。'),
    'infantry': ('控制点锚点', '3 号常驻敌方前哨卡，4 号守己方前哨卡；卡片受威胁时最近的步兵回防，恢复阈值以上才重新前压。'),
    'sentry': ('守点与姿态管理', '守住己方前哨卡，安静时保持进攻姿态散热，被打到半血以下才切防御姿态，缺弹时远程补弹。'),
    'aerial': ('装甲拆解', '每架飞行器选择剩余行程最短的装甲面，贴近后直冲；优先敌方前哨，前哨清空后转向可受伤的基地。'),
}


def sidecars(title, model=None):
    label, tactic, description = ENTRY[1], ENTRY[2], ENTRY[3]
    chosen = [(model['name'], model['role'])] if model else [
        ('1 号重型', 'heavy'), ('3/4 号步兵', 'infantry'), ('6 号机库', 'aerial'), ('7 号哨兵', 'sentry')]
    units = [{'name': name[:16], 'role': ROLE_TEXT[role][0], 'task': ROLE_TEXT[role][1]} for name, role in chosen]
    tags = ['outpost_rush', 'aerial', 'assembly', 'focus_fire'] if model is None else {
        'heavy': ['assembly', 'outpost_rush'], 'infantry': ['outpost_rush', 'focus_fire'],
        'sentry': ['outpost_rush', 'sniping'], 'aerial': ['aerial', 'outpost_rush']}[model['role']]
    summary = description + ' 全部判断只使用公开观察：卡片坐标、判定进度、炮口实际朝向与型号能力都来自观察本身。'
    if model:
        description = ROLE_TEXT[model['role']][1]
        summary = f"适用于 {model['name']} 的自由适配策略；每次部署独立控制自身，按实际阵容选择己方卡片分工。" + description
    showcase = validate_showcase({
        'format': 'rmuc-showcase-v1', 'title': title, 'tagline': description, 'summary': summary,
        'generated_by': AGENT,
        'style': {'aggression': 60, 'defense': 75, 'economy': 75,
                  'objective': 100, 'teamwork': 80, 'adaptability': 65},
        'phases': [
            {'from': 0, 'to': 40, 'title': '开局抢位', 'goal': '机器人按卡片分工就位，重型先走上敌方前哨卡消耗对方控制点，步兵在出生点补弹。', 'focus': 'objective'},
            {'from': 40, 'to': 180, 'title': '拆位与科技', 'goal': '拆掉敌方前哨控制点后重型转入 1-3 级科技，步兵继续守住两张卡，空中系统持续冲撞旋转装甲。', 'focus': 'economy'},
            {'from': 180, 'to': 330, 'title': '控制度争夺', 'goal': description, 'focus': 'objective'},
            {'from': 330, 'to': 420, 'title': '终局守分', 'goal': '领先时不再离开卡片，落后时优先抢回己方控制点，保证到时比较控制度不吃亏。', 'focus': 'defense'},
        ],
        'units': units,
        'rules': [
            {'when': '己方前哨卡判定进度超过 4 秒', 'then': '最近的步兵立刻回防，重新站上卡片把进度顶回去。'},
            {'when': '敌方前哨控制点仍被敌方完全控制', 'then': '重型留在该卡片上继续消耗，不参与火力对射。'},
            {'when': '炮口实际朝向与解算角度相差超过容差', 'then': '只转动云台，不开火；对准后的下一拍才击发。'},
            {'when': '血量低于 30% 或进入弱化状态', 'then': '撤到补给区或已完全控制的前哨卡回复到 82% 再回位。'},
        ],
        'priorities': ['两张前哨卡的同时控制', '己方前哨控制点不被夺走', '科技装配与 42mm 火力', '可命中的敌人'],
        'strengths': ['一台机器人即可维持一个控制点的活性', '按卡片坐标与判定进度决策，不看伤害数字',
                      '按实际炮口朝向校验开火，迭代解算弹道提前量'],
        'weaknesses': ['对同时压制两张卡片的对手需要不断换位', '未实现能量机关激活', '轮足型号翻倒后仍依赖重型救援'],
    })
    if model:
        role = model['role']
        goals = {
            'heavy': ['走上敌方前哨卡，先把对方控制点拆掉。', '回到装配台完成 1-3 级科技，提高全队收入。',
                      '在工作台安装模块化 42mm，必要时争取四级防御。', '在装配台附近控热射击，弹药不足时补充。'],
            'infantry': ['出生点补弹后按分工前往己方或敌方前哨卡。', '守住卡片，只在对方进度即将完成时换位回防。',
                         '血量跌破阈值就撤到补给区或完全控制的前哨卡。', '控制度领先时不再主动离开卡片换取伤害。'],
            'sentry': ['开局补弹后前往己方前哨卡，建立守点火力。', '安静时保持进攻姿态散热，被压制时切防御姿态。',
                       '缺弹时远程补弹或利用配给，不轻易离开卡片。', '终局保留控制点存在，必要时用强化姿态顶住一波。'],
            'aerial': ['起飞后选择剩余行程最短的装甲面冲撞敌方前哨。', '每次决策重新评估目标，不固定等待某个方位。',
                       '敌方前哨清空且基地可受伤时转向基地装甲。', '电量低于阈值回库停靠，保留剩余航时。'],
        }[role]
        for phase, goal in zip(showcase['phases'], goals):
            phase['goal'] = goal
        showcase['rules'] = {
            'heavy': [{'when': '尚未安装 42mm 且敌方前哨控制点未被拆掉', 'then': '留在敌方前哨卡上消耗对方控制点。'},
                      {'when': '控制点被拆掉或已安装 42mm', 'then': '转到装配台完成科技并输出。'},
                      {'when': '附近有翻倒队友且科技已起步', 'then': '在限时内尝试机械臂救援。'}],
            'infantry': [{'when': '己方卡片判定进度上升', 'then': '立刻回防并站回卡片。'},
                         {'when': '敌方控制点未被拆掉', 'then': '留在敌方卡片上消耗，不追打撤退的敌人。'},
                         {'when': '血量低于 30%', 'then': '进入撤退状态直到回复到 82%。'}],
            'sentry': [{'when': '卡片安静且弹药充足', 'then': '保持进攻姿态，用三倍散热维持持续火力。'},
                       {'when': '半血以下且正在挨打', 'then': '切换防御姿态，必要时用强化姿态顶住。'},
                       {'when': '弹药低于 45 发', 'then': '远程补弹，不离开卡片。'}],
            'aerial': [{'when': '存在归属敌方的前哨', 'then': '选择剩余行程最短的装甲面冲撞。'},
                       {'when': '前哨清空且基地可受伤', 'then': '转向基地装甲面。'},
                       {'when': '电量不足', 'then': '回库停靠，保留剩余电量。'}],
        }.get(role, showcase['rules'])
        if role == 'aerial':
            showcase['strengths'] = ['每拍重新选择最近装甲面', '贴近后直冲，不等待旋转相位', '电量不足才回库']
            showcase['weaknesses'] = ['护罩耗尽后该机不能继续使用', '机库不充电，整局续航有限', '基地无敌时不能造成伤害']
        showcase = validate_showcase(showcase)
    profile = validate_profile({'agent': AGENT, 'author': 'deepseek-v4.1-flash-max', 'tactic': tactic,
                                'tags': tags, 'display_name': title, 'description': summary})
    return showcase, profile


def outputs():
    policy = (ROOT / 'scripts/dsv41_policy_2027.py').read_text()
    with tempfile.TemporaryDirectory(prefix='dsv41-submissions-') as temporary:
        folder = Path(temporary)

        def entry(name, model=None, title=None):
            source = folder / (name + '.py')
            source.write_text(policy)
            showcase, profile = sidecars(title, model)
            output = folder / name
            save_submission(output, 'adaptive' if model else 'team',
                            {str(model['slot']) if model else 'team': source},
                            robot=model['slot'] if model else None,
                            team_lineup=None if model else seasons.default_lineup('2027'),
                            showcase=showcase, profile=profile, season='2027')
            return {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}

        name, label = ENTRY[0], ENTRY[1]
        yield name, entry(name, title=f'DeepSeek · {label} 2027')
        if PUBLISH_ADAPTIVE:
            models = robot_models()
            for model_id in seasons.legal_models('2027'):
                model = models[str(model_id)]
                name = f'dsv41_2027_adaptive_{model_id}'
                yield name, entry(name, model=model, title=f'DeepSeek · {model_id} 型 2027')


def smoke(entries):
    """Run the compiled controller against one real opening observation per entry, so a
    missing import or a bad early decision fails the build instead of the match."""
    from rmuc_arena.engine import Match
    sys.path.insert(0, str(ROOT / 'rmuc_arena'))
    lineup = {1: 2711, 3: 2731, 4: 2732, 6: 2761, 7: 2771}
    teams = {'red': [{'slot': slot, 'model': model} for slot, model in lineup.items()],
             'blue': [{'slot': slot, 'model': model} for slot, model in lineup.items()]}
    match = Match(seed=7, duration=20, map_name='rmuc2027', lineups=teams)
    try:
        observation = match.observation('red', None)
        observation['message_inboxes'] = {slot: [] for slot in observation['controlled_ids']}
        observation['messages'] = []
        for key, source in entries.items():
            module = {'__name__': f'dsv41_smoke_{key}'}
            exec(compile(source, f'{key}/strategy.py', 'exec'), module)
            commands, state = module['act'](json.loads(json.dumps(observation)), {})
            if not commands:
                raise SystemExit(f'{key}: the controller returned no commands on the opening tick')
            for slot, fields in commands.items():
                for field, value in fields.items():
                    if isinstance(value, float) and value != value:
                        raise SystemExit(f'{key}: slot {slot} produced NaN in {field}')
    finally:
        match.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=authoring_examples())
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--no-smoke', action='store_true', help='Skip the opening-observation smoke test')
    parser.add_argument('--with-adaptive', action='store_true', help='Also build one entry per legal 2027 model')
    args = parser.parse_args()
    global PUBLISH_ADAPTIVE
    PUBLISH_ADAPTIVE = args.with_adaptive
    changed, count, samples = [], 0, {}
    for name, files in outputs():
        count += 1
        samples[name] = files['strategy.py'].decode()
        for filename, data in files.items():
            target = args.output / name / filename
            if target.is_file() and target.read_bytes() == data:
                continue
            changed.append(str(target))
            if not args.check:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
    if not args.no_smoke:
        smoke(samples)
    if args.check and changed:
        raise SystemExit('Stale DeepSeek strategies: ' + ', '.join(changed))
    print(f'{count} DeepSeek V4.1 Flash Max submissions validated'
          + ('' if args.no_smoke else ' and smoke-tested')
          + f'; {len(changed)} files ' + ('need updating.' if args.check else 'updated.'))


if __name__ == '__main__':
    main()
