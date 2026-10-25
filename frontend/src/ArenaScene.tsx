import {FortressWarning} from './FortressWarning';
import {Component,Suspense,memo,useEffect,useMemo,useRef,type MutableRefObject,type ReactNode} from 'react';
import {Canvas,useFrame,useThree,type ThreeEvent} from '@react-three/fiber';
import {OrbitControls,useGLTF,Html} from '@react-three/drei';
import * as THREE from 'three';
import type {CameraMode,Drone,Frame,RenderFeed,Robot,TeamId} from './types';
import {frameSeason,is42} from './types';
import type {IntroSegment} from './intro';
import {TEAM_COLORS} from './types';
import {terrainHeight} from './terrain';
import {Effects,pulse} from './effects';
import {CombatText,MechanismHud,PickupHud,RobotHud,RuneBoard,RuneBurst,StructureHud} from './hud';
import {cloneForTeam,LED_COLORS,SHELL} from './teamMaterials';
import {Venue} from './venue';
import type {ArenaAudio} from './media';
import {FPV_EYE_LIFT,feedAlpha,robotWorld} from './world';
import {lobScope} from './scope';
import {useSightRenderer,SightRig} from './sight';
import {legRig,poseLegs,applyArmorNumber} from './robotRig';
import {runeActive,runeArmLight} from './runeLights';
import {useRobotScene} from './customModels';
import {batchStaticStructure} from './rigidMeshes';
import {concreteSurface,disposeSurface,floorSurface,type SurfaceSet} from './fieldSurfaces';
import {RoomEnvironment} from 'three/examples/jsm/environments/RoomEnvironment.js';

type Controls=React.ElementRef<typeof OrbitControls>;
// Pre-match picker framing: a 45-degree oblique view of the whole field to choose a half, then the
// same angle over that team's start area to choose a chassis.
export type PickView={stage:'side'|'robot';team?:TeamId};
// Default framing of the rulebook broadcast: elevated over the long side, field below the scoreboard.
// Every preset eye is 15 % higher than the previous framing: the field reads better from above.
const BROADCAST_EYE:[number,number,number]=[0,20.5,21.3],BROADCAST_TARGET:[number,number,number]=[0,0,-1.2];
// Broadcast uses the 42° lens of the rulebook stream; a pilot gets a 64° field of view
// (80° read as too wide: the field edge pulled the eye off the crosshair).
const BROADCAST_FOV=42,FPV_FOV=64;
// A spectator's eye eases toward the engine turret at up to this rate (rad/s). A pilot's eye takes
// the engine gimbal angle directly, matching the barrel model frame for frame.
const EYE_RATE=8;
// Ceilings are 15 % higher too: the broadcast preset and the first-person eye both look down on
// the field from further up.
const CINEMATIC_EYE=27.6,FOLLOW_EYE=4.4;
// Distance of the 45-degree side-picker eye: it fits the arena on whichever axis is tighter, so no
// window shape crops the field. The half picker reads it too, because which half (or the stands) the
// pointer is over has to be decided on this framing, not on the live eye — the eye backs off while the
// audience seats are aimed at, and deciding the zone on the moving eye would make it oscillate.
const SIDE_PICK_ELEVATION=45;
// Picker camera easing (1/s): the eye and its look target settle at slightly different rates so a big
// move (side overview → start cluster) reads as a swoop with the field staying framed, never a cut.
const PICK_EASE_POS=3.2,PICK_EASE_LOOK=4.2;
// The overhead camera leaves the top of the canvas to the broadcast plates: the field is framed at
// 80 % of the size that would just fit, so its far edge never sits under them.
const TOP_SCAN_SCALE=.8;
function sidePickDistance(halfW:number,halfH:number,fovDeg:number,aspect:number){
  const vFov=THREE.MathUtils.degToRad(fovDeg),hFov=2*Math.atan(Math.tan(vFov/2)*Math.max(.2,aspect));
  return Math.max((halfH*1.26)/Math.tan(vFov/2),(halfW*1.06)/Math.tan(hFov/2));
}
// A 2027 heavy robot rides its arm instead of a barrel until the launcher is fitted. The barrel line
// sits at the top of the hull and put the eye a metre up, which read as far too high for an arm view,
// so the arm view is a low camera just ahead of the arm mast: it looks over the reach with the gripper
// at the edge of the frame instead of staring into the tower it is mounted on.
const ARM_EYE_M=0.5,ARM_EYE_FORWARD=.15;
// The boom the working heavy is watched from: the model publishes the lift's world pivot and its reach
// axis every frame, so the view turns with the big arm and is never steered by the wrist or the jaws.
const ARM_BOOM_LOOK=3.2;
// Work camera: while the heavy's arm is mining or feeding a core, the driver watches the machine from
// behind its shoulder instead of from inside it — the gripper's relation to the core is the thing
// being judged, and that is impossible to read from the arm's own eye.
// The chase camera the 跟随 mode and the heavy's mining/feeding view share: this far behind the
// chassis heading, this high above the point of interest.
const FOLLOW_BACK=4;
// Drones are a fraction of a chassis: the chase eye sits closer and lower so the small body fills
// the frame instead of reading as a dot under a broadcast-wide shot.
const DRONE_FOLLOW_BACK=1.7,DRONE_FOLLOW_EYE=.9;
// Yaw of an engine body quaternion ([i,j,k,w], Z up), used when a drone is slow enough that its
// velocity says nothing about where its nose points.
const droneYaw=(q?:number[])=>{
  if(!q||q.length<4)return 0;
  const [x,y,z,w]=q;
  return Math.atan2(2*(w*z+x*y),1-2*(y*y+z*z));
};
// The drone a hangar's follow camera rides: the one already airborne, else the next best body.
const leadDrone=(r?:Robot|null)=>r?.drones?.find(d=>d.state==='flying')??r?.drones?.find(d=>d.state==='docked')??r?.drones?.find(d=>d.state==='down')??r?.drones?.[0]??null;
const droneHangar=(id:string)=>/-d\d+$/.test(id)?id.slice(0,id.lastIndexOf('-d')):null;
function droneOnField(frame:Frame,id:string){
  for(const robot of frame.robots){
    const drone=robot.drones?.find(d=>d.id===id);
    if(drone)return {robot,drone};
  }
  return null;
}
const workEyeAt=new THREE.Vector3();
// A camera change eases over this long, so switching first person → follow → broadcast reads as one
// move instead of a cut.
const TRANSITION_S=.5;
const armBooms=new Map<string,{at:THREE.Vector3;dir:THREE.Vector3}>();
// Stable tuples: a fresh array on every React render would make R3F resize the renderer each frame.
const BROADCAST_DPR:[number,number]=[1,1.2],FPV_DPR:[number,number]=[.8,1.05];
// Adaptive resolution trades pixels for frames; below this the image is too soft to read the field.
const DPR_FLOOR=.6;
const point=(r:{x:number;y:number;z?:number},h=0,width=28,height=15)=>new THREE.Vector3(r.x-width/2,(r.z||0)+h,r.y-height/2);
// Shortest signed difference between two wrapped yaw angles.
const yawDelta=(from:number,to:number)=>{const d=(to-from+Math.PI)%(Math.PI*2);return (d<0?d+Math.PI*2:d)-Math.PI;};
// The barrel's world yaw and pitch. The engine reports the gimbal angles in the hull frame, so a
// camera that used them directly would disagree with the barrel whenever the chassis sat on a
// ramp, climbed a step or tipped. Carrying the local angles through the hull attitude keeps the
// first-person lens exactly on the bore line.
const barrelView=(r:Robot)=>{
  const fallback={yaw:r.aim??r.heading??0,pitch:r.pitch??0};
  const q=r.quaternion;
  if(!q||q.length!==4)return fallback;
  const localYaw=(r.aim??r.heading??0)-(r.heading??0),pitch=r.pitch??0,cos=Math.cos(pitch);
  const vx=Math.cos(localYaw)*cos,vy=Math.sin(localYaw)*cos,vz=Math.sin(pitch);
  const [qx,qy,qz,qw]=q;
  const tx=2*(qy*vz-qz*vy),ty=2*(qz*vx-qx*vz),tz=2*(qx*vy-qy*vx);
  const x=vx+qw*tx+qy*tz-qz*ty,y=vy+qw*ty+qz*tx-qx*tz,z=vz+qw*tz+qx*ty-qy*tx;
  return {yaw:Math.atan2(y,x),pitch:Math.asin(Math.max(-1,Math.min(1,z)))};
};
const colors={red:new THREE.Color(LED_COLORS.red),blue:new THREE.Color(LED_COLORS.blue)},WHITE=new THREE.Color('#ffffff');
const toHeight=(frame:Frame,x:number,y:number)=>terrainHeight(frame.arena,x,y);

// Structures are static scenery with a few named hinges, so they are merged by material as soon as
// they are cloned: the field and the two bases are most of the draw calls in a broadcast frame.
// The field map is left as loaded: its materials are restyled by name and carry baked contact shadows per material.
const STRUCTURE_ASSET=/^\/assets\/(?:base-|outpost-|tech-core-|rune-)/;
function useAsset(url:string,team?:TeamId){
  const scene=useRobotScene(url);
  const asset=useMemo(()=>{const clone=cloneForTeam(scene,team);return STRUCTURE_ASSET.test(url)?batchStaticStructure(clone):clone;},[scene,team,url]),gl=useThree(state=>state.gl);
  // A newly loaded caster also invalidates the cached shadow while paused.
  useEffect(()=>{gl.shadowMap.needsUpdate=true;},[gl,asset]);
  return asset;
}

