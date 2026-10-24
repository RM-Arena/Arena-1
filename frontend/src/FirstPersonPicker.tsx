import {useEffect,useRef,useState} from 'react';
import {ScanEye,X} from 'lucide-react';
import type {Drone,Frame,TeamId} from './types';
import {TEAM_LABEL,TEAMS,robotName} from './matchStats';

// A first-person target: a robot, or one drone of a 2027 aerial system (its hangar has no view of its own).
export interface PovOption{id:string;robot:string;team:TeamId;slot:number;short:string;label:string;detail:string;down:boolean;gun:boolean;drone?:Drone['state']}
const DRONE_STATE={docked:'机库待命',flying:'飞行中',down:'坠落',disabled:'失效'} as const;

export function povOptions(frame:Frame):PovOption[]{
  return frame.robots.flatMap(r=>r.drones?.length
    ?r.drones.map((d,k)=>({id:d.id,robot:r.id,team:r.team,slot:r.slot,short:`${r.team==='red'?'R':'B'}${r.slot}·${k+1}`,label:`空中机器人 ${k+1}`,detail:DRONE_STATE[d.state],down:d.state==='down'||d.state==='disabled',gun:false,drone:d.state}))
    :[{id:r.id,robot:r.id,team:r.team,slot:r.slot,short:`${r.team==='red'?'R':'B'}${r.slot}`,label:robotName(r),detail:r.role==='aerial'?(r.support_active?'空中支援':'停机待命'):r.alive?`${Math.ceil(r.hp)} HP`:'阵亡',down:r.role!=='aerial'&&!r.alive,
      gun:r.role!=='engineer'&&(r.role!=='heavy'||r.launcher==='fitted'||r.launcher==='installed')}]);
}

export function FirstPersonPicker({frame,active,target,onEnter,onExit}:{frame:Frame;active:boolean;target:string;onEnter:(option:PovOption)=>void;onExit:()=>void}){
  const [open,setOpen]=useState(false),root=useRef<HTMLDivElement>(null);
  useEffect(()=>{if(!open)return;
    const away=(e:PointerEvent)=>{if(!root.current?.contains(e.target as Node))setOpen(false);},key=(e:KeyboardEvent)=>{if(e.key==='Escape')setOpen(false);};
    document.addEventListener('pointerdown',away);document.addEventListener('keydown',key);
    return()=>{document.removeEventListener('pointerdown',away);document.removeEventListener('keydown',key);};},[open]);
  const options=povOptions(frame),current=active?options.find(o=>o.id===target):undefined;
  return <div ref={root} className={`pov-picker ${open?'open':''}`}>
    <button className={`pov-fab ${active?'active':''}`} title="第一视角" aria-label="第一视角" aria-haspopup="menu" aria-expanded={open} data-sound="open" onClick={()=>setOpen(v=>!v)}>
      <ScanEye size={18}/><span>{current?current.short:'第一视角'}</span>
    </button>
    {open&&<div className="pov-menu" role="menu" aria-label="选择第一视角机器人">
      <header><strong>第一视角</strong><small>选择一台机器人</small>{active&&<button className="pov-exit" data-sound="back" onClick={()=>{onExit();setOpen(false);}}><X size={12}/>退出</button>}</header>
      {TEAMS.map(team=><section key={team} className={`pov-team ${team}`}><h4>{TEAM_LABEL[team]}</h4>
        {frame.robots.filter(r=>r.team===team).sort((a,b)=>a.slot-b.slot).map(r=>{const own=options.filter(o=>o.robot===r.id),pick=(o:PovOption)=>{onEnter(o);setOpen(false);};
          // An aerial system lists its drones as one row of chips instead of a card each.
          if(r.drones?.length)return <div key={r.id} className="pov-fleet"><b>{r.slot}</b><span>空中机器人</span><div>{own.map((o,k)=><button key={o.id} role="menuitemradio" aria-checked={active&&o.id===target} title={`${o.label} · ${o.detail}`} aria-label={`${o.label} · ${o.detail}`} className={`pov-drone ${o.drone} ${active&&o.id===target?'current':''}`} data-sound="select" onClick={()=>pick(o)}>{k+1}</button>)}</div></div>;
          return own.map(o=><button key={o.id} role="menuitemradio" aria-checked={active&&o.id===target} className={`pov-option ${active&&o.id===target?'current':''} ${o.down?'down':''}`} data-sound="select" onClick={()=>pick(o)}>
            <b>{o.slot}</b><span>{o.label}</span><small>{o.detail}</small>
          </button>);})}
      </section>)}
    </div>}
  </div>;
}

// What the onboard camera shows on top of the scene: a reticle for gun-carrying robots and whose view this is.
export function PovOverlay({frame,target}:{frame:Frame;target:string}){
  const option=povOptions(frame).find(o=>o.id===target);if(!option)return null;
  return <div className={`pov-overlay ${option.team}`} aria-hidden>
    {option.gun&&!option.down&&<div className="pov-reticle"><i/><i/><i/><i/></div>}
    {option.down&&<div className="pov-down">{option.detail}</div>}
  </div>;
}
