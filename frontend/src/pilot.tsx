import {useEffect,useMemo,useRef,useState,type CSSProperties,type MutableRefObject} from 'react';
import {Gamepad2,RotateCcw,X,Coins,Layers,PlugZap,Power,Zap,Maximize2,Minimize2} from 'lucide-react';
import {ROLE_NAMES,TEAM_COLORS,type Arena,type CameraMode,type Frame,type MatchEvent,type PilotView,type Robot,type RobotHardware,type Structure,type TeamId} from './types';
import {CameraControls} from './CameraControls';
import {terrainHeight} from './terrain';
import {FPV_EYE_LIFT} from './world';
import {lobScope} from './scope';
import './pilot.css';

// Sent at the simulation's own 20 Hz cadence; the server holds the last command for a
// little longer, so a dropped or late request never stalls the robot.
const SEND_MS=50;
// Input is also pushed on the leading edge of a change (see `nudge`) as long as a request is not
// already in flight, which takes the worst-case input latency from 50 ms down to one round trip.
const NUDGE_MS=12;
// The first-person lens is 64°, so one mouse pixel has to turn the gimbal further than it did on
// the old 80° view for the same hand movement; keeping the ratio keeps the aim familiar.
// The lobbed-fire sight magnifies only its aperture (2.5×), so the mouse is slowed by the same
// factor while it is on the eye; the field around it stays at the plain first-person scale.
const LOB_SCALE=2.5;
// The 42 mm shell on its flat arc carries about 21 m; past that the crosshair cannot be the impact
// point any more, so the cockpit says so instead of firing a round that falls short.
const LOB_MAX_RANGE=20.5;
const FOV_SCALE=64/80;
const YAW_SENSITIVITY=.0042*FOV_SCALE,PITCH_SENSITIVITY=.0032*FOV_SCALE;
const PITCH_MIN=-.26,PITCH_MAX=.78;
// Radians the gimbal may turn per send (about 6.5 rad/s: the turrets' own slew limit), so the view
// never runs far ahead of the real turret even when a request is slow or dropped.
const STEP_RATE=6.5;
const KEY_YAW_RATE=3.4,KEY_PITCH_RATE=1.9;
// Holding a turn key for this long ramps the keyboard rate up to double, so tap-aim stays precise
// while a long slewing turn does not feel sticky.
const KEY_RAMP=0.7;
// How fast the eye borrows the gun's angle while the aim assist is locked (rad/s of blend).
const LOCK_FOLLOW=14;
// The aim assist only picks armour the pilot can actually see: inside the lens, with a clear
// line to the plate. A 64° vertical lens is ±32°; the view is wider than it is tall.
// 12 m is the hard ceiling: beyond that the assist refuses to lock anything at all, robots and
// structures alike, which is what the rules use for close-quarters assisted fire.
const LOCK_YAW=.80,LOCK_PITCH=.56,LOCK_RANGE=12;
// A plate must also sit within this true angular distance of the crosshair to take the lock; the
// closest one wins, so the reticle decides between a robot and a structure at the same angle.
const LOCK_ANGLE=.62;
// Target retention: a lock that is still visible and still close to the reticle is kept until another
// plate is clearly better, so a spinning or partially covered chassis never makes the lock flicker
// between two neighbours. `KEEP_SLACK` is the extra angular room the held plate gets (radians) and
// `KEEP_SWITCH` the fraction the challenger must beat it by.
const KEEP_SLACK=.07,KEEP_SWITCH=.85;
// Ground combat robots (heavy, the two infantry and the sentry) order plates that sit at the same
// angle from the crosshair, then structures. The crosshair itself always comes first.
const GROUND_PRIORITY_SLOTS=new Set([1,3,4,7]);// 小陀螺: the chassis spins under a gimbal that keeps the world aim, like the reference simulator's
// standard mecanum spin. The engine caps a chassis yaw command at ±12 rad/s. A pilot spins with the
// yaw motors' burst authority (`yaw_boost`), which is what makes the hull twice as fast as the
// rated motors allow: measured 10.3 rad/s against 5.0 rad/s for the same chassis without it.
const SPIN_MAX=12,SPIN_MARGIN=.9,SPIN_LUNGE=1.9;
// Supercapacitor dump: the engine's chassis budget is capped at 200 W and anything above the
// robot's own limit is drawn from the supercap (1800 J), so holding C asks for the full budget.
const SUPERCAP_POWER=200;
// Wheel-legged jump, tuned to the engine's leg thrust: crouch, push, then absorb. The latest
// spec halves the jump authority to keep the leap manageable while the chassis remains stable in air.
const JUMP_STRENGTH=.5,JUMP_CROUCH_MS=200,JUMP_LAND_MS=500,JUMP_TIMEOUT_MS=1800;
const HELD_KEYS=['Space','KeyF','KeyI','KeyJ','KeyW','KeyA','KeyS','KeyD','KeyX','KeyC','ShiftLeft','ShiftRight','ArrowLeft','ArrowRight','ArrowUp','ArrowDown'];
const INPUT_REPEAT_BLOCK=new Set(['Space','KeyB','KeyC','KeyI','KeyJ','ShiftLeft','ShiftRight','ArrowLeft','ArrowRight','ArrowUp','ArrowDown']);

type PilotAction={move:[number,number];aim:number;pitch:number;fire:boolean;brake?:boolean;power?:number;yaw_rate?:number;yaw_boost?:number;heading?:number;leg_height?:number;jump?:number;climb?:number;buy_ammo?:{remote:boolean;amount?:number};remote_heal?:boolean;revive?:boolean;install_launcher?:boolean;pick_unit?:boolean;assembly?:number;assembly_insert?:boolean;assembly_lift?:boolean;assembly_flip?:boolean;assembly_rotate?:number;assembly_confirm?:boolean;aim_point?:[number,number,number]};

const wrap=(a:number)=>((a%(Math.PI*2))+Math.PI*2)%(Math.PI*2);
const shortest=(from:number,to:number)=>{const d=(to-from)%(Math.PI*2);return d>Math.PI?d-Math.PI*2:d<-Math.PI?d+Math.PI*2:d;};
const pct=(value:number,max:number)=>`${Math.max(0,Math.min(1,max>0?value/max:0))*100}%`;

function command(yaw:number,pitch:number,keys:Set<string>,spin=0,options:{fire:boolean;boost:boolean;limit:number;legHeight?:number|null;jump?:number|null;climb?:boolean}):PilotAction{
  const forward=(keys.has('KeyW')?1:0)-(keys.has('KeyS')?1:0);
  // While spinning, A/D choose the rotation direction instead of strafing.
  const strafe=spin?0:(keys.has('KeyD')?1:0)-(keys.has('KeyA')?1:0);
  const brake=keys.has('KeyX');
  let mx=0,my=0;
  if(!brake&&(forward||strafe)){
    // Engine axes: forward is (cos yaw, sin yaw), screen right is (-sin yaw, cos yaw).
    const dx=Math.cos(yaw)*forward-Math.sin(yaw)*strafe;
    const dy=Math.sin(yaw)*forward+Math.cos(yaw)*strafe;
    const length=Math.hypot(dx,dy);
    mx=dx/length;my=dy/length;
  }
  // Releasing the throttle sends a zero move on purpose: powered motors then hold the chassis and
  // brake at the model's brake force, which stops it in a fraction of the time that driving
  // backwards against the motion would (that route is limited by motor power and even overshoots
  // into reverse), and it cannot creep backwards once the robot has stopped.
  const driving=!brake&&(!!forward||!!strafe||!!mx||!!my);
  const action:PilotAction={move:[mx,my],aim:wrap(yaw),pitch:Math.min(PITCH_MAX,Math.max(PITCH_MIN,pitch)),fire:options.fire};
  if(brake)action.brake=true;
  if(spin)action.yaw_rate=spin;
  // Chassis and gimbal each carry their own forward axis; by default the hull follows the gimbal's
  // forward, so the robot drives where the pilot looks while the gimbal keeps the world aim.
  if(!spin)action.heading=wrap(yaw);
  // The pilot uses the robot's current power budget while driving and spinning. A dedicated
  // supercap dump is only used when C is held; otherwise the engine runs on the chassis' own limit.
  if(options.boost)action.power=SUPERCAP_POWER;
  else if(driving)action.power=Math.min(SUPERCAP_POWER,Math.max(1,Math.round(options.limit)));
  // Small-spin burst authority is only unlocked by the capacitor dump; otherwise the hull follows the
  // chassis' rated yaw power and stays predictable.
  if(spin&&options.boost)action.yaw_boost=1;
  if(options.legHeight!==null&&options.legHeight!==undefined)action.leg_height=options.legHeight;
  if(options.jump)action.jump=options.jump;
  // Step-climbing mode: the legs mount a kerb or stair the chassis is touching.
  if(options.climb)action.climb=1;
  return action;
}

// Sight line from the gimbal eye to a point, through the field the pilot sees: the same obstacle
// boxes and terrain the renderer draws, so a plate behind a wall or a deck never locks.
function sightBlocked(arena:Arena,from:[number,number,number],to:[number,number,number]){
  const dx=to[0]-from[0],dy=to[1]-from[1],dz=to[2]-from[2];
  // Exact segment/box test for every barrier. Walking the ray in fixed steps could step over a
  // 0.15 m wall and report a plate behind it as visible.
  for(const w of arena.obstacles){
    const a=w.rotation??0,c=Math.cos(a),s=Math.sin(a);
    const cx=w.x+w.w/2,cy=w.y+w.h/2;
    const ax=from[0]-cx,ay=from[1]-cy,bx=to[0]-cx,by=to[1]-cy;
    const x0=ax*c+ay*s,y0=-ax*s+ay*c,x1=bx*c+by*s,y1=-bx*s+by*c;
    const bottom=w.bottom??0;
    let t0=0,t1=1;
    const slab=(p0:number,p1:number,lo:number,hi:number)=>{
      const d=p1-p0;
      if(Math.abs(d)<1e-9)return p0>=lo&&p0<=hi;
      let near=(lo-p0)/d,far=(hi-p0)/d;
      if(near>far){const swap=near;near=far;far=swap;}
      t0=Math.max(t0,near);t1=Math.min(t1,far);
      return t0<=t1;
    };
    if(slab(x0,x1,-w.w/2,w.w/2)&&slab(y0,y1,-w.h/2,w.h/2)&&slab(from[2],to[2],bottom,bottom+(w.height??1)))return true;
  }
  // Terrain has no simple box form, so sample it; the step is small enough for the 0.15 m rims.
  const length=Math.hypot(dx,dy,dz),steps=Math.max(1,Math.ceil(length/.1));
  for(let i=1;i<steps;i++){
    const t=i/steps,x=from[0]+dx*t,y=from[1]+dy*t,z=from[2]+dz*t;
    if(terrainHeight(arena,x,y)>z+.12)return true;
  }
  return false;
}

// The plate a shooter at `eye` can actually hit: the one whose face points at the eye, or the
// weakspot when an opened structure exposes it (the same choice the engine's solver makes).
function facingPlate(structure:Structure,eye:[number,number,number]){
  const plates=(structure.armor_plates??[]).filter(p=>p.weakspot||!structure.armor_open);
  const pool=plates.length?plates:structure.armor_plates??[];
  let best:{point:[number,number,number];score:number}|null=null;
  for(const plate of pool){
    const [x,y,z]=plate.center as [number,number,number];
    const score=plate.normal[0]*(eye[0]-x)+plate.normal[1]*(eye[1]-y)+plate.normal[2]*(eye[2]-z);
    if(!best||score>best.score)best={point:[x,y,z],score};
  }
  return best?.point??null;
}

// Quaternion rotation of a vector, matching the engine's `_rotate` in the public SDK.
const rotateVector=(q:number[],v:[number,number,number]):[number,number,number]=>{
  const [x,y,z,w]=q,[vx,vy,vz]=v;
  const tx=2*(y*vz-z*vy),ty=2*(z*vx-x*vz),tz=2*(x*vy-y*vx);
  return [vx+w*tx+y*tz-z*ty,vy+w*ty+z*tx-x*tz,vz+w*tz+x*ty-y*tx];
};

// The armour plate the engine's solver will aim at for a robot. The frame does not publish a
// robot's plate list, so rebuild the same four face centres from its chassis size and quaternion:
// the hull centre can peek over a barrier while the lower plate stays hidden, and only the plate
// actually aimed at may take the lock.
function robotPlate(robot:Robot,eye:[number,number,number]):[number,number,number]{
  const size=robot.chassis_size_m,q=robot.quaternion;
  const fallback:[number,number,number]=[robot.x,robot.y,(robot.z||0)+(robot.armor_center_z_m??.3)];
  if(!size||!q||q.length!==4||robot.role==='aerial')return fallback;
  let best:{point:[number,number,number];score:number}|null=null;
  for(let face=0;face<4;face++){
    const angle=face*Math.PI/2,nx=Math.cos(angle),ny=Math.sin(angle);
    const reach=(face%2===0?size[0]:size[1])/2-.032;
    const height=face%2?(robot.armor_side_center_z_m??robot.armor_center_z_m??.3):(robot.armor_center_z_m??.3);
    const offset=rotateVector(q,[nx*reach,ny*reach,height]);
    const point:[number,number,number]=[robot.x+offset[0],robot.y+offset[1],(robot.z||0)+offset[2]];
    const normal=rotateVector(q,[nx*Math.cos(Math.PI/12),ny*Math.cos(Math.PI/12),Math.sin(Math.PI/12)]);
    const dx=eye[0]-point[0],dy=eye[1]-point[1],dz=eye[2]-point[2];
    const score=(normal[0]*dx+normal[1]*dy+normal[2]*dz)/Math.max(.001,Math.hypot(dx,dy,dz));
    if(!best||score>best.score)best={point,score};
  }
  return best?.point??fallback;
}

