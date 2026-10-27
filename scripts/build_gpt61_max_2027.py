"""Build the reproducible GPT-6.1-Sol-Max serial-leg submission."""
import argparse
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from build_gpt61_trident_2027 import LINEUP, metadata as base_metadata
from rmuc_arena.showcase import validate_profile, validate_showcase
from rmuc_arena.submissions import save_submission

NAME = 'gpt61_sol_max_2027'
TITLE = 'GPT-6.1-Sol-Max · 三叉戟进化 2027'
AGENT = {'provider': 'openai', 'model': 'GPT-6.1-Sol-Max'}


def source():
    return '\n\n'.join((ROOT / 'scripts' / name).read_text(encoding='utf-8') for name in
        ('gpt61_policy_2027.py', 'gpt61_trident_2027.py', 'gpt61_max_2027.py'))


def metadata():
    showcase, profile = base_metadata()
    description = '2712 / 305 / 305 / 2763 / 2772。重型提前安装发射机构并锚定己方基地；三台串联腿收腿提前起跳，步兵守己方前哨，哨兵争敌方高地，另一台步兵根据控制点占用情况选择接防、协攻或绕后。重型先等接防再撤退，虚弱与低血量机器人转身跳下高地，持续恢复至85%；哨兵有队友守点时回库领取累计免费弹药。共享弹药预算，过滤掩体、地形和队友遮挡的射击。'
    showcase.update(title=TITLE, generated_by=AGENT, summary=description,
        tagline='守住基地，读阵争点，串联腿跨越高地。',
        style={'aggression': 80, 'defense': 90, 'economy': 45, 'objective': 98, 'teamwork': 95, 'adaptability': 90})
    showcase['phases'] = [
        {'from': 0, 'to': 25, 'title': '越障与后方锚定', 'goal': '重型提前装好尚未通电的发射机构再守基地；两台步兵分道收腿起跳，哨兵延后跟进，机库攻击前哨。', 'focus': 'objective'},
        {'from': 25, 'to': 180, 'title': '读阵争分', 'goal': '步兵和哨兵建立双前哨控制；敌方基地有人保持占用时协攻高地，无人防守时步兵走端部坡道、隧道与公路之间的侧路绕后占基地卡。', 'focus': 'objective'},
        {'from': 180, 'to': 330, 'title': '接防与恢复', 'goal': '重型确认队友实际激活基地卡后才撤回；低血量与虚弱机器人先转身助跑跳下高地，回库恢复至85%，哨兵领取累计免费弹药。', 'focus': 'defense'},
        {'from': 330, 'to': 420, 'title': '保持有效占用', 'goal': '继续守住己方基地与前哨，保留已取得的控制点存在；按剩余弹药配额补弹，发射权解锁后重型就地提供42mm火力。', 'focus': 'objective'}]
    showcase['units'] = [
        {'name': '1号2712重型', 'role': '基地锚点', 'task': '提前安装发射机构，持续激活己方基地卡；有实际接防才撤退，发射权解锁后就地射击。'},
        {'name': '3号305串联腿', 'role': '协攻与绕后', 'task': '敌方基地仍有占用者时协助争敌方高地，基地空缺时按北侧路线绕后；死亡后重建路线状态。'},
        {'name': '4号305串联腿', 'role': '前哨与接防', 'task': '驻守己方前哨卡，与高地卡上的来敌拉开距离；基地需要恢复时先接防，交接结束后重新越障回前哨。'},
        {'name': '7号2772串联腿', 'role': '敌方高地锚点', 'task': '延后越障，争夺敌方高地卡；依交火与血量切换姿态，受压时使用强化防御。'},
        {'name': '6号2763机库', 'role': '空中拆解', 'task': '三架无人机分别预测旋转装甲，优先攻击敌方前哨，再攻击具备伤害条件的基地。'}]
    showcase['rules'] = [
        {'when': '串联腿准备跨越己方高地', 'then': '先收腿到0.12m，在第一道立面之前起跳，保持朝向；起跳受地面接触和冷却约束，限时失败后重新导航。'},
        {'when': '敌方基地卡仍被敌人激活', 'then': '机动步兵优先协攻敌方高地；基地卡空缺后再转为绕后。'},
        {'when': '己方基地守卫血量不足', 'then': '步兵先接防，守卫确认基地卡已有队友有效占用后才离开。'},
        {'when': '虚弱、血量低于24%，或哨兵缺弹且有健康队友保持前线占用', 'then': '进入持续恢复流程；转身助跑离开高地，回补给区恢复到85%，哨兵领取配给后再进场。'},
        {'when': '射线被地形、建筑或队友阻挡', 'then': '停止开火，保留弹药；仅向可达目标求解带阻力和底盘初速的弹道。'},
        {'when': '多台机器人同时申请补给', 'then': '共享当前金币与全队弹药配额，扣除已分配订单，避免重复支出。'}]
    showcase['priorities'] = ['己方基地有效占用', '双前哨控制度', '无人防守的敌方基地', '可靠越障', '补给与接防']
    showcase['strengths'] = ['针对串联腿的提前起跳与下高地返回路线', '按公开控制点占用情况分配协攻和绕后', '先接防再撤退，减少基地控制空窗', '掩体与队友射击过滤，共享弹药预算']
    showcase['weaknesses'] = ['尚未实现能量机关激活', '放弃早期装配经济，重型依赖按规则自动获得发射权', '固定地图路线仍可能受拥堵和敌方碰撞影响', '本地开发对手不能代表尚未公开的正式参赛策略']
    profile.update(agent=AGENT, author='GPT-6.1-Sol-Max', display_name=TITLE, description=description,
        tactic='balanced', tags=['mobility', 'focus_fire', 'aerial', 'outpost_rush'])
    return validate_showcase(showcase), validate_profile(profile)


def output():
    with tempfile.TemporaryDirectory(prefix='gpt61-sol-max-') as temporary:
        folder = Path(temporary)
        policy = folder / 'policy.py'
        policy.write_text(source(), encoding='utf-8')
        showcase, profile = metadata()
        target = folder / NAME
        save_submission(target, 'team', {'team': policy}, team_lineup=LINEUP,
            season='2027', showcase=showcase, profile=profile)
        return {p.name: p.read_bytes() for p in target.iterdir() if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'examples')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    changes = []
    for name, data in output().items():
        target = args.output / NAME / name
        if target.is_file() and target.read_bytes() == data:
            continue
        changes.append(str(target))
        if not args.check:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    if args.check and changes:
        raise SystemExit('Stale submission: ' + ', '.join(changes))
    print(f'{NAME}: {len(changes)} files updated; attribution={AGENT["model"]}')


if __name__ == '__main__':
    main()
