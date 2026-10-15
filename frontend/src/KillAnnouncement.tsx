import {useEffect,useRef,useState,type CSSProperties} from 'react';
import {createPortal} from 'react-dom';
import type {BroadcastDirector} from './broadcast';
import {KILL_CUES,type KillHighlight} from './killAnnouncements';
import type {Frame} from './types';
import {ROLE_NAMES} from './types';
import './killAnnouncement.css';

export function KillAnnouncement({director,frame,images,paused}:{director:BroadcastDirector;frame:Frame;images:Record<string,string>;paused:boolean}){
  const [highlight,setHighlight]=useState<KillHighlight|null>(null),pausedRef=useRef(paused);pausedRef.current=paused;
  useEffect(()=>{
    let id:number,last=performance.now();
    const animate=(now:number)=>{director.advanceHighlight(Math.min(100,now-last),pausedRef.current);last=now;
      const current=director.highlight;setHighlight(previous=>previous?.key===current?.key?previous:current);id=requestAnimationFrame(animate);};
    id=requestAnimationFrame(animate);return()=>cancelAnimationFrame(id);
  },[director]);
  if(!highlight)return null;
  const cue=KILL_CUES[highlight.cue],killer=frame.robots.find(r=>r.id===highlight.killer),image=killer?images[`${killer.model_asset}|${killer.team}`]:undefined;
  const name=killer?`${highlight.team==='red'?'红':'蓝'}方 ${killer.slot}号 · ${ROLE_NAMES[killer.role]}`:highlight.killer;
  const style={'--kill-life':`${highlight.life}ms`,'--kill-rank':cue.rank,animationPlayState:paused?'paused':'running'} as CSSProperties;
  if(highlight.cue!=='aced'){
    const host=document.querySelector('#viewport .bc-killfeed');if(!host)return null;
    return createPortal(<div className={`kill-announcement compact ${highlight.team} ${paused?'paused':''}`} style={style} data-kill-announcement={highlight.cue} role="status" aria-live="polite" aria-label={`${cue.title}，${name}`}>
      <span className="kill-compact-icon" aria-hidden>{image?<img src={image} alt=""/>:<b>{highlight.team==='red'?'R':'B'}{killer?.slot||''}</b>}</span>
      <strong>{cue.title}</strong><span className="kill-compact-player">{highlight.team==='red'?'红':'蓝'}方 {killer?.slot}号</span>
    </div>,host,highlight.key);
  }
  return <div key={highlight.key} className={`kill-announcement ${highlight.team} rank-${cue.rank} ${highlight.cue} ${paused?'paused':''}`} style={style} data-kill-announcement={highlight.cue} role="status" aria-live="polite" aria-label={`${cue.title}，${name}`}>
    <div className="kill-impact"/><div className="kill-sweep"/>
    <div className="kill-rays" aria-hidden>{Array.from({length:12},(_,i)=><i key={i} style={{'--ray':i} as CSSProperties}/>)}</div>
    <div className="kill-wing left"/><div className="kill-wing right"/>
    <div className="kill-medal" aria-hidden><svg viewBox="0 0 100 100"><path d="M50 2 90 25v50L50 98 10 75V25Z"/><path d="M50 10 83 29v42L50 90 17 71V29Z"/></svg>{image?<img src={image} alt=""/>:<b>{highlight.team==='red'?'R':'B'}{killer?.slot||''}</b>}<span>{highlight.cue==='aced'?'✦':cue.rank}</span></div>
    <div className="kill-copy"><small>{cue.subtitle}</small><strong>{cue.title}</strong><span>{highlight.cue==='aced'?`${highlight.team==='red'?'蓝':'红'}方地面机器人全部阵亡`:name}</span>
      <div className="kill-marks" aria-hidden>{Array.from({length:Math.min(5,cue.rank)},(_,i)=><i key={i} style={{'--mark':i} as CSSProperties}>◆</i>)}</div>
    </div>
    <div className="kill-progress"/>
  </div>;
}
