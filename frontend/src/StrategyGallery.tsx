import {Fragment,useEffect,useMemo,useRef,useState,type CSSProperties,type FormEvent,type ReactNode} from 'react';
import {createPortal} from 'react-dom';
import {ArrowLeft,ArrowRight,Check,ChevronDown,CircleAlert,CircleCheck,FileQuestion,FileText,Lock,Pencil,RotateCw,Search,Sparkles,Swords,TriangleAlert,Trophy,Upload,X} from 'lucide-react';
import {MODE_LABELS,ROLE_NAMES,type ControlMode,type Showcase,type StrategyDetail,type StrategySummary,type StrategyTag,type Tactic} from './types';
import {LLM_PROVIDERS,PROVIDERS,detectProvider,providerOf,type AgentProvider} from './agents';
import {AgentBadge} from './agentLogos';
import {FOCUS,STYLE_AXES,TACTICS,TAGS,UNIT_COLORS,PhaseTimeline,StyleRadar,TacticalMap,fallbackShowcase,fallbackStyle,strategyTitle,tacticOf,useArena} from './showcaseViz';
import './gallery.css';
import {StrategyUpdates} from './StrategyUpdates';

// 策略库: every saved strategy as a tactics card drawn from its showcase.json (docs/STRATEGY_SHOWCASE.md) — never its source code.
const AUTHORS:AgentProvider[]=[...LLM_PROVIDERS,'human','unknown'];
const SHORT:Partial<Record<AgentProvider,string>>={'bytedance-seed':'ByteDance'};
const MODE_ORDER:ControlMode[]=['team','distributed','squad','robot','adaptive'];
const TACTIC_ORDER:Tactic[]=['balanced','assault','siege','guard','economy'];
const TAG_ORDER=Object.keys(TAGS) as StrategyTag[];
type Sort='new'|'elo'|'name';
const SORTS:[Sort,string][]=[['new','最新'],['elo','Elo'],['name','名称']];
// The 57 organizer presets (3 per robot model) are near-identical, so they live in a collapsed shelf below the user strategies.
const isPreset=(s:StrategySummary)=>s.official&&s.mode==='adaptive'&&!!s.preset;
const authorOf=(s:StrategySummary)=>providerOf(s.profile?.agent??s.agent);
const stamp=(s:StrategySummary)=>{const t=s.created_at??s.profile?.created_at??0;return t&&t<1e12?t*1000:t;};
const day=(ms:number)=>ms?new Date(ms).toLocaleDateString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit'}):'—';
const bytes=(n:number)=>n<1024?`${n} B`:n<1048576?`${(n/1024).toFixed(1)} KB`:`${(n/1048576).toFixed(2)} MB`;
const light=(color:string)=>`color-mix(in srgb,${color} 76%,#fff)`;
const byTitle=(a:StrategySummary,b:StrategySummary)=>strategyTitle(a).localeCompare(strategyTitle(b),'zh-CN');
const SORTERS:Record<Sort,(a:StrategySummary,b:StrategySummary)=>number>={new:(a,b)=>stamp(b)-stamp(a)||Number(a.official)-Number(b.official)||byTitle(a,b),elo:(a,b)=>(b.standing?.rating??-1)-(a.standing?.rating??-1)||byTitle(a,b),name:byTitle};
function modelLine(s:StrategySummary){const a=s.profile?.agent??s.agent,p=providerOf(a);return a?.model||(p==='human'?s.profile?.author||'人工编写':PROVIDERS[p].maker);}
function haystack(s:StrategySummary){const p=authorOf(s);return [s.name,s.key,strategyTitle(s),s.showcase?.tagline,s.profile?.description,s.profile?.author,s.profile?.agent?.model,PROVIDERS[p].name,PROVIDERS[p].maker,PROVIDERS[p].examples,s.model_name,s.preset?.name,MODE_LABELS[s.mode],TACTICS[tacticOf(s)].name,...(s.profile?.tags||[]).map(t=>TAGS[t])].filter(Boolean).join(' ').toLowerCase();}
function Chips({s}:{s:StrategySummary}){const t=TACTICS[tacticOf(s)];return <><span className="sg-chip mode">{MODE_LABELS[s.mode]}</span>{(s.mode==='adaptive'||s.mode==='robot')&&s.model_name&&<span className="sg-chip model">{s.robot?<b>{s.robot}</b>:null}{s.model_name}</span>}<span className="sg-chip tactic" style={{'--tc':t.color} as CSSProperties}><i/>{t.name}</span></>;}

