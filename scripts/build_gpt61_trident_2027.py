"""Build the fixed triple serial-leg RMUC 2027 assault submission."""
import argparse
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rmuc_arena.strategy_sources import authoring_examples
sys.path.insert(0, str(ROOT / 'scripts'))
from build_gpt61_strategies_2027 import AGENT, sidecars
from rmuc_arena.showcase import validate_profile, validate_showcase
from rmuc_arena.submissions import save_submission

NAME = 'gpt61_2027_trident'
LINEUP = {'1': 2712, '3': 305, '4': 305, '6': 2763, '7': 2772}
TITLE = 'GPT · 三叉戟突击 2027'


def source():
    return (ROOT / 'scripts/gpt61_policy_2027.py').read_text(encoding='utf-8') + '\n\n' + (ROOT / 'scripts/gpt61_trident_2027.py').read_text(encoding='utf-8')


def metadata():
    showcase, profile = sidecars('pressure', TITLE)
    summary = '305 串联腿步兵×2、2772 串联腿哨兵组成三路突击；健康时持续前压，不因小幅领先收缩。开局分道跨越中路高地，推进中对正台阶起跳。血量低于32%撤回，恢复到80%再进场；重型驻守己方前哨卡，三无人机继续拆前哨。'
    showcase.update(tagline='三台串联腿，跨越高地，健康就前压。', summary=summary,
        style={'aggression':95,'defense':55,'economy':45,'objective':95,'teamwork':90,'adaptability':85})
    showcase['phases'] = [
        {'from':0,'to':25,'title':'三腿越障','goal':'两台步兵错开车道，哨兵延迟跟进；减速对正并收腿起跳，跨过中路两道台阶，失败则限时改道。','focus':'objective'},
        {'from':25,'to':180,'title':'持续前压','goal':'两步兵争夺敌方前哨卡与高地卡，哨兵从另一侧跟进；低血量撤回，健康机器人继续推进。','focus':'objective'},
        {'from':180,'to':330,'title':'前哨转堡垒','goal':'留人控制敌方前哨，另一台步兵进入敌方堡垒；哨兵接防，重型留守己方前哨卡，保护后方控制点。','focus':'objective'},
        {'from':330,'to':420,'title':'终局强攻','goal':'健康时继续前压和争夺控制点；小幅领先不触发全队回撤，失去己方控制点时仅派最近的一台接防。','focus':'objective'}]
    showcase['units'] = [
        {'name':'1号双臂重型','role':'后方锚点','task':'驻守己方前哨卡，为三台串联腿争取进攻空间；发射器按时间解锁且己方控制点稳固时，再安装42mm。'},
        {'name':'3号305串联腿','role':'前哨突击','task':'从低地连续跳上高地，推进敌方前哨卡；低血量恢复后重新加入战线。'},
        {'name':'4号305串联腿','role':'高地与堡垒','task':'错开车道跨越高地，争夺敌方高地卡；有人守点后再深入堡垒。'},
        {'name':'7号2772串联腿','role':'前线火力接替','task':'跟随跳跃上高地，从另一侧前压；按交火、移动与血量切换姿态。'},
        {'name':'6号三无人机库','role':'空中拆解','task':'错开冲撞旋转装甲，优先敌方前哨，再攻击可受伤的基地。'}]
    showcase['rules'] = [
        {'when':'血量健康且仍有进攻目标','then':'继续前压，不因控制度小幅领先回撤。'},
        {'when':'血量低于32%或处于虚弱状态','then':'撤往最近可用恢复点，持续恢复至80%再进场。'},
        {'when':'接近可跨越台阶且血量至少55%','then':'减速对正、收腿并按冷却起跳；开局路线17秒未完成则改道。'},
        {'when':'己方前哨控制点丢失','then':'仅派距离最近的健康地面机器人接防，其余继续施压。'},
        {'when':'机器人翻倒','then':'停止推进和开火，等待串联腿自动复位后继续原路线。'}]
    showcase['priorities'] = ['健康时前压','敌方控制点','地形跨越','后方接防','低血量恢复']
    showcase['strengths'] = ['三台串联腿分道跳跃越障','健康时持续向敌方控制点推进','自动复位后恢复原任务']
    showcase['weaknesses'] = ['激进站位更容易承受集火','尚未实现能量机关激活','越障失败会延误推进，需要改道','重型优先守点，牺牲早期科技经济','后期基地防守与弹药节制仍可改进']
    profile.update(description=summary, tags=['mobility','focus_fire','outpost_rush','aerial'], tactic='assault')
    return validate_showcase(showcase), validate_profile(profile)


def output():
    with tempfile.TemporaryDirectory(prefix='gpt61-trident-') as temporary:
        folder = Path(temporary)
        policy = folder / 'policy.py'
        policy.write_bytes(source().encode('utf-8'))
        showcase, profile = metadata()
        save_submission(folder / NAME, 'team', {'team':policy}, team_lineup=LINEUP,
                        season='2027', showcase=showcase, profile=profile)
        return {p.name:p.read_bytes() for p in (folder / NAME).iterdir() if p.is_file()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=authoring_examples())
    parser.add_argument('--check', action='store_true')
    args=parser.parse_args()
    changed=[]
    for name,data in output().items():
        target=args.output / NAME / name
        if target.is_file() and target.read_bytes()==data:
            continue
        changed.append(str(target))
        if not args.check:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    if args.check and changed:
        raise SystemExit('Stale triple-leg submission: '+', '.join(changed))
    print(f'{NAME}: {len(changed)} files updated; attribution={AGENT["model"]}')

if __name__=='__main__':
    main()
