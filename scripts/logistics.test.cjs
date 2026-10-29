const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
const frameSeason=f=>f?.season==='2027'||f?.arena?.name==='rmuc2027'?'2027':'2026';
const code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../frontend/src/logistics.ts'),'utf8'),
  {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const scope={exports:{},require:name=>name==='./types'?{frameSeason}:require(name)};
vm.runInNewContext(code,scope);
const {logisticsOf,fpvResolutionScale,LOGISTICS_DIVISOR_HP}=scope.exports;
const frame=(hp,patch={})=>({season:'2027',arena:{name:'rmuc2027'},bases:{red:{hp,max_hp:10000},blue:{hp:10000,max_hp:10000}},...patch});

test('λ falls one percent for every 200 hp the own base loses',()=>{
  assert.equal(logisticsOf(frame(10000),'red'),1);
  assert.equal(logisticsOf(frame(6000),'red'),.8);
  assert.equal(logisticsOf(frame(0),'red'),.5);
  assert.equal(logisticsOf(frame(10000),'red'),1,'the enemy base does not degrade this team');
  assert.equal(LOGISTICS_DIVISOR_HP,20000);
});

test('the divisor comes from the published season rules and falls back when absent',()=>{
  assert.equal(logisticsOf(frame(5000,{rulebook_rules:{logistics:{base_loss_divisor_hp:10000}}}),'red'),.5);
  assert.equal(logisticsOf(frame(5000,{rulebook_rules:{logistics:{}}}),'red'),.75);
  assert.equal(logisticsOf(frame(5000),'red'),.75);
});

test('2026 and incomplete snapshots keep the full first-person picture',()=>{
  assert.equal(logisticsOf({season:'2026',arena:{name:'rmuc2026'},bases:{red:{hp:0,max_hp:5000}}},'red'),1);
  assert.equal(logisticsOf(null,'red'),1);
  assert.equal(logisticsOf({season:'2027',arena:{name:'rmuc2027'}},'red'),1);
  assert.equal(logisticsOf({season:'2027',arena:{name:'rmuc2027'},bases:{red:{hp:NaN,max_hp:10000}}},'red'),1);
});

test('the first-person picture scales each side by λ, i.e. λ² pixels',()=>{
  assert.equal(fpvResolutionScale(frame(6000),'red'),.8);
  assert.equal(fpvResolutionScale(frame(10000),'red'),1);
});
