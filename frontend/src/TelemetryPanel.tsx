import {Activity,Shield,Target} from 'lucide-react';
import {clock} from './media';
import {ROLE_NAMES,TEAM_COLORS,type Frame,type Robot,type MatchEvent,type TeamId} from './types';
import {mechanismProgress,type MechanismKind} from './mechanismProgress';

const hp=(value:number)=>Math.ceil(Math.max(0,value));
const percent=(value:number,max:number)=>max>0?Math.max(0,Math.min(100,value/max*100)):0;

function RobotTelemetry({robot:r,selected,onSelect,time}:{robot:Robot;selected:string;onSelect:(id:string)=>void;time:number}){
  const air=r.role==='aerial';
  const armText:Record<string,string>={rescue:'机械臂·救援',assembly:'机械臂·装配',pick:'机械臂·夹取',manual:'机械臂·手动'};
  const pickup=r.unit_pickup?({approaching:'夹取·对准',gripping:'夹取·闭爪',lifting:'夹取·抬升',stowing:'夹取·入仓'}[r.unit_pickup.stage]||'夹取中'):null;
  const status=r.red_card?'红牌罚下':r.overspeed_locked?'超弹速锁定':r.heat_permanent_lock?'永久禁发':r.launcher_fault?'发射器故障':(r.fpv_blocked_until||0)>time?'视野遮挡':air?(r.support_active?'空中支援':'停机待命'):!r.alive?'复活中':r.self_righting?'自主翻身':r.tipped?'翻倒':r.powered===false?'底盘断电':r.weak?'弱状态':pickup?pickup:r.invulnerable?'无敌':r.deployed?'已部署':(r.arm_mode&&armText[r.arm_mode])||'';
  return <button title={r.design_name||ROLE_NAMES[r.role]} className={`data-robot-row ${r.team} ${r.id===selected?'selected':''} ${!air&&!r.alive?'dead':''}`} data-id={r.id} onClick={()=>onSelect(r.id)} aria-label={`${r.team==='red'?'红':'蓝'}方${r.slot}号${ROLE_NAMES[r.role]}`}>
    <span className="data-robot-slot">{r.slot}</span>
    <span className="data-robot-main">
      <span className="data-robot-title"><span>{r.design_name?.replace(/^\S+\s+/,'')||ROLE_NAMES[r.role]}<small>Lv.{r.level}</small>{!!r.yellow_cards&&<em className="yellow-card-count">黄牌 {r.yellow_cards}</em>}</span><strong data-robot-hp={r.id}>{air?'无血量机制':`${hp(r.hp)} / ${hp(r.max_hp)}`}</strong></span>
      <span className="data-hp-track"><i style={{width:`${air?(r.support_active?100:0):percent(r.hp,r.max_hp)}%`,background:TEAM_COLORS[r.team]}}/></span>
      <span className="data-robot-meta"><span className={r.overheated?'hot':''}>{air?`${status} · 免费 ${(r.support_time||0).toFixed(0)}s`:!r.alive&&!r.red_card?`${status} ${(r.respawn_progress||0).toFixed(1)} / ${(r.respawn_required||0).toFixed(0)}`:status||(r.role==='engineer'?`${(r.mass_kg||0).toFixed(1)}kg · 机械臂`:`${r.mass_kg?r.mass_kg.toFixed(1)+'kg · ':''}热 ${hp(r.heat)}/${hp(r.max_heat)}`)}</span><span>{r.role==='engineer'?`携带 ${r.carried_units}`:`${r.ammo} 发`}</span></span>
    </span>
  </button>;
}

