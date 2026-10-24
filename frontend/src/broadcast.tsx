import {strategyDisplayName,strategyName} from './strategyIdentity';
import {useEffect,useLayoutEffect,useRef,useState,type ReactNode} from 'react';
import type {Frame,MatchEvent,Metadata,Robot,TeamId} from './types';
import {MODE_LABELS,baseProtected,frameSeason,outpostHolder} from './types';
import {TEAM_LABEL,TEAMS,other,robotName,type MatchStats} from './matchStats';
import {clock} from './media';
import {KillAnnouncer,type KillAnnouncement,type KillHighlight} from './killAnnouncements';
import {AgentBadge,AgentLogo} from './agentLogos';
import {PROVIDERS,agentLabel,providerOf,robotAgent,teamAgents,teamEmblem} from './agents';
import './broadcast.css';

// ---------------------------------------------------------------- director
// Turns frames and events into the transient broadcast call-outs: centre banners, bottom toasts and the kill feed.
export type Callout={key:string;kind:'banner'|'toast'|'kill';team:TeamId;at:number;life:number;title:string;detail?:string;chips?:string[];icon?:'assembly'|'rune'|'outpost'|'revive';killer?:string;victim?:string};
export class BroadcastDirector{
  items:Callout[]=[];private last:Frame|null=null;private seen=new Set<string>();private serial=0;
  highlight:KillHighlight|null=null;private kills=new KillAnnouncer();
  reset(){this.items=[];this.last=null;this.seen.clear();this.kills.reset();this.highlight=null;}
  restoreKills(frames:Frame[]){this.kills.restore(frames);this.highlight=null;}
  announce(announcement:KillAnnouncement,seconds:number){this.highlight={...announcement,key:`${announcement.key}-${this.serial++}`,age:0,life:seconds*1000};}
  advanceHighlight(milliseconds:number,paused:boolean){if(!this.highlight||paused)return;this.highlight.age+=milliseconds;if(this.highlight.age>=this.highlight.life)this.highlight=null;}
  private push(c:Omit<Callout,'key'|'at'>,delay=0){this.items.push({...c,key:`${c.kind}-${this.serial++}`,at:performance.now()+delay});if(this.items.length>24)this.items.splice(0,this.items.length-24);}
  active(kind:Callout['kind'],now=performance.now()){return this.items.filter(c=>c.kind===kind&&now>=c.at&&now<c.at+c.life);}
  frame(f:Frame){
    const last=this.last;this.last=f;if(!last||f.tick<=last.tick||f.status!=='running'&&f.status!=='finished')return;
    for(const team of TEAMS){
      const was=last.outposts?.[team],now=f.outposts?.[team];
      if(was&&now&&was.hp>0&&now.hp<=0){this.push({kind:'banner',team,life:2600,title:`${TEAM_LABEL[team]}前哨站被摧毁`});if(f.bases[team].hp>0)this.push({kind:'banner',team,life:2600,title:`${TEAM_LABEL[team]}基地无敌解除`},2700);}
      if(!last.bases[team].armor_open&&f.bases[team].armor_open)this.push({kind:'banner',team,life:2800,title:`${TEAM_LABEL[team]}基地护甲打开`});
      const cap=(t:Frame,k:TeamId)=>(t.teams[k] as {level_cap?:number}).level_cap||0;
      if(cap(f,team)>cap(last,team)&&cap(last,team)>0)this.push({kind:'banner',team,life:2600,title:`${TEAM_LABEL[team]}等级上限提高至${cap(f,team)}`},600);
    }
    if(last.remaining>60&&f.remaining<=60)this.push({kind:'banner',team:'red',life:3000,title:'比赛剩余 1 分钟'});
  }
  events(list:MatchEvent[],frame:Frame|null){
    const announcements=frame?this.kills.advance(frame,list):[];
    for(const e of list){
      const key=e.id||`${e.tick}:${e.type}:${e.robot}`;if(this.seen.has(key))continue;this.seen.add(key);
      const team=e.team as TeamId|undefined,payload=e as MatchEvent&Record<string,number|string|boolean|undefined>;
      if(e.type==='destroy'&&e.robot)this.push({kind:'kill',team:(e.killer?.startsWith('red')?'red':'blue'),life:5200,title:'摧毁',killer:e.killer,victim:e.robot});
      else if(e.type==='respawn'&&e.robot&&e.instant){const side=team||(e.robot.startsWith('red-')?'red':'blue');this.push({kind:'toast',team:side,life:4200,icon:'revive',title:`${TEAM_LABEL[side]} ${e.robot.split('-')[1]}号满血复活`,chips:[`花费 ${e.cost??'—'} 金币`,'3秒无敌']});}
      else if(e.type==='assembly_success'&&team){const d=Number(payload.difficulty)||1,cap=(frame?.teams[team] as {level_cap?:number}|undefined)?.level_cap;
        this.push({kind:'toast',team,life:4200,icon:'assembly',title:`${TEAM_LABEL[team]}工程成功装配 ${d} 级难度`,chips:[`+${Math.round(Number(payload.income_per_10s)||0)}/10s`,...(d>=3?[`防御 +${d===4?50:25}%`]:[]),...(cap?[`Lv.MAX ${cap}`]:[])]});}
      else if(e.type==='rune_activated'&&team){const large=payload.mode==='large',attack=Number(payload.attack)||1,defense=Number(payload.defense)||0,cooling=Number(payload.cooling)||1;
        this.push({kind:'toast',team,life:4200,icon:'rune',title:`${TEAM_LABEL[team]}成功激活${large?'大':'小'}能量机关！`,chips:[...(attack>1?[`攻击 ×${attack}`]:[]),...(defense>0?[`防御 +${Math.round(defense*100)}%`]:[]),...(cooling>1?[`冷却 ×${cooling}`]:[]),`${Math.round(Number(payload.duration)||0)}s`]});}
      else if(e.type==='rune_start'&&team)this.push({kind:'banner',team,life:2400,title:`${TEAM_LABEL[team]}${payload.mode==='large'?'大':'小'}能量机关正在激活`});
      else if(e.type==='outpost_rebuilt'&&team)this.push({kind:'toast',team,life:3600,icon:'outpost',title:`${TEAM_LABEL[team]}前哨站重建成功`,chips:[`血量 ${Math.round(Number(payload.hp)||750)}`,'基地恢复无敌']});
    }
    if(this.seen.size>8000)this.seen.clear();
    return announcements;
  }
}

