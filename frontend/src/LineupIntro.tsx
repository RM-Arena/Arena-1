import {strategyName} from './strategyIdentity';
import {useEffect,useMemo,useRef,useState,type CSSProperties} from 'react';
import type {Frame,Metadata,Robot,RobotHardware,Standing,TeamId} from './types';
import {MODE_LABELS,ROLE_NAMES,frameSeason} from './types';
import {TEAM_LABEL,TEAMS,robotName} from './matchStats';
import {Stage,TeamCrest,teamName} from './broadcast';
import {AgentBadge,AgentLogo} from './agentLogos';
import {PROVIDERS,agentLabel,providerOf,robotAgent,teamAgents,type RobotAgent} from './agents';
import {introAt,introSchedule,type IntroCut} from './intro';
import './intro.css';

const CHASSIS:Record<string,string>={mecanum:'麦克纳姆轮',swerve:'舵轮',omni:'全向轮',wheel_legged:'双轮足',quadrotor:'多旋翼',legged:'串联腿'};
const CHECKS=['选手端连接','裁判系统模块','场地道具','机器人满血重置'];
const record=(standings:Standing[],m:Metadata|null,team:TeamId)=>{const t=m?.teams[team];return t?standings.find(s=>s.name===t.name&&s.version===t.version):undefined;};
const shownName=(m:Metadata|null,team:TeamId)=>teamName(m,team);
// The public catalog (with level-one referee stats) when available, else the frame's own hardware table.
const hardware=(f:Frame,r:Robot,models?:Record<string,RobotHardware>)=>models?.[String(r.model_slot??r.slot)]??f.robot_models?.[String(r.model_slot??r.slot)];


function useCount(target:number,ms:number,delay:number){
  const [value,setValue]=useState(0);
  useEffect(()=>{let id=0;const start=performance.now()+delay;const step=(now:number)=>{const u=Math.max(0,Math.min(1,(now-start)/ms));setValue(target*(1-Math.pow(1-u,3)));if(u<1)id=requestAnimationFrame(step);};id=requestAnimationFrame(step);return()=>cancelAnimationFrame(id);},[target,ms,delay]);
  return value;
}
function Stat({label,value,max,unit,digits=0,index,text}:{label:string;value:number;max:number;unit?:string;digits?:number;index:number;text?:string}){
  const shown=useCount(value,700,180+index*90);
  return <div className="li-stat" style={{'--i':index,'--fill':`${Math.max(4,Math.min(100,value/Math.max(1e-6,max)*100))}%`} as CSSProperties}><span>{label}</span><div><i/></div><b>{text??shown.toFixed(digits)}{unit&&!text&&<small>{unit}</small>}</b></div>;
}

function AgentCard({agent,team,label='策略生成'}:{agent:RobotAgent|null;team:TeamId;label?:string}){
  const provider=providerOf(agent),info=PROVIDERS[provider];
  return <div className={`li-agent ${team}`} style={{'--brand':info.color} as CSSProperties}>
    <div className="li-agent-ring"><AgentBadge provider={provider} size={190} ring={info.color}/><i/><i/></div>
    <span className="li-agent-label">{label} · AGENT</span>
    <strong>{agentLabel(agent)}</strong><small>{agent?.model?(info.maker===info.name?info.name:`${info.maker} · ${info.name}`):info.maker}</small>
    {agent?.strategy&&<em>策略 · {strategyName(agent.strategy)}</em>}
  </div>;
}

