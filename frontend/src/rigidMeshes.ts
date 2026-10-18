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
  templates.set(source,scene);return scene;
}
