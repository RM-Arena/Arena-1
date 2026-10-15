const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
function compile(name,imports={},extras={}){
 const source=fs.readFileSync(path.join(__dirname,'../frontend/src/'+name+'.ts'),'utf8');
 const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 const scope={exports:{},require:n=>{if(!(n in imports))throw new Error('Unexpected import '+n);return imports[n];},Float32Array,Map,Set,Math,Promise,Error,window:{setTimeout:()=>0},...extras};vm.runInNewContext(code,scope);return scope.exports;
}
const identity=compile('strategyIdentity'),playlist=compile('audioPlaylist'),killAnnouncements=compile('killAnnouncements'),{MUSIC,broadcastMusicCue,audibleEvents}=playlist;
class Param{value=0;setValueAtTime(v){this.value=v;}setTargetAtTime(v){this.value=v;}exponentialRampToValueAtTime(v){this.value=v;}cancelScheduledValues(){}}
class Node{gain=new Param();frequency=new Param();Q=new Param();playbackRate=new Param();connections=[];connect(node){this.connections.push(node);return node;}disconnect(){}start(at,offset=0){this.started={at,offset};}stop(at){this.stopped=at;}}
class Context{
 currentTime=0;state='suspended';sampleRate=1000;destination=new Node();sources=[];
 createPanner(){const n=new Node();for(const p of ['positionX','positionY','positionZ'])n[p]=new Param();return n;}createGain(){return new Node();}createMediaStreamDestination(){return new Node();}createConvolver(){return new Node();}
 createDynamicsCompressor(){const n=new Node();for(const p of ['threshold','knee','ratio','attack','release'])n[p]=new Param();return n;}
 createBuffer(channels,length,rate){return {duration:length/rate,getChannelData:()=>new Float32Array(length)};}
 createBufferSource(){const n=new Node();this.sources.push(n);return n;}createOscillator(){return new Node();}createWaveShaper(){return new Node();}createBiquadFilter(){return new Node();}
 decodeAudioData(data){return Promise.resolve({duration:data.url.includes('/announcer/')?3:data.url.includes('countdown')?5:data.url.includes('summoning')?113.92:32,url:data.url});}
 resume(){this.state='running';return Promise.resolve();}suspend(){this.state='suspended';return Promise.resolve();}close(){this.state='closed';return Promise.resolve();}
 advance(seconds){if(this.state==='running')this.currentTime+=seconds;}
}
function harness(fetcher=async url=>({ok:true,arrayBuffer:async()=>({url})})){
 const {ArenaAudio}=compile('media',{'./audioPlaylist':playlist,'./killAnnouncements':killAnnouncements,'./strategyIdentity':identity},{AudioContext:Context,fetch:fetcher});return new ArenaAudio();
}
async function flush(){for(let i=0;i<12;i++)await Promise.resolve();}
test('recorded video headings use display names and the actual season and roster',()=>{
 const labels=[],ctx={fillRect(){},drawImage(){},fillText(text){labels.push(text);}};
 const {BroadcastRecorder}=compile('media',{'./audioPlaylist':playlist,'./killAnnouncements':killAnnouncements,'./strategyIdentity':identity},{document:{createElement:()=>({getContext:()=>ctx})}});
 const recorder=new BroadcastRecorder({});recorder.source={width:1920,height:1080};recorder.recorder={state:'recording'};
 const robots=['red','blue'].flatMap(team=>[1,3,4,6,7].map(slot=>({team,slot,role:'infantry',alive:true,hp:100,max_hp:100,heat:0,max_heat:40})));
 const frame={season:'2027',remaining:420,seed:42,status:'running',arena:{name:'rmuc2027'},robots,teams:{red:{score:0},blue:{score:0}},bases:{red:{hp:10000,max_hp:10000},blue:{hp:10000,max_hp:10000}}};
 recorder.draw(frame,{teams:{red:{name:'official_2027_team',display_name:'官方基线 2027'},blue:{name:'official_2027_hold'}}});
 assert.ok(labels.some(t=>t.includes('基线策略 2027')));
 assert.ok(labels.some(t=>t.includes('5v5 / RMUC 2027')));
 assert.doesNotMatch(labels.join('\n'),/official|官方|6v6|RMUC 2026/i);
});
const state={page:'arena',hangar:false,prematch:null,post:null,status:'ready'};

