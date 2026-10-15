---
layout: home
hero:
  name: Arena-1
  text: 看懂机器人对抗，写出你的打法
  tagline: 不认识 RoboMaster 也能开始。从观看第一场比赛，到让 Agent 开发策略；支持 RMUC 2027（默认）与 RMUC 2026。
  image:
    src: /logo.png
    alt: Arena-1 机器人策略竞技场
  actions:
    - theme: brand
      text: 从零认识比赛
      link: /guide/what-is-arena
    - theme: alt
      text: 安装并跑第一局
      link: /guide/getting-started
    - theme: alt
      text: 2027 规则图解
      link: /guide/rules-2027
features:
  - title: 先看懂，再动手
    details: 用实际画面和示意图认识基地、前哨、兵种与资源。第一次体验可以直接使用示例策略，无需编程。
  - title: 两个赛季，两种战术重心
    details: 2027 是重型、步兵、空中机器人系统与哨兵组成的 5v5，强调控制点；2026 保留英雄、工程与三步兵的 6v6。
  - title: 让 Agent 开发策略
    details: 生成含规则、硬件与接口的任务，编写 Python、练习、提交，再用完整对局检验实际行为。
  - title: 在回放里找到原因
    details: 暂停、换镜头、跟随机器人，结合血量、弹药、热量与控制度，理解一次丢点或进攻为何发生。
---

<script setup>
import {withBase} from 'vitepress';
</script>

<section id="wechat-community" class="wechat-community" aria-labelledby="wechat-community-title">
  <div class="wechat-community-copy">
    <h2 id="wechat-community-title">加入 RM-Arena 微信交流群</h2>
    <p>交流机器人策略、RoboMaster 规则和 Arena-1 使用经验，也欢迎分享你的打法与对局。</p>
    <p>使用微信扫一扫，或打开原图保存后在微信中识别二维码。</p>
    <p class="wechat-community-expiry">二维码有效期至 <time datetime="2026-10-22">2026 年 10 月 22 日</time>。</p>
    <a :href="withBase('/media/wechat-group.png')" target="_blank" rel="noreferrer">打开二维码原图 →</a>
  </div>
  <a class="wechat-community-image" :href="withBase('/media/wechat-group.png')" target="_blank" rel="noreferrer" aria-label="查看 RM-Arena 微信交流群二维码原图">
    <img :src="withBase('/media/wechat-group.png')" width="720" height="1094" alt="RM-Arena 微信交流群二维码，有效期至 2026 年 10 月 22 日" />
  </a>
</section>

## 第一次来，先知道这是什么

Arena-1 是一个机器人团队对抗仿真应用。红蓝两队保护自己的基地，争夺场上目标，管理弹药和资源。你可以只当观众，也可以为机器人编写策略；所有上场行动由程序完成，物理与裁判规则由引擎执行。

![RMUC 2027 场地实际全景：两端基地、中央高地、前哨与装配区](/media/rmuc2027-field.jpg)

*2027 是默认赛季。5v5 指五个出战位置，其中一套机库可以带多架空中机器人。*

## 按你现在的目标阅读

| 你想做什么 | 推荐路线 |
| --- | --- |
| 完全不了解 RoboMaster | [认识比赛](/guide/what-is-arena) → [术语速查](/guide/glossary) → [第一场比赛](/guide/getting-started) |
| 已经用过 2026，想了解新内容 | [两季对照](/guide/seasons) → [2027 控制点与兵种](/guide/rules-2027) |
| 想让 Agent 开发打法 | [创建任务与练习提交](/guide/strategies) → [对战与复盘](/guide/features) |
| 想修改仿真或界面 | [从源码运行](/guide/development) → [系统架构](/development/architecture) |

## 2027 为什么要占点？

到时判胜首先比较控制度。保持己方控制、争夺敌方前哨与基地控制点，会影响得分、前哨重建和基地保护；不能只凭伤害数字判断领先。

[![2027 四个控制点的结构和得分条件](/media/control-2027.svg)](/guide/rules-2027)

继续阅读[2027 规则图解](/guide/rules-2027)，或[观看两季实机演示](/demo)。

## 这是怎样的仿真？

桌面应用与浏览器版本使用同一套 3D 界面，Rust 引擎推进物理，Python 程序控制机器人，记录可以导出并回放。项目按固定版本的规则做适配，保留 2026 与 2027 两套场地；未实现飞镖、雷达与电子对抗，2026 的哨兵位置按步兵运行。

这里介绍的是 Arena-1 的行为，不等于真实赛事所有规则或最新修订。规则依据与仿真假设可从[赛季对照](/guide/seasons)进入查阅。源码见 [GitHub 仓库](https://github.com/RM-Arena/Arena-1)。

::: warning 使用许可
本项目公开源码，**禁止商用，仅供非商业学习与教学使用**。请先阅读[许可证与素材说明](/license)。
:::

<style scoped>
.wechat-community { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 40px; align-items: center; margin: 32px 0; padding: 28px; border: 1px solid var(--vp-c-divider); border-radius: 16px; background: var(--vp-c-bg-soft); scroll-margin-top: 88px; }
.wechat-community-copy h2 { margin: 0 0 16px; padding: 0; border: 0; font-size: 25px; line-height: 1.4; }
.wechat-community-copy p { margin: 12px 0; }
.wechat-community-expiry { color: var(--vp-c-text-2); font-size: 14px; }
.wechat-community-image { display: block; width: 100%; max-width: 300px; justify-self: center; }
.wechat-community-image img { display: block; width: 100%; height: auto; border-radius: 12px; }
@media (max-width: 640px) { .wechat-community { grid-template-columns: minmax(0, 1fr); gap: 20px; padding: 20px; } .wechat-community-copy h2 { font-size: 22px; } }
</style>