export function StrategyGallery({onUpload,onBattle,refreshKey}:{onUpload:()=>void;onBattle?:(s:StrategySummary)=>void;refreshKey:number}){
  const [list,setList]=useState<StrategySummary[]|null>(null),[error,setError]=useState(''),[reload,setReload]=useState(0),[loading,setLoading]=useState(false);
  const [authors,setAuthors]=useState<Set<AgentProvider>>(()=>new Set()),[mode,setMode]=useState<ControlMode|'all'>('all'),[tactic,setTactic]=useState<Tactic|'all'>('all'),[query,setQuery]=useState(''),[sort,setSort]=useState<Sort>('new');
  const [presetsOpen,setPresetsOpen]=useState<boolean|null>(null),[openKey,setOpenKey]=useState<string|null>(null);
  useEffect(()=>{let live=true;setLoading(true);setError('');
    fetch('/api/strategies').then(async r=>{if(!r.ok)throw new Error(`策略库读取失败（HTTP ${r.status}）`);return r.json() as Promise<StrategySummary[]>;})
      .then(v=>{if(live)setList(Array.isArray(v)?v:[]);}).catch(e=>{if(live)setError((e as Error).message||'策略库读取失败');}).finally(()=>{if(live)setLoading(false);});
    return()=>{live=false;};},[refreshKey,reload]);
  const all=useMemo(()=>list||[],[list]),index=useMemo(()=>new Map(all.map(s=>[s.key,haystack(s)])),[all]);
  const words=query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  // Each facet counts what the other filters leave, so a chip's number is what clicking it would show.
  const pass=(s:StrategySummary,skip?:'author'|'mode'|'tactic')=>words.every(w=>index.get(s.key)?.includes(w))&&(skip==='author'||!authors.size||authors.has(authorOf(s)))&&(skip==='mode'||mode==='all'||s.mode===mode)&&(skip==='tactic'||tactic==='all'||tacticOf(s)===tactic);
  function facet<K>(skip:'author'|'mode'|'tactic',key:(s:StrategySummary)=>K){const counts=new Map<K,number>();let total=0;for(const s of all)if(pass(s,skip)){counts.set(key(s),(counts.get(key(s))||0)+1);total++;}return {counts,total};}
  const authorFacet=facet('author',authorOf),modeFacet=facet('mode',s=>s.mode),tacticFacet=facet('tactic',tacticOf);
  const shown=all.filter(s=>pass(s)).sort(SORTERS[sort]),main=shown.filter(s=>!isPreset(s)),presets=shown.filter(isPreset);
  const filtered=words.length>0||authors.size>0||mode!=='all'||tactic!=='all',presetsExpanded=presetsOpen??(filtered&&!main.length);
  const open=openKey?all.find(s=>s.key===openKey)??null:null;
  const clear=()=>{setAuthors(new Set());setMode('all');setTactic('all');setQuery('');};
  const toggleAuthor=(p:AgentProvider)=>setAuthors(old=>{const next=new Set(old);if(next.has(p))next.delete(p);else next.add(p);return next;});
  const saved=(v:StrategySummary)=>setList(old=>old?.map(s=>s.key===v.key?{...s,...v}:s)??old);
  const llm=all.filter(s=>(LLM_PROVIDERS as AgentProvider[]).includes(authorOf(s))).length;
  return <section className="sg-page">
    <div className="sg-backdrop" aria-hidden="true"/>
    <header className="sg-head">
      <div className="sg-head-copy"><span className="sg-kicker"><i/>STRATEGY GALLERY</span><h1>策略库</h1><p>每份策略都有一张战术卡：风格雷达、比赛节奏、地图路线与关键决策。不看代码，也能看懂它怎么打。</p></div>
      <div className="sg-head-side">
        <dl className="sg-head-stats"><div><dt>收录策略</dt><dd>{list?all.length:'—'}</dd></div><div><dt>AI 生成</dt><dd>{list?llm:'—'}</dd></div><div><dt>附战术卡</dt><dd>{list?all.filter(s=>s.showcase).length:'—'}</dd></div><div><dt>已上榜</dt><dd>{list?all.filter(s=>s.standing).length:'—'}</dd></div></dl>
        <div className="sg-head-actions"><button className={`sg-icon ${loading?'spin':''}`} aria-label="刷新策略库" title="刷新" disabled={loading} onClick={()=>setReload(n=>n+1)}><RotateCw size={15}/></button><button className="primary sg-upload" onClick={onUpload}><Upload size={15}/>上传策略</button></div>
      </div>
    </header>
    <StrategyUpdates/>
    <div className="sg-filters">
      <div className="sg-filter-row sg-authors" role="group" aria-label="按生成者筛选"><span className="sg-filter-label">生成者</span>
        <div className="sg-author-rail">{AUTHORS.map((p,i)=>{const n=authorFacet.counts.get(p)||0,on=authors.has(p),info=PROVIDERS[p];
          return <Fragment key={p}>{i===LLM_PROVIDERS.length&&<span className="sg-rail-split" aria-hidden="true"/>}<button className={`sg-author ${on?'on':''} ${n?'':'empty'}`} style={{'--pc':info.color} as CSSProperties} aria-pressed={on} aria-label={`${info.name}，${n} 条`} title={`${info.name} · ${info.examples}`} onClick={()=>toggleAuthor(p)}><AgentBadge provider={p} size={30}/><span>{SHORT[p]||info.name}</span><em>{n}</em></button></Fragment>;})}</div>
      </div>
      <div className="sg-filter-row sg-filter-controls">
        <Segmented label="控制模式" value={mode} onChange={setMode} options={[['all','全部',modeFacet.total],...MODE_ORDER.filter(m=>all.some(s=>s.mode===m)).map(m=>[m,MODE_LABELS[m],modeFacet.counts.get(m)||0] as [ControlMode,string,number])]}/>
        <Segmented label="战术" value={tactic} onChange={setTactic} options={[['all','全部',tacticFacet.total],...TACTIC_ORDER.map(t=>[t,TACTICS[t].short,tacticFacet.counts.get(t)||0,TACTICS[t].color] as [Tactic,string,number,string])]}/>
        <label className="sg-search"><Search size={14}/><input type="search" value={query} placeholder="搜索策略、模型、作者、标签" aria-label="搜索策略" onChange={e=>setQuery(e.target.value)}/>{query&&<button type="button" aria-label="清除搜索" onClick={()=>setQuery('')}><X size={13}/></button>}</label>
        <Segmented className="sg-sort" label="排序" value={sort} onChange={setSort} options={SORTS}/>
      </div>
    </div>
    {error&&list&&<p className="sg-inline-error" role="alert"><TriangleAlert size={13}/>{error}，显示的是上次读取的结果。</p>}
    {!list?error?<div className="sg-empty"><CircleAlert size={26}/><p>{error}</p><button onClick={()=>setReload(n=>n+1)}><RotateCw size={14}/>重试</button></div>
      :<div className="sg-grid" aria-busy="true">{Array.from({length:6},(_,i)=><div key={i} className="sg-card sg-skeleton" aria-hidden="true"/>)}</div>
    :!all.length?<div className="sg-empty"><Upload size={26}/><p>策略库还是空的。<br/>上传第一份策略，并附上 showcase.json 战术卡。</p><button className="primary" onClick={onUpload}>上传策略</button></div>
    :<>
      <div className="sg-result" aria-live="polite"><span>{filtered?<>筛选出 <b>{main.length+presets.length}</b> 条 / 共 {all.length} 条</>:<>共 <b>{all.length}</b> 条策略</>}{presets.length>0&&<>，其中预置策略 {presets.length} 条已折叠</>}</span>{filtered&&<button className="sg-clear" onClick={clear}><X size={12}/>清除筛选</button>}</div>
      {main.length?<div className="sg-grid">{main.map((s,i)=><StrategyCard key={s.key} s={s} index={i} onOpen={()=>setOpenKey(s.key)}/>)}</div>
        :<div className="sg-empty compact"><Search size={22}/><p>{presets.length?'没有符合条件的用户策略，下方预置策略中有匹配项。':'没有符合条件的策略。'}</p>{filtered&&<button onClick={clear}>清除筛选</button>}</div>}
      {presets.length>0&&<PresetShelf items={presets} open={presetsExpanded} onToggle={()=>setPresetsOpen(!presetsExpanded)} onOpen={setOpenKey}/>}
    </>}
    {open&&<DetailView s={open} onClose={()=>setOpenKey(null)} onBattle={onBattle} onSaved={saved}/>}
  </section>;
}