function RobotModel({id,role,team,url,feed,selected,onSelect,hidden,hover,pick,onPick}:{id:string;role:string;team:TeamId;url:string;feed:MutableRefObject<RenderFeed>;selected:string;onSelect:(id:string)=>void;hidden?:boolean;hover?:MutableRefObject<string|null>;pick?:boolean;onPick?:(id:string)=>void}){
  const asset=useAsset(url,team),group=useRef<THREE.Group>(null),body=asset.getObjectByName('Chassis'),turret=asset.getObjectByName('Turret'),pitch=asset.getObjectByName('GunPitch');
  const poseNow=useMemo(()=>new THREE.Quaternion(),[]),poseOld=useMemo(()=>new THREE.Quaternion(),[]);
  useEffect(()=>applyArmorNumber(asset,id.slice(id.lastIndexOf('-')+1)),[asset,id]);
  useEffect(()=>()=>{armBooms.delete(id);},[id]);
  const lift=asset.getObjectByName('GunElevator'),shoulder=asset.getObjectByName('ArmShoulder'),forearm=asset.getObjectByName('ArmForearm');
  const arms=useMemo(()=>['','Aux_'].map(prefix=>{const get=(n:string)=>asset.getObjectByName(prefix+n);const slew=get('ArmSlew');return slew?{slew,lift:get('ArmLift')!,stage:get('ArmMastStage')!,reach:get('ArmReach')!,yaw:get('ArmWristYaw')!,pitch:get('ArmWristPitch')!,roll:get('ArmWristRoll')!,jaws:[get('GripperJaw_0'),get('GripperJaw_1')],liftRest:get('ArmLift')!.position.y}:null;}),[asset]);
  // Scratch vectors for the boom the first-person arm view follows.
  const boomAt=useMemo(()=>new THREE.Vector3(),[]),boomDir=useMemo(()=>new THREE.Vector3(),[]),boomQuat=useMemo(()=>new THREE.Quaternion(),[]);
  const steering=useMemo(()=>[0,1,2,3].map(k=>asset.getObjectByName('SteerModule_'+k)),[asset]);
  const foldMasts=useMemo(()=>{const nodes:THREE.Object3D[]=[];asset.traverse(o=>{if(o.name.startsWith('FoldMast_'))nodes.push(o);});return nodes;},[asset]);
  const legs=useMemo(()=>legRig(asset),[asset]);
  const carried=[asset.getObjectByName('CarriedUnit_0'),asset.getObjectByName('CarriedUnit_1')];
  const heldUnit=useRef<THREE.Group>(null),unitAsset=useAsset('/assets/energy-unit-ch4.glb');
  const rotorNodes=useMemo(()=>{const nodes:THREE.Object3D[]=[];asset.traverse(o=>{if(o.name.startsWith('Rotor_')&&!(o instanceof THREE.Mesh))nodes.push(o);});return nodes;},[asset]);
  const wheelNodes=useMemo(()=>{const nodes:THREE.Object3D[]=[];asset.traverse(o=>{if(/^Wheel_\d+$/.test(o.name)&&!(o instanceof THREE.Mesh))nodes.push(o);});return nodes.sort((a,b)=>Number(a.name.slice(6))-Number(b.name.slice(6)));},[asset]);
  const ring=useRef<THREE.Mesh>(null),shield=useRef<THREE.Mesh>(null),light=useRef<THREE.PointLight>(null),pickRing=useRef<THREE.Mesh>(null);const lastPosition=useRef(new THREE.Vector3());
  const deadShade=useRef<boolean|null>(null);
  const materials=useMemo(()=>{const list:THREE.Material[]=[];asset.traverse(o=>{if(o instanceof THREE.Mesh)list.push(...(Array.isArray(o.material)?o.material:[o.material]));});return list;},[asset]);
  const glows=useMemo(()=>materials.filter((m):m is THREE.MeshStandardMaterial=>m instanceof THREE.MeshStandardMaterial&&m.name.startsWith('TeamGlow')).map(m=>({m,emissive:m.emissive.clone(),intensity:m.emissiveIntensity})),[materials]);
  const gunRest=useMemo(()=>pitch?.position.clone(),[pitch]);
  // RMUC 2027 heavy robots: the modular 42 mm launcher appears once it is fitted at the workbench.
  const launcherModule=asset.getObjectByName('LauncherModule');
  useFrame(({clock},dt)=>{const f=feed.current.frame;if(!f||!group.current)return;const r=f.robots.find(r=>r.id===id);if(!r)return;
    const physicalAlive=r.role==='aerial'||r.alive;
    const old=feed.current.previous?.robots.find(r=>r.id===id)||r;
    const alpha=feedAlpha(feed.current);
    const pos=point(r,0,f.arena.width,f.arena.height);pos.lerp(point(old,0,f.arena.width,f.arena.height),1-alpha);group.current.position.copy(pos);
    if(r.quaternion){const a=r.quaternion,b=old.quaternion||a;poseNow.set(-a[0],-a[2],-a[1],a[3]);poseOld.set(-b[0],-b[2],-b[1],b[3]);group.current.quaternion.copy(poseOld.slerp(poseNow,alpha));}else group.current.rotation.y=-r.heading;
    // Turret and gun are posed with the same interpolation the first-person eye uses, so the view
    // and the barrel hold an identical yaw and pitch on every rendered frame.
    const aimNow=(old.aim??r.aim??0)+yawDelta(old.aim??r.aim??0,r.aim??0)*alpha;
    const headingNow=(old.heading??r.heading??0)+yawDelta(old.heading??r.heading??0,r.heading??0)*alpha;
    if(turret)turret.rotation.y=-(aimNow-headingNow);
    if(pitch)pitch.rotation.z=(old.pitch??0)+((r.pitch??0)-(old.pitch??0))*alpha;
    if(pitch&&gunRest)pitch.position.x=gunRest.x-pulse('shot:'+id,is42(r.role)?.22:.08)*(is42(r.role)?.06:.015);
    if(launcherModule)launcherModule.visible=r.launcher==='fitted'||r.launcher==='installed';
    // Mirrored model: engine wheel index k sits at model index k^1 (four wheels) or 1-k (two).
    const hardware=f.robot_models?.[String(r.model_slot??r.slot)];
    steering.forEach((node,i)=>{if(node&&r.steering_angles)node.rotation.y=-r.steering_angles[i^1];});
    const twoWheel=wheelNodes.length===2;
    const travel=lastPosition.current.distanceTo(pos);if(travel<1)for(const [i,node] of wheelNodes.entries()){const k=twoWheel?1-i:i^1;node.rotation.z-=r.wheel_angular_velocity?r.wheel_angular_velocity[k]*dt:travel/(hardware?.wheel_radius_m||((r.model_slot??r.slot)===1?.09:(r.model_slot??r.slot)===2||(r.model_slot??r.slot)===7?.085:(r.model_slot??r.slot)===4?.08:.075));if(legs)continue;if(r.suspension)node.position.y=(hardware?.wheel_radius_m||((r.model_slot??r.slot)===1?.09:(r.model_slot??r.slot)===2||(r.model_slot??r.slot)===7?.085:(r.model_slot??r.slot)===4?.08:.075))+(hardware?.suspension_rest_m||.09)-r.suspension[k];if(steering[i]&&r.suspension)node.position.y=-r.suspension[k]+(hardware?.suspension_rest_m||.09);}lastPosition.current.copy(pos);
    if(legs&&r.legs){
      // Legs follow the frame interpolation; a whole hip turn dropped by the engine is not replayed.
      const was=old.legs??r.legs,turn=(r.hip_angle??0)-(old.hip_angle??r.hip_angle??0),wrapped=turn-Math.round(turn/(2*Math.PI))*2*Math.PI;
      poseLegs(legs,r.legs.map((l,k)=>was[k]+(l-was[k])*alpha),wheelNodes,(r.hip_angle??0)-wrapped*(1-alpha));
    }
    arms.forEach((arm,index)=>{if(!arm)return;const q=(index===0?r.arm_joints:r.arm2_joints)||[0,0,.22+.48*(r.arm_extension||0),0,(r.arm_extension||0)>.5?0:-1.57,0,0];
      // Robot GLBs are mirrored across their X-Z plane relative to the engine frame (as the
      // turret's -yaw shows): rotations about vertical and forward axes change sign.
      arm.slew.rotation.y=-q[0];arm.lift.position.y=arm.liftRest+q[1];arm.stage.position.y=q[1]/2;arm.reach.position.x=q[2];arm.yaw.rotation.y=-q[3];arm.pitch.rotation.z=-q[4];arm.roll.rotation.x=-q[5];
      arm.jaws.forEach((jaw,k)=>{if(jaw)jaw.position.z=-(k?1:-1)*(.018+q[6]*.032);});});
    // Publish the boom once the arm is posed: the lift's world pivot and its reach axis (model +x is
    // the direction the reach extends). Only the chassis a pilot sits in needs it, so the extra world
    // matrix update stays on one robot per frame, and the published copy is eased like the view.
    const boom=arms[0];
    if(boom&&hidden&&role==='heavy'){
      group.current.updateWorldMatrix(true,true);
      boom.lift.getWorldPosition(boomAt);
      boom.lift.getWorldQuaternion(boomQuat);
      boomDir.set(1,0,0).applyQuaternion(boomQuat).normalize();
      const known=armBooms.get(id);
      if(!known)armBooms.set(id,{at:boomAt.clone(),dir:boomDir.clone()});
      else{
        known.at.lerp(boomAt,Math.min(1,dt*14));
        known.dir.lerp(boomDir,Math.min(1,dt*10)).normalize();
      }
    }
    for(const node of rotorNodes)node.rotation.y+=dt*((r.motor_power_w??(r.z>.5?1000:0))>100?90:0);
    if(body&&!r.quaternion){body.rotation.z=physicalAlive?Math.sin(clock.elapsedTime*8+r.slot)*.006:-.08;body.position.y=physicalAlive?Math.min(.025,r.vx*r.vx*.001):-.08;}
    if(lift)lift.position.y=r.transform_allowed?-(hardware?.muzzle_z_m??.4)+r.muzzle_height_m!:r.crouched?-.265:0;
    for(const node of foldMasts){const rest=node.userData.rest_height_m??.30,height=rest+((node.userData.folded_height_m??.08)-rest)*(r.transform_progress??0);node.scale.y=height/rest;node.position.y=(node.userData.base_z_m??.10)+height/2;}
    if(shoulder)shoulder.rotation.z=(r.arm_extension||0)*.72;
    if(forearm)forearm.rotation.z=(r.arm_extension||0)*2.47;
    if(heldUnit.current){const selectedTip=r.unit_pickup?.arm===1?r.arm2_tip:r.arm_tip;const held=r.unit_pickup?.held&&r.alive&&selectedTip;heldUnit.current.visible=!!held;
      if(held){group.current.updateWorldMatrix(true,false);const tip=point({x:selectedTip![0],y:selectedTip![1],z:selectedTip![2]},0,f.arena.width,f.arena.height);
        heldUnit.current.position.copy(group.current.worldToLocal(tip));
        const q=(r.unit_pickup?.arm===1?r.arm2_joints:r.arm_joints)||[0,0,0,0,0,0,0],yaw=q[0]+q[3],pitch=q[4];
        heldUnit.current.quaternion.setFromUnitVectors(new THREE.Vector3(1,0,0),new THREE.Vector3(Math.cos(yaw)*Math.cos(pitch),-Math.sin(pitch),Math.sin(yaw)*Math.cos(pitch)));}}
    carried.forEach((node,i)=>{if(node)node.visible=i<r.carried_units;});
    // Wrecks stay on the field as physical obstacles: dimmed, lamps off. The alpha is written only
    // when the chassis actually dies or revives — assigning it every frame dirties the whole
    // material list for no reason.
    if(deadShade.current!==!physicalAlive){deadShade.current=!physicalAlive;for(const m of materials){m.transparent=!physicalAlive;m.opacity=physicalAlive?1:.62;}}
    // Team light bars breathe slightly and flare on a hit, so they read as running hardware
    // rather than a flat painted stripe.
    const hit=pulse(id,.18),breathe=1+.16*Math.sin(clock.elapsedTime*5.5+id.length);
    for(const g of glows){g.m.emissive.copy(g.emissive).lerp(WHITE,hit*.7);g.m.emissiveIntensity=r.alive||r.role==='aerial'?g.intensity*breathe*(1+hit*3):g.intensity*.08;}
    if(ring.current){ring.current.visible=selected===id&&!hidden;ring.current.rotation.z=clock.elapsedTime*.2;}
    // Pre-match picker: the chassis under the pointer lifts slightly and wears a pulsing team
    // ring, so approaching a robot on the field reads as "this one is selectable".
    if(pickRing.current){
      const lit=pick&&hover?.current===id;
      pickRing.current.visible=!!lit;
      if(lit){const s=1+.06*Math.sin(clock.elapsedTime*6);pickRing.current.scale.setScalar(s);}
      group.current.scale.setScalar(lit?1.035:1);
    }
    if(shield.current){shield.current.visible=r.alive&&r.shield>0&&!hidden;const material=shield.current.material as THREE.MeshBasicMaterial;material.opacity=.08+Math.sin(clock.elapsedTime*8)*.025;}
    if(light.current){const flash=feed.current.events.some(e=>e.type==='shot'&&e.robot===id);light.current.position.set(Math.cos(r.aim-r.heading)*Math.cos(r.pitch)*(r.muzzle_reach_m||.3),(r.muzzle_height_m||.55)+Math.sin(r.pitch)*(r.muzzle_reach_m||.3),Math.sin(r.aim-r.heading)*Math.cos(r.pitch)*(r.muzzle_reach_m||.3));light.current.intensity=flash?.15:Math.max(0,light.current.intensity-dt*30);}
    // The first-person eye sits in the gimbal, so the turret and its barrel are dropped while the
    // robot is driven from inside; the hull stays on screen, which is what a pilot expects to see
    // when they look down at their own chassis.
    if(turret)turret.visible=!hidden;
    group.current.visible=true;
  });
  // While the picker is up the click belongs to `PickProbe`: it resolves the chassis nearest the
  // pointer, which is exactly the one highlighted. Raycasting here as well would hand the pick to a
  // different chassis than the one lit up for anything standing in front of another.
  const pick_=(e:ThreeEvent<PointerEvent>)=>{e.stopPropagation();document.body.dataset.lastPick=id;if(!pick)onSelect(id);};
  return <group ref={group} onPointerDown={pick_}>
    <primitive object={asset}/>
    {(role==='engineer'||role==='heavy')&&<><group ref={heldUnit} visible={false}>
      <primitive object={unitAsset} rotation={[0,0,-Math.PI/2]}/>
    </group><PickupHud id={id} feed={feed}/></>}
    <mesh ref={ring} rotation={[-Math.PI/2,0,0]} position={[0,.024,0]} visible={selected===id}><ringGeometry args={[.75,.79,48]}/><meshBasicMaterial color="#edc27a" transparent opacity={.9} side={THREE.DoubleSide}/></mesh>
    <mesh ref={pickRing} rotation={[-Math.PI/2,0,0]} position={[0,.03,0]} visible={false}><ringGeometry args={[.52,.62,48]}/><meshBasicMaterial color={TEAM_COLORS[team]} transparent opacity={.85} side={THREE.DoubleSide} depthWrite={false}/></mesh>
    <mesh ref={shield} position={[0,.47,0]} visible={false}><sphereGeometry args={[.82,20,12]}/><meshBasicMaterial color={TEAM_COLORS[team]} transparent opacity={.1} depthWrite={false}/></mesh>
    <pointLight ref={light} position={[.75,.8,0]} color="#66ee55" intensity={0} distance={1}/>
  </group>;
}

// RMUC 2027 aerial robots: each hangar's drones fly as separate bodies (robot.drones). A drone is
// its own follow target: clicking it selects `<hangar>-d<index>`, and selecting the hangar lights
// every body it launched so the viewer can pick one of them from the field.
function DroneModel({robot,droneId,index,team,url,feed,selected,onSelect}:{robot:string;droneId:string;index:number;team:TeamId;url:string;feed:MutableRefObject<RenderFeed>;selected:string;onSelect:(id:string)=>void}){
  const asset=useAsset(url,team),group=useRef<THREE.Group>(null),now=useMemo(()=>new THREE.Quaternion(),[]),was=useMemo(()=>new THREE.Quaternion(),[]);
  const id=droneId,ring=useRef<THREE.Mesh>(null);
  const rotors=useMemo(()=>{const nodes:THREE.Object3D[]=[];asset.traverse(o=>{if(o.name.startsWith('Rotor_')&&!(o instanceof THREE.Mesh))nodes.push(o);});return nodes;},[asset]);
  const materials=useMemo(()=>{const list:THREE.Material[]=[];asset.traverse(o=>{if(o instanceof THREE.Mesh)list.push(...(Array.isArray(o.material)?o.material:[o.material]));});return list;},[asset]);
  useFrame(({clock},dt)=>{const f=feed.current.frame;if(!f||!group.current)return;const r=f.robots.find(r=>r.id===robot),d=r?.drones?.[index];if(!d){group.current.visible=false;return;}
    const old:Drone=feed.current.previous?.robots.find(o=>o.id===robot)?.drones?.[index]||d,alpha=feedAlpha(feed.current);
    group.current.visible=true;group.current.position.copy(point(d,0,f.arena.width,f.arena.height)).lerp(point(old,0,f.arena.width,f.arena.height),1-alpha);
    const a=d.quaternion,b=old.quaternion||a;now.set(-a[0],-a[2],-a[1],a[3]);was.set(-b[0],-b[2],-b[1],b[3]);group.current.quaternion.copy(was.slerp(now,alpha));
    for(const node of rotors)node.rotation.y+=dt*(d.state==='flying'?120:0);
    for(const m of materials){m.transparent=d.state==='disabled';m.opacity=d.state==='disabled'?.45:1;}
    // The hangar paints all of its drones, whether the hangar itself or one of them is followed;
    // the body the camera rides gets a brighter pulsing ring.
    const own=selected===id,family=!own&&(selected===robot||droneHangar(selected)===robot);
    if(ring.current){
      ring.current.visible=own||family;
      const material=ring.current.material as THREE.MeshBasicMaterial;
      material.color.set(own?'#edc27a':TEAM_COLORS[team]);material.opacity=own?.95:family?.55:0;
      ring.current.scale.setScalar(own?1+.1*Math.sin(clock.elapsedTime*8):1);
    }
  });
  return <group ref={group}>
    <primitive object={asset}/>
    <mesh ref={ring} rotation={[-Math.PI/2,0,0]} position={[0,-.02,0]} visible={false}><ringGeometry args={[.16,.19,32]}/><meshBasicMaterial transparent opacity={.9} depthWrite={false}/></mesh>
    {/* A drone is small enough that the ring alone is hard to hit: this invisible sphere widens the
        click target without drawing anything on top of the model. */}
    <mesh onPointerDown={e=>{e.stopPropagation();onSelect(id);}}><sphereGeometry args={[.16,12,8]}/><meshBasicMaterial transparent opacity={0} depthWrite={false}/></mesh>
  </group>;
}

