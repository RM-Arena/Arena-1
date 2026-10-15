import {useEffect,useMemo,useRef,type JSX} from 'react';
import {useFrame} from '@react-three/fiber';
import * as THREE from 'three';

// Arena surroundings seen behind the field on the broadcast: dark tiered stands, crowd, LED ribbon boards and end screens.
const W=28,H=15,GAP=5,TIERS=7,DEPTH=1.25,RISE=.55;
const rng=(seed:number)=>()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};

// One seamless cycle of the scrolling ribbon; RIBBON_M is its length in metres on the boards.
const RIBBON_FONT='italic 800 50px "SF Pro Display","PingFang SC",system-ui,sans-serif',RIBBON_PARTS=[['ROBOMASTER 2026','#e9edf7'],['THE FINALS','#ff3b6b'],['RMUC ARENA','#7fb4ff'],['STRATEGY LEAGUE','#e9edf7']] as const;
let RIBBON_M=16;
function ribbonTexture(){
  const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d')!;ctx.font=RIBBON_FONT;
  const width=Math.ceil(RIBBON_PARTS.reduce((w,[text])=>w+ctx.measureText(text).width+60,0));canvas.width=width;canvas.height=96;RIBBON_M=width/96*.5;
  const g=ctx.createLinearGradient(0,0,width,0);g.addColorStop(0,'#1a0b33');g.addColorStop(.5,'#0b1a3d');g.addColorStop(1,'#1a0b33');ctx.fillStyle=g;ctx.fillRect(0,0,width,96);
  ctx.font=RIBBON_FONT;ctx.textBaseline='middle';let x=18;
  for(const [text,color] of RIBBON_PARTS){ctx.fillStyle=color;ctx.fillText(text,x,50);x+=ctx.measureText(text).width+60;ctx.fillStyle='#ffcf4a';ctx.fillRect(x-38,43,12,12);}
  ctx.fillStyle='rgba(255,255,255,.07)';for(let y=0;y<96;y+=4)ctx.fillRect(0,y,width,1);
  const t=new THREE.CanvasTexture(canvas);t.colorSpace=THREE.SRGBColorSpace;t.wrapS=THREE.RepeatWrapping;t.anisotropy=4;return t;
}
function screenTexture(team:'red'|'blue'){
  const canvas=document.createElement('canvas');canvas.width=1024;canvas.height=512;const ctx=canvas.getContext('2d')!;
  const g=ctx.createLinearGradient(0,0,1024,512);g.addColorStop(0,team==='red'?'#3a0610':'#041a3c');g.addColorStop(1,'#07080f');ctx.fillStyle=g;ctx.fillRect(0,0,1024,512);
  ctx.strokeStyle=team==='red'?'#ff3b30':'#2f8cff';ctx.lineWidth=10;ctx.strokeRect(24,24,976,464);
  ctx.textAlign='center';ctx.fillStyle='#f4f6fb';ctx.font='italic 900 120px "SF Pro Display",system-ui,sans-serif';ctx.fillText('RMUC',512,250);
  ctx.font='700 54px "PingFang SC",system-ui,sans-serif';ctx.fillStyle=team==='red'?'#ff8a80':'#8cc4ff';ctx.fillText(team==='red'?'红方 · RED SIDE':'蓝方 · BLUE SIDE',512,350);
  const t=new THREE.CanvasTexture(canvas);t.colorSpace=THREE.SRGBColorSpace;return t;
}

function Ribbon({length,height,repeat,texture,...props}:{length:number;height:number;repeat:number;texture:THREE.Texture}&JSX.IntrinsicElements['mesh']){
  const geometry=useMemo(()=>{const g=new THREE.PlaneGeometry(length,height),uv=g.attributes.uv as THREE.BufferAttribute;for(let i=0;i<uv.count;i++)uv.setX(i,uv.getX(i)*repeat);return g;},[length,height,repeat]);
  useEffect(()=>()=>geometry.dispose(),[geometry]);
  return <mesh geometry={geometry} {...props}><meshBasicMaterial map={texture} toneMapped={false} fog={false} side={THREE.DoubleSide}/></mesh>;
}

