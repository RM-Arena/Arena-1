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
// is wall clock, so it already includes the playback speed.
//
// It is clamped around the engine's own step, and that clamp is what keeps a late packet from
// showing up as a stutter: without it a 130 ms gap stretched the *whole field* into slow motion for
// 150 ms and the next packet then restarted the blend from the older sample, which rewind is the
// visible "一卡一卡" in the cockpit. Too long a window is now the extrapolation's job (see
// `OVERDUE_MAX`), and too short a one is only a slight speed-up of a fraction of a step.
export function sampleSpan(feed:RenderFeed){
  const f=feed.frame;
  const nominal=Math.max(16,(f?.dt??.05)*1000/Math.max(.5,feed.speed));
  const pace=f&&feed.pace?feed.pace:nominal;
  return Math.min(nominal*1.6,Math.max(nominal*.85,pace));
}

// The blend phase for the whole scene. It is allowed to run a little past 1.0 so that a late packet
// leaves the bodies moving instead of parking them on the newest sample — that is the frame
// compensation, and it is the only "inserted frame" the transport can honestly provide: the curve
// continues with the velocity the simulation actually had. It is safe only because `robotWorld`
// continues along the Hermite curve, which is continuous in position *and* velocity; a linear
// extrapolation would have to guess the rate, and a rate change (a pilot starting or stopping a turn)
// would snap the picture back.
//
// Because `sampleSpan` is now clamped to the engine's step, this cap is what covers a single missed
// packet (up to about 60 % of a step) with continued motion instead of a pause.
const OVERDUE_MAX=1.6;
export function feedAlpha(feed:RenderFeed){
  const f=feed.frame;if(!f)return 1;
  if(feed.paused)return 1;
  if(feed.replay)return feed.alpha??1;
  return Math.min(OVERDUE_MAX,Math.max(0,(clock()-feed.received)/sampleSpan(feed)));
}

// The phase the scene actually draws with. `feedAlpha` restarts from zero on every packet, and packets
// do not arrive at an even cadence: the socket callback, the JSON parse, the React commit and the
// compositor each add their own delay, so on a 50 ms window a 12 ms wobble is a quarter of a step. The
// field then speeds up, stalls and catches up several times a second ? which is what "????" is, and
// it shows most in the channel with the least visual damping: the eye height.
//
// The playhead is a second clock in *engine* time. It advances with the frame's own elapsed time and is
// only nudged to stay inside a band of one sample behind the newest packet ? not servoed onto the
// arrival phase, because that phase is a sawtooth whose mean error would keep stealing speed. Inside
// the band the speed is exactly 1.0, so the picture moves at a constant rate however the packets fall,
// and a packet that arrives late or early merely moves the playhead within the band. Outside it, a
// ?10 % correction brings it back over a few hundred milliseconds; nothing ever rewinds.
type Playhead={ready:boolean;t:number;generation:unknown;now:number};
const playhead:Playhead={ready:false,t:0,generation:null,now:0};
// Draw this far behind the newest sample, in steps. Three quarters of a step means the drawn phase
// sweeps 0.25 ? 1.25 across each pair: mostly interpolation, at most a quarter step of extrapolation.
export const PLAYHEAD_LAG=.75;
// Correction authority. Inside a quarter of a step the speed is exactly 1.0, which is the whole point:
// a browser's packet jitter is ?8?12 ms on a 50 ms step (0.16?0.24 of a step), so it is absorbed
// without the picture ever changing speed. Outside it, a 6 % trim brings the phase back over ~a second.
export const PLAYHEAD_DEAD=.25,PLAYHEAD_GAIN=1,PLAYHEAD_TRIM=.06;
export function resetPlayhead(){playhead.ready=false;playhead.now=0;}
const clock=()=>typeof performance==='undefined'?Date.now():performance.now();
export function liveAlpha(feed:RenderFeed,now=clock()):number{
  const f=feed.frame;if(!f)return 1;
  if(feed.paused||feed.replay){playhead.ready=false;playhead.now=0;return feedAlpha(feed);}
  const rate=Math.max(.5,feed.speed),step=Math.max(.005,(f.dt??.05)/rate);
  const elapsed=playhead.now?Math.min(.25,Math.max(0,(now-playhead.now)/1000)):0;
  playhead.now=now;
  const alpha=()=>Math.min(OVERDUE_MAX,Math.max(-PHASE_BEHIND,1+(playhead.t-f.time)/step));
  if(!playhead.ready||playhead.generation!==feed.generation){
    playhead.ready=true;playhead.generation=feed.generation;
    playhead.t=f.time-PLAYHEAD_LAG*step;
    return alpha();
  }
  // Where the newest sample says we ought to be drawing. Unlike the arrival phase this reference is
  // *continuous* across a packet: `f.time` jumps by the step the packet advanced and the arrival clock
  // restarts from zero by the same amount, so their sum moves only with wall time.
  const expected=f.time+(now-feed.received)/1000*rate;
  const err=(expected-PLAYHEAD_LAG*step-playhead.t)/step;
  const trim=Math.abs(err)>PLAYHEAD_DEAD?Math.max(-PLAYHEAD_TRIM,Math.min(PLAYHEAD_TRIM,PLAYHEAD_GAIN*err)):0;
  playhead.t+=elapsed*(1+trim)*rate;
  return alpha();
}
// How far the drawn phase may sit before the newest pair (a few milliseconds of the previous step). A
// phase below zero continues the Hermite curve backwards for that sliver instead of skipping it, which
// would be one small hiccup per early packet ? exactly the jitter this exists to remove.
const PHASE_BEHIND=.35;

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
  if(alpha>OVERDUE_MAX+0.4||gap>2||gap>speed*(sampleSpan(feed)/1000)*4+.25){return out.set(ox+(nx-ox)*alpha,oy+(ny-oy)*alpha,oz+(nz-oz)*alpha);}
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