function Segmented<T extends string>({label,value,options,onChange,className=''}:{label:string;value:T;options:([T,string]|[T,string,number]|[T,string,number,string])[];onChange:(v:T)=>void;className?:string}){
  return <div className={`sg-seg ${className}`} role="group" aria-label={label}><span className="sg-filter-label">{label}</span><div>{options.map(([v,text,n,color])=><button key={v} type="button" aria-pressed={value===v} className={value===v?'on':''} style={color?{'--tc':color} as CSSProperties:undefined} onClick={()=>onChange(v)}>{color&&<i/>}{text}{n!==undefined&&<em>{n}</em>}</button>)}</div></div>;
}

function StrategyCard({s,index,onOpen}:{s:StrategySummary;index:number;onOpen:()=>void}){
  const p=authorOf(s),info=PROVIDERS[p],title=strategyTitle(s),tagline=s.showcase?.tagline||s.profile?.description||s.preset?.description||TACTICS[tacticOf(s)].brief;
  return <button className={`sg-card ${s.showcase?'':'bare'}`} style={{'--pc':info.color,animationDelay:`${Math.min(index,14)*35}ms`} as CSSProperties} onClick={onOpen} aria-label={`${title}：${info.name} ${modelLine(s)}，${MODE_LABELS[s.mode]}。查看战术卡`}>
    <span className="sg-card-top"><span className="sg-card-badge"><AgentBadge provider={p} size={44}/></span><span className="sg-card-agent"><small>{info.name}</small><b>{modelLine(s)}</b></span><StyleRadar thumb size={60} style={s.showcase?.style??fallbackStyle(s)} color={light(info.color)} auto={!s.showcase}/></span>
    <span className="sg-card-title"><span>{title}</span></span>
    <span className="sg-card-tagline">{tagline}</span>
    <span className="sg-chips"><Chips s={s}/></span>
    <span className="sg-card-foot">{s.standing?<span className="sg-card-elo"><Trophy size={12}/><b>{Math.round(s.standing.rating)}</b><small>{s.standing.wins}胜 {s.standing.losses}负{s.standing.draws?` ${s.standing.draws}平`:''}</small></span>:<span>尚未上榜</span>}
      {s.showcase?<code>{s.version.slice(0,8)}</code>:<span className="sg-card-bare"><FileQuestion size={12}/>暂无展示文件</span>}</span>
  </button>;
}

