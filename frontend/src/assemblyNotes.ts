// Why the rulebook ended an assembly attempt, in the pilot's own words. Both seasons report the
// reason on the `assembly_failed` event and keep it on the team's core state until the next order,
// so the HUD, the assembly panel and the event feed all read the same table.
export const ASSEMBLY_FAIL_TEXT:Record<string,string>={
  left_assembly_area:'重装机器人连续 15 秒不在装配区交互模块卡上',
  heavy_destroyed:'重装机器人在装配中被击毁',
  unit_extracted:'能量单元被取出',
  pair_window:'双核配对步骤超出同步窗口',
  timeout:'装配限时用尽',
  secondary_window:'第二枚核心超出插入窗口',
  core_window:'第二枚核心超出插入窗口',
};

export const assemblyFailText=(reason?:string|null)=>reason?(ASSEMBLY_FAIL_TEXT[reason]??reason):'装配未完成';

// Why the engine declined a level order. The cockpit repeats an order until it is answered, so a
// refusal is the only thing that stops the retry: it has to say what to fix, or the panel looks dead.
export const ASSEMBLY_REFUSED_TEXT:Record<string,string>={
  outside_zone:'重装机器人不在己方兑矿台的交互模块卡上（开到卡片上再下达）',
  destroyed:'重装机器人已被击毁',
  penalised:'重装机器人处于罚下状态',
  busy:'已有一次装配正在进行，等它完成或失败后再下达',
  core_loaded:'科技核心内已有能量单元：装配难度暂时锁定',
  locked:'该等级尚未解锁（每分钟解锁一级）',
  previous_level:'需要先完成上一级装配',
  once:'四级装配本场只能完成一次',
  no_unit:'携带的能量单元不足（一级 1 个，四级 2 个）',
  priority:'对方正在做四级装配，本轮装配被让行',
};

export const assemblyRefusedText=(reason?:string|null)=>reason?(ASSEMBLY_REFUSED_TEXT[reason]??reason):'引擎拒绝了这条装配指令';