// ---------------------------------------------------------------- scaling stage
// Lays the overlay out on a 1920-wide broadcast canvas and scales it into the viewport; narrow viewports get the compact variant.
// Full-screen ceremonies keep the 1920 layout and only scale.
export function Stage({children,className='',compactable=false}:{children:ReactNode;className?:string;compactable?:boolean}){
  const host=useRef<HTMLDivElement>(null),[box,setBox]=useState({w:1920,h:1080,s:1,compact:false});
  useLayoutEffect(()=>{const el=host.current?.parentElement;if(!el)return;const fit=()=>{const w=el.clientWidth,h=el.clientHeight,compact=compactable&&w<1180,design=compact?1400:1920,s=w/design;setBox({w:design,h:h/s,s,compact});};fit();const ro=new ResizeObserver(fit);ro.observe(el);return()=>ro.disconnect();},[compactable]);
  return <div ref={host} className={`bc-stage ${box.compact?'compact':''} ${className}`} style={{width:box.w,height:box.h,transform:`scale(${box.s})`}}>{children}</div>;
}

// ---------------------------------------------------------------- pieces
const pct=(v:number,max:number)=>max>0?Math.max(0,Math.min(100,v/max*100)):0;
export const teamName=(m:Metadata|null,team:TeamId)=>strategyDisplayName(m?.teams[team])||(team==='red'?'红方':'蓝方');
export function Emblem({team,name,size=64}:{team:TeamId;name:string;size?:number}){
  const letter=(strategyName(name).match(/[A-Za-z一-龥]/)?.[0]||'R').toUpperCase();
  return <svg className={`bc-emblem ${team}`} width={size} height={size} viewBox="-50 -50 100 100" aria-hidden><defs><linearGradient id={`em-${team}`} x1="0" y1="-1" x2="0" y2="1"><stop offset="0" stopColor={team==='red'?'#ff6b5f':'#5fb2ff'}/><stop offset="1" stopColor={team==='red'?'#8c0d14':'#0b3f8c'}/></linearGradient></defs>
    <circle r="47" fill="#f4f6f8"/><circle r="41" fill={`url(#em-${team})`}/><polygon points="0,-30 26,-15 26,15 0,30 -26,15 -26,-15" fill="none" stroke="#fff" strokeWidth="3" opacity=".55"/><text y="13" textAnchor="middle" fontSize="38" fontWeight="900" fontStyle="italic" fill="#fff">{letter}</text></svg>;
}
// The team emblem: the one LLM maker behind the team, the mixed emblem for several, or the classic letter crest.
export function TeamCrest({metadata,team,size}:{metadata:Metadata|null;team:TeamId;size:number}){
  const emblem=teamEmblem(metadata,team);
  return emblem?<AgentBadge provider={emblem} size={size} ring={team==='red'?'#ff4b4b':'#3aa0ff'} title={emblem==='mixed'?`混合 · ${teamAgents(metadata,team).map(agentLabel).join(' / ')}`:teamAgents(metadata,team).map(agentLabel).join(' / ')||PROVIDERS[emblem].name}/>:<Emblem team={team} name={teamName(metadata,team)} size={size}/>;
}
function Chevrons({level}:{level:number}){const n=level>=10?3:Math.ceil(level/3);return <span className={`bc-chev ${level>=10?'max':''}`} title={`Lv.${level}`}>{Array.from({length:n},(_,i)=><i key={i}/>)}</span>;}

