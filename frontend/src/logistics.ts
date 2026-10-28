import {frameSeason} from './types';
import type {TeamId} from './types';

// 5.6.1 table 5-19: λ = 1 − lost base HP / 20000. The divisor is published in the season's
// `rulebook_rules.logistics`; the fallback only covers an older snapshot without it.
export const LOGISTICS_DIVISOR_HP=20000;

interface LogisticsFrame{season?:string;arena?:{name:string};bases?:Record<string,{hp:number;max_hp:number}>;rulebook_rules?:{logistics?:{base_loss_divisor_hp?:number}}}

/** The team's logistics coefficient λ, or 1 outside 2027 or before the base has any damage. */
export function logisticsOf(frame:LogisticsFrame|null|undefined,team:TeamId){
  if(!frame||frameSeason(frame)!=='2027')return 1;
  const base=frame.bases?.[team];
  if(!base||!(base.max_hp>0)||!Number.isFinite(base.hp))return 1;
  const published=Number(frame.rulebook_rules?.logistics?.base_loss_divisor_hp);
  const divisor=Number.isFinite(published)&&published>0?published:LOGISTICS_DIVISOR_HP;
  return Math.min(1,Math.max(.05,1-Math.max(0,base.max_hp-base.hp)/divisor));
}

/** 5.6.1: the FPV feed carries λ² of its pixels, so each side of the picture scales by λ. */
export const fpvResolutionScale=(frame:LogisticsFrame|null|undefined,team:TeamId)=>logisticsOf(frame,team);
