const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
// `aiming.ts` deliberately has no React or three imports, so it loads in a bare VM with the same
// transpile trick the rigid-mesh test uses.
function load(){
  const context={exports:{},require:name=>{
    if(name==='./terrain')return terrain;
    throw new Error('unexpected require '+name);
  }};
  const terrainSrc=fs.readFileSync(path.join(__dirname,'../frontend/src/terrain.ts'),'utf8');
  const terrainCtx={exports:{},require:()=>({})};
  vm.runInNewContext(ts.transpileModule(terrainSrc,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,terrainCtx);
  const terrain=terrainCtx.exports;
  const src=fs.readFileSync(path.join(__dirname,'../frontend/src/aiming.ts'),'utf8');
  vm.runInNewContext(ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,context);
  return context.exports;
}
const aiming=load();

// A flat 28 × 15 m field with no terrain relief unless a test adds it.
const arena=(obstacles=[],terrain=[])=>({width:28,height:15,obstacles,terrain,zones:[],name:'test',asset:''});
const box=(x,y,w,h,height=1.2,bottom=0)=>({x,y,w,h,height,bottom,kind:'barrier'});
// A chassis on the field, facing +x, with the fields the assist reads.
const chassis=(over)=>({id:'blue-3',slot:3,team:'blue',role:'infantry',x:10,y:7.5,z:0,vx:0,vy:0,vz:0,hp:100,max_hp:100,
  alive:true,quaternion:[0,0,0,1],chassis_size_m:[.5,.5,.5],armor_center_z_m:.3,armor_side_center_z_m:.3,
  muzzle_height_m:.5,aim:0,pitch:0,heading:0,...over});
const shooter=chassis({id:'red-3',slot:3,team:'red',x:2,y:7.5,role:'infantry'});
const frame=(extra={})=>({arena:arena(),bases:{red:{hp:10000,max_hp:10000,x:2,y:2,armor_plates:[]},blue:{hp:10000,max_hp:10000,x:26,y:13,armor_plates:[]}},
  outposts:{},robots:[],teams:{red:{},blue:{}},...extra});

test('a half-hidden plate loses the lock to the clean plate beside it',()=>{
  const near=chassis({id:'blue-3',slot:3,x:7.0,y:6.4});
  const clear=chassis({id:'blue-4',slot:4,x:7.0,y:8.6});
  // A wall that covers the left chassis' near face but leaves the right one in the open.
  const wall=box(4.6,5.0,.6,2.6,1.4);
  const field=frame({arena:arena([wall]),robots:[near,clear]});
  // The reticle sits between the two, so both are valid candidates at almost the same angle.
  const view={yaw:0,pitch:-.02};
  const eye=[2,7.5,(shooter.muzzle_height_m)*1.27];
  assert.equal(aiming.sightBlocked(field.arena,eye,[7.0,6.4,.3]),true,'the wall hides the near chassis');
  assert.equal(aiming.sightBlocked(field.arena,eye,[7.0,8.6,.3]),false,'the far chassis stays visible');
  const pick=aiming.lockTarget(shooter,[near,clear],field.arena,view,field,null);
  assert.ok(pick,'something has to lock');
  assert.equal(pick.id,'blue-4','the exposed plate takes the lock, not the sliver behind the wall');
  assert.ok(pick.exposure>0.9,'the chosen plate is fully exposed');
});

test('a plate dead under the reticle still beats a cleaner one further out',()=>{
  const centre=chassis({id:'blue-3',slot:3,x:7.0,y:7.5});
  const offside=chassis({id:'blue-4',slot:4,x:7.0,y:10.2});
  const wall=box(4.6,9.4,.6,3.0,1.4);
  const field=frame({arena:arena([wall]),robots:[centre,offside]});
  const pick=aiming.lockTarget(shooter,[centre,offside],field.arena,{yaw:0,pitch:0},field,null);
  assert.equal(pick.id,'blue-3','angular distance decides outside the exposure band');
});

test('a lock is kept until the challenger is clearly better',()=>{
  const a=chassis({id:'blue-3',slot:3,x:7.0,y:7.2});
  const b=chassis({id:'blue-4',slot:4,x:7.0,y:7.9});
  const field=frame({arena:arena(),robots:[a,b]});
  const first=aiming.lockTarget(shooter,[a,b],field.arena,{yaw:0,pitch:0},field,null);
  const kept=aiming.lockTarget(shooter,[a,b],field.arena,{yaw:(b.y-7.5)/9,pitch:0},field,first.id);
  assert.equal(kept.id,first.id,'the held plate is not traded away by a small angle change');
});

test('the lobbed shell lands on the barrier under the reticle, not the ground behind it',()=>{
  const wall=box(4,6.0,.6,3.0,1.4);
  const field=frame({arena:arena([wall])});
  // Aim level at the wall's inward face; the old code returned the floor behind it.
  const hit=aiming.lobPoint({...shooter},field,0,0,.0127+1.27);
  assert.ok(hit,'the reticle meets something solid');
  assert.ok(Math.abs(hit[0]-4.0)<.05,`impact x should sit on the wall face, got ${hit[0]}`);
  assert.ok(hit[1]>6.0&&hit[1]<9.0,'the impact stays within the wall footprint');
});

test('a lobbed shell over a wall still drops on the terrain the view meets',()=>{
  const field=frame({arena:arena([box(4,6.0,.6,3.0,.2)])});
  // A shallow lob clears that low kerb and comes down on the floor past it: nothing solid is under
  // the reticle, so the impact point is the ground the sight line finally meets.
  const hit=aiming.lobPoint({...shooter},field,0,-.1,.0127+1.27);
  assert.ok(hit,'a lob over cover still has an impact point');
  assert.ok(hit[0]>5,`it lands past the kerb, got x=${hit[0]}`);
  assert.equal(hit[2],0,'and on the floor');
});

test('an armour plate is preferred over the barrier it stands behind',()=>{
  const plate={center:[10,7.5,.6],normal:[-1,0,.05],width:.28,height:.26};
  const field=frame({arena:arena([]),bases:{red:{hp:1,max_hp:1,x:0,y:0,armor_plates:[]},blue:{hp:9000,max_hp:10000,x:10,y:7.5,armor_plates:[plate]}}});
  const near=box(7.0,6.0,.6,3.0,1.4);
  field.arena.obstacles=[near];
  const blocked=aiming.lobPoint({...shooter},field,0,0,.0127+1.27);
  assert.ok(blocked[0]<8,`the nearer barrier wins, got ${blocked[0]}`);
  field.arena.obstacles=[];
  const through=aiming.lobPoint({...shooter},field,0,0,.0127+1.27);
  assert.ok(Math.abs(through[0]-10)<.05,'with the barrier gone the shell reaches the base plate');
});
