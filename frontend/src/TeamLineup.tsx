import {useEffect,useRef,useState} from 'react';
import {ArrowLeft,Ban,Battery,Bot,Check,ChevronRight,Copy,Crosshair,Download,Gauge,Hammer,LockKeyhole,Rocket,Shield,ShieldCheck,Timer,Wrench,X,Zap} from 'lucide-react';
import {ROLE_NAMES,SEASON_LABELS,SEASON_SLOTS,type Role,type RobotHardware,type Season,type TeamLineup} from './types';
import {RobotPreview} from './RobotPreview';
import './teamLineup.css';

export const DEFAULT_LINEUP:TeamLineup={1:1,2:2,3:3,4:4,6:6,7:7};
// RMUC 2027: 1 heavy, 3/4 infantry, 6 aerial robot system (hangar), 7 automatic sentry.
export const DEFAULT_LINEUPS:Record<Season,TeamLineup>={'2026':DEFAULT_LINEUP,'2027':{1:2711,3:2731,4:2732,6:2761,7:2771}};
export const SEASON_ROLES:Record<Season,Record<number,Role>>={'2026':{1:'hero',2:'engineer',3:'infantry',4:'infantry',6:'aerial',7:'infantry'},'2027':{1:'heavy',3:'infantry',4:'infantry',6:'aerial',7:'sentry'}};
/** Whether a model passes a season's construction rules (config robot_designs[*].seasons). */
export const legalIn=(model:RobotHardware|undefined,season:Season)=>!!model&&(model.seasons?.[season]?.legal??season==='2026');
export const legalityIssues=(model:RobotHardware,season:Season)=>(model.seasons?.[season]?.issues||[]).map(i=>i.zh).join('；');
export const validLineup=(lineup:TeamLineup,models:Record<string,RobotHardware>,season:Season)=>SEASON_SLOTS[season].every(slot=>{const m=models[String(lineup[String(slot)])];return m?.role===SEASON_ROLES[season][slot]&&legalIn(m,season);})&&Object.keys(lineup).length===SEASON_SLOTS[season].length;
const drives:Record<string,string>={mecanum:'麦克纳姆轮',swerve:'舵轮',omni:'全向轮',wheel_legged:'双轮足',quadrotor:'旋翼'};
const roleIcons={hero:Crosshair,engineer:Wrench,infantry:Shield,aerial:Rocket,heavy:Hammer,sentry:ShieldCheck};
const code=(model?:RobotHardware)=>model?.name.split(' ')[0]||'—';
const title=(model:RobotHardware)=>model.name.replace(/^\S+\s+/, '');
export const sameLineup=(a:TeamLineup,b:TeamLineup)=>{const keys=new Set([...Object.keys(a),...Object.keys(b)]);return [...keys].every(slot=>a[slot]===b[slot]);};
export function modelAbilities(model:RobotHardware){return [model.transform_allowed?'折叠穿隧道':null,model.arm_count===2?'双机械臂':null,model.chassis_type==='wheel_legged'?(model.step_climb_m?'可跳跃 / 登阶':'可跳跃 / 飞坡'):null,model.leg_type==='serial'?'翻倒自救':null,model.role==='hero'?(model.deploy_allowed?'部署机构':'不可部署'):null,model.role==='heavy'?'模块化42mm':null,model.role==='sentry'?'全自动':null,model.role==='aerial'?(model.drone_count?`${model.drone_count}架空中机器人`:`${model.rotor_count}旋翼`):null].filter(Boolean).join(' · ')||model.focus;}

