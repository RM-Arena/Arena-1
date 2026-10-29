const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
const source=fs.readFileSync(path.join(__dirname,'../frontend/src/cockpitMotion.ts'),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}});
const context={exports:{},require:(id)=>{
  // The motion model only needs the launcher predicate from the shared types module.
  if(id==='./types')return {is42:role=>role==='hero'||role==='heavy'};
  throw new Error(`unexpected import ${id}`);
}};
vm.runInNewContext(compiled.outputText,context);
const {createShakeState,shakeOf,SHAKE_LIMITS,createEyeLift,eyeLiftStep,createEyeMount,eyeMountStep}=context.exports;

// A minimal cockpit body: `shakeOf` reads exactly these fields off the engine frame.
const body=(over={})=>({id:'red-1',slot:1,role:'infantry',alive:true,grounded:true,vx:0,vy:0,vz:0,
  motor_power_w:0,power_limit:100,last_shot_time:0,last_damage_time:0,...over});

function run(state,robot,seconds,hz,onFrame){
  const dt=1/hz,peak={y:0,roll:0,pitch:0};
  let elapsed=0;
  for(let i=0;i<Math.round(seconds*hz);i++){
    const out=shakeOf(state,robot,dt);elapsed+=dt;
    for(const axis of ['y','roll','pitch'])peak[axis]=Math.max(peak[axis],Math.abs(out[axis]));
    if(onFrame)onFrame(out,elapsed,i);
  }
  return {peak,out:shakeOf(state,robot,0)};
}

test('a parked chassis does not shake the lens',()=>{
  const state=createShakeState(),robot=body({motor_power_w:0});
  const {peak}=run(state,robot,2,60);
  // Idle current still flows through the motors; it must not reach the camera while nothing moves.
  assert.ok(peak.y<3e-4,`idle heave ${peak.y}`);
  assert.ok(peak.roll<1e-4,`idle roll ${peak.roll}`);
  assert.ok(peak.pitch<1e-4,`idle pitch ${peak.pitch}`);
});

test('tread rumble while rolling stays inside the published caps',()=>{
  const state=createShakeState(),robot=body({vx:3.2,motor_power_w:100});
  const {peak}=run(state,robot,3,120);
  assert.ok(peak.y>5e-4,'a rolling chassis should have some rumble');
  assert.ok(peak.y<=SHAKE_LIMITS.y+1e-6,`heave ${peak.y}`);
  assert.ok(peak.roll<=SHAKE_LIMITS.roll+1e-6,`roll ${peak.roll}`);
  assert.ok(peak.pitch<=SHAKE_LIMITS.pitch+1e-6,`pitch ${peak.pitch}`);
});

test('a landing is a small heave that settles in about a tenth of a second',()=>{
  const state=createShakeState();
  // Two settled frames, then the vertical speed drops from 1.2 m/s to zero: a dropped step.
  const ground=body({vz:0}),falling=body({vz:1.2});
  shakeOf(state,ground,1/60);shakeOf(state,ground,1/60);
  let landed=shakeOf(state,falling,1/60);
  const peak=landed.y;
  assert.ok(peak<0,`the landing must dip: ${peak}`);
  assert.ok(Math.abs(peak)<=0.0065,`landing heave ${peak}`);
  // 120 ms later the lens is back under 20 % of the landing dip.
  let last=landed;
  for(let i=0;i<7;i++)last=shakeOf(state,ground,1/60);
  assert.ok(Math.abs(last.y)<Math.abs(peak)*.25,`still ${last.y} after 120 ms`);
});

test('60 Hz and 120 Hz renderings of the same landing agree',()=>{
  const at=(hz)=>{
    const state=createShakeState(),ground=body(),falling=body({vz:1.2});
    shakeOf(state,ground,1/hz);shakeOf(state,ground,1/hz);
    shakeOf(state,falling,1/hz);
    const sample={};
    for(let i=0;i<Math.round(.2*hz);i++){
      const out=shakeOf(state,ground,1/hz),t=(i+1)/hz;
      if(Math.abs(t-.05)<1/hz/2)sample.short=out.y;
      if(Math.abs(t-.15)<1/hz/2)sample.long=out.y;
    }
    return sample;
  };
  const a=at(60),b=at(120);
  assert.ok(Math.abs(a.short-b.short)<2.5e-4,`50 ms: ${a.short} vs ${b.short}`);
  assert.ok(Math.abs(a.long-b.long)<6e-5,`150 ms: ${a.long} vs ${b.long}`);
});

