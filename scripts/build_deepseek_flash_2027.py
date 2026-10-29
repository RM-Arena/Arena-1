"""Build the DeepSeek Flash RMUC 2027 split-anchor submission.

The controller lives in ``scripts/deepseek_flash_2027.py``.  The submission is
self-contained and content addressed; this script only writes the manifest and
the display sidecars, so the source hash and the profile stay reproducible.
"""
import argparse
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rmuc_arena.strategy_sources import authoring_examples

from rmuc_arena.showcase import validate_profile, validate_showcase
from rmuc_arena.submissions import save_submission

NAME = 'deepseek_flash_2027_anchor'
LINEUP = {'1': 2711, '3': 2731, '4': 2732, '6': 2761, '7': 2771}
TITLE = 'DeepSeek · 守家夺锚 2027'
AGENT = {'provider': 'deepseek', 'model': 'deepseek-v4.1-flash-1017'}


def source():
    return (ROOT / 'scripts/deepseek_flash_2027.py').read_text(encoding='utf-8')


def metadata():
    summary = ('2027 到时先比控制度：同时控制双方基地控制点每秒 +3，而一张基地卡有人就能维持一个基地控制点。'
               '7 号 2771 哨兵与 3 号 2731 步兵沿公开路线双锚进入敌方基地卡背面：哨兵先到并承受集火，'
               '步兵随后接替卡位，任何一台活着就保持 +3。4 号 2732 步兵守己方中央高地卡，'
               '在敌方机器人进入己方基地口袋时回防基地卡；1 号 2711 重型不开科技，直接停在己方基地卡上，'
               '用 50% 基地卡防御和车体挡住突入路线；6 号 2761 机库持续拆敌方前哨，'
               '让对手也拿不到完整的前哨控制点。红蓝两侧采用不同的回防阈值：红色路线更早到达敌方基地，'
               '蓝色路线在己方半场交战更久，因此蓝色 2732 更晚离开中央卡。')
    showcase = validate_showcase({
        'format': 'rmuc-showcase-v1',
        'title': TITLE,
        'tagline': '双锚抢 +3，重装守家，中央卡反制对手的前哨控制度。',
        'summary': summary,
        'generated_by': AGENT,
        'style': {'aggression': 78, 'defense': 92, 'economy': 30,
                  'objective': 100, 'teamwork': 92, 'adaptability': 82},
        'phases': [
            {'from': 0, 'to': 40, 'title': '双锚出发',
             'goal': '2771 与 2731 走公开路线进入敌方基地卡；2732 占己方中央高地卡，2711 直接停己方基地卡，机库拆敌方前哨。',
             'focus': 'objective'},
            {'from': 40, 'to': 120, 'title': '敌基地卡建立',
             'goal': '哨兵先到卡背面，步兵接替；任意一台留在卡上即保持敌方基地控制点，控制度开始每秒 +3。',
             'focus': 'objective'},
            {'from': 120, 'to': 300, 'title': '守家与轮换',
             'goal': '2732 在敌方进入己方基地口袋时回防，2711 用基地卡 50% 防御和车体挡路；3 号在低血量且脱战时远程回血；哨兵用防御姿态和强化防御承伤，阵亡后回补给区解除虚弱再返场。',
             'focus': 'defense'},
            {'from': 300, 'to': 420, 'title': '终局守分',
             'goal': '至少保留一台机器人在敌方基地卡上，同时不让对手拿到己方基地控制点；控制度领先时不追人，只守卡。',
             'focus': 'objective'},
        ],
        'units': [
            {'name': '7 号 2771 哨兵', 'role': '敌基地卡主锚',
             'task': '沿公开路线到达敌方基地卡背面，停车保持临时控制；被集火时切防御姿态，低血量时开启强化防御。',
             'route': [[9.6, 4.7], [8.9, 2.2], [12.9, 3.3], [17.4, 1.1], [19.75, 2.7], [21.0, 2.5],
                       [22.4, 3.0], [22.8, 5.1], [24.1, 4.8], [26.8, 4.4], [27.1, 7.5]]},
            {'name': '3 号 2731 步兵', 'role': '敌基地卡副锚',
             'task': '跟随哨兵，稍后到达；哨兵被击倒时接替卡位，低血量时先在卡上脱战回血，虚弱时回补给区。',
             'route': [[9.6, 4.7], [8.9, 2.2], [12.9, 3.3], [17.4, 1.1], [19.75, 2.7], [21.0, 2.5],
                       [22.4, 3.0], [22.8, 5.1], [24.1, 4.8], [26.8, 4.4], [27.1, 7.5]]},
            {'name': '4 号 2732 步兵', 'role': '中央卡与回防',
             'task': '默认站己方中央高地卡，阻止对手拿到完整前哨控制点；敌方进入己方基地口袋或己方基地控制点丢失时回防基地卡。'},
            {'name': '1 号 2711 重型', 'role': '基地卡车体锚',
             'task': '不开科技、不装 42mm，直接停在己方基地卡上；用 50% 基地卡防御和车体挡住敌方突入路线；除回补给区解除虚弱外不离开基地卡。'},
            {'name': '6 号 2761 机库', 'role': '空中拆解',
             'task': '四架空中机器人持续冲撞敌方前哨；前哨清空且敌方基地可受伤时转向基地装甲。'},
        ],
        'rules': [
            {'when': '敌方机器人进入己方基地口袋，或己方基地控制点丢失', 'then': '4 号 2732 立刻回防基地卡；2711 始终留在基地卡上。'},
            {'when': '己方基地卡安全', 'then': '2732 回到己方中央高地卡，保持己方前哨控制点完整，阻止对手 +1。'},
            {'when': '敌方基地卡无人防守', 'then': '2771 与 2731 直接进卡；任意一台在卡上满 5 秒即建立临时控制，之后不主动离开。'},
            {'when': '敌方基地卡有人防守', 'then': '哨兵先承受伤害，步兵在侧翼输出；血量低于 55% 时先脱战回血，不追出卡外。'},
            {'when': '机器人虚弱', 'then': '回己方补给区解除虚弱后返场；哨兵和重型在金币足够时立即复活，缩短基地卡空窗。'},
            {'when': '敌方前哨仍归对方', 'then': '机库优先冲撞前哨；前哨清除且基地可受伤时才转基地。'},
        ],
        'priorities': ['敌方基地控制点（+3/秒）', '己方基地控制点不被夺取', '己方中央高地卡', '敌方前哨', '可命中的敌人'],
        'strengths': ['双锚接力，单台被击倒不会立刻丢 +3', '2711 基地卡 50% 防御 + 车体挡路，专门反制对手的基地偷取', '2732 中央卡反制对手的前哨 +1', '红蓝两侧分别调回防阈值，补偿两条路线的到达时间差', '机库持续拆前哨，削弱对手的完整前哨控制'],
        'weaknesses': ['重型放弃科技与 42mm，正面火力较低', '双锚路线依赖 2731 的登阶与公共路径，遇到针对性堵截会延迟', '两台锚点同时阵亡时 +3 会中断', '2732 在中央卡与基地卡之间切换，极端情况下可能两头失守', '未实现能量机关激活'],
    })
    profile = validate_profile({
        'agent': AGENT,
        'author': 'deepseek-v4.1-flash-1017',
        'tactic': 'siege',
        'tags': ['base_rush', 'focus_fire', 'aerial', 'mobility'],
        'display_name': TITLE,
        'description': summary,
    })
    return showcase, profile


def output():
    with tempfile.TemporaryDirectory(prefix='deepseek-flash-') as temporary:
        folder = Path(temporary)
        policy = folder / 'strategy.py'
        policy.write_text(source(), encoding='utf-8')
        showcase, profile = metadata()
        save_submission(folder / NAME, 'team', {'team': policy}, team_lineup=LINEUP,
                        season='2027', showcase=showcase, profile=profile)
        return {p.name: p.read_bytes() for p in (folder / NAME).iterdir() if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=authoring_examples())
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    changed = []
    for name, data in output().items():
        target = args.output / NAME / name
        if target.is_file() and target.read_bytes() == data:
            continue
        changed.append(str(target))
        if not args.check:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    if args.check and changed:
        raise SystemExit('Stale deepseek-flash submission: ' + ', '.join(changed))
    print(f'{NAME}: {len(changed)} files updated; attribution={AGENT["model"]}')


if __name__ == '__main__':
    main()