test('all stage cues use shipped assets and reserve the competition track for the match',()=>{
 assert.equal(new Set(Object.values(MUSIC).map(t=>t.url)).size,9);
 for(const cue of Object.keys(MUSIC)){assert.ok(fs.existsSync(path.join(__dirname,'../frontend/public',MUSIC[cue].url)));if(cue!=='match')assert.notEqual(MUSIC[cue].url,MUSIC.match.url);}
});
test('menus, hangar, self-check, countdown and each result screen select their own cue',()=>{
 for(const [stage,cue] of [[{page:'home'},'home'],[{page:'history'},'lobby'],[{hangar:true},'hangar'],[{modal:true},'setup'],[{prematch:'self_check'},'self_check'],[{prematch:'countdown'},'countdown'],[{post:'victory'},'victory'],[{post:'results'},'results'],[{post:'mvp'},'mvp'],[{status:'running'},'match']])assert.equal(broadcastMusicCue({...state,...stage}),cue);
 assert.equal(broadcastMusicCue({...state,status:'running',page:'leaderboard'}),'lobby');
 assert.equal(broadcastMusicCue({...state,started:true}),'match');
 assert.equal(broadcastMusicCue({...state,busy:true}),'setup');
 assert.equal(broadcastMusicCue({...state,status:'finished',started:true}),'results');
});
test('the lineup intro plays the setup theme in RM matches and the uploaded track in free battles',()=>{
 assert.equal(MUSIC[broadcastMusicCue({...state,prematch:'self_check'})].url,'/assets/audio/home.mp3');
 assert.equal(broadcastMusicCue({...state,prematch:'self_check',free:true}),'self_check_free');
 assert.equal(MUSIC.self_check_free.url,'/assets/audio/intro-free.m4a');
 assert.equal(broadcastMusicCue({...state,prematch:'countdown',free:true}),'countdown');
});
test('the judged plate hit replaces the generic contact, without hiding other impacts',()=>{
 const hit={type:'hit',tick:12,team:'red',x:2,y:3,z:.4},duplicate={...hit,type:'impact'},wall={...duplicate,x:4},later={...duplicate,tick:13};
 const list=audibleEvents([hit,duplicate,wall,later]);assert.equal(list.length,3);assert.ok(!list.includes(duplicate));assert.ok(list.includes(wall));assert.ok(list.includes(later));
});
test('formal music starts at zero after the countdown, with the full original track loop',async()=>{
 const a=harness();a.bgm('countdown','game-1',5);await a.enable();await flush();a.context.advance(2);a.bgm('match','game-1');await flush();
 assert.equal(a.diagnostics.cue,'match');assert.equal(a.diagnostics.startOffset,0);assert.equal(a.diagnostics.track,MUSIC.match.url);
 const s=a.context.sources.at(-1);assert.equal(s.loopStart,0);assert.equal(s.loopEnd,113.92);assert.equal(s.playbackRate.value,1);
});
test('repeated render updates and playback-speed controls do not restart match music',async()=>{
 const a=harness();a.bgm('match','game-1');await a.enable();await flush();const starts=a.diagnostics.starts;a.context.advance(3);
 for(let i=0;i<20;i++)a.bgm('match','game-1',5,8);
 assert.equal(a.diagnostics.starts,starts);assert.equal(a.diagnostics.position,3);assert.equal(a.context.sources.at(-1).playbackRate.value,1);
});
test('a new match or replay generation restarts at zero even when the cue is still match',async()=>{
 const a=harness();a.bgm('match','game-1');await a.enable();a.context.advance(17);const starts=a.diagnostics.starts;
 a.bgm('match','game-2');assert.equal(a.diagnostics.starts,starts+1);assert.equal(a.diagnostics.position,0);assert.equal(a.diagnostics.startOffset,0);
});
test('pause freezes the soundtrack; resume continues without rewinding',async()=>{
 const a=harness();a.bgm('match','game-1');await a.enable();a.context.advance(2.5);const starts=a.diagnostics.starts;
 a.setPaused(true);a.context.advance(60);assert.equal(a.diagnostics.position,2.5);a.setPaused(false);await flush();a.context.advance(1);
 assert.equal(a.diagnostics.position,3.5);assert.equal(a.diagnostics.starts,starts);
});
test('switching sound off really mutes the master and re-enabling match music starts from the head',async()=>{
 const a=harness();a.bgm('match','game-1');await a.enable();a.context.advance(9);a.disable();assert.equal(a.enabled,false);assert.ok(a.master.gain.value<=.001);assert.equal(a.musicPlaying,false);
 await a.enable();assert.equal(a.diagnostics.startOffset,0);assert.equal(a.diagnostics.position,0);
});
test('each post-match stage changes the actual source buffer',async()=>{
 const a=harness();a.bgm('match','game-1');await a.enable();
 for(const cue of ['victory','results','mvp','results']){a.bgm(cue,'game-1');await flush();assert.equal(a.diagnostics.cue,cue);assert.equal(a.diagnostics.track,MUSIC[cue].url);assert.notEqual(a.diagnostics.track,MUSIC.match.url);}
});
test('home and match setup swap music while match, post-match and archive tracks stay original',async()=>{
 const a=harness();a.bgm(broadcastMusicCue({...state,page:'home',post:'mvp',status:'finished'}),'preview');await a.enable();await flush();
 assert.equal(a.diagnostics.track,'/assets/audio/lobby.m4a');
 a.bgm(broadcastMusicCue(state),'preview');await flush();assert.equal(a.diagnostics.track,'/assets/audio/home.mp3');
 a.bgm(broadcastMusicCue({...state,page:'history'}),'preview');await flush();assert.equal(a.diagnostics.track,'/assets/audio/lobby.m4a');
 for(const [post,url] of [[null,'/assets/audio/summoning-glory.m4a'],['victory','/assets/audio/victory.m4a'],['results','/assets/audio/results.m4a'],['mvp','/assets/audio/mvp.m4a']]){
  a.bgm(broadcastMusicCue({...state,page:'arena',status:'running',post}),'preview');await flush();assert.equal(a.diagnostics.track,url);
 }
});
test('a late asset response cannot replace the requested match with lobby music',async()=>{
 let release;const a=harness(url=>url===MUSIC.lobby.url?new Promise(r=>{release=()=>r({ok:true,arrayBuffer:async()=>({url})});}):Promise.resolve({ok:true,arrayBuffer:async()=>({url})}));
 a.bgm('lobby','game-1');const enabled=a.enable();await flush();a.bgm('match','game-1');await flush();assert.equal(a.diagnostics.cue,'match');release();await enabled;await flush();assert.equal(a.diagnostics.cue,'match');assert.equal(a.diagnostics.startOffset,0);
});
test('paused or hidden playback never queues a stale burst of effects for resume',async()=>{
 const a=harness();a.bgm('match','game-1');await a.enable();a.setPaused(true);const count=a.context.sources.length;
 a.play({type:'hit',damage:200,tick:1});a.countdown(3);assert.equal(a.context.sources.length,count);
});
test('countdown follows a faster referee clock while match playback returns to normal rate',async()=>{
 const a=harness();a.bgm('countdown','game-1',3,2);await a.enable();await flush();assert.equal(a.diagnostics.startOffset,2);assert.equal(a.context.sources.at(-1).playbackRate.value,2);
 a.bgm('match','game-1',0,4);await flush();assert.equal(a.diagnostics.startOffset,0);assert.equal(a.context.sources.at(-1).playbackRate.value,1);
});

