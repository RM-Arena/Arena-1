import * as THREE from 'three';

export function applyArmorNumber(asset:THREE.Object3D,slot:string){
  const canvas=document.createElement('canvas');canvas.width=128;canvas.height=128;
  const ctx=canvas.getContext('2d')!;ctx.fillStyle='#15202a';ctx.font='bold 104px Arial';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(slot,64,68,118);
  const texture=new THREE.CanvasTexture(canvas),geometry=new THREE.PlaneGeometry(.043,.043).rotateX(-Math.PI/2);
  const material=new THREE.MeshBasicMaterial({map:texture,transparent:true,side:THREE.DoubleSide,depthWrite:false});
  const labels:THREE.Mesh[]=[];
  asset.traverse(node=>{if(node.name.startsWith('ArmorNumber')&&!(node instanceof THREE.Mesh)){
    node.children.forEach(child=>{child.visible=false;});const label=new THREE.Mesh(geometry,material);node.add(label);labels.push(label);
  }});
  return()=>{labels.forEach(label=>label.removeFromParent());texture.dispose();geometry.dispose();material.dispose();};
}

type FiveBarRig={kind:'five_bar';upper:THREE.Object3D[];lower:THREE.Object3D[];geometry:{hip_height_m:number;upper_m:number;lower_m:number;pivot_x_m:number;pivot_above_hip_m:number}};
type SerialRig={kind:'serial';thigh:THREE.Object3D[];shank:THREE.Object3D[];geometry:{hip_height_m:number;upper_m:number;lower_m:number}};
export type LegRig=FiveBarRig|SerialRig;
export function legRig(asset:THREE.Object3D):LegRig|null{
  const raw=asset.userData?.leg_geometry??asset.getObjectByName('Robot')?.userData?.leg_geometry;if(!raw)return null;
  const geometry=typeof raw==='string'?JSON.parse(raw):raw;
  // Model side 0 = R (Wheel_0), 1 = L (Wheel_1).
  if(geometry.type==='serial'){
    const thigh=['R','L'].map(n=>asset.getObjectByName(`Leg${n}_Thigh`)),shank=['R','L'].map(n=>asset.getObjectByName(`Leg${n}_Shank`));
    if(thigh.some(o=>!o)||shank.some(o=>!o))return null;
    return {kind:'serial',thigh:thigh as THREE.Object3D[],shank:shank as THREE.Object3D[],geometry};
  }
  const names=['RF','RB','LF','LB'];const upper=names.map(n=>asset.getObjectByName(`Leg${n}_Upper`)),lower=names.map(n=>asset.getObjectByName(`Leg${n}_Lower`));
  if(upper.some(o=>!o)||lower.some(o=>!o))return null;
  return {kind:'five_bar',upper:upper as THREE.Object3D[],lower:lower as THREE.Object3D[],geometry};
}
const angle=(p:number[],q:number[])=>Math.atan2(-(q[0]-p[0]),-(q[1]-p[1]));
// Same closed-form two-link solutions as assets/blender/robot_specs.py. `hip` is the serial
// legs' swing about the hip axle (the engine's hip_angle); five-bar legs ignore it.
export function poseLegs(rig:LegRig,legs:number[],wheels:THREE.Object3D[],hip=0){
  if(rig.kind==='serial'){
    const {hip_height_m:z,upper_m:a,lower_m:b}=rig.geometry;
    legs.forEach((raw,engineSide)=>{
      const side=1-engineSide,length=Math.max(Math.abs(a-b)+.002,Math.min(a+b-.002,raw));
      const bend=Math.acos(Math.max(-1,Math.min(1,(a*a+length*length-b*b)/(2*a*length))));
      const pivot=[0,z],knee=[-a*Math.sin(hip+bend),z-a*Math.cos(hip+bend)],axle=[-length*Math.sin(hip),z-length*Math.cos(hip)];
      const au=angle(pivot,knee),al=angle(knee,axle);
      rig.thigh[side].rotation.z=-au;rig.shank[side].rotation.z=-(al-au);
      if(wheels[side]){wheels[side].position.x=axle[0];wheels[side].position.y=axle[1];}
    });
    return;
  }
  const g=rig.geometry,pivotZ=g.hip_height_m+g.pivot_above_hip_m;
  // Engine leg 0 is the right (-y) leg; the mirrored model draws it as the 'L' side, Wheel_1.
  legs.forEach((length,engineSide)=>{
    const side=1-engineSide,axle=[0,g.hip_height_m-length];
    [[g.pivot_x_m,1],[-g.pivot_x_m,-1]].forEach(([px,out],k)=>{
      const pivot=[px,pivotZ],dx=axle[0]-pivot[0],dz=axle[1]-pivot[1],d=Math.max(1e-6,Math.hypot(dx,dz));
      const cos=Math.max(-1,Math.min(1,(g.upper_m**2+d*d-g.lower_m**2)/(2*g.upper_m*d))),a=Math.atan2(dz,dx)+out*Math.acos(cos);
      const knee=[pivot[0]+g.upper_m*Math.cos(a),pivot[1]+g.upper_m*Math.sin(a)],au=angle(pivot,knee),al=angle(knee,axle);
      rig.upper[side*2+k].rotation.z=-au;rig.lower[side*2+k].rotation.z=-(al-au);
    });
    if(wheels[side])wheels[side].position.y=axle[1];
  });
}

