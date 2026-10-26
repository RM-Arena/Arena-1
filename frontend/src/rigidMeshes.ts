import * as THREE from 'three';
import {mergeGeometries} from 'three/examples/jsm/utils/BufferGeometryUtils.js';

// Only these shipped robot groups are rigid decorations. Every other group stays
// a separate batch boundary, including unknown joints added by future models.
const decoration=/^(?:ArmorMount_\d+|ArmorPlate(?:\.?\d+)?|Battery|LightBar|SuperCapModule|Magazine|VideoTransmitter|StatusBeacon|ArmCamera)$/;
const templates=new WeakMap<THREE.Object3D,THREE.Object3D>();

function layout(geometry:THREE.BufferGeometry){
  return [!!geometry.index,...Object.keys(geometry.attributes).sort().map(name=>{
    const a=geometry.attributes[name];
    return `${name}:${a.itemSize}:${a.normalized}:${a.array.constructor.name}:${'gpuType' in a?a.gpuType:''}`;
  })].join('|');
}

// Bake only fixed relative transforms. Wheels, leg links, turrets, arm joints,
// armour-number holders and visibility switches keep their original hierarchy.
// Cached geometry belongs to the template, just like the GLTF loader's geometry.
// A whole structure is rigid scenery apart from a few named hinges: the base's outer shells, the
// outpost rotor, the rune rotor and the core's carriage / lift / yaw / pitch / roll chain. Those are
// never touched, and neither is anything hanging under them; the rest is baked into the asset root
// and merged per material, which turns a base or the field from a hundred draw calls into a handful.
const MOVING = /^(?:BaseShell_|ArmorRotor|RuneRotor|RuneArm_|CoreCarriage|CoreLift|CoreYaw|CorePitch|CoreRoll|CoreUnit|AvailableUnit_|CoreHead)/;

// Every node the cockpit poses on a robot, plus the armour-number plates it swaps out at runtime.
// Colour merging must never cross one of these, or the animation would move a baked-in copy of the
// part while its joint stayed behind.
const ROBOT_JOINT = /^(?:Chassis|Turret|GunPitch|GunElevator|LauncherModule|CarriedUnit|ArmorNumber|ArmorDigit|SteerModule|FoldMast|Wheel|Rotor_|Leg(?:R|L|RF|RB|LF|LB)_(?:Thigh|Shank|Upper|Lower)|Arm(?:Slew|Lift|MastStage|Reach|Wrist\w*|Shoulder|Forearm)|Aux_|GripperJaw)/;

// A merged batch carries the roughness and metalness of every part it swallowed in a per-vertex
// attribute, because a standard material otherwise has one value for the whole draw. The two chunks
// are the exact places three reads those uniforms, so the lighting path stays stock.
function surfaceShader(material: THREE.MeshStandardMaterial) {
  material.onBeforeCompile = shader => {
    shader.vertexShader = 'attribute vec2 aSurface;\nvarying vec2 vSurface;\n' + shader.vertexShader
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvSurface = aSurface;');
    shader.fragmentShader = 'varying vec2 vSurface;\n' + shader.fragmentShader
      .replace('#include <roughnessmap_fragment>', '#include <roughnessmap_fragment>\nroughnessFactor = vSurface.x;')
      .replace('#include <metalnessmap_fragment>', '#include <metalnessmap_fragment>\nmetalnessFactor = vSurface.y;');
  };
  // Every batch shares one program, so the compiler sees a single shader for all of them.
  material.customProgramCacheKey = () => 'colour-batch-surface';
}

