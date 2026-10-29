// Aiming geometry for the cockpit, kept free of React so it can be tested on its own: what the
// assisted lock should pick, and where a lobbed shell lands when the crosshair *is* the impact point.
// Everything here reads the same referee frame the HUD does — obstacle boxes, terrain, armour plates —
// so the assist and the shot can never disagree with the field that is drawn.
import type {Arena,Frame,Robot,Structure,TeamId} from './types';
import {terrainHeight} from './terrain';

// The first-person lens is 64°, so the assist only considers plates inside it; 12 m is the hard
// ceiling, which is what the rules use for close-quarters assisted fire.
export const LOCK_YAW=.80,LOCK_PITCH=.56,LOCK_RANGE=12;
// A plate must also sit within this true angular distance of the crosshair to take the lock.
export const LOCK_ANGLE=.62;
// Target retention: a lock that is still visible and still close to the reticle is kept until another
// plate is clearly better, so a spinning or partly covered chassis never makes the lock flicker
// between two neighbours. `KEEP_SLACK` is the extra angular room the held plate gets (radians) and
// `KEEP_SWITCH` the fraction the challenger must beat it by.
export const KEEP_SLACK=.07,KEEP_SWITCH=.85;
// Two plates count as "both under the crosshair" when their angular distance from the reticle is
// within this band: inside it the least occluded face wins, outside it the closer one always does.
// About 4°, which is a couple of plate widths at 10 m — exactly the case where a plate is peeking out
// of cover beside a clean one.
export const LOCK_EXPOSURE_BAND=.07;
// Ground combat robots (heavy, the two infantry and the sentry) order plates that sit at the same
// angle from the crosshair, then structures. The crosshair itself always comes first.
export const GROUND_PRIORITY_SLOTS=new Set([1,3,4,7]);

export const shortest=(from:number,to:number)=>{const d=(to-from)%(Math.PI*2);return (d>Math.PI?d-Math.PI*2:d<-Math.PI?d+Math.PI*2:d);};

// Prepared sight geometry for one arena. `sightBlocked` runs thousands of times per assist tick
// (12 plates × 2 eyes × a grid of samples each, and once per 0.1 m of terrain), and it used to take
// the sine and cosine of every barrier's rotation on every one of those calls. The field never
// changes during a match and the frame's static half is a single object, so the box list is built
// once per arena and reused.
interface SightBox {cx:number;cy:number;c:number;s:number;hw:number;hh:number;bottom:number;top:number}
const prepared=new WeakMap<Arena,{boxes:SightBox[]}>();
function sightGeometry(arena:Arena){
  let ready=prepared.get(arena);
  if(!ready){
    const boxes:SightBox[]=(arena.obstacles??[]).map(w=>{
      const a=w.rotation??0;
      return {cx:w.x+w.w/2,cy:w.y+w.h/2,c:Math.cos(a),s:Math.sin(a),
        hw:w.w/2,hh:w.h/2,bottom:w.bottom??0,top:(w.bottom??0)+(w.height??1)};
    });
    ready={boxes};
    prepared.set(arena,ready);
  }
  return ready;
}

