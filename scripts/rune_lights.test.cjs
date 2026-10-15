const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
const source=fs.readFileSync(path.join(__dirname,'../frontend/src/runeLights.ts'),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}});
const context={exports:{}};vm.runInNewContext(compiled.outputText,context);
const {runeArmLight,runeActive}=context.exports;

test('a valid hit stays gold while the next target is selected',()=>{
  const state={status:'activating',lit:[1],activated_arms:[0],targets:[{arm:0,hit:true,last_hit_at:2,last_hit_valid:true}]};
  assert.equal(runeArmLight(state,0,2),'hit');
  assert.equal(runeArmLight(state,0,4),'hit');
  assert.equal(runeArmLight(state,1,4),'target');
  assert.equal(runeArmLight(state,2,4),'off');
});
test('impact flash expires on match time and cannot leak backwards when seeking',()=>{
  const state={status:'activating',lit:[1],activated_arms:[],targets:[{arm:0,last_hit_at:2,last_hit_valid:false}]};
  assert.equal(runeArmLight(state,0,1.9),'off');
  assert.equal(runeArmLight(state,0,2.2),'impact');
  assert.equal(runeArmLight(state,0,2.36),'off');
  assert.equal(runeArmLight(state,1,2.36),'target');
});
test('all five arms stay lit for the entire buff, even if struck again',()=>{
  const state={status:'active',active_until:49,activated_arms:[0,1,2,3,4],targets:[{arm:0,last_hit_at:10,last_hit_valid:false}]};
  for(const time of [4,10,10.2,30,48.999]){
    assert.equal(runeActive(state,time),true);
    for(let arm=0;arm<5;arm++)assert.equal(runeArmLight(state,arm,time),'active');
  }
  for(let arm=0;arm<5;arm++)assert.equal(runeArmLight(state,arm,49),'off');
});
test('expired or failed activation clears old hit records in historical replays',()=>{
  for(const status of ['idle','failed']){
    const state={status,lit:[1],activated_arms:[0,1,2,3,4],targets:[{arm:0,hit:true}]};
    for(let arm=0;arm<5;arm++)assert.equal(runeArmLight(state,arm,50),'off');
  }
});
test('red and blue faces retain independent activation state',()=>{
  const red={status:'active',active_until:45};
  const blue={status:'activating',lit:[2],activated_arms:[1]};
  assert.equal(runeArmLight(red,2,20),'active');
  assert.equal(runeArmLight(blue,2,20),'target');
  assert.equal(runeArmLight(blue,1,20),'hit');
  assert.equal(runeArmLight(blue,0,20),'off');
});
test('a previously hit large-rune arm can become a pending target again',()=>{
  const state={status:'activating',lit:[0,2],activated_arms:[0],targets:[{arm:0,hit:true,last_hit_at:2,last_hit_valid:true}]};
  assert.equal(runeArmLight(state,0,2.1),'hit');
  assert.equal(runeArmLight(state,0,3),'target');
});
