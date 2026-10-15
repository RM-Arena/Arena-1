import {Component,Suspense,useEffect,useLayoutEffect,useMemo,useRef,useState,type ReactNode} from 'react';
import {Canvas,useFrame,useThree} from '@react-three/fiber';
import {Html,OrbitControls,useGLTF} from '@react-three/drei';
import type {OrbitControls as Controls} from 'three-stdlib';
import * as THREE from 'three';
import {RotateCw,ScanLine,Wrench} from 'lucide-react';
import {cloneForTeam,LED_COLORS} from './teamMaterials';
import {useRobotScene} from './customModels';
import {applyArmorNumber,legRig,poseLegs} from './robotRig';
import type {ArmHardware,RobotHardware,TeamId} from './types';

function useReducedMotion(){
  const [reduced,setReduced]=useState(()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(()=>{const media=window.matchMedia('(prefers-reduced-motion: reduce)'),update=()=>setReduced(media.matches);media.addEventListener('change',update);return()=>media.removeEventListener('change',update);},[]);
  return reduced;
}

class PreviewBoundary extends Component<{children:ReactNode;onRetry:()=>void},{failed:boolean}>{
  state={failed:false};
  static getDerivedStateFromError(){return {failed:true};}
  render(){return this.state.failed?<div className="hangar-preview-failure"><ScanLine size={32}/><p>3D 模型暂时无法加载</p><button onClick={this.props.onRetry}>重新加载</button></div>:this.props.children;}
}

function PreviewModel({model,slot,team,demo}:{model:RobotHardware;slot:number;team:TeamId;demo:boolean}){
  const scene=useRobotScene(model.asset),body=useRef<THREE.Group>(null);
  const asset=useMemo(()=>cloneForTeam(scene,team),[scene,team]);
  const baseBounds=useMemo(()=>{const box=new THREE.Box3().setFromObject(asset);return {center:box.getCenter(new THREE.Vector3()),size:box.getSize(new THREE.Vector3()),floor:box.min.y};},[asset]);
  const sizing=useMemo(()=>{
    const {center,size,floor}=baseBounds;
    const legTravel=demo?(model.leg_max_m??0)-(model.leg_nominal_m??0):0;
    const extent=Math.max(size.x,size.z,size.y+Math.max(0,legTravel),...(demo&&model.arm_count?model.extended_m:[]));
    return {scale:1.8/extent,center,floor};
  },[baseBounds,model,demo]);
  const initialScale=useRef(sizing.scale);
  const rig=useMemo(()=>{
    const arms=['','Aux_'].map(prefix=>{const get=(name:string)=>asset.getObjectByName(prefix+name),lift=get('ArmLift');return lift?{slew:get('ArmSlew')!,lift,stage:get('ArmMastStage')!,reach:get('ArmReach')!,yaw:get('ArmWristYaw')!,pitch:get('ArmWristPitch')!,roll:get('ArmWristRoll')!,jaws:[get('GripperJaw_0'),get('GripperJaw_1')],rest:lift.position.y}:null;});
    const rotors:THREE.Object3D[]=[],masts:THREE.Object3D[]=[],wheels:THREE.Object3D[]=[];
    asset.traverse(node=>{if(node.name.startsWith('Rotor_')&&!(node instanceof THREE.Mesh))rotors.push(node);if(node.name.startsWith('FoldMast_')&&!(node instanceof THREE.Mesh))masts.push(node);if(/^Wheel_\d+$/.test(node.name)&&!(node instanceof THREE.Mesh))wheels.push(node);if(node.name.startsWith('CarriedUnit_'))node.visible=false;});
    wheels.sort((a,b)=>Number(a.name.slice(6))-Number(b.name.slice(6)));
    return {arms,rotors,masts,wheels,legs:legRig(asset),turret:asset.getObjectByName('Turret'),pitch:asset.getObjectByName('GunPitch'),lift:asset.getObjectByName('GunElevator'),steering:[0,1,2,3].map(i=>asset.getObjectByName('SteerModule_'+i))};
  },[asset]);
  useEffect(()=>applyArmorNumber(asset,String(slot)),[asset,slot]);
  useEffect(()=>()=>{asset.traverse(node=>{if(node instanceof THREE.Mesh)(Array.isArray(node.material)?node.material:[node.material]).forEach(m=>m.dispose());});},[asset]);
  const elapsed=useRef(0);
  useFrame((_,dt)=>{
    elapsed.current=demo?elapsed.current+Math.min(dt,.05):0;const t=elapsed.current;
    if(rig.turret)rig.turret.rotation.y=demo?Math.sin(t*.65)*.5:0;
    if(rig.pitch)rig.pitch.rotation.z=demo&&!model.transform_allowed?Math.sin(t*.8)*.13:0;
    const folded=model.transform_allowed&&demo?(1-Math.cos(t*.9))/2:0;
    if(rig.lift)rig.lift.position.y=-(model.muzzle_z_m-(model.folded_muzzle_z_m??model.muzzle_z_m))*folded;
    for(const mast of rig.masts){const rest=mast.userData.rest_height_m,height=rest+(mast.userData.folded_height_m-rest)*folded;mast.scale.y=height/rest;mast.position.y=mast.userData.base_z_m+height/2;}
    rig.arms.forEach((arm,i)=>{
      const d:ArmHardware|undefined=i===0?model.arm:model.arm2;if(!arm||!d)return;
      const phase=t*.75+i*Math.PI*.75,q=[...d.stowed];
      if(demo){q[0]=model.arm_count===2?(i?1:-1)*(.65+.2*Math.sin(phase)):.55*Math.sin(phase);q[1]=.13+.11*Math.sin(phase);q[2]=Math.min(d.limits[2][1],d.workspace_half_m?d.workspace_half_m-d.tool_length_m-.04:.46);q[3]=.3*Math.sin(phase);q[4]=-.55+.3*Math.sin(phase);q[6]=(.5+.5*Math.sin(phase*2));}
      arm.slew.rotation.y=-q[0];arm.lift.position.y=arm.rest+q[1];arm.stage.position.y=q[1]/2;arm.reach.position.x=q[2];arm.yaw.rotation.y=-q[3];arm.pitch.rotation.z=-q[4];arm.roll.rotation.x=-q[5];arm.jaws.forEach((jaw,k)=>{if(jaw)jaw.position.z=-(k?1:-1)*(.018+q[6]*d.jaw_travel_m);});
    });
    rig.steering.forEach(node=>{if(node)node.rotation.y=demo?Math.sin(t*.9)*.65:0;});
    const nominal=model.leg_nominal_m??.2;let length=demo&&rig.legs?nominal+(model.leg_max_m!-nominal)*(1-Math.cos(t*1.2))*.5:nominal,hip=0,lift=length-nominal;
    if(demo&&rig.legs?.kind==='serial'){
      // Serial legs, 8 s cycle: the legs pump for 5 s, then tuck while the hips make one full turn.
      const cycle=t%8;length=cycle<5?nominal+(model.leg_max_m!-nominal)*(1-Math.cos(cycle*Math.PI*.8))*.5:nominal;lift=length-nominal;
      if(cycle>=5){const s=(cycle-5)/3,tuck=Math.min(1,s/.15,(1-s)/.15);length=nominal+((model.leg_min_m??.12)-nominal)*tuck;
        const p=Math.max(0,Math.min(1,(s-.12)/.76));hip=-Math.PI*2*p*p*(3-2*p);lift=0;}
    }
    if(rig.legs)poseLegs(rig.legs,[length,length],rig.wheels,hip);
    for(const rotor of rig.rotors)if(demo)rotor.rotation.y+=dt*24;
    if(body.current){const scale=THREE.MathUtils.damp(body.current.scale.x,sizing.scale,5,dt);body.current.scale.setScalar(scale);body.current.position.set(-sizing.center.x*scale,(-sizing.floor+(rig.legs?lift:0))*scale+(model.role==='aerial'&&demo?.08+.035*Math.sin(t):0),-sizing.center.z*scale);}
  });
  return <group ref={body} scale={initialScale.current} position={[-sizing.center.x*sizing.scale,-sizing.floor*sizing.scale,-sizing.center.z*sizing.scale]}><primitive object={asset}/></group>;
}

function CameraRig({rotate,reset,framing=1}:{rotate:boolean;reset:number;framing?:number}){
  const controls=useRef<Controls>(null),{camera,size}=useThree();
  useLayoutEffect(()=>{const distance=framing*Math.max(2.9,2.65/Math.max(size.width/size.height,.6));camera.position.set(distance*.8,distance*.52,distance*.9);camera.lookAt(0,.8,0);controls.current?.target.set(0,.8,0);controls.current?.update();},[camera,size.width,size.height,reset,framing]);
  return <OrbitControls ref={controls} makeDefault target={[0,.8,0]} autoRotate={rotate} autoRotateSpeed={.75} enablePan={false} minDistance={2.4} maxDistance={7} minPolarAngle={.3} maxPolarAngle={Math.PI*.48}/>;
}

export function RobotPreview({model,slot,framing=1}:{model:RobotHardware;slot:number;framing?:number}){
  const [team,setTeam]=useState<TeamId>('red'),[rotate,setRotate]=useState(true),[demo,setDemo]=useState(false),[reset,setReset]=useState(0),[attempt,setAttempt]=useState(0),reduced=useReducedMotion();
  const animated=model.role!=='engineer'||model.arm_count>0;
  return <section className="hangar-preview" aria-label={`${model.name}动态3D展示`}>
    <div className="hangar-preview-top"><span><i/> LIVE MODEL <b>{String(model.slot).padStart(3,'0')}</b></span><div className="hangar-team-switch">{(['red','blue'] as const).map(t=><button key={t} className={team===t?'active':''} aria-label={`${t==='red'?'红':'蓝'}方模型配色`} aria-pressed={team===t} onClick={()=>setTeam(t)} style={{'--team-led':LED_COLORS[t]} as React.CSSProperties}>{t==='red'?'RED':'BLUE'}</button>)}</div></div>
    <PreviewBoundary key={model.asset+attempt} onRetry={()=>{useGLTF.clear(model.asset);setAttempt(n=>n+1);}}><Canvas shadows dpr={[1,1.5]} camera={{fov:33,near:.01,far:40}} gl={{antialias:true,alpha:true}}>
      <ambientLight intensity={1.4}/><hemisphereLight args={['#dcefff','#192c39',1.4]}/>
      <directionalLight position={[3,5,4]} intensity={3.5} castShadow shadow-mapSize={[1024,1024]}/><directionalLight position={[-3,2,-2]} intensity={2.7} color="#6bdcff"/>
      <pointLight position={[0,.35,-1]} color={LED_COLORS[team]} intensity={1.8}/>
      <mesh position={[0,-.065,0]} receiveShadow><cylinderGeometry args={[1.12,1.18,.12,64]}/><meshStandardMaterial color="#162735" metalness={.6} roughness={.42}/></mesh>
      <mesh rotation={[-Math.PI/2,0,0]} position={[0,.001,0]}><ringGeometry args={[1.01,1.018,96]}/><meshBasicMaterial color="#80dced" transparent opacity={.55}/></mesh>
      <mesh rotation={[-Math.PI/2,0,0]} position={[0,-.002,0]} receiveShadow><circleGeometry args={[1.11,64]}/><meshStandardMaterial color="#13222e" metalness={.45} roughness={.65}/></mesh>
      <gridHelper args={[6,40,'#213f50','#152a37']} position={[0,-.13,0]}/>
      <Suspense fallback={<Html center><div className="hangar-model-loading"><ScanLine size={24}/><span>装载构型…</span></div></Html>}><PreviewModel key={model.asset+team} model={model} slot={slot} team={team} demo={demo&&!reduced}/></Suspense>
      <CameraRig rotate={rotate&&!reduced} reset={reset+model.slot} framing={framing}/>
    </Canvas></PreviewBoundary>
    <div className="hangar-preview-bottom"><span>拖动旋转 · 滚轮缩放{demo?' · 机构动作演示':''}</span><div><button aria-label="自动旋转" aria-pressed={rotate} className={rotate?'active':''} onClick={()=>setRotate(!rotate)}><RotateCw size={15}/></button><button aria-label="机构演示" aria-pressed={demo} disabled={!animated} className={demo?'active':''} onClick={()=>setDemo(!demo)}><Wrench size={15}/></button><button aria-label="重置3D视角" onClick={()=>setReset(n=>n+1)}><ScanLine size={15}/></button></div></div>
  </section>;
}
