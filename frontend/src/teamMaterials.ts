import * as THREE from 'three';
import type {TeamId} from './types';

// Broadcast palette: saturated referee-light colours for LEDs and HUD fills; TEAM_COLORS stays the softer UI tint.
export const LED_COLORS:Record<TeamId,string>={red:'#ff3b30',blue:'#2f8cff'};
export const SHELL:Record<TeamId,string>={red:'#1c1517',blue:'#131922'};
// Smallest geometry radius that still casts a shadow: below this a part only costs a draw in every
// shadow refresh, and the field never shows its shadow anyway.
const SHADOW_CASTER_RADIUS=.22;

// Real robots, bases and outposts are black machines whose team identity is carried by light strips and armour lights.
export function teamMaterial(source:THREE.Material,team?:TeamId){
  const material=source.clone() as THREE.MeshStandardMaterial;
  if(!team||!material.name.startsWith('Team'))return material;
  if(material.name.startsWith('TeamPrimary')){material.color.set(SHELL[team]);material.metalness=Math.max(material.metalness,.35);material.roughness=Math.min(material.roughness,.55);material.emissive?.set('#000000');}
  else{
    material.color.set(LED_COLORS[team]);material.emissive?.set(LED_COLORS[team]);
    // The light bars are the only team colour on a black machine, so they are driven well past
    // the shell's response: at 30 m a pale tint reads as grey, a saturated bar reads as the team.
    material.emissiveIntensity=Math.max(material.emissiveIntensity||1,3.4);
  }
  return material;
}

export function cloneForTeam(scene:THREE.Object3D,team?:TeamId){
  const clone=scene.clone(true);
  // One tinted clone per source material, shared by every mesh that used it: a team swap used to
  // hand each mesh its own material, which multiplied state changes, defeated batching and made the
  // renderer sort the whole field one draw at a time.
  const tinted=new Map<string,THREE.Material>();
  const tint=(m:THREE.Material)=>{const key=m.uuid;let made=tinted.get(key);if(!made){made=teamMaterial(m,team);tinted.set(key,made);}return made;};
  clone.traverse(o=>{
    if(!(o instanceof THREE.Mesh))return;
    // Only parts big enough to read on the floor throw a shadow: forcing every bolt and light bar to
    // cast one doubled the shadow pass for shadows nobody can see from a broadcast camera.
    if(!o.geometry.boundingSphere)o.geometry.computeBoundingSphere();
    const radius=o.geometry.boundingSphere?.radius??0;
    o.castShadow=radius===0||radius>=SHADOW_CASTER_RADIUS;
    o.receiveShadow=true;
    const list=Array.isArray(o.material)?o.material as THREE.Material[]:[o.material as THREE.Material];
    const shared=list.map(tint);
    o.material=Array.isArray(o.material)?shared:shared[0];
  });
  return clone;
}
