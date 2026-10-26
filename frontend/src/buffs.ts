import {frameSeason,type Frame,type Robot} from './types';

// One buff/debuff as the broadcast and the cockpit draw it. The value is always the *final* number
// the engine is using this tick: same-kind gains have already taken their maximum there, so nothing
// here re-applies a rule.
export type BuffKind='attack'|'defense'|'vulnerability'|'cooling'|'power'|'invulnerable'|'weak'|'heat'|'lock';
export interface BuffChip {kind:BuffKind;label:string;value:number;text:string;title:string}

const percent=(v:number)=>`${Math.round(v*100)}%`;
const one=(v:number)=>Math.round(v*10)/10;
// Multipliers keep two decimals so a 15 % vulnerability reads ×1.15 instead of a rounded ×1.2.
const mult=(v:number)=>`${Math.round(v*100)/100}`;

// The chassis power limit the design was built with, which is what a power buff is measured against.
function designPower(frame:Frame,r:Robot){
  const model=frame.robot_models?.[String(r.model_slot??r.slot)];
  if(!model)return 0;
  const season=frameSeason(frame);
  const stats=model.initial_stats_by_season?.[season]??model.initial_stats;
  return stats?.power_w??0;
}

/**
 * Active buffs and debuffs for one robot, ordered by how much they change the fight.
 * Percentages are computed, not copied: cooling is the effective rate over the design rate
 * (`max(rate × multiplier, rate + flat)`, exactly the engine's formula), power is the current
 * limit over the design limit, and defence/vulnerability are shown separately because the damage
 * formula is `1 - defence + vulnerability`.
 */
export function robotBuffs(r:Robot,frame:Frame):BuffChip[]{
  const chips:BuffChip[]=[];
  const attack=r.attack_multiplier??1;
  if(attack>1.0001)chips.push({kind:'attack',label:'攻击增益',value:attack,text:percent(attack),title:`攻击增益：弹丸伤害 ×${mult(attack)}`});
  const defense=r.defense_buff??0;
  if(defense>1e-6)chips.push({kind:'defense',label:'防御增益',value:defense,text:percent(defense),title:`防御增益：受到伤害 ×${mult(1-defense)}`});
  const vulnerability=r.vulnerability??0;
  if(vulnerability>1e-6)chips.push({kind:'vulnerability',label:'易伤',value:vulnerability,text:percent(vulnerability),title:`易伤：受到伤害 ×${mult(1+vulnerability)}`});
  const rate=r.cooling_rate||0,effective=Math.max(rate*(r.cooling_multiplier??1),rate+(r.cooling_bonus??0));
  if(rate>0&&Math.abs(effective-rate)>1e-6)chips.push({kind:'cooling',label:'热量冷却增益',value:effective/rate,text:percent(effective/rate),
    title:`热量冷却增益：${one(rate)} → ${one(effective)} /秒`});
  const power=designPower(frame,r);
  if(power>0&&r.power_limit>0&&Math.abs(r.power_limit/power-1)>1e-6)chips.push({kind:'power',label:'底盘功率增益',value:r.power_limit/power,text:percent(r.power_limit/power),
    title:`底盘功率：${Math.round(power)} → ${Math.round(r.power_limit)} W`});
  if(r.invulnerable)chips.push({kind:'invulnerable',label:'无敌',value:r.shield??0,text:r.shield>0.05?`${Math.ceil(r.shield)}s`:'无敌',title:`无敌：剩余 ${one(r.shield??0)} 秒`});
  if(r.weak)chips.push({kind:'weak',label:'虚弱',value:0,text:'虚弱',title:'虚弱：发射机构锁定、增益点无效，回到补给区 / 基地 / 完全控制的前哨站增益卡解除'});
  if(r.overheated&&!r.heat_permanent_lock)chips.push({kind:'heat',label:'过热',value:0,text:'过热',title:'枪管过热：冷却到 0 之前不能射击'});
  if(r.heat_permanent_lock)chips.push({kind:'lock',label:'永久禁发',value:0,text:'禁发',title:'热量越限达到永久阈值：本局不能再次射击'});
  else if(r.overspeed_permanent_lock||r.overspeed_locked)chips.push({kind:'lock',label:'超弹速锁定',value:0,text:'超速',title:'弹丸初速超限：锁定期内禁止发射'});
  return chips;
}