// `hidden` is a pilot looking at the other team: the card keeps its normal look, but the enemy
// robot's health, ammunition and level are not published.
function RobotCard({r,image,selected,onSelect,assemblies,metadata,hidden=false,player=false}:{r:Robot;image?:string;selected:boolean;onSelect:(id:string)=>void;assemblies:number[];metadata:Metadata|null;hidden?:boolean;player?:boolean}){
  const agent=robotAgent(metadata,r.team,r.slot);
  const air=r.role==='aerial',fleet=r.drones,dead=!air&&!r.alive,hp=air?(fleet?pct(fleet.reduce((sum,d)=>sum+Math.max(0,d.integrity),0),fleet.length*Math.max(1,...fleet.map(d=>d.integrity),3)):r.support_active?100:0):pct(r.hp,r.max_hp),respawn=r.respawn_required>0?Math.floor(Math.min(1,r.respawn_progress/r.respawn_required)*100):0;
  return <button className={`bc-card ${r.team} ${dead?'dead':''} ${selected?'selected':''} ${player?'player':''}`} onClick={()=>onSelect(r.id)} aria-label={`${TEAM_LABEL[r.team]}${r.slot}号${robotName(r)}${player?' · 玩家操控':agent?` · 策略来自 ${agentLabel(agent)}`:''}`}>
    {/* A chassis the player is driving publishes itself instead of the strategy that is no longer
        steering it: the badge above the card reads P1 rather than an agent logo. */}
    {player?<span className="bc-card-agent pilot" title="玩家操控 P1">P1</span>:agent&&<span className="bc-card-agent" title={`${agentLabel(agent)}${agent.strategy?` · ${strategyName(agent.strategy)}`:''}`}><AgentLogo provider={providerOf(agent)} size={20}/></span>}
    <span className="bc-card-art">{image?<img src={image} alt=""/>:<span className="bc-card-ph"/>}{r.role==='hero'&&<i className="bc-mode">{(r as Robot&{profile?:string}).profile==='melee'?'近':'远'}</i>}{dead&&!hidden&&<b className="bc-respawn">{respawn}%</b>}</span>
    <span className="bc-card-id"><em>{r.slot}</em><span>{robotName(r)}</span>{!hidden&&<Chevrons level={r.level||1}/>}</span>
    {/* A pilot sees the normal card, but an enemy's health is a flat grey bar: the bar keeps the
        row's shape without publishing the value, and ammunition/level are not shown. */}
    <span className={`bc-card-hp${hidden?' muted':''}`} title={hidden?'对方血量不公开':undefined}><i style={{width:hidden?'100%':`${hp}%`}}/>{Array.from({length:4},(_,k)=><s key={k} style={{left:`${(k+1)*20}%`}}/>)}</span>
    <span className={`bc-card-meta${hidden?' muted':''}`}>{hidden?<span>· · ·</span>:r.role==='engineer'||(r.role==='heavy'&&r.launcher!=='installed'&&r.launcher!=='fitted')?<span className="bc-stars">{[0,1,2,3].map(k=><i key={k} className={assemblies[k]?'on':''}>★</i>)}</span>:fleet?<span>✈ {fleet.filter(d=>d.state==='flying').length}/{fleet.filter(d=>d.state!=='disabled').length}</span>:<span>≡ {r.ammo}</span>}{!hidden&&air&&!fleet&&<small>{r.support_active?'空中支援':'待命'}</small>}{!hidden&&r.role==='sentry'&&r.posture&&<small>{({attack:'进攻',defense:'防御',move:'移动'} as const)[r.posture]}{r.posture_enhanced?'·强化':''}</small>}</span>
  </button>;
}