function features(model:RobotHardware){
  const result:{name:string;detail:string}[]=[];
  if(model.transform_allowed)result.push({name:'低姿态穿越',detail:`炮塔与导轨折叠后高 ${Math.round((model.folded_height_m??.235)*1000)}mm，可通过两侧低矮隧道；洞内展开受屋顶限制。`});
  if(model.arm_count)result.push({name:model.arm_count===2?'双臂独立协作':'升降伸缩机械臂',detail:model.arm_count===2?'两只手可分别控制，支持一手扶正队友、另一手夹取能量单元。':'支持夹取、抬升、装配与扶正。取物需要真实的闭爪和入仓过程。'});
  if(model.chassis_type==='wheel_legged')result.push({name:'主动平衡与跳跃',detail:`腿长 ${Math.round((model.leg_min_m??.12)*1000)}–${Math.round((model.leg_max_m??.34)*1000)}mm。支持飞坡与越障，驱动沿车身前后方向。`});
  if(model.leg_type==='serial')result.push({name:'串联腿 · 髋关节整周旋转',detail:'髋关节没有限位。翻倒、侧躺或车身倒扣后，腿先转到地面，再把车身绕轮轴翻回来，约 1–2 秒，无需工程救援。'});
  if(model.chassis_type==='swerve')result.push({name:'四轮独立转向',detail:`舵轮以 ${Math.round((model.steer_rate_rad_s??0)*180/Math.PI)}°/s 转向，适合高抓地机动；换向需要转动轮组。`});
  if(model.chassis_type==='omni'||model.chassis_type==='mecanum')result.push({name:'全向移动',detail: `${drives[model.chassis_type]}支持前后与横向移动。不同构型的抓地、效率与重量分别配置。`});
  if(model.role==='hero')result.push({name:model.deploy_allowed?'固定炮台机构':'机动英雄 · 无部署机构',detail:model.deploy_allowed?'准备阶段选远程性能后，可在己方半场部署；使用42mm大弹丸。':'使用42mm大弹丸。部署动作不可用，保留双轮足机动能力。'});
  if(model.role==='aerial'&&model.drone)result.push({name:`机库 · ${model.drone_count} 架全自动空中机器人`,detail:`每架 ${Math.round(model.drone.size_m*1000)}mm / ${Math.round(model.drone.mass_kg*1000)}g，护罩可承受 ${model.drone.impact_integrity} 次有效撞击；只能撞击基地与前哨站中层装甲，机库内不充电。`});
  else if(model.role==='aerial')result.push({name:`${model.rotor_count}旋翼空中支援`,detail:'完整桨叶护罩与绳长约束；使用17mm弹丸，飞行会消耗电池和支援时间。'});
  if(model.role==='heavy')result.push({name:'模块化 42mm 发射机构',detail:`完成 3 级装配或按时间规则解锁后，在工作台停稳约 ${model.launcher_module_kg?.toFixed(1)??'5'} kg 模块安装，首发弹丸完成装配确认；之前只负责能量单元与科技核心。`});
  if(model.role==='sentry')result.push({name:'全自动哨兵 · 三种姿态',detail:'进攻、防御、移动姿态各有增益与代价，切换间隔 5 秒；每分钟可在补给区领取 100 发。'});
  return result;
}

interface Briefing {team_lineup:TeamLineup;task:{zh:string;en:string};guides:{zh:string;en:string}}
interface Workspace {workspace:string;task_file:string;deadline_utc:string;team_lineup:TeamLineup}