// The enemy armour — robot plate, outpost or base — that the pilot can see and that sits closest
// to the crosshair. Every candidate must be inside the first-person lens, within 12 m, and have a
// clear line to the plate; a plate behind a wall, a deck or a ramp is never picked, so an unblocked
// plate always wins over one hidden behind cover. `keep` is the plate the assist locked last tick:
// while it is still a valid candidate it stays locked unless a challenger is clearly closer to the
// reticle, which is what keeps the lock from flickering between two neighbours.
export function lockTarget(robot:Robot,robots:Robot[],arena:Arena,view:{yaw:number;pitch:number},frame:Frame,keep?:string|null){
  // `priority`: 0 ground combat robot, 1 other chassis, 2 outpost/base.
  const hits:{id:string;angle:number;distance:number;priority:number;side?:TeamId}[]=[];
  const muzzleHeight=robot.muzzle_height_m??.5;
  const baseZ=robot.z||0;
  // The eye the pilot actually looks through; the barrel sits lower. A plate must be visible from
  // the eye and reachable from the muzzle, so neither the camera nor the shot can see through
  // cover.
  const eye:[number,number,number]=[robot.x,robot.y,baseZ+muzzleHeight*FPV_EYE_LIFT];
  const muzzle:[number,number,number]=[robot.x,robot.y,baseZ+muzzleHeight+.08];
  const consider=(id:string,x:number,y:number,z:number,priority:number,side?:TeamId)=>{
    const dx=x-eye[0],dy=y-eye[1];
    const distance=Math.hypot(dx,dy);
    if(distance>LOCK_RANGE||distance<.05)return;
    const yawOff=Math.abs(shortest(view.yaw,Math.atan2(dy,dx)));
    const platePitch=Math.atan2(z-eye[2],distance);
    const pitchOff=Math.abs(platePitch-view.pitch);
    if(yawOff>LOCK_YAW||pitchOff>LOCK_PITCH)return;
    if(sightBlocked(arena,eye,[x,y,z]))return;
    if(sightBlocked(arena,muzzle,[x,y,z]))return;
    // The true angular separation from the crosshair, so "nearest the reticle" means the same
    // thing for a plate straight ahead as for one near the edge of the lens.
    const cosine=Math.sin(view.pitch)*Math.sin(platePitch)
      +Math.cos(view.pitch)*Math.cos(platePitch)*Math.cos(shortest(view.yaw,Math.atan2(dy,dx)));
    const angle=Math.acos(Math.max(-1,Math.min(1,cosine)));
    if(angle>LOCK_ANGLE)return;
    hits.push({id,angle,distance,priority,side});
  };
  for(const other of robots){
    if(other.team===robot.team||!other.alive||other.role==='aerial')continue;
    const plate=robotPlate(other,eye);
    consider(other.id,plate[0],plate[1],plate[2],GROUND_PRIORITY_SLOTS.has(other.slot)?0:1);
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
    if(plate)consider(`${enemy}_base`,plate[0],plate[1],plate[2],2,enemy);
  }
  for(const [key,structure] of hostileOutposts){
    const plate=facingPlate(structure,eye);
    if(plate)consider(`${key}_outpost`,plate[0],plate[1],plate[2],2,structure.owner??key);
  }
  if(!hits.length)return null;
  // Closest to the crosshair wins, full stop: a plate dead under the reticle must never lose the
  // lock to a chassis type that merely ranks higher. The chassis tier and the range only order
  // plates that sit at the same angle from the crosshair.
  hits.sort((a,b)=>a.angle-b.angle||a.priority-b.priority||a.distance-b.distance);
  const best=hits[0];
  if(!keep)return best;
  // The plate that was already locked keeps the lock while it is a valid candidate and is not clearly
  // worse than the challenger: slack in radians plus a margin on the ratio, so jitter at the reticle
  // never trades one plate for another.
  const held=hits.find(h=>h.id===keep);
  if(!held)return best;
  if(best.id===held.id)return held;
  if(held.angle<=best.angle+KEEP_SLACK||best.angle>held.angle*KEEP_SWITCH)return held;
  return best;
}

// Lock readout: a structure has no slot number, and its colour follows the actual owner (an
// outpost rebuilt by the other team is labelled with the team that holds it).
function lockLabel(id:string,side?:TeamId){
  const [key,...rest]=id.split('_');
  const labelSide=(side??key)==='red'?'红方':'蓝方';
  const kind=rest.join('_');
  if(kind==='base')return `${labelSide} 基地装甲`;
  if(kind==='outpost')return `${labelSide} 前哨站装甲`;
  return `${labelSide} ${id.split('-')[1]} 号`;
}

// The point under the crosshair for lobbed fire: the crosshair *is* the impact point, so the cockpit
// has to hand the server a world point rather than an angle. Enemy base and outpost armour plates are
// tested first (ray against the plate plane, inside its outline), then the shot is dropped onto the
// terrain the view finally meets — a lob over a wall still lands where the reticle sits.
const lobPoint=(robot:Robot,frame:Frame,yaw:number,pitch:number):[number,number,number]|null=>{
  const eye:[number,number,number]=[robot.x,robot.y,(robot.z??0)+(robot.muzzle_height_m??.5)*FPV_EYE_LIFT];
  const dir:[number,number,number]=[Math.cos(yaw)*Math.cos(pitch),Math.sin(yaw)*Math.cos(pitch),Math.sin(pitch)];
  let best:{t:number;point:[number,number,number]}|null=null;
  const structures=[...Object.entries(frame.bases??{}),...Object.entries(frame.outposts??{})];
  for(const [team,structure] of structures){
    if(team===robot.team)continue;
    for(const plate of (structure as {armor_plates?:{center:number[];normal:number[];width?:number;height?:number}[]}).armor_plates??[]){
      const n=plate.normal,c=plate.center;
      const denom=dir[0]*n[0]+dir[1]*n[1]+dir[2]*n[2];
      if(Math.abs(denom)<1e-6)continue;
      const t=((c[0]-eye[0])*n[0]+(c[1]-eye[1])*n[1]+(c[2]-eye[2])*n[2])/denom;
      if(t<=1)continue;
      const hit:[number,number,number]=[eye[0]+dir[0]*t,eye[1]+dir[1]*t,eye[2]+dir[2]*t];
      const along=(hit[0]-c[0])*-n[1]+(hit[1]-c[1])*n[0];
      const across=hit[2]-c[2];
      // A small margin: the shell has a 21 mm bore and the pilot is aiming with a reticle, not a laser.
      if(Math.abs(along)>(plate.width??.135)/2+.12||Math.abs(across)>(plate.height??.125)/2+.12)continue;
      if(!best||t<best.t)best={t,point:hit};
    }
  }
  if(best)return best.point;
  for(let t=1;t<=45;t+=.25){
    const x=eye[0]+dir[0]*t,y=eye[1]+dir[1]*t,z=eye[2]+dir[2]*t;
    if(x<0||y<0||x>frame.arena.width||y>frame.arena.height)return null;
    const ground=terrainHeight(frame.arena,x,y);
    if(z<=ground)return [x,y,ground];
  }
  return null;
};

// The heavy robot's third energy unit rides in the gripper once both storage bays are full, so the
// cockpit counts it as carried: the model shows it clamped in the jaws.
const unitsOnBoard=(robot:Robot|null|undefined)=>
  !robot?0:(robot.carried_units??0)+(robot.unit_pickup?.stage==='carrying'?1:0);

// The team's resource dispenser: the pickup point the arm has to reach, so the cockpit can tell a
// pilot how far the chassis still is and refuse a grab that the arm could never reach.
type ResourceSpot={x:number;y:number;dir:[number,number]};
const resourceSpot=(robot:Robot|null,frame?:Frame):ResourceSpot|null=>{
  if(!robot||!frame)return null;
  const fixtures=(frame.arena as {field_geometry?:{fixtures?:{kind?:string;team?:TeamId;pick_point?:number[];pick_dir?:number[]}[]}}|undefined)?.field_geometry?.fixtures;
  const found=fixtures?.find(f=>f.kind==='resource'&&f.team===robot.team);
  if(!found?.pick_point)return null;
  return {x:found.pick_point[0],y:found.pick_point[1],dir:[found.pick_dir?.[0]??0,found.pick_dir?.[1]??0]};
};

// Local purchasing needs the robot on its own supply pad, high point, or a fully controlled
// outpost — the same zones the rulebook accepts. Anything else is a remote order.
const inSupply=(robot:Robot|null,frame?:Frame)=>{
  if(!robot)return false;
  const zones=robot.last_raw_zones??[];
  const team=robot.team,other:TeamId=team==='red'?'blue':'red';
  if(zones.includes(`${team}_base`)||zones.includes(`${team}_supply`)||zones.includes(`${team}_high_point`))return true;
  if(frame?.season!=='2027'){
    // 2026 also accepts a live own outpost, or the enemy one while it is down (first 5 minutes).
    const own=frame?.outposts?.[team],foe=frame?.outposts?.[other];
    if(own&&own.hp>0&&zones.includes(`${team}_outpost`))return true;
    if(foe&&foe.hp<=0&&(frame?.time??0)<300&&zones.includes(`${other}_outpost`))return true;
    return false;
  }
  if(!frame?.positions)return false;
  return (['red','blue'] as const).some(owner=>{
    const position=frame.positions?.[`${owner}_outpost`];
    return zones.includes(`${owner}_outpost`)&&position?.controller===team&&position.control==='full';
  });
};

// Ammunition economy per season: the batch and price the rulebook charges for a click.
type AmmoRule={batch:number;cost:number;cap:number};
type AmmoEconomy={season:string;ammo:Record<'17mm'|'42mm',{local:AmmoRule;remote:AmmoRule}>};
const ammoKind=(robot:Robot|null)=>robot?.role==='heavy'?'42mm':robot?.role==='infantry'||robot?.role==='sentry'?'17mm':null;
type AmmoPrices={local:AmmoRule;remote:AmmoRule};
const AMMO_FALLBACK:Record<'17mm'|'42mm',AmmoPrices>={
  '17mm':{local:{batch:10,cost:10,cap:1000},remote:{batch:100,cost:150,cap:1000}},
  '42mm':{local:{batch:1,cost:10,cap:100},remote:{batch:10,cost:150,cap:100}},
};
const ammoPrices=(economy:Record<string,AmmoEconomy>|null,season:string,kind:'17mm'|'42mm'):AmmoPrices=>economy?.[season]?.ammo?.[kind]??AMMO_FALLBACK[kind];
// Heat a round adds, straight from the rulebook (`/api/health`). `null` means the value is not
// known yet; a sentry in enhanced attack posture and a heavy's launcher-install shot add none.
type HeatRules=Record<string,Record<string,number>>;
const shotHeatFor=(robot:Robot|null,rules:HeatRules|null,season:string):number|null=>{
  if(!robot)return null;
  if((robot.posture==='attack'&&robot.posture_enhanced)||(robot.role==='heavy'&&robot.launcher==='fitted'))return 0;
  const kind=ammoKind(robot);
  if(!kind)return null;
  const value=rules?.[season]?.[kind];
  return typeof value==='number'&&Number.isFinite(value)?value:null;
};
// The trigger keeps at least one full round plus a little headroom free. Using the measured jump
// when it is higher adapts to a modified weapon; before the rules arrive, half the barrel is a
// deliberately conservative stand-in so the first burst cannot cross the limit.
export const shotBudgetFor=(robot:Robot|null,rules:HeatRules|null,season:string,measured:number):number=>{
  const rule=shotHeatFor(robot,rules,season);
  if(rule===0)return 0;
  return Math.max(measured,rule??0)||Math.max(1,(robot?.max_heat||0)/2);
};
export const heatReserveFor=(budget:number,maxHeat:number):number=>budget>0?Math.max(budget*1.15,maxHeat*.05):0;
// Seconds of match already played, and the gold each purchase costs, straight from the rulebook.
const elapsedFor=(frame:Frame)=>Math.max(0,(frame.duration||420)-(frame.remaining||0));
const reviveCostFor=(frame:Frame,robot:Robot|null)=>{
  const level=robot?.role==='sentry'?1:Math.max(1,robot?.level||1);
  return Math.ceil(elapsedFor(frame)/60)*80+level*20;
};
const remoteHealCostFor=(frame:Frame)=>50+Math.ceil(elapsedFor(frame)/60*20);
// Remote orders need six seconds clear of both firing and taking damage.
const disengageWait=(frame:Frame,robot:Robot|null)=>{
  if(!robot)return 6;
  const clock=elapsedFor(frame);
  return Math.max(0,6-Math.min(clock-(robot.last_shot_time??-1e9),clock-(robot.last_damage_time??-1e9)));
};

// 小陀螺 rate for this model: the engine's chassis yaw cap, scaled from the model's own gimbal slew
// so a slow turret does not out-turn its hull. The supercap behind C asks for the whole 12 rad/s.
function spinRateFor(frame:Frame,robot:Robot|null,boost=false){
  if(boost)return SPIN_MAX;
  const slot=String(robot?.model_slot??robot?.slot??'');
  const design=(frame.robot_models as Record<string,{turret_yaw_rate_rad_s?:number}>|undefined)?.[slot];
  const turret=design?.turret_yaw_rate_rad_s??5.5;
  return Math.min(SPIN_MAX,turret*SPIN_MARGIN*SPIN_LUNGE);
}

type LegRange={min:number;nominal:number;max:number};

// The leg travel of a wheel-legged chassis, or null for everything else: `capabilities.jump` is
// what the engine checks before it accepts `jump`/`leg_height` at all.
function legRangeFor(frame:Frame,robot:Robot|null):LegRange|null{
  if(!robot)return null;
  const slot=String(robot.model_slot??robot.slot??'');
  const design=(frame.robot_models as Record<string,{capabilities?:{jump?:boolean};leg_min_m?:number;leg_nominal_m?:number;leg_max_m?:number}>|undefined)?.[slot];
  if(!design?.capabilities?.jump)return null;
  const min=design.leg_min_m??.12,nominal=design.leg_nominal_m??.245,max=design.leg_max_m??.39;
  return {min,nominal,max};
}

// How tall a step this chassis can mount with its legs; 0 means it has no step-climb mode.
function stepClimbFor(frame:Frame,robot:Robot|null){
  const slot=String(robot?.model_slot??robot?.slot??'');
  const design=(frame.robot_models as Record<string,{step_climb_m?:number}>|undefined)?.[slot];
  return design?.step_climb_m??0;
}

// Supercapacitor capacity comes from the hardware table, so the arc shows real joules.
function supercapNominalFor(frame:Frame,robot:Robot|null){
  const slot=String(robot?.model_slot??robot?.slot??'');
  const design=(frame.robot_models as Record<string,{supercap_nominal_j?:number}>|undefined)?.[slot];
  const nominal=design?.supercap_nominal_j;
  return nominal&&nominal>0?nominal:1800;
}

