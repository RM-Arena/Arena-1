import {useEffect,useMemo,useState,type CSSProperties} from 'react';
import type {Frame,Metadata,Robot,RobotHardware,Standing,TeamId} from './types';
import {MODE_LABELS} from './types';
import {TEAM_LABEL,TEAMS,nickname,robotName,verdict,type MatchStats,type Mvp} from './matchStats';
import {Stage,TeamCrest,teamName} from './broadcast';
import {LineupIntro} from './LineupIntro';
import type {IntroCut} from './intro';

const fmt=(n:number)=>Math.round(n).toLocaleString('en-US');

// ---------------------------------------------------------------- pre-match
// Rule 6.4 self-check, shown as the lineup intro, followed by the 6.5 five-second countdown.
export function Prematch({stage,remaining,duration,frame,metadata,standings,images,models,free,paused,replay,onCut,onSkip}:{stage:'self_check'|'countdown';remaining:number;duration:number;frame:Frame;metadata:Metadata|null;standings:Standing[];images:Record<string,string>;models?:Record<string,RobotHardware>;free:boolean;paused:boolean;replay?:boolean;onCut:(cut:IntroCut)=>void;onSkip:()=>void}){
  const n=Math.max(1,Math.ceil(remaining-1e-6));
  if(stage==='countdown')return <Stage className="cer-countdown"><div className="cd-shade"/>
    <svg key={'bolt'+n} className={`cd-bolt k${n%2}`} viewBox="0 0 1920 1080" preserveAspectRatio="none" aria-hidden><polyline points={bolt(n)}/><polyline className="core" points={bolt(n)}/></svg>
    <div key={n} className="cd-number">{n}</div><div className="cd-caption">比赛即将开始</div><button className="cer-skip" onClick={onSkip}>跳过</button></Stage>;
  return <LineupIntro frame={frame} metadata={metadata} standings={standings} images={images} models={models} duration={duration} remaining={remaining} free={free} paused={paused} replay={replay} onCut={onCut} onSkip={onSkip}/>;
}
function bolt(seed:number){let s=seed*9301+49297;const r=()=>{s=(s*9301+49297)%233280;return s/233280;};const pts:string[]=[];const vertical=seed%2===0;
  for(let i=0;i<=22;i++){const t=i/22;pts.push(vertical?`${960+(r()-.5)*180+(t-.5)*260},${t*1080}`:`${t*1920},${540+(r()-.5)*150+(t-.5)*-220}`);}return pts.join(' ');}

export function StartFlash(){return <Stage className="cer-start"><div className="start-flash"/><div className="start-text">比赛开始</div></Stage>;}

// ---------------------------------------------------------------- victory
// Shards converge into a hexagonal crystal, wings unfold and the winner title sweeps in, tinted in the winning colour.
export function Victory({frame}:{frame:Frame}){
  const w=frame.winner,c=w||'draw',title=w?`${TEAM_LABEL[w]}胜利`:'双方平局',{headline}=verdict(frame);
  const shards=useMemo(()=>Array.from({length:22},(_,i)=>({a:i/22*360+Math.random()*12,d:520+Math.random()*420,s:24+Math.random()*60,r:Math.random()*360,delay:Math.random()*.25})),[]);
  return <Stage className={`cer-victory ${c}`}>
    <div className="vic-tint"/><div className="vic-flash"/>
    <svg className="vic-bolts" viewBox="0 0 1920 1080" preserveAspectRatio="none" aria-hidden><polyline className="b1" points="0,260 300,330 520,300 760,420 900,470"/><polyline className="b2" points="1920,820 1620,760 1400,800 1150,640 1020,600"/></svg>
    <div className="vic-shards">{shards.map((s,i)=><i key={i} style={{'--a':`${s.a}deg`,'--d':`${s.d}px`,'--s':`${s.s}px`,'--r':`${s.r}deg`,'--delay':`${s.delay}s`} as CSSProperties}/>)}</div>
    <div className="vic-emblem">
      <svg viewBox="-260 -160 520 320" aria-hidden><defs>
        <linearGradient id="vic-face" x1="0" y1="-1" x2="0" y2="1"><stop offset="0" className="s0"/><stop offset="1" className="s1"/></linearGradient>
        <linearGradient id="vic-wing" x1="0" y1="0" x2="1" y2="0"><stop offset="0" className="w0"/><stop offset="1" className="w1"/></linearGradient></defs>
        <g className="vic-wings"><path className="wing l" d="M-70 -40 L-250 -88 L-220 -52 L-248 -40 L-205 -14 L-232 -2 L-150 22 L-70 10 Z"/><path className="wing r" d="M70 -40 L250 -88 L220 -52 L248 -40 L205 -14 L232 -2 L150 22 L70 10 Z"/></g>
        <g className="vic-hex"><polygon points="0,-128 108,-64 108,64 0,128 -108,64 -108,-64" className="hex-edge"/><polygon points="0,-112 94,-56 94,56 0,112 -94,56 -94,-56" fill="url(#vic-face)"/>
          <polygon points="0,-112 94,-56 0,0 -94,-56" className="hex-hi"/><path d="M-40 70 L-40 -62 L22 -62 Q56 -62 56 -26 Q56 6 24 10 L60 70 L30 70 L0 14 L-12 14 L-12 70 Z M-12 -36 L-12 -10 L18 -10 Q28 -10 28 -23 Q28 -36 18 -36 Z" className="hex-r"/></g>
      </svg>
    </div>
    <div className="vic-title"><span>{title}</span></div>
    <div className="vic-reason">{headline}</div>
  </Stage>;
}

