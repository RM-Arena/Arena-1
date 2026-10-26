import type {Frame,TeamId} from './types';
import {pointInPolygon} from './terrain';
export const FORTRESS_HOLD_SECONDS=20;
// 2027 holds the enemy fortress for 10 s; the count only needs presence on the card once activated.
export const FORTRESS_HOLD_SECONDS_2027=10;
export const FORTRESS_WARNING_SECONDS=6;
export interface FortressAlert {attacker:TeamId;defender:TeamId;robot:string;remaining:number;x:number;y:number;radius:number}
// A running capture, from its first tick: the readout shows `hold / holdSeconds` the whole way, so
// the top-of-screen ring and the world-space plate exist before the last-six-seconds warning.
export interface FortressCapture {attacker:TeamId;defender:TeamId;robot:string;hold:number;holdSeconds:number;remaining:number;progress:number;x:number;y:number;radius:number}

// The season travels on the frame; older replays only carry the arena name.
const season2027=(f:Frame)=>f.season==='2027'||f.arena?.name==='rmuc2027';

// The enemy robot currently standing on `defender`'s fortress card, with its running hold. Only a
// current, valid occupation counts: retained progress on a robot that has left the card (or one that
// is dead, weak or still reads a stale contact) never builds a capture.
export function fortressCapture(frame:Frame,defender:TeamId):FortressCapture|null{
 const base=frame.bases[defender],outpost=frame.outposts?.[defender],zone=frame.arena.zones.find(z=>z.id===`${defender}_fortress`),top=season2027(frame);
 if(frame.status!=='running'||frame.time<180||!zone||!base||base.hp<=0||base.armor_open)return null;
 // 2026 only opens the enemy card while the defender's outpost is down. In 2027 the count is live
 // once it has started (control of the outpost position gates activation, not the countdown), so a
 // rebuilt outpost must not hide a running capture.
 if(!top&&(!outpost||outpost.hp>0||!outpost.ever_destroyed))return null;
 const occupants=frame.zones?.[zone.id]?.occupants||[],attacker:TeamId=defender==='red'?'blue':'red';
 const holdSeconds=top?FORTRESS_HOLD_SECONDS_2027:FORTRESS_HOLD_SECONDS;
 const fresh=Math.max(frame.dt||.05,.001)*2+1e-7;
 let best:FortressCapture|null=null;
 for(const r of frame.robots){
  if(r.team!==attacker||!r.alive||r.weak||r.red_card||!occupants.includes(r.id))continue;
  if(top?r.role==='aerial':r.role!=='infantry')continue;
  const hold=r.fortress_hold,last=r.fortress_last_contact;
  if(hold===undefined||!Number.isFinite(hold)||hold<0||last===undefined||!Number.isFinite(last))continue;
  if(Math.abs(frame.time-last)>fresh)continue;
  const standing=r.last_raw_zones?r.last_raw_zones.includes(zone.id):zone.polygon?pointInPolygon(r.x,r.y,zone.polygon):Math.hypot(r.x-zone.x,r.y-zone.y)<=zone.radius;
  if(!standing)continue;
  const held=Math.min(hold,holdSeconds);
  if(best&&held<=best.hold)continue;
  best={attacker,defender,robot:r.id,hold:held,holdSeconds,remaining:Math.max(0,holdSeconds-held),progress:holdSeconds>0?held/holdSeconds:0,x:zone.x,y:zone.y,radius:zone.radius};
 }
 return best;
}

// The last six seconds, when the broadcast shouts the countdown.
export function fortressAlert(frame:Frame,defender:TeamId):FortressAlert|null{
 const capture=fortressCapture(frame,defender);
 if(!capture||capture.remaining<=1e-8||capture.remaining>FORTRESS_WARNING_SECONDS+1e-7)return null;
 return {attacker:capture.attacker,defender:capture.defender,robot:capture.robot,remaining:Math.min(FORTRESS_WARNING_SECONDS,capture.remaining),x:capture.x,y:capture.y,radius:capture.radius};
}