function BaseModel({team,feed,url}:{team:TeamId;feed:MutableRefObject<RenderFeed>;url:string}){
  const asset=useAsset(url,team),group=useRef<THREE.Group>(null),opening=useRef(0);
  // Figures 4-10/4-11: six half-shells hinged at the pyramid corners swing outward as the
  // armour opens (same 1.15 rad sweep as the engine's collision shells).
  const hinges=useMemo(()=>{const result:{node:THREE.Object3D;original:THREE.Quaternion;swing:number}[]=[];asset.traverse(node=>{if(node.name.startsWith('BaseShell_'))result.push({node,original:node.quaternion.clone(),swing:Number(node.userData.swing)||1});});return result;},[asset]);
  // The lamps are resolved once: walking the whole base model every frame just to find a dozen
  // TeamGlow materials is pure overhead on the render thread.
  const glows=useMemo(()=>{const list:THREE.MeshStandardMaterial[]=[];asset.traverse(o=>{if(o instanceof THREE.Mesh)for(const m of Array.isArray(o.material)?o.material:[o.material])if(m instanceof THREE.MeshStandardMaterial&&m.name.startsWith('TeamGlow'))list.push(m);});return list;},[asset]);
  const rotation=useMemo(()=>new THREE.Quaternion(),[]),up=useMemo(()=>new THREE.Vector3(0,1,0),[]);
  useFrame(({clock},dt)=>{const b=feed.current.frame?.bases[team];if(!b||!group.current)return;group.current.position.copy(point(b,0,feed.current.frame!.arena.width,feed.current.frame!.arena.height));opening.current=b.armor_open_progress??THREE.MathUtils.damp(opening.current,b.armor_open?1:0,5,dt);for(const h of hinges)h.node.quaternion.copy(h.original).multiply(rotation.setFromAxisAngle(up,h.swing*opening.current*1.15));const glow=1.1+Math.sin(clock.elapsedTime*2)*.15+pulse('base-'+team,.25)*2.5;for(const m of glows)m.emissiveIntensity=glow;});
  return <group ref={group}><primitive object={asset}/><pointLight color={LED_COLORS[team]} intensity={2.2} distance={3.2} decay={2} position={[0,.9,0]}/></group>;
}

// A 2027 outpost rebuilt by the other team carries that team's lights and shell tint.
function OutpostModel({team,feed,url}:{team:TeamId;feed:MutableRefObject<RenderFeed>;url:string}){
  const asset=useAsset(url,team),group=useRef<THREE.Group>(null),rotor=asset.getObjectByName('ArmorRotor');
  // Same as the base: the glowing and tinted materials are collected once instead of walking the
  // whole outpost model on every frame.
  const tinted=useMemo(()=>{const glow:THREE.MeshStandardMaterial[]=[],primary:THREE.MeshStandardMaterial[]=[];asset.traverse(o=>{if(!(o instanceof THREE.Mesh))return;for(const m of Array.isArray(o.material)?o.material:[o.material]){if(!(m instanceof THREE.MeshStandardMaterial))continue;if(m.name.startsWith('TeamGlow'))glow.push(m);else if(m.name.startsWith('TeamPrimary'))primary.push(m);}});return {glow,primary};},[asset]);
  useFrame(()=>{const f=feed.current.frame,b=f?.outposts?.[team];if(!b||!group.current)return;group.current.position.copy(point(b,0,f!.arena.width,f!.arena.height));// The rotor turns between frames like the interpolated drones that strike it.
    const was=feed.current.previous?.outposts?.[team]?.rotation??b.rotation??0,turn=(b.rotation||0)-was;
    if(rotor)rotor.rotation.y=-(was+Math.atan2(Math.sin(turn),Math.cos(turn))*feedAlpha(feed.current));const held=b.owner??team;
    for(const m of tinted.glow){m.emissiveIntensity=b.hp>0?(m.userData.glow??=m.emissiveIntensity)*(1+pulse('outpost-'+team,.25)*2.5):0;m.color.set(b.hp>0?LED_COLORS[held]:'#1a1c20');m.emissive.set(LED_COLORS[held]);}
    for(const m of tinted.primary)m.color.set(SHELL[held]);});
  return <group ref={group}><primitive object={asset}/></group>;
}


const RUNE_OFF=new THREE.Color('#1b2126');
const RUNE_HIT=new THREE.Color('#ffc247'),RUNE_IMPACT=new THREE.Color('#ffffff');
function lamp(m:THREE.MeshStandardMaterial,on:boolean,color:THREE.Color,intensity=2){m.color.copy(on?color:RUNE_OFF);m.emissive.copy(color);m.emissiveIntensity=on?intensity:0;}

// One coaxial lamp face per team (5.5.2): red faces the red half, blue the blue half.
function RuneFace({team,feed,url}:{team:TeamId;feed:MutableRefObject<RenderFeed>;url:string}){
  const asset=useAsset(url,team),group=useRef<THREE.Group>(null),rotor=asset.getObjectByName('RuneRotor');
  const arms=useMemo(()=>{
    const list=[0,1,2,3,4].map(()=>({frame:[] as THREE.MeshStandardMaterial[],target:[] as THREE.MeshStandardMaterial[],ring:[] as THREE.MeshStandardMaterial[],arrows:[[],[],[],[]] as THREE.MeshStandardMaterial[][]}));
    const logo:THREE.MeshStandardMaterial[]=[];
    asset.traverse(o=>{if(!(o instanceof THREE.Mesh))return;const m=o.material as THREE.MeshStandardMaterial;
      let node:THREE.Object3D|null=o,arm=-1,arrow=-1;while(node){const a=/^RuneArm_(\d)$/.exec(node.name),b=/^RuneArrow_\d_(\d)$/.exec(node.name);if(a&&arm<0)arm=+a[1];if(b&&arrow<0)arrow=+b[1];node=node.parent;}
      if(m.name.startsWith('TeamRuneLogo'))logo.push(m);
      if(arm<0)return;const slot=list[arm];
      if(m.name.startsWith('TeamRuneArrow')&&arrow>=0)slot.arrows[arrow].push(m);else if(m.name.startsWith('TeamRuneTarget'))slot.target.push(m);else if(m.name.startsWith('TeamRuneRing'))slot.ring.push(m);else if(m.name.startsWith('TeamRuneFrame'))slot.frame.push(m);});
    return {list,logo};
  },[asset]);
  const color=useMemo(()=>new THREE.Color(team==='red'?'#ff3424':'#2f86ff'),[team]),local=useMemo(()=>new THREE.Vector3(),[]),inverse=useMemo(()=>new THREE.Matrix4(),[]);
  useFrame(()=>{const f=feed.current.frame,rune=f?.arena.rune,state=f?.runes?.[team];if(!f||!rune||!state||!group.current||!rotor)return;
    const yaw=rune.axis_yaw||0,sign=team==='red'?-1:1,offset=rune.face_offset_m??.35;
    group.current.position.set(rune.x+sign*offset*Math.cos(yaw)-f.arena.width/2,rune.z,rune.y+sign*offset*Math.sin(yaw)-f.arena.height/2);
    group.current.rotation.set(0,Math.atan2(-sign*Math.sin(yaw),sign*Math.cos(yaw)),0);group.current.updateMatrixWorld();
    const targets=(state.targets||[]) as {x:number;y:number;z:number;arm:number}[];
    inverse.copy(group.current.matrixWorld).invert();
    const blend=feedAlpha(feed.current),previous=feed.current.previous?.runes?.[team]?.targets||[];
    const angles=targets.map(t=>{const old=previous.find((o:{arm:number})=>o.arm===t.arm)||t;local.copy(point({x:old.x+(t.x-old.x)*blend,y:old.y+(t.y-old.y)*blend,z:old.z+(t.z-old.z)*blend},0,f.arena.width,f.arena.height)).applyMatrix4(inverse);return Math.atan2(local.z,local.y);});
    if(angles.length)rotor.rotation.x=angles[0];
    // Map each modelled arm to the engine arm it covers after the rotation.
    const active=runeActive(state,f.time),activating=state.status==='activating';
    arms.list.forEach((slot,node)=>{
      let engineArm=node;
      if(angles.length){const want=angles[0]+node*Math.PI*2/5;let best=1e9;angles.forEach((a,k)=>{const d=Math.abs(Math.atan2(Math.sin(a-want),Math.cos(a-want)));if(d<best){best=d;engineArm=targets[k].arm??k;}});}
      const light=runeArmLight(state,engineArm,f.time),held=light==='active'||light==='hit'||light==='impact',target=light==='target';
      const tint=light==='hit'?RUNE_HIT:light==='impact'?RUNE_IMPACT:color;
      slot.frame.forEach(m=>lamp(m,held,tint,1.1));slot.ring.forEach(m=>lamp(m,held,tint,1.3));
      slot.target.forEach(m=>lamp(m,held||target,tint,held?1.4:1.4+Math.sin(f.time*14)*.4));
      slot.arrows.forEach((list,k)=>{const on=held||(target&&((f.time*6-k)%4+4)%4<1.6);list.forEach(m=>lamp(m,on,tint,1.4));});
    });
    arms.logo.forEach(m=>lamp(m,true,color,active?1.4:activating?1:.5));
  });
  return <group ref={group}><primitive object={asset}/></group>;
}

function RuneModel({team,feed}:{team:TeamId;feed:MutableRefObject<RenderFeed>}){
  const url=feed.current.frame?.arena.structure_assets?.rune;
  return url?<RuneFace team={team} feed={feed} url={url}/>:<LegacyRuneModel team={team} feed={feed}/>;
}

// Technology core on its 6-axis mount, posed in the 5.3.3 assembly frame.
function TechCore({team,feed,url}:{team:TeamId;feed:MutableRefObject<RenderFeed>;url:string}){
  const asset=useAsset(url,team),group=useRef<THREE.Group>(null);
  const nodes=useMemo(()=>({carriage:asset.getObjectByName('CoreCarriage'),lift:asset.getObjectByName('CoreLift'),yaw:asset.getObjectByName('CoreYaw'),pitch:asset.getObjectByName('CorePitch'),roll:asset.getObjectByName('CoreRoll'),unit:asset.getObjectByName('CoreUnit')}),[asset]);
  const lamps=useMemo(()=>{const list:THREE.MeshStandardMaterial[]=[];asset.traverse(o=>{if(o instanceof THREE.Mesh&&(o.material as THREE.Material).name.startsWith('TeamCoreLamp'))list.push(o.material as THREE.MeshStandardMaterial);});return list;},[asset]);
  const color=useMemo(()=>new THREE.Color(LED_COLORS[team]),[team]),rotation=useMemo(()=>new THREE.Euler(0,0,0,'YZX'),[]),offset=useMemo(()=>new THREE.Vector3(),[]);
  const unitRest=useMemo(()=>nodes.unit?.position.clone(),[nodes]);
  useFrame(({clock})=>{const f=feed.current.frame,frame=f?.arena.assembly_frames?.[team],state=f?.assemblies?.[team];if(!f||!frame||!group.current||!nodes.carriage||!nodes.lift||!nodes.yaw||!nodes.pitch||!nodes.roll)return;
    const [ox,oy]=frame.origin,[ax,ay]=frame.x_axis,floor=Math.min(oy,f.arena.height-oy)*Math.tan(1.5*Math.PI/180);
    group.current.position.set(ox-f.arena.width/2,floor+(frame.z0_m||.5),oy-f.arena.height/2);group.current.rotation.set(0,Math.atan2(-ay,ax),0);
    const previous=feed.current.previous?.assemblies?.[team],blend=feedAlpha(feed.current);
    const old=previous?.attempt===state.attempt?previous:state;
    const lerp=(key:string)=>(old[key]||0)+((state[key]||0)-(old[key]||0))*blend;
    const current=(state?.current_pose||state?.pose||frame.initial_pose) as number[],prior=(old.current_pose||current) as number[];
    const pose=current.map((v,i)=>prior[i]+(v-prior[i])*blend),[x,y,z,theta,phi,alpha]=pose,rad=Math.PI/180;
    // E = pivot + R·(0.10, 0, 0), R = Ry(-theta)·Rz(90-phi)·Rx(alpha), local Y up and Z = assembly +Y.
    rotation.set(alpha*rad,-theta*rad,(90-phi)*rad,'YZX');offset.set(.10,0,0).applyEuler(rotation);
    const pivot=[x-offset.x,z-offset.y,y-offset.z];
    nodes.carriage.position.set(pivot[0],.30,pivot[2]);nodes.lift.position.y=pivot[1]-.40;
    nodes.yaw.rotation.y=-theta*rad;nodes.pitch.rotation.z=(90-phi)*rad;nodes.roll.rotation.x=alpha*rad;
    const stage=state?.stage||'idle',ready=stage==='inserting'||stage==='buffered',moving=stage==='moving';
    if(nodes.unit&&unitRest){nodes.unit.visible=(ready||stage==='complete')&&(state.inserted||0)>0;nodes.unit.position.set(unitRest.x+.06-lerp('inserted'),unitRest.y,unitRest.z+lerp('translated'));nodes.unit.rotation.x=lerp('rotation')*rad;}
    lamps.forEach(m=>lamp(m,ready||(moving&&Math.sin(clock.elapsedTime*10)>0),color,ready?2.2:1.4));
  });
  return <group ref={group}><primitive object={asset}/></group>;
}

function LegacyRuneModel({team,feed}:{team:TeamId;feed:MutableRefObject<RenderFeed>}){
  const heads=useRef<Array<THREE.Group|null>>([]),cards=useRef<Array<THREE.Mesh|null>>([]),beams=useRef<Array<THREE.Mesh|null>>([]);
  const direction=useMemo(()=>new THREE.Vector3(),[]);
  useFrame(()=>{const f=feed.current.frame,state=f?.runes?.[team],targets=state?.targets;if(!f||!targets?.length)return;
    const center=point({x:targets.reduce((s:number,t:any)=>s+t.x,0)/5,y:targets.reduce((s:number,t:any)=>s+t.y,0)/5,z:targets.reduce((s:number,t:any)=>s+t.z,0)/5});
    const yaw=f.arena.rune?.axis_yaw||0;
    const blend=feedAlpha(feed.current),previous=feed.current.previous?.runes?.[team]?.targets||[];
    targets.forEach((t:any,i:number)=>{const old=previous.find((o:{arm:number})=>o.arm===t.arm)||t;const target=point({x:old.x+(t.x-old.x)*blend,y:old.y+(t.y-old.y)*blend,z:old.z+(t.z-old.z)*blend}),head=heads.current[i],card=cards.current[i];
      if(head){head.position.copy(target);head.rotation.y=Math.PI/2-yaw;}
      const light=runeArmLight(state,t.arm??i,f.time),tint=light==='hit'?RUNE_HIT:light==='impact'?RUNE_IMPACT:colors[team];
      if(card)lamp(card.material as THREE.MeshStandardMaterial,light!=='off',tint,1.4);
      const beam=beams.current[i];if(beam){direction.copy(target).sub(center);beam.position.copy(center).add(target).multiplyScalar(.5);beam.scale.y=direction.length();beam.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),direction.normalize());}
      if(beam)lamp(beam.material as THREE.MeshStandardMaterial,['active','hit','impact'].includes(light),tint,1.1);
    });
  });
  return <group>{[0,1,2,3,4].map(i=><group key={i}><group ref={e=>{heads.current[i]=e;}}><mesh><boxGeometry args={[.35,.35,.045]}/><meshStandardMaterial color="#172027" metalness={.65} roughness={.4}/></mesh><mesh ref={e=>{cards.current[i]=e;}} position={[0,0,.027]}><circleGeometry args={[.15,32]}/><meshStandardMaterial color={TEAM_COLORS[team]} emissive={TEAM_COLORS[team]} side={THREE.DoubleSide} metalness={.35} roughness={.55}/></mesh>{[.05,.10,.146].map(radius=><mesh key={radius} position={[0,0,.029]}><ringGeometry args={[radius-.003,radius,32]}/><meshBasicMaterial color="#283039" side={THREE.DoubleSide}/></mesh>)}</group><mesh ref={e=>{beams.current[i]=e;}}><boxGeometry args={[.065,1,.04]}/><meshStandardMaterial color="#364149" metalness={.7} roughness={.45}/></mesh></group>)}</group>;
}