// Shipped structures give nearly every part its own material, so material-keyed merging barely helps.
// The rest of the way is to bake each part's diffuse colour *and* its roughness / metalness into
// vertex attributes and merge everything that shares a texture into one draw: a base drops from ~100
// calls to a few, and a robot's hull from 13 material variants to one. The batch's material reads the
// baked surface from `aSurface` (see `surfaceShader`), so paint and bare metal still shade apart.
// Team lights and self-lit parts are left alone, because the cockpit animates them per material.
// `joints` merges inside one joint instead of across the whole asset: an articulated model (a
// robot's hull, turret, gun, each wheel, each leg link) collapses to a few draws per joint without
// touching the node the engine animates. The scope is the nearest ancestor on the way up that the
// cockpit actually poses, so a part modelled as its own node still folds into its joint.
function mergeByColour(source: THREE.Object3D, keep?: (node: THREE.Object3D) => boolean, joints?: RegExp) {
  const scopes = new Map<THREE.Object3D, Map<string, THREE.Mesh[]>>();
  source.traverse(node => {
    if (!(node instanceof THREE.Mesh) || node instanceof THREE.SkinnedMesh || node instanceof THREE.InstancedMesh) return;
    if (!node.visible || node.children.length) return;
    if (keep?.(node)) return;
    const material = node.material;
    if (Array.isArray(material) || !(material instanceof THREE.MeshStandardMaterial) || !material.visible) return;
    if (material.name.startsWith('Team')) return;
    if (material.emissive && material.emissive.getHex() !== 0) return;
    // A surface that genuinely blends — glass, a glowing panel, a decal — cannot share a draw with its
    // neighbours, because the transparent pass has to sort it against them every frame. A solid part
    // that the exporter merely left in "blend" mode is another matter: at full opacity, with depth
    // writes and normal blending, the pixel lands the same whatever order the parts are drawn in, so
    // those parts join a batch like any other. The flag rides in the key, so the two kinds never end
    // up in one draw.
    if (material.alphaMap || material.alphaTest > 0) return;
    if (material.transparent && (material.opacity < .999 || !material.depthWrite || material.blending !== THREE.NormalBlending)) return;
    if (Object.keys(node.geometry.morphAttributes || {}).length) return;
    // A mirrored part would flip winding once its transform is baked into the vertices.
    if (node.matrixWorld.determinant() <= 0) return;
    for (let p: THREE.Object3D | null = node; p && p !== source; p = p.parent) {
      if (MOVING.test(p.name)) return;
    }
    const key = [material.map?.uuid ?? '', material.side, material.transparent, layout(node.geometry)].join(':');
    let scope = source;
    if (joints) {
      scope = source;
      for (let p: THREE.Object3D | null = node.parent; p && p !== source; p = p.parent) {
        if (joints.test(p.name)) { scope = p; break; }
      }
    }
    let groups = scopes.get(scope);
    if (!groups) { groups = new Map(); scopes.set(scope, groups); }
    const group = groups.get(key);
    if (group) group.push(node);
    else groups.set(key, [node]);
  });
  for (const [scope, groups] of scopes) {
    const inverse = new THREE.Matrix4().copy(scope.matrixWorld).invert();
    for (const meshes of groups.values()) {
      if (meshes.length < 2) continue;
      const parts: THREE.BufferGeometry[] = [];
      for (const mesh of meshes) {
        const material = mesh.material as THREE.MeshStandardMaterial;
        const geometry = mesh.geometry.clone().applyMatrix4(new THREE.Matrix4().multiplyMatrices(inverse, mesh.matrixWorld));
        const count = geometry.attributes.position.count;
        const shade = new Float32Array(count * 3);
        for (let i = 0; i < count; i++) {
          shade[i * 3] = material.color.r;
          shade[i * 3 + 1] = material.color.g;
          shade[i * 3 + 2] = material.color.b;
        }
        geometry.setAttribute('color', new THREE.BufferAttribute(shade, 3));
        const surface = new Float32Array(count * 2);
        for (let i = 0; i < count; i++) {
          surface[i * 2] = material.roughness;
          surface[i * 2 + 1] = material.metalness;
        }
        geometry.setAttribute('aSurface', new THREE.BufferAttribute(surface, 2));
        parts.push(geometry);
      }
      const merged = mergeGeometries(parts);
      parts.forEach(part => part.dispose());
      if (!merged) continue;
      merged.computeBoundingBox();
      merged.computeBoundingSphere();
      const first = meshes[0];
      const material = (first.material as THREE.MeshStandardMaterial).clone();
      material.vertexColors = true;
      material.color.setRGB(1, 1, 1);
      surfaceShader(material);
      const batch = new THREE.Mesh(merged, material);
      batch.name = `ColourBatch_${meshes.length}`;
      // A batch speaks for every part it swallowed, so it keeps the shadow behaviour of any of them;
      // the radius trim that follows removes the small stuff again.
      batch.castShadow = meshes.some(mesh => mesh.castShadow);
      batch.receiveShadow = meshes.some(mesh => mesh.receiveShadow);
      scope.add(batch);
      meshes.forEach(mesh => mesh.removeFromParent());
    }
  }
}

