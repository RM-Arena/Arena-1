import * as THREE from 'three';
import type {RenderFeed,Robot} from './types';

// The first-person eye sits this many muzzle heights above the barrel line. The lift keeps the
// camera clear of its own barrel while the view stays parallel to it; the 0.85 factor lowers the
// eye 15 % from the previous 1.495 so the cockpit sits closer to the gun it is aiming.
export const FPV_EYE_LIFT=1.27;

// Frame-rate independent easing. A `lerp(target, dt*k)` factor changes its response with the frame
// rate — the same camera is twice as sluggish at 120 Hz as at 60 Hz, and a dropped frame overshoots —
// so every camera follower uses this exponential form instead: the fraction of the gap closed in `dt`
// is the same at any refresh, and the motion stays continuous through a hitch.
export const dampFactor=(rate:number,dt:number)=>1-Math.exp(-Math.max(0,rate)*Math.max(0,dt));

// Common panel rates, slowest first. The frame-time controller snaps its measured refresh to one of
// these — the fastest the measurement is within 8 % of — so a stray fast frame cannot make a 60 Hz
// panel look like an 80 Hz one and shrink the budget the scene aims at. A 120 Hz panel gets 8.3 ms.
export const DISPLAY_RATES=[60,75,90,100,120,144,165,240];
export const displayRate=(hz:number)=>DISPLAY_RATES.reduce((best,rate)=>rate<=Math.max(60,hz)*1.08?rate:best,60);
export const displayBudget=(hz:number)=>1/displayRate(hz);

export const toWorld=(arena:{width:number;height:number},x:number,y:number,z=0,out=new THREE.Vector3())=>out.set(x-arena.width/2,z,y-arena.height/2);

// How long the newest snapshot pair is blended over. The scene blends over the *measured* gap between
// snapshots rather than the engine's nominal step, because a server that publishes at 10 Hz while the
// frame says 20 Hz would otherwise leave every robot frozen for the last part of each cycle. `pace`
// is wall clock, so it already includes the playback speed. The 15 % slack means the blend is still
// running when the next packet lands, so the field never comes to a stop between snapshots.
export function sampleSpan(feed:RenderFeed){
  const f=feed.frame;
  return f&&feed.pace?Math.max(16,feed.pace*1.15):Math.max(16,(f?.dt??.05)*1000/Math.max(.5,feed.speed));
}

// The blend phase for the whole scene. It is allowed to run a little past 1.0 so that a late packet
// leaves the bodies moving instead of parking them on the newest sample — that is the frame
// compensation. It is safe only because `robotWorld` continues along the Hermite curve, which is
// continuous in position *and* velocity; a linear extrapolation would have to guess the rate, and a
// rate change (a pilot starting or stopping a turn) would snap the picture back.
const OVERDUE_MAX=1.18;
export function feedAlpha(feed:RenderFeed){
  const f=feed.frame;if(!f)return 1;
  if(feed.paused)return 1;
  if(feed.replay)return feed.alpha??1;
  return Math.min(OVERDUE_MAX,Math.max(0,(performance.now()-feed.received)/sampleSpan(feed)));
}

// Cubic Hermite through p0 → p1 with the sample velocities as tangents. A straight line between two
// snapshots is continuous in position but not in velocity: the eye changes speed abruptly at every
// packet boundary, which reads as a series of small ticks even at a steady frame rate. The engine
// publishes the velocity of every body, so the curve can start and end with exactly the motion the
// simulation had, the joins disappear, and a phase past 1.0 simply rides on past the last sample
// with the same velocity instead of jumping.
const hermite=(p0:number,p1:number,m0:number,m1:number,t:number)=>{
  const t2=t*t,t3=t2*t;
  return (2*t3-3*t2+1)*p0+(t3-2*t2+t)*m0+(-2*t3+3*t2)*p1+(t3-t2)*m1;
};

export function robotWorld(feed:RenderFeed,r:Robot,alpha:number,out:THREE.Vector3){
  const f=feed.frame!;
  const old=feed.previous?.robots.find(o=>o.id===r.id)||r;
  const ox=old.x-f.arena.width/2,oy=old.z||0,oz=old.y-f.arena.height/2;
  const nx=r.x-f.arena.width/2,ny=r.z||0,nz=r.y-f.arena.height/2;
  if(old===r){return out.set(nx,ny,nz);}
  // A respawn teleports the chassis: two unrelated poses must be joined by a straight line, or the
  // curve would swing out through a metre of empty air on the way. The same goes for a phase that
  // has run away (a stalled tab), which is capped so nothing can drift off the field.
  const gap=Math.hypot(nx-ox,nz-oz);
  const speed=Math.max(Math.hypot(old.vx||0,old.vy||0),Math.hypot(r.vx||0,r.vy||0));
  if(alpha>1.6||gap>2||gap>speed*(sampleSpan(feed)/1000)*4+.25){return out.set(ox+(nx-ox)*alpha,oy+(ny-oy)*alpha,oz+(nz-oz)*alpha);}
  const dt=sampleSpan(feed)/1000;
  return out.set(
    hermite(ox,nx,(old.vx||0)*dt,(r.vx||0)*dt,alpha),
    hermite(oy,ny,(old.vz||0)*dt,(r.vz||0)*dt,alpha),
    hermite(oz,nz,(old.vy||0)*dt,(r.vy||0)*dt,alpha));
}


const eye=new THREE.Vector3();
// Scale for a camera-facing overlay so `unit` world metres track perspective, softly floored and capped as a share of the viewport's shorter side.
export function screenFit(position:THREE.Vector3,camera:THREE.Camera,viewport:{width:number;height:number},unit:number,min:number,max:number){
  const fov=(camera as THREE.PerspectiveCamera).fov||42,distance=Math.max(.5,camera.getWorldPosition(eye).distanceTo(position));
  const raw=unit*viewport.height/(2*Math.tan(fov*Math.PI/360)*distance),side=Math.min(viewport.width,viewport.height);
  return Math.min(max*side,Math.hypot(min*side,raw))/raw;
}
