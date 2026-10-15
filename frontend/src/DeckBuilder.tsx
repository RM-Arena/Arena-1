import {useEffect,useMemo,useRef,useState,type DragEvent} from 'react';
import {ArrowDown,ArrowUp,Bot,Check,Copy,FolderOpen,GripVertical,Minus,Plus,Save,Search,SlidersHorizontal,Trash2,X} from 'lucide-react';
import type {DeckPreset,FreeControllers} from './freeBattle';
import {applyDeckTactic,filterRobotGroups,groupRobotCards,strategyLabel} from './deckCatalog';
import {SEASON_LABELS,type CatalogEntry,type RobotHardware,type Role,type Season,type TeamId} from './types';
import {legalIn,legalityIssues} from './TeamLineup';
import './deckBuilder.css';
export const MODEL_NAMES:Record<number,string>={1:'重型英雄',2:'搬运工程',3:'双轮足步兵',4:'爆发步兵',6:'空中机器人',7:'稳健步兵'};
type Decks=Record<TeamId,string[]>;
type DragCard={source:string;team?:TeamId;index?:number};
const DRAG_TYPE='application/x-rmuc-robot';
const ALL_ROLES:[Role|'all',string][]=[['all','全部'],['hero','英雄'],['engineer','工程'],['heavy','重型'],['infantry','步兵'],['sentry','哨兵'],['aerial','空中']];
const TEAM_NAME={red:'红方',blue:'蓝方'};

