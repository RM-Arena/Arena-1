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
    base = '\n\n'.join((ROOT / 'scripts' / name).read_text(encoding='utf-8') for name in
        ('gpt61_policy_2027.py', 'gpt61_trident_2027.py', 'gpt61_max_2027.py',
         'sol_max_navigation_2027.py', 'sol_max_cover_2027.py', 'sol_max_formation_2027.py',
         'sol_max_support_2027.py', 'sol_max_fire_control_2027.py', 'sol_max_sentry_2027.py', 'sol_max_turning_2027.py', 'sol_max_vision_2027.py'))
    return base + (ROOT / 'scripts/sol_max_coordination_2027.py').read_text(encoding='utf-8')


def metadata():
    showcase, profile = base_metadata()
    description = '2712 / 305 / 305 / 2763 / 2772。串联腿分道越障，重型优先守基地。保留前沿火力，基地告警只分配一台援军；双路突入优先由守点步兵拦截，单哨兵绕后由哨兵选择射界接防，锚点稳定后归队。补给落点分散，再出场排队起跳；补给区与基地采用不同集结路径，失败通道限时停用。近场交火按地面接触与姿态预算先防护，再强化输出；开火按完整决策周期预留两弹热量。云台错相搜索，按加速与转向预测弹着点，过滤友军与遮挡。治疗、补弹和复活共享预算，优先使用完全受控前哨的免费治疗。'
    showcase.update(title=TITLE, generated_by=AGENT, summary=description,
        tagline='守住基地，读阵争点，串联腿跨越高地。',
        style={'aggression': 80, 'defense': 90, 'economy': 45, 'objective': 98, 'teamwork': 95, 'adaptability': 90})
    showcase['phases'] = [
        {'from': 0, 'to': 25, 'title': '越障与后方锚定', 'goal': '重型沿基地外缘直接就位；步兵分道收腿起跳，哨兵延后跟进并在越障时保持移动姿态，落地近战再选择防护与输出。机库攻击敌方前哨。', 'focus': 'objective'},
        {'from': 25, 'to': 180, 'title': '分工拦截与争分', 'goal': '保持前沿独立任务，前沿已获控制而己方前哨丢失时由机动步兵回补。对进入后场的突入者只分配一台援军，双路突入优先用守点步兵，单哨兵绕后由哨兵选择射界应对；锚点稳定后解除接防。', 'focus': 'objective'},
        {'from': 180, 'to': 330, 'title': '恢复与再次出场', 'goal': '优先就近使用完全受控前哨治疗，补给区按槽位分散停靠。再次出场按实际位置选择集结路径，依次使用起跳通道；从基地归队时先绕开堡垒。恢复达标后继续任务，哨兵有接防时领取免费配给。', 'focus': 'defense'},
        {'from': 330, 'to': 420, 'title': '保持有效占用', 'goal': '继续守住己方基地与前哨，保留已取得的控制点存在；按剩余弹药配额补弹，发射权解锁后重型就地提供42mm火力。', 'focus': 'objective'}]
    showcase['units'] = [
        {'name': '1号2712重型', 'role': '基地锚点', 'task': '开局直接守基地；仅在补给区有实际接防时限时尝试装模块；真正受压后沿基地边缘转移，治疗优先；独立舵轮保持机身朝向穿过狭窄位置。'},
        {'name': '3号305串联腿', 'role': '协攻与补位', 'task': '协攻前沿；前沿已获控制时回补丢失的己方前哨，敌方基地空缺时沿侧路绕后。'},
        {'name': '4号305串联腿', 'role': '守点与接防', 'task': '沿己方高地卡运动，优先拦截双路基地突入；锚点稳定后归队，重新建立越障路线。'},
        {'name': '7号2772串联腿', 'role': '前沿火力与反绕后', 'task': '保持前沿火力，必要时对单哨兵绕后选择基地射界接防；确认安全后归队。近场按有限预算使用强化防御与强化攻击。'},
        {'name': '6号2763机库', 'role': '空中拆解', 'task': '三架无人机分别预测旋转装甲，优先攻击敌方前哨，再攻击具备伤害条件的基地。'}]
    showcase['rules'] = [
        {'when': '串联腿准备跨越己方高地', 'then': '先收腿到0.12m，在第一道立面之前起跳，保持朝向；起跳受地面接触和冷却约束，限时失败后重新导航。'},
        {'when': '敌方基地卡仍被敌人激活', 'then': '机动步兵优先协攻敌方高地；基地卡空缺后再转为绕后。'},
        {'when': '己方基地守卫血量不足', 'then': '步兵先接防，守卫确认基地卡已有队友有效占用后才离开。'},
        {'when': '己方前哨丢失且前沿已获控制', 'then': '机动步兵回补，保留哨兵的独立前沿任务；基地拦截只分配一台援军。'},
        {'when': '虚弱、血量低于24%，或哨兵缺弹且有健康队友接防', 'then': '进入持续恢复流程；优先就近到完全受控前哨治疗，需要配给的哨兵回补给区，恢复到85%后再进场。'},
        {'when': '射线被地形、建筑或队友阻挡', 'then': '停止开火，保留弹药；仅向可达目标求解带阻力和底盘初速的弹道。'},
        {'when': '多台机器人同时申请补给', 'then': '共享当前金币与全队弹药配额，扣除已分配订单，避免重复支出。'}]
    showcase['rules'].append({'when':'已在免费恢复卡上，或治疗后已恢复至85%且虚弱解除','then':'保留金币用于补弹；空弹时允许小批量本地购弹。确认没有未完成跳跃后，就地恢复任务。'})
    showcase['rules'].append({'when':'补给后或基地接防后再次出场','then':'按起点选择集结路径，排队使用跳跃通道；通道占用限时，基地防守优先于重新越障。'})
    showcase['rules'].append({'when':'准备连续射击或切换哨兵姿态','then':'按整个决策周期预留两弹热量，避免过热停火与视野变暗。'})
    showcase['priorities'] = ['己方基地有效占用', '双前哨控制度', '无人防守的敌方基地', '可靠越障', '补给与接防']
    showcase['strengths'] = ['开局快攻与中后期安全返场分开规划', '根据控制权、基地威胁与有效占用组织接防', '加速转向提前量与分离射界', '关键治疗优先，强化攻击预算按交火使用']
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