// Pointer lock is not available in every host (embedded previews reject it outright), so aiming
// also works with a plain mouse over the viewport, the arrow keys, and a hidden cursor. The lock is
// requested on the viewport because the canvas carries `pointer-events:none` while piloting.
function requestLock(onDenied:(message:string)=>void){
  if(document.pointerLockElement)return;
  // Chrome grants the lock only from a user gesture and only for an element of the active
  // document, so the canvas is asked first, then the viewport, then the page itself.
  const targets=[
    document.querySelector('#viewport canvas') as HTMLElement|null,
    document.querySelector('#viewport') as HTMLElement|null,
    document.body,
  ].filter((element):element is HTMLElement=>!!element);
  const denied=()=>onDenied('此环境不允许锁定鼠标：在画面内移动鼠标即可转向（或用方向键）');
  for(const target of targets){
    let result:unknown;
    try{result=target.requestPointerLock?.();}catch{continue;}
    if(result&&typeof (result as Promise<void>).then==='function'){
      (result as Promise<void>).then(()=>undefined).catch(denied);
    }
    return;
  }
  denied();
}

// Center HUD: three arcs only — health, power and heat — around the crosshair, with the round
// count beside them. The supercapacitor and buffer arcs that used to fill the other two quadrants
// told a pilot nothing they could act on mid-fight, so they are gone; the whole cluster keeps the
// spec's 40 % transparency.
const RING_R=33,RING_SPAN=76,RING_STROKE=3.4/4;
// `value` in 0..1 picks how much of the span is drawn from the arc's start.
function arcPart(cx:number,cy:number,r:number,fromDeg:number,spanDeg:number,value:number){
  const v=Math.max(0,Math.min(1,value));
  if(v<=.001)return '';
  const a=(d:number)=>d*Math.PI/180,from=a(fromDeg),to=a(fromDeg+spanDeg*v);
  return `M${(cx+r*Math.cos(from)).toFixed(2)} ${(cy+r*Math.sin(from)).toFixed(2)} A${r} ${r} 0 0 1 ${(cx+r*Math.cos(to)).toFixed(2)} ${(cy+r*Math.sin(to)).toFixed(2)}`;
}
const ARCS=[-140,-30,80] as const;

function AimRing({robot,heatBlocked}:{robot:Robot;heatBlocked:boolean}){
  const share=(value:number,max:number)=>max>0?Math.max(0,Math.min(1,value/max)):0;
  const hp=share(robot.hp,robot.max_hp);
  const power=share(robot.power_w??0,robot.power_limit||200);
  const heat=share(robot.heat,robot.max_heat);
  const heatColor=robot.overheated?'#ff7a66':heatBlocked?'#ffb454':heat>.75?'#ffb454':'#8fd3e8';
  return <>
    {/* Arc order clockwise from the lower left: health, power, heat. Only a real barrel lock turns
        the ring red; a blocked shot merely warms the heat arc. */}
    <div className={`pilot-reticle ${robot.overheated?'overheated':''}`} aria-hidden="true">
      <svg viewBox="0 0 96 96">
        {ARCS.map((start,i)=><path key={`t${i}`} d={arcPart(48,48,RING_R,start,RING_SPAN,1)} fill="none" stroke="#ffffff" strokeOpacity=".22" strokeWidth={RING_STROKE} strokeLinecap="round"/>)}
        <path d={arcPart(48,48,RING_R,ARCS[0],RING_SPAN,hp)} fill="none" stroke={hp<.3?'#ff6a5a':'#7fe0a8'} strokeWidth={RING_STROKE} strokeLinecap="round"/>
        <path d={arcPart(48,48,RING_R,ARCS[1],RING_SPAN,power)} fill="none" stroke="#ffcf4a" strokeWidth={RING_STROKE} strokeLinecap="round"/>
        <path d={arcPart(48,48,RING_R,ARCS[2],RING_SPAN,heat)} fill="none" stroke={heatColor} strokeWidth={RING_STROKE} strokeLinecap="round"/>
      </svg>
    </div>
    <svg className="pilot-cross" viewBox="0 0 32 32" aria-hidden="true">
      {/* `var()` only resolves in a style property, not in an SVG presentation attribute, so the
          crosshair rides the team accent through inline style instead of `stroke=`. */}
      <g style={{stroke:'var(--hud-cross,#eaf2f8)'}} strokeWidth="1.6" strokeLinecap="round" fill="none">
        <path d="M16 5v5M16 22v5M5 16h5M22 16h5"/>
      </g>
      <circle cx="16" cy="16" r="1.2" style={{fill:'var(--hud-cross,#eaf2f8)'}}/>
    </svg>
    <div className={`pilot-readout ${robot.overheated?'overheated':''}`} aria-hidden="true">
      <span className="pilot-ammo">{robot.ammo}<i>发</i></span>
      <small>{robot.overheated?'过热':robot.max_heat>0?`热 ${Math.round(robot.heat)}/${Math.round(robot.max_heat)}`:'无热限'}</small>
    </div>
  </>;
}

function Vitals({robot,thresholds,capNominal,gold}:{robot:Robot;thresholds:number[];capNominal:number;gold:number}){
  const level=Math.max(1,robot.level||1);
  // Rules thresholds define each level's span; without them fall back to the even 550 curve.
  const floor=thresholds[level-1]??(level-1)*550,ceiling=thresholds[level]??level*550;
  const xp=ceiling>floor?pct((robot.experience??0)-floor,ceiling-floor):'100%';
  const hpShare=robot.max_hp>0?robot.hp/robot.max_hp:0;
  const hpColor=hpShare>.5?'#7fe0a8':hpShare>.25?'#ffcf4a':'#ff6a5a';
  return <div className="pilot-vitals" aria-label="机体状态">
    <div className="vitals-head"><b>{robot.team==='red'?'R':'B'}{robot.slot}</b><span>{ROLE_NAMES[robot.role]}</span><em>LV {level}</em></div>
    <div className="vital">
      <span>HP</span><b style={{color:hpColor}}>{Math.max(0,Math.ceil(robot.hp))}</b><small>/{Math.ceil(robot.max_hp)}</small>
      <i className="hp" style={{width:pct(robot.hp,robot.max_hp),background:hpColor}}/>
    </div>
    <div className="vital"><span>EXP</span><b>{Math.round(robot.experience??0)}</b><small>升级</small><i className="xp" style={{width:xp}}/></div>
    <div className="vital"><span>缓冲</span><b>{Math.round(robot.buffer_energy_j??0)}</b><small>J · 上限 {Math.round(robot.power_limit||0)} W</small><i className="buffer" style={{width:pct(robot.buffer_energy_j??0,60)}}/></div>
    <div className="vital"><span>超电</span><b>{Math.round(robot.supercap_energy_j??0)}</b><small>/{Math.round(capNominal)} J</small><i className="supercap" style={{width:pct(robot.supercap_energy_j??0,capNominal)}}/></div>
    <div className="vital"><span>金币</span><b>{Math.round(gold)}</b><small>本局累计 · O 买弹 · H 远程{robot.role==='heavy'?' · I 装配 · J 装发射机构':''}</small></div>
  </div>;
}

// Hover card of the pre-match chassis picker: the same numbers the lineup inspection shows, so a
// pilot can size a chassis up under the pointer instead of guessing from the model alone.
const CHASSIS_NAMES:Record<string,string>={mecanum:'麦克纳姆轮',swerve:'舵轮',omni:'全向轮',wheel_legged:'双轮足',quadrotor:'多旋翼',legged:'串联腿'};
export function PickRobotCard({robot,hardware,image,hint='点击接管这台机体'}:{robot:Robot;hardware?:RobotHardware;image?:string;hint?:string}){
  const caps=hardware?.capabilities as Record<string,unknown>|undefined,air=robot.role==='aerial';
  const stats=hardware?.initial_stats;
  const chips=[hardware?(CHASSIS_NAMES[hardware.chassis_type]||hardware.chassis_type):null,caps?.jump?'跳跃':null,caps?.transformation?'变形':null,caps?.tunnel?'过隧道':null,caps?.self_righting?'自扶正':null,caps?.deployment?'部署':null].filter(Boolean) as string[];
  return <div className={`pilot-pick-card ${robot.team}`}>
    <div className="ppc-head">
      <b>{String(robot.slot).padStart(2,'0')}</b>
      <div><span>{robot.team==='red'?'红方':'蓝方'} · {ROLE_NAMES[robot.role]}</span><h3>{hardware?.name||robot.design_name||ROLE_NAMES[robot.role]}</h3><small>{robot.model_slot??robot.slot} 型 · {hardware?.focus||robot.design_focus||''}</small></div>
      {image&&<img className="ppc-art" src={image} alt=""/>}
    </div>
    <div className="ppc-stats">
      <span>生命值<b>{air?'空中支援':Math.round(robot.max_hp)}</b></span>
      <span>底盘功率<b>{Math.round(robot.power_limit||stats?.power_w||0)} W</b></span>
      <span>热量上限<b>{robot.max_heat?Math.round(robot.max_heat):'无发射'}</b></span>
      <span>单发伤害<b>{stats?.damage?`${stats.damage} · ${stats.damage>=100?'42mm':'17mm'}`:'—'}</b></span>
      <span>机动速度<b>{(hardware?.speed_reference_mps||0).toFixed(1)} m/s</b></span>
      <span>整机质量<b>{(robot.mass_kg||hardware?.mass_kg||0).toFixed(1)} kg</b></span>
    </div>
    {chips.length>0&&<div className="ppc-chips">{chips.map(c=><span key={c}>{c}</span>)}</div>}
    <div className="ppc-hint">{hint}</div>
  </div>;
}

// The pointer is tracked once for the cockpit: a card that mounts because a chassis just came under
// the pointer has to land there immediately instead of at the corner or the middle of the screen.
const pointerNow={x:0,y:0,seen:false};
if(typeof window!=='undefined')window.addEventListener('pointermove',(event)=>{pointerNow.x=event.clientX;pointerNow.y=event.clientY;pointerNow.seen=true;},{passive:true});

// Link Start keeps the pointer free while it scans the field: the card rides the pointer and names
// the chassis underneath, so the pilot reads the numbers before committing to a link.
export function LinkHoverCard({robot,hardware,image}:{robot:Robot;hardware?:RobotHardware;image?:string}){
  const host=useRef<HTMLDivElement|null>(null);
  useEffect(()=>{
    // The card is docked to the bottom-left of the field rather than following the pointer: while a
    // chassis is under the pointer the camera dives onto it, so a card pinned to the pointer would sit
    // exactly on the machine it is describing.
    const place=()=>{
      const el=host.current;if(!el)return;
      const w=el.offsetWidth||330,h=el.offsetHeight||250;
      const field=document.getElementById('viewport')?.getBoundingClientRect();
      const left=(field?field.left:0)+12,top=(field?field.bottom:window.innerHeight)-h-12;
      el.style.transform=`translate3d(${Math.round(left)}px,${Math.round(top)}px,0)`;
    };
    place();
    window.addEventListener('resize',place,{passive:true});
    return()=>window.removeEventListener('resize',place);
  },[]);
  return <div ref={host} className="pilot-link-hover" aria-live="polite">
    <PickRobotCard robot={robot} hardware={hardware} image={image} hint="点击这台机体 · 建立连接"/>
  </div>;
}

// The commitment screen: one chassis, its numbers, and the two ways out. Enter accepts so a pilot
// can confirm with the keyboard after scanning with the pointer.
export function LinkConfirm({robot,hardware,image,onConfirm,onCancel}:{robot:Robot;hardware?:RobotHardware;image?:string;onConfirm:()=>void;onCancel:()=>void}){
  const accept=useRef<HTMLButtonElement|null>(null),host=useRef<HTMLDivElement|null>(null);
  useEffect(()=>{
    accept.current?.focus();
    const key=(event:KeyboardEvent)=>{
      if(event.key==='Escape'){event.preventDefault();onCancel();}
      else if(event.key==='Enter'){event.preventDefault();onConfirm();}
    };
    window.addEventListener('keydown',key);
    return()=>window.removeEventListener('keydown',key);
  },[onConfirm,onCancel]);
  return <div className="link-confirm" ref={host} role="dialog" aria-modal="true" aria-label="建立神经连接">
    <div className="link-confirm-ring" aria-hidden="true"/>
    <div className={`link-confirm-panel ${robot.team}`}>
      <span className="link-confirm-eyebrow"><PlugZap size={13}/>LINK START</span>
      <h2>建立神经连接？</h2>
      <p className="link-confirm-lead">接管后这台机体交由你直接操控，策略仍指挥其余机体。</p>
      <PickRobotCard robot={robot} hardware={hardware} image={image} hint="确认后视角将切入第一人称"/>
      <div className="link-confirm-actions">
        <button className="link-back" onClick={onCancel}><X size={13}/>取消</button>
        <button className="link-go" ref={accept} onClick={onConfirm}><Zap size={14}/>LINK START</button>
      </div>
    </div>
  </div>;
}

// The side brief of the pre-match half picker: it rides above whichever half the pointer is over, so
// the field itself stays unobstructed while a pilot compares the two sides before committing.
export function HalfBrief({side,team,strategy,mode,standing,robots,active}:{
  side:TeamId;team:string;strategy:string;mode:string;robots:number;
  standing?:{rating:number;games:number;wins:number;losses:number;draws:number};
  active:boolean;
}){
  const rate=standing&&standing.games>0?Math.round(standing.wins/standing.games*100):null;
  return <div className={`half-brief ${side} ${active?'active':''}`} aria-hidden={!active}>
    <span className="hb-side"><i/>{team} · 阵地</span>
    <b>{strategy}</b>
    <div className="hb-rows">
      <span>胜率<em>{rate===null?'首战':`${rate}%`}</em></span>
      <span>Elo<em>{standing?Math.round(standing.rating):'—'}</em></span>
      <span>战绩<em>{standing?`${standing.wins}/${standing.losses}/${standing.draws}`:'—'}</em></span>
      <span>机体<em>{robots}<small>台</small></em></span>
    </div>
    <small>{mode} · 单击确认</small>
  </div>;
}