// ---------------------------------------------------------------- results
function Diverge({label,red,blue,format=fmt}:{label:string;red:number;blue:number;format?:(n:number)=>string}){
  const total=Math.max(1,red+blue);
  return <div className="res-row"><b className="red">{format(red)}</b><div className="res-bar"><span>{label}</span><div><i className="red" style={{width:`${red/total*50}%`}}/><i className="blue" style={{width:`${blue/total*50}%`}}/></div></div><b className="blue">{format(blue)}</b></div>;
}
function Tile({icon,value,label}:{icon:string;value:string;label:string}){return <div className="res-tile"><span>{icon}</span><b>{value}</b><small>{label}</small></div>;}

export function Results({frame,metadata,stats,images,onMvp,onClose,auto}:{frame:Frame;metadata:Metadata|null;stats:MatchStats;images:Record<string,string>;onMvp:()=>void;onClose:()=>void;auto:boolean}){
  const v=verdict(frame),w=frame.winner,hero=(t:TeamId)=>frame.robots.find(r=>r.team===t&&r.role==='hero')||frame.robots.find(r=>r.team===t);
  const [left,setLeft]=useState(auto?10:0);
  useEffect(()=>{if(!auto)return;const id=window.setInterval(()=>setLeft(n=>Math.max(0,n-1)),1000);return()=>window.clearInterval(id);},[auto]);
  useEffect(()=>{if(auto&&left===0)onMvp();},[auto,left,onMvp]);
  const dmg=(t:TeamId)=>(frame.teams[t] as {attack_damage?:number}).attack_damage??frame.teams[t].score,maxAssembly=(t:TeamId)=>{const a=stats.teams[t].assemblies.map((n,i)=>n?i+1:0);return Math.max(0,...a);};
  return <Stage className="cer-results">
    <div className="res-bg red"/><div className="res-bg blue"/>
    {TEAMS.map(t=>{const r=hero(t),img=r&&images[`${r.model_asset}|${t}|showcase`];return img?<img key={t} className={`res-robot ${t}`} src={img} alt=""/>:null;})}
    {w&&<div className={`res-win ${w}`}>WIN</div>}
    <header className="res-head">{TEAMS.map(t=><div key={t} className={`res-team ${t}`}><div><h2>{teamName(metadata,t)}</h2><small>{metadata?MODE_LABELS[metadata.teams[t].mode]:''}</small></div><TeamCrest metadata={metadata} team={t} size={150}/></div>)}
      <div className="res-score"><b className="red">{w==='red'?1:0}</b><span>VS</span><b className="blue">{w==='blue'?1:0}</b></div></header>
    <section className="res-verdict"><h3>胜利判定条件</h3>
      <div className="res-structures">{TEAMS.map(t=>{const b=frame.bases[t],o=frame.outposts?.[t];return <div key={t} className={`res-struct ${t}`}>
        <div className="res-outpost"><small>前哨站</small><b>{o?Math.ceil(Math.max(0,o.hp)):'—'}</b><i style={{width:`${o?Math.max(0,o.hp)/o.max_hp*100:0}%`}}/></div>
        <div className="res-base"><small>基地</small><b>{Math.ceil(Math.max(0,b.hp))}</b><i style={{width:`${Math.max(0,b.hp)/b.max_hp*100}%`}}/></div></div>;})}
        <div className="res-reason"><b>{v.headline}</b><span>{v.detail}</span></div></div>
    </section>
    <section className="res-detail"><h3>详细数据</h3>
      <Diverge label="经济总量" red={stats.teams.red.economy} blue={stats.teams.blue.economy}/>
      <Diverge label="总伤害量" red={dmg('red')} blue={dmg('blue')}/>
      <Diverge label="击杀对手" red={frame.teams.red.kills} blue={frame.teams.blue.kills}/>
      <div className="res-row"><b className="red">{stats.teams.red.shots42}/{stats.teams.red.shots17}</b><div className="res-bar"><span>大/小弹丸数</span><div><i className="red" style={{width:`${(stats.teams.red.shots42*10+stats.teams.red.shots17)/Math.max(1,stats.teams.red.shots42*10+stats.teams.red.shots17+stats.teams.blue.shots42*10+stats.teams.blue.shots17)*50}%`}}/><i className="blue" style={{width:`${(stats.teams.blue.shots42*10+stats.teams.blue.shots17)/Math.max(1,stats.teams.red.shots42*10+stats.teams.red.shots17+stats.teams.blue.shots42*10+stats.teams.blue.shots17)*50}%`}}/></div></div><b className="blue">{stats.teams.blue.shots42}/{stats.teams.blue.shots17}</b></div>
    </section>
    {TEAMS.map(t=>{const s=stats.teams[t];return <aside key={t} className={`res-tiles ${t}`}>
      <Tile icon="✷" value={`大×${s.runes.large} 小×${s.runes.small}`} label="能量机关"/><Tile icon="⚙" value={maxAssembly(t)?`Lv.${maxAssembly(t)}`:'—'} label="最高装配"/>
      <Tile icon="▲" value={`Lv.${s.levelMax}`} label="最高等级"/><Tile icon="◆" value={`×${stats.teams[t==='red'?'blue':'red'].outpostsLost}`} label="击毁前哨站"/></aside>;})}
    <footer className="res-actions"><button onClick={onMvp}>MVP 结算{left>0?` · ${left}s`:''}</button><button onClick={onClose}>继续查看战场</button></footer>
  </Stage>;
}

