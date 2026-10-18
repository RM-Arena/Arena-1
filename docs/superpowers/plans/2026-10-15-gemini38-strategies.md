# Gemini 3.8 Flash RMUC 2027 策略矩阵与对战优化实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以 `gemini-3.8-flash` 身份开发并优化多套 RMUC 2027 竞技策略，分别与 Claude Opus 5.5 和 GPT-6.1 Sol xhigh 的策略进行完整对打评测与迭代优化，最终完成参赛版本构建与发布。

**Architecture:**
构建模块化自包含控制器 `scripts/gemini38_policy_2027.py`，实现极速锁点（`blitz`）、科技重装（`tech_overload`）与游猎突袭（`hunter`）三套战术矩阵。配套自动构建与元数据生成脚本 `scripts/build_gemini38_strategies_2027.py`，支持全队策略与合规型号自由适配策略的构建、战术卡生成、内容寻址哈希校验，并通过标准评测引擎 `scripts/evaluate_2027.py` 实施红蓝换边对照对打，验证胜率、控制度和零策略错误。

**Tech Stack:** Python 3.12+ (标准库 + `rmuc_arena.sdk`), JSON, FastAPI/Rust runner, RMUC 2027 Rules Engine.

**Spec:** [docs/RULES_2027_IMPLEMENTATION.md](file:///Users/sn/draft/RMUC-Arena/docs/RULES_2027_IMPLEMENTATION.md), [docs/STRATEGY_SHOWCASE.md](file:///Users/sn/draft/RMUC-Arena/docs/STRATEGY_SHOWCASE.md), [docs/ROBOT_HARDWARE_DESIGNS.md](file:///Users/sn/draft/RMUC-Arena/docs/ROBOT_HARDWARE_DESIGNS.md)

## Global Constraints

- 运行环境：Python 只能使用标准库与 `sdk.py`，不能依赖外部第三方库。
- 决策延迟：单次决策严格限制在 200 ms 以内（`decision_deadline_s: 0.2`）。
- 内存与状态：`state` 序列化为 JSON 且不超过 256 KiB，`actions` 总大小不超过 16 KiB。
- 参赛身份：所有策略的元数据署名必须为 `agent: {"provider": "google", "model": "gemini-3.8-flash"}`。
- 合规性：遵守 RMUC 2027 出战规范与合规检查，无策略异常（`policy_errors: 0`）。

## Review Focus

1. **出界与多边形卡位（Polygon Inset）**：在占领前哨卡时，目标点必须严格落在卡片内部有效区域，避免踩在边缘或与底座碰撞导致卡滞。
2. **超级电容与功率管理（Supercap Burst）**：超级电容放电加速必须在直道冲刺与关键卡位时触发，避障与爬坡时保留基础功率，不能导致电容耗尽后在减速带上失速。
3. **空中机器人冲撞提前量（Aerial Strike Lead）**：针对旋转装甲板（420s 内转动），必须结合飞行时间、角速度动态计算装甲接触点，避免冲空或撞击保护立柱。
4. **控制度逻辑与优势收缩（Control Degree Dominance）**：2027 赛制到时先比控制度，当确立控制度优势后，必须保证己方控制点关联卡至少有 1 台健康机器人驻守，严禁全员离卡追击导致优势丢失。
5. **异常与容错兜底（Exception Handling）**：在 `act()` 全局捕获所有潜在异常，保证即便出现非预期几何运算失误时，也能返回安全动作和状态，绝不触发停机惩罚。

---

## Task Structure

### Task 1: 策略核心控制器实现 (`scripts/gemini38_policy_2027.py`)

**Files:**
- Create: `scripts/gemini38_policy_2027.py`

- [ ] **Step 1.1**: 实现底层运动学辅助函数（`wrap`, `distance`, `unstick`, `smart_drive`），集成超级电容开局突进与战术加速能力。
- [ ] **Step 1.2**: 实现高精度弹道与提前量解算器（`firing_solution`, `barrel_angles`, `weapon`），支持空气阻力、射击角度两分法搜索与多目标集火优先级排序。
- [ ] **Step 1.3**: 实现空中机器人（机库无人机）自适应旋转拦截与快速俯冲撞击逻辑。
- [ ] **Step 1.4**: 实现重型机器人科技装配流水线（1~3 级快速装配、42mm 工作台安装、高地火力炮位）。
- [ ] **Step 1.5**: 实现步兵（极速占点、双机互锁掩护、脱战补弹与回血）与哨兵（动态姿态切换引擎、卡位防守）。
- [ ] **Step 1.6**: 实现三种核心战术模式分支（`blitz` 极速锁点、`tech_overload` 科技重装、`hunter` 游猎突袭）。
- [ ] **Step 1.7**: 在本地通过单步测试脚本验证 `act(obs, state)` 语法与接口返回值。

### Task 2: 构建脚本与战术卡生成器 (`scripts/build_gemini38_strategies_2027.py`)

**Files:**
- Create: `scripts/build_gemini38_strategies_2027.py`

- [ ] **Step 2.1**: 定义 Gemini 3.8 Flash 的 Agent 元数据（`google / gemini-3.8-flash`）与战术描述体系。
- [ ] **Step 2.2**: 为 `gemini38_2027_blitz`、`gemini38_2027_tech_overload` 和 `gemini38_2027_hunter` 生成符合规范的 `showcase.json`（风格、阶段、战术卡、优劣势）与 `profile.json`。
- [ ] **Step 2.3**: 实现内容寻址与版本生成机制，将策略发布到 `examples/` 和 `submissions/` 目录。
- [ ] **Step 2.4**: 运行构建脚本，验证所有生成的策略通过 `validate_showcase`、`validate_profile` 与 `load_submission` 校验。

### Task 3: 与 Claude Opus 5.5 基线实战对打与调优

**Files:**
- Test Output: `build/eval_vs_claude.json`

- [ ] **Step 3.1**: 使用 `evaluate_2027.py` 运行 Gemini 策略 vs Claude 基线（`claude_opus55_xhigh_2027_team` 和 `claude_opus55_xhigh_2027_hold`），设置红蓝换边（红方 + 蓝方）。
- [ ] **Step 3.2**: 分析对局日志、控制度、胜率、伤害量和决策耗时。
- [ ] **Step 3.3**: 针对暴露的问题（如开局冲点时机、受损撤退阈值、装甲板预判精度）进行代码调优。
- [ ] **Step 3.4**: 验证对打结果达到期望胜率与 0 策略错误。

### Task 4: 与 GPT-6.1 Sol xhigh 前哨锁链/压制策略实战对打与调优

**Files:**
- Test Output: `build/eval_vs_gpt.json`

- [ ] **Step 4.1**: 使用 `evaluate_2027.py` 运行 Gemini 策略 vs GPT 策略（`gpt61_2027_control` 和 `gpt61_2027_pressure`），双边对抗。
- [ ] **Step 4.2**: 针对 GPT 的前哨快速占点与守点轮换机制，检验 Gemini 的超级电容突进、交叉火力压制与哨兵姿态自适应效果。
- [ ] **Step 4.3**: 针对与 GPT 的拉锯对局进一步优化资源兑换率与控制度保分逻辑。
- [ ] **Step 4.4**: 验证在多种子、双边对抗下胜率领先且无超时与异常。

### Task 5: 综合评测报告与全套策略正式提交发布

**Files:**
- Create: `benchmarks/gemini38_2027.json`
- Update: `examples/gemini38_2027_blitz/`
- Update: `examples/gemini38_2027_tech_overload/`
- Update: `examples/gemini38_2027_hunter/`
- Update: `README.md`

- [ ] **Step 5.1**: 运行完整对战基准矩阵，生成正式评测报告 `benchmarks/gemini38_2027.json`。
- [ ] **Step 5.2**: 重新构建并固定最终发布的策略版本哈希与战术卡。
- [ ] **Step 5.3**: 更新 `README.md` 与策略库展示索引，加入 Gemini 3.8 Flash 策略与对打战绩。
- [ ] **Step 5.4**: 进行最终状态校验（`git status`、策略有效性检验）。