// Sight line from the gimbal eye to a point, through the field the pilot sees: the same obstacle
// boxes and terrain the renderer draws, so a plate behind a wall or a deck never locks.
export function sightBlocked(arena:Arena,from:[number,number,number],to:[number,number,number]){
  const dx=to[0]-from[0],dy=to[1]-from[1],dz=to[2]-from[2];
  // Exact segment/box test for every barrier. Walking the ray in fixed steps could step over a
  // 0.15 m wall and report a plate behind it as visible. The boxes arrive with their rotation
  // already resolved (see `sightGeometry`), which is the difference between a 12 ms and a 1 ms
  // assist tick.
  for(const w of sightGeometry(arena).boxes){
    const ax=from[0]-w.cx,ay=from[1]-w.cy,bx=to[0]-w.cx,by=to[1]-w.cy;
    const x0=ax*w.c+ay*w.s,y0=-ax*w.s+ay*w.c,x1=bx*w.c+by*w.s,y1=-bx*w.s+by*w.c;
    let t0=0,t1=1;
    const slab=(p0:number,p1:number,lo:number,hi:number)=>{
      const d=p1-p0;
      if(Math.abs(d)<1e-9)return p0>=lo&&p0<=hi;
      let near=(lo-p0)/d,far=(hi-p0)/d;
      if(near>far){const swap=near;near=far;far=swap;}
      t0=Math.max(t0,near);t1=Math.min(t1,far);
      return t0<=t1;
    };
    if(slab(x0,x1,-w.hw,w.hw)&&slab(y0,y1,-w.hh,w.hh)&&slab(from[2],to[2],w.bottom,w.top))return true;
  }
  // Terrain has no simple box form, so sample it; the step is small enough for the 0.15 m rims.
  const length=Math.hypot(dx,dy,dz),steps=Math.max(1,Math.ceil(length/.1));
  for(let i=1;i<steps;i++){
    const t=i/steps,x=from[0]+dx*t,y=from[1]+dy*t,z=from[2]+dz*t;
    if(terrainHeight(arena,x,y)>z+.12)return true;
  }
  return false;
}

// How much of an armour plate is actually exposed, 0 (nothing) to 1 (the whole face). A plate that
// is half behind a barrier still passes a centre-point line test, so two plates at almost the same
// angle from the reticle used to be ordered by whichever happened to be a hair closer to the
// crosshair — and the assist could lock onto the sliver peeking out of cover while the fully exposed
// one beside it stayed unhittable. The face is sampled on a grid instead, so "least occluded" is a
// measurement rather than a guess.
export function plateExposure(arena:Arena,eye:[number,number,number],center:[number,number,number],normal:number[],width=.27,height=.25){
  // Two in-plane axes for the plate face: the normal is horizontal-ish, so up and its cross product
  // span it.
  const up:[number,number,number]=[0,0,1];
  const right:[number,number,number]=[normal[1]*up[2]-normal[2]*up[1],normal[2]*up[0]-normal[0]*up[2],normal[0]*up[1]-normal[1]*up[0]];
  const rl=Math.hypot(right[0],right[1],right[2])||1;
  right[0]/=rl;right[1]/=rl;right[2]/=rl;
  let clear=0,total=0;
  for(const u of [-.4,0,.4])for(const v of [-.4,0,.4]){
    const p:[number,number,number]=[center[0]+right[0]*u*width+up[0]*v*height,center[1]+right[1]*u*width+up[1]*v*height,center[2]+right[2]*u*width+up[2]*v*height];
    total++;
    if(!sightBlocked(arena,eye,p))clear++;
  }
  return clear/total;
}

// Quaternion rotation of a vector, matching the engine's `_rotate` in the public SDK.
export const rotateVector=(q:number[],v:[number,number,number]):[number,number,number]=>{
  const [x,y,z,w]=q,[vx,vy,vz]=v;
  const tx=2*(y*vz-z*vy),ty=2*(z*vx-x*vz),tz=2*(x*vy-y*vx);
  return [vx+w*tx+y*tz-z*ty,vy+w*ty+z*tx-x*tz,vz+w*tz+x*ty-y*tx];
};

