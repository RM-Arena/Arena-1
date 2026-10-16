"""Submit the GPT-6.1 Sol xhigh policies through the standard content-addressed writer.

The controller is self-contained in each entry. Team entries bind their hardware;
adaptive entries control only the observed instance of their registered model.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rmuc_arena import seasons
from rmuc_arena.models import robot_models
from rmuc_arena.showcase import validate_profile, validate_showcase
from rmuc_arena.submissions import save_submission

AGENT = {'provider': 'openai', 'model': 'gpt-6.1-sol-xhigh'}
STYLES = {
    'control': ('双点锁链', 'balanced', '先争前哨控制度，领先后回守；保留占点机器人，另一台步兵再进攻堡垒。'),
    'pressure': ('协同压制', 'assault', '两台步兵从前哨卡推进，哨兵在有队友接防时前压；控制度领先后收缩。'),
    'fortress': ('堡垒反击', 'guard', '步兵分别守己方前哨卡和高地卡，哨兵错开站位，重型升科技后提供火力。'),
}
PUBLISHED_STYLES = ('control', 'pressure')
LINEUPS = {
    'dual_arm': ('双臂重装', {'1': 2712, '3': 304, '4': 302, '6': 2763, '7': 2772}),
    'omni': ('全向机动', {'1': 2713, '3': 303, '4': 301, '6': 2762, '7': 2771}),
    'serial': ('串联腿协同', {'1': 2712, '3': 305, '4': 3, '6': 2763, '7': 2772}),
    'assault': ('突击与稳健', {'1': 2711, '3': 4, '4': 7, '6': 2761, '7': 2771}),
}


def sidecars(style, title, model=None):
    label, tactic, description = STYLES[style]
    roles = {'heavy': ('科技与炮火', '取件完成科技装配，返回工作台安装 42mm；之后控热射击、补弹并支援控制点。'),
             'infantry': ('控制点步兵', '按底盘稳定性、自复位能力与速度分工，夺取或接防前哨控制点，留人守点后再进攻堡垒。'),
             'sentry': ('守点与轮换', '守住己方高地卡，按交战情况切换姿态；有队友接防时补弹和回血。'),
             'aerial': ('空中拆解', '分配撞击方位，追踪旋转装甲；优先敌方前哨，再处理可受伤的基地。')}
    chosen = [(model['name'], model['role'])] if model else [('1 号重型', 'heavy'), ('3/4 号步兵', 'infantry'), ('6 号机库', 'aerial'), ('7 号哨兵', 'sentry')]
    units = [{'name': name[:16], 'role': roles[role][0], 'task': roles[role][1]} for name, role in chosen]
    tags = ['assembly', 'aerial', 'focus_fire', 'outpost_rush'] if model is None else {
        'heavy': ['assembly', 'rescue'], 'infantry': ['focus_fire', 'mobility'],
        'sentry': ['focus_fire'], 'aerial': ['aerial', 'outpost_rush']}[model['role']]
    summary = description + ' 使用实际炮口朝向校验瞄准，迭代计算飞行时间与运动提前量；尊重型号原生性能选择。补给和回血保持到恢复阈值，优先使用完全控制的前哨。'
    if model:
        description = roles[model['role']][1]
        summary = f"适用于 {model['name']}；每次部署独立控制自身，从实际阵容分工。" + description
    showcase = validate_showcase({'format': 'rmuc-showcase-v1', 'title': title, 'tagline': description,
        'summary': summary, 'generated_by': AGENT,
        'style': {'aggression': 35 if style == 'fortress' else 80 if style == 'pressure' else 60,
                  'defense': 90 if style == 'fortress' else 65, 'economy': 75,
                  'objective': 95, 'teamwork': 90, 'adaptability': 80},
        'phases': [
            {'from': 0, 'to': 60, 'title': '开局部署', 'goal': '就地补弹，机库拆前哨；重型完成一级装配，地面机器人建立控制点站位。', 'focus': 'objective'},
            {'from': 60, 'to': 180, 'title': '科技与接防', 'goal': '完成二三级装配并安装发射模块，按缺弹和血量接替守点。', 'focus': 'economy'},
            {'from': 180, 'to': 330, 'title': '控制度与堡垒', 'goal': description, 'focus': 'defense' if style == 'fortress' else 'objective'},
            {'from': 330, 'to': 420, 'title': '终局守分', 'goal': '领先时守住己方控制点，落后时继续争点；保留占点机器人和可用弹量。', 'focus': 'objective'}],
        'units': units,
        'rules': [
            {'when': '控制度领先达到收缩阈值', 'then': '步兵回守两张己方前哨关联卡，重型改用后方炮位。'},
            {'when': '己方前哨控制点失守', 'then': '地面机器人优先夺回己方控制点。'},
            {'when': '有人接替守点且哨兵缺弹', 'then': '在可用的己方前哨或补给区补弹。'},
            {'when': '炮口方向或俯仰尚未对准', 'then': '先转动云台，等待实际炮口进入射击误差范围。'}],
        'priorities': ['己方前哨控制点', '控制度', '科技装配', '可命中的敌人'],
        'strengths': ['根据控制度选择进攻或守分', '按实际炮口和飞行时间射击', '守点轮换减少控制点空窗'],
        'weaknesses': ['尚未实现能量机关激活', '无法自行翻身的轮足型号仍依赖重型救援', '弹量兑换达到全队上限后火力会下降']})
    if model:
        role = model['role']
        goals = {
            'heavy': ['先拾取能量单元并完成一级科技，保障全队收入。', '继续二三级装配，优先保障装配进行中的操作，接近的翻倒队友由机械臂救援。',
                      '在工作台安装 42mm；有资源和时间时争取四级防御，之后提供炮火。', '按控制度选择炮位，控热、补弹并保留血量。'],
            'infantry': ['在出生点补弹，按底盘稳定性、自复位能力和速度选择突进或接防。', '争取前哨控制点；保留守点机器人，低血量时持续恢复到阈值。',
                         '领先时回守，落后时争点；有队友留守敌方前哨时才进攻堡垒。', '根据实际控制度保护领先或继续争夺，按脱战条件补弹回血。'],
            'sentry': ['携初始弹量前往己方高地卡，建立守点火力。', '按交火、移动与血量切换姿态；缺弹时等待队友接防后补给。',
                       '持续守点，利用进攻姿态散热；补给区可领取累积配给。', '保留控制点存在，安全时远程回血，缺弹时与队友轮换。'],
            'aerial': ['分别起飞避开龙门，预测旋转装甲方位并冲撞敌方前哨。', '继续攻击仍归敌方的前哨；前哨清除且基地可受伤时转向基地。',
                       '依据建筑归属与控制点状态选择目标，保持各机独立冲撞节奏。', '护罩和电量允许时继续攻击；电量低则回库，回库不恢复电量。'],
        }[role]
        for phase, goal in zip(showcase['phases'], goals):
            phase['goal'] = goal
        showcase['rules'] = {
            'heavy': [{'when': '尚未完成一级科技', 'then': '优先取件和装配，保障初始科技收入。'},
                      {'when': '发射模块解锁', 'then': '返回工作台安装模块并补充 42mm。'},
                      {'when': '当前装配完成且附近有翻倒队友', 'then': '在限时内尝试机械臂救援，再继续装配或战斗。'}],
            'aerial': [{'when': '存在归属敌方的前哨', 'then': '分配撞击方位，预测旋转装甲接触时刻。'},
                       {'when': '前哨清除且敌方基地可受伤', 'then': '转向基地暴露装甲。'},
                       {'when': '电量不足或没有可攻击目标', 'then': '返回机库停靠，保留剩余电量。'}],
        }.get(role, showcase['rules'])
        if role == 'aerial':
            showcase['strengths'] = ['按装甲旋转提前量冲撞', '按建筑实际归属选择目标', '各机独立维护冲撞与退离节奏']
            showcase['weaknesses'] = ['护罩耗尽后该机不能继续使用', '机库不充电，整局续航有限', '基地无敌时不能造成伤害']
        showcase = validate_showcase(showcase)
    profile = validate_profile({'agent': AGENT, 'author': 'gpt-6.1-sol-xhigh', 'tactic': tactic,
                                'tags': tags, 'display_name': title, 'description': summary})
    return showcase, profile


def outputs(include_experimental=False):
    policy = (ROOT / 'scripts/gpt61_policy_2027.py').read_text()
    with tempfile.TemporaryDirectory(prefix='gpt61-submissions-') as temporary:
        folder = Path(temporary)
        def entry(name, style='control', lineup=None, model=None, title=None):
            source = folder / (name + '.py')
            source.write_text(policy.replace('STYLE = "control"', f'STYLE = "{style}"'))
            showcase, profile = sidecars(style, title, model)
            output = folder / name
            save_submission(output, 'adaptive' if model else 'team',
                {str(model['slot']) if model else 'team': source}, robot=model['slot'] if model else None,
                team_lineup=None if model else lineup, showcase=showcase, profile=profile, season='2027')
            return {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}
        for style in STYLES if include_experimental else PUBLISHED_STYLES:
            label, _, _ = STYLES[style]
            name = f'gpt61_2027_{style}'
            yield name, entry(name, style, seasons.default_lineup('2027'), title=f'GPT · {label} 2027')
        for key, (label, lineup) in LINEUPS.items():
            name = f'gpt61_2027_lineup_{key}'
            yield name, entry(name, lineup=lineup, title=f'GPT · {label} 2027')
        models = robot_models()
        for model_id in seasons.legal_models('2027'):
            model = models[str(model_id)]
            name = f'gpt61_2027_adaptive_{model_id}'
            yield name, entry(name, model=model, title=f'GPT · {model_id} 型 2027')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'examples')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--include-experimental', action='store_true', help='Include the evaluated defense experiment, excluded from the default publication set')
    args = parser.parse_args()
    changed, count = [], 0
    for name, files in outputs(args.include_experimental):
        count += 1
        for filename, data in files.items():
            target = args.output / name / filename
            if target.is_file() and target.read_bytes() == data:
                continue
            changed.append(str(target))
            if not args.check:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
    if args.check and changed:
        raise SystemExit('Stale GPT strategies: ' + ', '.join(changed))
    print(f'{count} GPT-6.1 Sol xhigh submissions validated; {len(changed)} files ' + ('need updating.' if args.check else 'updated.'))


if __name__ == '__main__':
    main()