export function Venue(){
  const crowd=useRef<THREE.InstancedMesh>(null),ribbon=useMemo(ribbonTexture,[]),screens=useMemo(()=>({red:screenTexture('red'),blue:screenTexture('blue')}),[]);
  const sides=useMemo(()=>[
    {pos:[0,0,H/2+GAP] as const,rot:0,len:W+2*GAP+4},{pos:[0,0,-H/2-GAP] as const,rot:Math.PI,len:W+2*GAP+4},
    {pos:[W/2+GAP,0,0] as const,rot:Math.PI/2,len:H+2*GAP},{pos:[-W/2-GAP,0,0] as const,rot:-Math.PI/2,len:H+2*GAP}],[]);
  const seats=useMemo(()=>{const list:{m:THREE.Matrix4;c:THREE.Color}[]=[],next=rng(2026),o=new THREE.Object3D();
    for(const s of sides)for(let t=0;t<TIERS;t++)for(let x=-s.len/2+.5;x<s.len/2-.5;x+=.62){if(next()<.18)continue;
      o.position.set(x+(next()-.5)*.12,-.85+RISE*(t+1)+.28,DEPTH*(t+.5));o.position.applyAxisAngle(new THREE.Vector3(0,1,0),s.rot).add(new THREE.Vector3(...s.pos));o.rotation.set(0,s.rot,0);o.scale.set(.26,.34+next()*.1,.22);o.updateMatrix();
      const world=o.position.x,phone=next()<.02,v=.018+next()*.035;
      const c=phone?new THREE.Color(1.2,1.2,1.3):next()<.3?new THREE.Color(world<0?v*2.4:v*.7,v*.75,world<0?v*.7:v*2.6):new THREE.Color(v,v*1.04,v*1.12);list.push({m:o.matrix.clone(),c});}
    return list;},[sides]);
  useEffect(()=>{const m=crowd.current;if(!m)return;seats.forEach((s,i)=>{m.setMatrixAt(i,s.m);m.setColorAt(i,s.c);});m.instanceMatrix.needsUpdate=true;if(m.instanceColor)m.instanceColor.needsUpdate=true;},[seats]);
  useEffect(()=>()=>{ribbon.dispose();screens.red.dispose();screens.blue.dispose();},[ribbon,screens]);
  useFrame((_,dt)=>{ribbon.offset.x=(ribbon.offset.x+dt*.025)%1;});
  return <group>
    {sides.map((s,i)=><group key={i} position={s.pos} rotation={[0,s.rot,0]}>
      {Array.from({length:TIERS},(_,t)=><mesh key={t} position={[0,-.85+RISE*(t+1)/2,DEPTH*(t+.5)]} receiveShadow><boxGeometry args={[s.len,RISE*(t+1),DEPTH]}/><meshStandardMaterial color="#0d1016" roughness={.95}/></mesh>)}
      <Ribbon position={[0,.15,-.02]} rotation={[0,Math.PI,0]} length={s.len} height={.5} repeat={s.len/RIBBON_M} texture={ribbon}/>
      <mesh position={[0,-.85+RISE*TIERS+2.2,DEPTH*TIERS+.4]} rotation={[0,Math.PI,0]}><planeGeometry args={[s.len,4.4]}/><meshStandardMaterial color="#090b10" roughness={1} side={THREE.DoubleSide}/></mesh>
      <Ribbon position={[0,-.85+RISE*TIERS+3.4,DEPTH*TIERS+.3]} rotation={[0,Math.PI,0]} length={s.len} height={.7} repeat={s.len/(RIBBON_M*1.4)} texture={ribbon}/>
    </group>)}
    {(['red','blue'] as const).map(team=>{const x=(team==='red'?-1:1)*(W/2+GAP+DEPTH*TIERS+.2);return <mesh key={team} position={[x,7.6,0]} rotation={[0,team==='red'?Math.PI/2:-Math.PI/2,0]}><planeGeometry args={[9,4.5]}/><meshBasicMaterial map={screens[team]} toneMapped={false}/></mesh>;})}
    <instancedMesh ref={crowd} args={[undefined,undefined,seats.length]} frustumCulled={false}><boxGeometry args={[1,1,1]}/><meshStandardMaterial roughness={.95}/></instancedMesh>
    <mesh rotation={[-Math.PI/2,0,0]} position={[0,-.86,0]}><planeGeometry args={[240,240]}/><meshStandardMaterial color="#06080c" roughness={1}/></mesh>
  </group>;
}
