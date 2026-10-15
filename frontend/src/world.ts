import * as THREE from 'three';
import type {RenderFeed,Robot} from './types';

export const toWorld=(arena:{width:number;height:number},x:number,y:number,z=0,out=new THREE.Vector3())=>out.set(x-arena.width/2,z,y-arena.height/2);

export function feedAlpha(feed:RenderFeed){
  const f=feed.frame;if(!f)return 1;
  return feed.paused?1:feed.replay?(feed.alpha??1):Math.min(1,(performance.now()-feed.received)/(f.dt*1000/Math.max(.5,feed.speed)));
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
