import {FortressWarning} from './FortressWarning';
import {Component,Suspense,useEffect,useMemo,useRef,type MutableRefObject,type ReactNode} from 'react';
import {Canvas,useFrame,useThree} from '@react-three/fiber';
import {OrbitControls,useGLTF,Html} from '@react-three/drei';
import * as THREE from 'three';
import type {CameraMode,Drone,Frame,RenderFeed,TeamId} from './types';
import {frameSeason,is42} from './types';
import type {IntroSegment} from './intro';
import {TEAM_COLORS} from './types';
import {terrainHeight} from './terrain';
import {Effects,pulse} from './effects';
import {CombatText,MechanismHud,PickupHud,RobotHud,RuneBoard,RuneBurst,StructureHud} from './hud';
import {cloneForTeam,LED_COLORS,SHELL} from './teamMaterials';
import {Venue} from './venue';
import type {ArenaAudio} from './media';
import {feedAlpha} from './world';
import {legRig,poseLegs,applyArmorNumber} from './robotRig';
import {runeActive,runeArmLight} from './runeLights';
import {useRobotScene} from './customModels';

type Controls=React.ElementRef<typeof OrbitControls>;
// Default framing of the rulebook broadcast: elevated over the long side, field below the scoreboard.
const BROADCAST_EYE:[number,number,number]=[0,15.5,18.5],BROADCAST_TARGET:[number,number,number]=[0,0,-1.2];
const point=(r:{x:number;y:number;z?:number},h=0,width=28,height=15)=>new THREE.Vector3(r.x-width/2,(r.z||0)+h,r.y-height/2);
const colors={red:new THREE.Color(LED_COLORS.red),blue:new THREE.Color(LED_COLORS.blue)},WHITE=new THREE.Color('#ffffff');
const toHeight=(frame:Frame,x:number,y:number)=>terrainHeight(frame.arena,x,y);

function useAsset(url:string,team?:TeamId){
  const scene=useRobotScene(url);
  const asset=useMemo(()=>cloneForTeam(scene,team),[scene,team]),gl=useThree(state=>state.gl);
  // A newly loaded caster also invalidates the cached shadow while paused.
  useEffect(()=>{gl.shadowMap.needsUpdate=true;},[gl,asset]);
  return asset;
}

