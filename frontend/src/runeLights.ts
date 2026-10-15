export interface RuneLightTarget {
  arm:number;
  hit?:boolean;
  lit?:boolean;
  last_hit_at?:number|null;
  last_hit_valid?:boolean;
}
export interface RuneLightState {
  status:string;
  active_until?:number;
  activated_arms?:number[];
  lit?:number[];
  targets?:RuneLightTarget[];
}
export type RuneArmLight='off'|'target'|'hit'|'impact'|'active';
export const RUNE_IMPACT_SECONDS=.35;

export function runeActive(state:RuneLightState,time:number){
  return state.status==='active'&&(state.active_until===undefined||time<state.active_until);
}

// Authoritative match time keeps hit feedback correct during pause, speed changes and seeking.
export function runeArmLight(state:RuneLightState,arm:number,time:number):RuneArmLight {
  if(runeActive(state,time))return 'active';
  const target=state.targets?.find(t=>t.arm===arm);
  const at=target?.last_hit_at;
  if(at!==undefined&&at!==null&&time>=at&&time-at<RUNE_IMPACT_SECONDS)
    return target?.last_hit_valid?'hit':'impact';
  if(state.status!=='activating')return 'off';
  if(target?.lit||state.lit?.includes(arm))return 'target';
  if(target?.hit||state.activated_arms?.includes(arm))return 'hit';
  return 'off';
}
