const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
function load(name,deps={}){
 const source=fs.readFileSync(path.join(__dirname,`../frontend/src/${name}.ts`),'utf8');
 const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}});
 const context={exports:{},require:key=>deps[key]};vm.runInNewContext(compiled.outputText,context);return context.exports;
}
const {fortressAlert}=load('fortressAlert',{'./terrain':load('terrain')});
function fixture(defender='blue',hold=14){
 const attacker=defender==='blue'?'red':'blue',id=`${attacker}-4`,zone=`${defender}_fortress`;
 return {status:'running',time:200,dt:.05,arena:{zones:[{id:zone,x:7,y:7,radius:.56}]},
  bases:{[defender]:{hp:5000,armor_open:false}},outposts:{[defender]:{hp:0,ever_destroyed:true}},
  zones:{[zone]:{occupants:[id],contested:false}},robots:[{id,team:attacker,role:'infantry',alive:true,weak:false,red_card:false,
  x:7,y:7,fortress_hold:hold,fortress_last_contact:199.95,last_raw_zones:[zone]}]};
}
test('the last six seconds use individual authoritative hold and attacking team color',()=>{
 for(const defender of ['red','blue']){
  const f=fixture(defender,13.95);assert.equal(fortressAlert(f,defender),null);
  f.robots[0].fortress_hold=14;let a=fortressAlert(f,defender);assert.equal(a.remaining,6);assert.notEqual(a.attacker,defender);
  f.robots[0].fortress_hold=19.5;assert.equal(fortressAlert(f,defender).remaining,.5);
  f.robots[0].fortress_hold=20;assert.equal(fortressAlert(f,defender),null);
 }
});
test('multiple occupants select the closest completion without summing holds; contest does not cancel it',()=>{
 const f=fixture();f.zones.blue_fortress.contested=true;
 f.robots.push({...f.robots[0],id:'red-7',fortress_hold:18});f.zones.blue_fortress.occupants.push('red-7');
 const a=fortressAlert(f,'blue');assert.equal(a.robot,'red-7');assert.equal(a.remaining,2);
 f.robots.forEach(r=>r.fortress_hold=10);assert.equal(fortressAlert(f,'blue'),null);
});
test('leaving or losing eligibility hides a retained occupation immediately',()=>{
 for(const patch of [{last_raw_zones:[]},{alive:false},{weak:true},{red_card:true},{role:'hero'},{role:'engineer'},{role:'aerial'},{team:'blue'},{fortress_last_contact:199}]){
  const f=fixture();Object.assign(f.robots[0],patch);assert.equal(fortressAlert(f,'blue'),null,JSON.stringify(patch));
 }
 const f=fixture();f.zones.blue_fortress.occupants=[];assert.equal(fortressAlert(f,'blue'),null);
});
test('progress without a valid fortress and destroyed outpost never shows a warning',()=>{
 for(const mutate of [f=>f.time=179.95,f=>f.status='finished',f=>f.status='ready',f=>f.bases.blue.hp=0,
  f=>f.bases.blue.armor_open=true,f=>f.outposts.blue.hp=750,f=>f.outposts.blue.ever_destroyed=false,
  f=>delete f.outposts,f=>f.arena.zones=[],f=>delete f.robots[0].fortress_hold,f=>f.robots[0].fortress_hold=NaN,
  f=>delete f.robots[0].fortress_last_contact,f=>delete f.zones.blue_fortress.occupants]){
  const f=fixture();mutate(f);assert.equal(fortressAlert(f,'blue'),null);
 }
});
test('pause and backward replay seek read snapshot time and progress; older frames use geometry',()=>{
 const f=fixture();for(let i=0;i<20;i++)assert.equal(fortressAlert(f,'blue').remaining,6);
 f.robots[0].fortress_hold=17;assert.equal(fortressAlert(f,'blue').remaining,3);
 f.robots[0].fortress_hold=14;assert.equal(fortressAlert(f,'blue').remaining,6);
 delete f.robots[0].last_raw_zones;assert.equal(fortressAlert(f,'blue').remaining,6);
 f.arena.zones[0].polygon=[[6.4,6.4],[7.6,6.4],[7.6,7.6],[6.4,7.6]];
 f.robots[0].x=7.5;assert.equal(fortressAlert(f,'blue').remaining,6);
 f.robots[0].x=8;assert.equal(fortressAlert(f,'blue'),null);
});