function PresetShelf({items,open,onToggle,onOpen}:{items:StrategySummary[];open:boolean;onToggle:()=>void;onOpen:(key:string)=>void}){
  const groups=useMemo(()=>{const map=new Map<number,StrategySummary[]>();for(const s of items){const k=s.robot??0;map.set(k,[...(map.get(k)||[]),s]);}
    return [...map].sort((a,b)=>a[0]-b[0]).map(([robot,list])=>({robot,list:[...list].sort((a,b)=>TACTIC_ORDER.indexOf(tacticOf(a))-TACTIC_ORDER.indexOf(tacticOf(b)))}));},[items]);
  return <section className={`sg-presets ${open?'open':''}`}>
    <button className="sg-presets-head" aria-expanded={open} aria-controls="sg-presets-body" onClick={onToggle}><FileText size={38}/><span><b>预置策略</b><small>{groups.length} 种机型 × 每型 3 种战术 · 自由对战时可直接选用</small></span><em>{items.length} 条</em><ChevronDown size={18}/></button>
    {open&&<div id="sg-presets-body" className="sg-preset-grid">{groups.map(g=>{const head=g.list[0];return <div key={g.robot} className="sg-preset-group"><header><b>{g.robot||'—'}</b><span>{head.model_name||`型号 ${g.robot}`}</span>{head.role&&<small>{ROLE_NAMES[head.role]}</small>}</header>
      {g.list.map(s=>{const t=TACTICS[tacticOf(s)];return <button key={s.key} className="sg-preset" style={{'--tc':t.color} as CSSProperties} onClick={()=>onOpen(s.key)}><i/><span><b>{s.preset?.name||t.name}</b><small>{s.preset?.description||t.brief}</small></span>{s.standing?<em title="Elo">{Math.round(s.standing.rating)}</em>:null}<ArrowRight size={14}/></button>;})}</div>;})}</div>}
  </section>;
}

function Section({n,title,en,aside,className='',children}:{n:number;title:string;en:string;aside?:ReactNode;className?:string;children:ReactNode}){
  return <section className={`sg-sec ${className}`} aria-label={title}><header className="sg-sec-head"><b>{String(n).padStart(2,'0')}</b><h3>{title}</h3><small>{en}</small>{aside&&<div className="sg-sec-aside">{aside}</div>}</header>{children}</section>;
}
const Skeleton=({h=16,w='100%'}:{h?:number;w?:string})=><div className="sg-skel" style={{height:h,width:w}} aria-hidden="true"/>;

