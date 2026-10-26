import {useEffect,useMemo,useRef,type MutableRefObject} from 'react';
import {useFrame} from '@react-three/fiber';
import {Html} from '@react-three/drei';
import * as THREE from 'three';
import {fortressCapture} from './fortressAlert';
import {terrainHeight} from './terrain';
import {LED_COLORS} from './teamMaterials';
import type {RenderFeed,TeamId} from './types';

const HEIGHT=4.1;
const vertex=`varying vec2 vUv;void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`;
const fragment=`uniform vec3 uColor;uniform float uOpacity;uniform float uTime;varying vec2 vUv;
void main(){float lift=pow(.5+.5*cos((vUv.y*4.-uTime*1.2)*6.283185),10.);float rim=.65+.35*cos(vUv.x*6.283185*2.);
float fade=.28+.72*pow(1.-vUv.y,.65);float alpha=uOpacity*(.2+lift*.18)*fade*rim;
gl_FragColor=vec4(uColor*(1.15+lift*.25),alpha);
#include <colorspace_fragment>
}`;

// The enemy capture of `defender`'s fortress, drawn on the fortress plateau itself: a beam in the
// attacker's colour, a turning hexagon (the plateau outline) and the live `hold / holdSeconds`
// readout. It runs from the first tick of the hold, not only the last seconds, so a viewer can see
// the whole countdown; a pilot in first person has none of it.
export function FortressWarning({defender,feed,hidden=false}:{defender:TeamId;feed:MutableRefObject<RenderFeed>;hidden?:boolean}){
 const attacker=defender==='red'?'blue':'red';
 const group=useRef<THREE.Group>(null),label=useRef<HTMLDivElement>(null),number=useRef<HTMLElement>(null),total=useRef<HTMLElement>(null),bar=useRef<HTMLElement>(null);
 const ring=useRef<THREE.MeshBasicMaterial>(null),core=useRef<THREE.MeshBasicMaterial>(null),hexRing=useRef<THREE.MeshBasicMaterial>(null),hex=useRef<THREE.Mesh>(null);
 const opacity=useRef(0),generation=useRef('');
 const material=useMemo(()=>new THREE.ShaderMaterial({uniforms:{uColor:{value:new THREE.Color(LED_COLORS[attacker])},uOpacity:{value:0},uTime:{value:0}},vertexShader:vertex,fragmentShader:fragment,transparent:true,depthWrite:false,side:THREE.DoubleSide,blending:THREE.AdditiveBlending,toneMapped:false}),[attacker]);
 useEffect(()=>()=>material.dispose(),[material]);
 useFrame((_,dt)=>{
  const f=feed.current.frame,g=group.current,node=label.current;if(!f||!g||!node)return;
  if(generation.current!==feed.current.generation){generation.current=feed.current.generation;opacity.current=0;material.uniforms.uTime.value=0;}
  const capture=hidden?null:fortressCapture(f,defender);
  if(capture){
   g.position.set(capture.x-f.arena.width/2,terrainHeight(f.arena,capture.x,capture.y)+.025,capture.y-f.arena.height/2);
   if(number.current)number.current.textContent=capture.hold.toFixed(1);
   if(total.current)total.current.textContent=`s / ${capture.holdSeconds} s`;
   if(bar.current)bar.current.style.width=`${(capture.progress*100).toFixed(1)}%`;
   // The hexagon spins faster as the countdown closes, so the last seconds read as urgent.
   if(hex.current)hex.current.rotation.z=-f.time*(.45+1.7*capture.progress);
   node.dataset.hold=capture.hold.toFixed(2);node.dataset.remaining=capture.remaining.toFixed(2);node.dataset.robot=capture.robot;
   material.uniforms.uTime.value+=Math.min(dt,.1)*(1+1.5*capture.progress);
  }
  opacity.current=THREE.MathUtils.damp(opacity.current,capture?1:0,hidden?30:capture?15:11,Math.min(dt,.1));
  const visible=opacity.current>.005;g.visible=visible;node.style.display=visible?'flex':'none';node.style.opacity=String(opacity.current);
  material.uniforms.uOpacity.value=opacity.current;
  if(ring.current)ring.current.opacity=opacity.current*.58;
  if(hexRing.current)hexRing.current.opacity=opacity.current*.42;
  if(core.current)core.current.opacity=opacity.current*.12;
 });
 return <group ref={group} visible={false}>
  <mesh position={[0,HEIGHT/2,0]} material={material} renderOrder={10}><cylinderGeometry args={[.88,.88,HEIGHT,64,1,true]}/></mesh>
  <mesh rotation={[-Math.PI/2,0,0]} renderOrder={11}><ringGeometry args={[.62,.75,80]}/><meshBasicMaterial ref={ring} color={LED_COLORS[attacker]} transparent opacity={0} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} side={THREE.DoubleSide}/></mesh>
  <mesh ref={hex} rotation={[-Math.PI/2,0,0]} position={[0,.009,0]} renderOrder={11}><ringGeometry args={[.84,.92,6,1]}/><meshBasicMaterial ref={hexRing} color={LED_COLORS[attacker]} transparent opacity={0} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} side={THREE.DoubleSide}/></mesh>
  <mesh rotation={[-Math.PI/2,0,0]} position={[0,.006,0]} renderOrder={10}><circleGeometry args={[.69,6]}/><meshBasicMaterial ref={core} color={LED_COLORS[attacker]} transparent opacity={0} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false}/></mesh>
  <Html center position={[0,HEIGHT+.32,0]} zIndexRange={[4,1]} style={{pointerEvents:'none'}}><div ref={label} className={`fortress-countdown ${attacker}`} data-fortress-warning={defender} data-attacker={attacker} role="timer" aria-label={`${defender==='red'?'红':'蓝'}方堡垒正在被占领`} style={{display:'none'}}><span>堡垒正在被占领</span><div><b ref={number}>0.0</b><small ref={total}>s / 10 s</small></div><i className="fortress-bar"><em ref={bar}/></i></div></Html>
 </group>;
}