function Tickers({frame,team}:{frame:Frame;team:TeamId}){
  const s=frame.runes?.[team],rows:{icon:string;text:string;time:number}[]=[];
  if(s?.status==='active'&&(s.active_until??0)>frame.time){const t=(s.active_until||0)-frame.time;rows.push(s.mode==='large'?{icon:'✷',text:`攻击×${s.attack||1}，防御+${Math.round((s.defense||0)*100)}%，热量冷却×${s.cooling||1}`,time:t}:{icon:'✷',text:'全队获得防御加成 +25%',time:t});}
  if(s?.status==='activating')rows.push({icon:'◎',text:`${s.mode==='large'?'大':'小'}能量机关激活中 · ${Math.round(s.ring_sum||0)}环`,time:Math.max(0,(s.hit_deadline||0)-frame.time)});
  const op=frame.outposts?.[team];if(op&&op.hp<=0&&op.rebuild)rows.push({icon:'⚒',text:'前哨站重建中',time:Math.max(0,(op.rebuild.required||0)-(op.rebuild.elapsed||0))});
  return <div className={`bc-tickers ${team}`}>{rows.map((r,i)=><div key={i} className="bc-ticker"><span className="bc-ticker-icon">{r.icon}</span><span>{r.text}</span><b>{Math.ceil(r.time)}s</b></div>)}</div>;
}

function MiniMap({frame,selected}:{frame:Frame;selected:string}){
  const a=frame.arena,W=420,H=225,x=(v:number)=>v/a.width*W,y=(v:number)=>v/a.height*H;
  return <svg className="bc-minimap" viewBox={`0 0 ${W} ${H}`} aria-label="战术小地图"><rect width={W} height={H} fill="#0d1218"/>
    {a.terrain.filter(t=>t.elevation>0).map((t,i)=>t.polygon?<polygon key={i} points={t.polygon.map(([px,py])=>`${x(px)},${y(py)}`).join(' ')} fill="#3a4350" stroke="#56606d" strokeWidth=".6"/>:<rect key={i} x={x(t.x)} y={y(t.y)} width={x(t.w)} height={y(t.h)} fill="#3a4350"/>)}
    {a.obstacles.map((w,i)=><rect key={i} x={x(w.x)} y={y(w.y)} width={Math.max(1,x(w.w))} height={Math.max(1,y(w.h))} fill="#77818c" transform={`rotate(${(w.rotation||0)*180/Math.PI} ${x(w.x+w.w/2)} ${y(w.y+w.h/2)})`}/>)}
    {TEAMS.map(t=>{const b=frame.bases[t],o=frame.outposts?.[t];return <g key={t}><polygon points={[0,1,2,3,4,5].map(k=>`${x(b.x)+11*Math.cos(k*Math.PI/3)},${y(b.y)+11*Math.sin(k*Math.PI/3)}`).join(' ')} className={`mm-base ${t}`}/>{o&&<rect x={x(o.x)-4} y={y(o.y)-4} width="8" height="8" className={`mm-outpost ${outpostHolder(frame,t)} ${o.hp<=0?'down':''}`}/>}</g>;})}
    {frame.robots.filter(r=>r.alive||r.role==='aerial').map(r=><g key={r.id} transform={`translate(${x(r.x)},${y(r.y)})`} className={`mm-bot ${r.team} ${r.id===selected?'sel':''}`}><circle r={r.id===selected?9:7.5}/><text y="3.6" textAnchor="middle">{r.slot}</text></g>)}
  </svg>;
}

