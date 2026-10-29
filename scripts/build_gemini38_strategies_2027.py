"""Submit Gemini 3.8 Flash RMUC 2027 policies through the standard content-addressed writer.

Generates self-contained submissions with valid showcase.json and profile.json.
Agent signature: google / gemini-3.8-flash
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
from rmuc_arena.showcase import validate_profile, validate_showcase
from rmuc_arena.submissions import save_submission

AGENT = {'provider': 'google', 'model': 'gemini-3.8-flash'}

STYLES = {
    'blitz': ('极速锁点', 'assault', '开局超级电容加速抢占前哨卡，双机互锁卡位；建立控制度领先后梯次收缩防守。'),
    'tech_overload': ('科技重装', 'balanced', '重型快速完成1~3级科技装配，高地架设42mm狙击炮台；哨兵智能三姿态，步兵护卫协同。'),
    'hunter': ('游猎突袭', 'assault', '集火敌方残血与虚弱目标，侧翼迂回压制敌方补给线；动态脱战回血，保持全队健康存活。'),
}


def sidecars(style, title):
    label, tactic, description = STYLES[style]
    roles = {
        'heavy': ('科技与炮火', '取件完成科技装配，安装42mm发射模块；在战略炮位控热超视距支援控制点。'),
        'infantry': ('先锋与互锁', '开局超级电容突进抢占前哨卡，多边形安全偏移站位互锁；确立领先优势后组织防线。'),
        'sentry': ('自适应守点', '根据交火和血量在防御/攻击/机动三姿态间自适应切换，守住关键关联卡并组织换防。'),
        'aerial': ('自适应拦截', '预测旋转装甲接触点快速冲撞敌方前哨；清除前哨且基地脆弱时直扑基地。')
    }
    units = [
        {'name': '1 号重型', 'role': roles['heavy'][0], 'task': roles['heavy'][1]},
        {'name': '3/4 号步兵', 'role': roles['infantry'][0], 'task': roles['infantry'][1]},
        {'name': '6 号机库', 'role': roles['aerial'][0], 'task': roles['aerial'][1]},
        {'name': '7 号哨兵', 'role': roles['sentry'][0], 'task': roles['sentry'][1]}
    ]
    tags = ['mobility', 'focus_fire', 'outpost_rush', 'assembly', 'aerial']
    summary = f"Gemini 3.8 Flash 开发的 2027 赛季{label}策略。{description}"

    style_scores = {
        'blitz': {'aggression': 85, 'defense': 65, 'economy': 70, 'objective': 95, 'teamwork': 90, 'adaptability': 85},
        'tech_overload': {'aggression': 60, 'defense': 85, 'economy': 95, 'objective': 85, 'teamwork': 90, 'adaptability': 80},
        'hunter': {'aggression': 90, 'defense': 60, 'economy': 65, 'objective': 80, 'teamwork': 85, 'adaptability': 95},
    }[style]

    showcase = validate_showcase({
        'format': 'rmuc-showcase-v1',
        'title': title,
        'tagline': description,
        'summary': summary,
        'generated_by': AGENT,
        'style': style_scores,
        'phases': [
            {'from': 0, 'to': 60, 'title': '开局冲刺', 'goal': '就地补弹，超级电容直冲前哨卡建立初始占领，无人机破防前哨，重型启动装配。', 'focus': 'objective'},
            {'from': 60, 'to': 180, 'title': '科技与占领', 'goal': '完成关键科技升级解锁发射模块，步兵双机互锁卡位，形成前哨火力压制。', 'focus': 'economy' if style == 'tech_overload' else 'objective'},
            {'from': 180, 'to': 330, 'title': '控制度争夺', 'goal': description, 'focus': 'objective'},
            {'from': 330, 'to': 420, 'title': '优势终局', 'goal': '控制度领先时全面梯次固守己方两张关联卡，落后时组织终局换家突击。', 'focus': 'defense'}
        ],
        'units': units,
        'rules': [
            {'when': '开局前 12 秒接近前哨卡', 'then': '释放超级电容全功率冲刺抢占独占判定。'},
            {'when': '控制度领先超过安全阈值', 'then': '全队梯次收缩固守关联卡，杜绝空点追敌。'},
            {'when': '发现敌方血量低于 35% 或虚弱单位', 'then': '全队射程内火力优先转火集火歼灭。'},
            {'when': '重型机器人 42mm 发射模块就绪', 'then': '占据中路制高点或战略炮位实施重炮狙击。'}
        ],
        'priorities': ['己方前哨控制点', '敌方残血集火', '控制度积累', '科技装配升级'],
        'strengths': [
            '超级电容开局突进与战术脱战爆发',
            '空气阻力与双轮迭代弹道精确解算',
            '多边形安全偏移互锁避免卡滞与扎堆',
            '自适应哨兵姿态引擎与快速装配流水线'
        ],
        'weaknesses': [
            '超级电容耗尽后恢复期间机动性回归常规',
            '极度偏向控制度保分，大比分落后时翻盘依赖基地强突'
        ]
    })

    profile = validate_profile({
        'format': 'rmuc-strategy-profile-v1',
        'agent': AGENT,
        'author': 'gemini-3.8-flash',
        'tactic': tactic,
        'tags': tags,
        'display_name': title,
        'description': summary
    })
    return showcase, profile


def outputs():
    policy = (ROOT / 'scripts/gemini38_policy_2027.py').read_text(encoding='utf-8')
    with tempfile.TemporaryDirectory(prefix='gemini38-submissions-') as temporary:
        folder = Path(temporary)
        for style, (label, _, _) in STYLES.items():
            name = f'gemini38_2027_{style}'
            source = folder / f'{name}.py'
            source.write_text(policy.replace('STYLE = "blitz"', f'STYLE = "{style}"'), encoding='utf-8')
            showcase, profile = sidecars(style, f'Gemini · {label} 2027')
            output = folder / name
            save_submission(
                output,
                'team',
                {'team': source},
                team_lineup=seasons.default_lineup('2027'),
                showcase=showcase,
                profile=profile,
                season='2027'
            )
            yield name, {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=authoring_examples())
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()

    count, changed = 0, []
    for name, files in outputs():
        count += 1
        target_dir = args.output / name
        target_dir.mkdir(parents=True, exist_ok=True)
        for filename, data in files.items():
            target = target_dir / filename
            if target.is_file() and target.read_bytes() == data:
                continue
            changed.append(str(target))
            if not args.check:
                target.write_bytes(data)

    if args.check and changed:
        raise SystemExit(f"Stale Gemini strategies: {', '.join(changed)}")
    print(f"{count} Gemini 3.8 Flash submissions validated; {len(changed)} files " +
          ('need updating.' if args.check else 'updated.'))


if __name__ == '__main__':
    main()
