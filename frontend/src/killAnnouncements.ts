import type {Frame,MatchEvent,TeamId} from './types';

export type KillCue='first-blood'|'double-kill'|'triple-kill'|'quadra-kill'|'penta-kill'|'aced';
export const MULTI_KILL_WINDOW_S=10;
export const KILL_CUES:Record<KillCue,{title:string;subtitle:string;url:string;gain:number;rank:number}>={
  'first-blood':{title:'第一滴血',subtitle:'FIRST BLOOD',url:'/assets/audio/announcer/first-blood.mp3',gain:.9,rank:1},
  'double-kill':{title:'双杀',subtitle:'DOUBLE KILL',url:'/assets/audio/announcer/double-kill.mp3',gain:1.8,rank:2},
  'triple-kill':{title:'三杀',subtitle:'TRIPLE KILL',url:'/assets/audio/announcer/triple-kill.mp3',gain:1.,rank:3},
  'quadra-kill':{title:'四杀',subtitle:'QUADRA KILL',url:'/assets/audio/announcer/quadra-kill.mp3',gain:1.,rank:4},
  'penta-kill':{title:'五杀',subtitle:'PENTA KILL',url:'/assets/audio/announcer/penta-kill.mp3',gain:1.5,rank:5},
  aced:{title:'团灭',subtitle:'ACE',url:'/assets/audio/announcer/aced.mp3',gain:2.8,rank:6},
};
export interface KillAnnouncement {key:string;cue:KillCue;team:TeamId;killer:string;victim:string;at:number;count:number}
export interface KillHighlight extends KillAnnouncement {age:number;life:number}
const multi:Record<number,KillCue>={2:'double-kill',3:'triple-kill',4:'quadra-kill',5:'penta-kill'};

// Uses simulation timestamps, so playback speed never changes the multi-kill window.
export class KillAnnouncer {
  private ready=false;private firstBlood=false;private seen=new Set<string>();
  private alive=new Map<string,boolean>();private streaks=new Map<string,{at:number;count:number}>();
  private wiped=new Set<TeamId>();
  reset(){this.ready=false;this.firstBlood=false;this.seen.clear();this.alive.clear();this.streaks.clear();this.wiped.clear();}
  restore(frames:Frame[]){this.reset();for(const frame of frames)this.advance(frame,frame.events);}
  advance(frame:Frame,events:MatchEvent[]):KillAnnouncement[]{
    const robots=new Map(frame.robots.map(r=>[r.id,r]));
    const ground=frame.robots.filter(r=>r.role!=='aerial');
    const enemyKill=(e:MatchEvent)=>{const killer=robots.get(e.killer||''),victim=robots.get(e.robot||'');return e.type==='destroy'&&killer&&victim&&victim.role!=='aerial'&&killer.team!==victim.team;};
    if(!this.ready){
      for(const r of ground)this.alive.set(r.id,r.alive);
      // A newly joined snapshot may contain several deaths and respawns. Undo them
      // in reverse to recover the state before the first event in this batch.
      for(const e of [...events].reverse())if(this.alive.has(e.robot||'')){
        if(e.type==='destroy')this.alive.set(e.robot!,true);
        else if(e.type==='respawn')this.alive.set(e.robot!,false);
      }
      this.firstBlood=frame.robots.reduce((sum,r)=>sum+(r.kills||0),0)>events.filter(enemyKill).length;
      this.ready=true;
    }
    const result:KillAnnouncement[]=[];
    for(const e of events){
      if(e.type!=='destroy'&&e.type!=='respawn')continue;
      const key=e.id||`${e.tick}:${e.type}:${e.robot}:${e.killer}`;
      if(this.seen.has(key))continue;this.seen.add(key);
      const victim=robots.get(e.robot||'');if(!victim||victim.role==='aerial')continue;
      if(e.type==='respawn'){this.alive.set(victim.id,true);this.wiped.delete(victim.team);this.streaks.delete(victim.id);continue;}
      const wasAlive=this.alive.get(victim.id);this.alive.set(victim.id,false);this.streaks.delete(victim.id);
      if(!wasAlive)continue;const killer=robots.get(e.killer||''),credited=!!killer&&!!enemyKill(e);
      const at=e.time??e.tick*(frame.dt||.05),team:TeamId=credited?killer!.team:victim.team==='red'?'blue':'red';let count=0;
      const push=(cue:KillCue)=>result.push({key:`${key}:${cue}`,cue,team,killer:credited?killer!.id:'',victim:victim.id,at,count});
      if(credited){
        const previous=this.streaks.get(killer!.id);
        count=previous&&at>=previous.at&&at-previous.at<=MULTI_KILL_WINDOW_S?previous.count+1:1;
        this.streaks.set(killer!.id,{at,count});
        if(!this.firstBlood){this.firstBlood=true;push('first-blood');}
        if(multi[count])push(multi[count]);
      }
      const opponents=ground.filter(r=>r.team===victim.team);
      if(opponents.length&&!this.wiped.has(victim.team)&&opponents.every(r=>!this.alive.get(r.id))){this.wiped.add(victim.team);push('aced');}
    }
    // Referee removals and current roster flags still count toward ground survival.
    for(const r of ground){this.alive.set(r.id,r.alive);if(r.alive)this.wiped.delete(r.team);}
    return result;
  }
}
