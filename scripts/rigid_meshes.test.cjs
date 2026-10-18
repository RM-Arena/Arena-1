const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
// Match GLTFLoader's ESM Three instance; mixing CJS/ESM breaks instanceof checks.
const THREE=require(path.join(path.dirname(require.resolve('three')),'three.module.js'));
const {GLTFLoader}=require('three/examples/jsm/loaders/GLTFLoader.js');
const source=fs.readFileSync(path.join(__dirname,'../frontend/src/rigidMeshes.ts'),'utf8');
const context={exports:{},require:name=>name==='three'?THREE:require(name)};
vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,context);
const {batchRigidMeshes}=context.exports;
const group=(name,parent)=>{const g=new THREE.Group();g.name=name;parent?.add(g);return g;};
const material=new THREE.MeshStandardMaterial();
const box=(parent,x=0,m=material)=>{const mesh=new THREE.Mesh(new THREE.BoxGeometry(),m);mesh.position.x=x;parent.add(mesh);return mesh;};
function counts(scene){let meshes=0,triangles=0;scene.traverse(o=>{if(o.isMesh){meshes++;triangles+=(o.geometry.index?.count??o.geometry.attributes.position.count)/3;}});return {meshes,triangles};}
// Compare actual world-space vertices, including duplicates, independently of batching or bounds.
function vertices(scene){scene.updateMatrixWorld(true);const result=[];scene.traverse(o=>{if(!o.isMesh)return;const p=o.geometry.attributes.position;for(let i=0;i<p.count;i++){const v=new THREE.Vector3().fromBufferAttribute(p,i).applyMatrix4(o.matrixWorld);result.push([v.x,v.y,v.z].map(n=>n.toFixed(4)).join(','));}});return result.sort();}

test('rigid decorations merge without changing geometry, source assets or cache identity',()=>{
 const scene=group('Robot'),chassis=group('Chassis',scene),battery=group('Battery',chassis);
 chassis.position.set(2,1,3);chassis.rotation.y=.4;battery.position.z=2;battery.rotation.z=.3;
 box(chassis,1);box(battery,2);const before=vertices(scene),result=batchRigidMeshes(scene);
 assert.equal(counts(result).meshes,1);assert.equal(counts(result).triangles,24);
 assert.deepEqual(vertices(result),before);assert.equal(counts(scene).meshes,2);
 assert.equal(batchRigidMeshes(scene),result);assert.notEqual(result,scene);
});

test('joints, unknown groups, armour numbers and visibility switches remain independent',()=>{
 const scene=group('Robot'),chassis=group('Chassis',scene);box(chassis);box(chassis,1);
 const names=['Turret','Wheel_0','LegR_Thigh','ArmLift','Aux_ArmReach','LauncherModule','CarriedUnit_0','ArmorNumber','FutureJoint'];
 for(const name of names){const joint=group(name,chassis);box(joint);box(joint,1);}
 const result=batchRigidMeshes(scene);
 for(const name of names){const original=scene.getObjectByName(name),batched=result.getObjectByName(name);assert.ok(batched);assert.equal(batched.parent.name,original.parent.name);original.rotation.y=batched.rotation.y=.65;original.position.z=batched.position.z=1.7;}
 assert.deepEqual(vertices(result),vertices(scene));
 const carried=result.getObjectByName('CarriedUnit_0');assert.ok(carried.children.length);carried.visible=false;
 const labels=result.getObjectByName('ArmorNumber');assert.ok(labels.children.every(child=>child.isMesh));
});

test('transparent, reflected, hidden and incompatible geometry are not folded into an opaque batch',()=>{
 const scene=group('Robot'),chassis=group('Chassis',scene);box(chassis);box(chassis,1);
 box(chassis,2,new THREE.MeshStandardMaterial({transparent:true,opacity:.5}));
 const reflected=box(chassis,3);reflected.scale.x=-1;
 const hidden=group('Battery',chassis);hidden.visible=false;box(hidden);box(hidden,1);
 const different=box(chassis,4);different.geometry.deleteAttribute('uv');
 const result=batchRigidMeshes(scene);
 assert.equal(counts(result).meshes,5);assert.equal(result.getObjectByName('Battery').visible,false);
 assert.deepEqual(vertices(result),vertices(scene));assert.equal(counts(result).triangles,counts(scene).triangles);
});

test('shipped robots keep all triangles, bounds and articulated groups while reducing mesh count',async()=>{
 for(const name of ['robot-2711-spec2027','robot-2731-spec2027','robot-2732-spec2027','robot-2771-spec2027','robot-305-spec2026v4','robot-2-spec2026v4','drone-2761-spec2027']){
  const file=path.join(__dirname,'../frontend/public/assets',name+'.glb');if(!fs.existsSync(file))throw new Error('Missing fixture: '+file);
  const bytes=fs.readFileSync(file),{scene}=await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),'');
  const result=batchRigidMeshes(scene),before=counts(scene),after=counts(result);
  assert.equal(after.triangles,before.triangles,name);assert.ok(after.meshes<=before.meshes,name);
  if(name.startsWith('robot-'))assert.ok(after.meshes<before.meshes,name);
  const original=new THREE.Box3().setFromObject(scene,true),batched=new THREE.Box3().setFromObject(result,true);
  assert.ok(original.min.distanceTo(batched.min)<1e-5&&original.max.distanceTo(batched.max)<1e-5,name);
  scene.traverse(node=>{if(!node.isMesh)assert.ok(result.getObjectByName(node.name),'Missing joint: '+node.name);});
  console.log(`${name}: ${before.meshes} -> ${after.meshes} meshes; ${after.triangles} triangles retained`);
 }
});
