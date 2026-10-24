import type {Frame,Metadata,MatchEvent} from './types';
import {strategyDisplayName} from './strategyIdentity';
import {MUSIC,type BgmCue} from './audioPlaylist';
import {KILL_CUES,type KillCue,type KillAnnouncement,type KillHighlight} from './killAnnouncements';
import {checkVideoExport,prepareVideoExport,saveMatchVideo,type VideoFormat} from './videoExport';
export type {BgmCue} from './audioPlaylist';
export const clock=(s:number)=>{s=Math.ceil(Math.max(0,s));return `${String(Math.floor(s/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`;};
export function download(blob:Blob,name:string){const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);}

type Vec={x:number;y:number;z:number};
const THROTTLE:Record<string,number>={'shot':.02,'shot-hero':.06,impact:.035,hit:.025,'hit-heavy':.05,collision:.07,base_hit:.05,outpost_hit:.05,overheat:.25,ammo_purchase:.1,unit_pickup:.1,level_up:.15,respawn:.1};
const IMPORTANT=new Set(['destroy','explosion','finish','respawn','rune_activated','base_hit','outpost_hit','level_up']);
const rand=(a:number,b:number)=>a+Math.random()*(b-a);

type Music={node:AudioBufferSourceNode;gain:GainNode;offset:number;startedAt:number;cue:BgmCue;scope:string;rate:number;duration:number;loop:boolean};
type MusicRequest={cue:BgmCue;scope:string;remaining:number;rate:number;at:number};
type DroneVoice={gain:GainNode;panner:PannerNode;noise:AudioBufferSourceNode;oscillators:OscillatorNode[];nodes:AudioNode[]};
type AnnouncementRequest={announcement:KillAnnouncement;started:(seconds:number)=>void;queuedAt:number};
type AnnouncementVoice={node:AudioBufferSourceNode;gain:GainNode;request:AnnouncementRequest};
const ANNOUNCEMENT_DURATION:Record<KillCue,number>={'first-blood':3.142,'double-kill':3.671,'triple-kill':2.134,'quadra-kill':2.646,'penta-kill':3.650,aced:2.793};
export type InterfaceCue='hover'|'click'|'select'|'confirm'|'back'|'open'|'success'|'error';