// The armour plate the engine's solver will aim at for a robot. The frame does not publish a
// robot's plate list, so rebuild the same four face centres from its chassis size and quaternion:
// the hull centre can peek over a barrier while the lower plate stays hidden, and only the plate
// actually aimed at may take the lock.
export function robotPlate(robot:Robot,eye:[number,number,number]){
  const size=robot.chassis_size_m,q=robot.quaternion;
  const fallback:[number,number,number]=[robot.x,robot.y,(robot.z||0)+(robot.armor_center_z_m??.3)];
  const fallbackNormal:[number,number,number]=[eye[0]-robot.x,eye[1]-robot.y,0];
  if(!size||!q||q.length!==4||robot.role==='aerial')return {point:fallback,normal:fallbackNormal};
  let best:{point:[number,number,number];normal:[number,number,number];score:number}|null=null;
  for(let face=0;face<4;face++){
    const angle=face*Math.PI/2,nx=Math.cos(angle),ny=Math.sin(angle);
    const reach=(face%2===0?size[0]:size[1])/2-.032;
    const height=face%2?(robot.armor_side_center_z_m??robot.armor_center_z_m??.3):(robot.armor_center_z_m??.3);
    const offset=rotateVector(q,[nx*reach,ny*reach,height]);
    const point:[number,number,number]=[robot.x+offset[0],robot.y+offset[1],(robot.z||0)+offset[2]];
    const normal=rotateVector(q,[nx*Math.cos(Math.PI/12),ny*Math.cos(Math.PI/12),Math.sin(Math.PI/12)]);
    const dx=eye[0]-point[0],dy=eye[1]-point[1],dz=eye[2]-point[2];
    const score=(normal[0]*dx+normal[1]*dy+normal[2]*dz)/Math.max(.001,Math.hypot(dx,dy,dz));
    if(!best||score>best.score)best={point,normal,score};
  }
  return best?{point:best.point,normal:best.normal}:{point:fallback,normal:fallbackNormal};
}

// The plate a shooter at `eye` can actually hit: the one whose face points at the eye, or the
// weakspot when an opened structure exposes it (the same choice the engine's solver makes).
export function facingPlate(structure:Structure,eye:[number,number,number]){
  const plates=(structure.armor_plates??[]).filter(p=>p.weakspot||!structure.armor_open);
  const pool=plates.length?plates:structure.armor_plates??[];
  let best:{point:[number,number,number];normal:number[];score:number}|null=null;
  for(const plate of pool){
    const [x,y,z]=plate.center as [number,number,number];
    const score=plate.normal[0]*(eye[0]-x)+plate.normal[1]*(eye[1]-y)+plate.normal[2]*(eye[2]-z);
    if(!best||score>best.score)best={point:[x,y,z],normal:plate.normal as number[],score};
  }
  return best?{point:best.point,normal:best.normal}:null;
}

export type PlateCandidate={id:string;angle:number;distance:number;priority:number;exposure:number;side?:TeamId;
  /** The face the exposure was measured on; filled in by `lockTarget` before ranking. */
  plate?:{point:[number,number,number];normal:number[]|null}};