// Tileable concrete for the field (UV = world metres x 0.4): the highland's grey camouflage patches and the floor's grain.
function concreteTexture(base:string,patches:string[],grain:number,blobs:number,seed:number){
  const size=1024,canvas=document.createElement('canvas');canvas.width=canvas.height=size;const ctx=canvas.getContext('2d')!;let s=seed;const r=()=>{s=(s*16807)%2147483647;return s/2147483647;};
  ctx.fillStyle=base;ctx.fillRect(0,0,size,size);
  for(let i=0;i<blobs;i++){const x=r()*size,y=r()*size,radius=50+r()*190,color=patches[Math.floor(r()*patches.length)],alpha=.12+r()*.22,squash=.45+r()*.55,turn=r()*Math.PI;
    for(const dx of [-size,0,size])for(const dy of [-size,0,size]){ctx.save();ctx.translate(x+dx,y+dy);ctx.rotate(turn);ctx.scale(1,squash);const g=ctx.createRadialGradient(0,0,0,0,0,radius);g.addColorStop(0,color);g.addColorStop(.45,color);g.addColorStop(1,'rgba(128,128,128,0)');ctx.globalAlpha=alpha;ctx.fillStyle=g;ctx.fillRect(-radius,-radius,radius*2,radius*2);ctx.restore();}}
  ctx.globalAlpha=1;const image=ctx.getImageData(0,0,size,size);for(let i=0;i<image.data.length;i+=4){const n=(r()-.5)*grain;image.data[i]+=n;image.data[i+1]+=n;image.data[i+2]+=n;}ctx.putImageData(image,0,0);
  const t=new THREE.CanvasTexture(canvas);t.colorSpace=THREE.SRGBColorSpace;t.wrapS=t.wrapT=THREE.RepeatWrapping;t.repeat.set(.25,.25);t.anisotropy=8;return t;
}

function ArenaMap({frame,feed}:{frame:Frame;feed:MutableRefObject<RenderFeed>}){
  const asset=useAsset(frame.arena.asset||`/assets/map-${frame.arena.name}.glb`),season=frameSeason(frame);
  const concrete=useMemo(()=>season==='2027'?null:{highland:concreteTexture('#86898d',['#6a6d71','#5a5e62','#9a9da0','#77797d'],18,150,2026),floor:concreteTexture('#2c2e32',['#232528','#36383c','#1e2023'],12,110,7)},[season]);
  // 2027 follows manual figures 4-1 to 4-3: mottled grey concrete highlands and kerbs, a near-black speckled floor and
  // matt paint. Colour, bump and roughness maps per surface; the GLB adds baked contact shadows (aoMap, second UV set).
  const surfaces=useMemo<{highland:SurfaceSet;floor:SurfaceSet}|null>(()=>season==='2027'?{highland:concreteSurface('#605d59',2027),floor:floorSurface('#302e2b',7)}:null,[season]);
  useEffect(()=>()=>{if(concrete){concrete.highland.dispose();concrete.floor.dispose();}if(surfaces){disposeSurface(surfaces.highland);disposeSurface(surfaces.floor);}},[concrete,surfaces]);
  useMemo(()=>asset.traverse(o=>{if(!(o instanceof THREE.Mesh))return;for(const m of (Array.isArray(o.material)?o.material:[o.material]) as THREE.MeshStandardMaterial[]){
    if(m.userData.broadcast)continue;m.userData.broadcast=true;
    if(surfaces){
      const surface=(set:SurfaceSet,tint:number,rough:number)=>{m.map=set.map;m.bumpMap=set.bump;m.bumpScale=1.2;m.roughnessMap=set.rough;m.roughness=rough;m.metalness=0;m.color.setScalar(tint);m.needsUpdate=true;};
      if(m.name.startsWith('RedFieldPaint')){m.color.set('#b8352d');m.emissive.set('#b8352d');m.emissiveIntensity=.18;m.roughness=.55;m.metalness=0;}
      else if(m.name.startsWith('BlueFieldPaint')){m.color.set('#2c55b6');m.emissive.set('#2c55b6');m.emissiveIntensity=.2;m.roughness=.55;m.metalness=0;}
      else if(m.name.startsWith('WhiteFieldPaint')){m.color.set('#cfcfcb');m.emissive.set('#ffffff');m.emissiveIntensity=.03;m.roughness=.6;m.metalness=0;}
      else if(m.name.startsWith('HighlandAsphalt'))surface(surfaces.highland,1,1);
      else if(m.name.startsWith('FieldBlack'))surface(surfaces.floor,1,1);
      else if(m.name.startsWith('ProtectiveMetal'))surface(surfaces.highland,1.32,1);
      else if(m.name.startsWith('ConcreteSide'))surface(surfaces.highland,.86,1);
      continue;
    }
    if(m.name.startsWith('RedFieldPaint')){m.color.set('#ff3b30');m.emissive.set('#ff2a1c');m.emissiveIntensity=2.6;m.toneMapped=false;}
    else if(m.name.startsWith('BlueFieldPaint')){m.color.set('#1f6dff');m.emissive.set('#1450ff');m.emissiveIntensity=2.3;m.toneMapped=false;}
    else if(m.name.startsWith('WhiteFieldPaint')){m.emissive.set('#ffffff');m.emissiveIntensity=.22;}
    else if(m.name.startsWith('HighlandAsphalt')){m.map=concrete!.highland;m.color.set('#ffffff');m.roughness=.84;m.needsUpdate=true;}
    else if(m.name.startsWith('FieldBlack')){m.map=concrete!.floor;m.color.set('#ffffff');m.roughness=.88;m.needsUpdate=true;}
    else if(m.name.startsWith('ProtectiveMetal')){m.color.multiplyScalar(1.25);}
    else if(m.name.startsWith('ConcreteSide')){m.map=concrete!.highland;m.color.set('#8a8c8e');m.roughness=.9;m.needsUpdate=true;}
  }}),[asset]);
  // Small field props (plate edges, bolts, sign posts) cast shadows nobody can see, and every caster
  // is a full draw in the shadow pass. The terrain and the big masses keep theirs.
  useEffect(()=>{asset.traverse(o=>{if(!(o instanceof THREE.Mesh)||!o.castShadow)return;if(!o.geometry.boundingSphere)o.geometry.computeBoundingSphere();const radius=o.geometry.boundingSphere?.radius??0;if(radius>0&&radius<.45)o.castShadow=false;});},[asset]);
  const units=useMemo(()=>(['red','blue'] as const).map(team=>({team,node:asset.getObjectByName('AvailableUnit_'+team)})),[asset]);
  useFrame(()=>{const f=feed.current.frame;if(!f)return;for(const u of units)if(u.node)u.node.visible=!f.robots.some(r=>r.team===u.team&&r.unit_pickup?.held)&&((f.teams[u.team] as {energy_units_left?:number|null}).energy_units_left??1)>0;});
  return <group><primitive object={asset}/>{frame.arena.zones.filter(z=>!z.id.includes('_road_')&&!z.id.includes('_highland_')&&!z.id.includes('_tunnel_')&&!z.id.includes('_fly_')).map(z=><Zone key={z.id} id={z.id} x={z.x} y={z.y} radius={z.radius} elevation={toHeight(frame,z.x,z.y)} feed={feed} floorOnly={!!frame.arena.layout_revision}/>)}</group>;
}
function Zone({id,x,y,radius,elevation,feed,floorOnly}:{id:string;x:number;y:number;radius:number;elevation:number;feed:MutableRefObject<RenderFeed>;floorOnly:boolean}){
  const ring=useRef<THREE.Mesh>(null),pad=useRef<THREE.Mesh>(null),beacon=useRef<THREE.Mesh>(null);
  useFrame(({clock})=>{const zone=feed.current.frame?.zones[id];if(!zone)return;const color=zone.owner?TEAM_COLORS[zone.owner]:'#d4b57c';
    if(ring.current)(ring.current.material as THREE.MeshBasicMaterial).color.set(color);if(pad.current){const m=pad.current.material as THREE.MeshBasicMaterial;m.color.set(color);m.opacity=.035+Math.abs(zone.progress)*.07;}
    if(beacon.current){const m=beacon.current.material as THREE.MeshStandardMaterial;m.color.set(color);m.emissive.set(color);m.emissiveIntensity=zone.contested?1+Math.sin(clock.elapsedTime*12)*.7:.7;}
  });
  return <group position={[x-14,elevation+.016,y-7.5]}><mesh ref={ring} visible={!floorOnly} rotation={[-Math.PI/2,0,0]}><ringGeometry args={[radius-.06,radius,64]}/><meshBasicMaterial color="#d4b57c" transparent opacity={.7} side={THREE.DoubleSide}/></mesh><mesh ref={pad} rotation={[-Math.PI/2,0,0]}><circleGeometry args={[radius-.1,48]}/><meshBasicMaterial color="#d4b57c" transparent opacity={.05} depthWrite={false}/></mesh>{!floorOnly&&<><mesh position={[0,.19,0]}><cylinderGeometry args={[.19,.25,.38,12]}/><meshStandardMaterial color="#71848b" metalness={.7} roughness={.4}/></mesh><mesh ref={beacon} position={[0,.54,0]}><cylinderGeometry args={[.085,.085,.35,12]}/><meshStandardMaterial color="#d4b57c" emissive="#d4b57c"/></mesh></>}</group>;
}