// What the map symbols mean: landmarks plus how routes and positions are drawn.
function MapKey(){
  const item=(icon:ReactNode,text:string)=><span><svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true">{icon}</svg>{text}</span>;
  return <div className="sg-map-key" aria-label="图例">
    {item(<polygon points="10,2 17,6 17,14 10,18 3,14 3,6" fill="#ff4b5540" stroke="#ff6b70" strokeWidth="1.6"/>,'己方基地')}
    {item(<polygon points="10,2 17,6 17,14 10,18 3,14 3,6" fill="#3aa0ff40" stroke="#5ab4ff" strokeWidth="1.6"/>,'敌方基地')}
    {item(<rect x="5" y="5" width="10" height="10" transform="rotate(45 10 10)" fill="#ff4b5560" stroke="#ff8a8d" strokeWidth="1.4"/>,'前哨站')}
    {item(<><circle cx="10" cy="10" r="7" fill="none" stroke="#f2c35b" strokeWidth="1.4" strokeDasharray="3 2"/><circle cx="10" cy="10" r="2.4" fill="#f2c35b"/></>,'能量机关')}
    {item(<><path d="M2 10H15" stroke="#c9d6de" strokeWidth="2"/><path d="M12 6L17 10L12 14" fill="none" stroke="#c9d6de" strokeWidth="2" strokeLinejoin="round"/></>,'路线与方向')}
    {item(<><circle cx="10" cy="10" r="8" fill="none" stroke="#c9d6de" strokeWidth="1.2" opacity=".5"/><circle cx="10" cy="10" r="5" fill="#c9d6de"/></>,'主要站位')}
  </div>;
}