// ---------------------------------------------------------------- MVP
export function MvpCard({mvp,metadata,image,onBack,onClose}:{mvp:Mvp;metadata:Metadata|null;image?:string;onBack:()=>void;onClose:()=>void}){
  const r:Robot=mvp.robot,team=r.team,{code,name}=nickname(r);
  return <Stage className={`cer-mvp ${team}`}>
    <div className="mvp-bg"/><div className="mvp-streak"/><div className="mvp-word">MVP</div>
    <div className="mvp-team"><TeamCrest metadata={metadata} team={team} size={260}/><h2>{teamName(metadata,team)}</h2><small>{metadata?`${MODE_LABELS[metadata.teams[team].mode]} · ${metadata.teams[team].version.slice(0,10)}`:''}</small></div>
    <div className="mvp-robot">{image&&<img src={image} alt=""/>}</div>
    <div className="mvp-panel">
      <div className="mvp-id"><em>{r.slot}</em><div><span>{name}</span><b>{robotName(r)}</b></div>{code&&<small>{code}</small>}</div>
      {mvp.lines.map(l=><div key={l.label} className="mvp-line"><span>{l.label}</span><b>{l.value}{l.unit&&<small>{l.unit}</small>}</b></div>)}
      {mvp.note&&<p>{mvp.note}</p>}
    </div>
    <footer className="res-actions"><button onClick={onBack}>返回数据面板</button><button onClick={onClose}>继续查看战场</button></footer>
  </Stage>;
}