// A lineup-intro camera cut: the overlay names the segment, the camera frames it for `length` seconds.
export type IntroShot={key:string;segment:IntroSegment;length:number};
const ease=(u:number)=>u*u*(3-2*u);
function introCamera(shot:IntroShot,u:number,frame:Frame,camera:THREE.Camera,look:THREE.Vector3){
  const s=shot.segment,e=ease(u);
  if(s.kind==='open'){const a=-1.05+e*1.25,r=7+e*15,h=(1.6+e*14)*1.15;camera.position.set(Math.sin(a)*r,h,Math.cos(a)*r);look.set(0,1.4*(1-e),-.4*e);}
  else if(s.kind==='team'){const side=s.team==='red'?1:-1;camera.position.set(side*(-3.2-2.8*e),(3.6-1.1*e)*1.15,side*(4.8-1.6*e));look.set(side*-11.2,.35,side*.4);}
  else if(s.kind==='faceoff'){camera.position.set(0,(17.5-3*e)*1.15,21.5-3.5*e);look.set(0,0,-.9);}
  else{
    const r=frame.robots.find(r=>r.id===s.id);if(!r)return;
    const hw=frame.robot_models?.[String(r.model_slot??r.slot)],dims=hw?.stowed_m||[.6,.6,.5],size=Math.max(dims[0],dims[1]),tall=dims[2]||.5;
    const p=point(r,0,frame.arena.width,frame.arena.height),a=r.heading+.8-e*.6,d=(1.35+size*1.9)*(1.12-.22*e),h=Math.max(.6,tall*1.05)+.3*e;
    camera.position.set(p.x+Math.cos(a)*d,p.y+h,p.z+Math.sin(a)*d);
    const half={x:frame.arena.width/2+1.5,z:frame.arena.height/2+1.5};camera.position.x=THREE.MathUtils.clamp(camera.position.x,-half.x,half.x);camera.position.z=THREE.MathUtils.clamp(camera.position.z,-half.z,half.z);
    look.set(p.x,p.y+tall*.42,p.z);
  }
  camera.lookAt(look);
}
function Director({mode,selected,feed,audio,onCanvas,onRender,shot,pilot,hud,pickView,pickHover,pickSeat,linkHover}:{mode:CameraMode;selected:string;feed:MutableRefObject<RenderFeed>;audio?:ArenaAudio;onCanvas:(canvas:HTMLCanvasElement)=>void;onRender:()=>void;shot?:IntroShot|null;pilot?:string|null;hud:boolean;pickView?:PickView|null;pickHover?:MutableRefObject<string|null>;pickSeat?:MutableRefObject<boolean>;linkHover?:MutableRefObject<string|null>}){
  const {camera,gl,setDpr,size}=useThree(),controls=useRef<Controls>(null),target=useMemo(()=>new THREE.Vector3(),[]);const previousMode=useRef('');
  const renderSight=useSightRenderer();
  const shadow=useRef({slot:-1,frame:null as Frame|null,generation:'',paused:false,shown:0});
  // Adaptive resolution: the scene is heavy enough that a fixed pixel ratio is wrong on both a
  // 4K desktop and a small laptop. Frame time is sampled and the renderer trades resolution for
  // frame rate inside a narrow band so the pilot sees a steady image either way.
  // `shadow`: the shadow map is refreshed on every n-th rendered frame while the field moves.
  const perf=useRef({time:0,frames:0,ratio:1.3,ceiling:1.3,shadow:1});
  const look=useMemo(()=>new THREE.Vector3(),[]),cut=useRef({key:'',at:0});
  const ear=useMemo(()=>new THREE.Vector3(),[]),ahead=useMemo(()=>new THREE.Vector3(),[]),up=useMemo(()=>new THREE.Vector3(),[]),origin=useMemo(()=>new THREE.Vector3(),[]);
  const eyePoint=useMemo(()=>new THREE.Vector3(),[]),eyeLook=useMemo(()=>new THREE.Vector3(),[]);
  // Heavy-robot arm camera: latched per robot with the last blended tool position and view point.
  // Latched look target of the heavy's arm view: the eye is positional but the aim eases, so a core
  // that jumps from one socket to the next does not snap the camera.
  const armEye=useRef({id:'',look:null as THREE.Vector3|null});
  // Third-person work camera for the heavy's arm, eased so entering and leaving the work view glides.
  const workEye=useRef({id:'',eye:new THREE.Vector3(),look:null as THREE.Vector3|null});
  // Camera-mode change: the pose the old mode left behind, eased into the new mode's pose.
  const blend=useRef({fromPos:new THREE.Vector3(),fromQuat:new THREE.Quaternion(),t:1});
  const blendTo=useMemo(()=>new THREE.Quaternion(),[]);
  // Chassis choice: eased camera pose plus the last chassis the pointer settled on.
  const pickEye=useMemo(()=>new THREE.Vector3(),[]),pickLook=useMemo(()=>new THREE.Vector3(),[]),pickNow=useMemo(()=>new THREE.Vector3(),[]);
  const pickAt=useRef({id:'',ready:false});
  // The picker eases into its first pose from whatever the broadcast left behind, and between the two
  // stages it glides instead of cutting, so side choice → chassis choice is one continuous move.
  const pickInit=useRef(false);
  const pickDir=useMemo(()=>new THREE.Vector3(),[]);
  // Eased 0→1 of how far the picker has backed off for the audience bowl.
  const seatZoom=useRef(0);
  // Link Start dives the overhead scan onto the chassis under the pointer: eased 0→1 of that dive,
  // and the distance that frames the last hovered machine at ~30 % of the picture.
  const linkDive=useRef({k:0,near:4,spot:[0,0] as [number,number]});
  // True between a pilot's death and their respawn, when the rules hold the camera pose.
  const dead=useRef(false);
  // The rendered turret angles: eased toward the engine's reported ones every frame, so 20 Hz
  // simulation steps do not turn into 20 Hz camera steps.
  const eye=useRef({id:'',yaw:0,pitch:0});
  useEffect(()=>onCanvas(gl.domElement),[gl,onCanvas]);
  useEffect(()=>{const restore=()=>{gl.shadowMap.needsUpdate=true;};gl.domElement.addEventListener('webglcontextrestored',restore);return()=>gl.domElement.removeEventListener('webglcontextrestored',restore);},[gl]);
  useFrame(({clock},dt)=>{
    // Pre-match picker: a fixed 45-degree oblique view of the whole field for the side choice, then
    // the same angle over the chosen team's start area for the chassis choice. It outranks the intro
    // because the pilot is actively choosing where to look.
    if(pickView){
      const f=feed.current.frame;
      if(f){
        const halfW=f.arena.width/2,halfH=f.arena.height/2;
        // The very first picker frame starts from the broadcast pose, so the picker never pops in: the
        // look target is seeded along the current view direction and every stage then only eases.
        if(!pickInit.current){
          pickInit.current=true;
          camera.getWorldDirection(pickDir);
          pickNow.copy(camera.position).addScaledVector(pickDir,12);
          pickAt.current.ready=false;
        }
        const easePos=1-Math.exp(-dt*PICK_EASE_POS),easeLook=1-Math.exp(-dt*PICK_EASE_LOOK);
        if(pickView.stage==='side'){
          // The side choice keeps the 45-degree overview of the whole field — the two halves read as
          // two halves of a table, and both team briefs have room above them. Aiming at the audience
          // bowl eases the eye back a further quarter, which is what brings the stands into view.
          const cam=camera as THREE.PerspectiveCamera;
          const base=sidePickDistance(halfW,halfH,cam.fov,cam.aspect||1.6);
          const want=pickSeat?.current?1:0;
          seatZoom.current+=(want-seatZoom.current)*Math.min(1,dt*4.5);
          const distance=base*(1+.28*seatZoom.current);
          const elevation=THREE.MathUtils.degToRad(SIDE_PICK_ELEVATION);
          pickEye.set(0,Math.sin(elevation)*distance,Math.cos(elevation)*distance);
          pickLook.set(0,0,0);
          camera.position.lerp(pickEye,easePos);
          pickNow.lerp(pickLook,easeLook);
          camera.up.set(0,1,0);
          camera.lookAt(pickNow);
        }else{
          // Chassis choice behaves like the lineup intro's per-robot cut: the camera rests on a low
          // three-quarter view of the start cluster and, as the pointer settles on a chassis, glides
          // in to the same close framing the intro uses for that robot, then pulls back.
          camera.up.set(0,1,0);
          const list=f.robots.filter(r=>r.team===pickView.team&&r.role!=='aerial');
          const hovered=pickHover?.current??null;
          if(hovered)pickAt.current.id=hovered;
          const shot2=list.find(r=>r.id===pickAt.current.id)||null;
          const vFov=THREE.MathUtils.degToRad((camera as THREE.PerspectiveCamera).fov||42);
          let cx=0,cz=0,spread=1.4;
          for(const r of list){const p=point(r,0,f.arena.width,f.arena.height);cx+=p.x;cz+=p.z;}
          if(list.length){cx/=list.length;cz/=list.length;}
          for(const r of list){const p=point(r,0,f.arena.width,f.arena.height);spread=Math.max(spread,Math.hypot(p.x-cx,p.z-cz)*2);}
          if(hovered&&shot2){
            const hw=f.robot_models?.[String(shot2.model_slot??shot2.slot)],dims=hw?.stowed_m||[.6,.6,.5];
            const size=Math.max(dims[0],dims[1]),tall=dims[2]||.5,p=point(shot2,0,f.arena.width,f.arena.height);
            const a=shot2.heading+.8,d=(1.35+size*1.9)*.96,h=Math.max(.6,tall*1.05)+.32;
            pickEye.set(p.x+Math.cos(a)*d,p.y+h,p.z+Math.sin(a)*d);
            pickLook.set(p.x,p.y+tall*.42,p.z);
          }else{
            const side=pickView.team==='red'?1:-1;
            const wide=Math.max((spread*.75+1.5)/Math.tan(vFov/2),4.4);
            pickEye.set(cx+side*wide*.6,1.4+wide*.3,cz+wide*.42);
            pickLook.set(cx,.55,cz);
          }
          const half={x:f.arena.width/2+1.2,z:f.arena.height/2+1.2};
          pickEye.x=THREE.MathUtils.clamp(pickEye.x,-half.x,half.x);pickEye.z=THREE.MathUtils.clamp(pickEye.z,-half.z,half.z);
          // No snap on entry: the same ease carries the eye from the side overview down over the start
          // cluster, and keeps carrying it while the pointer moves from chassis to chassis.
          camera.position.lerp(pickEye,easePos);
          pickNow.lerp(pickLook,easeLook);
          camera.lookAt(pickNow);
        }
        previousMode.current='pick';
        // Published for the tests: the picker's own eye, updated every frame while a stage is running.
        gl.domElement.dataset.pickEye=`${camera.position.x.toFixed(2)},${camera.position.y.toFixed(2)},${camera.position.z.toFixed(2)}`;
        gl.domElement.dataset.pickSeat=pickSeat?.current?'1':'0';
        return;
      }
    }
    // Leaving the picker resets it, so the next match starts its own glide from the live pose.
    pickInit.current=false;
    // The intro owns the camera; the chosen broadcast mode resumes from its default framing afterwards.
    if(shot){const f=feed.current.frame;if(cut.current.key!==shot.key)cut.current={key:shot.key,at:clock.elapsedTime};if(f)introCamera(shot,Math.min(1,(clock.elapsedTime-cut.current.at)/Math.max(.2,shot.length)),f,camera,look);previousMode.current='intro';return;}
    // The sight line the reticle points along. A pilot who has the lobbed-fire sight up looks where
    // they aim, not down the barrel, so the camera takes the cockpit angles and the launcher
    // elevates on its own underneath. The lens itself keeps the plain first-person fov: only the
    // aperture is magnified, by the sight pass at the end of the frame.
    const scoped=mode==='fpv'&&lobScope.active;
    const fov=mode==='fpv'?FPV_FOV:BROADCAST_FOV;
    const far=mode==='fpv'?160:220;
    {
      // Applied every frame: the scope flips the lens without changing the camera mode.
      const cam=camera as THREE.PerspectiveCamera;
      if(cam.fov!==fov||cam.far!==far){cam.fov=fov;cam.far=far;cam.updateProjectionMatrix();}
    }
    // Every mode below writes its own camera pose; `settle` then eases out of the pose the previous
    // mode left behind, so first person → follow → broadcast is one continuous move, not a cut.
    const blendQ=blend.current;
    const settle=()=>{
      if(blendQ.t>=1)return;
      blendQ.t=Math.min(1,blendQ.t+dt/TRANSITION_S);
      const a=blendQ.t*blendQ.t*(3-2*blendQ.t);
      camera.position.lerp(blendQ.fromPos,1-a);
      blendTo.copy(camera.quaternion);
      camera.quaternion.copy(blendQ.fromQuat).slerp(blendTo,a);
    };
    // Restarting the ease is what makes moves *inside* one mode (the heavy's shoulder camera) glide
    // too: the branch below swaps the pose, and the blend carries the eye across from where it was.
    const restart=()=>{blendQ.fromPos.copy(camera.position);blendQ.fromQuat.copy(camera.quaternion);blendQ.t=0;};
    if(previousMode.current!==mode){
      // The camera still holds the old mode's pose here, so that is what the move starts from.
      blendQ.fromPos.copy(camera.position);blendQ.fromQuat.copy(camera.quaternion);blendQ.t=0;
      previousMode.current=mode;
      if(mode==='orbit'){camera.position.set(...BROADCAST_EYE);controls.current?.target.set(...BROADCAST_TARGET);}}
    // Only the top view leans the world over; every other mode wants the normal world up, and the
    // orbit controls derive their own gimbal from it.
    if(mode!=='top')camera.up.set(0,1,0);
    // The top view is written every frame, not once on the switch: the transition eases from the
    // previous pose back over the new one, so a one-shot pose would be pulled away and the camera
    // would park at the old angle. The distance fits the whole arena on whichever axis is tighter,
    // so the overhead view looks the same in every window shape.
    if(mode==='top'){
      const arena=feed.current.frame?.arena,cam=camera as THREE.PerspectiveCamera;
      const w=arena?.width??28,h=arena?.height??15;
      const tanV=Math.tan(THREE.MathUtils.degToRad(cam.fov)/2),tanH=tanV*Math.max(.2,cam.aspect);
      // The overhead scan frames the field at `TOP_SCAN_SCALE` of the largest size that fits: the
      // broadcast plates sit along the top of the canvas, so a field that just touched the frame edge
      // had its far half behind them.
      const dist=Math.max((h/2+1.6)/tanV,(w/2+1.6)/tanH,6)/TOP_SCAN_SCALE;
      // Link Start: the scan is the chassis picker, so a machine under the pointer is what the viewer
      // is looking at. The eye glides straight down onto it until it fills about 30 % of the picture,
      // and pulls all the way back out when the pointer leaves — the overhead framing never tilts, so
      // the move is a dolly, not a cut, and the robot stays centred while it happens.
      const dive=linkDive.current,hovered=linkHover?.current??null,scan=feed.current.frame;
      const robot=hovered&&scan?scan.robots.find(r=>r.id===hovered)??null:null;
      if(robot){
        const model=scan!.robot_models?.[String(robot.model_slot??robot.slot)],dims=model?.stowed_m||[.6,.6,.5];
        const size=Math.max(dims[0],dims[1],dims[2]||.5),p=point(robot,0,w,h);
        // 30 % of the frame height: the picture is `2 * near * tanV` tall at the eye.
        dive.near=THREE.MathUtils.clamp(size/(.6*tanV),1.6,dist);
        dive.spot=[p.x,p.z];
      }
      const want=robot?1:0;
      dive.k+=(want-dive.k)*Math.min(1,dt*3.4);
      const k=dive.k<.001?0:dive.k,spot=dive.spot??[0,0];
      const near=dist+(dive.near-dist)*k;
      camera.position.set(spot[0]*k,near,spot[1]*k);
      camera.up.set(0,0,-1);
      camera.lookAt(spot[0]*k,0,spot[1]*k);
    }
    if(mode==='cinematic'){const a=clock.elapsedTime*.052;camera.position.set(Math.sin(a)*26,CINEMATIC_EYE,Math.cos(a)*24);camera.lookAt(0,0,0);}
    // First person is the gun: the eye sits at the barrel and looks along the same gimbal the model
    // draws, so the crosshair and the barrel can never disagree in yaw or pitch. The angles come
    // from the engine frame (interpolated between 20 Hz samples), and a fast follow keeps the view
    // continuous while a pilot's input is in flight.
    if(mode==='fpv'){const f=feed.current.frame,r=f?.robots.find(r=>r.id===selected);if(f&&r){
      // The rules keep the view pose while the chassis is destroyed; nothing turns until respawn.
      if(!r.alive){dead.current=true;settle();return;}
      const own=pilot&&pilot===r.id;
      const was=feed.current.previous?.robots.find(o=>o.id===r.id)||r,alpha=feedAlpha(feed.current);
      robotWorld(feed.current,r,alpha,eyePoint);
      // 27 % above the muzzle line: the eye clears the gun without leaving its line of sight. A heavy
      // with no launcher has no gun to ride, so the arm view below places its own low eye instead.
      // Both fitted and installed count: the lens changes over the moment the module is bolted on, so
      // a heavy never keeps the arm camera after its barrel is installed.
      const heavy=r.role==='heavy';
      const hd=(was.heading??r.heading??0)+yawDelta(was.heading??r.heading??0,r.heading??0)*alpha;
      const core=f.assemblies?.[r.team];
      const feeding=heavy&&!!core&&['moving','inserting','buffered'].includes(core.stage)&&(r.last_raw_zones??[]).includes(`${r.team}_assembly`);
      // Mining and feeding a core cannot be read from inside the machine, so those steps are watched
      // in the same third-person chase view as the 跟随 camera. `carrying` is deliberately left out:
      // once the gripper holds its unit and the robot drives off the pad the cockpit takes over again,
      // which is what the third unit riding in the jaws needs.
      const mining=heavy&&!!r.unit_pickup&&r.unit_pickup.stage!=='carrying';
      if(mining||feeding){
        const view=workEye.current;
        if(view.id!==r.id){restart();view.id=r.id;view.look=null;view.eye.copy(camera.position);}
        const focus=point(r,.40,f.arena.width,f.arena.height);
        if(!view.look)view.look=focus.clone();
        else view.look.lerp(focus,Math.min(1,dt*6));
        workEyeAt.set(view.look.x-Math.cos(hd)*FOLLOW_BACK,view.look.y+FOLLOW_EYE,view.look.z-Math.sin(hd)*FOLLOW_BACK);
        workEyeAt.x=THREE.MathUtils.clamp(workEyeAt.x,-f.arena.width/2+.6,f.arena.width/2+.6);
        workEyeAt.z=THREE.MathUtils.clamp(workEyeAt.z,-f.arena.height/2+.6,f.arena.height/2+.6);
        view.eye.lerp(workEyeAt,Math.min(1,dt*3));
        camera.position.copy(view.eye);
        camera.up.set(0,1,0);camera.lookAt(view.look);
        dead.current=false;
        settle();
        return;
      }
      if(workEye.current.id){restart();workEye.current.id='';}
      const armView=heavy&&!['fitted','installed'].includes(r.launcher??'');
      if(!armView)eyePoint.y+=(r.muzzle_height_m??.5)*FPV_EYE_LIFT;
      if(armView){
        const arm=armEye.current;
        if(arm.id!==r.id){arm.id=r.id;arm.look=null;}
        // The eye sits on the chassis centreline a little ahead of the arm mast and at the height of
        // the model's own arm camera, taken from the same interpolated pose as the hull so it cannot
        // twitch between 20 Hz samples. The mast then reads as a column at the edge of the lens.
        eyePoint.x+=Math.cos(hd)*ARM_EYE_FORWARD;
        eyePoint.z+=Math.sin(hd)*ARM_EYE_FORWARD;
        eyePoint.y+=ARM_EYE_M;
        const yaw=barrelView(r).yaw;
        const working=!!core&&['moving','inserting','buffered','verifying'].includes(core.stage);
        const workbench=working?(f.arena.assembly_frames as Record<string,{origin?:number[];z0_m?:number}>|undefined)?.[r.team]:undefined;
        const boom=armBooms.get(r.id);
        if(boom&&working){
          // Idle arm work that the grip camera cannot cover (verifying a core) still follows the boom's
          // reach axis, which is what a driver watches. The wrist keeps its own pitch and roll, so the
          // lens is never steered by the jaws the way following the gripper would.
          eyeLook.copy(boom.at).addScaledVector(boom.dir,ARM_BOOM_LOOK);
        }else if(workbench?.origin){
          const origin=workbench.origin,plinth=point({x:origin[0],y:origin[1]} as Robot,0,f.arena.width,f.arena.height);
          eyeLook.set(plinth.x,plinth.y+(workbench.z0_m??.4)+.05,plinth.z);
        }else eyeLook.set(eyePoint.x+Math.cos(yaw)*5,eyePoint.y-.35,eyePoint.z+Math.sin(yaw)*5);
        if(!arm.look)arm.look=eyeLook.clone();
        else arm.look.lerp(eyeLook,Math.min(1,dt*9));
        camera.position.copy(eyePoint);
        camera.up.set(0,1,0);camera.lookAt(arm.look);
        dead.current=false;
        settle();
        return;
      }
      // The barrel's own world angles, interpolated between the 20 Hz samples exactly like the
      // model's turret and gun, so the view pitch is the barrel pitch on flat ground, ramps and
      // while the hull is climbing.
      const nowView=barrelView(r),wasView=barrelView(was);
      const targetYaw=(wasView.yaw+yawDelta(wasView.yaw,nowView.yaw)*alpha+Math.PI*2)%(Math.PI*2);
      const targetPitch=wasView.pitch+(nowView.pitch-wasView.pitch)*alpha;
      const view=eye.current;
      // A respawn teleports the chassis, so the new pose is taken as-is instead of being swept to.
      if(view.id!==r.id||dead.current){view.id=r.id;view.yaw=targetYaw;view.pitch=targetPitch;dead.current=false;}
      if(own){
        // Piloting: the eye takes the interpolated gimbal angle itself. The robot model poses its
        // turret with the very same alpha, so the view pitch is the barrel pitch — no second easing.
        // With the lobbed-fire scope up the gun is pointed far above the target, so the eye keeps the
        // cockpit's own sight line instead: the reticle stays on the point the shell has to hit.
        if(scoped){view.yaw=lobScope.yaw;view.pitch=lobScope.pitch;}
        else{view.yaw=targetYaw;view.pitch=targetPitch;}
      }else if(scoped){
        view.yaw=lobScope.yaw;view.pitch=lobScope.pitch;
      }else{
        const maxStep=EYE_RATE*dt;
        view.yaw=(view.yaw+Math.max(-maxStep,Math.min(maxStep,yawDelta(view.yaw,targetYaw))))%(Math.PI*2);
        view.pitch+=Math.max(-maxStep,Math.min(maxStep,targetPitch-view.pitch));
      }
      camera.position.copy(eyePoint);
      eyeLook.set(eyePoint.x+Math.cos(view.yaw)*Math.cos(view.pitch),eyePoint.y+Math.sin(view.pitch),eyePoint.z+Math.sin(view.yaw)*Math.cos(view.pitch));
      camera.up.set(0,1,0);camera.lookAt(eyeLook);
    }}
    if(mode==='follow'){
      const f=feed.current.frame;
      if(f){
        // A drone is followed as a body of its own. Selecting the hangar does not park the camera on
        // the hangar either: it rides the lead drone, while every drone of that hangar is ringed.
        const onField=droneOnField(f,selected);
        const hangar=onField?null:f.robots.find(r=>r.id===selected&&r.role==='aerial');
        const drone=onField?.drone??leadDrone(hangar);
        if(drone){
          const owner=onField?.robot??hangar!;
          const previous=feed.current.previous?.robots.find(r=>r.id===owner.id)?.drones?.find(d=>d.id===drone.id)||drone;
          const alpha=feedAlpha(feed.current);
          const focus=point(drone,0,f.arena.width,f.arena.height).lerp(point(previous,0,f.arena.width,f.arena.height),1-alpha);
          target.lerp(focus,Math.min(1,dt*8));
          const speed=Math.hypot(drone.vx,drone.vy),angle=speed>.15?Math.atan2(drone.vy,drone.vx):droneYaw(drone.quaternion);
          const desired=target.clone().add(new THREE.Vector3(-Math.cos(angle)*DRONE_FOLLOW_BACK,DRONE_FOLLOW_EYE,-Math.sin(angle)*DRONE_FOLLOW_BACK));
          desired.x=THREE.MathUtils.clamp(desired.x,-f.arena.width/2+.6,f.arena.width/2-.6);
          desired.z=THREE.MathUtils.clamp(desired.z,-f.arena.height/2+.6,f.arena.height/2-.6);
          camera.position.lerp(desired,Math.min(1,dt*4));camera.lookAt(target);
        }else{
          const r=f.robots.find(r=>r.id===selected);
          if(r){target.lerp(point(r,.40),Math.min(1,dt*6));const angle=r.heading;const desired=target.clone().add(new THREE.Vector3(-Math.cos(angle)*FOLLOW_BACK,FOLLOW_EYE,-Math.sin(angle)*FOLLOW_BACK));desired.x=THREE.MathUtils.clamp(desired.x,-f.arena.width/2+.6,f.arena.width/2-.6);desired.z=THREE.MathUtils.clamp(desired.z,-f.arena.height/2+.6,f.arena.height/2-.6);camera.position.lerp(desired,Math.min(1,dt*3));camera.lookAt(target);}
        }
      }
    }
    settle();
    // Sample ~1 s of frames and move the pixel ratio one notch toward the frame-time target.
    const p=perf.current;
    p.ceiling=mode==='fpv'?FPV_DPR[1]:BROADCAST_DPR[1];
    if(p.ratio>p.ceiling){p.ratio=p.ceiling;setDpr(p.ceiling);}
    p.time+=dt;p.frames++;
    if(p.time>=1){
      const avg=p.time/p.frames;p.time=0;p.frames=0;
      const next=avg>.019?Math.max(DPR_FLOOR,p.ratio-.12):avg<.0135?Math.min(p.ceiling,p.ratio+.08):p.ratio;
      if(Math.abs(next-p.ratio)>.01){p.ratio=next;setDpr(next);}
      // The shadow pass is the first cost to give up when the frame budget is already missed, but only
      // down to every fourth frame: a map refreshed a few times a second leaves each robot's shadow
      // trailing a step behind it, which reads as lag rather than as a cheaper picture.
      p.shadow=avg>.026?Math.min(4,p.shadow+1):avg<.018?Math.max(1,p.shadow-1):p.shadow;
    }
  });
  useFrame(()=>{if(!audio?.enabled)return;const focus=mode==='orbit'?controls.current?.target||origin:mode==='follow'?target:origin;ear.copy(camera.position).sub(focus);ear.setLength(Math.min(ear.length(),9)).add(focus);camera.getWorldDirection(ahead);up.set(0,1,0).applyQuaternion(camera.quaternion);audio.listen(ear,ahead,up,feed.current.frame?.arena);});
  useFrame(()=>{audio?.drones(feed.current.frame);},-2);
  // A fixed directional light does not need new shadows for camera motion, only for moving casters.
  // While the field moves the map follows every rendered frame, so a shadow stays under its robot
  // instead of jumping after it; the pass is a few dozen merged casters and costs well under a
  // millisecond on the main pass's budget. Only a machine that cannot hold the frame budget refreshes
  // it every second to fourth frame. A changed paused frame always refreshes it once.
  useFrame(({gl,scene,camera})=>{
    const f=feed.current,s=shadow.current;
    const slot=(s.slot+1)%perf.current.shadow;
    if(f.generation!==s.generation||f.paused!==s.paused||(f.paused?f.frame!==s.frame:slot===0)){
      gl.shadowMap.needsUpdate=true;s.frame=f.frame;s.generation=f.generation;s.paused=f.paused;
    }
    s.slot=slot;
    // The frame is drawn either straight to the canvas or, with the lobbed-fire sight on the eye,
    // through the lens pass that magnifies the aperture and keeps the rest of the field plain.
    renderSight(scene as THREE.Scene,camera as THREE.PerspectiveCamera,size.width,size.height,FPV_FOV,mode==='fpv');
    // Draw-call accounting for the diagnostics panel: it is the cheapest way to tell an aliasing
    // bound frame from a geometry bound one without a profiler. The scene census (how many meshes,
    // materials and textures the arena is built from) is what says whether a frame is bound by draw
    // calls rather than by shading, so it rides along with the same sample.
    if((s.shown=(s.shown??0)+1)%30===0){
      const r=gl.info.render;
      let meshes=0,casters=0;
      scene.traverse(o=>{if((o as THREE.Mesh).isMesh){meshes++;if(o.castShadow)casters++;}});
      (window as unknown as {arenaRender?:unknown}).arenaRender={calls:r.calls,triangles:r.triangles,frame:r.frame,dpr:perf.current.ratio,
        meshes,shadowCasters:casters,materials:gl.info.memory.geometries,textures:gl.info.memory.textures,shadowEvery:perf.current.shadow,
        eye:[camera.position.x,camera.position.y,camera.position.z].map(v=>Math.round(v*100)/100),up:[camera.up.x,camera.up.y,camera.up.z]};
    }
    // Copy the just-rendered frame synchronously, before WebGL releases its buffer.
    onRender();
  },1);
  return <OrbitControls ref={controls} enabled={mode==='orbit'&&!shot&&!pickView} enableDamping dampingFactor={.075} maxPolarAngle={Math.PI*.47} minDistance={4} maxDistance={72} target={BROADCAST_TARGET}/>;
}