function ModelDetails({model,peers,season}:{model:RobotHardware;peers:RobotHardware[];season:Season}){
  const stats=model.initial_stats_by_season?.[season]??model.initial_stats;
  const meters=[{name:'参考速度',value:model.speed_reference_mps,max:Math.max(...peers.map(m=>m.speed_reference_mps)),unit:'m/s'},
    {name:'电池容量',value:model.battery_wh,max:Math.max(...peers.map(m=>m.battery_wh)),unit:'Wh'}];
  return <aside className="hangar-details">
    <div className="hangar-model-heading"><span>MODEL {String(model.slot).padStart(3,'0')}</span><b>{code(model)}</b><h3>{title(model)}</h3><p>{model.focus}</p></div>
    <div className="hangar-tags"><span>{model.chassis_type==='hangar'?'固定机库':drives[model.chassis_type]}</span><span>{model.role==='hero'?'42mm':model.role==='heavy'?'模块化42mm':model.role==='engineer'?'作业机器人':model.role==='aerial'&&model.drone?'撞击':'17mm'}</span>{model.seasons&&(['2026','2027'] as Season[]).map(s=><span key={s} className={legalIn(model,s)?'legal':'illegal'} title={legalIn(model,s)?'':legalityIssues(model,s)}>{SEASON_LABELS[s]} {legalIn(model,s)?'✓':'✗'}</span>)}</div>
    <div className="hangar-stat-grid">
      <div><Shield size={15}/><span>预选 Lv.1 血量</span><strong>{model.role==='aerial'?'—':stats?.hp??'—'}<small>{model.role==='aerial'?'无血量机制':'HP'}</small></strong></div>
      {model.drone?<div><Zap size={15}/><span>空中机器人</span><strong>{model.drone_count}<small>架 · {Math.round(model.drone.mass_kg*1000)} g</small></strong></div>:<div><Zap size={15}/><span>{model.role==='aerial'?'飞行峰值功率':'预选底盘功率'}</span><strong>{model.role==='aerial'?model.flight_power_max_w:stats?.power_w??'—'}<small>W</small></strong></div>}
      <div><Gauge size={15}/><span>整机基础质量</span><strong>{model.mass_kg.toFixed(2)}<small>kg</small></strong></div>
      {model.drone?<div><Crosshair size={15}/><span>护罩耐撞</span><strong>{model.drone.impact_integrity}<small>次 / 架</small></strong></div>:<div><Crosshair size={15}/><span>{model.role==='engineer'||model.role==='heavy'?'独立机械臂':'热量 / 冷却'}</span><strong>{model.role==='engineer'||model.role==='heavy'?model.arm_count:`${stats?.max_heat??'—'} / ${stats?.cooling??'—'}`}<small>{model.role==='engineer'||model.role==='heavy'?'只':'/s'}</small></strong></div>}
    </div>
    <div className="hangar-meters">{meters.map(m=><div key={m.name}><div><span>{m.name}</span><b>{m.value.toFixed(m.unit==='m/s'?1:0)} <small>{m.unit}</small></b></div><span className="hangar-meter"><i style={{width:`${m.value/m.max*100}%`}}/></span></div>)}</div>
    <div className="hangar-feature-list">{features(model).map(f=><div key={f.name}><Check size={13}/><div><strong>{f.name}</strong><p>{f.detail}</p></div></div>)}</div>
    <div className="hangar-footprint"><span>收纳尺寸</span><b>{model.stowed_m.map(v=>Math.round(v*1000)).join(' × ')} <small>mm</small></b></div>
    <p className="hangar-stats-note">条形按同兵种型号比较。速度为控制参考值；初始性能可在规则允许的准备阶段改选。</p>
  </aside>;
}

