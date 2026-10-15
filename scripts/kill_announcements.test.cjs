const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
const source=fs.readFileSync(path.join(__dirname,'../frontend/src/killAnnouncements.ts'),'utf8');
const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const scope={exports:{},Map,Set};vm.runInNewContext(code,scope);const {KillAnnouncer,KILL_CUES}=scope.exports;
const robot=(id,role='infantry')=>({id,slot:Number(id.split('-')[1]),team:id.split('-')[0],role,alive:true,kills:0});
const initial=(count=5)=>({tick:0,time:0,dt:.05,robots:[robot('red-1'),...Array.from({length:count},(_,i)=>robot(`blue-${i+1}`)),robot('blue-6','aerial')],events:[]});
function kill(frame,victim,at,killer='red-1'){
 frame=structuredClone(frame);frame.time=at;frame.tick=Math.round(at/ frame.dt);frame.robots.find(r=>r.id===victim).alive=false;
 const attacker=frame.robots.find(r=>r.id===killer);if(attacker)attacker.kills++;
 frame.events=[{id:`kill-${victim}-${at}`,type:'destroy',tick:frame.tick,time:at,robot:victim,killer}];return frame;
}
const cues=list=>Array.from(list,a=>a.cue);

test('all six announcer files are shipped with distinct public URLs',()=>{
 assert.equal(Object.keys(KILL_CUES).length,6);assert.equal(new Set(Object.values(KILL_CUES).map(c=>c.url)).size,6);
 for(const cue of Object.values(KILL_CUES))assert.ok(fs.existsSync(path.join(__dirname,'../frontend/public',cue.url)));
});
test('one robot earns first blood through penta; wipe ignores the indestructible aerial',()=>{
 const a=new KillAnnouncer();let f=initial();a.advance(f,[]);
 for(let i=1;i<=5;i++){
  f=kill(f,`blue-${i}`,i);assert.deepEqual(cues(a.advance(f,f.events)),i===1?['first-blood']:i===5?['penta-kill','aced']:[['double-kill','triple-kill','quadra-kill'][i-2]]);
  assert.deepEqual(cues(a.advance(f,f.events)),[]);
 }
 assert.equal(f.robots.find(r=>r.role==='aerial').alive,true);
});
test('streaks belong to one killer and use event time rather than the latest replay frame time',()=>{
 const a=new KillAnnouncer();let f=initial();f.robots.push(robot('red-2'));a.advance(f,[]);
 f=kill(f,'blue-1',1);a.advance(f,f.events);f=kill(f,'blue-2',2,'red-2');assert.deepEqual(cues(a.advance(f,f.events)),[]);
 f=kill(f,'blue-3',10.9);f.time=99;assert.deepEqual(cues(a.advance(f,f.events)),['double-kill']);
 f=kill(f,'blue-4',21);assert.deepEqual(cues(a.advance(f,f.events)),[]);
});
test('death and respawn reset a killer streak; another wipe needs enemies to revive',()=>{
 const a=new KillAnnouncer();let f=initial(2);a.advance(f,[]);f=kill(f,'blue-1',1);a.advance(f,f.events);
 f=kill(f,'red-1',2,'blue-2');a.advance(f,f.events);f.robots[0].alive=true;
 f.events=[{id:'revive-red',type:'respawn',tick:60,time:3,robot:'red-1'}];a.advance(f,f.events);
 f=kill(f,'blue-2',4);assert.deepEqual(cues(a.advance(f,f.events)),['aced']);
 f.robots.find(r=>r.id==='blue-1').alive=true;f.events=[{id:'revive-blue',type:'respawn',tick:100,time:5,robot:'blue-1'}];a.advance(f,f.events);
 f=kill(f,'blue-1',6);assert.deepEqual(cues(a.advance(f,f.events)),['double-kill','aced']);
});
test('environment, friendly fire and unknown killers do not become first blood or multi-kills',()=>{
 for(const killer of [undefined,'outpost','blue-2']){
  const a=new KillAnnouncer();let f=initial();a.advance(f,[]);f=kill(f,'blue-1',1,killer);f.events[0].killer=killer;
  assert.deepEqual(cues(a.advance(f,f.events)),[]);
  f=kill(f,'blue-2',2);assert.deepEqual(cues(a.advance(f,f.events)),['first-blood']);
 }
});
test('seek rebuilds first blood and the active chain silently, then resumes at the next kill',()=>{
 let f=initial();const history=[f];f=kill(f,'blue-1',1);history.push(f);f=kill(f,'blue-2',2);history.push(f);
 const a=new KillAnnouncer();a.restore(history);f=kill(f,'blue-3',3);assert.deepEqual(cues(a.advance(f,f.events)),['triple-kill']);
 a.restore([history[0]]);f=kill(history[0],'blue-1',1);assert.deepEqual(cues(a.advance(f,f.events)),['first-blood']);
});
test('batched kills preserve kill order and produce exactly one ace after the last ground death',()=>{
 let f=initial();const events=[];for(let i=1;i<=5;i++){f=kill(f,`blue-${i}`,i);events.push(...f.events);}
 const a=new KillAnnouncer();assert.deepEqual(cues(a.advance(f,events)),['first-blood','double-kill','triple-kill','quadra-kill','penta-kill','aced']);
});
test('joining an existing match does not mislabel its next destruction as first blood',()=>{
 let f=initial();f.robots[0].kills=5;const a=new KillAnnouncer();a.advance(f,[]);f=kill(f,'blue-1',100);assert.deepEqual(cues(a.advance(f,f.events)),[]);
});
test('a structure or environmental final blow can wipe a team without earning player kill credit',()=>{
 const a=new KillAnnouncer();let f=initial(1);a.advance(f,[]);f=kill(f,'blue-1',1,'outpost');
 assert.deepEqual(cues(a.advance(f,f.events)),['aced']);
});
