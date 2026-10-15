import type {Frame,TeamId} from './types';
import {pointInPolygon} from './terrain';
export const FORTRESS_HOLD_SECONDS=20;
export const FORTRESS_WARNING_SECONDS=6;
export interface FortressAlert {attacker:TeamId;defender:TeamId;robot:string;remaining:number;x:number;y:number;radius:number}

// Only the current, valid occupation counts. Retained progress alone must not keep a warning alive.
export function fortressAlert(frame:Frame,defender:TeamId):FortressAlert|null{
 const base=frame.bases[defender],outpost=frame.outposts?.[defender],zone=frame.arena.zones.find(z=>z.id===`${defender}_fortress`);
 if(frame.status!=='running'||frame.time<180||!zone||base.hp<=0||base.armor_open||!outpost||outpost.hp>0||!outpost.ever_destroyed)return null;
 const occupants=frame.zones[zone.id]?.occupants||[],attacker=defender==='red'?'blue':'red';
 const candidates=frame.robots.filter(r=>{
  const hold=r.fortress_hold,last=r.fortress_last_contact;
  const standing=r.last_raw_zones?r.last_raw_zones.includes(zone.id):zone.polygon?pointInPolygon(r.x,r.y,zone.polygon):Math.hypot(r.x-zone.x,r.y-zone.y)<=zone.radius;
  return r.team===attacker&&r.role==='infantry'&&r.alive&&!r.weak&&!r.red_card&&standing&&occupants.includes(r.id)
   &&hold!==undefined&&Number.isFinite(hold)&&hold>0&&last!==undefined&&Number.isFinite(last)
   &&Math.abs(frame.time-last)<=Math.max(frame.dt||.05,.001)*2+1e-7;
 });
 if(!candidates.length)return null;
 const leader=candidates.reduce((best,r)=>(r.fortress_hold||0)>(best.fortress_hold||0)?r:best);
 const remaining=FORTRESS_HOLD_SECONDS-(leader.fortress_hold||0);
 if(remaining<=1e-8||remaining>FORTRESS_WARNING_SECONDS+1e-7)return null;
 return {attacker,defender,robot:leader.id,remaining:Math.min(FORTRESS_WARNING_SECONDS,remaining),x:zone.x,y:zone.y,radius:zone.radius};
}
