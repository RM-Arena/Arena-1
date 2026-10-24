import * as THREE from 'three';
import type {RenderFeed,Robot} from './types';

// The first-person eye sits this many muzzle heights above the barrel line. The lift keeps the
// camera clear of its own barrel while the view stays parallel to it; the 0.85 factor lowers the
// eye 15 % from the previous 1.495 so the cockpit sits closer to the gun it is aiming.
export const FPV_EYE_LIFT=1.27;

export const toWorld=(arena:{width:number;height:number},x:number,y:number,z=0,out=new THREE.Vector3())=>out.set(x-arena.width/2,z,y-arena.height/2);

export function feedAlpha(feed:RenderFeed){
  const f=feed.frame;if(!f)return 1;
  if(feed.paused)return 1;
  if(feed.replay)return feed.alpha??1;
  // The scene blends the previous snapshot into the newest one over the *measured* gap between
  // snapshots, not over the engine's nominal step: a server that publishes at 11 Hz while the frame
  // says 20 Hz would otherwise leave every robot frozen for the last 40 ms of each cycle, which reads
  // as stutter even at 140 fps. `pace` is wall-clock, so it already includes the playback speed.
  // The small bias means the blend is still running when the next packet lands, never idling.
  const span=feed.pace?Math.max(16,feed.pace*1.04):Math.max(16,f.dt*1000/Math.max(.5,feed.speed));
  const alpha=(performance.now()-feed.received)/span;
  // A late packet — a strategy decision can hold the engine for 200 ms — would otherwise freeze the
  // field until it lands. Carrying the last motion a third of a step further hides that stall; the
  // overshoot on a 50 ms step is centimetres.
  return Math.min(feed.pace?1.3:1,alpha);
}

export function robotWorld(feed:RenderFeed,r:Robot,alpha:number,out:THREE.Vector3){
  const f=feed.frame!,old=feed.previous?.robots.find(o=>o.id===r.id)||r;
  return out.set(old.x+(r.x-old.x)*alpha-f.arena.width/2,old.z+(r.z-old.z)*alpha,old.y+(r.y-old.y)*alpha-f.arena.height/2);
}

const eye=new THREE.Vector3();
// Scale for a camera-facing overlay so `unit` world metres track perspective, softly floored and capped as a share of the viewport's shorter side.
export function screenFit(position:THREE.Vector3,camera:THREE.Camera,viewport:{width:number;height:number},unit:number,min:number,max:number){
  const fov=(camera as THREE.PerspectiveCamera).fov||42,distance=Math.max(.5,camera.getWorldPosition(eye).distanceTo(position));
  const raw=unit*viewport.height/(2*Math.tan(fov*Math.PI/360)*distance),side=Math.min(viewport.width,viewport.height);
  return Math.min(max*side,Math.hypot(min*side,raw))/raw;
}