export function DeckBuilder({cards,decks,onChange,onClose,strategies,controllers,onControllers,season='2026',models={}}:{cards:Record<string,CatalogEntry>;strategies:Record<string,CatalogEntry>;controllers:FreeControllers;onControllers:(value:FreeControllers)=>void;decks:Decks;onChange:(decks:Decks)=>void;onClose:()=>void;season?:Season;models?:Record<string,RobotHardware>}){
  const [team,setTeam]=useState<TeamId>('red'),[query,setQuery]=useState(''),[role,setRole]=useState<Role|'all'>('all'),[model,setModel]=useState(0),[sources,setSources]=useState<Record<number,string>>({}),[quantity,setQuantity]=useState(1),[dragOver,setDragOver]=useState(false);
  const [presets,setPresets]=useState<DeckPreset[]>([]),[presetName,setPresetName]=useState(''),[selectedPreset,setSelectedPreset]=useState(''),[saving,setSaving]=useState(false),[presetError,setPresetError]=useState(''),[saved,setSaved]=useState(false);
  const dialog=useRef<HTMLElement>(null),search=useRef<HTMLInputElement>(null),close=useRef(onClose);close.current=onClose;
  const groups=useMemo(()=>groupRobotCards(cards),[cards]);
  // Only roles with cards in this season; models failing its construction rules are listed apart and cannot be added.
  const ROLES=ALL_ROLES.filter(([id])=>id==='all'||groups.some(g=>g.role===id));
  const excluded=Object.values(models).filter(m=>!legalIn(m,season)&&m.role!=='scout').sort((a,b)=>a.slot-b.slot);
  const filtered=filterRobotGroups(groups,query,role),current=filtered.find(group=>group.model===model)||filtered[0];
  const choice=current&&(current.choices.find(c=>c.id===sources[current.model])||current.choices[0]);
  const other=team==='red'?'blue':'red',independent=controllers[team].mode==='independent';
  const teamStrategies=Object.entries(strategies).filter(([,entry])=>entry.mode==='team');
  const missing=[...decks.red,...decks.blue].some(id=>!cards[id]);
  const invalidController=Object.values(controllers).some(c=>c.mode==='team'&&strategies[c.strategy]?.mode!=='team');
  useEffect(()=>{
    const previous=document.activeElement as HTMLElement|null;search.current?.focus();
    const key=(event:KeyboardEvent)=>{
      if(event.key==='Escape'){event.preventDefault();close.current();}
      if(event.key!=='Tab')return;
      const elements=[...(dialog.current?.querySelectorAll<HTMLElement>('button:not([disabled]),input:not([disabled]),select:not([disabled]),summary')||[])].filter(el=>el.getClientRects().length);
      const first=elements[0],last=elements[elements.length-1];
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
    };
    document.addEventListener('keydown',key);
    return()=>{document.removeEventListener('keydown',key);previous?.focus();};
  },[]);
  useEffect(()=>{let active=true;fetch('/api/deck-presets').then(async r=>{if(!r.ok)throw new Error('无法读取已保存卡组');return r.json();}).then(v=>{if(active)setPresets(v);}).catch(e=>{if(active)setPresetError(e.message);});return()=>{active=false;};},[]);
  useEffect(()=>setSaved(false),[decks,controllers]);
  async function savePreset(){
    setSaving(true);setSaved(false);setPresetError('');
    try{
      const name=presetName.trim();
      const response=await fetch('/api/deck-presets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,decks,controllers,replace:presets.some(p=>p.name===name)})});
      const value=await response.json();
      if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:'保存卡组失败');
      setPresets(old=>[...old.filter(p=>p.name!==name),value]);setSelectedPreset(name);setSaved(true);
    }catch(e){setPresetError((e as Error).message);}finally{setSaving(false);}
  }
  function loadPreset(){const preset=presets.find(p=>p.name===selectedPreset);if(!preset)return;onChange({red:[...preset.decks.red],blue:[...preset.decks.blue]});onControllers(structuredClone(preset.controllers));setPresetName(preset.name);setSaved(false);setPresetError([...preset.decks.red,...preset.decks.blue].some(id=>!cards[id])?'这份卡组有不可用的策略，请更换后再开赛。':'');}
  function insert(target:TeamId,card:DragCard,at=decks[target].length,count=1){
    if(!cards[card.source])return;
    const next=[...decks[target]],moving=card.team===target&&typeof card.index==='number'&&next[card.index]===card.source;
    if(moving){next.splice(card.index!,1);if(card.index!<at)at--;}
    // RMUC 2027: one aerial robot system (hangar) per team.
    const hangar=(id:string)=>cards[id]?.role==='aerial';
    if(season==='2027'&&!moving&&hangar(card.source)&&(count>1||next.some(hangar))){setPresetError(`RMUC 2027 每方最多一套空中机器人系统，${TEAM_NAME[target]}已经有了。`);return;}
    setPresetError('');
    next.splice(at,0,...Array.from({length:count},()=>card.source));onChange({...decks,[target]:next});
  }
  function replace(index:number,source:string){if(cards[source]?.robot===cards[decks[team][index]]?.robot)onChange({...decks,[team]:decks[team].map((id,i)=>i===index?source:id)});}
  function reorder(index:number,delta:number){const next=[...decks[team]],to=index+delta;if(to<0||to>=next.length)return;[next[index],next[to]]=[next[to],next[index]];onChange({...decks,[team]:next});}
  function drag(event:DragEvent,card:DragCard){event.dataTransfer.setData(DRAG_TYPE,JSON.stringify(card));event.dataTransfer.effectAllowed=card.team?'copyMove':'copy';}
  function allow(event:DragEvent){if(Array.from(event.dataTransfer.types).includes(DRAG_TYPE)){event.preventDefault();setDragOver(true);}}
  function drop(event:DragEvent,at?:number){event.preventDefault();event.stopPropagation();setDragOver(false);try{insert(team,JSON.parse(event.dataTransfer.getData(DRAG_TYPE)),at);}catch{/* Ignore unrelated drags. */}}
  return <div className="modal-backdrop free-backdrop"><section ref={dialog} className="free-builder" role="dialog" aria-modal="true" aria-labelledby="free-builder-title">
    <header className="free-header"><div><span className="eyebrow">FREE BATTLE</span><h2 id="free-builder-title">自由对战 · 阵容工坊</h2><p>选机器人，配策略，加入阵容。每台机器人都可以单独搭配。当前规则：{SEASON_LABELS[season]}{season==='2027'?'（每方最多一套空中机器人系统）':''}。</p></div><div className="free-catalog-count"><b>{groups.length}</b> 种型号 <span> / </span><b>{Object.values(cards).filter(c=>c.preset).length}</b> 条预置</div><button className="icon-button" aria-label="关闭卡组编辑器" onClick={onClose}><X size={20}/></button></header>
    <div className="free-workbench">
      <aside className="free-library"><div className="free-section-label"><b>01</b> 选择机器人<span>{filtered.length} 种</span></div><label className="free-search"><Search size={15}/><input ref={search} aria-label="搜索机器人或策略" placeholder="搜索型号、名称或策略" value={query} onChange={e=>setQuery(e.target.value)}/>{query&&<button aria-label="清空搜索" onClick={()=>setQuery('')}><X size={13}/></button>}</label><div className="free-role-filters" aria-label="机器人类型">{ROLES.map(([id,label])=><button key={id} aria-pressed={role===id} onClick={()=>setRole(id)}>{label}</button>)}</div>
        <div className="free-model-list">{filtered.map(group=><button key={group.model} className={`free-model ${current?.model===group.model?'selected':''}`} aria-pressed={current?.model===group.model} onClick={()=>setModel(group.model)}><span className="free-model-id">{group.model}</span><span><strong>{group.name}</strong><small>{group.choices.filter(c=>c.card.preset).length} 条预置{group.choices.some(c=>!c.card.preset)?` · ${group.choices.filter(c=>!c.card.preset).length} 条自定义`:''}</small></span>{current?.model===group.model&&<Check size={14}/>}</button>)}{!filtered.length&&<p className="free-empty">没有找到匹配的机器人。<button onClick={()=>{setQuery('');setRole('all');}}>重置筛选</button></p>}</div>{excluded.length>0&&<details className="free-excluded"><summary>不符合 {SEASON_LABELS[season]} 制作规范的型号 · {excluded.length} 种（不可上场）</summary><ul>{excluded.map(m=><li key={m.slot} title={legalityIssues(m,season)}><b>{m.slot}</b> {m.name}<small>{legalityIssues(m,season)||'该赛季没有此兵种'}</small></li>)}</ul></details>}
      </aside>
      <section className="free-policy"><div className="free-section-label"><b>02</b> 搭配策略</div>{current&&choice?<><div className="free-chosen-model"><Bot size={32}/><span>{current.model}</span><h3>{current.name}</h3></div><div className="free-tactics" role="group" aria-label={`${current.model} 型预置策略`}>{current.choices.filter(c=>c.card.preset).map(c=><button key={c.id} aria-pressed={choice.id===c.id} className={choice.id===c.id?'selected':''} onClick={()=>setSources({...sources,[current.model]:c.id})}><span className="free-radio">{choice.id===c.id&&<Check size={11}/>}</span><span><strong>{c.card.preset!.name}</strong><small>{c.card.preset!.description}</small></span></button>)}</div>{current.choices.some(c=>!c.card.preset)&&<label className="free-custom">自定义策略<select aria-label={`${current.model} 型自定义策略`} value={choice.card.preset?'':choice.id} onChange={e=>{if(e.target.value)setSources({...sources,[current.model]:e.target.value});}}><option value="">选择自定义版本</option>{current.choices.filter(c=>!c.card.preset).map(c=><option key={c.id} value={c.id}>{c.card.name} · {c.card.version.slice(0,8)}</option>)}</select></label>}
        <div className="free-add-area"><div className="free-destination" role="group" aria-label="添加目标">{(['red','blue'] as const).map(t=><button key={t} className={t} aria-label={`添加目标${TEAM_NAME[t]}`} aria-pressed={team===t} onClick={()=>setTeam(t)}>{TEAM_NAME[t]} · {decks[t].length} 台</button>)}</div><div className="free-quantity"><span>添加数量</span><div><button disabled={quantity<=1} aria-label="减少添加数量" onClick={()=>setQuantity(quantity-1)}><Minus size={14}/></button><input type="number" aria-label="添加数量" min={1} max={99} value={quantity} onChange={e=>setQuantity(Math.max(1,Math.min(99,Math.floor(Number(e.target.value))||1)))}/><button disabled={quantity>=99} aria-label="增加添加数量" onClick={()=>setQuantity(quantity+1)}><Plus size={14}/></button></div></div><button className={`free-add ${team}`} onClick={()=>insert(team,{source:choice.id},undefined,quantity)}><Plus size={16}/>加入{TEAM_NAME[team]} · {quantity} 台</button><small>{independent?`当前策略：${strategyLabel(choice.card)}`:'当前由全队策略统一控制'}</small></div></>:<p className="free-empty">选一个机器人开始配置。</p>}</section>
      <section className={`free-roster ${team} ${dragOver?'drag-over':''}`} data-deck-team={team} onDragOver={allow} onDragLeave={event=>{if(!event.currentTarget.contains(event.relatedTarget as Node))setDragOver(false);}} onDrop={event=>drop(event)}><div className="free-section-label"><b>03</b> 上场阵容</div><div className="free-team-tabs" role="group" aria-label="编辑阵营">{(['red','blue'] as const).map(t=><button key={t} className={t} aria-pressed={team===t} onClick={()=>setTeam(t)}><span className={`team-dot ${t}`}/>{TEAM_NAME[t]}<b>{decks[t].length}</b></button>)}</div>
        <div className="free-roster-tools"><select aria-label={`${TEAM_NAME[team]}统一切换预置策略`} value="" disabled={!independent||!decks[team].length} onChange={e=>onChange({...decks,[team]:applyDeckTactic(decks[team],cards,e.target.value)})}><option value="">统一切换预置…</option><option value="balanced">全部使用均衡策略</option><option value="assault">全部使用进攻 / 科技策略</option><option value="guard">全部使用防守 / 救援策略</option></select><button disabled={!decks[other].length} title={`复制${TEAM_NAME[other]}阵容与控制方式`} aria-label={`复制${TEAM_NAME[other]}阵容`} onClick={()=>{onChange({...decks,[team]:[...decks[other]]});onControllers({...controllers,[team]:{...controllers[other]}});}}><Copy size={14}/></button><button disabled={!decks[team].length} title={`清空${TEAM_NAME[team]}`} aria-label={`清空${TEAM_NAME[team]}阵容`} onClick={()=>onChange({...decks,[team]:[]})}><Trash2 size={14}/></button></div>
        <details className="free-control-options" key={team}><summary><SlidersHorizontal size={13}/>{independent?'独立控制 · 每台使用自己的策略':`全队控制 · ${strategies[controllers[team].strategy]?.name||'请选择策略'}`}<span>设置</span></summary><label>控制方式<select aria-label={`${TEAM_NAME[team]}控制方式`} value={controllers[team].mode} onChange={e=>onControllers({...controllers,[team]:{...controllers[team],mode:e.target.value as 'team'|'independent'}})}><option value="independent">独立控制 · 每台一份策略</option><option value="team">全队控制 · 一份策略控制全队</option></select></label>{!independent&&<label>全队策略<select aria-label={`${TEAM_NAME[team]}全队策略`} value={controllers[team].strategy} onChange={e=>onControllers({...controllers,[team]:{...controllers[team],strategy:e.target.value}})}><option value="">选择已保存的全队策略</option>{teamStrategies.map(([id,c])=><option key={id} value={id}>{c.name} · {c.version.slice(0,8)}</option>)}</select></label>}</details>
        <div className="free-deployed-list">{decks[team].map((source,index)=>{const card=cards[source],options=groups.find(g=>g.model===card?.robot)?.choices||[];return <article key={`${team}-${index}`} className={`free-deployed ${card?'':'unavailable'}`} data-deployed-index={index} onDragOver={allow} onDrop={event=>drop(event,index)}><span className="free-slot">{String(index+1).padStart(2,'0')}</span><span className="free-drag-handle" draggable onDragStart={event=>drag(event,{source,team,index})} title="拖动调整出场顺序"><GripVertical size={15}/></span><div><strong>{card?`${card.robot} · ${card.model_name||MODEL_NAMES[card.robot||0]||'机器人'}`:'策略已不可用'}</strong>{independent?<select aria-label={`${TEAM_NAME[team]}第 ${index+1} 台策略`} value={source} disabled={!card} onChange={e=>replace(index,e.target.value)}>{!card&&<option value={source}>{source}</option>}{options.map(c=><option key={c.id} value={c.id}>{strategyLabel(c.card)}{c.card.preset?'':' · 自定义'}</option>)}</select>:<small>全队策略统一控制</small>}</div><div className="free-row-actions"><button aria-label={`上移${TEAM_NAME[team]}第 ${index+1} 台`} disabled={index===0} onClick={()=>reorder(index,-1)}><ArrowUp size={12}/></button><button aria-label={`下移${TEAM_NAME[team]}第 ${index+1} 台`} disabled={index===decks[team].length-1} onClick={()=>reorder(index,1)}><ArrowDown size={12}/></button><button aria-label={`复制${TEAM_NAME[team]}第 ${index+1} 台`} disabled={!card} onClick={()=>insert(team,{source},index+1)}><Copy size={12}/></button><button aria-label={`移除${TEAM_NAME[team]}第 ${index+1} 台`} onClick={()=>onChange({...decks,[team]:decks[team].filter((_,i)=>i!==index)})}><X size={13}/></button></div></article>;})}{!decks[team].length&&<div className="free-roster-empty"><Bot size={34}/><strong>{TEAM_NAME[team]}还没有机器人</strong><p>从左侧选择型号和策略，<br/>点击「加入{TEAM_NAME[team]}」。</p></div>}</div>
        <p className="free-roster-note">{decks[team].length?`${decks[team].length} 台机器人 · 支持重复型号与不同策略`:'数量自由，红蓝双方可以搭配不同阵容'}</p>
      </section>
    </div>
    <details className="free-saves"><summary><FolderOpen size={15}/>保存与加载卡组<span>{presets.length?`${presets.length} 份已保存`:'保存常用搭配，下次直接使用'}</span></summary><div className="free-save-fields"><label>已保存卡组<select aria-label="已保存卡组" value={selectedPreset} onChange={e=>setSelectedPreset(e.target.value)}><option value="">选择卡组</option>{presets.map(p=><option key={p.name} value={p.name}>{p.name}</option>)}</select></label><button disabled={!selectedPreset||saving} onClick={loadPreset}><FolderOpen size={14}/>加载</button><label>卡组名称<input aria-label="卡组名称" value={presetName} maxLength={64} placeholder="例如：轮足突击队" onChange={e=>{setPresetName(e.target.value);setSaved(false);}}/></label><button disabled={saving||!presetName.trim()||!decks.red.length||!decks.blue.length||missing||invalidController} onClick={savePreset}><Save size={14}/>{saving?'保存中…':presets.some(p=>p.name===presetName.trim())?'更新卡组':'保存卡组'}</button></div></details>
    {saved&&<p className="free-feedback" role="status">卡组已保存，可随时加载机器人、策略和控制方式。</p>}{presetError&&<p className="free-feedback error" role="alert">{presetError}</p>}
    <div className="free-footer"><span aria-live="polite">{missing?'有不可用的策略，请移除或加载其他卡组。':invalidController?'请在控制设置中选择可用的全队策略。':!decks.red.length||!decks.blue.length?'红蓝双方各添加至少一台机器人，即可开赛。':`红方 ${decks.red.length} 台 / 蓝方 ${decks.blue.length} 台 · 阵容已就绪`}</span><button className="primary" onClick={onClose}>完成配置<Check size={15}/></button></div>
  </section></div>;
}