function RobotShot({frame,metadata,r,index,count,length,ranges,models}:{frame:Frame;metadata:Metadata|null;r:Robot;index:number;count:number;length:number;ranges:Record<string,number>;models?:Record<string,RobotHardware>}){
  const hw=hardware(frame,r,models),agent=robotAgent(metadata,r.team,r.slot),air=r.role==='aerial',stats=hw?.initial_stats;
  const caps=hw?.capabilities as Record<string,unknown>|undefined,chips=[hw?CHASSIS[hw.chassis_type]||hw.chassis_type:null,caps?.jump?'跳跃':null,caps?.transformation?'变形':null,caps?.tunnel?'过隧道':null,caps?.self_righting?'自扶正':null,caps?.deployment?'部署':null,Number(caps?.arms)>1?'双臂':Number(caps?.arms)===1?'机械臂':null].filter(Boolean) as string[];
  const lines=[
    {label:'生命值',value:air?0:r.max_hp,max:ranges.hp,text:air?'空中支援':undefined},
    {label:'底盘功率',value:r.power_limit||stats?.power_w||0,max:ranges.power,unit:' W'},
    {label:'热量上限',value:r.max_heat||0,max:ranges.heat,text:r.max_heat?undefined:'无发射'},
    {label:'单发伤害',value:stats?.damage||0,max:ranges.damage,text:stats?.damage?`${stats.damage} · ${stats.damage>=100?'42mm':'17mm'}`:'—'},
    {label:'机动速度',value:hw?.speed_reference_mps||0,max:ranges.speed,unit:' m/s',digits:1},
    {label:'整机质量',value:r.mass_kg||hw?.mass_kg||0,max:ranges.mass,unit:' kg',digits:1},
  ];
  return <div className={`li-shot ${r.team}`} style={{'--len':`${length}s`} as CSSProperties}>
    <div className="li-flash"/><div className="li-sweep"/>
    <div className="li-reticle"><i/><i/><i/><i/><b/></div>
    <div className="li-spec">
      <div className="li-number">{String(r.slot).padStart(2,'0')}</div>
      <div className="li-id"><span>{TEAM_LABEL[r.team]} · {ROLE_NAMES[r.role]}</span><h3>{hw?.name||r.design_name||robotName(r)}</h3><small>{r.model_slot??r.slot} 型 · {hw?.focus||r.design_focus||''}</small></div>
      <div className="li-stats">{lines.map((l,i)=><Stat key={l.label} index={i} {...l}/>)}</div>
      <div className="li-chips">{chips.map((c,i)=><span key={c} style={{'--i':i} as CSSProperties}>{c}</span>)}</div>
    </div>
    <AgentCard agent={agent} team={r.team}/>
    <div className="li-pips"><span>{TEAM_LABEL[r.team]}阵容</span>{Array.from({length:count},(_,i)=><i key={i} className={i<index?'done':i===index?'now':''}/>)}<b>{index+1}<small>/{count}</small></b></div>
  </div>;
}

function TeamCard({frame,metadata,team,images}:{frame:Frame;metadata:Metadata|null;team:TeamId;images:Record<string,string>}){
  const robots=frame.robots.filter(r=>r.team===team).sort((a,b)=>a.slot-b.slot),agents=teamAgents(metadata,team),count=(a:RobotAgent)=>robots.filter(r=>{const x=robotAgent(metadata,team,r.slot);return providerOf(x)===providerOf(a)&&(x?.model||'')===(a.model||'');}).length;
  return <div className={`li-team ${team}`}>
    <div className="li-slash"/><div className="li-slash two"/>
    <div className="li-team-word">{team==='red'?'RED':'BLUE'}</div>
    <div className="li-team-body">
      <div className="li-team-crest"><TeamCrest metadata={metadata} team={team} size={250}/></div>
      <div><span className="li-kicker">{TEAM_LABEL[team]} · {metadata?MODE_LABELS[metadata.teams[team].mode]:''} · {robots.length} 台机器人</span><h2>{shownName(metadata,team)}</h2>
        <div className="li-team-agents">{agents.length?agents.map((a,i)=><span key={i} style={{'--i':i,'--brand':PROVIDERS[providerOf(a)].color} as CSSProperties}><AgentLogo provider={providerOf(a)} size={34}/><b>{agentLabel(a)}</b>{agents.length>1&&<small>×{count(a)}</small>}</span>):<span><b>未标注策略来源</b></span>}</div></div>
    </div>
    <div className="li-team-strip">{robots.map((r,i)=><span key={r.id} style={{'--i':i} as CSSProperties}>{images[`${r.model_asset}|${team}`]&&<img src={images[`${r.model_asset}|${team}`]} alt=""/>}<b>{r.slot}</b></span>)}</div>
  </div>;
}

