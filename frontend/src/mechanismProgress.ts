import type {Frame,TeamId} from './types';

export type MechanismKind='outpost'|'assembly';
export interface MechanismProgress {label:string;detail:string;progress:number}
const fraction=(value:number)=>Number.isFinite(value)?Math.max(0,Math.min(1,value)):0;
const operations:Record<string,string>={unloading:'取矿',positioning:'核心就位',inserting:'插入',translating:'平移',rotating:'旋转',verifying:'确认',buffered:'缓冲确认'};
const blocked:Record<string,string>={chassis_unstable:'请停稳底盘',arm_out_of_reach:'机械臂未到位',arm_misaligned:'请对准核心姿态',engineer_absent:'工程未到装配区'};

// Live play and replay use the same authoritative progress; no wall-clock timers.
export function mechanismProgress(frame:Frame,team:TeamId,kind:MechanismKind):MechanismProgress|null {
  if(kind==='outpost'){
    const outpost=frame.outposts?.[team],hold=outpost?.rebuild;
    if(!outpost||outpost.hp>0||!hold||hold.required<=0)return null;
    return {label:'前哨站重建',detail:`${hold.robot.split('-')[1]}号 · ${hold.elapsed.toFixed(1)} / ${hold.required.toFixed(1)} s`,progress:fraction(hold.progress)};
  }
  const core=frame.assemblies?.[team];
  if(!core||!['unloading','moving','inserting','buffered'].includes(core.stage))return null;
  const units=core.difficulty===4?2:1,unit=Math.min(units,(core.inserted_units||0)+1);
  return {label:`${core.difficulty}级兑矿 · ${operations[core.operation]||'操作中'}`,
    detail:`第 ${unit}/${units} 单元${core.requirements?` · ${core.requirements.name} / ${(core.requirements.tip_tolerance_m*1000).toFixed(0)} mm / ${core.requirements.tool_tolerance_deg}°`:''} · ${blocked[core.blocked_reason]||`本步 ${Math.round(fraction(core.operation_progress)*100)}%`}${core.stage==='buffered'?` · 缓冲 ${Math.max(0,(core.buffer_until||core.ready_at)-frame.time).toFixed(1)}s`:''}`,
    // The unload pre-stage has no core step to count, so its own bar is the arm taking the ore out.
    progress:fraction(core.stage==='unloading'?(core.operation_progress??0):core.progress)};
}
