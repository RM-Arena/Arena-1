const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
const source=fs.readFileSync(path.join(__dirname,'../frontend/src/world.ts'),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}});
// `world.ts` only needs a vector for its screen-space helpers; the camera easing is pure maths.
class Vector3{set(x,y,z){this.x=x;this.y=y;this.z=z;return this;}copy(v){return this.set(v.x,v.y,v.z);}clone(){const v=new Vector3();return v.copy(this);}}
const context={exports:{},require:(id)=>{
  if(id==='three')return {Vector3};
  if(id==='./types')return {};
  throw new Error(`unexpected import ${id}`);
}};
vm.runInNewContext(compiled.outputText,context);
const {dampFactor,displayRate,displayBudget}=context.exports;

const apply=(rate,dt,steps,from=0,to=1)=>{
  let value=from;
  for(let i=0;i<steps;i++)value+=(to-value)*dampFactor(rate,dt);
  return value;
};

test('the same wall-clock time closes the same gap at any frame rate',()=>{
  for(const hz of [60,90,120,144,240]){
    const value=apply(6,1/hz,hz);
    // One second at any refresh leaves the camera within a hair of the target.
    assert.ok(Math.abs(value-1+Math.exp(-6))<1e-9,`${hz} Hz reached ${value}`);
  }
});

test('two half steps equal one full step',()=>{
  for(const rate of [3,6,9,14,30,33]){
    const full=apply(rate,1/60,1),halves=apply(rate,1/120,2);
    assert.ok(Math.abs(full-halves)<1e-12,`rate ${rate}: ${full} vs ${halves}`);
  }
});

test('a 120 Hz panel gets an 8.3 ms budget and a 60 Hz panel keeps 16.7 ms',()=>{
  assert.equal(displayRate(60),60);
  assert.equal(displayRate(59.4),60);
  assert.equal(displayRate(119.4),120);
  assert.equal(displayRate(143),144);
  assert.equal(displayRate(164),165);
  assert.ok(Math.abs(displayBudget(120)*1000-8.33)<.01);
  assert.ok(Math.abs(displayBudget(60)*1000-16.67)<.01);
});

test('a noisy refresh measurement snaps to a real panel rate, never a faster one',()=>{
  // A 60 Hz panel with stray fast frames averages ~78 Hz: it must snap to 75 Hz, not to 90+, so the
  // budget cannot be shrunk below what the display can actually present.
  assert.equal(displayRate(78),75);
  assert.equal(displayRate(62),60);
  assert.equal(displayRate(119.4),120);
  assert.equal(displayRate(100),100);
});

test('a dropped frame does not overshoot the target',()=>{
  // A 50 ms hitch must still land short of the target, never past it: the follow is a decay, not a spring.
  for(const rate of [3,9,33]){
    const value=apply(rate,.05,1);
    assert.ok(value>0&&value<1,`rate ${rate} overshot to ${value}`);
    assert.ok(value>apply(rate,1/60,1),`rate ${rate} a hitch must move further than a normal frame`);
  }
});