// Procedural match audio: layered noise/tone voices, 3D panned around the camera, with a shared room reverb and limiter.
export class ArenaAudio {
  enabled=false;context:AudioContext|null=null;master!:GainNode;destination!:MediaStreamAudioDestinationNode;
  private bus!:GainNode;private wet!:GainNode;private noise!:AudioBuffer;private last=new Map<string,number>();private voices:number[]=[];private arena={width:28,height:15};
  private music!:GainNode;private buffers=new Map<string,AudioBuffer>();private loading=new Map<BgmCue,Promise<void>>();private resolved=new Map<BgmCue,string>();private failures=new Map<BgmCue,string[]>();private source:Music|null=null;private saturation!:Float32Array<ArrayBuffer>;private musicError:string|null=null;private musicStarts=0;
  // Every stage owns its track; match sources always start at zero.
  private wanted:MusicRequest|null=null;private paused=false;
  // Which cue already played its opening recording out, per match/screen, so the hand-off to the
  // looping track happens exactly once and survives speed changes, pause and re-renders.
  private handedOver:{cue:BgmCue;scope:string}|null=null;
  private bgmVolume=.6;private rotorVoices=new Map<string,DroneVoice>();
  private announcementBus!:GainNode;private announcementBuffers=new Map<KillCue,AudioBuffer>();
  private announcementLoads=new Map<KillCue,Promise<boolean>>();private announcementQueue:AnnouncementRequest[]=[];
  private announcementVoice:AnnouncementVoice|null=null;private announcementStarts=0;private announcementEpoch=0;private announcementError:string|null=null;
  // Interface feedback stays available while playback is paused, and follows the same sound switch.
  private interfaceContext:AudioContext|null=null;private interfaceGain:GainNode|null=null;
  private interfaceLast=new Map<InterfaceCue,number>();private interfaceCount=0;private interfaceCue:InterfaceCue|null=null;
  ui(cue:InterfaceCue){
    if(!this.enabled)return;
    const c=this.interfaceContext??(this.interfaceContext=new AudioContext({latencyHint:'interactive'}));
    if(!this.interfaceGain){this.interfaceGain=c.createGain();this.interfaceGain.gain.value=.2;this.interfaceGain.connect(c.destination);}
    const gap=cue==='hover'?.09:.045;
    if(c.currentTime-(this.interfaceLast.get(cue)??-1)<gap)return;
    this.interfaceLast.set(cue,c.currentTime);
    const play=()=>{
      if(!this.enabled||c.state!=='running')return;
      this.interfaceGain!.gain.setTargetAtTime(.2,c.currentTime,.01);
      const notes:Record<InterfaceCue,number[]>={hover:[980],click:[660,880],select:[740,1100],confirm:[523,784,1047],back:[880,587],open:[440,660,880],success:[659,880,1318],error:[294,220]};
      const duration=cue==='hover'?.035:cue==='click'||cue==='select'?.065:.11;
      notes[cue].forEach((frequency,i)=>{
        const o=c.createOscillator(),g=c.createGain(),at=c.currentTime+.003+i*.045;
        o.type=cue==='error'?'triangle':'sine';o.frequency.value=frequency;
        g.gain.setValueAtTime(.0001,at);g.gain.exponentialRampToValueAtTime(cue==='hover'?.12:.27,at+.003);g.gain.exponentialRampToValueAtTime(.0001,at+duration);
        o.connect(g).connect(this.interfaceGain!);o.start(at);o.stop(at+duration+.01);
        o.onended=()=>{o.disconnect();g.disconnect();};
      });
      this.interfaceCount++;this.interfaceCue=cue;
    };
    if(c.state==='running')play();else void c.resume().then(play).catch(()=>{});
  }
  setBgmVolume(value:number){
    if(!Number.isFinite(value))return;
    this.bgmVolume=Math.max(0,Math.min(1,value));
    if(this.context&&this.music){const t=this.context.currentTime;this.music.gain.cancelScheduledValues(t);this.music.gain.setTargetAtTime(.8*this.bgmVolume,t,.025);}
  }
  async enable(){
    if(!this.context){
      const c=this.context=new AudioContext({latencyHint:'interactive'});
      this.master=c.createGain();this.master.gain.value=.8;this.master.connect(c.destination);this.destination=c.createMediaStreamDestination();this.master.connect(this.destination);
      const limitedBus=()=>{const limiter=c.createDynamicsCompressor();limiter.threshold.value=-9;limiter.knee.value=8;limiter.ratio.value=6;limiter.attack.value=.002;limiter.release.value=.2;limiter.connect(this.master);return limiter;};
      const limiter=limitedBus();
      this.bus=c.createGain();this.bus.gain.value=.58;this.bus.connect(limiter);
      const reverb=c.createConvolver();reverb.buffer=this.room(c,1.25);this.wet=c.createGain();this.wet.gain.value=.34;this.wet.connect(reverb);reverb.connect(limiter);
      this.noise=c.createBuffer(1,c.sampleRate*2,c.sampleRate);const data=this.noise.getChannelData(0);for(let i=0;i<data.length;i++)data[i]=Math.random()*2-1;
      // Announcer peaks must not trigger compression on the music channel.
      this.music=c.createGain();this.music.gain.value=.8*this.bgmVolume;this.music.connect(limitedBus());
      // Leave headroom when speech is added over a full-volume, unchanged BGM.
      this.announcementBus=c.createGain();this.announcementBus.gain.value=.65;this.announcementBus.connect(limiter);
      this.saturation=new Float32Array(2048);for(let i=0;i<this.saturation.length;i++){const x=i/(this.saturation.length-1)*2-1;this.saturation[i]=Math.tanh(x*1.45)/Math.tanh(1.45);}
    }
    this.enabled=true;this.master.gain.cancelScheduledValues(this.context.currentTime);this.master.gain.setTargetAtTime(.8,this.context.currentTime,.025);
    if(this.paused)await this.context.suspend();else await this.context.resume();
    const cue=this.wanted?.cue;if(cue)await this.loadTrack(cue);
    // Cache the competition and countdown tracks before their first transition (the match opening has
    // to hand over to the looping sting the moment it ends, four minutes into the match).
    void this.loadTrack('match');void this.loadTrack('match_alt');void this.loadTrack('countdown');this.sync();
    for(const cue of Object.keys(KILL_CUES) as KillCue[])void this.loadAnnouncement(cue);
    this.syncAnnouncements();
  }
  disable(){
    this.enabled=false;this.fadeOut(.08);this.stopDrones();this.cancelAnnouncements();
    if(this.interfaceContext&&this.interfaceGain)this.interfaceGain.gain.setTargetAtTime(.0001,this.interfaceContext.currentTime,.01);
    if(this.context){const t=this.context.currentTime;this.master.gain.cancelScheduledValues(t);this.master.gain.setTargetAtTime(.0001,t,.025);}
  }
  setPaused(paused:boolean){
    if(paused===this.paused)return;this.paused=paused;
    if(!this.context||!this.enabled)return;
    if(paused)void this.context.suspend();else void this.context.resume().then(()=>{this.sync();this.syncAnnouncements();});
  }
  bgm(cue:BgmCue|null,scope='default',remaining=5,rate=1){
    if(cue===null){this.wanted=null;this.fadeOut(.2);return;}
    const changed=this.wanted?.cue!==cue||this.wanted?.scope!==scope;
    if(changed){this.fadeOut(.16);this.wanted={cue,scope,remaining,rate,at:this.context?.currentTime??0};}
    else if(cue==='countdown'){this.wanted={cue,scope,remaining,rate,at:this.context?.currentTime??0};}
    if(this.enabled){void this.loadTrack(cue);this.sync();}
  }
  get musicPlaying(){return !!this.source;}
  get diagnostics(){return {state:this.context?.state??'none',cue:this.source?.cue??null,wanted:this.wanted?.cue??null,
    track:this.source?MUSIC[this.source.cue].url:null,file:this.source?this.resolved.get(this.source.cue)??null:null,
    failed:this.source?this.failures.get(this.source.cue)??[]:[],
    scope:this.source?.scope??null,startOffset:this.source?.offset??null,
    position:this.source&&this.context?Math.round(this.position(this.source)*100)/100:null,starts:this.musicStarts,error:this.musicError,bgmVolume:this.bgmVolume,drones:this.rotorVoices.size,interfaceSounds:this.interfaceCount,interfaceCue:this.interfaceCue,
    announcer:{cue:this.announcementVoice?.request.announcement.cue??null,starts:this.announcementStarts,queued:this.announcementQueue.map(r=>r.announcement.cue),loaded:this.announcementBuffers.size,error:this.announcementError}};}
  announce(announcement:KillAnnouncement,started:(seconds:number)=>void){
    if(this.paused)return;
    if(!this.enabled||!this.context||this.context.state!=='running'){started(Math.max(3.4,ANNOUNCEMENT_DURATION[announcement.cue]+.2));return;}
    // Keep the current voice intact. Pending multi-kills upgrade to the newest
    // count for that robot; an ACE remains separate and follows the PENTA.
    if(KILL_CUES[announcement.cue].rank>=2&&KILL_CUES[announcement.cue].rank<=5)
      this.announcementQueue=this.announcementQueue.filter(r=>r.announcement.killer!==announcement.killer||KILL_CUES[r.announcement.cue].rank<2||KILL_CUES[r.announcement.cue].rank>5);
    this.announcementQueue.push({announcement,started,queuedAt:this.context.currentTime});
    if(this.announcementQueue.length>4){const rank=Math.min(...this.announcementQueue.map(r=>KILL_CUES[r.announcement.cue].rank));this.announcementQueue.splice(this.announcementQueue.findIndex(r=>KILL_CUES[r.announcement.cue].rank===rank),1);}
    this.syncAnnouncements();
  }
  cancelAnnouncements(){
    this.announcementEpoch++;this.announcementQueue=[];
    const voice=this.announcementVoice;this.announcementVoice=null;
    if(voice&&this.context){voice.gain.gain.cancelScheduledValues(this.context.currentTime);voice.gain.gain.setValueAtTime(.0001,this.context.currentTime);voice.node.stop(this.context.currentTime);}
    this.updateEffectsMix();
  }
  private updateEffectsMix(){
    if(!this.context||!this.bus)return;const t=this.context.currentTime,duck=!!this.announcementVoice;
    this.bus.gain.cancelScheduledValues(t);this.bus.gain.setTargetAtTime(.58*(duck?.7:1),t,.08);
  }
  private loadAnnouncement(cue:KillCue):Promise<boolean>{
    if(this.announcementBuffers.has(cue))return Promise.resolve(true);
    const pending=this.announcementLoads.get(cue);if(pending)return pending;if(!this.context)return Promise.resolve(false);
    const load=fetch(KILL_CUES[cue].url).then(r=>{if(!r.ok)throw new Error(`Announcer unavailable: ${cue}`);return r.arrayBuffer();})
      .then(data=>this.context!.decodeAudioData(data)).then(buffer=>{this.announcementBuffers.set(cue,buffer);return true;})
      .catch(error=>{this.announcementError=String(error.message||error);this.announcementLoads.delete(cue);return false;});
    this.announcementLoads.set(cue,load);return load;
  }
  private syncAnnouncements(){
    const c=this.context;if(!this.enabled||!c||this.paused||c.state!=='running'||this.announcementVoice)return;
    while(this.announcementQueue.length&&c.currentTime-this.announcementQueue[0].queuedAt>8)this.announcementQueue.shift();
    const request=this.announcementQueue[0];if(!request)return;
    const buffer=this.announcementBuffers.get(request.announcement.cue);
    if(!buffer){const epoch=this.announcementEpoch;void this.loadAnnouncement(request.announcement.cue).then(ok=>{
      if(epoch!==this.announcementEpoch||this.announcementQueue[0]!==request)return;
      if(!ok){this.announcementQueue.shift();if(!this.paused)request.started(Math.max(3.4,ANNOUNCEMENT_DURATION[request.announcement.cue]+.2));}
      this.syncAnnouncements();
    });return;}
    this.announcementQueue.shift();const node=c.createBufferSource(),gain=c.createGain();node.buffer=buffer;gain.gain.value=KILL_CUES[request.announcement.cue].gain;
    node.connect(gain).connect(this.announcementBus);const voice={node,gain,request};this.announcementVoice=voice;this.announcementStarts++;this.updateEffectsMix();
    node.onended=()=>{node.disconnect();gain.disconnect();if(this.announcementVoice!==voice)return;this.announcementVoice=null;this.updateEffectsMix();this.syncAnnouncements();};
    node.start(c.currentTime);request.started(Math.max(3.4,buffer.duration+.2));
  }
  // A decoded buffer is cached per file (several cues can share one soundtrack) but the *choice* of
  // file is cached per cue: `results` and `pick` both fall back to `home.mp3`, and a shared key
  // would let the first one's fallback answer for the second and hide its own uploaded track.
  private loadTrack(cue:BgmCue):Promise<void>{    const chosen=this.resolved.get(cue);
    if(chosen&&this.buffers.has(chosen))return Promise.resolve();
    const pending=this.loading.get(cue);if(pending)return pending;
    if(!this.context)return Promise.resolve();
    const url=MUSIC[cue].url;
    // A cue may name a file that is not shipped (`highlight.m4a`, `<cue>-theme.*`): try it, then fall
    // back to what the repository does ship, and remember the winner for this cue.
    const fetchTrack=(source:string)=>fetch(source).then(r=>{if(!r.ok)throw new Error(`Music unavailable: ${cue}`);return r.arrayBuffer();}).then(data=>this.context!.decodeAudioData(data));
    const listed=(value:string|string[]|undefined)=>Array.isArray(value)?value:value?[value]:[];
    // Walk the chain in order: an uploaded track, then the shipped one, then a format this browser
    // can actually decode. `used` remembers which file won and `failures` why the others did not, so
    // a track that silently falls back can be explained in the diagnostics panel.
    let used=url;
    this.failures.delete(cue);
    const attempt=(sources:string[]):Promise<AudioBuffer>=>{
      const [next,...rest]=sources;
      if(!next)return Promise.reject(new Error(`Music unavailable: ${cue}`));
      return fetchTrack(next).then(track=>{used=next;return track;}).catch(e=>{
        const list=this.failures.get(cue)??[];list.push(`${next} → ${String((e as Error)?.message||e).slice(0,90)}`);this.failures.set(cue,list);
        return attempt(rest);
      });
    };
    const load=attempt([...listed(MUSIC[cue].override),url,...listed(MUSIC[cue].fallback)])
      .then(track=>{this.buffers.set(used,track);this.resolved.set(cue,used);this.musicError=null;this.sync();})
      .catch(e=>{this.musicError=String(e.message||e);this.loading.delete(cue);});
    this.loading.set(cue,load);return load;
  }
  private position(m:Music){const p=m.offset+(this.context!.currentTime-m.startedAt)*m.rate;return m.loop?p%m.duration:Math.min(p,m.duration);}
  // The track a cue is currently scoring with. A cue with a hand-off target (`match` → the repository
  // sting) plays its own recording **once**, and from its end the target takes over on loop; a machine
  // that has no installed recording at all falls straight through to the target instead of going quiet.
  private scoring(want:MusicRequest):BgmCue{
    const then=MUSIC[want.cue].then;
    if(!then)return want.cue;
    const handedOver=this.handedOver?.cue===want.cue&&this.handedOver.scope===want.scope;
    const missing=!this.resolved.has(want.cue)&&!this.loading.has(want.cue);
    return handedOver||missing?then:want.cue;
  }
  private sync(){
    const want=this.wanted;if(!this.enabled||!this.context||!want||this.paused)return;
    const cue=this.scoring(want);
    const chosen=this.resolved.get(cue);
    const buffer=chosen?this.buffers.get(chosen):undefined;if(!buffer)return;
    const countdown=cue==='countdown',rate=countdown?Math.max(.5,Math.min(8,want.rate)):1;
    const target=countdown?Math.max(0,Math.min(buffer.duration-.001,5-Math.max(0,want.remaining-(this.context.currentTime-want.at)*rate))):0;
    const s=this.source;
    if(s&&s.cue===cue&&s.scope===want.scope){
      if(!countdown||Math.abs(this.position(s)-target)<.35&&s.rate===rate)return;
    }
    this.fadeOut(.12);const c=this.context,node=c.createBufferSource(),gain=c.createGain();node.buffer=buffer;
    // A hand-off cue runs to its end once, so the loop that follows is the other recording.
    node.loop=MUSIC[cue].loop&&!MUSIC[cue].then;node.loopStart=0;node.loopEnd=buffer.duration;node.playbackRate.value=rate;
    gain.gain.setValueAtTime(.0001,c.currentTime);gain.gain.exponentialRampToValueAtTime(MUSIC[cue].gain,c.currentTime+.12);
    node.connect(gain).connect(this.music);node.start(c.currentTime,target);
    const current:Music={node,gain,offset:target,startedAt:c.currentTime,cue,scope:want.scope,rate,duration:buffer.duration,loop:node.loop};this.source=current;this.musicStarts++;
    node.onended=()=>{node.disconnect();gain.disconnect();if(this.source!==current)return;
      this.source=null;
      if(!MUSIC[cue].then)return;
      this.handedOver={cue,scope:want.scope};
      this.sync();
    };
  }
  private fadeOut(seconds:number){
    const s=this.source;if(!s||!this.context)return;this.source=null;const t=this.context.currentTime;
    s.gain.gain.cancelScheduledValues(t);s.gain.gain.setValueAtTime(Math.max(.0001,s.gain.gain.value),t);s.gain.gain.exponentialRampToValueAtTime(.0001,t+seconds);s.node.stop(t+seconds+.02);
  }
  dispose(){this.enabled=false;this.wanted=null;this.fadeOut(.02);this.stopDrones();this.cancelAnnouncements();void this.context?.close();void this.interfaceContext?.close();}
  // Persistent rotor voices follow the flight state, rather than triggering every frame.
  drones(frame:Frame|null){
    if(!frame||frame.status!=='running'){this.stopDrones();return;}
    if(!this.enabled||!this.context||this.paused||this.context.state!=='running')return;
    this.arena=frame.arena;const c=this.context,t=c.currentTime;
    const flying=frame.robots.filter(r=>r.role==='aerial'&&(r.drones?r.drones.some(d=>d.state==='flying'):r.powered!==false&&(r.support_active||r.z>.25)&&r.grounded!==true));
    const active=new Set(flying.map(r=>r.id));
    for(const id of this.rotorVoices.keys())if(!active.has(id))this.stopDrone(id);
    for(const r of flying){
      let voice=this.rotorVoices.get(r.id);
      if(!voice){
        const gain=c.createGain(),panner=c.createPanner();gain.gain.value=0;
        panner.panningModel='equalpower';panner.distanceModel='inverse';panner.refDistance=5;panner.rolloffFactor=1;panner.maxDistance=60;gain.connect(panner).connect(this.bus);
        const noise=c.createBufferSource(),filter=c.createBiquadFilter(),wind=c.createGain();noise.buffer=this.noise;noise.loop=true;filter.type='bandpass';filter.frequency.value=650;filter.Q.value=.55;wind.gain.value=.17;noise.connect(filter).connect(wind).connect(gain);noise.start(t);
        const oscillators:OscillatorNode[]=[],nodes:AudioNode[]=[filter,wind];
        for(const [i,level] of [.35,.11,.045].entries()){const motor=c.createOscillator(),partial=c.createGain();motor.type=i===0?'triangle':'sine';partial.gain.value=level;motor.connect(partial).connect(gain);motor.frequency.value=115*(i+1);motor.start(t);oscillators.push(motor);nodes.push(partial);}
        voice={gain,panner,noise,oscillators,nodes};this.rotorVoices.set(r.id,voice);
      }
      const load=Math.min(1,Math.max(.15,(r.motor_power_w??400)/900)),speed=Math.hypot(r.vx,r.vy,r.vz);
      voice.gain.gain.setTargetAtTime((.18+load*.12)/Math.sqrt(Math.max(1,flying.length)),t,.18);
      voice.oscillators.forEach((o,i)=>o.frequency.setTargetAtTime((100+load*50+Math.min(speed,4)*7)*(i+1)+(i%2?1.7:0),t,.12));
      voice.panner.positionX.value=r.x-frame.arena.width/2;voice.panner.positionY.value=r.z;voice.panner.positionZ.value=r.y-frame.arena.height/2;
    }
  }
  private stopDrone(id:string){
    const voice=this.rotorVoices.get(id);if(!voice||!this.context)return;this.rotorVoices.delete(id);
    const t=this.context.currentTime;voice.gain.gain.cancelScheduledValues(t);voice.gain.gain.setTargetAtTime(0,t,.09);
    const sources=[voice.noise,...voice.oscillators];sources.forEach(o=>o.stop(t+.35));
    voice.noise.onended=()=>{sources.forEach(o=>o.disconnect());voice.nodes.forEach(n=>n.disconnect());voice.gain.disconnect();voice.panner.disconnect();};
  }
  private stopDrones(){for(const id of this.rotorVoices.keys())this.stopDrone(id);}
  // Countdown pips: 5..1 short, 0 the long start horn.
  countdown(n:number){
    if(!this.enabled||!this.context||this.paused||this.context.state!=='running')return;const c=this.context,t=c.currentTime+.005,o=c.createGain();o.gain.value=.5;o.connect(this.master);window.setTimeout(()=>o.disconnect(),2500);
    if(n>0){this.tone(o,t,'sine',n<=3?1320:880,n<=3?1320:880,.16,.5,.004);this.tone(o,t,'triangle',n<=3?2640:1760,n<=3?2640:1760,.08,.12,.002);}
    else{for(const f of [523.25,659.25,783.99,1046.5])this.tone(o,t,'sawtooth',f,f,.9,.07,.02);this.tone(o,t,'sine',130,65,.7,.6,.004);this.hiss(o,t,'bandpass',2600,5200,.5,.18,1,.01);}
  }
  // Lineup intro cuts: a swell and boom for the opening, a whoosh and hit for each team card and robot shot.
  sting(kind:'open'|'team'|'robot'|'faceoff'){
    if(!this.enabled||!this.context||this.paused||this.context.state!=='running')return;const c=this.context,t=c.currentTime+.005,o=c.createGain();o.gain.value=.42;o.connect(this.master);window.setTimeout(()=>o.disconnect(),3500);
    if(kind==='robot'){this.hiss(o,t,'bandpass',1400,6200,.28,.22,1.4,.04);this.tone(o,t+.16,'square',1900,1250,.05,.07,.002);this.tone(o,t+.16,'sine',96,52,.3,.5,.004);return;}
    if(kind==='team'){this.hiss(o,t,'bandpass',260,3600,.5,.3,1.1,.18);this.tone(o,t+.38,'sine',120,46,.7,.75,.004);this.tone(o,t+.38,'sawtooth',220,180,.35,.07,.01);this.hiss(o,t+.38,'lowpass',900,140,.5,.25);return;}
    this.hiss(o,t,'bandpass',300,5200,kind==='open'?1.1:.6,.26,1,kind==='open'?.9:.4);const hit=t+(kind==='open'?.95:.45);
    this.tone(o,hit,'sine',78,36,1.4,.9,.004);this.hiss(o,hit,'lowpass',1200,120,.9,.35);
    for(const f of kind==='open'?[146.83,220,293.66,440]:[164.81,246.94,329.63,493.88])this.tone(o,hit,'sawtooth',f,f,1.2,.05,.02);
  }
  listen(p:Vec,forward:Vec,up:Vec,arena?:{width:number;height:number}){
    if(!this.context)return;if(arena)this.arena=arena;const l=this.context.listener;
    if(l.positionX){l.positionX.value=p.x;l.positionY.value=p.y;l.positionZ.value=p.z;l.forwardX.value=forward.x;l.forwardY.value=forward.y;l.forwardZ.value=forward.z;l.upX.value=up.x;l.upY.value=up.y;l.upZ.value=up.z;}
    else{l.setPosition(p.x,p.y,p.z);l.setOrientation(forward.x,forward.y,forward.z,up.x,up.y,up.z);}
  }
  play(e:MatchEvent){
    if(!this.enabled||!this.context||this.paused||this.context.state!=='running')return;const c=this.context,t=c.currentTime+.005,v=1+(Math.random()-.5)*.1;
    this.voices=this.voices.filter(end=>end>c.currentTime);if(this.voices.length>40&&!IMPORTANT.has(e.type))return;
    const heavyHit=(e.damage??0)>=60,key=e.type==='shot'&&(e.role==='hero'||e.role==='heavy')?'shot-hero':e.type==='hit'&&heavyHit?'hit-heavy':e.type,gap=THROTTLE[key];
    if(gap!==undefined){if(t-(this.last.get(key)??-1)<gap)return;this.last.set(key,t);}
    if(e.type==='shot'&&(e.role==='hero'||e.role==='heavy')){
      const o=this.voice(e,1,.22,.5);
      this.hiss(o,t,'highpass',2400,2400,.009,.18,.7);this.tone(o,t,'sine',125*v,40,.3,.9,.002);this.hiss(o,t,'lowpass',1600,240,.22,.6,.7);
      this.tone(o,t+.035,'square',240*v,170,.035,.05);this.hiss(o,t+.03,'bandpass',900,600,.08,.12,2);
    }else if(e.type==='shot'){
      const o=this.voice(e,.7,.08,.18),k=e.role==='aerial'?v*1.15:v;
      this.hiss(o,t,'highpass',2600,2600,.007,.13,.7);this.hiss(o,t,'bandpass',1050*k,520,.085,.32,.8);this.tone(o,t,'sine',174*k,73,.11,.43);this.tone(o,t,'triangle',347*k,218,.055,.08);
    }else if(e.type==='hit'){
      const o=this.thickVoice(e,heavyHit?.94:.78,heavyHit?.23:.13,heavyHit?.65:.38);
      this.hiss(o,t,'bandpass',1700*v,1100,.012,heavyHit?.16:.10,.8);
      if(heavyHit){
        this.bell(o,t,[[142*v,.60,.48],[239*v,.32,.34],[397*v,.18,.26],[673*v,.06,.16]],.84);
        this.tone(o,t,'sine',88*v,43,.34,.65,.003);this.hiss(o,t,'lowpass',1050,220,.27,.46,.7);
        this.tone(o,t+.009,'triangle',178*v,94,.18,.22,.004);
      }else{
        this.bell(o,t,[[187*v,.52,.25],[317*v,.30,.19],[529*v,.14,.13],[881*v,.035,.09]],.79);
        this.tone(o,t,'sine',130*v,66,.15,.43,.002);this.hiss(o,t,'lowpass',850,280,.13,.34,.7);
      }
    }else if(e.type==='base_hit'||e.type==='outpost_hit'){
      const heavy=(e.damage??0)>=100,o=this.thickVoice(e,e.type==='base_hit'?.95:.82,.28,1.05);
      this.bell(o,t,[[79*v,.53,.72],[133*v,.39,.58],[223*v,.26,.42],[371*v,.12,.30],[619*v,.045,.18]],heavy?.91:.67);
      this.hiss(o,t,'bandpass',1050,620,.034,.21,.7);this.hiss(o,t,'lowpass',670,145,.23,.30,.7);
      this.tone(o,t,'sine',heavy?72:105,heavy?35:56,.36,heavy?.58:.35,.003);
      if(e.weakspot)this.bell(o,t+.012,[[465*v,.09,.22],[782*v,.04,.15]],.6);
    }else if(e.type==='impact'){
      const o=this.thickVoice(e,.50,.07,.28);
      this.hiss(o,t,'bandpass',850*v,360,.07,.43,.65);this.tone(o,t,'sine',118*v,65,.10,.29,.002);
      this.bell(o,t,[[302*v,.13,.13],[506*v,.04,.08]],.5);
    }else if(e.type==='collision'){
      const k=Math.max(.25,Math.min(1,(e.impulse_n_s??20)/40)),o=this.voice(e,.4+k*.6,.15,.2);
      this.tone(o,t,'sine',95*v,48,.14,.6*k+.1);this.hiss(o,t,'lowpass',700,200,.1,.45*k+.1);this.tone(o,t,'square',190*v,140,.04,.04*k);
    }else if(e.type==='destroy'||e.type==='explosion'){
      const k=e.type==='destroy'?1:.65,o=this.voice(e,1.1*k,.55,2.4);
      this.hiss(o,t,'highpass',1600,700,.09,.9);this.tone(o,t,'sine',84,28,1.1,1,.006);this.hiss(o,t,'lowpass',2600,140,1.5,.85,.8,.004);this.hiss(o,t+.02,'lowpass',260,60,2.2,.5,.7,.06);
      if(e.type==='destroy')this.tone(this.filter(o,'lowpass',2400,2400,0,t),t+.06,'sawtooth',1300,70,.85,.09,.01);
      for(let i=0;i<10;i++)this.hiss(o,t+.08+Math.random()*.9,'bandpass',rand(1800,5200),rand(1800,5200),.018,rand(.05,.27),2);
    }else if(e.type==='respawn'){
      const o=this.voice(e,.55,.3,1.2);this.tone(o,t,'triangle',220,880,.6,.25,.35);this.tone(o,t,'sine',440,1760,.6,.12,.35);this.bell(o,t+.45,[[1318,.3,.6],[1976,.2,.45],[2637,.1,.3]],.7);
    }else if(e.type==='level_up'){
      const o=this.voice(e,.45,.3,1);[784,988,1175,1568].forEach((f,i)=>this.bell(o,t+i*.07,[[f,.3,.4],[f*2,.12,.25],[f*3.01,.05,.15]],1));
    }else if(e.type==='overheat'){
      const o=this.voice(e,.45,.2,.8);this.hiss(o,t,'highpass',2600,4200,.7,.35,.7,.03);this.tone(o,t,'square',1400,1400,.06,.05);this.tone(o,t+.11,'square',1400,1400,.06,.05);
    }else if(e.type==='ammo_purchase'){
      const o=this.voice(e,.45,.15,.4);this.bell(o,t,[[1975,.25,.12]],1);this.bell(o,t+.06,[[2637,.25,.28]],1);
    }else if(e.type==='unit_pickup'||e.type==='assembly_start'){
      const o=this.voice(e,.42,.12,.3);this.tone(o,t,'square',300*v,180,.07,.18);this.tone(o,t,'sine',140,90,.09,.4);this.hiss(o,t,'bandpass',1300,900,.05,.55,1);this.hiss(o,t+.075,'highpass',3800,3800,.012,.35,.7);
    }else if(['assembly_success','outpost_rebuilt','capture','skill'].includes(e.type)){
      const o=this.voice(e,.45,.35,1.2);[523.25,659.25,783.99].forEach((f,i)=>this.bell(o,t+i*.09,[[f,.3,.7],[f*2,.12,.4]],1));
    }else if(e.type==='assembly_first_core'){
      const o=this.voice(e,.4,.25,.6);this.bell(o,t,[[880,.3,.3],[1760,.12,.2]],1);this.bell(o,t+.08,[[1318.5,.3,.45],[2637,.1,.3]],1);
    }else if(e.type==='assembly_failed'){
      const o=this.voice(e,.8,.25,.8),buzz=this.filter(o,'lowpass',1400,700,.5,t);
      this.tone(buzz,t,'square',330,330,.16,.12,.005);this.tone(buzz,t+.18,'square',220,196,.32,.12,.005);this.hiss(o,t,'bandpass',600,400,.12,.2,1.5);
    }else if(e.type==='remote_heal'){
      const o=this.voice(e,.45,.4,1.2);[587.33,739.99,880,1174.66].forEach((f,i)=>this.bell(o,t+i*.06,[[f,.28,.5],[f*2,.1,.3]],1));this.hiss(o,t,'bandpass',2400,6000,.6,.12,2,.25);
    }else if(e.type==='income'){
      const o=this.voice(e,.35,.3,.7);this.bell(o,t,[[2093,.25,.2],[4186,.08,.12]],1);this.bell(o,t+.07,[[2637,.25,.4],[5274,.08,.2]],1);
    }else if(e.type==='rune_start'){
      const o=this.voice(e,.45,.4,1.3);this.tone(this.filter(o,'lowpass',300,1800,1,t),t,'sawtooth',110,220,1.1,.22,.4);this.tone(o,t,'sine',110,220,1.1,.18,.4);
    }else if(e.type==='rune_reset'){
      const o=this.voice(e,.5,.35,1);this.tone(this.filter(o,'lowpass',1600,300,.7,t),t,'sawtooth',330,110,.7,.2,.01);this.tone(o,t,'sine',220,90,.6,.25,.01);
    }else if(e.type==='rune_activated'){
      const o=this.voice(e,.55,.5,2),pad=this.filter(o,'lowpass',400,3200,.9,t);
      for(const f of [220,277.18,329.63,440])this.tone(pad,t,'sawtooth',f,f,1.7,.16,.12);this.bell(o,t+.25,[[1760,.2,.8],[2637,.12,.6]],1);
    }else if(e.type==='finish'&&!this.resolved.has('victory')){
      const o=this.voice(e,.8,.45,3),brass=this.filter(o,'lowpass',900,2400,.3,t),win=!!e.winner;
      for(const f of win?[196,246.94,293.66]:[196,233.08,293.66])for(const [d,a] of [[1,.14],[1.004,.08]])this.tone(brass,t,'sawtooth',f*d,f*d,.3,a,.02);
      for(const f of win?[261.63,329.63,392,523.25]:[220,261.63,329.63,440])for(const [d,a] of [[1,.14],[1.005,.08]])this.tone(brass,t+.28,'sawtooth',f*d,f*d,1.9,a,.04);
      this.tone(o,t,'sine',98,60,.6,.7);this.tone(o,t+.28,'sine',98,55,.9,.8);this.hiss(o,t+.28,'lowpass',500,120,.6,.4);
    }
  }
  private thickVoice(e:MatchEvent,gain:number,send:number,life:number){
    const out=this.voice(e,gain,send,life),warm=this.context!.createBiquadFilter(),drive=this.context!.createWaveShaper();
    warm.type='lowpass';warm.frequency.value=3100;warm.Q.value=.6;drive.curve=this.saturation;drive.oversample='2x';
    drive.connect(warm).connect(out);window.setTimeout(()=>{drive.disconnect();warm.disconnect();},(life+.35)*1000);return drive;
  }
  private voice(e:MatchEvent,gain:number,send:number,life:number){
    const c=this.context!,out=c.createGain();out.gain.value=gain;let tail:AudioNode=out,reverb:GainNode|null=null;
    if(e.x!==undefined&&e.y!==undefined){
      const p=c.createPanner();p.panningModel='equalpower';p.distanceModel='inverse';p.refDistance=7;p.rolloffFactor=.7;p.maxDistance=100;
      p.positionX.value=e.x-this.arena.width/2;p.positionY.value=e.z??.5;p.positionZ.value=e.y-this.arena.height/2;out.connect(p);tail=p;
    }
    tail.connect(this.bus);if(send>0){reverb=c.createGain();reverb.gain.value=send;tail.connect(reverb);reverb.connect(this.wet);}
    this.voices.push(c.currentTime+life);window.setTimeout(()=>{tail.disconnect();out.disconnect();reverb?.disconnect();},(life+.3)*1000);
    return out;
  }
  private envelope(param:AudioParam,t:number,peak:number,attack:number,dur:number){param.setValueAtTime(.0001,t);param.exponentialRampToValueAtTime(Math.max(.0002,peak),t+attack);param.exponentialRampToValueAtTime(.0001,t+Math.max(dur,attack+.005));}
  private tone(out:AudioNode,t:number,type:OscillatorType,f0:number,f1:number,dur:number,peak:number,attack=.003){
    const c=this.context!,o=c.createOscillator(),g=c.createGain();o.type=type;o.frequency.setValueAtTime(f0,t);if(f1!==f0)o.frequency.exponentialRampToValueAtTime(f1,t+dur);
    this.envelope(g.gain,t,peak,attack,dur);o.connect(g).connect(out);o.start(t);o.stop(t+dur+.05);
  }
  private hiss(out:AudioNode,t:number,type:BiquadFilterType,f0:number,f1:number,dur:number,peak:number,q=.8,attack=.002){
    const c=this.context!,s=c.createBufferSource(),f=c.createBiquadFilter(),g=c.createGain();s.buffer=this.noise;s.loop=true;f.type=type;f.Q.value=q;
    f.frequency.setValueAtTime(f0,t);if(f1!==f0)f.frequency.exponentialRampToValueAtTime(f1,t+dur);
    this.envelope(g.gain,t,peak,attack,dur);s.connect(f).connect(g).connect(out);s.start(t,Math.random()*1.9);s.stop(t+dur+.05);
  }
  private bell(out:AudioNode,t:number,partials:number[][],peak:number){for(const [f,a,d] of partials)this.tone(out,t,'sine',f,f,d,peak*a,.002);}
  private filter(out:AudioNode,type:BiquadFilterType,f0:number,f1:number,dur:number,t:number){
    const f=this.context!.createBiquadFilter();f.type=type;f.frequency.setValueAtTime(f0,t);if(f1!==f0)f.frequency.exponentialRampToValueAtTime(f1,t+dur);f.connect(out);return f;
  }
  private room(c:AudioContext,seconds:number){
    const length=Math.floor(c.sampleRate*seconds),buffer=c.createBuffer(2,length,c.sampleRate);
    for(let ch=0;ch<2;ch++){
      const data=buffer.getChannelData(ch);let low=0;
      for(let i=0;i<length;i++){const t=i/length;low+=(Math.random()*2-1-low)*(.5-.42*t);data[i]=low*Math.pow(1-t,3.2)*Math.min(1,i/(c.sampleRate*.008));}
      for(const [delay,gain] of [[.011,.5],[.019,.35],[.027+ch*.004,.3],[.041,.2]])data[Math.floor(delay*c.sampleRate)]+=gain*(ch?-1:1);
    }
    return buffer;
  }
}

