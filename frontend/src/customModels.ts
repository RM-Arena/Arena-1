import * as THREE from 'three';
import {useGLTF} from '@react-three/drei';
import {useMemo} from 'react';
import type {Frame,Metadata,RobotSkin,TeamId} from './types';
import {batchFlyingBody,batchRigidMeshes} from './rigidMeshes';

// Uploaded robot appearances (rmuc_arena/custom_models.py). The asset URL carries the base model's stowed
// envelope and the mesh's forward axis, so any user GLB is turned to face +X, scaled into that envelope and
// stood on the floor; replays render the same way without the registry.
// Server assets carry the fit in the query; local previews (blob: URLs) carry it in the fragment.
export const isCustomAsset=(url:string)=>/[?#]fit=/.test(url);
const TURN:Record<string,number>={'+x':0,'-x':Math.PI,'+z':Math.PI/2,'-z':-Math.PI/2};
const fitted=new WeakMap<THREE.Object3D,Map<string,THREE.Object3D>>();
export function fitCustomModel(scene:THREE.Object3D,url:string){
  let cache=fitted.get(scene);if(!cache){cache=new Map();fitted.set(scene,cache);}
  const hit=cache.get(url);if(hit)return hit;
  const query=new URLSearchParams(url.match(/[?#](fit=.*)$/)?.[1]||''),fit=(query.get('fit')||'.6,.6,.5').split(',').map(Number),turn=TURN[query.get('fwd')||'+x']??0;
  const group=new THREE.Group(),inner=scene.clone(true);inner.rotation.y=turn;group.add(inner);group.updateMatrixWorld(true);
  let box=new THREE.Box3().setFromObject(inner);const size=box.getSize(new THREE.Vector3());
  const scale=Math.min(fit[0]/Math.max(1e-6,size.x),fit[1]/Math.max(1e-6,size.z),(fit[2]||.5)*1.6/Math.max(1e-6,size.y));
  inner.scale.multiplyScalar(Number.isFinite(scale)&&scale>0?scale:1);group.updateMatrixWorld(true);
  box=new THREE.Box3().setFromObject(inner);const center=box.getCenter(new THREE.Vector3());
  inner.position.x-=center.x;inner.position.z-=center.z;inner.position.y-=box.min.y;
  // A floor ring in the team's light colour (materials named Team* are tinted per team) keeps sides readable;
  // its notch marks the simulated forward direction, so uploaders can check the axis and viewers the heading.
  const radius=Math.max(fit[0],fit[1])*.62,glow=new THREE.MeshStandardMaterial({name:'TeamGlowRing',color:'#ffffff',emissive:'#ffffff',emissiveIntensity:1.6,side:THREE.DoubleSide});
  const ring=new THREE.Mesh(new THREE.RingGeometry(radius*.9,radius,48),glow);ring.rotation.x=-Math.PI/2;ring.position.y=.012;group.add(ring);
  const notch=new THREE.Shape([new THREE.Vector2(radius*1.28,0),new THREE.Vector2(radius*1.02,radius*.16),new THREE.Vector2(radius*1.02,-radius*.16)]);
  const arrow=new THREE.Mesh(new THREE.ShapeGeometry(notch),glow);arrow.rotation.x=-Math.PI/2;arrow.position.y=.013;group.add(arrow);
  cache.set(url,group);return group;
}
// useGLTF plus the fitting above for uploaded appearances.
// Drones are flown by the engine, not by their GLTF clips: a hangar of four is otherwise ~55 separate
// parts each (and as many draw calls, twice over with the shadow pass), so their rigid parts are
// merged per material — rotor subgroups keep their own node, so the spin still works.
const DRONE_ASSET=/^\/assets\/drone-/;
export function useRobotScene(url:string){
  const {scene,animations}=useGLTF(url);
  const drone=DRONE_ASSET.test(url),rigid=/^\/assets\/(?:robot|drone)-/.test(url)&&!animations.length;
  return useMemo(()=>isCustomAsset(url)?fitCustomModel(scene,url):drone?batchFlyingBody(scene):rigid?batchRigidMeshes(scene):scene,[scene,animations,url,drone,rigid]);
}

export const skinFor=(metadata:Metadata|null|undefined,team:TeamId,model:number|undefined):RobotSkin|undefined=>model===undefined?undefined:metadata?.skins?.[team]?.[String(model)];
// Shows uploaded appearances in a frame: each robot keeps its simulated hardware and takes the chosen mesh.
export function applySkins<T extends Frame|null|undefined>(frame:T,metadata:Metadata|null|undefined):T{
  if(!frame||!metadata?.skins)return frame;
  for(const r of frame.robots){const skin=skinFor(metadata,r.team,r.model_slot??r.slot);if(skin)r.model_asset=skin.asset;}
  return frame;
}
