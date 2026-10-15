import type {Frame,MatchEvent,Robot,TeamId} from './types';
import {ROLE_NAMES} from './types';

export const TEAMS=['red','blue'] as const;
export const TEAM_LABEL:Record<TeamId,string>={red:'红方',blue:'蓝方'};
export const other=(team:TeamId):TeamId=>team==='red'?'blue':'red';
const teamOf=(id?:string):TeamId|null=>id?.startsWith('red')?'red':id?.startsWith('blue')?'blue':null;

export interface TeamTally{economy:number;assemblyEconomy:number;shots17:number;shots42:number;runes:{small:number;large:number};assemblies:number[];assemblyTimes:Record<number,number>;outpostsLost:number;levelMax:number}
const blank=():TeamTally=>({economy:0,assemblyEconomy:0,shots17:0,shots42:0,runes:{small:0,large:0},assemblies:[0,0,0,0],assemblyTimes:{},outpostsLost:0,levelMax:1});

// Everything the broadcast shows beyond a single frame: coins earned, shots by calibre, assembly records.
// Live play feeds frames and events as they arrive; replays are scanned once on load.
export class MatchStats{
  teams:Record<TeamId,TeamTally>={red:blank(),blue:blank()};
  shots=new Map<string,number>();levels=new Map<string,number>();revision=0;
  private seen=new Set<string>();private last:Frame|null=null;private starts:Partial<Record<TeamId,{difficulty:number;time:number}>>={};
  reset(){this.teams={red:blank(),blue:blank()};this.shots.clear();this.levels.clear();this.seen.clear();this.last=null;this.starts={};this.revision++;}
  frame(f:Frame){
    const last=this.last;if(last&&f.tick<last.tick)return;
    for(const team of TEAMS){
      const t=this.teams[team],now=f.teams[team],before=last?.teams[team];
      if(!before)t.economy+=Math.max(0,now.resources);else if(now.resources>before.resources)t.economy+=now.resources-before.resources;
      const a=(now as Record<string,number>).next_tech_income,b=(before as Record<string,number>|undefined)?.next_tech_income;
      if(b!==undefined&&b>0&&a>b+1e-6)t.assemblyEconomy+=(before as Record<string,number>).tech_income||0;
      if(last&&(last.outposts?.[team]?.hp??0)>0&&(f.outposts?.[team]?.hp??1)<=0)t.outpostsLost++;
    }
    for(const r of f.robots){if(r.level>(this.levels.get(r.id)||0))this.levels.set(r.id,r.level);const t=this.teams[r.team];t.levelMax=Math.max(t.levelMax,r.level);}
    this.last=f;this.revision++;
  }
  events(list:MatchEvent[]){
    for(const e of list){
      const key=e.id||`${e.tick}:${e.type}:${e.robot}:${e.x}`;if(this.seen.has(key))continue;this.seen.add(key);
      const team=(e.team as TeamId|undefined)||teamOf(e.robot);
      if(e.type==='shot'&&team){if(e.role==='hero')this.teams[team].shots42++;else this.teams[team].shots17++;this.shots.set(e.robot!,(this.shots.get(e.robot!)||0)+1);}
      else if(e.type==='rune_activated'&&team)this.teams[team].runes[(e as {mode?:string}).mode==='large'?'large':'small']++;
      else if(e.type==='assembly_start'&&team)this.starts[team]={difficulty:(e as {difficulty?:number}).difficulty||1,time:e.time??e.tick*.05};
      else if(e.type==='assembly_success'&&team){
        const d=(e as {difficulty?:number}).difficulty||1,start=this.starts[team],t=this.teams[team];t.assemblies[d-1]++;
        if(start?.difficulty===d){const spent=(e.time??e.tick*.05)-start.time;if(spent>0&&!(t.assemblyTimes[d]<=spent))t.assemblyTimes[d]=spent;}
      }
    }
    this.revision++;
  }
}

export function statsFromFrames(frames:Frame[]){const stats=new MatchStats();for(const f of frames){stats.frame(f);stats.events(f.events);}return stats;}