// RMUC 2027 lighting: the broadcast fill plus a faint studio environment for reflections, so the baked contact shadows
// (which scale the fill) and the surfaces' bump and roughness read; the key light's shadow map covers only the field,
// four times as finely.
function FieldLights2027(){
  const {gl,scene}=useThree();
  useEffect(()=>{const pmrem=new THREE.PMREMGenerator(gl),env=pmrem.fromScene(new RoomEnvironment(),.04).texture;
    scene.environment=env;scene.environmentIntensity=.14;
    return()=>{scene.environment=null;scene.environmentIntensity=1;env.dispose();pmrem.dispose();};},[gl,scene]);
  return <><hemisphereLight args={['#e4eefb','#1c2128',1.65]}/><ambientLight intensity={.12}/><directionalLight position={[4,26,9]} intensity={3.1} color="#f4f6ff" castShadow shadow-mapSize={[4096,4096]} shadow-camera-left={-17} shadow-camera-right={17} shadow-camera-top={17} shadow-camera-bottom={-17} shadow-bias={-.0002} shadow-normalBias={.015}/></>;
}

class SceneBoundary extends Component<{children:ReactNode;onRetry:()=>void;audio?:ArenaAudio},{failed:boolean}>{
  state={failed:false};
  static getDerivedStateFromError(){return {failed:true};}
  componentDidCatch(){this.props.audio?.drones(null);}
  render(){return this.state.failed?<div className="scene-recovery"><p>战场模型暂时无法加载</p><button onClick={()=>{this.props.onRetry();this.setState({failed:false});}}>重新加载战场</button></div>:this.props.children;}
}
// Everything the scene tree is built from, as one comparable string: the 20 Hz frame updates only
// move robots inside `feed`, so rebuilding the React tree for each of them is wasted work.
function sceneSignature(frame:Frame){
  let key=`${frame.season??''}|${frame.rules}|${frame.arena.layout_revision??''}|${frame.arena.asset}|${frame.arena.width}x${frame.arena.height}|${frame.arena.structure_assets?.base??''}|${frame.arena.structure_assets?.outpost??''}|${frame.arena.structure_assets?.core??''}|${frame.arena.assembly_frames?'a':''}${frame.runes?'r':''}${frame.outposts?'o':''}`;
  for(const r of frame.robots)key+=`|${r.id},${r.team},${r.role},${r.model_asset??''},${r.drones?.length??0}`;
  return key;
}

// The key light carries the only shadow pass. A pilot sits close to the field where a 512² map is
// indistinguishable from 768², so the map shrinks in first person and grows for the broadcast.
function Sun({mode}:{mode:CameraMode}){
  const light=useRef<THREE.DirectionalLight>(null),{gl}=useThree();
  useEffect(()=>{
    const l=light.current;if(!l)return;
    const size=mode==='fpv'?512:768;
    if(l.shadow.mapSize.x===size)return;
    l.shadow.mapSize.set(size,size);
    l.shadow.map?.dispose();l.shadow.map=null;
    gl.shadowMap.needsUpdate=true;
  },[mode,gl]);
  return <directionalLight ref={light} position={[4,26,9]} intensity={3.1} color="#f4f6ff" castShadow shadow-mapSize={[768,768]} shadow-camera-left={-28} shadow-camera-right={28} shadow-camera-top={24} shadow-camera-bottom={-24} shadow-bias={-.0004}/>;
}