test('BGM volume adjusts live without restarting music or changing the effects bus',async()=>{
 const a=harness();a.setBgmVolume(.25);a.bgm('match','game-1');await a.enable();a.context.advance(4);
 const starts=a.diagnostics.starts,effects=a.bus.gain.value;assert.equal(a.music.gain.value,.2);
 a.setBgmVolume(0);assert.equal(a.music.gain.value,0);assert.equal(a.diagnostics.position,4);assert.equal(a.diagnostics.starts,starts);assert.equal(a.master.gain.value,.8);assert.equal(a.bus.gain.value,effects);
 a.setBgmVolume(2);assert.equal(a.diagnostics.bgmVolume,1);a.setBgmVolume(NaN);assert.equal(a.diagnostics.bgmVolume,1);
});
test('rotor voices persist during flight, move in space, and stop on landing or leaving the arena',async()=>{
 const a=harness();await a.enable();const drone={id:'red-6',role:'aerial',x:3,y:4,z:1.6,vx:1,vy:0,vz:0,support_active:true,grounded:false,motor_power_w:600};
 const frame={status:'running',arena:{width:28,height:15},robots:[drone]};
 a.drones(frame);assert.equal(a.diagnostics.drones,1);const voice=a.rotorVoices.get('red-6'),count=a.context.sources.length;
 for(let i=0;i<20;i++)a.drones({...frame,robots:[{...drone,x:6}]});assert.equal(a.context.sources.length,count);assert.equal(voice.panner.positionX.value,-8);
 a.setPaused(true);a.drones(frame);assert.equal(a.diagnostics.drones,1);a.setPaused(false);await flush();
 a.drones({...frame,robots:[{...drone,alive:false,support_active:false}]});assert.equal(a.diagnostics.drones,1);
 a.drones({...frame,robots:[{...drone,z:0,support_active:false,grounded:true}]});assert.equal(a.diagnostics.drones,0);assert.ok(voice.noise.stopped>0);
 a.drones(frame);a.drones(null);assert.equal(a.diagnostics.drones,0);a.drones(frame);a.disable();assert.equal(a.diagnostics.drones,0);
});
test('multiple aerial models have separate voices and finished matches stop all rotors',async()=>{
 const a=harness();await a.enable();const drone={role:'aerial',x:3,y:4,z:2,vx:0,vy:0,vz:0,support_active:true};
 const frame={status:'running',arena:{width:28,height:15},robots:[{...drone,id:'red-1'},{...drone,id:'blue-3'}]};
 a.drones(frame);assert.equal(a.diagnostics.drones,2);a.drones({...frame,status:'finished'});assert.equal(a.diagnostics.drones,0);
});