function RobotModel({id,role,team,url,feed,selected,onSelect}:{id:string;role:string;team:TeamId;url:string;feed:MutableRefObject<RenderFeed>;selected:string;onSelect:(id:string)=>void}){
  const asset=useAsset(url,team),group=useRef<THREE.Group>(null),body=asset.getObjectByName('Chassis'),turret=asset.getObjectByName('Turret'),pitch=asset.getObjectByName('GunPitch');
  const poseNow=useMemo(()=>new THREE.Quaternion(),[]),poseOld=useMemo(()=>new THREE.Quaternion(),[]);
  useEffect(()=>applyArmorNumber(asset,id.slice(id.lastIndexOf('-')+1)),[asset,id]);
  const lift=asset.getObjectByName('GunElevator'),shoulder=asset.getObjectByName('ArmShoulder'),forearm=asset.getObjectByName('ArmForearm');
  const arms=useMemo(()=>['','Aux_'].map(prefix=>{const get=(n:string)=>asset.getObjectByName(prefix+n);const slew=get('ArmSlew');return slew?{slew,lift:get('ArmLift')!,stage:get('ArmMastStage')!,reach:get('ArmReach')!,yaw:get('ArmWristYaw')!,pitch:get('ArmWristPitch')!,roll:get('ArmWristRoll')!,jaws:[get('GripperJaw_0'),get('GripperJaw_1')],liftRest:get('ArmLift')!.position.y}:null;}),[asset]);
  const steering=useMemo(()=>[0,1,2,3].map(k=>asset.getObjectByName('SteerModule_'+k)),[asset]);
  const foldMasts=useMemo(()=>{const nodes:THREE.Object3D[]=[];asset.traverse(o=>{if(o.name.startsWith('FoldMast_'))nodes.push(o);});return nodes;},[asset]);
  const legs=useMemo(()=>legRig(asset),[asset]);
  const carried=[asset.getObjectByName('CarriedUnit_0'),asset.getObjectByName('CarriedUnit_1')];
  const heldUnit=useRef<THREE.Group>(null),unitAsset=useAsset('/assets/energy-unit-ch4.glb');
  const rotorNodes=useMemo(()=>{const nodes:THREE.Object3D[]=[];asset.traverse(o=>{if(o.name.startsWith('Rotor_')&&!(o instanceof THREE.Mesh))nodes.push(o);});return nodes;},[asset]);
  const wheelNodes=useMemo(()=>{const nodes:THREE.Object3D[]=[];asset.traverse(o=>{if(/^Wheel_\d+$/.test(o.name)&&!(o instanceof THREE.Mesh))nodes.push(o);});return nodes.sort((a,b)=>Number(a.name.slice(6))-Number(b.name.slice(6)));},[asset]);
  const ring=useRef<THREE.Mesh>(null),shield=useRef<THREE.Mesh>(null),light=useRef<THREE.PointLight>(null);const lastPosition=useRef(new THREE.Vector3());
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
    if(turret)turret.rotation.y=-(r.aim-r.heading);
    if(pitch)pitch.rotation.z=r.pitch||0;
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
    // Wrecks stay on the field as physical obstacles: dimmed, lamps off.
    for(const m of materials){m.transparent=!physicalAlive;m.opacity=physicalAlive?1:.62;}
    const hit=pulse(id,.18);for(const g of glows){g.m.emissive.copy(g.emissive).lerp(WHITE,hit*.7);g.m.emissiveIntensity=r.alive||r.role==='aerial'?g.intensity*(1+hit*3):g.intensity*.08;}
    if(ring.current){ring.current.visible=selected===id;ring.current.rotation.z=clock.elapsedTime*.2;}
    if(shield.current){shield.current.visible=r.alive&&r.shield>0;const material=shield.current.material as THREE.MeshBasicMaterial;material.opacity=.08+Math.sin(clock.elapsedTime*8)*.025;}
    if(light.current){const flash=feed.current.events.some(e=>e.type==='shot'&&e.robot===id);light.current.position.set(Math.cos(r.aim-r.heading)*Math.cos(r.pitch)*(r.muzzle_reach_m||.3),(r.muzzle_height_m||.55)+Math.sin(r.pitch)*(r.muzzle_reach_m||.3),Math.sin(r.aim-r.heading)*Math.cos(r.pitch)*(r.muzzle_reach_m||.3));light.current.intensity=flash?.15:Math.max(0,light.current.intensity-dt*30);}
  });
  return <group ref={group} onClick={e=>{e.stopPropagation();onSelect(id);}}>
    <primitive object={asset}/>
    {(role==='engineer'||role==='heavy')&&<><group ref={heldUnit} visible={false}>
      <primitive object={unitAsset} rotation={[0,0,-Math.PI/2]}/>
    </group><PickupHud id={id} feed={feed}/></>}
    <mesh ref={ring} rotation={[-Math.PI/2,0,0]} position={[0,.024,0]} visible={selected===id}><ringGeometry args={[.75,.79,48]}/><meshBasicMaterial color="#edc27a" transparent opacity={.9} side={THREE.DoubleSide}/></mesh>
    <mesh ref={shield} position={[0,.47,0]} visible={false}><sphereGeometry args={[.82,20,12]}/><meshBasicMaterial color={TEAM_COLORS[team]} transparent opacity={.1} depthWrite={false}/></mesh>
    <pointLight ref={light} position={[.75,.8,0]} color="#66ee55" intensity={0} distance={1}/>
  </group>;
}

