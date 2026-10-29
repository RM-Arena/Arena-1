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
const {dampFactor,displayRate,displayBudget,liveAlpha,resetPlayhead}=context.exports;

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

// ---- Playhead ------------------------------------------------------------------------------------
// A 20 Hz feed whose packets arrive with the scheduling jitter a browser really has: the socket
// callback, the JSON parse and the React commit each add their own delay, on top of a main thread that
// is also drawing. Arrival times stay monotone, but their spacing wobbles around 50 ms.
const step=.05;
const feedAt=(time,tick,received,generation='live:m1')=>({
  frame:{dt:step,time,tick},previous:{},received,pace:50,speed:1,paused:false,replay:false,
  generation,alpha:1,
});

function runArrivals(jitter, hz=120, packets=40, seed=7){
  resetPlayhead();
  let state=seed;
  const random=()=>{state=(state*1103515245+12345)%2147483648;return state/2147483648;};
  const frameMs=1000/hz;
  // Sample n exists at n*step of engine time and reaches the client at n*50 ms plus jitter.
  const arrivals=[];
  for(let n=0;n<=packets;n++)arrivals.push(Math.max(1,n*50+(random()*2-1)*jitter));
  const rows=[];
  let tick=0;
  for(let time=arrivals[0];time<=arrivals.at(-1);time+=frameMs){
    while(tick+1<arrivals.length&&arrivals[tick+1]<=time)tick++;
    const f=feedAt(tick*step,tick,arrivals[tick]);
    rows.push({tick,time,phase:liveAlpha(f,time)});
  }
  return rows;
}

test('the playhead moves at exactly real time while the packets themselves jitter',()=>{
  const rows=runArrivals(6);
  // Phase advance per frame, in sample steps. 120 Hz drawing against a 50 ms step is 1/6 step a frame.
  const nominal=1/6;
  const speeds=[];
  for(let i=1;i<rows.length;i++){
    // A packet boundary moves the phase back by one step; adding it back leaves the real motion.
    const boundary=rows[i].tick!==rows[i-1].tick?1:0;
    speeds.push((rows[i].phase-rows[i-1].phase+boundary)/nominal);
  }
  const body=speeds.slice(10);
  const spread=Math.max(...body)-Math.min(...body);
  // 40 packets of ?6 ms jitter used to move the picture ?25 % faster and slower; the band keeps it at 1.
  assert.ok(spread<0.07,`playhead speed spread ${spread.toFixed(3)}x`);
});

test('the playhead never rewinds and stays within one step of the newest sample',()=>{
  const rows=runArrivals(8);
  let rewinds=0,worstLag=0;
  for(let i=1;i<rows.length;i++){
    const boundary=rows[i].tick!==rows[i-1].tick?1:0;
    if(rows[i].phase-rows[i-1].phase+boundary<0)rewinds++;
    worstLag=Math.max(worstLag,1-rows[i].phase);
  }
  assert.equal(rewinds,0,'the drawn phase ran backwards');
  assert.ok(worstLag>-0.4&&worstLag<1.0,`drew ${worstLag.toFixed(2)} steps behind the newest sample`);
});

test('a long packet gap is covered by the extrapolated tail instead of a freeze',()=>{
  resetPlayhead();
  // One packet, then 120 ms of silence: two and a half steps with nothing new to interpolate.
  const feed=feedAt(0,0,10);
  liveAlpha(feed,10);
  let phase=0;
  for(let t=10;t<=130;t+=8.33)phase=liveAlpha(feed,t);
  assert.ok(phase>1.1,`parked at ${phase.toFixed(2)} while the packet was late`);
  assert.ok(phase<=1.6,`ran away to ${phase.toFixed(2)}`);
});

test('a paused feed parks the playhead and a new match reseeds it',()=>{
  resetPlayhead();
  const paused={...feedAt(0,0,10),paused:true};
  liveAlpha(paused,10);
  // Resuming seeds at the current sample instead of replaying the gap.
  const resumed=feedAt(5*step,5,900);
  const alpha=liveAlpha(resumed,900);
  assert.ok(alpha>0&&alpha<1,`resumed at ${alpha.toFixed(2)}`);
  // A different match is a different timeline: the playhead must not carry the old phase over.
  const other=feedAt(0,0,1000,'live:m2');
  const first=liveAlpha(other,1000);
  assert.ok(first>=0&&first<1,`new match started at ${first.toFixed(2)}`);
});