// DOM ceremonies are not in the WebGL canvas, so the export redraws their essentials: countdown numerals and the result title.
export type RecorderOverlay={kind:'countdown';n:number}|{kind:'title';title:string;sub:string;color:string}|{kind:'intro';title:string;sub:string;lines:string[];image?:string}|{kind:'results';headline:string;rows:{label:string;red:string;blue:string}[]}|{kind:'mvp';name:string;team:string;lines:string[];image?:string}|null;
export class BroadcastRecorder {
  canvas=document.createElement('canvas');ctx:CanvasRenderingContext2D;recorder:MediaRecorder|null=null;source:HTMLCanvasElement|null=null;stream:MediaStream|null=null;started=0;frames=0;chunks:Blob[]=[];overlay:RecorderOverlay=null;announcement:KillHighlight|null=null;
  private capture:Promise<{blob:Blob;error:string|null}>|null=null;private format:VideoFormat='mp4';
  private recovery:{blob:Blob;name:string;matchId?:string;duration?:number}|null=null;private overlayImages=new Map<string,HTMLImageElement>();
  constructor(public audio:ArenaAudio){this.canvas.width=1920;this.canvas.height=1080;this.ctx=this.canvas.getContext('2d')!;}
  get active(){return this.recorder?.state==='recording';}
  get hasRecovery(){return this.recovery!==null;}
  saveOriginal(){if(this.recovery){download(this.recovery.blob,this.recovery.name);this.recovery=null;}}
  discardOriginal(){this.recovery=null;}
  async start(format:VideoFormat='mp4'){
    if(this.active)throw new Error('录像已经开始');
    if(this.hasRecovery)throw new Error('请先保存或丢弃上一段原始录像');
    if(!this.source)throw new Error('请等待 3D 场景加载');
    if(!window.MediaRecorder)throw new Error('当前浏览器不支持录像，请使用 Chrome / Edge');
    const mime=['video/webm;codecs=vp9,opus','video/webm;codecs=vp8,opus','video/webm'].find(m=>MediaRecorder.isTypeSupported(m));
    if(!mime)throw new Error('当前浏览器不支持录像，请使用桌面应用或 Chrome / Edge');
    await checkVideoExport(format);await this.audio.enable();
    // Seed a frame even if the renderer is still loading or the scene is paused.
    this.ctx.fillStyle='#10191f';this.ctx.fillRect(0,0,1920,1080);this.frames=0;
    const stream=this.canvas.captureStream(30);this.stream=stream;this.chunks=[];this.format=format;
    try{
      for(const track of this.audio.destination.stream.getAudioTracks())stream.addTrack(track.clone());
      const recorder=this.recorder=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:8000000});
      this.capture=new Promise(resolve=>{let error:string|null=null;
        recorder.ondataavailable=e=>{if(e.data.size)this.chunks.push(e.data);};
        recorder.onerror=()=>{error='录像编码失败';};
        recorder.onstop=()=>{const blob=new Blob(this.chunks,{type:recorder.mimeType||mime});stream.getTracks().forEach(t=>t.stop());this.stream=null;this.chunks=[];resolve({blob,error});};
      });
      this.started=performance.now();recorder.start(1000);
    }catch(error){stream.getTracks().forEach(t=>t.stop());this.stream=null;this.recorder=null;this.capture=null;throw error;}
  }
  async cancel(){const capture=this.capture;if(this.recorder&&this.recorder.state!=='inactive')this.recorder.stop();if(capture)await capture;this.capture=null;this.recorder=null;}
  get canRetrySave(){return !!this.recovery?.matchId;}
  async retrySave(onProgress:(message:string)=>void=()=>{}){const r=this.recovery;if(!r?.matchId)return;await saveMatchVideo(r.blob,r.matchId,onProgress,r.duration);this.recovery=null;}
  async stop(onProgress:(message:string)=>void=()=>{},matchId?:string){
    const capture=this.capture;if(!capture)return;
    const duration=Math.max(.034,(performance.now()-this.started)/1000);
    if(this.recorder&&this.recorder.state!=='inactive')this.recorder.stop();
    const {blob,error}=await capture;this.capture=null;this.recorder=null;
    const name='rmuc-arena-'+new Date().toISOString().replaceAll(':','-');
    try{
      if(error)throw new Error(error);
      if(matchId)await saveMatchVideo(blob,matchId,onProgress,duration);
      else{const video=await prepareVideoExport(blob,this.format,onProgress,duration);download(video,`${name}.${this.format}`);}
    }catch(cause){if(blob.size){this.recovery={blob,name:`${name}.webm`,matchId,duration};throw new Error(`${(cause as Error).message} 原始 WebM 已保留，请点击「保存原始 WebM」。`);}throw cause;}
  }
  draw(frame:Frame,metadata:Metadata|null){if(!this.active||!this.source)return;this.frames++;const c=this.ctx;c.fillStyle='#10191f';c.fillRect(0,0,1920,1080);const scale=Math.min(1920/this.source.width,942/this.source.height),w=this.source.width*scale,h=this.source.height*scale;c.drawImage(this.source,(1920-w)/2,90+(942-h)/2,w,h);c.fillStyle='#0f181ee8';c.fillRect(0,0,1920,90);c.fillRect(0,1030,1920,50);c.textBaseline='middle';c.textAlign='left';c.fillStyle='#e6b66c';c.font='bold 25px sans-serif';c.fillText('RMUC / STRATEGY LEAGUE',28,44);c.fillStyle='#e78e7e';c.font='bold 26px sans-serif';c.fillText(`${strategyDisplayName(metadata?.teams.red)||'红方'}  ${Math.floor(frame.teams.red.score)}`,470,44);c.textAlign='right';c.fillStyle='#83c5e9';c.fillText(`${Math.floor(frame.teams.blue.score)}  ${strategyDisplayName(metadata?.teams.blue)||'蓝方'}`,1490,44);c.textAlign='center';c.fillStyle='#edf2f5';c.font='32px monospace';c.fillText(clock(frame.remaining),960,44);c.font='16px sans-serif';c.fillStyle='#9cabb6';c.fillText(`RUST ENGINE · SEED ${frame.seed} · ${frame.arena.name.toUpperCase()} · ${frame.status==='finished'?(frame.winner?.toUpperCase()||'DRAW')+' / MATCH COMPLETE':`${frame.robots.filter(r=>r.team==='red').length}v${frame.robots.filter(r=>r.team==='blue').length} / RMUC ${frame.season||(frame.arena.name==='rmuc2027'?'2027':'2026')}`}`,960,1056);
    c.font='15px sans-serif';c.textAlign='left';c.fillStyle='#ca9f96';c.fillText(`基地 ${Math.ceil(frame.bases.red.hp)} / ${frame.bases.red.max_hp}   前哨 ${Math.ceil(frame.outposts?.red.hp||0)} / ${frame.outposts?.red.max_hp||1500}`,470,74);c.textAlign='right';c.fillStyle='#8ebacf';c.fillText(`基地 ${Math.ceil(frame.bases.blue.hp)} / ${frame.bases.blue.max_hp}   前哨 ${Math.ceil(frame.outposts?.blue.hp||0)} / ${frame.outposts?.blue.max_hp||1500}`,1490,74);
    // RMUC 2027 ranks timeouts by cumulative control degree, so the export carries it under the clock like the live HUD.
    if((frame.season||(frame.arena.name==='rmuc2027'?'2027':'2026'))==='2027'){c.textAlign='center';c.fillStyle='#9cabb6';c.fillText('控制度',960,74);c.font='bold 18px sans-serif';c.textAlign='right';c.fillStyle='#e78e7e';c.fillText(String(Math.floor(frame.teams.red.control??0)),922,74);c.textAlign='left';c.fillStyle='#83c5e9';c.fillText(String(Math.floor(frame.teams.blue.control??0)),998,74);}
    for(const [side,team] of [[0,'red'],[1,'blue']] as const){let i=0;for(const r of frame.robots.filter(r=>r.team===team)){const x=side?1800:18,y=138+i++*47;c.fillStyle='#0f181ece';c.fillRect(x,y,102,37);c.textAlign='left';c.font='13px sans-serif';c.fillStyle=side?'#83c5e9':'#e78e7e';c.fillText(`${side?'B':'R'}${r.slot}  ${r.role==='aerial'?(r.support_active?'AIR':'PAD'):r.alive?Math.ceil(r.hp):'OUT'}`,x+8,y+12);c.fillRect(x+8,y+25,86*(r.max_hp>0?r.hp/r.max_hp:r.support_active?1:0),3);c.fillStyle='#ddba76';c.fillRect(x+8,y+31,86*(r.max_heat>0?r.heat/r.max_heat:0),2);}}
    if(this.announcement&&!this.overlay)this.drawAnnouncement(this.announcement,frame);
    const o=this.overlay;if(o){c.save();c.textAlign='center';c.textBaseline='middle';
      if(o.kind==='countdown'){c.fillStyle='rgba(0,0,0,.35)';c.fillRect(0,90,1920,940);c.font='italic 900 360px sans-serif';c.shadowColor='#a77bff';c.shadowBlur=60;c.fillStyle='#fff';c.fillText(o.n>0?String(o.n):'比赛开始',960,540);}
      else if(o.kind==='title'){const g=c.createRadialGradient(960,540,80,960,540,900);g.addColorStop(0,o.color+'aa');g.addColorStop(1,'rgba(0,0,0,.75)');c.fillStyle=g;c.fillRect(0,90,1920,940);c.font='italic 900 150px sans-serif';c.shadowColor=o.color;c.shadowBlur=40;c.fillStyle='#fff';c.fillText(o.title,960,500);c.shadowBlur=0;c.font='bold 44px sans-serif';c.fillText(o.sub,960,640);}
      else if(o.kind==='intro'){
        c.fillStyle='#07111cce';c.fillRect(160,690,1600,300);c.fillStyle='#e9bd78';c.font='bold 48px sans-serif';c.fillText(o.title,960,745);c.fillStyle='#e5edf4';c.font='28px sans-serif';c.fillText(o.sub,960,800);
        c.font='22px sans-serif';o.lines.slice(0,3).forEach((line,i)=>c.fillText(line,960,855+i*38));
      }else if(o.kind==='results'){
        c.fillStyle='#08131bf5';c.fillRect(130,115,1660,890);c.fillStyle='#e9bd78';c.font='bold 46px sans-serif';c.fillText('赛后数据面板',960,170);c.fillStyle='#dbe7f0';c.font='25px sans-serif';c.fillText(o.headline,960,222);
        o.rows.forEach((row,i)=>{const y=285+i*58;c.fillStyle=i%2?'#142330':'#10202b';c.fillRect(200,y-24,1520,50);c.textAlign='center';c.font='23px sans-serif';c.fillStyle='#adbfcd';c.fillText(row.label,960,y);c.fillStyle='#f4a294';c.fillText(row.red,480,y);c.fillStyle='#8ecff2';c.fillText(row.blue,1440,y);});
      }else if(o.kind==='mvp'){
        c.fillStyle='#08131bf2';c.fillRect(160,150,1600,820);c.fillStyle='#e9bd78';c.font='italic bold 90px sans-serif';c.fillText('MVP',960,255);c.fillStyle='#e6eff5';c.font='bold 42px sans-serif';c.fillText(o.name,960,355);c.font='28px sans-serif';c.fillText(o.team,960,415);
        if(o.image){let img=this.overlayImages.get(o.image);if(!img){img=new Image();img.src=o.image;this.overlayImages.set(o.image,img);}if(img.complete&&img.naturalWidth)c.drawImage(img,210,420,560,500);}
        c.font='32px sans-serif';o.lines.forEach((line,i)=>c.fillText(line,o.image?1210:960,540+i*72));
      }
      c.restore();}
  }
  private drawAnnouncement(h:KillHighlight,frame:Frame){
    const c=this.ctx,cue=KILL_CUES[h.cue],color=h.cue==='aced'?'#ffe2a0':h.team==='red'?'#ff7064':'#69bfff';
    const enter=Math.min(1,h.age/220),leave=Math.min(1,(h.life-h.age)/300),r=frame.robots.find(robot=>robot.id===h.killer);
    if(h.cue!=='aced'){
      c.save();c.globalAlpha=Math.max(0,Math.min(enter,leave));c.translate(1560+5*(1-enter),102);c.fillStyle='#08111ade';c.fillRect(0,0,330,32);c.fillStyle=color;c.fillRect(0,0,3,32);
      c.textAlign='left';c.textBaseline='middle';c.font='700 20px sans-serif';c.fillText(cue.title,12,16);c.textAlign='right';c.fillStyle='#bdcbd8';c.font='16px sans-serif';c.fillText(`${h.team==='red'?'红':'蓝'}方 ${r?.slot??'?'}号`,318,16);c.restore();return;
    }
    c.save();c.globalAlpha=Math.max(0,Math.min(enter,leave));c.translate(960,410);c.scale(.83+.17*(1-Math.pow(1-enter,3)),.83+.17*(1-Math.pow(1-enter,3)));
    const glow=c.createRadialGradient(0,0,30,0,0,380);glow.addColorStop(0,color+'55');glow.addColorStop(1,color+'00');c.fillStyle=glow;c.fillRect(-400,-190,800,380);
    c.fillStyle='#08111aee';c.fillRect(-320,-98,640,196);c.strokeStyle=color;c.lineWidth=2;c.beginPath();c.moveTo(-320,-98);c.lineTo(320,-98);c.moveTo(-320,98);c.lineTo(320,98);c.stroke();
    c.shadowColor=color;c.shadowBlur=24;c.fillStyle=color;c.textAlign='center';c.textBaseline='middle';c.font='800 22px sans-serif';c.fillText(cue.subtitle,0,-62);
    c.fillStyle='#fff';c.font='italic 900 76px sans-serif';c.fillText(cue.title,0,-5);c.shadowBlur=0;c.fillStyle='#cbd8e5';c.font='22px sans-serif';
    c.fillText(h.cue==='aced'?`${h.team==='red'?'蓝':'红'}方地面机器人全部阵亡`:`${h.team==='red'?'红':'蓝'}方 ${r?.slot??'?'}号 · ${r?.design_name||r?.role||''}`,0,62);
    c.fillStyle=color;c.fillRect(-320,98,640*Math.max(0,1-h.age/h.life),3);
    if(h.age<850){c.globalAlpha*=1-h.age/850;for(let i=0;i<12;i++){const angle=i*Math.PI/6,distance=100+h.age*.2;c.save();c.rotate(angle);c.fillRect(-2,-distance,4,16);c.restore();}}
    c.restore();
  }
}