// RMUC 2027 aerial robots: each hangar's drones fly as separate bodies (robot.drones).
function DroneModel({robot,index,team,url,feed}:{robot:string;index:number;team:TeamId;url:string;feed:MutableRefObject<RenderFeed>}){
  const asset=useAsset(url,team),group=useRef<THREE.Group>(null),now=useMemo(()=>new THREE.Quaternion(),[]),was=useMemo(()=>new THREE.Quaternion(),[]);
  const rotors=useMemo(()=>{const nodes:THREE.Object3D[]=[];asset.traverse(o=>{if(o.name.startsWith('Rotor_')&&!(o instanceof THREE.Mesh))nodes.push(o);});return nodes;},[asset]);
  const materials=useMemo(()=>{const list:THREE.Material[]=[];asset.traverse(o=>{if(o instanceof THREE.Mesh)list.push(...(Array.isArray(o.material)?o.material:[o.material]));});return list;},[asset]);
  useFrame((_,dt)=>{const f=feed.current.frame;if(!f||!group.current)return;const r=f.robots.find(r=>r.id===robot),d=r?.drones?.[index];if(!d){group.current.visible=false;return;}
    const old:Drone=feed.current.previous?.robots.find(o=>o.id===robot)?.drones?.[index]||d,alpha=feedAlpha(feed.current);
    group.current.visible=true;group.current.position.copy(point(d,0,f.arena.width,f.arena.height)).lerp(point(old,0,f.arena.width,f.arena.height),1-alpha);
    const a=d.quaternion,b=old.quaternion||a;now.set(-a[0],-a[2],-a[1],a[3]);was.set(-b[0],-b[2],-b[1],b[3]);group.current.quaternion.copy(was.slerp(now,alpha));
    for(const node of rotors)node.rotation.y+=dt*(d.state==='flying'?120:0);
    for(const m of materials){m.transparent=d.state==='disabled';m.opacity=d.state==='disabled'?.45:1;}
  });
  return <group ref={group}><primitive object={asset}/></group>;
}

function BaseModel({team,feed,url}:{team:TeamId;feed:MutableRefObject<RenderFeed>;url:string}){
  const asset=useAsset(url,team),group=useRef<THREE.Group>(null),opening=useRef(0);
  // Figures 4-10/4-11: six half-shells hinged at the pyramid corners swing outward as the
  // armour opens (same 1.15 rad sweep as the engine's collision shells).
  const hinges=useMemo(()=>{const result:{node:THREE.Object3D;original:THREE.Quaternion;swing:number}[]=[];asset.traverse(node=>{if(node.name.startsWith('BaseShell_'))result.push({node,original:node.quaternion.clone(),swing:Number(node.userData.swing)||1});});return result;},[asset]);
  const rotation=useMemo(()=>new THREE.Quaternion(),[]),up=useMemo(()=>new THREE.Vector3(0,1,0),[]);
  useFrame(({clock},dt)=>{const b=feed.current.frame?.bases[team];if(!b||!group.current)return;group.current.position.copy(point(b,0,feed.current.frame!.arena.width,feed.current.frame!.arena.height));opening.current=b.armor_open_progress??THREE.MathUtils.damp(opening.current,b.armor_open?1:0,5,dt);for(const h of hinges)h.node.quaternion.copy(h.original).multiply(rotation.setFromAxisAngle(up,h.swing*opening.current*1.15));asset.traverse(o=>{if(o instanceof THREE.Mesh)for(const m of Array.isArray(o.material)?o.material:[o.material])if(m instanceof THREE.MeshStandardMaterial&&m.name.startsWith('TeamGlow'))m.emissiveIntensity=1.1+Math.sin(clock.elapsedTime*2)*.15+pulse('base-'+team,.25)*2.5;});});
  return <group ref={group}><primitive object={asset}/><pointLight color={LED_COLORS[team]} intensity={2.2} distance={3.2} decay={2} position={[0,.9,0]}/></group>;
}