const finite=(v:number|undefined)=>Number.isFinite(v)?v!:0;
// Rule 5.8: base HP, then outpost HP / survival, then attack damage, then total remaining robot HP.
export function verdict(f:Frame):{headline:string;detail:string}{
  const w=f.winner,reason=f.reason||'timeout';
  if(reason==='base_destroyed')return {headline:'败方基地被摧毁',detail:`${w?TEAM_LABEL[w]:''}击毁敌方基地，提前结束比赛`};
  if(reason==='elimination')return {headline:'敌方机器人全部退场',detail:'一方无可战斗机器人'};
  if(reason==='forfeit')return {headline:'裁判判负',detail:'严重违规，判负方本局失利'};
  if(reason==='stopped')return {headline:'比赛手动结束',detail:'本局未计入排名'};
  const base=(t:TeamId)=>finite(f.bases[t]?.hp),op=(t:TeamId)=>f.outposts?.[t];
  if(Math.ceil(base('red'))!==Math.ceil(base('blue')))return {headline:'比赛时间耗尽',detail:'基地剩余血量高的一方获胜'};
  const broken=(t:TeamId)=>!!op(t)?.ever_destroyed;
  if(!broken('red')&&!broken('blue')&&Math.ceil(finite(op('red')?.hp))!==Math.ceil(finite(op('blue')?.hp)))return {headline:'比赛时间耗尽',detail:'基地血量相同，前哨站剩余血量高的一方获胜'};
  if(broken('red')!==broken('blue'))return {headline:'比赛时间耗尽',detail:'基地血量相同，前哨站未被击毁过的一方获胜'};
  const dmg=(t:TeamId)=>finite((f.teams[t] as {attack_damage?:number}).attack_damage??f.teams[t].score);
  if(Math.round(dmg('red'))!==Math.round(dmg('blue')))return {headline:'比赛时间耗尽',detail:'基地与前哨站相同，全队攻击伤害高的一方获胜'};
  if(w)return {headline:'比赛时间耗尽',detail:'全队总剩余血量高的一方获胜'};
  return {headline:'双方平局',detail:'所有判定条件均相同'};
}

export const robotName=(r:Robot)=>r.role==='infantry'?'步兵':r.role==='aerial'?'无人机':ROLE_NAMES[r.role];
export function nickname(r:Robot){const parts=(r.design_name||'').split(' ');return {code:parts.length>1?parts[0]:'',name:parts.slice(parts.length>1?1:0).join(' ')||robotName(r)};}

export interface MvpLine{label:string;value:string;unit?:string}
export interface Mvp{robot:Robot;score:number;lines:MvpLine[];note?:string}
export function mvp(f:Frame,stats:MatchStats):Mvp|null{
  const pool=f.robots.filter(r=>!f.winner||r.team===f.winner);if(!pool.length)return null;
  const score=(r:Robot)=>{const t=stats.teams[r.team];return r.damage+300*r.kills+(r.role==='engineer'?1.5*t.assemblyEconomy+300*t.assemblies.reduce((a,b)=>a+b,0):0);};
  const robot=pool.reduce((best,r)=>score(r)>score(best)?r:best,pool[0]),t=stats.teams[robot.team];
  if(robot.role==='engineer'){
    const done=t.assemblies.map((n,i)=>n?i+1:0).filter(Boolean),top=done.length?Math.max(...done):0,fastest=t.assemblyTimes[top];
    return {robot,score:score(robot),lines:[{label:'装配获得经济',value:String(Math.round(t.assemblyEconomy))},{label:'成功装配次数',value:t.assemblies.join('/')},{label:'最高装配难度',value:top?`Lv.${top}`:'—'},{label:top?`${['一','二','三','四'][top-1]}级装配耗时`:'装配耗时',value:fastest?fastest.toFixed(1):'—',unit:fastest?'s':''}],note:'*成功装配次数：成功装配一级/二级/三级/四级难度的次数'};
  }
  const shots=stats.shots.get(robot.id)||0,calibre=robot.role==='hero'?'42mm':'17mm';
  return {robot,score:score(robot),lines:[{label:'总伤害',value:String(Math.round(robot.damage))},{label:'击毁机器人',value:String(robot.kills)},{label:`${calibre}弹丸发弹量`,value:String(shots)},{label:'最高等级',value:`Lv.${stats.levels.get(robot.id)||robot.level}`}],note:'*总伤害：本局对敌方机器人、前哨站与基地造成的攻击伤害'};
}
