const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
const source=fs.readFileSync(path.join(__dirname,'../frontend/src/mechanismProgress.ts'),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}});
const context={exports:{}};vm.runInNewContext(compiled.outputText,context);
const {mechanismProgress}=context.exports;

test('a rebuilding outpost shows the authoritative ratio and the builder duration',()=>{
  const frame={outposts:{red:{hp:0,rebuild:{robot:'red-2',elapsed:2,required:5,progress:.4}}}};
  const display=mechanismProgress(frame,'red','outpost');
  assert.equal(display.progress,.4);
  assert.match(display.detail,/2号.*2\.0 \/ 5\.0/);
  frame.outposts.red.hp=750;
  assert.equal(mechanismProgress(frame,'red','outpost'),null);
});
test('absent builders and old replay fields hide progress without crashing',()=>{
  for(const outposts of [undefined,{}, {red:{hp:0}}, {red:{hp:0,rebuild:null}}]){
    assert.equal(mechanismProgress({outposts},'red','outpost'),null);
  }
  assert.equal(mechanismProgress({},'blue','assembly'),null);
});
test('the second level-four unit displays half total progress and a distinct phase',()=>{
  const display=mechanismProgress({assemblies:{blue:{stage:'inserting',difficulty:4,inserted_units:1,operation:'rotating',operation_progress:.6,progress:.8}}},'blue','assembly');
  assert.match(display.label,/4级兑矿.*旋转/);
  assert.match(display.detail,/2\/2.*60%/);
  assert.equal(display.progress,.8);
});
test('pause and replay seek use frame progress without a local countdown',()=>{
  const snapshot=(elapsed)=>({outposts:{red:{hp:0,rebuild:{robot:'red-7',elapsed,required:10,progress:elapsed/10}}}});
  const paused=snapshot(6);
  for(let i=0;i<20;i++)assert.equal(mechanismProgress(paused,'red','outpost').progress,.6);
  assert.equal(mechanismProgress(snapshot(2),'red','outpost').progress,.2);
});
test('completed, failed and idle exchanges do not retain a running bar',()=>{
  for(const stage of ['idle','complete','failed'])assert.equal(mechanismProgress({assemblies:{red:{stage,difficulty:1,progress:1}}},'red','assembly'),null);
});

test('graded assembly shows its physical precision without breaking older replays',()=>{
 const frame={time:200,assemblies:{red:{stage:'inserting',difficulty:4,operation:'verifying',progress:.5,requirements:{name:'极限',tip_tolerance_m:.004,tool_tolerance_deg:.75},blocked_reason:'arm_misaligned'}}};
 const value=mechanismProgress(frame,'red','assembly');assert.match(value.detail,/极限 \/ 4 mm \/ 0.75°/);assert.match(value.detail,/请对准核心姿态/);
 delete frame.assemblies.red.requirements;const old=mechanismProgress(frame,'red','assembly');assert.ok(!old.detail.includes('undefined'));assert.match(old.detail,/第 1\/2 单元/);
});