export function PlayerCockpit({frame,active,onEngage,onRelease,view,open,onOpen,paused,onError,camera,onCamera,onPause,canPause=true,fullscreen=false,onFullscreen,link=false,onLink,linkPending=null,onLinkPick,linkImage,seat=null,send}:{
  frame:Frame;
  active:string|null;
  onEngage:(id:string)=>void;
  onRelease:()=>void;
  view:MutableRefObject<PilotView|null>;
  open:boolean;
  onOpen:(open:boolean)=>void;
  paused:boolean;
  onError:(message:string)=>void;
  camera?:CameraMode;
  onCamera?:(mode:CameraMode)=>void;
  onPause?:()=>void;
  /** Only the host referee may pause a LAN match from a cockpit. */
  canPause?:boolean;
  /** The viewport is fullscreen: the panel offers the way back out as well as in. */
  fullscreen?:boolean;
  onFullscreen?:()=>void;
  /** Link Start is unfolded: the panel is docked to the right and the field becomes the picker. */
  link?:boolean;
  onLink?:(on:boolean)=>void;
  /** Chassis waiting for the pilot's confirmation, or null while the field is still being scanned. */
  linkPending?:string|null;
  onLinkPick?:(id:string|null)=>void;
  /** Studio render of the pending chassis, shown on the confirmation plate. */
  linkImage?:string;
  /** LAN operator seat: the cockpit may only link to this chassis and never switches sides. */
  seat?:{team:TeamId;slot:number}|null;
  /** LAN transport: input goes over the WebSocket instead of a 20 Hz HTTP request. */
  send?:(body:{team:TeamId;slot:number;action:unknown;assist?:string})=>Promise<unknown>;
}){
  const [team,setTeam]=useState<TeamId>(seat?.team??'red'),[locked,setLocked]=useState(false);
  useEffect(()=>{if(seat)setTeam(seat.team);},[seat?.team,seat?.slot]);
  const [notice,setNotice]=useState(''),[lockInfo,setLockInfo]=useState<{id:string;distance:number;side?:TeamId}|null>(null);
  const [thresholds,setThresholds]=useState<number[]>([]);
  // Ammunition economy from the server, so the order the cockpit places always matches the
  // price, batch and purchase cap the rulebook will apply.
  const [economy,setEconomy]=useState<Record<string,AmmoEconomy>|null>(null);
  const economyRef=useRef<Record<string,AmmoEconomy>|null>(null);
  economyRef.current=economy;
  // Per-round heat from the server, so the trigger guard uses the rulebook value instead of
  // guessing from the first burst.
  const [heatRules,setHeatRules]=useState<HeatRules|null>(null);
  const heatRulesRef=useRef<HeatRules|null>(null);
  heatRulesRef.current=heatRules;
  // Every notice fades on its own so the view never keeps a stale message.
  useEffect(()=>{if(!notice)return;window.clearTimeout(noticeTimer.current);noticeTimer.current=window.setTimeout(()=>setNotice(''),3500);return()=>window.clearTimeout(noticeTimer.current);},[notice]);
  const keys=useRef(new Set<string>()),inFlight=useRef(false),lastSend=useRef(0);
  // Ordered so a release can never be overtaken by an older command still in flight.
  const pending=useRef<Promise<unknown>|null>(null),releasing=useRef(false),sent=useRef<number|null>(null);
  // The raw aim target the hand has built up; `view` (shared with the camera) carries only the
  // gimbal angle that was actually commanded, so the crosshair rides the gun instead of leading it.
  const input=useRef<PilotView|null>(null),nudge=useRef<((now:number)=>void)|null>(null),held=useRef(0);
  // Wheel-legged jump phases: idle → crouch (0.2 s) → air → land (0.5 s cushion).
  const jump=useRef<{stage:'idle'|'crouch'|'air'|'land';at:number;seen:boolean}>({stage:'idle',at:0,seen:false});
  // One-shot ammo order: true = remote delivery, false = local purchase in the supply zone.
  // `buyPending` is the order stamp, cleared by the engine's own purchase event or by a timeout.
  const buy=useRef<{remote:boolean;amount:number}|null>(null),buyPending=useRef(0),noticeTimer=useRef(0),openRef=useRef(false);
  // The plate the aim assist currently holds, so an established lock is not traded away every tick.
  const lockId=useRef<string|null>(null);
  // One-shot immediate respawn / remote heal requests, consumed by the next manual command.
  const revive=useRef(false),heal=useRef(false);
  // Local (O) and remote (H) purchase dialogs. While one is open the pointer is released and the
  // pilot's keys are ignored, so the quantity can be picked with the mouse.
  const [store,setStore]=useState<{mode:'local'|'remote';tab:'ammo'|'heal';amount:number;batches:number}|null>(null);
  const storeRef=useRef(store);
  storeRef.current=store;
  // Heavy-robot choreography: I picks up a core at the resource station, opens the assembly order at
  // the plinth and holds the launcher installation at the workbench; O is the ammunition purchase and
  // H the remote delivery, for every robot.
  const [assembly,setAssembly]=useState(false);
  const assemblyRef=useRef(false);
  assemblyRef.current=assembly;
  const assemblyOrder=useRef<number|null>(null);
  const heavyHold=useRef({pick:false,install:false});
  const pickNotice=useRef('');
  // R flips the mechanical sight up on a heavy that has its 42 mm on: a 2.5× lens in the aperture,
  // and the crosshair becomes the impact point the server drops the shell onto.
  const [lob,setLob]=useState(false);
  const lobRef=useRef(false);
  // A tap on the trigger in lob mode keeps asking for that round until it has left the barrel: the
  // launcher first has to climb to the solved elevation.
  const lobShot=useRef<{ammo:number;at:number}|null>(null);
  const lobActive=(robot:Robot|null)=>!!robot&&robot.role==='heavy'&&['fitted','installed'].includes(robot.launcher??'');
  function setLobMode(next:boolean){
    lobRef.current=next;setLob(next);
    lobScope.active=next;
    if(!next)lobScope.sight=0;
    // Seed the shared sight line so the first frame of the sight is already where the pilot looks.
    if(next){lobScope.yaw=sent.current??0;lobScope.pitch=view.current?.pitch??0;}
    setNotice(next?'吊射模式 · 机械瞄具已翻到眼前（2.5× 镜内放大）· 准星即落点':'瞄具翻回，退出吊射模式');
  }  const modal=open||store!==null||assembly;
  openRef.current=modal;
  // The match only accepts input once the prep phase ends; before that the pointer stays free so
  // the setup panel can be used, and a destroyed chassis hands the pointer back until it revives.
  const running=frame.status==='running';
  const runningRef=useRef(false);
  runningRef.current=running;
  // True once the pilot asked for the mouse in this engagement, so a respawn can take it back.
  const armed=useRef(false),wasDead=useRef(false),quietLock=useRef(false);
  // The pointer the field currently holds, so the panel can take it back before it is clickable.
  const captured=useRef<number|null>(null);
  // The aerial system flies itself, so only chassis robots can be piloted.
  const roster=useMemo(()=>frame.robots.filter(r=>r.team===team&&r.role!=='aerial'&&(!seat||r.slot===seat.slot)),[frame.robots,team,seat?.slot]);
  // A pilot keeps the robot they engaged even if the lineup changes under them.
  const piloted=active?frame.robots.find(r=>r.id===active&&r.role!=='aerial')??null:null;
  const target=piloted??roster[0]??null;
  // The chassis the field scan (or the docked roster) put forward for confirmation.
  const linkRobot=linkPending?frame.robots.find(r=>r.id===linkPending)??null:null;
  const robotRef=useRef<Robot|null>(piloted);
  robotRef.current=piloted;
  // A destroyed chassis keeps the camera and the keys until the rules bring it back, exactly like
  // the referee HUD: the view is frozen, greyed, and shows the respawn countdown.
  const dead=!!piloted&&!piloted.alive;
  const deadRef=useRef(dead);
  deadRef.current=dead;
  const respawnLeft=Math.max(0,Math.round((piloted?.respawn_required||0)-(piloted?.respawn_progress||0)));
  const respawnShare=piloted?.respawn_required?Math.min(1,Math.max(0,(piloted.respawn_progress||0)/piloted.respawn_required)):0;
  // Heat control, measured from the robot itself as a fallback for the rulebook value. The heat a
  // single shot adds is the jump seen between two frames; the id guard stops a takeover switch
  // from reading the previous chassis' heat as a shot.
  const shotHeat=useRef(0),lastShot=useRef({id:'',heat:0,ammo:0});
  if(piloted){
    const seen=lastShot.current;
    if(seen.id===piloted.id){
      const spent=seen.ammo-piloted.ammo,rise=piloted.heat-seen.heat;
      // Two shells can land inside one 50 ms window, so the rise is split over the shells spent.
      if(spent>0&&rise>0)shotHeat.current=Math.max(shotHeat.current,rise/spent);
    }else shotHeat.current=0;
    lastShot.current={id:piloted.id,heat:piloted.heat,ammo:piloted.ammo};
  }
  // A shell that would push the barrel past its limit is not fired: the engine locks the gun when
  // heat crosses the limit instead of refusing the shot, so this guard is what keeps the barrel
  // usable. The rulebook value is authoritative, the measured jump covers a modified weapon and
  // half the barrel is the conservative stand-in until `/api/health` answers.
  const heatSeason=String(frame.season??'2027');
  const shotBudget=shotBudgetFor(piloted,heatRules,heatSeason,shotHeat.current);
  const heatReserve=heatReserveFor(shotBudget,piloted?.max_heat||0);
  const heatBlocked=!!piloted&&!!piloted.alive&&!piloted.overheated&&(piloted.max_heat||0)>0&&piloted.heat+heatReserve>piloted.max_heat;
  const heatLocked=!!piloted&&(piloted.overheated||!!piloted.heat_permanent_lock);
  const fireBlocked=heatBlocked||heatLocked;
  const supercapNominal=supercapNominalFor(frame,piloted);
  // A hit flickers a red vignette, the reference client's damage feedback.
  const [hitTick,setHitTick]=useState(0);
  // Step-climb feedback: the key state drives the mode badge immediately, and the engine's own
  // step_climb event holds the "climbing" state so a brief input gap cannot make it blink.
  const [climbHeld,setClimbHeld]=useState(false),[climbPulse,setClimbPulse]=useState(0);
  const lastHp=useRef(piloted?.hp??0);
  useEffect(()=>{
    const hp=piloted?.hp??0;
    if(piloted&&hp<lastHp.current-1)setHitTick(t=>t+1);
    lastHp.current=hp;
  },[piloted?.hp,piloted]);
  const robotsRef=useRef(frame.robots);
  robotsRef.current=frame.robots;
  // The spin rate depends on the hardware table, which is static for a match.
  const frameRef=useRef(frame);
  frameRef.current=frame;
  // A respawn teleports the chassis, so the aim target is resynced to the new turret pose instead
  // of sweeping the view back to where the robot died.
  useEffect(()=>{
    const r=robotRef.current;
    if(!r||!r.alive)return;
    const aim={yaw:r.aim??r.heading??0,pitch:Math.min(PITCH_MAX,Math.max(PITCH_MIN,r.pitch??0))};
    input.current={...aim};
    view.current={...aim};
    sent.current=wrap(aim.yaw);
    held.current=0;
    jump.current={stage:'idle',at:0,seen:false};
  },[piloted?.alive]);
  useEffect(()=>{if(paused)keys.current.clear();},[paused]);
  // Level thresholds and ammunition prices are rules data; the HUD reads them once instead of
  // hardcoding the curve.
  useEffect(()=>{let live=true;fetch('/api/health').then(r=>r.json()).then(v=>{if(!live)return;if(Array.isArray(v?.experience?.thresholds))setThresholds(v.experience.thresholds);if(v?.economy)setEconomy(v.economy);if(v?.heat&&typeof v.heat==='object')setHeatRules(v.heat as HeatRules);}).catch(()=>undefined);return()=>{live=false;};},[]);
  // Purchase feedback comes from the engine's own ammo_purchase event, so the cash and count are the rules'.
  useEffect(()=>{
    const purchase=frame.events.find(event=>event.type==='ammo_purchase'&&event.robot===piloted?.id) as (MatchEvent&{amount?:number;cost?:number;remote?:boolean})|undefined;
    if(purchase){
      buyPending.current=0;
      setNotice(`+${purchase.amount??0} 发 · ${purchase.cost??0} 金币${purchase.remote?'（远程，6 秒送达）':'（补给区）'}`);
    }
  },[frame.events,piloted]);
  // A refused order says why, instead of looking like a lost click.
  useEffect(()=>{
    const refusal=frame.events.find(event=>event.type==='ammo_refused'&&event.robot===piloted?.id) as (MatchEvent&{reason?:string})|undefined;
    if(refusal){
      buyPending.current=0;
      setNotice(`购买未生效：${refusal.reason??'当前条件不满足'}`);
    }
  },[frame.events,piloted]);
  // The engine's step event is the ground truth for the badge, including the carry after the key
  // is released.
  useEffect(()=>{
    if(frame.events.some(event=>event.type==='step_climb'&&event.robot===piloted?.id))setClimbPulse(performance.now());
  },[frame.events,piloted]);

  const post=async(body:{team:TeamId;slot:number;action:unknown;assist?:string})=>{
    if(send)return await send(body);
    const response=await fetch('/api/player',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const value=await response.json().catch(()=>({}));
    if(!response.ok){
      // A stale backend rejects the pilot body outright; say so instead of looking like the AI took over.
      if(response.status===422)throw new Error('服务端版本过旧，无法接管：请重启 python scripts/project.py run');
      // The match may still be booting on its own thread; that refusal is temporary.
      const failure=Object.assign(new Error(typeof value.detail==='string'?value.detail:'无法交接第一视角操控'),{status:response.status});
      throw failure;
    }
    return value;
  };

  const activeId=piloted?.id??null;
  // Taking a chassis marks this engagement as one that wants the mouse, even when the takeover came
  // from the pre-match picker instead of the cockpit's own engage button.
  useEffect(()=>{if(activeId)armed.current=true;},[activeId]);
  useEffect(()=>{
    if(!activeId)return;
    releasing.current=false;
    sent.current=null;
    const startAim=()=>{const robot=robotRef.current;return {yaw:robot?.aim??robot?.heading??0,pitch:Math.min(PITCH_MAX,Math.max(PITCH_MIN,robot?.pitch??0))};};
    if(!input.current)input.current=startAim();
    if(!view.current)view.current={...input.current};
    const canvas=document.querySelector('#viewport canvas') as HTMLCanvasElement|null;
    // The canvas itself ignores pointer events while piloting, so the lock request listens on the
    // viewport instead of the canvas.
    const surface=document.querySelector('#viewport') as HTMLElement|null;
    const send=async()=>{
      const robot=robotRef.current,current=input.current;
      const now=performance.now();
      if(!robot||!current||inFlight.current||releasing.current){lastSend.current=now;return;}
      // A destroyed chassis stays on the pilot's lease but takes no input: the camera keeps its
      // pose and the only thing that moves is the respawn countdown.
      if(deadRef.current){
        const heldAim=view.current??current;
        // A destroyed chassis cannot jump, so the phase machine is parked until it respawns.
        jump.current={stage:'idle',at:0,seen:false};
        inFlight.current=true;
        const leaseAction:{move:[number,number];aim:number;pitch:number;fire:boolean;brake:boolean;revive?:boolean}={move:[0,0],aim:wrap(heldAim.yaw),pitch:heldAim.pitch,fire:false,brake:true};
        // Immediate respawn: one paid order, then the engine revives at the next rules tick.
        if(revive.current){revive.current=false;leaseAction.revive=true;}
        const lease=post({team:robot.team,slot:robot.slot,action:leaseAction});
        pending.current=lease;
        try{await lease;}catch{/* the respawn lease is best-effort */}
        finally{inFlight.current=false;}
        return;
      }
      const elapsed=lastSend.current?Math.min(.2,(now-lastSend.current)/1000):SEND_MS/1000;
      lastSend.current=now;
      // Held turn keys ramp up to twice the base rate, so taps stay fine and long slews are quick.
      const turning=keys.current.has('ArrowLeft')||keys.current.has('ArrowRight')||keys.current.has('ArrowUp')||keys.current.has('ArrowDown');
      held.current=turning?held.current+elapsed:0;
      const ramp=1+Math.min(1,held.current/KEY_RAMP);
      // Ignore duplicate key-repeat events so a held key does not stack multiple input packets in a
      // single burst; the set state already represents the held intent, and the ramp handles long aim.
      if(keys.current.has('ArrowLeft'))current.yaw-=KEY_YAW_RATE*ramp*elapsed;
      if(keys.current.has('ArrowRight'))current.yaw+=KEY_YAW_RATE*ramp*elapsed;
      if(keys.current.has('ArrowUp'))current.pitch+=KEY_PITCH_RATE*ramp*elapsed;
      if(keys.current.has('ArrowDown'))current.pitch-=KEY_PITCH_RATE*ramp*elapsed;
      current.pitch=Math.min(PITCH_MAX,Math.max(PITCH_MIN,current.pitch));
      // Lock against the gun/camera pose the pilot is actually looking through, not the raw mouse
      // target: while the turret slews the input can point at a plate that is still off screen.
      const lockView={yaw:robot.aim??robot.heading??current.yaw,pitch:Math.min(PITCH_MAX,Math.max(PITCH_MIN,robot.pitch??current.pitch))};
      const assisted=keys.current.has('MouseRight')
        ?lockTarget(robot,robotsRef.current,frameRef.current.arena,lockView,frameRef.current,lockId.current)
        :null;
      const next=assisted?{id:assisted.id,distance:assisted.distance,side:assisted.side}:null;
      lockId.current=next?.id??null;
      setLockInfo(prev=>prev?.id===next?.id&&prev?.distance===next?.distance?prev:next);
      // Command the gimbal at a bounded rate; the camera reads this commanded angle, so the eye,
      // the crosshair and the gun stay on one timeline.
      const wanted=wrap(current.yaw);
      const budget=Math.min(.9,STEP_RATE*elapsed);
      const step=sent.current===null?0:Math.max(-budget,Math.min(budget,shortest(sent.current,wanted)));
      sent.current=sent.current===null?wanted:wrap(sent.current+step);
      // While assisted the engine owns the angles; the input eases onto the gun instead of
      // snapping, so releasing the button never jumps the camera.
      if(assisted){
        const blend=Math.min(1,LOCK_FOLLOW*elapsed);
        current.yaw=wrap(current.yaw+shortest(current.yaw,robot.aim)*blend);
        current.pitch+=(Math.min(PITCH_MAX,Math.max(PITCH_MIN,robot.pitch??0))-current.pitch)*blend;
        sent.current=wrap(current.yaw);
      }
      const pitch=Math.min(PITCH_MAX,Math.max(PITCH_MIN,current.pitch));
      // 小陀螺: Shift spins the chassis; A/D pick the direction, W/S keep driving. The gimbal keeps
      // the commanded world aim, so the crosshair stays on the target while the hull turns. The
      // supercap behind C lets the hull outrun the gimbal a little, which speeds the spin up.
      const spinning=keys.current.has('ShiftLeft')||keys.current.has('ShiftRight');
      // C dumps the supercapacitor into the chassis: a 200 W budget lets the drive and the yaw
      // motors pull the 1800 J buffer instead of the battery.
      const boost=keys.current.has('KeyC')&&(robot.supercap_energy_j??0)>0;
      const spin=spinning?spinRateFor(frameRef.current,robot,boost)*(keys.current.has('KeyA')?1:keys.current.has('KeyD')?-1:1):0;
      // Wheel-legged jump: crouch, let the engine's legs push, then absorb the landing. The phases
      // run on the 20 Hz send tick, which is also the engine's own step.
      const legs=legRangeFor(frameRef.current,robot);
      let legHeight:number|null=null,leap:number|null=null;
      if(legs){
        const phase=jump.current;
        if(phase.stage==='crouch'){
          if(now-phase.at<JUMP_CROUCH_MS)legHeight=legs.min;
          else{jump.current={stage:'air',at:now,seen:false};leap=JUMP_STRENGTH;}
        }else if(phase.stage==='air'){
          // Keep the body at a stable leg extension while airborne so the jump lands level instead of
          // wobbling the hull as the legs cycle through the airtime. The new 50% strength keeps the
          // leap from overpowering the arena while still clearing steps.
          legHeight=legs.nominal;
          if(!robot.grounded)jump.current.seen=true;
          else if(jump.current.seen||now-phase.at>JUMP_TIMEOUT_MS)jump.current={stage:'land',at:now,seen:false};
        }else if(phase.stage==='land'){
          if(now-phase.at<JUMP_LAND_MS)legHeight=legs.min+.03;
          else jump.current={stage:'idle',at:now,seen:false};
        }
      }
      // Trigger discipline: fire only while the next shell still fits. The reserve is one full
      // round plus 15 % headroom, so a shot arriving between two frames cannot tip the barrel over
      // its limit; the server repeats the check against live engine state. A wheel-legged chassis
      // spends Space on its legs instead, so the trigger stays on the mouse.
      // A lobbed shot is also queued: the launcher climbs to the solved elevation over half a
      // second and the server holds the round until it is there, so a tap has to keep asking for
      // that round until it has actually left the barrel.
      const queued=lobShot.current;
      const queuedDone=queued?(robot.ammo<queued.ammo||performance.now()-queued.at>2500):false;
      if(queuedDone)lobShot.current=null;
      const wantsFire=(queued!==null&&!queuedDone)||keys.current.has('MouseLeft')||(!legs&&keys.current.has('Space'));
      const perShot=shotBudgetFor(robot,heatRulesRef.current,String(frameRef.current.season??'2027'),shotHeat.current);
      const reserve=heatReserveFor(perShot,robot.max_heat||0);
      const heatFits=robot.overheated||robot.heat_permanent_lock
        ? false
        : (robot.max_heat||0)<=0||robot.heat+reserve<=robot.max_heat;
      // F: step-climbing mode, held so the legs take each stair of a flight in turn.
      const steer=stepClimbFor(frameRef.current,robot)>0&&keys.current.has('KeyF');
      const action=command(sent.current,pitch,keys.current,spin,{fire:wantsFire&&heatFits,boost,limit:robot.power_limit||100,
        legHeight,jump:leap,climb:steer});
      // A 2027 heavy works with its arm: the pilot picks the ore level and the tool follows the
      // engine's own step sequence, so a human never has to micro-manage five arm axes. Every flag
      // is only read by the branch the attempt is actually on.
      if(robot.role==='heavy'){
        const core=frameRef.current.assemblies?.[robot.team];
        if(core&&['moving','inserting','buffered'].includes(core.stage)){
          action.assembly_insert=true;action.assembly_lift=true;action.assembly_flip=true;
          const first=core.cores?.[0];
          if(first&&Number.isFinite(first.target_rotation))action.assembly_rotate=first.target_rotation;
          if(!core.blocked_reason)action.assembly_confirm=true;
        }
        if(assemblyOrder.current!==null){action.assembly=assemblyOrder.current;assemblyOrder.current=null;}
        if(heavyHold.current.install&&(robot.launcher==='locked'||robot.launcher==='unlocked'||robot.launcher==='installing'))action.install_launcher=true;
        // Taking an ore is a real stop-and-grab: the chassis has to be parked at the dispenser and
        // still, otherwise the arm cannot reach the unit and the engine cancels the grab.
        const spot=resourceSpot(robot,frameRef.current);
        const gap=spot?Math.hypot(robot.x-spot.x,robot.y-spot.y):Infinity;
        const parked=Math.hypot(robot.vx||0,robot.vy||0)<.6;
        if(heavyHold.current.pick&&!robot.weak&&gap<1.45&&parked)action.pick_unit=true;
        const grab=robot.unit_pickup;
        if(grab&&grab.stage==='carrying'){
          const label='夹爪已带 1 个能量单元 · 弹仓 2 个已满 · 开到装配台按 I 直接插入';
          if(label!==pickNotice.current){pickNotice.current=label;setNotice(label);}
        }else if(grab){
          const stage=grab.stage==='approaching'?'对准取矿台':grab.stage==='gripping'?'夹住能量单元':grab.stage==='lifting'?'抬升':grab.stage==='stowing'?'收入弹仓':'取矿';
          const label=`取矿 · ${stage} ${Math.round((grab.progress??0)*100)}% · 保持停稳并按住 I`;
          if(label!==pickNotice.current){pickNotice.current=label;setNotice(label);}
        }else if(pickNotice.current){pickNotice.current='';setNotice('');}
      }
      // Hand the commanded angle to the camera; it is the single source both the eye and the gun use.
      if(!view.current)view.current={yaw:sent.current,pitch};
      else{view.current.yaw=sent.current;view.current.pitch=pitch;}
      // Remote health delivery is also a one-shot order.
      if(heal.current){action.remote_heal=true;heal.current=false;}
      // Keep the ammunition order until the request lands: a refused or dropped POST must not
      // silently swallow the click.
      const order=buy.current;
      if(order){action.buy_ammo={remote:order.remote,amount:order.amount};}
      // Flat-arc gunnery: hand the server the world point under the reticle; it solves the shell's
      // drop and overrides aim/pitch, so the round comes down on that point (the crosshair *is* the
      // impact point). The camera reads the same sight line, because in this mode the lens no longer
      // follows the gun.
      if(lobRef.current&&lobActive(robot)){
        lobScope.yaw=sent.current;lobScope.pitch=pitch;
        const point=lobPoint(robot,frameRef.current,sent.current,pitch);
        const inRange=!!point&&Math.hypot(point[0]-robot.x,point[1]-robot.y)<=LOB_MAX_RANGE;
        if(point&&inRange)action.aim_point=point;
        // Nothing to drop the shell onto (the reticle is on the sky or outside the field) or the
        // point is past the flat arc's reach: a round fired anyway would just fly off and fall
        // short, so the trigger is refused until the crosshair sits on a reachable point.
        else{lobShot.current=null;action.fire=false;}
      }
      inFlight.current=true;
      const body:{team:TeamId;slot:number;action:PilotAction;assist?:string}={team:robot.team,slot:robot.slot,action};
      if(assisted)body.assist=assisted.id;
      const request=post(body);
      pending.current=request;
      try{await request;if(order&&buy.current===order)buy.current=null;}
      catch(error){
        const failure=error as Error&{status?:number};
        // Waiting for the match to boot is not a failure: keep the keys and try again next tick.
        if(failure.status===409&&/准备中/.test(failure.message))setNotice(failure.message);
        // A refused command (an older server rejecting a new field, a rules refusal) must not wipe
        // what the pilot is holding: clearing the keys made the F badge and the throttle flicker.
        else if(failure.status===409||failure.status===422)setNotice(failure.message);
        else onError(failure.message);
      }
      finally{inFlight.current=false;}
    };
    const interactive=(target:EventTarget|null)=>!!(target as HTMLElement|null)?.closest?.('button,select,input,textarea,a,[role="button"]');
    // A change of aim is pushed immediately when nothing is in flight, so the robot starts turning
    // on the same frame instead of waiting for the next 50 ms tick.
    const nudgeNow=(stamp:number)=>{if(releasing.current||inFlight.current||stamp-lastSend.current<NUDGE_MS)return;void send();};
    nudge.current=nudgeNow;
    const onKeyDown=(event:KeyboardEvent)=>{
      if(deadRef.current)return;
      if((event.target as HTMLElement|null)?.closest?.('input,textarea,select,[contenteditable="true"]'))return;
      // A purchase dialog owns the keyboard (Escape closes it, buttons take the mouse).
      if(storeRef.current)return;
      if(INPUT_REPEAT_BLOCK.has(event.code) && event.repeat){return;}
      if(HELD_KEYS.includes(event.code))event.preventDefault();
      // I on a 2027 heavy robot is the arm work key: hold it at your own resource station to grab a
      // core, press it at the assembly plinth to choose the ore level. The 42 mm launcher is fitted
      // with J, and O is the ammunition purchase for every robot, heavy included.
      if(event.code==='KeyI'&&!event.repeat&&robotRef.current){
        const robot=robotRef.current;
        if(robot.role==='heavy'){
          if(!robot.alive)return;
          const zones=robot.last_raw_zones??[];
          const spot=resourceSpot(robot,frameRef.current);
          const gap=spot?Math.hypot(robot.x-spot.x,robot.y-spot.y):Infinity;
          if(zones.includes(`${robot.team}_resource`)&&unitsOnBoard(robot)<3){
            // Alignment is the pilot's job: park at the dispenser, facing it, then hold I.
            const facing=spot?Math.abs(shortest(Math.atan2(spot.dir[1],spot.dir[0]),robot.heading)):0;
            if(gap>1.45){setNotice(`离取矿台还有 ${gap.toFixed(1)} m：开到取矿台边再按住 I`);return;}
            if(Math.hypot(robot.vx||0,robot.vy||0)>=.6){setNotice('先把机体停稳，再按住 I 取矿');return;}
            heavyHold.current.pick=true;
            setNotice(facing>Math.PI/3?'按住 I 取矿中：车头没有正对取矿口，机械臂可能要绕很远':'按住 I 取矿：机械臂对准能量单元后会自动夹取');
            nudgeNow(performance.now());
            return;
          }
          // J holds the launcher installation at the workbench; I keeps the arm work (mining, ore board).
          // The board is where the launcher note lives, so I never tries to install from a distance.
          // The order board opens anywhere so the levels and their rewards can be read; the engine
          // only accepts the order inside the assembly zone, which the board refuses up front.
          document.exitPointerLock?.();
          keys.current.clear();
          setAssembly(true);
          return;
        }
      }
      // J: a 2027 heavy fits its 42 mm launcher at the team workbench — hold it while the installer
      // runs. Once the module is on, J does nothing and H is the remote delivery for everyone.
      if(event.code==='KeyJ'&&!event.repeat&&robotRef.current){
        const robot=robotRef.current;
        if(robot.role!=='heavy'||!robot.alive)return;
        // The module can be bolted on at any point in the match; the rules' unlock only decides when it
        // may actually shoot.
        if(robot.launcher==='fitted'||robot.launcher==='installed'){
          setNotice('42 mm 发射机构已经装好');
          return;
        }
        heavyHold.current.install=true;
        setNotice((robot.last_raw_zones??[]).includes(`${robot.team}_workbench`)
          ?'安装 42 mm 发射机构：留在工位内按住 J'
          :'需停在己方工位（workbench）内按住 J 才能安装发射机构');
        nudgeNow(performance.now());
        return;
      }
      // R: lobbed fire. A heavy with its 42 mm on flips up a 3× sight; the crosshair then marks the
      // impact point and the server solves the high arc for it.
      if(event.code==='KeyR'&&!event.repeat&&robotRef.current){
        const robot=robotRef.current;
        if(!lobActive(robot)){
          setNotice(robot.role==='heavy'?'吊射模式需要先装好 42 mm 发射机构':'吊射模式只在重装机器人上可用');
          return;
        }
        document.exitPointerLock?.();
        setLobMode(!lobRef.current);
        requestAnimationFrame(()=>requestLock(setNotice));
        return;
      }
      // O: local purchase dialog, only on a supply pad, high point or fully controlled outpost.
      if(event.code==='KeyO'&&!event.repeat&&robotRef.current){
        const robot=robotRef.current;
        if(!robot.alive)return;
        if(!ammoKind(robot)){setNotice('该型号不通过补给购买弹药');return;}
        if(robot.weak){setNotice('虚弱状态不能购买：先到补给区或已完全控制的前哨站增益点解除虚弱');return;}
        if(!inSupply(robot,frameRef.current)){
          setNotice('需在己方补给区、制高点或完全控制的前哨站内购买；远程购买请按 H');
          return;
        }
        document.exitPointerLock?.();
        keys.current.clear();
        const kind=ammoKind(robot) as '17mm'|'42mm';
        const price=ammoPrices(economyRef.current,String(frameRef.current.season??'2027'),kind);
        setStore({mode:'local',tab:'ammo',amount:price.local.batch,batches:1});
        return;
      }
      // H: remote store — ammunition or a health delivery, both six seconds after disengaging.
      if(event.code==='KeyH'&&!event.repeat&&robotRef.current){
        const robot=robotRef.current;
        if(!robot.alive){setNotice('阵亡状态不能远程购买');return;}
        document.exitPointerLock?.();
        keys.current.clear();
        const kind=ammoKind(robot) as '17mm'|'42mm'|null;
        const price=kind?ammoPrices(economyRef.current,String(frameRef.current.season??'2027'),kind):null;
        setStore({mode:'remote',tab:price?'ammo':'heal',amount:price?price.remote.batch:0,batches:1});
        return;
      }
      // Space is the jump of a wheel-legged chassis; everywhere else it stays the trigger.
      if(event.code==='Space'&&legRangeFor(frameRef.current,robotRef.current)){
        if(!event.repeat&&jump.current.stage==='idle')jump.current={stage:'crouch',at:performance.now(),seen:false};
        nudgeNow(performance.now());
        return;
      }
      // Ignore synthetic repeat presses for movement and aim keys; they are already represented by the
      // current Set state. This prevents stray keydown bursts from injecting random steering input.
      if(event.repeat && /^(KeyW|KeyA|KeyS|KeyD|ArrowLeft|ArrowRight|ArrowUp|ArrowDown|ShiftLeft|ShiftRight|KeyC|KeyX|MouseLeft|MouseRight)$/.test(event.code))return;
      keys.current.add(event.code);
      if(event.code==='KeyF')setClimbHeld(true);
      nudgeNow(performance.now());
    };
    const onKeyUp=(event:KeyboardEvent)=>{
      keys.current.delete(event.code);
      if(event.code==='KeyF')setClimbHeld(false);
      if(event.code==='KeyI')heavyHold.current.pick=false;
      if(event.code==='KeyJ')heavyHold.current.install=false;
      if(event.code==='ArrowLeft'||event.code==='ArrowRight'||event.code==='ArrowUp'||event.code==='ArrowDown')held.current=0;
      // Release is pushed at once too: waiting for the next tick would keep the wheels pushing
      // (or the brake off) for another 50 ms, which is exactly what made stopping feel long.
      nudgeNow(performance.now());
    };
    const onMove=(event:PointerEvent)=>{
      const current=input.current;
      // Nothing steers before the countdown ends or while the chassis is destroyed: the pointer is
      // the browser's in both cases.
      if(!current||!runningRef.current||deadRef.current||openRef.current||(!event.movementX&&!event.movementY))return;
      // With pointer lock the events target the locked canvas. Without it the pointer may sit
      // over the HUD or the cockpit panel, so only interactive controls stop the aiming.
      if(!document.pointerLockElement&&interactive(event.target))return;
      // Pointer lock reports raw deltas that some mice scale up on fast flicks; clamping keeps a
      // single event from throwing the turret across the field.
      const dx=Math.max(-220,Math.min(220,event.movementX)),dy=Math.max(-220,Math.min(220,event.movementY));
      // A magnified sight turns slower by the same factor the lens is narrowed, so the reticle keeps
      // tracking the target instead of overshooting it.
      const zoom=lobRef.current?1/LOB_SCALE:1;
      current.yaw+=dx*YAW_SENSITIVITY*zoom;
      current.pitch=Math.min(PITCH_MAX,Math.max(PITCH_MIN,current.pitch-dy*PITCH_SENSITIVITY*zoom));
      nudgeNow(performance.now());
    };
    const onDown=(event:MouseEvent)=>{
      // The right button is the aim assist and the middle one would start autoscroll, so neither
      // may reach the browser — even when the pointer happens to sit over a HUD chip.
      if(event.button===1||event.button===2)event.preventDefault();
      if(deadRef.current||interactive(event.target))return;
      if(event.button===0){keys.current.add('MouseLeft');if(lobRef.current)lobShot.current={ammo:robotRef.current?.ammo??0,at:performance.now()};nudgeNow(performance.now());}
      if(event.button===2){keys.current.add('MouseRight');nudgeNow(performance.now());}
    };
    const onUp=(event:MouseEvent)=>{
      if(event.button===0){keys.current.delete('MouseLeft');nudgeNow(performance.now());}
      if(event.button===2){keys.current.delete('MouseRight');nudgeNow(performance.now());}
    };
    const onContext=(event:MouseEvent)=>event.preventDefault();
    const onBlur=()=>{keys.current.clear();setClimbHeld(false);};
    // The lock may sit on the canvas rather than the viewport, so any locked element counts.
    const onLockChange=()=>{quietLock.current=false;setLocked(!!document.pointerLockElement);};
    // The panel needs a free cursor, so nothing grabs the pointer back while it is open, and the
    // prep phase and a dead chassis keep it free as well.
    const relock=()=>{if(!openRef.current&&runningRef.current&&!deadRef.current)requestLock(setNotice);};
    // Automatic grabs (after the countdown, after a respawn) cannot carry a user gesture, so their
    // refusal stays quiet: the "click to lock" hint is guidance enough.
    const onLockError=()=>{if(quietLock.current){quietLock.current=false;return;}setNotice('此环境不允许锁定鼠标：在画面内移动鼠标即可转向（或用方向键）');};
    window.addEventListener('keydown',onKeyDown);
    window.addEventListener('keyup',onKeyUp);
    window.addEventListener('blur',onBlur);
    document.addEventListener('pointerlockchange',onLockChange);
    document.addEventListener('pointerlockerror',onLockError);
    document.addEventListener('pointermove',onMove);
    document.addEventListener('mousedown',onDown);
    document.addEventListener('mouseup',onUp);
    document.addEventListener('contextmenu',onContext);
    // A press anywhere in the field takes the pointer back; the panel's own controls never do.
    // Where the host refuses pointer lock, capturing the pointer keeps the drag feeding the
    // view even when the cursor leaves the field.
    const onPress=(event:PointerEvent)=>{
      if(openRef.current||!runningRef.current||deadRef.current||interactive(event.target))return;
      if(!document.pointerLockElement){
        captured.current=event.pointerId;
        try{surface?.setPointerCapture(event.pointerId);}catch{/* capture is a bonus, not a need */}
      }
      relock();
    };
    const onReleaseCapture=(event:PointerEvent)=>{
      captured.current=null;
      try{surface?.releasePointerCapture(event.pointerId);}catch{}
    };
    surface?.addEventListener('click',relock);
    surface?.addEventListener('pointerdown',onPress);
    surface?.addEventListener('pointerup',onReleaseCapture);
    surface?.addEventListener('pointercancel',onReleaseCapture);
    void send();
    const timer=window.setInterval(()=>void send(),SEND_MS);
    return()=>{
      window.clearInterval(timer);
      window.removeEventListener('keydown',onKeyDown);
      window.removeEventListener('keyup',onKeyUp);
      window.removeEventListener('blur',onBlur);
      document.removeEventListener('pointerlockchange',onLockChange);
      document.removeEventListener('pointerlockerror',onLockError);
      document.removeEventListener('pointermove',onMove);
      document.removeEventListener('mousedown',onDown);
      document.removeEventListener('mouseup',onUp);
      document.removeEventListener('contextmenu',onContext);
      surface?.removeEventListener('click',relock);
      surface?.removeEventListener('pointerdown',onPress);
      surface?.removeEventListener('pointerup',onReleaseCapture);
      surface?.removeEventListener('pointercancel',onReleaseCapture);
      if(document.pointerLockElement)document.exitPointerLock();
      keys.current.clear();
      setLocked(false);
      setClimbHeld(false);
      heavyHold.current={pick:false,install:false};
      assemblyOrder.current=null;
      // Leaving the cockpit drops the magnified sight; the next pilot starts on the plain lens.
      lobRef.current=false;
      lobScope.active=false;lobScope.sight=0;
      nudge.current=null;
      held.current=0;
      jump.current={stage:'idle',at:0,seen:false};
      input.current=null;
      view.current=null;
    };
  },[activeId,view,onError]);

  // P opens the cockpit anywhere in the arena, so a pilot can be engaged without hunting for a button.
  // The panel needs a usable cursor, so opening it hands the mouse back to the browser.
  useEffect(()=>{
    const onKey=(event:KeyboardEvent)=>{
      if((event.target as HTMLElement|null)?.closest?.('input,textarea,select,[contenteditable="true"]'))return;
      if(event.code==='KeyP'&&!event.repeat){
        if(storeRef.current)return;
        event.preventDefault();
        const opening=!openRef.current;
        // The panel needs a usable cursor: hand the pointer back to the browser (no-op if free).
        if(opening)document.exitPointerLock?.();
        onOpen(opening);
        // Closing the panel hands the mouse back to the cockpit, so the pilot can aim again
        // without clicking the view first (a key press is a user gesture, so the lock is allowed).
        if(!opening&&robotRef.current)requestLock(setNotice);
      }
      else if(event.code==='Escape'){
        if(storeRef.current){
          event.preventDefault();
          setStore(null);
          if(robotRef.current)requestLock(setNotice);
        }else if(assemblyRef.current){
          event.preventDefault();
          setAssembly(false);
          if(robotRef.current)requestLock(setNotice);
        }else if(openRef.current)onOpen(false);
      }
    };
    window.addEventListener('keydown',onKey);
    return()=>window.removeEventListener('keydown',onKey);
  },[onOpen]);

  // The cockpit owns the cursor only while it is actually driving: opening a dialog hands the
  // pointer (and any capture) back to the browser so its controls can be clicked, and closing it
  // hides the cursor again for aiming.
  useEffect(()=>{
    const surface=document.querySelector('#viewport') as HTMLElement|null;
    // Only a live, running engagement owns the cursor: the prep phase and a destroyed chassis
    // keep it free so the pointer can be used for clicks.
    const driving=!!activeId&&!modal&&running&&!dead;
    if(!driving){
      if(captured.current!==null){
        try{surface?.releasePointerCapture(captured.current);}catch{/* already released */}
        captured.current=null;
      }
      if(document.pointerLockElement)document.exitPointerLock?.();
    }
    document.body.classList.toggle('pilot-cursor-hidden',driving);
  },[activeId,modal,running,dead]);
  useEffect(()=>()=>{document.body.classList.remove('pilot-cursor-hidden');},[]);

  // The pointer is taken only once the prep phase is over, and handed back while destroyed. Both
  // transitions try without a user gesture: if the browser refuses, the "click to lock" hint stays.
  useEffect(()=>{
    if(!activeId||!running||modal||dead)return;
    if(!document.pointerLockElement&&armed.current){
      quietLock.current=true;
      requestLock(()=>{quietLock.current=false;});
    }
  },[activeId,running,modal,dead]);
  useEffect(()=>{
    if(!activeId)return;
    if(dead){
      if(document.pointerLockElement){
        armed.current=true;
        document.exitPointerLock?.();
        setLocked(false);
      }
      wasDead.current=true;
    }else if(wasDead.current){
      wasDead.current=false;
      if(armed.current){
        quietLock.current=true;
        requestLock(()=>{quietLock.current=false;});
      }
    }
  },[dead,activeId]);

  function engage(id?:string){
    const chosen=id?frame.robots.find(r=>r.id===id)??null:target;
    if(!chosen||piloted||frame.status==='finished')return;
    const aim={yaw:chosen.aim??chosen.heading,pitch:Math.min(PITCH_MAX,Math.max(PITCH_MIN,chosen.pitch??0))};
    input.current={...aim};
    view.current={...aim};
    onEngage(chosen.id);
    onOpen(false);
    setStore(null);
    armed.current=true;
    // During the prep phase the pointer stays free; the effect above grabs it when play starts.
    if(running)requestLock(setNotice);
    else setNotice('准备阶段结束后自动锁定鼠标，可先用鼠标或方向键转云台');
  }

  async function release(){
    if(!piloted||releasing.current)return;
    releasing.current=true;
    setStore(null);
    keys.current.clear();
    // Stop the stream immediately, then let the last command land before handing the robot back,
    // so a held trigger cannot outlive the exit.
    input.current=null;
    view.current=null;
    lobRef.current=false;
    lobScope.active=false;
    lobScope.sight=0;
    await pending.current?.catch(()=>undefined);
    try{await post({team:piloted.team,slot:piloted.slot,action:null});}catch{/* the match may already be over */}
    onRelease();
  }

  // Read straight off the key set: the HUD already re-renders with every frame, so the badge
  // appears within one tick of the key being pressed.
  const spinKeys=keys.current;
  const spinning=!!piloted&&!dead&&(spinKeys.has('ShiftLeft')||spinKeys.has('ShiftRight'));
  const spinDir=spinKeys.has('KeyA')?'逆时针':spinKeys.has('KeyD')?'顺时针':'逆时针';
  const boostActive=!!piloted&&!dead&&spinKeys.has('KeyC')&&(piloted.supercap_energy_j??0)>0;
  const jumping=!!piloted&&!dead&&jump.current.stage!=='idle';
  const legsFor=legRangeFor(frame,piloted);
  // F holds the step-climbing mode of a stair-climbing wheel-legged chassis. The engine's step
  // event keeps the badge lit for a moment, so releasing or re-pressing the key never blinks it.
  const climbMode=!!piloted&&!dead&&stepClimbFor(frame,piloted)>0;
  const stepActive=performance.now()-climbPulse<900;
  const climbing=climbMode&&(climbHeld||stepActive);
  // The trigger, read live so the heat warning only shows while a shot is actually being held back.
  const triggerHeld=spinKeys.has('MouseLeft')||(!legsFor&&spinKeys.has('Space'));
  // Team gold funds ammunition orders; a team starts a match with none.
  const teamState=frame.teams?.[piloted?.team??'red'] as {resources?:number;purchased_42?:number;purchased_17?:number}|undefined;
  const gold=Number(teamState?.resources??0);
  const storeKind=ammoKind(piloted);
  const storeSeason=String(frame.season??'2027');
  const storePrices=storeKind?ammoPrices(economy,storeSeason,storeKind):null;
  const purchased=Number((storeKind==='42mm'?teamState?.purchased_42:teamState?.purchased_17)??0);
  const localMax=storePrices?Math.max(0,Math.min(storePrices.local.cap-purchased,Math.floor(gold/storePrices.local.cost*storePrices.local.batch))):0;
  const remoteMaxBatches=storePrices?Math.max(0,Math.min(Math.floor((storePrices.remote.cap-purchased)/storePrices.remote.batch),Math.floor(gold/storePrices.remote.cost))):0;
  const localPrice=storePrices&&store&&store.mode==='local'?Math.round(store.amount/storePrices.local.batch*storePrices.local.cost):0;
  const remoteShots=storePrices&&store?store.batches*storePrices.remote.batch:0;
  const remotePrice=storePrices&&store?store.batches*storePrices.remote.cost:0;
  const healCost=remoteHealCostFor(frame);
  const disengage=disengageWait(frame,piloted);
  const reviveCost=reviveCostFor(frame,piloted);
  const localSteps=storeKind==='42mm'?[10,5,1]:[50,10,5,1];
  // 2027 assembly orders: the rulebook unlocks one more level per minute of match time, each level
  // needs the previous one finished, level 4 only ever completes once, and the arm must carry a
  // core (two for the borrowed-core level).
  const heavy=!!piloted&&piloted.role==='heavy';
  const atAssembly=!!piloted&&(piloted.last_raw_zones??[]).includes(`${piloted.team}_assembly`);
  const coreState=piloted?frame.assemblies?.[piloted.team]:null;
  const completed:number[]=((frame.teams?.[piloted?.team??'red'] as {completed_difficulties?:number[]}|undefined)?.completed_difficulties)??[];
  const assemblyLevels=[1,2,3,4].map(level=>{
    const unlockAt=(level-1)*60,carry=level===4?2:1;
    const waiting=Math.max(0,Math.ceil(unlockAt-(frame.time??0)));
    const busy=!!coreState&&!['idle','complete','failed'].includes(coreState.stage);
    const reason=!atAssembly?'需停在己方装配区（兑矿台）内下达装配'
      :level===4&&completed.includes(4)?'四级装配本场只能完成一次'
      :waiting>0?`比赛开始 ${unlockAt/60} 分钟后解锁（还差 ${waiting} 秒）`
      :!completed.includes(level)&&level>1&&!completed.includes(level-1)?`需先完成 ${level-1} 级装配`
      :unitsOnBoard(piloted)<carry?`需要携带 ${carry} 个能量单元（当前 ${unitsOnBoard(piloted)}；夹爪可夹 1 个）`
      :busy?`${coreState?.difficulty??1} 级装配进行中`
      :completed.includes(level)?'已完成 · 可再次装配（非首次收益）':'可装配';
    const ready=reason==='可装配'||reason.startsWith('已完成');
    return {level,ready,reason,first:!completed.includes(level)};
  });
  const rewards:Record<number,string>={
    1:'首次：重装机器人升至 5 级，此后每 10 秒 +40 金币；非首次：每 10 秒额外 +4 金币',
    2:'首次：升至 7 级，等级上限 5 → 7，每 10 秒额外 +20 金币；非首次：每 10 秒额外 +8 金币',
    3:'首次：升至 10 级，全队地面机器人 / 前哨站 / 基地 +25% 防御，解锁 42 mm 发射机构，等级上限 → 10，每 10 秒额外 +20 金币；非首次：每 10 秒额外 +12 金币',
    4:'首次：全队 +50% 防御，每 10 秒额外 +40 金币（本场仅一次）',
  };
  // The rules' unlock decides when the 42 mm may shoot (difficulty 3, or 300 - M/50 - 2N/3 seconds);
  // bolting the module on is allowed at any time.
  const teamLauncherUnlocked=piloted?((frame.teams[piloted.team]?.completed_difficulties??[]).includes(3)
    || (frame.time??0)+1e-8>=(frame.teams[piloted.team]?.launcher_unlock_s??0)):false;
  const launcherNote=piloted&&piloted.role==='heavy'
    ?(piloted.launcher==='installed'?'42 mm 发射机构已安装 · H 是远程补给'
      :piloted.launcher==='fitted'?(teamLauncherUnlocked?'42mm 未最终确认 · 开一枪即定装':'42mm 已装好 · 解锁后才能发射')
      :piloted.launcher==='installing'?'正在安装 42 mm 发射机构：留在工位内按住 J'
      :piloted.launcher==='unlocked'?'42 mm 已解锁：开到己方工位按住 J 安装'
      :'42 mm 可随时提前安装 · 解锁后才能发射')
    :'';

  function closeAssembly(){
    setAssembly(false);
    if(robotRef.current)requestLock(setNotice);
  }

  function orderAssembly(level:number){
    assemblyOrder.current=level;
    setAssembly(false);
    setNotice(`${level} 级装配已下达：机械臂自动执行，第一人称跟随机械臂视角`);
    nudge.current?.(performance.now());
    if(robotRef.current)requestLock(setNotice);
  }

  function closeStore(){
    setStore(null);
    if(robotRef.current)requestLock(setNotice);
  }

  // A heavy robot buys 42 mm ammunition at the supply pad like everyone else: O opens the ordinary
  // purchase dialog; the ore board only appears behind I, at the assembly plinth.
  function openLocalStore(){
    if(!piloted)return;
    const kind=ammoKind(piloted);
    if(!kind||!inSupply(piloted,frame))return;
    const price=ammoPrices(economyRef.current,String(frame.season??'2027'),kind);
    setAssembly(false);
    setStore({mode:'local',tab:'ammo',amount:price.local.batch,batches:1});
  }

  function adjustStore(delta:number){
    setStore(s=>{
      if(!s)return s;
      if(s.mode==='local')return {...s,amount:Math.max(0,Math.min(localMax,s.amount+delta))};
      const top=Math.max(1,remoteMaxBatches);
      return {...s,batches:Math.max(1,Math.min(top,s.batches+delta))};
    });
  }

  function placeAmmo(remote:boolean,amount:number){
    if(!piloted||!storePrices)return;
    buy.current={remote,amount};
    const rule=remote?storePrices.remote:storePrices.local;
    const cost=Math.round(amount/rule.batch*rule.cost);
    const stamp=performance.now();
    buyPending.current=stamp;
    setNotice(remote?`远程下单 ${amount} 发 · ${cost} 金币 · 6 秒后送达`:`补给区下单 ${amount} 发 · ${cost} 金币 · 立即补弹`);
    window.setTimeout(()=>{
      if(buyPending.current!==stamp)return;
      buyPending.current=0;
      const team=frameRef.current.teams?.[piloted.team] as {resources?:number;purchased_42?:number;purchased_17?:number}|undefined;
      const kind=ammoKind(piloted);
      const bought=Number((kind==='42mm'?team?.purchased_42:team?.purchased_17)??0)-purchased;
      if(bought>0)setNotice(`+${bought} 发 · ${Math.round(gold-Number(team?.resources??gold))} 金币${remote?'（远程，6 秒送达）':'（补给区）'}`);
      else setNotice('下单未生效：请查看服务端返回的原因');
    },1600);
  }

  function confirmStore(){
    if(!store||!piloted)return;
    if(store.mode==='local'){
      if(store.amount<=0||!storePrices)return;
      placeAmmo(false,store.amount);
    }else if(store.tab==='ammo'){
      if(remoteShots<=0||!storePrices)return;
      placeAmmo(true,remoteShots);
    }else{
      heal.current=true;
      setNotice(`远程兑换血量 · ${healCost} 金币 · 6 秒后送达（期间阵亡则失效且不退款）`);
    }
    closeStore();
  }

  function buyRevive(){
    if(!piloted)return;
    if(gold<reviveCost){setNotice(`金币不足：立即复活需 ${reviveCost} 金币（现有 ${Math.round(gold)}）`);return;}
    revive.current=true;
    setNotice(`立即复活 · ${reviveCost} 金币 · 保留等级与经验`);
  }

  // Range to the point under the reticle, shown next to the scope: the pilot aims by distance, and
  // the flat arc only reaches about 21 m, so the scope has to say when the crosshair is too far.
  const lobRange=lob&&piloted&&lobActive(piloted)
    ?(()=>{const p=lobPoint(piloted,frame,view.current?.yaw??piloted.aim??0,view.current?.pitch??0);
        return p?Math.hypot(p[0]-piloted.x,p[1]-piloted.y):null;})()
    :null;
  const lobReach=lobRange===null?' · 无落点（准星压在地面或装甲板上）'
    :lobRange>LOB_MAX_RANGE?' · 超出射程（42 mm 平射约 21 m）'
    :` · ${lobRange.toFixed(0)} m`;

  return <>
    {piloted&&<>
      {lob&&!dead&&<div className="pilot-scope" aria-label="吊射机械瞄具">
        {/* The tube is modelled in 3D and the lens pass in `sight.tsx` magnifies its bore; the cross
            itself is UI, so it stays a one-pixel hairline at any resolution and any magnification. */}
        <div className="pilot-lob-cross" aria-hidden="true">
          <svg viewBox="0 0 200 200">
            <g className="lob-shadow">
              <line x1="100" y1="6" x2="100" y2="88" vectorEffect="non-scaling-stroke"/>
              <line x1="100" y1="112" x2="100" y2="194" vectorEffect="non-scaling-stroke"/>
              <line x1="6" y1="100" x2="88" y2="100" vectorEffect="non-scaling-stroke"/>
              <line x1="112" y1="100" x2="194" y2="100" vectorEffect="non-scaling-stroke"/>
            </g>
            <g className="lob-line">
              <line x1="100" y1="6" x2="100" y2="88" vectorEffect="non-scaling-stroke"/>
              <line x1="100" y1="112" x2="100" y2="194" vectorEffect="non-scaling-stroke"/>
              <line x1="6" y1="100" x2="88" y2="100" vectorEffect="non-scaling-stroke"/>
              <line x1="112" y1="100" x2="194" y2="100" vectorEffect="non-scaling-stroke"/>
            </g>
            <circle className="lob-dot" cx="100" cy="100" r="1.3"/>
          </svg>
        </div>
        <div className="pilot-scope-label">吊射 · 2.5× 镜内放大 · 准星即落点{lobReach}{lobShot.current?' · 抬炮中，到位自动发射':''}</div>
      </div>}
      <AimRing robot={piloted} heatBlocked={heatBlocked}/>
      <Vitals robot={piloted} thresholds={thresholds} capNominal={supercapNominal} gold={gold}/>
      {hitTick>0&&<div key={hitTick} className="pilot-hit" aria-hidden="true"/>}
      <div className="pilot-status">
        {lockInfo&&!dead&&<div className="pilot-lock">
          <i className="bracket"/><span>锁定 {lockLabel(lockInfo.id,lockInfo.side)}</span><em>{lockInfo.distance.toFixed(1)} m</em>
        </div>}
        {spinning&&<div className="pilot-spin"><i/>{`小陀螺 · ${spinDir} · ${spinRateFor(frame,piloted,boostActive).toFixed(1)} rad/s${boostActive?' · 超电加速':''}`}</div>}
        {boostActive&&<div className="pilot-boost"><i/>超电输出 · 200 W · {Math.round(piloted.supercap_energy_j??0)} J</div>}
        {jumping&&<div className="pilot-jump"><i/>{jump.current.stage==='crouch'?'下蹲蓄力':jump.current.stage==='air'?'腾空':'落地缓冲'}</div>}
        {climbing&&!jumping&&<div className="pilot-jump"><i/>登阶模式 · 抵住台阶自动抬腿上台阶</div>}
        {lob&&!dead&&<div className="pilot-lob"><i/>吊射 · 瞄具已翻到眼前 · R 翻回</div>}
        {heatLocked&&!dead&&<div className="pilot-heatlock">枪管过热 · 冷却中</div>}
        {heatBlocked&&!heatLocked&&!dead&&triggerHeld&&<div className="pilot-heatlock">热量保护 · 暂停射击</div>}
      </div>
      {!locked&&!dead&&!open&&<div className="pilot-grab">鼠标未锁定 · 点击画面锁定（或直接移动鼠标转向）</div>}
      {notice&&<div className="pilot-notice"><i/>{notice}</div>}
      {dead&&<div className="pilot-respawn" role="status" aria-label="等待复活">
        <strong>已阵亡</strong>
        <div className="respawn-bar"><i style={{width:`${respawnShare*100}%`}}/></div>
        <span>{respawnLeft>0?`免费复活倒计时 ${respawnLeft}s`:'正在返场…'}</span>
        <button className="pilot-revive" disabled={gold<reviveCost} onClick={buyRevive}>立即复活 · {reviveCost} 金币</button>
        <small>免费复活：读条结束后自动复活 · 立即复活：保留等级与经验，3 秒虚弱与无敌，功率上限翻倍 4 秒</small>
      </div>}
    </>}
    {!piloted&&!open&&<button className="pilot-open" onClick={()=>onOpen(true)} aria-label="打开第一视角驾驶面板"><Gamepad2 size={14}/>驾驶菜单<kbd>P</kbd></button>}
    {open&&<>
      {/* While Link Start scans the field the panel is docked to the right and the field itself is
          the picker, so the backdrop that would swallow every canvas click is left out. */}
      {!link&&<div className="pilot-backdrop" onClick={()=>onOpen(false)}/>}
      <div className={`pilot-panel ${!piloted&&link?`pilot-link team-${team}`:''}`} role="dialog" aria-label={!piloted&&link?'选择机体':'第一视角驾驶'}>
        <div className="pilot-heading"><Gamepad2 size={14}/><span>{!piloted&&link?'LINK START':'第一视角驾驶'}</span><em>{piloted?`${paused?'已暂停':'接管中'} · ${piloted.team==='red'?'红':'蓝'}方 ${piloted.slot} 号`:link?'俯视选机 · 点击机体':'P 打开/关闭'}</em><button className="pilot-x" onClick={()=>onOpen(false)} aria-label="关闭面板"><span className="pilot-x-glyph" aria-hidden="true">✕</span></button></div>
        {!piloted?(link?<div className="pilot-roster-wrap">
          {!seat&&<div className="pilot-team-switch" role="group" aria-label="阵营">
            {(['red','blue'] as const).map(side=><button key={side} className={team===side?'active':''} style={{'--team':TEAM_COLORS[side]} as CSSProperties} onClick={()=>setTeam(side)}>{side==='red'?'红方':'蓝方'} · {frame.robots.filter(r=>r.team===side&&r.role!=='aerial').length} 台</button>)}
          </div>}
          <div className="pilot-roster" role="group" aria-label="选择机体">
            {roster.map(r=><button key={r.id} className={`pilot-roster-row ${r.alive?'':'dead'}`} onClick={()=>onLinkPick?.(r.id)} aria-label={`${r.team==='red'?'红':'蓝'}方${r.slot}号${ROLE_NAMES[r.role]}${r.alive?'':' · 已阵亡'}`}>
              <b>{String(r.slot).padStart(2,'0')}</b>
              <span>{ROLE_NAMES[r.role]}</span>
              <i><s style={{width:`${r.max_hp>0?Math.max(0,Math.min(100,r.hp/r.max_hp*100)):0}%`}}/></i>
              <em>{Math.ceil(Math.max(0,r.hp))}</em>
            </button>)}
          </div>
          <p className="pilot-link-tip">悬停战场上的机体：镜头俯冲到该机体（约占画面 30%）并显示详细参数，点击机体建立连接。</p>
          <button className="link-back" onClick={()=>onLink?.(false)}><X size={13}/>返回</button>
        </div>:<div className="pilot-setup">
          <button className="pilot-link-start" onClick={()=>onLink?.(true)} aria-label="Link Start 选择机体">
            <span className="pls-glow" aria-hidden="true"/>
            <PlugZap size={17}/>
            <b>LINK START</b>
            <small>建立神经连接 · 俯视选机</small>
          </button>
          {camera&&onCamera&&<div className="pilot-panel-camera" aria-label="镜头模式">
            <CameraControls compact mode={camera} onChange={onCamera}/>
          </div>}
          {onFullscreen&&<button className="pilot-setup-act" onClick={onFullscreen} title={fullscreen?'退出全屏 (F / Esc)':'全屏观战 (F)'}>{fullscreen?<Minimize2 size={13}/>:<Maximize2 size={13}/>}{fullscreen?'退出全屏':'全屏观战'}</button>}
          <p className="pilot-hints">点击 LINK START 后视角切到俯视，鼠标靠近机体即可查看参数，点选机体确认后直接切入第一人称。空中机器人由自动飞行系统控制，不可手动驾驶。</p>
        </div>):<div className="pilot-readouts">
          <span><b>HP</b>{Math.max(0,Math.ceil(piloted.hp))}<small>/{Math.ceil(piloted.max_hp)}</small></span>
          <span><b>弹量</b>{piloted.ammo}</span>
          <span className={piloted.overheated?'hot':''}><b>热量</b>{Math.round(piloted.heat)}<small>/{Math.round(piloted.max_heat)}</small></span>
          <span><b>速度</b>{Math.hypot(piloted.vx,piloted.vy).toFixed(1)}<small>m/s</small></span>
          <span><b>金币</b>{Math.round(frame.teams[piloted.team]?.resources??0)}</span>
          <span><b>位置</b>{inSupply(piloted,frame)?'补给区':'野外'}</span>
          {legsFor&&<span><b>腿长</b>{(piloted.legs?.[0]??0).toFixed(2)}<small>m · 空格跳跃</small></span>}
        </div>}
        {piloted&&<div className="pilot-actions">
          <button className="pilot-act-resume" onClick={()=>{onOpen(false);requestLock(setNotice);}}><RotateCcw size={13}/>继续操控</button>
          {onFullscreen&&<button className="pilot-act-fullscreen" onClick={onFullscreen} title={fullscreen?'退出全屏 (F / Esc)':'全屏观战 (F)'}>{fullscreen?<Minimize2 size={13}/>:<Maximize2 size={13}/>}{fullscreen?'退出全屏':'全屏'}</button>}
          {onPause&&canPause&&<button className="pilot-act-pause" onClick={onPause}>{paused?'继续比赛':'暂停比赛'}</button>}
          <button className="pilot-act-exit" onClick={()=>void release()}><X size={13}/>退出驾驶</button>
        </div>}
        {piloted&&<>
          <div className="pilot-hints-title">驾驶小则</div>
          <p className="pilot-hints">鼠标/方向键 转云台 · 右键按住 自动瞄准：锁定离准星最近的装甲板（机器人、前哨站、基地）· <b>O 补给区购买弹药</b>· <b>H 远程补给</b>（远程需脱离交战 6 秒）{heavy?<>{' · '}<b>I 重装：矿区取矿 · 装配区选装配难度</b>{' · '}<b>J 工位内按住安装 42 mm 发射机构</b>{' · '}<b>R 吊射 3× 镜（装好 42 mm 后，准星即落点）</b></>:null} · WASD 移动（松开自动刹车）· 左键 开火（热量接近上限时自动停火保护枪管）{legsFor?' · 空格 跳跃（下蹲 0.3 s，落地缓冲 0.5 s）':' · 空格 开火'}{climbMode?' · F 按住登阶（抵住台阶自动抬腿）':''} · <b>Shift 小陀螺自旋</b>（A/D 定方向）· <b>C 超电输出</b>（200 W，同时加快自旋）· X 刹车 · P 关闭面板即继续操控并重新锁定鼠标</p>
        </>}
      </div>
    </>}
    {assembly&&<>
      <div className="pilot-backdrop" onClick={closeAssembly}/>
      <div className="pilot-panel pilot-store pilot-assembly" role="dialog" aria-label="选择装配难度">
        <div className="pilot-heading"><Layers size={14}/><span>兑矿 / 装配难度</span><em>{piloted?`重装 · ${piloted.team==='red'?'红':'蓝'}方 ${piloted.slot} 号 · 携带 ${unitsOnBoard(piloted)} 个能量单元${piloted.unit_pickup?.stage==='carrying'?'（含夹爪 1 个）':''}`:'未接管'}</em><button className="pilot-x" onClick={closeAssembly} aria-label="关闭装配"><span className="pilot-x-glyph" aria-hidden="true">✕</span></button></div>
        {!piloted||piloted.role!=='heavy'
          ?<p className="pilot-hints">只有重装机器人执行兑矿装配。</p>
          :<>
            <div className="pilot-store-info"><b>装配顺序</b><span>每级需先完成上一级 · 4 级本场仅一次 · 一级 1 个能量单元，四级 2 个</span></div>
            <div className="pilot-store-info"><b>发射机构</b><span>{launcherNote}</span></div>
            <div className="pilot-assembly-levels" role="group" aria-label="装配难度">
              {assemblyLevels.map(({level,ready,reason,first})=><button key={level} className={ready?'ready':''} disabled={!ready} onClick={()=>orderAssembly(level)}>
                <b>{level} 级</b><small>{reason}</small><i>{first?'首次收益':'重复收益'}：{rewards[level]}</i>
              </button>)}
            </div>
            {coreState&&['moving','inserting','buffered'].includes(coreState.stage)&&<p className="pilot-store-note">当前 {coreState.difficulty} 级装配进行中：{coreState.operation??'操作中'} · 机械臂会自动完成插入 / 抬升 / 翻转 / 旋转 / 确认。</p>}
            {unitsOnBoard(piloted)<1&&<p className="pilot-store-warn">没有携带能量单元：先开到己方矿区，按住 I 让机械臂夹取。</p>}
            {!atAssembly&&<p className="pilot-store-warn">当前不在己方装配区：开到兑矿台（场心）再下达装配。</p>}
            {atAssembly&&<p className="pilot-store-note">己方装配区内重装机器人处于无敌状态：装配时不会被击穿，可以放心留在工位。</p>}
            <div className="pilot-actions">
              {storePrices&&inSupply(piloted,frame)&&<button onClick={openLocalStore}>本区购买 {storeKind} 弹药</button>}
              <button onClick={closeAssembly}>关闭</button>
            </div>
          </>}
      </div>
    </>}
    {store&&<>
      <div className="pilot-backdrop" onClick={closeStore}/>
      <div className="pilot-panel pilot-store" role="dialog" aria-label={store.mode==='local'?'补给区购买':'远程补给'}>
        <div className="pilot-heading"><Coins size={14}/><span>{store.mode==='local'?'补给区购买':'远程补给'}</span><em>{piloted?`${storeKind??'—'} · ${piloted.team==='red'?'红':'蓝'}方 ${piloted.slot} 号`:'未接管'}</em><button className="pilot-x" onClick={closeStore} aria-label="关闭购买"><span className="pilot-x-glyph" aria-hidden="true">✕</span></button></div>
        {!piloted?<p className="pilot-hints">请先接管一台机器人。</p>:<>
          {store.mode==='remote'&&<div className="pilot-team-switch" role="group" aria-label="远程项目">
            <button className={store.tab==='ammo'?'active':''} disabled={!storePrices} onClick={()=>setStore(s=>s?{...s,tab:'ammo'}:s)}>远程买弹</button>
            <button className={store.tab==='heal'?'active':''} onClick={()=>setStore(s=>s?{...s,tab:'heal'}:s)}>远程买血</button>
          </div>}
          {store.mode==='local'&&storePrices&&<>
            <div className="pilot-store-info"><b>{storeKind}</b><span>补给区原价 {storePrices.local.batch} 发 / {storePrices.local.cost} 金币</span></div>
            <div className="pilot-qty" role="group" aria-label="购买数量">
              {localSteps.map(s=><button key={'m'+s} onClick={()=>adjustStore(-s)}>-{s}</button>)}
              <output>{store.amount}</output>
              {[...localSteps].reverse().map(s=><button key={'p'+s} onClick={()=>adjustStore(s)}>+{s}</button>)}
            </div>
            <div className="pilot-store-info"><span>合计 <b>{localPrice}</b> 金币</span><span>现有 {Math.round(gold)} · 剩余可购 {Math.max(0,storePrices.local.cap-purchased)} 发</span></div>
            {!inSupply(piloted,frame)&&<p className="pilot-store-warn">已离开补给区/完全控制的前哨站，本次下单会被拒绝。</p>}
            {localPrice>gold&&<p className="pilot-store-warn">金币不足。</p>}
          </>}
          {store.mode==='remote'&&store.tab==='ammo'&&storePrices&&<>
            <div className="pilot-store-info"><b>{storeKind} 远程</b><span>{storePrices.remote.batch} 发 / {storePrices.remote.cost} 金币</span></div>
            <div className="pilot-qty" role="group" aria-label="购买批数">
              {[10,1].map(s=><button key={'m'+s} onClick={()=>adjustStore(-s)}>-{s}</button>)}
              <output>{remoteShots} 发</output>
              {[1,10].map(s=><button key={'p'+s} onClick={()=>adjustStore(s)}>+{s}</button>)}
            </div>
            <div className="pilot-store-info"><span>合计 <b>{remotePrice}</b> 金币</span><span>{store.batches} 批 · 现有 {Math.round(gold)} · 剩余可购 {Math.max(0,storePrices.remote.cap-purchased)} 发</span></div>
            {remotePrice>gold&&<p className="pilot-store-warn">金币不足。</p>}
            {purchased+remoteShots>storePrices.remote.cap&&<p className="pilot-store-warn">超过本队购买上限。</p>}
            {disengage>0&&<p className="pilot-store-warn">远程下单需脱离交战 6 秒：还要 {Math.ceil(disengage)} 秒</p>}
          </>}
          {store.mode==='remote'&&store.tab==='heal'&&<>
            <div className="pilot-store-info"><b>远程兑换血量</b><span>6 秒后恢复 60% 上限血量</span></div>
            <div className="pilot-store-info"><span>费用 <b>{healCost}</b> 金币</span><span>现有 {Math.round(gold)} · 次数不限</span></div>
            <p className="pilot-store-note">确认后 6 秒送达；这 6 秒内阵亡则本次兑换失效，金币不返还。</p>
            {disengage>0&&<p className="pilot-store-warn">远程兑换需脱离交战 6 秒：还要 {Math.ceil(disengage)} 秒</p>}
          </>}
          <div className="pilot-actions">
            <button onClick={confirmStore} disabled={store.mode==='local'
              ?(store.amount<=0||localPrice>gold||!inSupply(piloted,frame))
              :store.tab==='ammo'
                ?(remoteMaxBatches<store.batches||remotePrice>gold||disengage>0)
                :(disengage>0||gold<healCost||dead)}>确定</button>
            <button onClick={closeStore}>取消</button>
          </div>
        </>}
      </div>
    </>}
    {/* Link Start confirmation: the chassis the pilot just clicked, with its numbers, before the
        camera dives into the cockpit. */}
    {linkRobot&&<LinkConfirm robot={linkRobot} hardware={frame.robot_models?.[String(linkRobot.model_slot??linkRobot.slot)]} image={linkImage} onConfirm={()=>engage(linkRobot.id)} onCancel={()=>onLinkPick?.(null)}/>}
  </>;
}