// A 2027 outpost rebuilt by the other team carries that team's lights and shell tint.
function OutpostModel({team,feed,url}:{team:TeamId;feed:MutableRefObject<RenderFeed>;url:string}){
  const asset=useAsset(url,team),group=useRef<THREE.Group>(null),rotor=asset.getObjectByName('ArmorRotor');
  useFrame(()=>{const f=feed.current.frame,b=f?.outposts?.[team];if(!b||!group.current)return;group.current.position.copy(point(b,0,f!.arena.width,f!.arena.height));// The rotor turns between frames like the interpolated drones that strike it.
    const was=feed.current.previous?.outposts?.[team]?.rotation??b.rotation??0,turn=(b.rotation||0)-was;
    if(rotor)rotor.rotation.y=-(was+Math.atan2(Math.sin(turn),Math.cos(turn))*feedAlpha(feed.current));const held=b.owner??team;asset.traverse(o=>{if(o instanceof THREE.Mesh)for(const m of Array.isArray(o.material)?o.material:[o.material]){if(!(m instanceof THREE.MeshStandardMaterial))continue;if(m.name.startsWith('TeamGlow')){m.emissiveIntensity=b.hp>0?(m.userData.glow??=m.emissiveIntensity)*(1+pulse('outpost-'+team,.25)*2.5):0;m.color.set(b.hp>0?LED_COLORS[held]:'#1a1c20');m.emissive.set(LED_COLORS[held]);}else if(m.name.startsWith('TeamPrimary'))m.color.set(SHELL[held]);}});});
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
  const asset=useAsset(frame.arena.asset||`/assets/map-${frame.arena.name}.glb`);
  const concrete=useMemo(()=>({highland:concreteTexture('#86898d',['#6a6d71','#5a5e62','#9a9da0','#77797d'],18,150,2026),floor:concreteTexture('#2c2e32',['#232528','#36383c','#1e2023'],12,110,7)}),[]);
  useEffect(()=>()=>{concrete.highland.dispose();concrete.floor.dispose();},[concrete]);
  useMemo(()=>asset.traverse(o=>{if(!(o instanceof THREE.Mesh))return;for(const m of (Array.isArray(o.material)?o.material:[o.material]) as THREE.MeshStandardMaterial[]){
    if(m.userData.broadcast)continue;m.userData.broadcast=true;
    if(m.name.startsWith('RedFieldPaint')){m.color.set('#ff3b30');m.emissive.set('#ff2a1c');m.emissiveIntensity=2.6;m.toneMapped=false;}
    else if(m.name.startsWith('BlueFieldPaint')){m.color.set('#1f6dff');m.emissive.set('#1450ff');m.emissiveIntensity=2.3;m.toneMapped=false;}
    else if(m.name.startsWith('WhiteFieldPaint')){m.emissive.set('#ffffff');m.emissiveIntensity=.22;}
    else if(m.name.startsWith('HighlandAsphalt')){m.map=concrete.highland;m.color.set('#ffffff');m.roughness=.84;m.needsUpdate=true;}
    else if(m.name.startsWith('FieldBlack')){m.map=concrete.floor;m.color.set('#ffffff');m.roughness=.88;m.needsUpdate=true;}
    else if(m.name.startsWith('ProtectiveMetal')){m.color.multiplyScalar(1.25);}
    else if(m.name.startsWith('ConcreteSide')){m.map=concrete.highland;m.color.set('#8a8c8e');m.roughness=.9;m.needsUpdate=true;}
  }}),[asset]);
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
  if(s.kind==='open'){const a=-1.05+e*1.25,r=7+e*15,h=1.6+e*14;camera.position.set(Math.sin(a)*r,h,Math.cos(a)*r);look.set(0,1.4*(1-e),-.4*e);}
  else if(s.kind==='team'){const side=s.team==='red'?1:-1;camera.position.set(side*(-3.2-2.8*e),3.6-1.1*e,side*(4.8-1.6*e));look.set(side*-11.2,.35,side*.4);}
  else if(s.kind==='faceoff'){camera.position.set(0,17.5-3*e,21.5-3.5*e);look.set(0,0,-.9);}
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
function Director({mode,selected,feed,audio,onCanvas,onRender,shot}:{mode:CameraMode;selected:string;feed:MutableRefObject<RenderFeed>;audio?:ArenaAudio;onCanvas:(canvas:HTMLCanvasElement)=>void;onRender:()=>void;shot?:IntroShot|null}){
  const {camera,gl}=useThree(),controls=useRef<Controls>(null),target=useMemo(()=>new THREE.Vector3(),[]);const previousMode=useRef('');
  const shadow=useRef({slot:-1,frame:null as Frame|null,generation:'',paused:false});
  const look=useMemo(()=>new THREE.Vector3(),[]),cut=useRef({key:'',at:0});
  const ear=useMemo(()=>new THREE.Vector3(),[]),ahead=useMemo(()=>new THREE.Vector3(),[]),up=useMemo(()=>new THREE.Vector3(),[]),origin=useMemo(()=>new THREE.Vector3(),[]);
  useEffect(()=>onCanvas(gl.domElement),[gl,onCanvas]);
  useEffect(()=>{const restore=()=>{gl.shadowMap.needsUpdate=true;};gl.domElement.addEventListener('webglcontextrestored',restore);return()=>gl.domElement.removeEventListener('webglcontextrestored',restore);},[gl]);
  useFrame(({clock},dt)=>{
    // The intro owns the camera; the chosen broadcast mode resumes from its default framing afterwards.
    if(shot){const f=feed.current.frame;if(cut.current.key!==shot.key)cut.current={key:shot.key,at:clock.elapsedTime};if(f)introCamera(shot,Math.min(1,(clock.elapsedTime-cut.current.at)/Math.max(.2,shot.length)),f,camera,look);previousMode.current='intro';return;}
    if(previousMode.current!==mode){previousMode.current=mode;if(mode==='orbit'){camera.position.set(...BROADCAST_EYE);controls.current?.target.set(...BROADCAST_TARGET);}if(mode==='top'){camera.position.set(0,34,.01);target.set(0,0,0);camera.lookAt(target);}}
    if(mode==='cinematic'){const a=clock.elapsedTime*.052;camera.position.set(Math.sin(a)*26,21,Math.cos(a)*24);camera.lookAt(0,0,0);}
    if(mode==='follow'){const r=feed.current.frame?.robots.find(r=>r.id===selected);if(r){target.lerp(point(r,.40),Math.min(1,dt*6));const angle=r.heading;const desired=target.clone().add(new THREE.Vector3(-Math.cos(angle)*4,3.3,-Math.sin(angle)*4));const arena=feed.current.frame!.arena;desired.x=THREE.MathUtils.clamp(desired.x,-arena.width/2+.6,arena.width/2-.6);desired.z=THREE.MathUtils.clamp(desired.z,-arena.height/2+.6,arena.height/2-.6);camera.position.lerp(desired,Math.min(1,dt*3));camera.lookAt(target);}}
  });
  useFrame(()=>{if(!audio?.enabled)return;const focus=mode==='orbit'?controls.current?.target||origin:mode==='follow'?target:origin;ear.copy(camera.position).sub(focus);ear.setLength(Math.min(ear.length(),9)).add(focus);camera.getWorldDirection(ahead);up.set(0,1,0).applyQuaternion(camera.quaternion);audio.listen(ear,ahead,up,feed.current.frame?.arena);});
  useFrame(()=>{audio?.drones(feed.current.frame);},-2);
  // A fixed directional light does not need new shadows for camera motion.
  // Keep moving shadows at 30 Hz; a changed paused frame always refreshes them.
  useFrame(({gl,scene,camera,clock})=>{
    const f=feed.current,s=shadow.current,slot=Math.floor(clock.elapsedTime*30);
    if(f.generation!==s.generation||f.paused!==s.paused||(f.paused?f.frame!==s.frame:slot!==s.slot)){
      gl.shadowMap.needsUpdate=true;s.slot=slot;s.frame=f.frame;s.generation=f.generation;s.paused=f.paused;
    }
    gl.render(scene,camera);
    // Copy the just-rendered frame synchronously, before WebGL releases its buffer.
    onRender();
  },1);
  return <OrbitControls ref={controls} enabled={mode==='orbit'&&!shot} enableDamping dampingFactor={.075} maxPolarAngle={Math.PI*.47} minDistance={4} maxDistance={72} target={BROADCAST_TARGET}/>;
}

class SceneBoundary extends Component<{children:ReactNode;onRetry:()=>void;audio?:ArenaAudio},{failed:boolean}>{
  state={failed:false};
  static getDerivedStateFromError(){return {failed:true};}
  componentDidCatch(){this.props.audio?.drones(null);}
  render(){return this.state.failed?<div className="scene-recovery"><p>战场模型暂时无法加载</p><button onClick={()=>{this.props.onRetry();this.setState({failed:false});}}>重新加载战场</button></div>:this.props.children;}
}
export function ArenaScene({frame,feed,mode,selected,audio,onSelect,onCanvas,onRender,shot}:{frame:Frame;feed:MutableRefObject<RenderFeed>;mode:CameraMode;selected:string;audio?:ArenaAudio;onSelect:(id:string)=>void;onCanvas:(canvas:HTMLCanvasElement)=>void;onRender:()=>void;shot?:IntroShot|null}){
  function retry(){for(const url of new Set([frame.arena.asset,...Object.values(frame.arena.structure_assets||{}),...frame.robots.map(r=>r.model_asset||`/assets/robot-${r.role}.glb`),...frame.robots.filter(r=>r.drones?.length&&r.model_asset).map(r=>r.model_asset!.replace('/robot-','/drone-'))]))useGLTF.clear(url);}
  return <SceneBoundary onRetry={retry} audio={audio}><Canvas shadows dpr={[1,1.6]} camera={{position:BROADCAST_EYE,fov:42,near:.1,far:220}} gl={{antialias:true}} onCreated={({gl,scene})=>{gl.shadowMap.autoUpdate=false;gl.toneMapping=THREE.ACESFilmicToneMapping;gl.toneMappingExposure=1.18;scene.background=new THREE.Color('#05070b');scene.fog=new THREE.Fog('#05070b',55,150);}}>
    <hemisphereLight args={['#e4eefb','#1c2128',1.9]}/><ambientLight intensity={.22}/><directionalLight position={[4,26,9]} intensity={3.1} color="#f4f6ff" castShadow shadow-mapSize={[2048,2048]} shadow-camera-left={-28} shadow-camera-right={28} shadow-camera-top={24} shadow-camera-bottom={-24} shadow-bias={-.0004}/><directionalLight position={[-18,12,-14]} color="#9fb9ff" intensity={1.1}/><directionalLight position={[18,9,14]} color="#c9b8ff" intensity={.45}/>
    <Venue season={frameSeason(frame)}/>
    <Suspense fallback={<Html center><div className="scene-loading">加载 Blender / glTF 资产…</div></Html>}><ArenaMap frame={frame} feed={feed}/><BaseModel team="red" feed={feed} url={frame.arena.structure_assets?.base||'/assets/base.glb'}/><BaseModel team="blue" feed={feed} url={frame.arena.structure_assets?.base||'/assets/base.glb'}/>{frame.outposts&&<><OutpostModel team="red" feed={feed} url={frame.arena.structure_assets?.outpost||'/assets/outpost.glb'}/><OutpostModel team="blue" feed={feed} url={frame.arena.structure_assets?.outpost||'/assets/outpost.glb'}/></>}{frame.runes&&<><RuneModel team="red" feed={feed}/><RuneModel team="blue" feed={feed}/></>}{frame.arena.structure_assets?.core&&frame.arena.assembly_frames&&<><TechCore team="red" feed={feed} url={frame.arena.structure_assets.core}/><TechCore team="blue" feed={feed} url={frame.arena.structure_assets.core}/></>}{frame.robots.map(r=><RobotModel key={r.id} id={r.id} role={r.role} team={r.team} url={r.model_asset||`/assets/robot-${r.role}.glb`} feed={feed} selected={selected} onSelect={onSelect}/>)}{frame.robots.filter(r=>r.drones?.length&&r.model_asset).flatMap(r=>r.drones!.map((d,k)=><DroneModel key={d.id} robot={r.id} index={k} team={r.team} url={r.model_asset!.replace('/robot-','/drone-')} feed={feed}/>))}</Suspense>
    <group visible={!shot}>{frame.robots.map(r=><RobotHud key={r.id} id={r.id} team={r.team} feed={feed} focus={selected===r.id} onSelect={onSelect}/>)}
    {(['red','blue'] as const).map(team=><group key={team}><StructureHud team={team} kind="base" feed={feed}/>{frame.outposts&&<StructureHud team={team} kind="outpost" feed={feed}/>}</group>)}</group>
    <CombatText feed={feed}/>{frame.runes&&<><RuneBoard feed={feed}/><RuneBurst feed={feed}/></>}
    {(['red','blue'] as const).map(team=><group key={team}><MechanismHud team={team} kind="outpost" feed={feed}/><FortressWarning defender={team} feed={feed}/></group>)}
    <Effects feed={feed}/><Director mode={mode} selected={selected} feed={feed} audio={audio} onCanvas={onCanvas} onRender={onRender} shot={shot}/>
  </Canvas></SceneBoundary>;
}
for(const role of ['hero','engineer','infantry','aerial'])useGLTF.preload('/assets/robot-'+role+'.glb');