export function batchStaticStructure(source: THREE.Object3D, options: {byColour?: boolean; trimShadows?: boolean} = {}) {
  const {byColour = true, trimShadows = true} = options;
  source.updateMatrixWorld(true);
  const inverse = new THREE.Matrix4().copy(source.matrixWorld).invert();
  const groups = new Map<string, THREE.Mesh[]>();
  source.traverse(node => {
    if (!(node instanceof THREE.Mesh) || node instanceof THREE.SkinnedMesh || node instanceof THREE.InstancedMesh) return;
    if (!node.visible || node.children.length) return;
    const { geometry, material } = node;
    if (Array.isArray(material) || material.transparent || !material.visible) return;
    if (Object.keys(geometry.morphAttributes || {}).length) return;
    // Baked into the vertices of a batch, a mirrored part would flip its winding and turn inside out.
    if (node.matrixWorld.determinant() <= 0) return;
    for (let p: THREE.Object3D | null = node; p && p !== source; p = p.parent) {
      if (MOVING.test(p.name)) return;
    }
    const key = `${material.uuid}:${node.castShadow}:${node.receiveShadow}:${node.renderOrder}:${layout(geometry)}`;
    const group = groups.get(key);
    if (group) group.push(node);
    else groups.set(key, [node]);
  });
  for (const meshes of groups.values()) {
    if (meshes.length < 2) continue;
    const parts = meshes.map(mesh => mesh.geometry.clone().applyMatrix4(new THREE.Matrix4().multiplyMatrices(inverse, mesh.matrixWorld)));
    const geometry = mergeGeometries(parts);
    parts.forEach(part => part.dispose());
    if (!geometry) continue;
    geometry.computeBoundingBox();
    geometry.computeBoundingSphere();
    const first = meshes[0];
    const batch = new THREE.Mesh(geometry, first.material);
    batch.name = `StaticBatch_${(first.material as THREE.Material).name || meshes.length}`;
    batch.castShadow = first.castShadow;
    batch.receiveShadow = first.receiveShadow;
    batch.renderOrder = first.renderOrder;
    source.add(batch);
    meshes.forEach(mesh => mesh.removeFromParent());
  }
  if (byColour) mergeByColour(source);
  if (!trimShadows) return source;
  // Shadow casters are a full draw each time the shadow map refreshes. On a structure only the big
  // masses throw a shadow anyone reads from a cockpit camera, so the small parts stop casting.
  source.traverse(node => {
    if (!(node instanceof THREE.Mesh) || !node.castShadow) return;
    if (!node.geometry.boundingSphere) node.geometry.computeBoundingSphere();
    const radius = node.geometry.boundingSphere?.radius ?? 0;
    if (radius > 0 && radius < 1.2) node.castShadow = false;
  });
  return source;
}