test('interface sounds are distinct, throttled, and independent of paused match audio',async()=>{
 const a=harness();await a.enable();a.setPaused(true);
 a.ui('click');await flush();assert.equal(a.diagnostics.interfaceSounds,1);assert.equal(a.diagnostics.interfaceCue,'click');
 assert.equal(a.context.state,'suspended');assert.equal(a.interfaceContext.state,'running');
 a.ui('click');assert.equal(a.diagnostics.interfaceSounds,1);
 a.ui('confirm');assert.equal(a.diagnostics.interfaceSounds,2);assert.equal(a.diagnostics.interfaceCue,'confirm');
 a.interfaceContext.advance(.2);a.ui('hover');a.ui('hover');assert.equal(a.diagnostics.interfaceSounds,3);
 a.ui('select');assert.equal(a.diagnostics.interfaceSounds,4);
 a.disable();a.interfaceContext.advance(1);a.ui('open');assert.equal(a.diagnostics.interfaceSounds,4);assert.ok(a.interfaceGain.gain.value<.001);
 a.dispose();assert.equal(a.interfaceContext.state,'closed');
});
test('muting during audio unlock cancels pending interface feedback',async()=>{
 const a=harness();await a.enable();a.ui('confirm');a.disable();await flush();assert.equal(a.diagnostics.interfaceSounds,0);
});