export function TeamLineupDialog({models,value,onChange,onClose,season='2026'}:{models:Record<string,RobotHardware>;value:TeamLineup;onChange:(v:TeamLineup)=>void;onClose:()=>void;season?:Season}){
  const roles=SEASON_ROLES[season],slots=SEASON_SLOTS[season];
  const [activeSlot,setActiveSlot]=useState<number>(1),[step,setStep]=useState<'selection'|'briefing'>('selection');
  const [name,setName]=useState(''),[minutes,setMinutes]=useState(90),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [briefing,setBriefing]=useState<Briefing|null>(null),[created,setCreated]=useState<Workspace|null>(null),[language,setLanguage]=useState<'zh'|'en'>('zh'),[copied,setCopied]=useState(false);
  const dialog=useRef<HTMLElement>(null),onCloseRef=useRef(onClose),busyRef=useRef(busy),locked=!!briefing||!!created;
  onCloseRef.current=onClose;busyRef.current=busy;
  const model=models[String(value[String(activeSlot)])];
  // Every model of the slot's role is listed; those failing this season's construction rules cannot be picked.
  const peers=Object.values(models).filter(m=>m.role===roles[activeSlot]).sort((a,b)=>Number(legalIn(b,season))-Number(legalIn(a,season))||a.slot-b.slot);
  const roster=slots.map(slot=>({slot,model:models[String(value[String(slot)])]}));
  const valid=validLineup(value,models,season);
  useEffect(()=>{
    const previous=document.activeElement as HTMLElement,overflow=document.body.style.overflow;document.body.style.overflow='hidden';dialog.current?.querySelector<HTMLButtonElement>('button')?.focus();
    const key=(e:KeyboardEvent)=>{if(e.key==='Escape'&&!busyRef.current){e.preventDefault();onCloseRef.current();}if(e.key==='Tab'){
      const targets=[...(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),a[href],[tabindex="0"]')??[])].filter(el=>el.getClientRects().length);
      const first=targets[0],last=targets.at(-1);if(!first)return;
      if(!dialog.current?.contains(document.activeElement)){e.preventDefault();first.focus();}
      else if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
    }};
    document.addEventListener('keydown',key);return()=>{document.removeEventListener('keydown',key);document.body.style.overflow=overflow;if(previous?.isConnected)previous.focus();};
  },[]);
  async function confirm(){setBusy(true);setError('');try{
    const response=await fetch('/api/team-briefing',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({team_lineup:value,season})}),data=await response.json();
    if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'阵容任务生成失败');setBriefing(data);setStep('briefing');
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  async function create(){if(!briefing)return;setBusy(true);setError('');try{
    const response=await fetch('/api/team-workspaces',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,minutes,team_lineup:briefing.team_lineup,season})}),data=await response.json();
    if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'创建失败');setCreated(data);
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  function download(lang:'zh'|'en'){
    if(!briefing)return;const url=URL.createObjectURL(new Blob([briefing.guides[lang]],{type:'text/markdown;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download=`team-${lang}-selected.md`;a.click();URL.revokeObjectURL(url);
  }
  const fleetMass=roster.reduce((total,r)=>total+(r.model?.mass_kg??0),0),fleetBattery=roster.reduce((total,r)=>total+(r.model?.battery_wh??0),0);
  return <div className="modal-backdrop hangar-backdrop"><section ref={dialog} className="team-lineup-dialog hangar" role="dialog" aria-modal="true" aria-label="team共同阵容">
    <header className="hangar-header"><div className="hangar-brand"><span><Bot size={22}/></span><div><small>RMUC ARENA / ROBOT ARMORY</small><h2>出战机库</h2></div></div><div className="hangar-symmetry"><i/><span>锁定出战阵容<b>完整型号 · 独立策略</b></span></div><button className="hangar-close" aria-label="关闭阵容选择" disabled={busy} onClick={onClose}><X size={20}/></button></header>
    <div className="hangar-stepbar"><div><button className={step==='selection'?'active':''} onClick={()=>setStep('selection')}><b>01</b> 配置阵容{briefing&&<Check size={14}/>}</button><ChevronRight size={13}/><button className={step==='briefing'?'active':''} disabled={!briefing} onClick={()=>setStep('briefing')}><b>02</b> Agent 任务</button></div><span>{SEASON_LABELS[season]} · {Object.values(models).filter(m=>legalIn(m,season)).length} 款合规构型 / {slots.length} 个出战位置</span></div>
    {step==='selection'?<>
      <div className="hangar-body"><nav className="hangar-roster" aria-label="出战位置"><span className="hangar-section-label">SLOTS / 出战位置</span>{roster.map(({slot,model:m})=>{const Icon=roleIcons[roles[slot] as keyof typeof roleIcons];return <button key={slot} aria-label={`${slot}号${ROLE_NAMES[roles[slot] as keyof typeof ROLE_NAMES]}位置`} aria-pressed={activeSlot===slot} className={activeSlot===slot?'active':''} onClick={()=>setActiveSlot(slot)}><span className="hangar-slot-number">{String(slot).padStart(2,'0')}</span><div><b><Icon size={13}/>{ROLE_NAMES[roles[slot] as keyof typeof ROLE_NAMES]}</b><span>{m?title(m):'选择型号'}</span><small>{code(m)}</small></div><ChevronRight size={14}/></button>;})}<div className="hangar-fleet"><span><Gauge size={13}/> 整队基础质量 <b>{fleetMass.toFixed(1)} kg</b></span><span><Battery size={13}/> 电池总容量 <b>{fleetBattery} Wh</b></span></div></nav>
        <div className="hangar-center">{model?<RobotPreview model={model} slot={activeSlot}/>:<div className="hangar-empty">正在加载机器人型号…</div>}
          <div className="hangar-candidates"><div><span className="hangar-section-label">CHASSIS SELECTION / 可选构型</span><small>{peers.length} 款{locked?' · 阵容已确认':''}</small></div><div className="hangar-model-grid">{peers.map(m=>{const legal=legalIn(m,season);return <button key={m.slot} disabled={locked||busy||!legal} aria-label={`选择${m.name}`} aria-pressed={model?.slot===m.slot} title={legal?undefined:`不符合 ${SEASON_LABELS[season]} 制作规范：${legalityIssues(m,season)}`} className={`${model?.slot===m.slot?'selected':''}${legal?'':' illegal'}`} onClick={()=>onChange({...value,[activeSlot]:m.slot})}><span>{code(m)}{model?.slot===m.slot&&<Check size={14}/>}{!legal&&<Ban size={13}/>}</span><b>{title(m)}</b><small>{legal?`${m.chassis_type==='hangar'?'固定机库':drives[m.chassis_type]} · ${m.bare_mass_kg.toFixed(1)}kg`:`不符合 ${season} 规范`}</small></button>;})}</div></div>
        </div>{model&&<ModelDetails model={model} peers={peers.filter(m=>legalIn(m,season))} season={season}/>}</div>
      <footer className="hangar-footer"><div><span><Shield size={15}/>{locked?'出战阵容已确认':'所选机器人即本任务锁定的出战阵容'}</span><small>{valid?`确认后生成包含全部 ${slots.length} 台型号的 ${SEASON_LABELS[season]} Agent 任务与规则。`:`有位置的型号不符合 ${SEASON_LABELS[season]} 制作规范，请重新选择。`}</small></div><div><button className="hangar-secondary" disabled={locked||busy} onClick={()=>onChange({...DEFAULT_LINEUPS[season]})}>恢复默认阵容</button><button className="hangar-primary" disabled={!valid||busy} onClick={briefing?()=>setStep('briefing'):confirm}>{busy?'生成阵容任务…':briefing?'查看 Agent 任务':'确认阵容，生成 Agent 任务'}<ChevronRight size={16}/></button></div></footer>
    </>:<><div className="hangar-briefing"><div className="hangar-briefing-title"><span className="hangar-section-label">MISSION BRIEFING / 开发任务</span><h3>你的 Agent 已知道完整出战阵容</h3><p>以下内容在确认型号后生成。阵容会写入任务、规则和受保护的记录，供 Agent 直接规划 {slots.length} 台机器人的分工。</p></div>
      <div className="hangar-confirmed-roster">{roster.map(({slot,model:m})=>m&&<div key={slot}><span>{String(slot).padStart(2,'0')} / {ROLE_NAMES[m.role]}</span><b>{code(m)}</b><strong>{title(m)}</strong><small>{modelAbilities(m)}</small></div>)}</div>
      <div className="hangar-briefing-columns"><section className="hangar-agent-copy"><div><b>将提供给参赛 Agent</b><span><button aria-pressed={language==='zh'} onClick={()=>setLanguage('zh')}>中文</button><button aria-pressed={language==='en'} onClick={()=>setLanguage('en')}>EN</button></span></div><pre>{briefing?.task[language]}</pre><div className="hangar-guide-downloads"><button onClick={()=>download('zh')}><Download size={14}/> 中文完整规则</button><button onClick={()=>download('en')}><Download size={14}/> English rules</button></div></section>
        <section className="hangar-development">{created?<><span className="hangar-status"><LockKeyhole size={16}/> 阵容已锁定 · 开发计时已开始</span><h4>把任务文件交给 Agent</h4><p>该任务包含所选阵容的中英文规则、硬件和练习接口。</p><code>{created.task_file}</code><button className="hangar-secondary" onClick={async()=>{try{await navigator.clipboard.writeText(created.task_file);setCopied(true);}catch{setError('复制失败，请手动复制任务路径。');}}}><Copy size={14}/>{copied?'已复制路径':'复制任务路径'}</button><small className="hangar-deadline"><Timer size={13}/> 截止：{new Date(created.deadline_utc).toLocaleString()}</small></>:<><span className="hangar-status"><Check size={16}/> 阵容已确认 · 尚未开始计时</span><h4>准备好，再开始开发</h4><p>点击开始后创建工作区并启动计时，阅读、编码、练习和提交共同使用这段时间。</p><label>开发任务名称<input aria-label="team开发任务名称" value={name} onChange={e=>setName(e.target.value)} placeholder="team-tunnel-v1" maxLength={48}/></label><label>开发时长<span><input aria-label="team开发分钟数" type="number" min={1} max={1440} value={minutes} onChange={e=>setMinutes(Number(e.target.value))}/><small>分钟</small></span></label><button className="hangar-primary" disabled={busy||!name||!Number.isInteger(minutes)||minutes<1||minutes>1440} onClick={create}><LockKeyhole size={16}/>{busy?'创建工作区…':`锁定阵容，开始 ${minutes} 分钟开发`}</button></>}</section>
      </div></div><footer className="hangar-footer"><button className="hangar-secondary" disabled={!!created||busy} onClick={()=>{setBriefing(null);setStep('selection');setError('');}}><ArrowLeft size={15}/>重新调整阵容</button><button className="hangar-primary" disabled={busy} onClick={onClose}>{created?'完成':'保存阵容，稍后开始'}</button></footer></>}
    {error&&<div className="hangar-error" role="alert">{error}</div>}
  </section></div>;
}