test('a dropped frame does not make the spring ring',()=>{
  const state=createShakeState(),ground=body(),falling=body({vz:1.2});
  shakeOf(state,ground,1/60);shakeOf(state,falling,.05);
  let previous=Math.abs(shakeOf(state,ground,.05).y),grew=false;
  for(let i=0;i<12;i++){
    const magnitude=Math.abs(shakeOf(state,ground,.05).y);
    if(magnitude>previous*1.001)grew=true;
    previous=magnitude;
  }
  assert.ok(!grew,'the heave grew after the impulse under 20 Hz frames');
  assert.ok(previous<1e-4,`not settled: ${previous}`);
});

test('a 42 mm shot kicks the barrel harder than a 17 mm shot but stays under the cap',()=>{
  const peak=(role)=>{
    const state=createShakeState(),idle=body({role});
    shakeOf(state,idle,1/60);
    const fired=body({role,last_shot_time:1});
    let highest=0;
    for(let i=0;i<24;i++)highest=Math.max(highest,Math.abs(shakeOf(state,fired,1/60).pitch));
    return highest;
  };
  const small=peak('infantry'),large=peak('heavy');
  assert.ok(large<=SHAKE_LIMITS.pitch+1e-6,`heavy pitch ${large}`);
  assert.ok(small<large,`17 mm ${small} should be softer than 42 mm ${large}`);
  // The model gives the 42 mm slightly more than twice the impulse; the spring response keeps the ratio.
  assert.ok(large/small>1.7,`kick ratio ${large/small}`);
});

// ---- Eye height --------------------------------------------------------------------------------
const lift=()=>createEyeLift();

test('the eye-height spring turns the washboard road into one soft heave',()=>{
  // The field's own road humps are 70 mm every 240 mm: at 2 m/s that is 8 Hz of body bob, and the hull
  // really does ride it. 15 mm of it is measured on the engine, so the lens must cut that band hard.
  const state=lift(),hz=120,dt=1/hz;
  let low=Infinity,high=-Infinity;
  for(let i=0;i<hz*2;i++){
    const t=i*dt,y=eyeLiftStep(state,0.19+0.0075*Math.sin(2*Math.PI*8*t),dt);
    if(t>1){low=Math.min(low,y);high=Math.max(high,y);}
  }
  // 15 mm peak-to-peak in, under 2.5 mm out: the remaining bob is the eye easing after the hull, not
  // a copy of the road. Without the spring this is 15 mm, which is what the pilot called "????".
  assert.ok(high-low<0.0025,`ripple left ${((high-low)*1000).toFixed(3)} mm of 15 mm peak-to-peak`);
});

test('the eye reaches a 0.2 m step in about a third of a second and never overshoots',()=>{
  const state=lift(),dt=1/120;
  eyeLiftStep(state,0,dt);
  let reached=null,highest=0;
  for(let i=1;i<=120;i++){
    const y=eyeLiftStep(state,0.2,dt);
    highest=Math.max(highest,y);
    if(reached===null&&y>=0.19)reached=i*dt;
  }
  assert.ok(reached!==null&&reached<0.35,`90 % after ${reached}`);
  assert.ok(highest<=0.201,`overshoot to ${highest.toFixed(4)} m`);
});

test('60, 120 and 240 Hz panels ride the same height',()=>{
  const at=(hz)=>{
    const state=lift(),dt=1/hz;let y=0;
    for(let i=0;i<Math.round(0.25*hz);i++)y=eyeLiftStep(state,i<hz/10?0.1:0.16,dt);
    return y;
  };
  const a=at(60),b=at(120),c=at(240);
  assert.ok(Math.abs(a-b)<0.001,`60 vs 120: ${a} vs ${b}`);
  assert.ok(Math.abs(b-c)<0.001,`120 vs 240: ${b} vs ${c}`);
});

test('a steady climb is tracked without lag, and the dead-band does not stall it',()=>{
  // A 0.3 m/s climb is a ramp input: the spring alone would trail it by 2V/?, which on a 23? slope is
  // the eye sinking into the deck. The slow vertical velocity is fed forward to cancel exactly that.
  const mount=createEyeMount(),dt=1/120,slope=0.3;
  eyeMountStep(mount,'red-1',0,0,dt);
  let worst=0,tail=0;
  for(let i=1;i<=240;i++){
    const height=slope*(i*dt);
    const y=eyeMountStep(mount,'red-1',height,slope,dt);
    if(i>120)worst=Math.max(worst,Math.abs(height-y));
    if(i>210)tail=Math.max(tail,Math.abs(height-y));
  }
  // A stalled dead-band would put the eye 30 mm behind and let it grow; the feed-forward keeps the
  // settled error at a few millimetres, which on a 23 degree slope is an invisible constant.
  assert.ok(tail<0.005,`settled ${(tail*1000).toFixed(1)} mm behind on a ${slope} m/s climb`);
  assert.ok(worst<0.01,`trailed ${(worst*1000).toFixed(1)} mm on a ${slope} m/s climb`);
});