function Opening({frame,metadata,standings,free}:{frame:Frame;metadata:Metadata|null;standings:Standing[];free:boolean}){
  const count=(t:TeamId)=>frame.robots.filter(r=>r.team===t).length;
  return <div className="li-open">
    <div className="li-open-bg red"/><div className="li-open-bg blue"/><div className="li-open-grid"/>
    <svg className="li-open-bolt" viewBox="0 0 1920 1080" preserveAspectRatio="none" aria-hidden><polyline points="960,0 900,300 1010,420 930,640 1040,760 960,1080"/></svg>
    <div className="li-open-title"><span>RMUC {frameSeason(frame)} · ROBOT STRATEGY LEAGUE</span><h1>{free?'自由对战':'RM 对战'}</h1><small>{free?`${count('red')} V ${count('blue')} · 阵容由 Agent 决定`:`标准 ${count('red')} V ${count('blue')} · 镜像阵容`}</small></div>
    {TEAMS.map(team=>{const s=record(standings,metadata,team),agents=teamAgents(metadata,team);return <div key={team} className={`li-open-team ${team}`}>
      <TeamCrest metadata={metadata} team={team} size={210}/>
      <h2>{shownName(metadata,team)}</h2>
      <p>{agents.length===1?agentLabel(agents[0]):agents.length>1?`${agents.length} 个 Agent 联合`:metadata?MODE_LABELS[metadata.teams[team].mode]:''}</p>
      <div className="li-open-rate">{s&&s.games?<><b>{Math.round(s.wins/s.games*100)}<i>%</i></b><span>Elo {Math.round(s.rating)} · {s.wins}胜 {s.losses}负 {s.draws}平</span></>:<><b className="new">NEW</b><span>首次登场</span></>}</div>
    </div>;})}
    <div className="li-open-vs">VS</div>
  </div>;
}

function Faceoff({frame,metadata,images,progress}:{frame:Frame;metadata:Metadata|null;images:Record<string,string>;progress:number}){
  return <div className="li-face">
    <div className="li-face-shade"/>
    {TEAMS.map(team=>{const robots=frame.robots.filter(r=>r.team===team).sort((a,b)=>a.slot-b.slot);return <div key={team} className={`li-face-team ${team}`}>
      <div className="li-face-head"><TeamCrest metadata={metadata} team={team} size={96}/><div><span>{TEAM_LABEL[team]}</span><h3>{shownName(metadata,team)}</h3></div></div>
      <div className={`li-face-grid n${Math.min(4,Math.ceil(robots.length/4))}`}>{robots.map((r,i)=>{const a=robotAgent(metadata,team,r.slot);return <div key={r.id} className="li-face-bot" style={{'--i':i} as CSSProperties}>
        <span className="li-face-art">{images[`${r.model_asset}|${team}`]&&<img src={images[`${r.model_asset}|${team}`]} alt=""/>}</span>
        <span className="li-face-agent" title={agentLabel(a)}><AgentLogo provider={providerOf(a)} size={22}/></span><b>{r.slot}</b><small>{ROLE_NAMES[r.role]}</small></div>;})}</div>
    </div>;})}
    <div className="li-face-vs">VS</div>
    <div className="li-face-check"><ul>{CHECKS.map((c,i)=><li key={c} className={progress>(i+1)/(CHECKS.length+1.5)?'ok':''}>{c}</li>)}</ul><strong className={progress>.82?'ready':''}>{progress>.82?'自检完成 · READY':'裁判系统自检中'}</strong></div>
  </div>;
}

// Stat-bar ceilings for a robot shot: the whole lineup and the public catalog, so a bar compares this
// chassis with the rest of the field instead of being scaled to itself.
export function robotShotRanges(frame:Frame,models?:Record<string,RobotHardware>){
  const list=Object.values(models||{}) as RobotHardware[];
  const max=(f:(m:RobotHardware)=>number,floor:number)=>Math.max(floor,...list.map(f),...frame.robots.map(r=>f(hardware(frame,r,models)||({} as RobotHardware))||0));
  return {hp:Math.max(1,...frame.robots.map(r=>r.max_hp||0),...list.map(m=>m.initial_stats?.hp||0)),power:max(m=>m.initial_stats?.power_w||0,1),heat:max(m=>m.initial_stats?.max_heat||0,1),damage:max(m=>m.initial_stats?.damage||0,1),speed:max(m=>m.speed_reference_mps||0,1),mass:max(m=>m.mass_kg||0,1)};
}

// Chassis choice reuses the lineup intro's robot shot verbatim — the flash, the sweep, the reticle,
// the animated stat bars, the chassis chips, the agent card and the lineup pips — so hovering a
// chassis in the picker reads exactly like its cut in the pre-match sequence.
export function RobotPickShot({frame,metadata,r,models,index=0,count=1}:{frame:Frame;metadata:Metadata|null;r:Robot;models?:Record<string,RobotHardware>;index?:number;count?:number}){
  const ranges=useMemo(()=>robotShotRanges(frame,models),[frame,models]);
  return <Stage className="cer-lineup pick-shot">
    <div className="li-bar top"/><div className="li-bar bottom"/>
    <div key={r.id} className="li-cut" style={{'--len':'9s'} as CSSProperties}>
      <RobotShot frame={frame} metadata={metadata} r={r} index={index} count={count} length={9} ranges={ranges} models={models}/>
    </div>
  </Stage>;
}

