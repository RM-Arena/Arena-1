<script setup>
import {withBase} from 'vitepress';
</script>

# 从画面看懂 Arena-1

本页的截图与录像来自应用实际运行。**先看 2027 默认赛季，再按需对照 2026。** 示意图、真实截图与历史截图会分别说明；历史画面中的策略名称和标签可能早于当前界面。

## 2027：先看空中机器人怎样攻击前哨

<video controls playsinline preload="metadata" :src="withBase('/media/rmuc2027-battle.mp4')" :poster="withBase('/media/rmuc2027-battle.jpg')" style="width:100%;border-radius:12px"></video>

*2027 实际录像。可以先找双方前哨站，再看飞行器如何接近旋转的中层装甲；它们以撞击攻击建筑，不是 2026 的空中射击。录像展示一次运行，不是胜率或战术能力保证。*

观察三个问题：空中机器人是不是撞到有效装甲？步兵有没有占到高地卡？重型正在搬运还是已经装上发射机构？对应规则见[2027 图解](/guide/rules-2027)。

## 把全景与地点对应起来

![2027 场地的真实 3D 全景](/media/rmuc2027-field.jpg)

*两端是基地，中间是中央高地、前哨站与装配设施；高低差、障碍和坡道会影响通行与视线。*

[![根据场地配置绘制的 2027 主要地点图](/media/field-2027-guide.svg)](/media/field-2027-guide.svg)

*位置示意省略了部分几何，不是导航路线图。*

## 重型与空中机器人各做什么？

![重型机器人装配科技核心](/media/rmuc2027-heavy.jpg)

*重型用机械臂操作科技核心，为全队争取等级、收入和防御；解锁后还要回工作台装炮。*

![空中机器人接近前哨站](/media/rmuc2027-drones.jpg)

*一套机库带多架飞行器，但在 5v5 阵容中仍只占 6 号一个位置。*

## 从设置阵容到开始对战

![2027 共同阵容与型号检查](/media/rmuc2027-lineup.jpg)

*RM 对战比较同硬件条件下的策略。不是所有旧型号都符合新赛季规范，不可选的会显示原因。*

![2027 自由对战的卡组设置](/media/rmuc2027-free-battle.jpg)

*自由对战可以组合不同数量和重复型号，但仍受赛季合规与一队一套机库的限制。*

![2027 完整比赛界面](/media/rmuc2027-battle.jpg)

*左侧设置与策略，中间是场景、计分板和时间线，右侧是资源与机器人状态。先看控制度，再把变化对应到场上的点。*

## 2026：对照另一套兵种与打法

<video controls playsinline preload="metadata" :src="withBase('/media/battle.mp4')" :poster="withBase('/media/battle.jpg')" style="width:100%;border-radius:12px"></video>

*2026 录像：每方英雄、工程、空中机器人与三台步兵。到时首先比较基地血量，与 2027 的控制度判据不同。*

两个赛季的共同点是移动、射击、资源管理和协作；差异包括阵容、空中攻击、装配执行者、地形与判胜。详见[2027 与 2026 对照](/guide/seasons)。

## 从观众变成策略开发者

![训练页面的任务创建与开发模式](/media/training.jpg)

*这张训练截图来自 2026 的历史界面。当前训练页可选择赛季，“多机协同”在 2027 生成五份机器人策略，在 2026 生成六份。*

[![任务、开发、提交、比赛和复盘的关系](/media/strategy-workflow.svg)](/guide/strategies)

[安装并开始第一场比赛](/guide/getting-started) · [开发你的第一份策略](/guide/strategies) · [术语速查](/guide/glossary)。