function StructureTelemetry({frame,team,kind}:{frame:Frame;team:TeamId;kind:'base'|'outpost'}){
  const value=(kind==='base'?frame.bases:frame.outposts)?.[team];
  if(!value)return null;
  const ratio=percent(value.hp,value.max_hp);
  const state=kind==='base'?(frame.outposts?.[team]?.hp>0?'前哨保护':value.armor_open?'装甲展开':'装甲闭合'):value.rebuild?'重建中':value.hp<=0?'已摧毁':value.ever_destroyed?'已重建':value.rotation_stopped?'停止转动':'旋转运行';
  return <div className={`structure-data ${ratio<=20?'critical':''}`} data-structure={`${team}-${kind}`}>
    <div className="structure-data-label">{kind==='base'?<Shield size={12}/>:<Target size={12}/>}<span>{kind==='base'?'基地':'前哨站'}</span><small>{Math.round(ratio)}%</small></div>
    <strong data-structure-hp={`${team}-${kind}`}>{hp(value.hp)}<small> / {hp(value.max_hp)}</small></strong>
    <span className="structure-hp-track"><i style={{width:`${ratio}%`,background:TEAM_COLORS[team]}}/></span>
    <div className="structure-data-state"><span>{state}</span>{kind==='base'&&(value.shield_hp||0)>0&&<b>盾 +{hp(value.shield_hp!)}</b>}</div>
    {kind==='outpost'&&<MechanismTelemetry frame={frame} team={team} kind="outpost"/>}
  </div>;
}

function MechanismTelemetry({frame,team,kind}:{frame:Frame;team:TeamId;kind:MechanismKind}){
  const display=mechanismProgress(frame,team,kind);if(!display)return null;
  const value=Math.round(display.progress*100);
  return <div className="mechanism-data" data-mechanism-panel={`${team}-${kind}`}>
    <div><span>{display.label}</span><b>{value}%</b></div>
    <div className="mechanism-progress-track" role="progressbar" aria-label={display.label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={value}><i style={{transform:`scaleX(${display.progress})`}}/></div>
    <small>{display.detail}</small>
  </div>;
}

export function TelemetryPanel({frame,selected,onSelect,replay,events,eventText}:{frame:Frame;selected:string;onSelect:(id:string)=>void;replay:boolean;events:MatchEvent[];eventText:(e:MatchEvent)=>string}){
  return <aside className="telemetry-panel match-data-panel" aria-label="比赛数据面板">
    <div className="data-panel-heading"><div><Activity size={14}/><h3>比赛数据</h3></div><span>{replay?'回放':'实时'} · {clock(frame.time)}</span></div>
    {(['red','blue'] as const).map(team=>{
      const robots=frame.robots.filter(r=>r.team===team),ground=robots.filter(r=>r.role!=='aerial');
      const alive=ground.filter(r=>r.alive).length;
      return <section className={`data-team ${team}`} key={team}>
        <div className="data-team-heading"><strong><i style={{background:TEAM_COLORS[team]}}/>{team==='red'?'红方':'蓝方'}</strong><span>金币 <b>{Math.floor(frame.teams[team].resources)}</b></span></div>
        <div className="structure-data-grid"><StructureTelemetry frame={frame} team={team} kind="base"/><StructureTelemetry frame={frame} team={team} kind="outpost"/></div>
        <MechanismTelemetry frame={frame} team={team} kind="assembly"/>
        <div className="ground-data"><span>地面存活 <b>{alive} / {ground.length}</b></span><span>地面总血量 <b>{hp(ground.reduce((sum,r)=>sum+r.hp,0))} / {hp(ground.reduce((sum,r)=>sum+r.max_hp,0))}</b></span></div>
        <div className="data-roster">{robots.map(r=><RobotTelemetry key={r.id} robot={r} selected={selected} onSelect={onSelect} time={frame.time}/>)}</div>
      </section>;
    })}
    <details className="data-events"><summary>比赛事件 <span>{events.length}</span></summary><div className="event-feed" id="events">{events.slice(0,15).map((e,i)=><div key={i} className={e.type.includes('error')?'error-event':''}><time>{clock(e.time??e.tick*.05)}</time><span>{eventText(e)}</span></div>)}{!events.length&&<p>开赛后显示战斗事件。</p>}</div></details>
  </aside>;
}
