import {useCallback,useEffect,useMemo,useRef,useState,type CSSProperties,type KeyboardEvent as ReactKeyboardEvent} from 'react';
import {Bot,ChevronLeft,ChevronRight,Crown,GraduationCap,History,LibraryBig,Radio,Shield,Trophy,Wifi,WifiOff} from 'lucide-react';
import {ROLE_NAMES,type CatalogEntry,type RobotHardware,type Standing} from './types';
import {RobotPreview} from './RobotPreview';
import './home.css';
export type ArenaMode='standard'|'deck';

type MenuItem={id:string;title:string;en:string;icon:typeof Shield;accent:string;brief:string;tags:string[];cta:string;run:()=>void};
const ROLE_ORDER=['heavy','hero','engineer','infantry','sentry','aerial'];
const CHASSIS:Record<string,string>={mecanum:'麦克纳姆轮',swerve:'舵轮',omni:'全向轮',wheel_legged:'双轮足',quadrotor:'多旋翼'};
// Deterministic sparks so the backdrop is stable across renders.
const SPARKS=Array.from({length:18},(_,i)=>({left:(i*37+11)%100,delay:-(i*1.7)%12,duration:9+(i*7)%8,size:2+(i%3),hue:i%3===0?'var(--home-red)':i%3===1?'var(--home-blue)':'var(--home-gold)'}));