// Rule 6.4 self-check as a broadcast lineup intro: the camera visits every robot while overlays introduce it.
export function LineupIntro({frame,metadata,standings,images,models:catalog,duration,remaining,offset=0,free,paused,replay=false,onCut,onSkip,locked=false}:{locked?:boolean;frame:Frame;metadata:Metadata|null;standings:Standing[];images:Record<string,string>;models?:Record<string,RobotHardware>;duration:number;remaining:number;offset?:number;free:boolean;paused:boolean;replay?:boolean;onCut:(cut:IntroCut)=>void;onSkip:()=>void}){
  const cuts=useMemo(()=>introSchedule(frame.robots,Math.max(1,duration-offset)),[frame.robots.map(r=>r.id).join(),duration,offset]);// eslint-disable-line react-hooks/exhaustive-deps
  // `offset` is the self-check time already spent before the sequence was allowed to start (the
  // pilot picks a chassis first). It shifts this timeline so the cards and the 3D cuts stay in step,
  // and the schedule is scaled to `duration - offset` — the time left for it — so every card and
  // every robot shot still plays before the countdown takes the screen.
  const elapsed=Math.max(0,duration-remaining-offset),at=introAt(cuts,elapsed),models=catalog&&Object.keys(catalog).length?catalog:frame.robot_models;
  const ranges=useMemo(()=>{const list=Object.values(models||{}) as RobotHardware[];const max=(f:(m:RobotHardware)=>number,floor:number)=>Math.max(floor,...list.map(f),...frame.robots.map(r=>f(hardware(frame,r,models)||({} as RobotHardware))||0));
    return {hp:Math.max(1,...frame.robots.map(r=>r.max_hp||0),...list.map(m=>m.initial_stats?.hp||0)),power:max(m=>m.initial_stats?.power_w||0,1),heat:max(m=>m.initial_stats?.max_heat||0,1),damage:max(m=>m.initial_stats?.damage||0,1),speed:max(m=>m.speed_reference_mps||0,1),mass:max(m=>m.mass_kg||0,1)};},[models,frame]);
  const last=useRef('');
  useEffect(()=>{if(at&&at.cut.key!==last.current){last.current=at.cut.key;if(!paused)onCut(at.cut);}},[at?.cut.key,paused,onCut]);// eslint-disable-line react-hooks/exhaustive-deps
  if(!at)return null;
  const s=at.cut.segment,robot=s.kind==='robot'?frame.robots.find(r=>r.id===s.id):undefined;  return <Stage className={`cer-lineup ${paused?'paused':''} ${s.kind}`}>
    {(s.kind==='robot'||s.kind==='team')&&<><div className="li-bar top"/><div className="li-bar bottom"/></>}
    <div key={at.cut.key} className="li-cut" style={{'--len':`${at.length}s`} as CSSProperties}>
      {s.kind==='open'&&<Opening frame={frame} metadata={metadata} standings={standings} free={free}/>}
      {s.kind==='team'&&<TeamCard frame={frame} metadata={metadata} team={s.team} images={images}/>}
      {s.kind==='robot'&&robot&&<RobotShot frame={frame} metadata={metadata} r={robot} index={s.index} count={s.count} length={at.length} ranges={ranges} models={models}/>}
      {s.kind==='faceoff'&&<Faceoff frame={frame} metadata={metadata} images={images} progress={at.progress}/>}
    </div>
    <div className="li-bug"><i/>{replay?'REPLAY':'LIVE'} · 赛前自检<b>{Math.ceil(remaining)}s</b></div>
    <div className="li-progress">{cuts.map(c=><i key={c.key} className={`${c.segment.kind} ${'team' in c.segment?c.segment.team:''} ${c.end<=elapsed?'done':c.key===at.cut.key?'now':''}`} style={{flexGrow:c.end-c.start}}/>)}</div>
    <button className="cer-skip" disabled={locked} onClick={onSkip}>跳过</button>
  </Stage>;
}