// The side choice is made on the field itself and it is pure geometry: the half under the pointer
// lights up in its team colour, a scan band sweeps along it, its corner pylons rise and an energy
// wall stands up on the outer edge. A click there opens that side's chassis choice; the stands
// around the field are the third answer — pointing at the audience seats and clicking watches instead.
type PickZone=TeamId|'seat';
function HalfPicker({feed,onPick,onHover,onSpectate,seatHot}:{feed:MutableRefObject<RenderFeed>;onPick:(team:TeamId)=>void;onHover?:(zone:PickZone|null)=>void;onSpectate?:()=>void;seatHot?:MutableRefObject<boolean>}){
  const {camera,gl,size}=useThree();
  const arena=feed.current.frame?.arena,halfW=(arena?.width??28)/2,halfH=(arena?.height??15)/2;
  const midX={red:-halfW/2,blue:halfW/2},outerX={red:-halfW,blue:halfW};
  const pointer=useRef({x:-9999,y:-9999}),hot=useRef<PickZone|null>(null),hovered=useRef<PickZone|null|undefined>(undefined);
  const ray=useMemo(()=>new THREE.Raycaster(),[]),plane=useMemo(()=>new THREE.Plane(new THREE.Vector3(0,1,0),0),[]);
  const ndc=useMemo(()=>new THREE.Vector2(),[]),hit=useMemo(()=>new THREE.Vector3(),[]),edge3=useMemo(()=>new THREE.Vector3(),[]);
  // The zone is decided on the picker's base framing, not on the live eye: aiming at the stands pulls
  // the eye back, and deciding on the zoomed pose would move the field under a still pointer and flip
  // the answer back and forth.
  const zoneCam=useMemo(()=>new THREE.PerspectiveCamera(42,1.6,.1,400),[]);
  const zoneRay=useMemo(()=>new THREE.Raycaster(),[]);
  // Live-eye ground hit for the pointer ring, kept apart from the zone hit.
  const ringAt=useMemo(()=>new THREE.Vector3(),[]),ringHit=useMemo(()=>new THREE.Vector3(),[]);
  // Screen x of a point on the field in the picker's base framing, used to decide which half the
  // pointer is nearest to.
  const screenX=(x:number)=>{edge3.set(x,0,0).project(zoneCam);return (edge3.x*.5+.5)*size.width;};
  const floor=useRef<Partial<Record<TeamId,THREE.MeshBasicMaterial>>>({}),wall=useRef<Partial<Record<TeamId,THREE.MeshBasicMaterial>>>({});
  const scan=useRef<Partial<Record<TeamId,THREE.Mesh|null>>>({}),scanMat=useRef<Partial<Record<TeamId,THREE.MeshBasicMaterial>>>({});
  const pylons=useRef<Record<TeamId,THREE.Mesh[]>>({red:[],blue:[]}),pylonMat=useRef<Record<TeamId,THREE.MeshBasicMaterial[]>>({red:[],blue:[]});
  const edge=useRef<Partial<Record<TeamId,THREE.MeshBasicMaterial>>>({});
  const cursor=useRef<THREE.Mesh>(null),cursorMat=useRef<THREE.MeshBasicMaterial>(null);
  const bowlMat=useRef<THREE.MeshBasicMaterial>(null);
  // The audience bowl is drawn as a flat frame around the playfield: one shape with the arena cut out
  // of it, so the pointer has something lit to aim at on every side of the field.
  const bowlGeo=useMemo(()=>{
    const shape=new THREE.Shape();
    const ox=halfW+3.2,oz=halfH+3.2;
    shape.moveTo(-ox,-oz);shape.lineTo(ox,-oz);shape.lineTo(ox,oz);shape.lineTo(-ox,oz);shape.closePath();
    const hole=new THREE.Path();
    hole.moveTo(-halfW,-halfH);hole.lineTo(-halfW,halfH);hole.lineTo(halfW,halfH);hole.lineTo(halfW,-halfH);hole.closePath();
    shape.holes.push(hole);
    return new THREE.ShapeGeometry(shape);
  },[halfW,halfH]);
  // Corner pylons are the only tall elements, so hovering a side reads from any camera angle.
  const corners=useMemo(()=>[[-1,-1],[-1,1],[1,-1],[1,1]].map(([sx,sz])=>({sx,sz})),[]);
  useEffect(()=>{
    const move=(event:PointerEvent)=>{const rect=gl.domElement.getBoundingClientRect();pointer.current={x:event.clientX-rect.left,y:event.clientY-rect.top};};
    window.addEventListener('pointermove',move,{passive:true});
    return()=>window.removeEventListener('pointermove',move);
  },[gl]);
  useEffect(()=>{
    const down=(event:PointerEvent)=>{
      if(event.button!==0)return;
      if(hot.current==='red'||hot.current==='blue')onPick(hot.current);
      else if(hot.current==='seat')onSpectate?.();
    };
    gl.domElement.addEventListener('pointerdown',down);
    return()=>gl.domElement.removeEventListener('pointerdown',down);
  },[gl,onPick,onSpectate]);
  useFrame(({clock})=>{
    const {width:w,height:h}=size;
    ndc.set(pointer.current.x/w*2-1,-(pointer.current.y/h)*2+1);
    // The zone is read from the base framing (fixed 45° eye at the fitted distance), so the pull-back
    // for the stands cannot move the field under a still pointer.
    const live=camera as THREE.PerspectiveCamera;
    zoneCam.fov=live.fov;zoneCam.aspect=live.aspect||1.6;zoneCam.updateProjectionMatrix();
    const base=sidePickDistance(halfW,halfH,zoneCam.fov,zoneCam.aspect);
    const elevation=THREE.MathUtils.degToRad(SIDE_PICK_ELEVATION);
    zoneCam.position.set(0,Math.sin(elevation)*base,Math.cos(elevation)*base);
    zoneCam.up.set(0,1,0);zoneCam.lookAt(0,0,0);zoneCam.updateMatrixWorld();
    zoneRay.setFromCamera(ndc,zoneCam);
    // Everything outside the playfield footprint is the audience: the stands ring the field on every
    // side and rise above it, so a ray that misses the ground plane still points into the seating.
    let team:PickZone='seat';
    if(zoneRay.ray.intersectPlane(plane,hit)&&Math.abs(hit.x)<=halfW&&Math.abs(hit.z)<=halfH){
      const redX=screenX(-halfW/2),blueX=screenX(halfW/2);
      team=Math.abs(pointer.current.x-redX)<=Math.abs(pointer.current.x-blueX)?'red':'blue';
    }
    // The pointer ring follows the live eye; it is only shown while a half is pointed at.
    ray.setFromCamera(ndc,camera);
    const hasRing=!!ray.ray.intersectPlane(plane,ringHit);
    ringAt.copy(ringHit);
    hot.current=team;
    gl.domElement.dataset.pickHalf=team??'';
    gl.domElement.dataset.pickHit=`${hit.x.toFixed(1)},${hit.z.toFixed(1)}`;
    // Only notify on a change: the caption above the field follows the hovered half without a
    // React pass on every frame.
    if(team!==hovered.current){hovered.current=team;onHover?.(team);}
    const t=clock.elapsedTime;
    for(const id of ['red','blue'] as const){
      const on=team===id,phase=id==='red'?0:1.7;
      const glow=floor.current[id];
      if(glow)glow.opacity=on?.3+.08*Math.sin(t*3.6):.07+.03*Math.sin(t*1.1+phase);
      const slab=wall.current[id];
      if(slab)slab.opacity=on?.48+.12*Math.sin(t*4.2):.06;
      const band=scan.current[id];
      if(band){band.visible=on;band.position.z=-halfH+((t*3)%(halfH*2));}
      const bandMat=scanMat.current[id];
      if(bandMat)bandMat.opacity=.3+.15*Math.sin(t*6);
      const line=edge.current[id];
      if(line)line.opacity=on?.85:.18;
      pylonMat.current[id].forEach(mat=>{mat.opacity=on?.9:.22;});
      pylons.current[id].forEach((mesh,i)=>{mesh.position.y=on?.95+.22*Math.sin(t*2.6+i*1.3):.42;mesh.scale.y=on?1+.18*Math.sin(t*3.4+i):.62;});
    }
    if(cursor.current)cursor.current.visible=team==='red'||team==='blue';
    if((team==='red'||team==='blue')&&cursor.current){
      const mat=cursorMat.current;
      if(mat)mat.color.set(TEAM_COLORS[team]);
      if(hasRing)cursor.current.position.set(ringAt.x,.18,ringAt.z);
      else cursor.current.position.set(hit.x,.18,hit.z);
      const pulse=1+.1*Math.sin(t*9);
      cursor.current.scale.set(pulse,pulse,pulse);
    }
    // The audience bowl answers the pointer the same way a half does, in instrument cyan: a lit frame
    // just outside the playfield, so the third answer is visible before it is clicked. It also tells the
    // director to pull the camera back, which is what makes the stands readable while they are aimed at.
    const bowl=bowlMat.current;
    if(seatHot)seatHot.current=team==='seat';
    if(bowl){
      const on=team==='seat';
      bowl.opacity=on?.3+.1*Math.sin(t*4.4):.055+.02*Math.sin(t*1.3);
      bowl.color.set(on?'#bdeaff':'#9fd8ef');
    }
  });
  return <group>
    {/* Audience bowl: the third answer. Sits just above the floor so the lit frame reads around the
        whole field without ever covering it. */}
    <mesh geometry={bowlGeo} position={[0,.07,0]} rotation={[-Math.PI/2,0,0]} renderOrder={10}>
      <meshBasicMaterial ref={bowlMat} color="#9fd8ef" transparent opacity={.06} depthWrite={false} side={THREE.DoubleSide} blending={THREE.AdditiveBlending}/>
    </mesh>
    {(['red','blue'] as const).map(id=><group key={id}>
      <mesh position={[midX[id],.09,0]} rotation={[-Math.PI/2,0,0]} renderOrder={11}>
        <planeGeometry args={[halfW,halfH*2]}/>
        <meshBasicMaterial ref={mat=>{if(mat)floor.current[id]=mat;}} color={TEAM_COLORS[id]} transparent opacity={.07} depthWrite={false} depthTest={false} blending={THREE.AdditiveBlending}/>
      </mesh>
      <mesh position={[midX[id],.11,0]} rotation={[-Math.PI/2,0,0]} renderOrder={12}>
        <ringGeometry args={[Math.min(halfW,halfH)*.42,Math.min(halfW,halfH)*.47,64]}/>
        <meshBasicMaterial color={TEAM_COLORS[id]} transparent opacity={.16} depthWrite={false} depthTest={false} side={THREE.DoubleSide}/>
      </mesh>
      {/* Scanning band: a lit strip travelling along the half, only while the side is hovered. */}
      <mesh ref={el=>{scan.current[id]=el;}} position={[midX[id],.13,0]} rotation={[-Math.PI/2,0,0]} visible={false} renderOrder={13}>
        <planeGeometry args={[halfW,.6]}/>
        <meshBasicMaterial ref={mat=>{if(mat)scanMat.current[id]=mat;}} color={TEAM_COLORS[id]} transparent opacity={.3} depthWrite={false} depthTest={false} blending={THREE.AdditiveBlending}/>
      </mesh>
      {/* Energy wall on the outer edge of the half. */}
      <mesh position={[outerX[id],1.1,0]} rotation={[0,Math.PI/2,0]} renderOrder={12}>
        <planeGeometry args={[halfH*2,2.2]}/>
        <meshBasicMaterial ref={mat=>{if(mat)wall.current[id]=mat;}} color={TEAM_COLORS[id]} transparent opacity={.06} depthWrite={false} side={THREE.DoubleSide} blending={THREE.AdditiveBlending}/>
      </mesh>
      <mesh position={[outerX[id],.12,0]} rotation={[-Math.PI/2,0,0]} renderOrder={13}>
        <planeGeometry args={[.16,halfH*2]}/>
        <meshBasicMaterial ref={mat=>{if(mat)edge.current[id]=mat;}} color={TEAM_COLORS[id]} transparent opacity={.18} depthWrite={false} depthTest={false} blending={THREE.AdditiveBlending}/>
      </mesh>
      {corners.map(({sx,sz})=><mesh key={`${sx}:${sz}`} ref={el=>{if(el&&!pylons.current[id].includes(el))pylons.current[id].push(el);}} position={[midX[id]+sx*(halfW/2-.8),.42,sz*(halfH-.8)]}>
        <boxGeometry args={[.5,2,.5]}/>
        <meshBasicMaterial ref={mat=>{if(mat&&!pylonMat.current[id].includes(mat))pylonMat.current[id].push(mat);}} color={TEAM_COLORS[id]} transparent opacity={.22} depthWrite={false} blending={THREE.AdditiveBlending}/>
      </mesh>)}
    </group>)}
    {/* Ground reticle pinned to the pointer, so the half about to be taken is obvious. */}
    <mesh ref={cursor} rotation={[-Math.PI/2,0,0]} position={[0,.18,0]} visible={false} renderOrder={14}>
      <ringGeometry args={[.95,1.12,48]}/>
      <meshBasicMaterial ref={cursorMat} color="#ffffff" transparent opacity={.75} side={THREE.DoubleSide} depthWrite={false} depthTest={false} blending={THREE.AdditiveBlending}/>
    </mesh>
  </group>;
}