// Which enemy plate the assisted lock takes: gather every plate inside the lens with a clear line
// from both the eye and the muzzle, measure how exposed each face is, then rank them.
export function lockTarget(robot:Robot,robots:Robot[],arena:Arena,view:{yaw:number;pitch:number},frame:Frame,keep?:string|null,eyeLift=1.27){
  const hits:PlateCandidate[]=[];
  const muzzleHeight=robot.muzzle_height_m??.5;
  const baseZ=robot.z||0;
  // The eye the pilot actually looks through; the barrel sits lower. A plate must be visible from
  // the eye and reachable from the muzzle, so neither the camera nor the shot can see through cover.
  const eye:[number,number,number]=[robot.x,robot.y,baseZ+muzzleHeight*eyeLift];
  const muzzle:[number,number,number]=[robot.x,robot.y,baseZ+muzzleHeight+.08];
  const consider=(id:string,point:[number,number,number],normal:number[]|null,priority:number,side?:TeamId)=>{
    const dx=point[0]-eye[0],dy=point[1]-eye[1];
    const distance=Math.hypot(dx,dy);
    if(distance>LOCK_RANGE||distance<.05)return;
    const yawOff=Math.abs(shortest(view.yaw,Math.atan2(dy,dx)));
    const platePitch=Math.atan2(point[2]-eye[2],distance);
    const pitchOff=Math.abs(platePitch-view.pitch);
    if(yawOff>LOCK_YAW||pitchOff>LOCK_PITCH)return;
    if(sightBlocked(arena,eye,point))return;
    if(sightBlocked(arena,muzzle,point))return;
    // The true angular separation from the crosshair, so "nearest the reticle" means the same thing
    // for a plate straight ahead as for one near the edge of the lens.
    const cosine=Math.sin(view.pitch)*Math.sin(platePitch)
      +Math.cos(view.pitch)*Math.cos(platePitch)*Math.cos(shortest(view.yaw,Math.atan2(dy,dx)));
    const angle=Math.acos(Math.max(-1,Math.min(1,cosine)));
    if(angle>LOCK_ANGLE)return;
    hits.push({id,angle,distance,priority,exposure:-1,side,plate:{point,normal}});
  };
  for(const other of robots){
    if(other.team===robot.team||!other.alive||other.role==='aerial')continue;
    const plate=robotPlate(other,eye);
    consider(other.id,plate.point,plate.normal,GROUND_PRIORITY_SLOTS.has(other.slot)?0:1);
  }
  // Outposts and bases are valid targets too: their armour plates are ordinary plates. An outpost
  // belongs to whoever last rebuilt it (`owner`), not to the half of the field it stands on, so a
  // red outpost rebuilt by blue is a blue structure.
  const enemy:TeamId=robot.team==='red'?'blue':'red';
  const hostileOutposts=(['red','blue'] as const)
    .map(key=>[key,frame.outposts?.[key]] as const)
    .filter(([key,structure])=>!!structure&&structure.hp>0&&(structure.owner??key)!==robot.team&&!!structure.armor_plates?.length);
  const base=frame.bases?.[enemy];
  if(base&&base.hp>0&&base.armor_plates?.length){
    const plate=facingPlate(base,eye);
    if(plate)consider(`${enemy}_base`,plate.point,plate.normal,2,enemy);
  }
  for(const [key,structure] of hostileOutposts){
    const plate=facingPlate(structure,eye);
    if(plate)consider(`${key}_outpost`,plate.point,plate.normal,2,structure.owner??key);
  }
  // Occlusion is the expensive part of the assist (nine sight lines per plate), and `pickPlate`
  // can only ever choose a plate within `LOCK_EXPOSURE_BAND` of the closest one — so the faces
  // further out than that are measured only when they could still win. A cockpit looking at an
  // empty field used to pay for every plate in the lens on every tick.
  if(hits.length){
    const best=Math.min(...hits.map(c=>c.angle));
    for(const c of hits){
      if(c.angle<=best+LOCK_EXPOSURE_BAND) c.exposure=c.plate?.normal?plateExposure(arena,eye,c.plate.point,c.plate.normal):1;
      else c.exposure=0;
    }
  }
  return pickPlate(hits,keep);
}

// Which candidate takes the lock. Angle still decides first, but only within `band`: when two plates
// sit at almost the same angular distance from the reticle — which is what "several targets near the
// crosshair" means in practice — the most exposed face wins. Beyond the band a plate dead under the
// reticle can never lose to one further out, however clean its line. `keep` is the plate held on the
// previous tick; it stays held while it is still a candidate and is not clearly worse, which is what
// stops the lock flickering between two neighbours.
export function pickPlate<T extends PlateCandidate>(candidates:T[],keep?:string|null,band=LOCK_EXPOSURE_BAND):T|null{
  if(!candidates.length)return null;
  const bestAngle=Math.min(...candidates.map(c=>c.angle));
  const near=candidates.filter(c=>c.angle<=bestAngle+band);
  near.sort((a,b)=>b.exposure-a.exposure||a.angle-b.angle||a.priority-b.priority||a.distance-b.distance);
  const best=near[0];
  if(!keep)return best;
  const held=candidates.find(c=>c.id===keep);
  if(!held)return best;
  if(best.id===held.id)return held;
  // A newly exposed plate still takes over, which is why the exposure gap is checked before the
  // angular slack.
  if(best.exposure>held.exposure+.15)return best;
  if(held.angle<=best.angle+KEEP_SLACK||best.angle>held.angle*KEEP_SWITCH)return held;
  return best;
}