export function batchRigidMeshes(source:THREE.Object3D){
  const cached=templates.get(source);if(cached)return cached;
  const scene=source.clone(true);scene.updateMatrixWorld(true);
  const batches=new Map<THREE.Object3D,Map<string,THREE.Mesh[]>>();
  scene.traverse(node=>{
    if(!(node instanceof THREE.Mesh)||node instanceof THREE.SkinnedMesh||node instanceof THREE.InstancedMesh||node.children.length||!node.visible)return;
    const {geometry,material}=node;
    if(Array.isArray(material)||material.transparent||Object.keys(geometry.morphAttributes).length||geometry.drawRange.start!==0||geometry.drawRange.count!==Infinity)return;
    let parent=node.parent;if(!parent)return;
    while(parent.parent&&decoration.test(parent.name)&&parent.visible&&parent.layers.mask===node.layers.mask)parent=parent.parent;
    // Keep reflected local transforms on their original nodes (baking would flip winding).
    const relative=new THREE.Matrix4().copy(parent.matrixWorld).invert().multiply(node.matrixWorld);
    if(relative.determinant()<=0)return;
    let groups=batches.get(parent);if(!groups){groups=new Map();batches.set(parent,groups);}
    const key=`${material.uuid}:${node.castShadow}:${node.receiveShadow}:${node.renderOrder}:${node.layers.mask}:${layout(geometry)}`;
    const group=groups.get(key);if(group)group.push(node);else groups.set(key,[node]);
  });
  for(const [parent,groups] of batches){
    const inverse=new THREE.Matrix4().copy(parent.matrixWorld).invert();
    for(const meshes of groups.values()){
      if(meshes.length<2)continue;
      const parts=meshes.map(mesh=>mesh.geometry.clone().applyMatrix4(new THREE.Matrix4().multiplyMatrices(inverse,mesh.matrixWorld)));
      const geometry=mergeGeometries(parts);parts.forEach(part=>part.dispose());if(!geometry)continue;
      geometry.computeBoundingBox();geometry.computeBoundingSphere();
      const first=meshes[0],batch=new THREE.Mesh(geometry,first.material);batch.name=`RigidBatch_${first.material instanceof THREE.Material?first.material.name:''}`;
      batch.castShadow=first.castShadow;batch.receiveShadow=first.receiveShadow;batch.renderOrder=first.renderOrder;batch.layers.mask=first.layers.mask;
      parent.add(batch);meshes.forEach(mesh=>mesh.removeFromParent());
    }
  }
  // Robots paint nearly every part with its own material, so material-keyed merging leaves one draw
  // per bolt. Baking the colours into vertex colours *inside each joint* collapses the hull, the
  // turret, the gun and every wheel to a handful of draws while the joints themselves stay animated.
  mergeByColour(scene, undefined, ROBOT_JOINT);
  // Tiny parts — bolts, cameras, light bars, plate edges — cast shadows nobody can see, and each
  // one costs a full draw in the shadow pass. Dropping them from the caster set is free.
  scene.traverse(node=>{
    if(!(node instanceof THREE.Mesh)||!node.castShadow)return;
    if(!node.geometry.boundingSphere)node.geometry.computeBoundingSphere();
    const radius=node.geometry.boundingSphere?.radius??0;
    if(radius>0&&radius<.16)node.castShadow=false;
  });
  templates.set(source,scene);return scene;
}

// A drone is a flying rigid body: the engine never plays its GLTF clips (the rotors are spun from
// `Rotor_*` node names), and a hangar of four is otherwise ~55 draw calls *each*, every shadow
// refresh included. Everything outside a rotor subtree is baked into one batch per surface response,
// which leaves a handful of draws plus one per rotor.
const ROTOR=/^Rotor_/;
export function batchFlyingBody(source:THREE.Object3D){
  const cached=templates.get(source);if(cached)return cached;
  const scene=source.clone(true);scene.updateMatrixWorld(true);
  const spinning=(node:THREE.Object3D)=>{for(let p:THREE.Object3D|null=node;p;p=p.parent)if(ROTOR.test(p.name))return true;return false;};
  // The drone's shell is painted one material per part, so material-keyed merging alone changes
  // nothing; baking each part's colour into vertex colours is what turns ~55 draws into a handful.
  mergeByColour(scene,spinning);
  // What spins is the rotor subtree, not the pieces inside it, so a hub and its blades can share one
  // draw per rotor instead of one each.
  const rotors=new Set<THREE.Object3D>();
  scene.traverse(node=>{if(ROTOR.test(node.name))rotors.add(node);});
  rotors.forEach(rotor=>mergeByColour(rotor));
  // A 1.4 m drone throws one readable shadow, from its hull: the shell details only cost draws.
  scene.traverse(node=>{
    if(!(node instanceof THREE.Mesh)||!node.castShadow)return;
    if(!node.geometry.boundingSphere)node.geometry.computeBoundingSphere();
    const radius=node.geometry.boundingSphere?.radius??0;
    if(radius>0&&radius<.2)node.castShadow=false;
  });
  templates.set(source,scene);return scene;
}