export function Home({models,catalog,cards,standings=[],connected=false,live,onTraining,onBattle,onHistory,onRankings,onGallery,onWatch,busy}:{models:Record<string,RobotHardware>;catalog:Record<string,CatalogEntry>;cards:Record<string,CatalogEntry>;standings?:Standing[];connected?:boolean;live?:{red:string;blue:string}|null;onTraining:()=>void;onBattle:(mode:ArenaMode)=>void;onHistory:()=>void;onRankings:()=>void;onGallery:()=>void;onWatch:()=>void;busy:boolean}){
  const champion=standings[0];
  const menu=useMemo<MenuItem[]>(()=>[
    {id:'rm',title:'RM 对战',en:'RM COMPETITION',icon:Shield,accent:'#f2c35b',brief:'正式赛制，可选 RMUC 2027（默认，5v5：重型、两台步兵、空中机器人系统、全自动哨兵）或 RMUC 2026（6v6）。双方使用相同构型阵容，只能选择符合该赛季制作规范的型号，七分钟决出胜负。',tags:['2027 / 2026 地图','镜像阵容','合规检查'],cta:'准备正式对战',run:()=>onBattle('standard')},
    {id:'free',title:'自由对战',en:'FREE BATTLE',icon:Bot,accent:'#5aaeff',brief:'从已保存的单机策略中部署任意型号、任意数量。红蓝阵容独立选择，支持重复出场。',tags:['不对称阵容','自由数量',`${Object.keys(cards).length} 份单机策略`],cta:'组建自由阵容',run:()=>onBattle('deck')},
    {id:'training',title:'策略训练',en:'STRATEGY TRAINING',icon:GraduationCap,accent:'#5fe0b6',brief:'四种开发方式，从单机技能到全队战术。创建任务、反复练习，再把参赛版本保存进策略库。',tags:['全队统筹','单机专精','多机协同','自由适配'],cta:'选择训练方式',run:onTraining},
    {id:'gallery',title:'策略库',en:'STRATEGY GALLERY',icon:LibraryBig,accent:'#c79bff',brief:'浏览每份策略的打法：由哪个 LLM 生成、风格雷达、七分钟节奏、战术路线与关键决策。上传你的策略，或给机器人换上自己的模型。',tags:['12 家 LLM','打法可视化','自定义机器人模型'],cta:'打开策略库',run:onGallery},
    {id:'history',title:'比赛与回放',en:'MATCH REPLAYS',icon:History,accent:'#86d8f0',brief:'每一场对战都有记录。回看完整回放、导出文件，或清理不再需要的比赛。',tags:['完整回放','导出 / 删除','本机保存'],cta:'打开比赛记录',run:onHistory},
    {id:'rankings',title:'策略排行榜',en:'RANKINGS',icon:Trophy,accent:'#ff9d66',brief:champion?`当前榜首 ${champion.name} · Elo ${Math.round(champion.rating)}。按策略版本累计 Elo，手动结束和策略错误的比赛不计分。`:'按策略版本累计 Elo。两份不同策略完成有效比赛后，排行榜开始累计。',tags:['版本 Elo','胜 / 负 / 平'],cta:'查看排名',run:onRankings},
  ],[cards,champion,onBattle,onTraining,onHistory,onRankings,onGallery]);
  const [active,setActive]=useState(0),buttons=useRef<(HTMLButtonElement|null)[]>([]);
  const units=useMemo(()=>Object.values(models).sort((a,b)=>ROLE_ORDER.indexOf(a.role)-ROLE_ORDER.indexOf(b.role)||a.slot-b.slot),[models]);
  const [unitIndex,setUnitIndex]=useState<number|null>(null);
  const shown=unitIndex??Math.max(0,units.findIndex(u=>u.slot===103));
  const unit=units[shown];
  const cycle=useCallback((step:number)=>{if(units.length)setUnitIndex(i=>((i??Math.max(0,units.findIndex(u=>u.slot===103)))+step+units.length)%units.length);},[units]);
  const ranges=useMemo(()=>({hp:Math.max(1,...units.map(u=>u.initial_stats?.hp||0)),speed:Math.max(1,...units.map(u=>u.speed_reference_mps||0)),heat:Math.max(1,...units.map(u=>u.initial_stats?.max_heat||0)),battery:Math.max(1,...units.map(u=>u.battery_wh||0))}),[units]);
  // Arrow keys drive the menu and the unit carousel like a console main menu; Enter starts the highlighted mode.
  const focusItem=(index:number)=>{const next=(index+menu.length)%menu.length;setActive(next);buttons.current[next]?.focus();};
  useEffect(()=>{const onKey=(e:KeyboardEvent)=>{const t=e.target as HTMLElement|null;if(e.metaKey||e.ctrlKey||e.altKey||t?.closest('input,textarea,select,[contenteditable="true"],[role="dialog"]'))return;
    if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();cycle(e.key==='ArrowLeft'?-1:1);}
    else if((e.key==='ArrowDown'||e.key==='ArrowUp')&&!t?.closest('.home-menu')){e.preventDefault();buttons.current[active]?.focus();}
    else if(e.key==='Enter'&&(t===document.body||!t)){e.preventDefault();menu[active].run();}};
    window.addEventListener('keydown',onKey);return()=>window.removeEventListener('keydown',onKey);},[active,cycle,menu]);
  function onMenuKey(e:ReactKeyboardEvent){if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();e.stopPropagation();focusItem(active+(e.key==='ArrowDown'?1:-1));}else if(e.key==='Home'||e.key==='End'){e.preventDefault();focusItem(e.key==='Home'?0:menu.length-1);}}
  const item=menu[active];
  const stats=unit?[
    {label:'生命值',value:unit.initial_stats?.hp||0,max:ranges.hp,text:unit.initial_stats?.hp?String(unit.initial_stats.hp):'不适用'},
    {label:'机动速度',value:unit.speed_reference_mps||0,max:ranges.speed,text:`${(unit.speed_reference_mps||0).toFixed(1)} m/s`},
    {label:'热量上限',value:unit.initial_stats?.max_heat||0,max:ranges.heat,text:unit.initial_stats?.max_heat?String(unit.initial_stats.max_heat):'无发射机构'},
    {label:'电池续航',value:unit.battery_wh||0,max:ranges.battery,text:`${Math.round(unit.battery_wh||0)} Wh`},
  ]:[];
  const caliber=unit?.initial_stats?.damage===200?'42 mm 大弹丸':unit?.initial_stats?.damage?'17 mm 小弹丸':null;

  return <main className="home-page">
    <div className="home-backdrop" aria-hidden="true"><div className="home-glow red"/><div className="home-glow blue"/><div className="home-beam red"/><div className="home-beam blue"/><div className="home-floor"/><div className="home-scan"/>{SPARKS.map((s,i)=><i key={i} className="home-spark" style={{left:`${s.left}%`,animationDelay:`${s.delay}s`,animationDuration:`${s.duration}s`,width:s.size,height:s.size,background:s.hue}}/>)}<div className="home-vignette"/></div>
    <section className="home-stage">
      <div className="home-command">
        <div className="home-logo"><span className="home-kicker"><i/>RMUC 2027 · 2026 · ROBOT STRATEGY LEAGUE</span><h1 className="home-title" aria-label="Arena-1"><span>ARENA</span><em>1</em></h1><p className="home-tagline"><strong>让策略，<b>驱动战场。</b></strong><span>训练你的 Agent，组建 RMUC 2027 五台或 2026 六台机器人的阵容，然后上场。</span></p></div>
        {busy&&<button className="home-live" onClick={onWatch}><span className="home-live-dot"/><b>LIVE</b><span>{live?<>{live.red}<small> vs </small>{live.blue}</>:'比赛进行中'}</span><em><Radio size={14}/>观战</em></button>}
        <nav className="home-menu" aria-label="主菜单" onKeyDown={onMenuKey}>
          {menu.map((m,i)=>{const Icon=m.icon;return <button key={m.id} ref={el=>{buttons.current[i]=el;}} className={`home-menu-item ${i===active?'active':''} ${i===0?'featured':''}`} style={{'--accent':m.accent} as CSSProperties} aria-describedby={i===active?'home-brief':undefined} onMouseEnter={()=>setActive(i)} onFocus={()=>setActive(i)} onClick={m.run}><span className="home-menu-index">{String(i+1).padStart(2,'0')}</span><Icon size={20} className="home-menu-icon"/><span className="home-menu-label"><b>{m.title}</b><small>{m.en}</small></span><ChevronRight size={20} className="home-menu-go"/></button>;})}
        </nav>
        <div className="home-brief" id="home-brief" style={{'--accent':item.accent} as CSSProperties} aria-live="polite"><div key={item.id} className="home-brief-body"><p>{item.brief}</p><div className="home-brief-foot"><div className="home-brief-tags">{item.tags.map(t=><span key={t}>{t}</span>)}</div><button className="home-brief-cta" onClick={item.run}>{item.cta}<kbd>Enter</kbd></button></div></div></div>
      </div>
      <div className="home-showcase">
        <span className="home-corner tl"/><span className="home-corner tr"/><span className="home-corner bl"/><span className="home-corner br"/>
        <div className="home-showcase-head"><span><i/>UNIT SELECT</span>{unit&&<b>{String(shown+1).padStart(2,'0')}<small> / {String(units.length).padStart(2,'0')}</small></b>}</div>
        <div className="home-showcase-stage">{unit?<RobotPreview model={unit} slot={unit.slot>100?Math.floor(unit.slot/100):unit.slot} framing={1.1}/>:<div className="home-showcase-empty"><Bot size={30}/>连接机器人构型库…</div>}
          {units.length>1&&<><button className="home-unit-nav prev" aria-label="上一台机器人" onClick={()=>cycle(-1)}><ChevronLeft size={22}/></button><button className="home-unit-nav next" aria-label="下一台机器人" onClick={()=>cycle(1)}><ChevronRight size={22}/></button></>}</div>
        {unit&&<div key={unit.slot} className="home-unit" aria-live="polite"><div className="home-unit-title"><div><span className="home-unit-role">{ROLE_NAMES[unit.role]}</span><h2>{unit.name}</h2><p>{unit.focus}</p></div><div className="home-unit-chips"><span>{CHASSIS[unit.chassis_type]||unit.chassis_type}</span><span>{unit.mass_kg.toFixed(1)} kg</span>{caliber&&<span>{caliber}</span>}</div></div>
          <div className="home-unit-stats">{stats.map(s=><div key={s.label} className="home-stat"><span>{s.label}</span><div className="home-stat-bar" role="meter" aria-label={s.label} aria-valuemin={0} aria-valuemax={s.max} aria-valuenow={s.value}>{Array.from({length:10},(_,k)=><i key={k} className={k<Math.round(s.value/s.max*10)?'on':''}/>)}</div><b>{s.text}</b></div>)}</div></div>}
      </div>
    </section>
    <div className="home-lobby">
      <div className="home-lobby-stats">
        <span className={connected?'online':'offline'}>{connected?<Wifi size={14}/>:<WifiOff size={14}/>}{connected?'仿真服务器在线':'正在连接服务器'}</span>
        <span><b>5<small>v</small>5</b>RMUC 2027</span>
        <span><b>{Object.keys(models).length||'—'}</b>机器人构型</span>
        <span><b>{Object.keys(catalog).length+Object.keys(cards).length}</b>已保存策略</span>
        {champion&&<span className="home-lobby-champion"><Crown size={14}/>榜首 <b>{champion.name}</b><small>{Math.round(champion.rating)}</small></span>}
      </div>
      <div className="home-keys" aria-hidden="true"><span><kbd>↑</kbd><kbd>↓</kbd>选择模式</span><span><kbd>←</kbd><kbd>→</kbd>切换机体</span><span><kbd>Enter</kbd>确认</span></div>
    </div>
  </main>;
}