// The point under the crosshair for lobbed fire: the crosshair *is* the impact point, so the cockpit
// has to hand the server a world point rather than an angle.
//
// Everything solid the reticle can meet is a candidate and the *nearest* one wins: enemy armour
// plates (ray against the plate plane, inside its outline), then any barrier box in the field — a
// wall, a deck, a barrier, the plinth — and finally the terrain or the arena floor. Without the
// boxes, aiming at the wall between the shooter and the target put the round on the ground behind
// it, which is not where the crosshair was.
export const lobPoint=(robot:Robot,frame:Frame,yaw:number,pitch:number,eyeLift:number):[number,number,number]|null=>{
  const eye:[number,number,number]=[robot.x,robot.y,(robot.z??0)+(robot.muzzle_height_m??.5)*eyeLift];
  const dir:[number,number,number]=[Math.cos(yaw)*Math.cos(pitch),Math.sin(yaw)*Math.cos(pitch),Math.sin(pitch)];
  // Every solid the ray meets, so the nearest one wins regardless of the order they were tested in.
  const hits:{t:number;point:[number,number,number]}[]=[];
  const keep=(t:number,point:[number,number,number])=>{if(t>1)hits.push({t,point});};
  const structures=[...Object.entries(frame.bases??{}),...Object.entries(frame.outposts??{})];
  for(const [team,structure] of structures){
    if(team===robot.team)continue;
    for(const plate of (structure as {armor_plates?:{center:number[];normal:number[];width?:number;height?:number}[]}).armor_plates??[]){
      const n=plate.normal,c=plate.center;
      const denom=dir[0]*n[0]+dir[1]*n[1]+dir[2]*n[2];
      if(Math.abs(denom)<1e-6)continue;
      const t=((c[0]-eye[0])*n[0]+(c[1]-eye[1])*n[1]+(c[2]-eye[2])*n[2])/denom;
      const hit:[number,number,number]=[eye[0]+dir[0]*t,eye[1]+dir[1]*t,eye[2]+dir[2]*t];
      const along=(hit[0]-c[0])*-n[1]+(hit[1]-c[1])*n[0];
      const across=hit[2]-c[2];
      // A small margin: the shell has a 21 mm bore and the pilot is aiming with a reticle, not a laser.
      if(Math.abs(along)>(plate.width??.135)/2+.12||Math.abs(across)>(plate.height??.125)/2+.12)continue;
      keep(t,hit);
    }
  }
  // Solid barriers, as the same rotated boxes the renderer and the sight test use. The ray is taken
  // into each box's own frame and clipped against its three slabs, so a shot grazing the top edge
  // lands on the top face instead of passing through the corner.
  for(const w of frame.arena.obstacles){
    const a=w.rotation??0,c=Math.cos(a),s=Math.sin(a);
    const cx=w.x+w.w/2,cy=w.y+w.h/2;
    const ax=eye[0]-cx,ay=eye[1]-cy;
    const ox=ax*c+ay*s,oy=-ax*s+ay*c;
    const dx=dir[0]*c+dir[1]*s,dy=-dir[0]*s+dir[1]*c;
    const bottom=w.bottom??0,top=bottom+(w.height??1);
    let t0=0,t1=60;
    const slab=(p0:number,p1:number,lo:number,hi:number)=>{
      if(Math.abs(p1)<1e-9)return p0>=lo&&p0<=hi;
      let near=(lo-p0)/p1,far=(hi-p0)/p1;
      if(near>far){const swap=near;near=far;far=swap;}
      t0=Math.max(t0,near);t1=Math.min(t1,far);
      return t0<=t1;
    };
    if(!slab(ox,dx,-w.w/2,w.w/2))continue;
    if(!slab(oy,dy,-w.h/2,w.h/2))continue;
    if(!slab(eye[2],dir[2],bottom,top))continue;
    if(t0<=0||t0>60)continue;
    keep(t0,[eye[0]+dir[0]*t0,eye[1]+dir[1]*t0,eye[2]+dir[2]*t0]);
  }
  if(hits.length){hits.sort((a,b)=>a.t-b.t);return hits[0].point;}
  for(let t=1;t<=45;t+=.25){
    const x=eye[0]+dir[0]*t,y=eye[1]+dir[1]*t,z=eye[2]+dir[2]*t;
    if(x<0||y<0||x>frame.arena.width||y>frame.arena.height)return null;
    const ground=terrainHeight(frame.arena,x,y);
    if(z<=ground)return [x,y,ground];
  }
  return null;
};
