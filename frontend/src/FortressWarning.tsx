import {useEffect,useMemo,useRef,type MutableRefObject} from 'react';
import {useFrame} from '@react-three/fiber';
import {Html} from '@react-three/drei';
import * as THREE from 'three';
import {fortressAlert} from './fortressAlert';
import {terrainHeight} from './terrain';
import {LED_COLORS} from './teamMaterials';
import type {RenderFeed,TeamId} from './types';

const HEIGHT=4.1;
const vertex=`varying vec2 vUv;void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`;
const fragment=`uniform vec3 uColor;uniform float uOpacity;uniform float uTime;varying vec2 vUv;
void main(){float lift=pow(.5+.5*cos((vUv.y*4.-uTime*1.2)*6.283185),10.);float rim=.65+.35*cos(vUv.x*6.283185*2.);
float fade=.28+.72*pow(1.-vUv.y,.65);float alpha=uOpacity*(.13+lift*.12)*fade*rim;
gl_FragColor=vec4(uColor*(1.15+lift*.25),alpha);
#include <colorspace_fragment>
}`;

export function FortressWarning({defender,feed}:{defender:TeamId;feed:MutableRefObject<RenderFeed>}){
 const attacker=defender==='red'?'blue':'red';
 const group=useRef<THREE.Group>(null),label=useRef<HTMLDivElement>(null),number=useRef<HTMLElement>(null),ring=useRef<THREE.MeshBasicMaterial>(null),core=useRef<THREE.MeshBasicMaterial>(null);
 const opacity=useRef(0),generation=useRef('');
 const material=useMemo(()=>new THREE.ShaderMaterial({uniforms:{uColor:{value:new THREE.Color(LED_COLORS[attacker])},uOpacity:{value:0},uTime:{value:0}},vertexShader:vertex,fragmentShader:fragment,transparent:true,depthWrite:false,side:THREE.DoubleSide,blending:THREE.AdditiveBlending,toneMapped:false}),[attacker]);
 useEffect(()=>()=>material.dispose(),[material]);
 useFrame((_,dt)=>{
  const f=feed.current.frame,g=group.current,node=label.current;if(!f||!g||!node)return;
  if(generation.current!==feed.current.generation){generation.current=feed.current.generation;opacity.current=0;}
  const alert=fortressAlert(f,defender);
  if(alert){g.position.set(alert.x-f.arena.width/2,terrainHeight(f.arena,alert.x,alert.y)+.025,alert.y-f.arena.height/2);
   if(number.current)number.current.textContent=String(Math.ceil(alert.remaining-1e-7));
   node.dataset.remaining=alert.remaining.toFixed(2);node.dataset.robot=alert.robot;}
  opacity.current=THREE.MathUtils.damp(opacity.current,alert?1:0,alert?14:11,Math.min(dt,.1));
  const visible=opacity.current>.005;g.visible=visible;node.style.display=visible?'flex':'none';node.style.opacity=String(opacity.current);
  material.uniforms.uOpacity.value=opacity.current;material.uniforms.uTime.value=f.time;
  if(ring.current)ring.current.opacity=opacity.current*.58;if(core.current)core.current.opacity=opacity.current*.12;
 });
 return <group ref={group} visible={false}>
  <mesh position={[0,HEIGHT/2,0]} material={material} renderOrder={10}><cylinderGeometry args={[.72,.72,HEIGHT,64,1,true]}/></mesh>
  <mesh rotation={[-Math.PI/2,0,0]} renderOrder={11}><ringGeometry args={[.62,.75,80]}/><meshBasicMaterial ref={ring} color={LED_COLORS[attacker]} transparent opacity={0} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} side={THREE.DoubleSide}/></mesh>
  <mesh rotation={[-Math.PI/2,0,0]} position={[0,.006,0]} renderOrder={10}><circleGeometry args={[.69,64]}/><meshBasicMaterial ref={core} color={LED_COLORS[attacker]} transparent opacity={0} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false}/></mesh>
  <Html center position={[0,HEIGHT+.32,0]} zIndexRange={[4,1]} style={{pointerEvents:'none'}}><div ref={label} className={`fortress-countdown ${attacker}`} data-fortress-warning={defender} data-attacker={attacker} role="timer" aria-label={`${defender==='red'?'红':'蓝'}方基地护甲展开倒计时`} style={{display:'none'}}><span>基地护甲展开</span><div><b ref={number}>6</b><small>秒</small></div></div></Html>
 </group>;
}