function ToastIcon({kind}:{kind?:Callout['icon']}){
  if(kind==='revive')return <svg viewBox="-50 -50 100 100"><path d="M-12-36H12V-12H36V12H12V36H-12V12H-36V-12H-12Z"/></svg>;
  if(kind==='rune')return <svg viewBox="-50 -50 100 100">{[0,1,2,3,4].map(i=><path key={i} transform={`rotate(${i*72})`} d="M-7 -12 L-9 -44 L9 -44 L7 -12 Z"/>)}<circle r="12"/></svg>;
  if(kind==='outpost')return <svg viewBox="-50 -50 100 100"><path d="M-14 40 L-8 -30 L8 -30 L14 40 Z"/><rect x="-22" y="-42" width="44" height="10"/></svg>;
  return <svg viewBox="-50 -50 100 100"><path d="M-36 34 L-10 34 L-4 4 L22 -16 L30 -6 L38 -30 L14 -38 L20 -26 L-14 -4 Z"/><circle cx="-23" cy="34" r="8"/></svg>;
}

// ---------------------------------------------------------------- HUD
export function BroadcastHud({frame,metadata,stats,director,images,selected,onSelect,round,pilot=null,player=null}:{frame:Frame;metadata:Metadata|null;stats:MatchStats;director:BroadcastDirector;images:Record<string,string>;selected:string;onSelect:(id:string)=>void;round:string;pilot?:TeamId|null;player?:string|null}){
  const now=performance.now(),[,tick]=useState(0);
  useEffect(()=>{const id=window.setInterval(()=>tick(n=>n+1),500);return()=>window.clearInterval(id);},[]);
  const damage=(t:TeamId)=>Math.floor((frame.teams[t] as {attack_damage?:number}).attack_damage??frame.teams[t].score),share=damage('red')+damage('blue')>0?damage('red')/(damage('red')+damage('blue'))*100:50;
  const wins=(t:TeamId)=>frame.status==='finished'&&frame.winner===t?1:0;
  const banner=director.active('banner',now).at(-1),toast=director.active('toast',now).at(-1),kills=director.active('kill',now).slice(-4);
  const image=(r?:Robot)=>r?images[`${r.model_asset}|${r.team}`]:undefined,find=(id?:string)=>frame.robots.find(r=>r.id===id);
  // RMUC 2027: control positions decide base invulnerability; control degree decides timeouts.
  const season=frameSeason(frame),position=(team:TeamId,kind:'outpost'|'base')=>frame.positions?.[`${team}_${kind}`];
  const control=(t:TeamId)=>Math.floor(frame.teams[t].control??0);
  const positionLabel=(team:TeamId)=>{const p=position(team,'outpost');if(!p)return null;const mine=p.controller===team;return <small className={`bc-position ${p.controller}`} title={`前哨控制点：${p.controller==='red'?'红方':'蓝方'}${p.control==='full'?'完全':'临时'}控制`}>{mine?'⚑':'⚐'} {p.control==='full'?'完全':'临时'}{mine?'':'·失守'}</small>;};
  const invulnerable=(team:TeamId)=>baseProtected(frame,team);
  return <Stage compactable>
    <div className="bc-top">
      {TEAMS.map(team=>{const base=frame.bases[team],op=frame.outposts?.[team],t=frame.teams[team] as {rebuild_credits?:number};return <div key={team} className={`bc-side ${team}`}>
        <div className="bc-outpost"><span>前哨站 <i className="bc-tower"/></span><b className={op&&op.hp<=0?'down':`held-${outpostHolder(frame,team)}`} title={outpostHolder(frame,team)===team?undefined:`已被${TEAM_LABEL[outpostHolder(frame,team)]}重建占领`}>{op?Math.ceil(Math.max(0,op.hp)):'—'}</b>{season==='2027'?positionLabel(team):<small title="可用重建次数">⚒ {t.rebuild_credits??0}</small>}</div>
        <div className="bc-team-main">
          <div className="bc-team-name"><span>{teamName(metadata,team)}</span><small>{teamEmblem(metadata,team)==='mixed'?`${teamAgents(metadata,team).length} 个 Agent 混合`:teamAgents(metadata,team).length?agentLabel(teamAgents(metadata,team)[0]):metadata?MODE_LABELS[metadata.teams[team].mode]:''}</small></div>
          <div className="bc-basebar"><i className="fill" style={{width:`${pct(base.hp,base.max_hp)}%`}}/><span className="bc-basebar-hex"/><b>{Math.ceil(Math.max(0,base.hp))}</b><i className="bc-base-icon"/></div>
          <div className="bc-team-sub"><span title="基地护盾">⛨ {Math.ceil(base.shield_hp||0)}</span>{invulnerable(team)&&base.hp>0&&<span className="bc-invuln">基地无敌</span>}{base.armor_open&&<span className="bc-armor">护甲展开</span>}</div>
        </div>
        <TeamCrest metadata={metadata} team={team} size={70}/>
      </div>;})}
      <div className="bc-clock">
        <small>{round}</small>
        <div className="bc-clock-row"><span className="bc-wins red">{wins('red')}</span><strong>{clock(frame.remaining).replace(/^0/,'')}</strong><span className="bc-wins blue">{wins('blue')}</span></div>
        <div className="bc-adv"><i style={{width:`${share}%`}}/><em style={{left:`${share}%`}}/></div>
        <div className="bc-coins"><span className="red">{Math.floor(frame.teams.red.resources)}<small>/{Math.floor(stats.teams.red.economy)}</small></span><b title="金币" aria-label="金币">¤</b><span className="blue">{Math.floor(frame.teams.blue.resources)}<small>/{Math.floor(stats.teams.blue.economy)}</small></span></div>
        {season==='2027'&&<div className="bc-dmg bc-control"><span>{control('red')}</span><small>CONTROL</small><span>{control('blue')}</span></div>}
        <div className="bc-dmg"><span>{damage('red')}</span><small>DAMAGE</small><span>{damage('blue')}</span></div>
      </div>
    </div>
    {TEAMS.map(team=>{const list=[...frame.robots.filter(r=>r.team===team)].sort((a,b)=>team==='red'?b.slot-a.slot:a.slot-b.slot);return <div key={team} className={`bc-cards ${team}`}>
      {list.map(r=><RobotCard key={r.id} r={r} image={image(r)} selected={selected===r.id} onSelect={onSelect} assemblies={stats.teams[team].assemblies} metadata={metadata} hidden={pilot!==null&&pilot!==team} player={r.id===player}/>)}
    </div>;})}
    {TEAMS.map(team=><Tickers key={team} frame={frame} team={team}/>)}
    {banner&&<div key={banner.key} className={`bc-banner ${banner.team}`}><span>{banner.title}</span></div>}
    <div className="bc-killfeed">{kills.map(k=>{const killer=find(k.killer),victim=find(k.victim);return <div key={k.key} className={`bc-kill ${k.team}`}>
      <span className={`bc-kill-bot ${killer?.team||other(k.team)}`}>{image(killer)&&<img src={image(killer)} alt=""/>}<em>{killer?.slot??'?'}</em></span><b>摧毁</b>
      <span className={`bc-kill-bot ${victim?.team||other(k.team)}`}>{image(victim)&&<img src={image(victim)} alt=""/>}<em>{victim?.slot??'?'}</em></span></div>;})}</div>
    {toast&&<div key={toast.key} className={`bc-toast ${toast.team}`}><span className="bc-toast-icon"><ToastIcon kind={toast.icon}/></span><div><strong>{toast.title}</strong><div className="bc-chips">{toast.chips?.map(c=><span key={c}>{c}</span>)}</div></div></div>}
    {!pilot&&<div className="bc-mini"><MiniMap frame={frame} selected={selected}/></div>}    <div className="bc-plate"><span>对抗赛 · 策略联赛</span><b>ROBOMASTER {season}</b></div>
  </Stage>;
}