function DetailView({s,onClose,onBattle,onSaved}:{s:StrategySummary;onClose:()=>void;onBattle?:(s:StrategySummary)=>void;onSaved:(s:StrategySummary)=>void}){
  const [detail,setDetail]=useState<StrategyDetail|null>(null),[error,setError]=useState(''),[retry,setRetry]=useState(0),[editing,setEditing]=useState(false),[hover,setHover]=useState<number|null>(null),[pinned,setPinned]=useState<number|null>(null);
  const panel=useRef<HTMLElement>(null),back=useRef<HTMLButtonElement>(null),escape=useRef(()=>{});
  escape.current=()=>{if(editing)setEditing(false);else onClose();};
  useEffect(()=>{let live=true;setDetail(null);setError('');
    fetch(`/api/strategies/${encodeURIComponent(s.key)}`).then(async r=>{if(!r.ok)throw new Error(`战术卡读取失败（HTTP ${r.status}）`);return r.json() as Promise<StrategyDetail>;})
      .then(v=>{if(live)setDetail(v);}).catch(e=>{if(live)setError((e as Error).message||'战术卡读取失败');});
    return()=>{live=false;};},[s.key,s.version,retry]);
  useEffect(()=>{panel.current?.scrollTo({top:0});setHover(null);setPinned(null);setEditing(false);},[s.key]);
  // Modal behaviour: focus the back button, trap Tab, Esc closes the editor first and then the card, restore focus on close.
  useEffect(()=>{
    const previous=document.activeElement as HTMLElement|null,overflow=document.body.style.overflow;document.body.style.overflow='hidden';back.current?.focus({preventScroll:true});
    const key=(e:KeyboardEvent)=>{
      if(e.key==='Escape'){e.preventDefault();escape.current();return;}
      if(e.key!=='Tab')return;
      const els=[...(panel.current?.querySelectorAll<HTMLElement>('button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex="0"]')||[])].filter(el=>el.getClientRects().length);
      const first=els[0],last=els[els.length-1];if(!first)return;
      if(!panel.current?.contains(document.activeElement)){e.preventDefault();first.focus();}
      else if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}
      else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
    };
    document.addEventListener('keydown',key);
    return()=>{document.removeEventListener('keydown',key);document.body.style.overflow=overflow;previous?.focus?.({preventScroll:true});};
  },[]);
  const arena=useArena(s.season==='2026'?'2026':'2027');
  const p=authorOf(s),info=PROVIDERS[p],color=light(info.color);
  const auto=detail?!detail.showcase:!s.showcase&&!error;
  const show:Showcase|null=detail?.showcase??(auto?fallbackShowcase(s):null);
  const style=show?.style??s.showcase?.style??fallbackStyle(s),title=strategyTitle(s),tagline=show?.tagline??s.showcase?.tagline??'';
  const ranked=STYLE_AXES.map(([k,l])=>({k,l,v:style[k]??0})).sort((a,b)=>b.v-a.v),top=ranked.slice(0,2),low=ranked[ranked.length-1];
  const units=show?.units??[],routed=units.some(u=>u.route?.length>1||u.anchor),focus=hover??pinned;
  let n=0;
  return createPortal(<div className="sg-detail-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose();}}>
    <article ref={panel} className="sg-detail" role="dialog" aria-modal="true" aria-labelledby="sg-detail-title" style={{'--pc':info.color,'--pcl':color} as CSSProperties}>
      <div className="sg-detail-bar"><button ref={back} className="sg-back" onClick={onClose}><ArrowLeft size={16}/>策略库</button><span className="sg-crumb" aria-hidden="true">/ {title}</span><kbd>Esc</kbd><button className="sg-icon ghost" aria-label="关闭战术卡" onClick={onClose}><X size={18}/></button></div>
      <header className="sg-hero">
        <div className="sg-hero-art" aria-hidden="true"/>
        <div className="sg-hero-badge"><span className="sg-halo glow" aria-hidden="true"/><span className="sg-halo" aria-hidden="true"/><AgentBadge provider={p} size={104}/></div>
        <div className="sg-hero-main">
          <span className="sg-hero-kicker"><b>{info.name}</b><i/>{modelLine(s)}{info.maker!==info.name&&p!=='human'&&p!=='unknown'&&<><i/><span>{info.maker}</span></>}</span>
          <h2 id="sg-detail-title">{title}</h2>
          {tagline?<p className="sg-hero-tagline">{tagline}</p>:!show&&<Skeleton h={18} w="60%"/>}
          <div className="sg-chips"><Chips s={s}/>{(s.profile?.tags||[]).map(t=><span key={t} className="sg-chip tag">#{TAGS[t]}</span>)}</div>
          <dl className="sg-hero-meta"><div><dt>作者</dt><dd>{s.profile?.author||(s.profile?.agent??s.agent)?.model||'未署名'}</dd></div><div><dt>版本</dt><dd><code title={s.version}>{s.version.slice(0,8)}</code></dd></div><div><dt>入库</dt><dd>{day(stamp(s))}</dd></div>{s.standing&&<div><dt>Elo</dt><dd className="elo">{Math.round(s.standing.rating)}</dd></div>}</dl>
        </div>
        <div className="sg-hero-actions">{onBattle&&<button className="primary" onClick={()=>onBattle(s)}><Swords size={15}/>用它对战</button>}<button className={editing?'on':''} aria-expanded={editing} onClick={()=>setEditing(v=>!v)}><Pencil size={14}/>编辑分类</button></div>
      </header>
      {editing&&<ProfileEditor key={s.key} s={s} onClose={()=>setEditing(false)} onSaved={onSaved}/>}
      {auto&&<div className="sg-auto"><Sparkles size={15}/><b>自动生成 · 作者未提供 showcase.json</b><span>风格与节奏由战术分类{s.preset?'和预置说明':''}推断，仅供参考；路线与关键决策需作者补充。</span></div>}
      {error&&!detail&&<div className="sg-auto error" role="alert"><TriangleAlert size={15}/><b>{error}</b><button onClick={()=>setRetry(v=>v+1)}><RotateCw size={13}/>重试</button></div>}
      <div className="sg-sections">
        <Section n={++n} title="战术风格" en="PLAY STYLE">
          <div className="sg-style"><StyleRadar style={style} size={300} color={color} auto={auto}/>
            <div className="sg-style-side">{show?<p className="sg-summary">{show.summary}</p>:<div className="sg-skel-stack"><Skeleton/><Skeleton/><Skeleton w="70%"/></div>}
              <div className="sg-insight"><span className="hi">主打 {top.map(a=><b key={a.k}>{a.l} {a.v}</b>)}</span><span className="lo">短板 <b>{low.l} {low.v}</b></span></div>
              <ul className="sg-bars">{STYLE_AXES.map(([k,l],i)=><li key={k} className={top.some(a=>a.k===k)?'top':''}><span>{l}</span><div><i style={{width:`${style[k]??0}%`,animationDelay:`${i*60}ms`}}/></div><b>{style[k]??0}</b></li>)}</ul></div></div>
        </Section>
        <Section n={++n} title="比赛节奏" en="MATCH TEMPO" aside={<div className="sg-focus-key">{Object.entries(FOCUS).map(([k,f])=><span key={k} style={{'--fc':f.color} as CSSProperties}><i/>{f.label}</span>)}</div>}>
          {show?<PhaseTimeline phases={show.phases}/>:<Skeleton h={120}/>}
        </Section>
        <Section n={++n} title="战术地图" en="TACTICAL MAP" aside={<span className="sg-map-hint">己方视角 · 己方基地在左 <ArrowRight size={12}/> 向右进攻</span>}>
          <div className="sg-map-wrap"><div className="sg-map-frame"><TacticalMap units={show?units:[]} arena={arena} focus={focus} onFocus={setHover} note={show&&!routed?'作者未提供路线与站位':undefined}/></div>
            <div className="sg-legend-col"><ul className="sg-legend">{units.map((u,i)=><li key={i}><button className={focus===i?'hot':''} style={{'--uc':UNIT_COLORS[i%UNIT_COLORS.length]} as CSSProperties} aria-pressed={pinned===i} onMouseEnter={()=>setHover(i)} onMouseLeave={()=>setHover(null)} onFocus={()=>setHover(i)} onBlur={()=>setHover(null)} onClick={()=>setPinned(v=>v===i?null:i)}>
              <i>{i+1}</i><span><b>{u.name}</b><em>{u.role}</em></span><p>{u.task}</p>{!(u.route?.length>1)&&!u.anchor&&<small>无路线</small>}</button></li>)}
              {show&&!units.length&&<li className="sg-legend-empty">作者未列出机器人分工。</li>}{!show&&<li><Skeleton h={64}/></li>}</ul><MapKey/></div></div>
        </Section>
        {show&&!auto?<>
          <Section n={++n} title="关键决策" en="KEY DECISIONS">
            {show.priorities.length>0&&<div className="sg-priorities"><span className="sg-sub">目标优先级</span><ol>{show.priorities.map((t,i)=><li key={i}><b>{i+1}</b>{t}</li>)}</ol></div>}
            {show.rules.length>0?<div className="sg-rules">{show.rules.map((r,i)=><div key={i} className="sg-rule" style={{animationDelay:`${i*50}ms`}}><div className="if"><em>IF</em><span>{r.when}</span></div><ArrowRight className="sg-rule-arrow" size={18}/><div className="then"><em>THEN</em><span>{r.then}</span></div></div>)}</div>:<p className="sg-muted">作者未列出关键决策规则。</p>}
          </Section>
          <Section n={++n} title="优势 / 弱点" en="STRENGTHS & WEAKNESSES">
            <div className="sg-pros"><div className="good"><h4><CircleCheck size={15}/>优势</h4>{show.strengths.length?<ul>{show.strengths.map((t,i)=><li key={i}><Check size={13}/>{t}</li>)}</ul>:<p className="sg-muted">未列出</p>}</div>
              <div className="bad"><h4><TriangleAlert size={15}/>弱点</h4>{show.weaknesses.length?<ul>{show.weaknesses.map((t,i)=><li key={i}><X size={13}/>{t}</li>)}</ul>:<p className="sg-muted">未列出</p>}</div></div>
          </Section></>
        :show&&<Section n={++n} title="关键决策 · 优势与弱点" en="NOT PROVIDED"><div className="sg-missing"><FileQuestion size={22}/><div><b>这份策略还没有战术卡</b><p>作者在策略目录写入 showcase.json（格式见 docs/STRATEGY_SHOWCASE.md）并重新上传后，这里会展示路线、关键决策、目标优先级与优劣势。</p></div></div></Section>}
        <Section n={++n} title="战绩" en="RECORD" className="half">
          {s.standing?<div className="sg-record"><div className="sg-elo"><span>ELO</span><b>{Math.round(s.standing.rating)}</b></div>
            <div className="sg-wld"><div className="sg-wld-bar" aria-hidden="true">{s.standing.wins>0&&<i className="w" style={{flex:s.standing.wins}}/>}{s.standing.draws>0&&<i className="d" style={{flex:s.standing.draws}}/>}{s.standing.losses>0&&<i className="l" style={{flex:s.standing.losses}}/>}</div>
              <dl><div><dt>胜</dt><dd className="w">{s.standing.wins}</dd></div><div><dt>平</dt><dd>{s.standing.draws}</dd></div><div><dt>负</dt><dd className="l">{s.standing.losses}</dd></div><div><dt>场次</dt><dd>{s.standing.games}</dd></div><div><dt>胜率</dt><dd>{s.standing.games?Math.round(s.standing.wins/s.standing.games*100):0}%</dd></div></dl></div></div>
          :<p className="sg-muted"><Trophy size={15}/>尚未参加计分比赛。完成有效对战后，这里会显示 Elo 与胜负。</p>}
        </Section>
        <Section n={++n} title="版本与文件" en="VERSION & FILES" className="half">
          <div className="sg-version"><span>版本</span><code>{s.version}</code></div>
          {detail?<div className="sg-files-wrap"><table className="sg-files"><thead><tr><th>文件</th><th>大小</th><th>行数</th><th>SHA-256</th></tr></thead><tbody>{detail.files.map(f=><tr key={f.name}><td><FileText size={12}/><span>{f.name}</span></td><td>{bytes(f.bytes)}</td><td>{f.lines}</td><td><code title={f.sha256}>{f.sha256.slice(0,12)}…</code></td></tr>)}</tbody></table>{!detail.files.length&&<p className="sg-muted">没有文件信息。</p>}</div>:error?null:<div className="sg-skel-stack"><Skeleton/><Skeleton/></div>}
          <p className="sg-note"><Lock size={12}/>源代码不在策略库公开；版本号由代码内容决定，展示文件不影响版本与 Elo。</p>
        </Section>
      </div>
    </article>
  </div>,document.body);
}

function ProfileEditor({s,onClose,onSaved}:{s:StrategySummary;onClose:()=>void;onSaved:(s:StrategySummary)=>void}){
  const p=s.profile,first=useRef<HTMLInputElement>(null);
  const [provider,setProvider]=useState<AgentProvider>(authorOf(s)),[model,setModel]=useState((p?.agent??s.agent)?.model||''),[tactic,setTactic]=useState<Tactic>(tacticOf(s)),[tags,setTags]=useState<StrategyTag[]>(p?.tags||[]);
  const [name,setName]=useState(p?.display_name||''),[author,setAuthor]=useState(p?.author||''),[description,setDescription]=useState(p?.description||''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const choices=AUTHORS;
  useEffect(()=>{first.current?.focus({preventScroll:true});first.current?.scrollIntoView({block:'nearest',behavior:'smooth'});},[]);
  async function submit(e:FormEvent){
    e.preventDefault();setBusy(true);setError('');
    try{
      const body={agent:{provider,...(model.trim()?{model:model.trim()}:{})},tactic,tags:TAG_ORDER.filter(t=>tags.includes(t)),display_name:name.trim(),author:author.trim(),description:description.trim()};
      const r=await fetch(`/api/strategies/${encodeURIComponent(s.key)}/profile`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const value=await r.json().catch(()=>({}));
      if(!r.ok)throw new Error(typeof value?.detail==='string'?value.detail:`保存分类失败（HTTP ${r.status}）`);
      onSaved(value as StrategySummary);onClose();
    }catch(err){setError((err as Error).message||'保存分类失败');}finally{setBusy(false);}
  }
  return <form className="sg-edit" onSubmit={submit} aria-labelledby="sg-edit-title">
    <div className="sg-edit-head"><h3 id="sg-edit-title"><Pencil size={14}/>编辑分类</h3><span>只影响策略库的展示与筛选，不改变策略版本与 Elo。</span></div>
    <fieldset className="sg-edit-authors"><legend>生成者</legend><div>{choices.map(a=><label key={a} className={provider===a?'on':''} style={{'--pc':PROVIDERS[a].color} as CSSProperties} title={PROVIDERS[a].examples}><input type="radio" name="sg-provider" value={a} checked={provider===a} onChange={()=>setProvider(a)}/><AgentBadge provider={a} size={24}/><span>{PROVIDERS[a].name}</span></label>)}</div></fieldset>
    <div className="sg-edit-grid">
      <label><span>模型名称</span><input ref={first} value={model} maxLength={64} placeholder="如 Claude Opus 5.5、GPT-5、Kimi K2" onChange={e=>{const v=e.target.value,d=detectProvider(v);setModel(v);if(d&&provider==='unknown')setProvider(d);}}/></label>
      <label><span>展示名称</span><input value={name} maxLength={40} placeholder={strategyTitle(s)} onChange={e=>setName(e.target.value)}/></label>
      <label><span>作者署名</span><input value={author} maxLength={40} placeholder="可留空" onChange={e=>setAuthor(e.target.value)}/></label>
    </div>
    <fieldset className="sg-edit-tactic"><legend>战术定位</legend><div>{TACTIC_ORDER.map(t=><label key={t} className={tactic===t?'on':''} style={{'--tc':TACTICS[t].color} as CSSProperties}><input type="radio" name="sg-tactic" value={t} checked={tactic===t} onChange={()=>setTactic(t)}/><b>{TACTICS[t].name}</b><small>{TACTICS[t].brief}</small></label>)}</div></fieldset>
    <fieldset className="sg-edit-tags"><legend>标签 · 可多选</legend><div>{TAG_ORDER.map(t=>{const on=tags.includes(t);return <label key={t} className={on?'on':''}><input type="checkbox" checked={on} onChange={()=>setTags(old=>on?old.filter(x=>x!==t):[...old,t])}/>{on&&<Check size={12}/>}{TAGS[t]}</label>;})}</div></fieldset>
    <label className="sg-edit-desc"><span>简介<small>{description.length} / 600</small></span><textarea rows={3} maxLength={600} value={description} placeholder="一两句话说明这份策略怎么打" onChange={e=>setDescription(e.target.value)}/></label>
    {error&&<p className="sg-edit-error" role="alert"><TriangleAlert size={14}/>{error}</p>}
    <div className="sg-edit-actions"><button type="button" onClick={onClose}>取消</button><button type="submit" className="primary" disabled={busy}>{busy?'保存中…':'保存分类'}</button></div>
  </form>;
}