const announcement=(cue,key=cue)=>({cue,key,team:'red',killer:'red-3',victim:'blue-3',at:1,count:2});
function finishVoice(a){const voice=a.announcementVoice;assert.ok(voice);a.context.advance(voice.node.buffer.duration);voice.node.onended();}
test('each kill cue decodes and plays the user-supplied original clip',async()=>{
 const a=harness();await a.enable();await flush();assert.equal(a.diagnostics.announcer.loaded,6);
 for(const cue of Object.keys(killAnnouncements.KILL_CUES)){
  let started=0;a.announce(announcement(cue),()=>started++);
  assert.equal(a.announcementVoice.node.buffer.url,killAnnouncements.KILL_CUES[cue].url);assert.equal(started,1);finishVoice(a);
 }
 assert.equal(a.diagnostics.announcer.starts,6);
});
test('announcements serialize, upgrade pending multi-kills, and play ace after penta',async()=>{
 const a=harness();await a.enable();await flush();const shown=[];
 for(const cue of Object.keys(killAnnouncements.KILL_CUES))a.announce(announcement(cue),()=>shown.push(cue));
 assert.deepEqual(shown,['first-blood']);assert.deepEqual(Array.from(a.diagnostics.announcer.queued),['penta-kill','aced']);
 finishVoice(a);assert.deepEqual(shown,['first-blood','penta-kill']);finishVoice(a);assert.deepEqual(shown,['first-blood','penta-kill','aced']);finishVoice(a);
 assert.equal(a.diagnostics.announcer.cue,null);assert.equal(a.diagnostics.announcer.starts,3);
});
test('all kill announcements leave music volume, playback and the user volume control independent',async()=>{
 const a=harness();a.bgm('match','game-1');await a.enable();await flush();const starts=a.diagnostics.starts;
 for(const cue of Object.keys(killAnnouncements.KILL_CUES)){
  const volume=a.music.gain.value;a.announce(announcement(cue),()=>{});assert.equal(a.music.gain.value,volume);
  a.setBgmVolume(.4);assert.ok(Math.abs(a.music.gain.value-.8*.4)<1e-10);finishVoice(a);
  assert.ok(Math.abs(a.music.gain.value-.8*.4)<1e-10);assert.equal(a.diagnostics.starts,starts);assert.equal(a.bus.gain.value,.58);
 }
 const volume=a.music.gain.value;a.announce(announcement('first-blood'),()=>{});a.cancelAnnouncements();assert.equal(a.music.gain.value,volume);
});
test('music does not share the compressor driven by gunfire and announcer peaks',async()=>{
 const a=harness();await a.enable();await flush();
 const musicLimiter=a.music.connections[0],effectsLimiter=a.bus.connections[0];
 assert.notEqual(musicLimiter,effectsLimiter);assert.equal(a.announcementBus.connections[0],effectsLimiter);
 assert.equal(musicLimiter.connections[0],a.master);assert.equal(effectsLimiter.connections[0],a.master);
});
test('pause freezes the current speech and does not accumulate new paused announcements',async()=>{
 const a=harness();await a.enable();await flush();a.announce(announcement('first-blood'),()=>{});a.context.advance(1);
 a.setPaused(true);a.context.advance(30);a.announce(announcement('double-kill'),()=>assert.fail('Paused cue must be ignored'));
 assert.equal(a.context.currentTime,1);assert.deepEqual(Array.from(a.diagnostics.announcer.queued),[]);assert.ok(!a.announcementVoice.node.stopped);
 a.setPaused(false);await flush();finishVoice(a);assert.equal(a.diagnostics.announcer.starts,1);
});
test('seek or match replacement invalidates late clip responses before sound or animation starts',async()=>{
 let release;const first=killAnnouncements.KILL_CUES['first-blood'].url;
 const a=harness(url=>url===first?new Promise(resolve=>{release=()=>resolve({ok:true,arrayBuffer:async()=>({url})});}):Promise.resolve({ok:true,arrayBuffer:async()=>({url})}));
 await a.enable();await flush();let shown=0;a.announce(announcement('first-blood'),()=>shown++);a.cancelAnnouncements();release();await flush();
 assert.equal(shown,0);assert.equal(a.diagnostics.announcer.starts,0);assert.deepEqual(Array.from(a.diagnostics.announcer.queued),[]);
});
test('muting cancels active and queued speech while muted kills retain their visual cue',async()=>{
 const a=harness();await a.enable();await flush();a.announce(announcement('first-blood'),()=>{});const node=a.announcementVoice.node;
 a.announce(announcement('double-kill'),()=>assert.fail('Muted queue must not resume'));a.disable();assert.notEqual(node.stopped,undefined);
 assert.equal(a.diagnostics.announcer.cue,null);assert.deepEqual(Array.from(a.diagnostics.announcer.queued),[]);
 let shown=0;a.announce(announcement('quadra-kill'),()=>shown++);assert.equal(shown,1);await a.enable();await flush();assert.equal(a.diagnostics.announcer.starts,1);
});
test('an unavailable announcer asset still presents the visual and drains its failed request',async()=>{
 const a=harness(async url=>({ok:!url.endsWith('aced.mp3'),arrayBuffer:async()=>({url})}));await a.enable();await flush();let shown=0;
 a.announce(announcement('aced'),()=>shown++);await flush();assert.equal(shown,1);assert.deepEqual(Array.from(a.diagnostics.announcer.queued),[]);assert.match(a.diagnostics.announcer.error,/aced/);
});
test('seeking while paused stops the active source before the suspended clock can resume it',async()=>{
 const a=harness();await a.enable();await flush();a.announce(announcement('first-blood'),()=>{});a.context.advance(1);const node=a.announcementVoice.node;
 a.setPaused(true);a.cancelAnnouncements();assert.equal(node.stopped,1);
 assert.equal(a.diagnostics.announcer.cue,null);a.setPaused(false);await flush();assert.equal(a.diagnostics.announcer.starts,1);
});
