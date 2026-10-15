import * as THREE from 'three';
import type {TeamId} from './types';

// Broadcast palette: saturated referee-light colours for LEDs and HUD fills; TEAM_COLORS stays the softer UI tint.
export const LED_COLORS:Record<TeamId,string>={red:'#ff3b30',blue:'#2f8cff'};
const SHELL:Record<TeamId,string>={red:'#1c1517',blue:'#131922'};

// Real robots, bases and outposts are black machines whose team identity is carried by light strips and armour lights.
export function teamMaterial(source:THREE.Material,team?:TeamId){
  const material=source.clone() as THREE.MeshStandardMaterial;
  if(!team||!material.name.startsWith('Team'))return material;
  if(material.name.startsWith('TeamPrimary')){material.color.set(SHELL[team]);material.metalness=Math.max(material.metalness,.35);material.roughness=Math.min(material.roughness,.55);material.emissive?.set('#000000');}
  else{material.color.set(LED_COLORS[team]);material.emissive?.set(LED_COLORS[team]);}
  return material;
}

export function cloneForTeam(scene:THREE.Object3D,team?:TeamId){
  const clone=scene.clone(true);
  clone.traverse(o=>{if(o instanceof THREE.Mesh){o.castShadow=true;o.receiveShadow=true;const list=Array.isArray(o.material)?o.material as THREE.Material[]:[o.material as THREE.Material];const tinted=list.map(m=>teamMaterial(m,team));o.material=Array.isArray(o.material)?tinted:tinted[0];}});
  return clone;
}