// Pre-match picker: no dialog and no list — the robot nearest the pointer on the field lights up
// and a click takes it over. Screen-space proximity keeps this independent of the model colliders,
// so a spinning turret or a folded mast can never make a chassis unclickable.
// The same probe serves the in-match Link Start scan: `canvasOnly` drops the pointer whenever it
// sits on cockpit chrome, so a panel docked over the field can never steal a chassis, and `radius`
// widens the catch circle for the overhead view where every chassis is small.
function PickProbe({pick,feed,hover,onPick,onHover,team,radius=82,hysteresis=1.7,canvasOnly=false,dataKey='pickHover'}:{pick:boolean;feed:MutableRefObject<RenderFeed>;hover:MutableRefObject<string|null>;onPick?:(id:string)=>void;onHover?:(id:string|null)=>void;team?:TeamId;radius?:number;hysteresis?:number;canvasOnly?:boolean;dataKey?:string}){
  const {camera,gl,size}=useThree();
  const pointer=useRef({x:-9999,y:-9999});
  useEffect(()=>{
    const el=gl.domElement;
    const move=(event:PointerEvent)=>{
      if(canvasOnly&&event.target!==el){pointer.current={x:-9999,y:-9999};return;}
      const rect=el.getBoundingClientRect();pointer.current={x:event.clientX-rect.left,y:event.clientY-rect.top};
    };
    window.addEventListener('pointermove',move,{passive:true});
    return()=>window.removeEventListener('pointermove',move);
  },[gl,canvasOnly]);
  // The click is taken from the canvas itself instead of a three.js raycast: the same proximity that
  // drives the highlight decides the target, so a chassis is clickable exactly where it lights up.
  useEffect(()=>{
    if(!pick)return;
    const down=(event:PointerEvent)=>{if(event.button===0&&hover.current)onPick?.(hover.current);};
    gl.domElement.addEventListener('pointerdown',down);
    return()=>gl.domElement.removeEventListener('pointerdown',down);
  },[pick,gl,onPick,hover]);
  const v=useMemo(()=>new THREE.Vector3(),[]),reported=useRef<string|null>(null),scores=useRef(new Map<string,number>());
  // The settled chassis is latched together with the pointer position that picked it: while the
  // pointer rests there the camera may glide in without the projection shifting the choice around.
  const latch=useRef({id:null as string|null,x:0,y:0});
  useFrame(()=>{
    if(!pick){hover.current=null;latch.current.id=null;return;}
    const f=feed.current.frame;if(!f)return;
    const {width:w,height:h}=size,{x,y}=pointer.current;
    if(latch.current.id&&Math.hypot(x-latch.current.x,y-latch.current.y)<=16){
      // Pointer is resting: keep the latched chassis while the camera glides in to inspect it.
    }else{
      // Only chassis that are actually on screen can be taken: with the camera pushed in on one robot
      // the others must not steal the pointer through an off-screen projection.
      let best:string|null=null,bestScore=1;
      scores.current.clear();
      for(const r of f.robots){
        if(r.role==='aerial')continue;
        if(team&&r.team!==team)continue;
        const wx=r.x-f.arena.width/2,wz=r.y-f.arena.height/2;
        v.set(wx,(r.z??0)+0.35,wz).project(camera);
        if(v.z>1)continue;
        const sx=(v.x*.5+.5)*w,sy=(-v.y*.5+.5)*h;
        if(sx<-30||sx>w+30||sy<-30||sy>h+30)continue;
        const near=THREE.MathUtils.clamp(1.5-Math.hypot(wx-camera.position.x,wz-camera.position.z)/22,.6,1.5);
        const score=Math.hypot(sx-x,sy-y)/(radius*near);
        scores.current.set(r.id,score);
        if(score<bestScore){bestScore=score;best=r.id;}
      }
      // Hysteresis: a settled chassis keeps the highlight until the pointer is clearly nearer to
      // another one or leaves it, so neighbours never trade the choice back and forth. The overhead
      // scan turns it off (`hysteresis` 1) because there the pointer must simply follow the nearest
      // chassis instead of holding on to the first one it crossed.
      const settled=latch.current.id,settledScore=settled?scores.current.get(settled):undefined;
      if(settled&&settledScore!==undefined){
        if(settledScore<=1)best=settled;
        else if(hysteresis>1&&bestScore>=settledScore*.62)best=settledScore<=hysteresis?settled:null;
      }
      hover.current=best;
      latch.current={id:best,x,y};
    }
    const settledId=hover.current;
    // Also published on the canvas so the picker is testable without reading three.js state.
    gl.domElement.dataset[dataKey]=settledId??'';
    // The hovered chassis also drives a DOM card, so the report is pushed only when it changes.
    if(settledId!==reported.current){reported.current=settledId;onHover?.(settledId);}
  });  return null;
}

// Shader programs are built on the first frame that draws a material. With a full arena and a
// dozen robots that first frame is a long stall, and it used to land exactly when the match
// started. `compileAsync` walks the tree and compiles every program through the parallel shader
// compiler, so the work happens off the critical path during the pre-match countdown instead of
// dropping a one-second frame on the first rendered tick.
function Prewarm({feed}:{feed:MutableRefObject<RenderFeed>}){
  const {gl,scene,camera}=useThree(),done=useRef('');
  useFrame(()=>{
    const generation=feed.current.generation;
    if(!generation||generation===done.current)return;
    done.current=generation;
    void gl.compileAsync(scene,camera).catch(()=>undefined);
  });
  return null;
}

function ArenaSceneView({frame,feed,mode,selected,audio,onSelect,onCanvas,onRender,shot,pilot,pick,onPick,onPickHalf,onPickHalfHover,onPickSpectate,onPickHover,pickView,linkPick,onLinkPick,onLinkHover}:{frame:Frame;feed:MutableRefObject<RenderFeed>;mode:CameraMode;selected:string;audio?:ArenaAudio;onSelect:(id:string)=>void;onCanvas:(canvas:HTMLCanvasElement)=>void;onRender:()=>void;shot?:IntroShot|null;pilot?:string|null;pick?:boolean;onPick?:(id:string)=>void;onPickHalf?:(team:TeamId)=>void;onPickHalfHover?:(zone:'red'|'blue'|'seat'|null)=>void;onPickSpectate?:()=>void;onPickHover?:(id:string|null)=>void;pickView?:PickView|null;linkPick?:boolean;onLinkPick?:(id:string)=>void;onLinkHover?:(id:string|null)=>void}){
  // A pilot sees the field through a first-person HUD, so the broadcast plates — enemy health bars,
  // structure bars, mechanism prompts — are switched off with the same flag.
  const hud=!pilot;
  function retry(){for(const url of new Set([frame.arena.asset,...Object.values(frame.arena.structure_assets||{}),...frame.robots.map(r=>r.model_asset||`/assets/robot-${r.role}.glb`),...frame.robots.filter(r=>r.drones?.length&&r.model_asset).map(r=>r.model_asset!.replace('/robot-','/drone-'))]))useGLTF.clear(url);}
  // Resolution is the largest single cost in this scene: the arena fills the screen with merged
  // geometry, so capping the device pixel ratio near 1.25 cuts fragment work by roughly 40%
  // versus the previous 1.6 ceiling without a visible change at normal viewing distance.
  const dpr=mode==='fpv'?FPV_DPR:BROADCAST_DPR;
  // Hover state lives in a ref: the picker must not re-render the whole scene tree as the pointer
  // travels from chassis to chassis. Link Start keeps its own ref so the two probes never share one.
  const hoverPick=useRef<string|null>(null),hoverLink=useRef<string|null>(null);
  // Whether the pointer is on the audience bowl, read by the director to pull the picker camera back.
  const pickSeat=useRef(false);
  // Only the side stage can point at the stands: once a side is picked the seats stop glowing (and any
  // pull-back they asked for unwinds), so the chassis choice is purely about the start cluster.
  useEffect(()=>{if(pickView?.stage!=='side')pickSeat.current=false;},[pickView?.stage]);
  return   <SceneBoundary onRetry={retry} audio={audio}><Canvas shadows dpr={dpr} camera={{position:BROADCAST_EYE,fov:42,near:.1,far:220}} gl={{antialias:true,powerPreference:'high-performance',stencil:false}} onCreated={({gl,scene})=>{gl.shadowMap.autoUpdate=false;gl.shadowMap.type=THREE.PCFShadowMap;gl.toneMapping=THREE.ACESFilmicToneMapping;gl.toneMappingExposure=1.18;scene.background=new THREE.Color('#05070b');scene.fog=new THREE.Fog('#05070b',55,150);
    // Where the draw calls come from, on demand: the render tree is deeply nested, so a flat mesh
    // count says nothing about which subtree to attack. Bucketing by the nearest named ancestor (or the
    // top-level child) is what turns "1175 calls" into "the venue is 400 of them", and the name-stem
    // histogram breaks the leftover "(unnamed)" bucket down by the mesh names the assets actually use.
    (window as unknown as {arenaScene?:THREE.Scene}).arenaScene=scene;
    (window as unknown as {arenaCensus?:()=>unknown}).arenaCensus=()=>{      const buckets=new Map<string,{meshes:number;casters:number;tris:number}>();
      const stems=new Map<string,number>();
      const add=(map:Map<string,{meshes:number;casters:number;tris:number}>,key:string,mesh:THREE.Mesh,tris:number)=>{
        const b=map.get(key)??{meshes:0,casters:0,tris:0};
        b.meshes++;if(mesh.castShadow)b.casters++;b.tris+=tris;map.set(key,b);
      };
      scene.traverse(o=>{
        const mesh=o as THREE.Mesh;if(!mesh.isMesh)return;
        const tris=mesh.geometry.index?mesh.geometry.index.count/3:(mesh.geometry.attributes.position?.count??0)/3;
        let named:THREE.Object3D|null=null;
        for(let p:THREE.Object3D|null=mesh;p;p=p.parent)if(p.name){named=p;break;}
        add(buckets,named?.name??'(unnamed)',mesh,tris);
        stems.set(mesh.name.replace(/\d+$/,'#')||'(empty)',(stems.get(mesh.name.replace(/\d+$/,'#')||'(empty)')??0)+1);
      });
      return {
        ancestors:[...buckets].map(([name,b])=>({name,meshes:b.meshes,casters:b.casters,tris:Math.round(b.tris)})).sort((a,b)=>b.meshes-a.meshes).slice(0,20),
        names:[...stems].sort((a,b)=>b[1]-a[1]).slice(0,20),
      };
    };}}>
    <PickProbe pick={!!pick&&pickView?.stage==='robot'} feed={feed} hover={hoverPick} onPick={onPick} onHover={onPickHover} team={pickView?.stage==='robot'?pickView.team:undefined}/>
    {/* Link Start scans the overhead field: every chassis of both teams in reach, and the pointer
        resting on the cockpit rail or its panel counts as no pointer at all. */}
    <PickProbe pick={!!linkPick} feed={feed} hover={hoverLink} onPick={onLinkPick} onHover={onLinkHover} radius={46} hysteresis={1} canvasOnly dataKey="linkHover"/>
    {pickView?.stage==='side'&&onPickHalf&&<HalfPicker feed={feed} onPick={onPickHalf} onHover={onPickHalfHover} onSpectate={onPickSpectate} seatHot={pickSeat}/>}
    {frameSeason(frame)==='2027'?<FieldLights2027/>:<><hemisphereLight args={['#e4eefb','#1c2128',1.9]}/><ambientLight intensity={.22}/><Sun mode={mode}/></>}<directionalLight position={[-18,12,-14]} color="#9fb9ff" intensity={1.1}/><directionalLight position={[18,9,14]} color="#c9b8ff" intensity={.45}/>
    <Venue season={frameSeason(frame)} seatHot={pickView?.stage==='side'?pickSeat:undefined}/>
    <Suspense fallback={<Html center><div className="scene-loading">加载 Blender / glTF 资产…</div></Html>}><Prewarm feed={feed}/><ArenaMap frame={frame} feed={feed}/><BaseModel team="red" feed={feed} url={frame.arena.structure_assets?.base||'/assets/base.glb'}/><BaseModel team="blue" feed={feed} url={frame.arena.structure_assets?.base||'/assets/base.glb'}/>{frame.outposts&&<><OutpostModel team="red" feed={feed} url={frame.arena.structure_assets?.outpost||'/assets/outpost.glb'}/><OutpostModel team="blue" feed={feed} url={frame.arena.structure_assets?.outpost||'/assets/outpost.glb'}/></>}{frame.runes&&<><RuneModel team="red" feed={feed}/><RuneModel team="blue" feed={feed}/></>}{frame.arena.structure_assets?.core&&frame.arena.assembly_frames&&<><TechCore team="red" feed={feed} url={frame.arena.structure_assets.core}/><TechCore team="blue" feed={feed} url={frame.arena.structure_assets.core}/></>}{frame.robots.map(r=><RobotModel key={r.id} id={r.id} role={r.role} team={r.team} url={r.model_asset||`/assets/robot-${r.role}.glb`} feed={feed} selected={selected} onSelect={onSelect} hidden={mode==='fpv'&&r.id===selected} hover={hoverPick} pick={pick} onPick={onPick}/>)}{frame.robots.filter(r=>r.drones?.length&&r.model_asset).flatMap(r=>r.drones!.map((d,k)=><DroneModel key={d.id} robot={r.id} droneId={d.id} index={k} team={r.team} url={r.model_asset!.replace('/robot-','/drone-')} feed={feed} selected={selected} onSelect={onSelect}/>))}</Suspense>
    {/* The world-space plates are DOM overlays (drei `Html`): a pilot has none of them, so they
        are unmounted rather than hidden, which saves both the per-frame DOM updates and the
        broadcast readouts a pilot must not see. */}
    {hud&&<group visible={!shot}>{frame.robots.map(r=><RobotHud key={r.id} id={r.id} team={r.team} feed={feed} focus={selected===r.id} onSelect={onSelect}/>)}
    {(['red','blue'] as const).map(team=><group key={team}><StructureHud team={team} kind="base" feed={feed}/>{frame.outposts&&<StructureHud team={team} kind="outpost" feed={feed}/>}</group>)}</group>}
    {hud&&<CombatText feed={feed}/>}{hud&&frame.runes&&<><RuneBoard feed={feed}/><RuneBurst feed={feed}/></>}
    {hud&&(['red','blue'] as const).map(team=><group key={team}><MechanismHud team={team} kind="outpost" feed={feed}/><FortressWarning defender={team} feed={feed}/></group>)}
    <SightRig/><Effects feed={feed}/><Director mode={mode} selected={selected} feed={feed} audio={audio} onCanvas={onCanvas} onRender={onRender} shot={shot} pilot={pilot} hud={hud} pickView={pickView} pickHover={hoverPick} pickSeat={pickSeat} linkHover={linkPick?hoverLink:undefined}/>
  </Canvas></SceneBoundary>;
}
// The scene only needs a new React pass when its structure changes (match, lineup, camera mode);
// per-tick robot motion is read from `feed` inside the render loop.
export const ArenaScene=memo(ArenaSceneView,(a,b)=>
  a.feed===b.feed&&a.mode===b.mode&&a.selected===b.selected&&a.pilot===b.pilot&&a.shot===b.shot
  &&a.pick===b.pick&&a.onPick===b.onPick&&a.onPickHalf===b.onPickHalf&&a.onPickHalfHover===b.onPickHalfHover&&a.onPickSpectate===b.onPickSpectate&&a.onPickHover===b.onPickHover&&a.pickView===b.pickView
  &&a.linkPick===b.linkPick&&a.onLinkPick===b.onLinkPick&&a.onLinkHover===b.onLinkHover
  &&a.linkPick===b.linkPick&&a.onLinkPick===b.onLinkPick&&a.onLinkHover===b.onLinkHover
  &&a.audio===b.audio&&a.onSelect===b.onSelect&&a.onCanvas===b.onCanvas&&a.onRender===b.onRender
  &&sceneSignature(a.frame)===sceneSignature(b.frame));
for(const role of ['hero','engineer','infantry','aerial'])useGLTF.preload('/assets/robot-'+role+'.glb');
