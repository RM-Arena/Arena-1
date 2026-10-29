"""Publish the DeepSeek V4.1 Flash 1017 Max RMUC 2027 policies.

The controller lives in scripts/dsv41_1017_policy_2027.py. Every entry embeds the same
source with STYLE replaced, so each submission is self-contained and content addressed.
The three cards share the mechanism layer; they differ only in which robot carries the
enemy base anchor.
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

AGENT = {'provider': 'deepseek', 'model': 'deepseek-v4.1-flash-1017-max'}
BASE_ROUTE = [[9.6, 4.7], [8.9, 2.2], [12.9, 3.3], [17.4, 1.1], [19.75, 2.7],
              [21.0, 2.5], [22.4, 3.0], [22.8, 5.1], [24.1, 4.8], [26.8, 4.4], [27.1, 7.5]]
HOME_ROUTE = [[3.2, 6.15], [7.2, 9.6], [8.25, 12.3], [11.9, 13.9], [12.0, 12.7], [11.4, 11.9], [10.8, 7.5]]

ENTRIES = {
    'sentry': {
        'name': 'dsv41_1017_sentry',
        'card': 'sentry',
        'title': 'DeepSeek · 釜底抽薪 2027',
        'tagline': '7 号哨兵独走敌方基地卡，控制度每秒 +3；双步兵守家，重型照常做科技。',
        'summary': '控制度由控制点决定：同时控制双方基地控制点每秒 +3，是前哨控制的三倍，而基地控制点只需要一张卡有人就能维持。'
                   '7 号哨兵沿南侧公开路点绕到敌方基地卡背面，停车保持临时控制；3、4 号步兵分别守住己方中央高地卡与前哨卡，'
                   '阻止对手拿到前哨控制度；1 号重型照常完成 1-3 级装配并安装 42mm；6 号机库冲撞敌方前哨装甲。'
                   '哨兵移动时切防御姿态，到达后停在基地车体背面，阵亡后先回补给区解除虚弱再返场。',
        'style': {'aggression': 55, 'defense': 85, 'economy': 70, 'objective': 100, 'teamwork': 80, 'adaptability': 70},
        'phases': [
            {'from': 0, 'to': 40, 'title': '开局分工', 'goal': '哨兵出发走南线，双步兵上己方中央高地卡与前哨卡，重型开始取件。', 'focus': 'objective'},
            {'from': 40, 'to': 120, 'title': '基地卡建立', 'goal': '哨兵绕过蓝方半场，停在敌方基地卡背面，控制度开始每秒 +3。', 'focus': 'objective'},
            {'from': 120, 'to': 330, 'title': '守卡与科技', 'goal': '守家双卡不掉，重型完成装配与 42mm；哨兵不离开基地卡。', 'focus': 'defense'},
            {'from': 330, 'to': 420, 'title': '终局守分', 'goal': '保持基地卡控制，哨兵阵亡则回补给区解除虚弱后尽快返场。', 'focus': 'defense'},
        ],
        'units': [
            {'name': '7 号哨兵', 'role': '基地卡主锚', 'task': '沿南侧公开路点绕到敌方基地卡背面，停车保持控制；受击时切防御姿态，血量低时使用强化防御。', 'route': BASE_ROUTE, 'anchor': [27.1, 7.5]},
            {'name': '3/4 号步兵', 'role': '守家双卡', 'task': '分别站在己方中央高地卡与前哨卡，阻止对手夺取己方前哨控制点；只在卡片被直接威胁时换位。', 'route': HOME_ROUTE, 'anchor': [10.8, 7.5]},
            {'name': '1 号重型', 'role': '科技与炮火', 'task': '取能量单元完成 1-3 级装配，在工作台安装 42mm，之后从装配台附近支援守家。'},
            {'name': '6 号机库', 'role': '空中拆解', 'task': '冲撞敌方前哨装甲；前哨清空且基地可受伤时转向基地装甲。'},
        ],
        'rules': [
            {'when': '哨兵尚未进入敌方基地卡', 'then': '沿南侧公开路点逐段推进，不穿过中央高地。'},
            {'when': '哨兵处于虚弱状态', 'then': '先回己方补给区解除虚弱，再重新出发。'},
            {'when': '哨兵受到伤害或敌方进入 9 米', 'then': '切防御姿态；血量低于 55% 时开启强化防御。'},
            {'when': '哨兵阵亡且金币足够', 'then': '立即复活；复活后仍虚弱时先回补给区。'},
            {'when': '己方中央高地卡被敌方占领', 'then': '守家步兵改站己方前哨卡，保持己方前哨控制点活跃。'},
            {'when': '重型完成 3 级装配', 'then': '到工作台安装 42mm，优先射击敌方重型与哨兵。'},
        ],
        'priorities': ['敌方基地控制点（+3/秒）', '己方前哨控制点不被夺取', '哨兵存活与卡位', '科技装配与 42mm', '可命中的敌人'],
        'strengths': ['基地控制度是前哨控制的三倍', '一张卡即可维持一个控制点', '基地车体遮挡敌方中央火力线',
                      '阵亡后可回补给区解除虚弱再返场', '守家双卡让对手难以拿到前哨控制度'],
        'weaknesses': ['哨兵孤军深入，被针对时需要复活与返场', '重型科技节奏比正面打法慢', '未实现能量机关激活',
                       '若哨兵被推出卡外超过 5 秒，基地控制会中断', '对同时压制基地卡与己方前哨的对手需要临场换位'],
    },
    'pair': {
        'name': 'dsv41_1017_pair',
        'card': 'pair',
        'title': 'DeepSeek · 双锚断粮 2027',
        'tagline': '哨兵加轮足步兵双锚占敌基地卡，一机被击倒另一机仍在卡上，控制度 +3/秒。',
        'summary': '同一套基地控制思路，但把 3 号登阶轮足步兵也派去敌方基地卡：哨兵先到，步兵随后，两台机器人轮流占卡。'
                   '只要任意一台留在卡上，敌方基地控制点就保持临时控制；哨兵被击倒时，轮足步兵仍能维持控制，给哨兵争取复活与返场时间。'
                   '代价是己方只剩 4 号步兵守家，因此 4 号优先站在己方中央高地卡，重型完成科技后用 42mm 支援。'
                   '两台前出机器人都在虚弱时回己方补给区解除虚弱。',
        'style': {'aggression': 70, 'defense': 75, 'economy': 65, 'objective': 100, 'teamwork': 90, 'adaptability': 75},
        'phases': [
            {'from': 0, 'to': 40, 'title': '双机出发', 'goal': '哨兵与 3 号步兵走南线，4 号步兵守己方中央高地卡，重型取件。', 'focus': 'objective'},
            {'from': 40, 'to': 120, 'title': '双锚建立', 'goal': '哨兵先占敌方基地卡，3 号随后到达；两台机器人轮流保持卡上有人。', 'focus': 'objective'},
            {'from': 120, 'to': 330, 'title': '轮换守卡', 'goal': '一台被击倒时另一台继续占卡；阵亡者回补给区解除虚弱后返场。', 'focus': 'defense'},
            {'from': 330, 'to': 420, 'title': '终局守分', 'goal': '至少保留一台机器人在敌方基地卡上，直到时间结束。', 'focus': 'defense'},
        ],
        'units': [
            {'name': '7 号哨兵', 'role': '基地卡主锚', 'task': '先到敌方基地卡背面，停车保持控制；受击时切防御姿态并开启强化防御。', 'route': BASE_ROUTE, 'anchor': [27.1, 7.5]},
            {'name': '3 号步兵', 'role': '基地卡副锚', 'task': '与哨兵同路，稍后到达；哨兵被击倒时接替占卡，虚弱时回补给区再返场。', 'route': BASE_ROUTE, 'anchor': [26.4, 7.0]},
            {'name': '4 号步兵', 'role': '守家单卡', 'task': '站在己方中央高地卡，阻止对手夺取己方前哨控制点；敌方接近时优先自保并保持卡位。', 'route': HOME_ROUTE, 'anchor': [10.8, 7.5]},
            {'name': '1 号重型', 'role': '科技与炮火', 'task': '完成 1-3 级装配并安装 42mm，之后支援守家与基地卡方向。'},
            {'name': '6 号机库', 'role': '空中拆解', 'task': '冲撞敌方前哨装甲，前哨清空后处理可受伤的基地。'},
        ],
        'rules': [
            {'when': '主锚尚未进入敌方基地卡', 'then': '沿南侧公开路点推进，副锚保持 2-4 米跟随。'},
            {'when': '主锚阵亡或虚弱', 'then': '副锚留在卡上，主锚回补给区解除虚弱后返场。'},
            {'when': '副锚先到达基地卡', 'then': '副锚直接占卡，不必等待主锚。'},
            {'when': '己方中央高地卡被敌方占领', 'then': '4 号步兵改站己方前哨卡，保持己方前哨控制点活跃。'},
            {'when': '敌方重型或哨兵接近基地卡', 'then': '两台前出机器人优先集火，不离开卡片。'},
        ],
        'priorities': ['敌方基地控制点（+3/秒）', '至少一台机器人留在基地卡', '己方前哨控制点不被夺取', '科技装配与 42mm', '可命中的敌人'],
        'strengths': ['两台机器人轮换占卡，单点被击倒不会立刻丢控制', '基地控制度是前哨控制的三倍', '基地车体遮挡中央火力线',
                      '副锚可以接替主锚的卡位', '守家步兵与重型仍能维持基本防守'],
        'weaknesses': ['己方只有一台步兵守家，面对双步兵压制时吃紧', '两台机器人同时深入，被集火时损失更大', '未实现能量机关激活',
                       '副锚的轮足底盘在复杂地形上更慢', '若两台同时阵亡，基地控制会中断'],
    },
    'heavy': {
        'name': 'dsv41_1017_heavy',
        'card': 'heavy',
        'title': 'DeepSeek · 重装断粮 2027',
        'tagline': '重型机器人放弃科技直取敌方基地卡，哨兵守家；用最厚车体换 +3/秒。',
        'summary': '把基地卡突袭交给 1 号重型机器人：它不开科技、不装 42mm，沿南侧公开路点直接开到敌方基地卡背面并停车。'
                   '重型开局有 50% 防御、600 血阶段和最大的车体，比哨兵更难被单台机器人清掉；7 号哨兵留在己方中央高地卡，'
                   '3、4 号步兵守家，形成最稳的主场防守。代价是整局没有 42mm 与科技收入，若基地卡被清掉，翻盘手段较少。'
                   '重型阵亡后先回己方补给区解除虚弱，再重新前往敌方基地卡。',
        'style': {'aggression': 45, 'defense': 95, 'economy': 25, 'objective': 100, 'teamwork': 75, 'adaptability': 60},
        'phases': [
            {'from': 0, 'to': 50, 'title': '重装出发', 'goal': '重型走南线，哨兵上己方中央高地卡，双步兵守卡，机库拆前哨。', 'focus': 'objective'},
            {'from': 50, 'to': 120, 'title': '基地卡建立', 'goal': '重型到达敌方基地卡背面并停车，控制度开始每秒 +3。', 'focus': 'objective'},
            {'from': 120, 'to': 330, 'title': '主场防守', 'goal': '哨兵与双步兵守住己方中央高地卡与前哨卡，重型不离开基地卡。', 'focus': 'defense'},
            {'from': 330, 'to': 420, 'title': '终局守分', 'goal': '重型保持卡位；阵亡则回补给区解除虚弱后尽快返场。', 'focus': 'defense'},
        ],
        'units': [
            {'name': '1 号重型', 'role': '基地卡主锚', 'task': '沿南侧公开路点绕到敌方基地卡背面，停车保持控制；放弃科技与 42mm。', 'route': BASE_ROUTE, 'anchor': [27.1, 7.5]},
            {'name': '7 号哨兵', 'role': '守家主锚', 'task': '守己方中央高地卡，按威胁切换进攻/防御姿态；低血量时开强化防御。', 'route': HOME_ROUTE, 'anchor': [10.8, 7.5]},
            {'name': '3/4 号步兵', 'role': '守家双卡', 'task': '分别站在己方中央高地卡与前哨卡，阻止对手夺取己方前哨控制点。', 'route': HOME_ROUTE, 'anchor': [10.8, 7.5]},
            {'name': '6 号机库', 'role': '空中拆解', 'task': '冲撞敌方前哨装甲；前哨清空且基地可受伤时转向基地装甲。'},
        ],
        'rules': [
            {'when': '重型尚未进入敌方基地卡', 'then': '沿南侧公开路点推进；不使用装配区，不领取能量单元。'},
            {'when': '重型处于虚弱状态', 'then': '先回己方补给区解除虚弱，再重新出发。'},
            {'when': '重型阵亡且金币足够', 'then': '立即复活；复活后仍虚弱时先回补给区。'},
            {'when': '己方中央高地卡被敌方占领', 'then': '哨兵改站己方前哨卡，双步兵继续守另一张卡。'},
            {'when': '敌方重型或步兵进入己方前哨区域', 'then': '哨兵与步兵优先集火，保持己方前哨控制点活跃。'},
        ],
        'priorities': ['敌方基地控制点（+3/秒）', '己方前哨控制点不被夺取', '重型存活与卡位', '己方基地无敌', '可命中的敌人'],
        'strengths': ['重型车体最厚，基地卡上最难被单机清掉', '哨兵与双步兵形成最稳的主场防守', '基地控制度是前哨控制的三倍',
                      '基地车体遮挡中央火力线', '阵亡后可回补给区解除虚弱再返场'],
        'weaknesses': ['整局没有科技收入与 42mm', '重型到达基地卡比哨兵慢', '未实现能量机关激活',
                       '若重型被集火清掉，翻盘手段较少', '对同时压制基地卡与己方前哨的对手需要临场换位'],
    },
}


# Three transferred lineups. The tactic is unchanged; only the hardware changes, so each
# card is generated from its base entry and keeps the same route, rules and role split.
LINEUP_SPECS = (
    ('sentry_dual_arm', 'sentry', '双臂重装',
     {'1': 2712, '3': 304, '4': 302, '6': 2763, '7': 2772},
     ['assembly', 'aerial'],
     '双臂重装 2712/304/302/2763/2772；7 号哨兵独走敌基地卡，控制度每秒 +3。'),
    ('pair_omni', 'pair', '全向机动',
     {'1': 2713, '3': 303, '4': 301, '6': 2762, '7': 2771},
     ['mobility', 'aerial'],
     '全向机动 2713/303/301/2762/2771；哨兵与 303 双锚占敌基地卡，控制度 +3/秒。'),
    ('pair_s2772', 'pair', '自复位哨兵',
     {'1': 2711, '3': 2731, '4': 2732, '6': 2761, '7': 2772},
     ['aerial'],
     '自复位哨兵 2711/2731/2732/2761/2772；双锚占敌基地卡，控制度 +3/秒。'),
)


def _fit(text, extra, limit):
    if len(text) + len(extra) <= limit:
        return text + extra
    return text[:max(0, limit - len(extra) - 1)] + '…' + extra


for _key, _base, _label, _lineup, _extra_tags, _tagline in LINEUP_SPECS:
    _entry = dict(ENTRIES[_base])
    _text = ' / '.join(str(model) for _, model in sorted(_lineup.items()))
    _entry.update({
        'name': f'dsv41_1017_{_key}',
        'card': _base,
        'lineup': _lineup,
        'label': _label,
        'extra_tags': _extra_tags,
        'title': ENTRIES[_base]['title'].replace(' 2027', f'·{_label} 2027'),
        'tagline': _tagline,
        'summary': _fit(ENTRIES[_base]['summary'], f' 本版阵容为 {_text}。', 600),
        'units': list(ENTRIES[_base]['units']) + [
            {'name': '出战阵容', 'role': _label, 'task': f'{_label}：{_text}'}],
        'strengths': (ENTRIES[_base]['strengths'][:4] + [f'{_label}阵容验证了同一套基地卡路线']),
        'weaknesses': (ENTRIES[_base]['weaknesses'][:4] + [f'{_label}的越障与转向手感不同，路线需保持一致']),
    })
    ENTRIES[_key] = _entry


def sidecars(key):
    entry = ENTRIES[key]
    card = entry['card']
    showcase = validate_showcase({
        'format': 'rmuc-showcase-v1',
        'title': entry['title'],
        'tagline': entry['tagline'],
        'summary': entry['summary'],
        'generated_by': AGENT,
        'style': entry['style'],
        'phases': entry['phases'],
        'units': entry['units'],
        'rules': entry['rules'],
        'priorities': entry['priorities'],
        'strengths': entry['strengths'],
        'weaknesses': entry['weaknesses'],
    })
    profile = validate_profile({
        'agent': AGENT,
        'author': 'deepseek-v4.1-flash-1017-max',
        'tactic': 'siege',
        'tags': (['base_rush', 'focus_fire', 'mobility'] if card == 'pair' else
                 ['base_rush', 'focus_fire', 'aerial'] if card == 'sentry' else ['base_rush', 'focus_fire'])
                + entry.get('extra_tags', []),
        'display_name': entry['title'],
        'description': entry['tagline'],
    })
    return showcase, profile


def outputs():
    policy = (ROOT / 'scripts/dsv41_1017_policy_2027.py').read_text()
    with tempfile.TemporaryDirectory(prefix='dsv41-1017-submissions-') as temporary:
        folder = Path(temporary)
        for key, entry in ENTRIES.items():
            source = folder / (entry['name'] + '.py')
            source.write_text(policy.replace('STYLE = "sentry"', f'STYLE = "{entry["card"]}"'))
            showcase, profile = sidecars(key)
            output = folder / entry['name']
            save_submission(output, 'team', {'team': source},
                            team_lineup=entry.get('lineup') or seasons.default_lineup('2027'),
                            showcase=showcase, profile=profile, season='2027')
            yield entry['name'], {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}


def smoke(entries):
    """Run the compiled controller against one real opening observation per entry."""
    from rmuc_arena.engine import Match
    sys.path.insert(0, str(ROOT / 'rmuc_arena'))
    lineup = seasons.default_lineup('2027')
    teams = {side: [{'slot': int(slot), 'model': int(model)} for slot, model in lineup.items()]
             for side in ('red', 'blue')}
    match = Match(seed=7, duration=5, map_name='rmuc2027', lineups=teams)
    try:
        observation = match.observation('red', None)
        observation['message_inboxes'] = {slot: [] for slot in observation['controlled_ids']}
        observation['messages'] = []
        for name, source in entries.items():
            module = {'__name__': f'dsv41_1017_smoke_{name}'}
            exec(compile(source, f'{name}/strategy.py', 'exec'), module)
            commands, state = module['act'](json.loads(json.dumps(observation)), {})
            if not commands:
                raise SystemExit(f'{name}: the controller returned no commands on the opening tick')
            for slot, fields in commands.items():
                for field, value in fields.items():
                    if isinstance(value, float) and value != value:
                        raise SystemExit(f'{name}: slot {slot} produced NaN in {field}')
    finally:
        match.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=authoring_examples())
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--no-smoke', action='store_true')
    args = parser.parse_args()
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
        raise SystemExit('Stale DeepSeek 1017 strategies: ' + ', '.join(changed))
    print(f'{count} DeepSeek V4.1 Flash 1017 Max submissions validated'
          + ('' if args.no_smoke else ' and smoke-tested')
          + f'; {len(changed)} files ' + ('need updating.' if args.check else 'updated.'))


if __name__ == '__main__':
    main()
