import {useEffect,useMemo,useRef,useState,type CSSProperties,type ChangeEvent,type DragEvent} from 'react';
import {ArrowLeft,ArrowRight,Check,FileCode2,FileJson,Upload,X} from 'lucide-react';
import {MODE_LABELS,ROLE_NAMES,SEASON_LABELS,SEASON_SLOTS,type ControlMode,type RobotHardware,type Season,type StrategyTag,type Tactic,type TeamLineup} from './types';
import {legalIn} from './TeamLineup';
import {LLM_PROVIDERS,PROVIDERS,detectProvider,type AgentProvider} from './agents';
import {AgentBadge,AgentLogo} from './agentLogos';
import './uploadWizard.css';

const TEMPLATE=`from sdk import action, nearest_enemy, aim_at, aim_pitch, navigate, intercept, can_fire

def act(obs, state):
    commands = {}
    for robot in obs["robots"]:
        slot = str(robot["slot"])
        if slot not in obs["controlled_ids"] or not robot["alive"]:
            continue
        target = nearest_enemy(robot, obs)
        if target:
            target = intercept(robot, target)
        commands[slot] = action(
            move=navigate(robot, (20, 12), obs["arena"]),
            aim=aim_at(robot, target) if target else None,
            pitch=aim_pitch(robot, target) if target else 0.04,
            fire=target is not None and can_fire(robot),
            buy_ammo={"amount": 1 if robot["role"]=="hero" else 10, "remote": False},
        )
    return commands, {"ticks": (state or {}).get("ticks", 0) + 1}
`;
export const TACTICS:{id:Tactic;name:string;note:string}[]=[
  {id:'balanced',name:'均衡全能',note:'攻守兼顾，按局势分配兵力'},
  {id:'assault',name:'正面进攻',note:'主动交战，压制敌方机器人'},
  {id:'siege',name:'攻坚推塔',note:'集中火力拆前哨站与基地'},
  {id:'guard',name:'稳守反击',note:'守住己方建筑，等待反击窗口'},
  {id:'economy',name:'运营发育',note:'优先经济、科技与能量机关'},
];
export const TAGS:{id:StrategyTag;name:string}[]=[
  {id:'rune',name:'能量机关'},{id:'assembly',name:'工程科技'},{id:'rescue',name:'救援扶正'},{id:'aerial',name:'空中支援'},{id:'sniping',name:'远程狙击'},
  {id:'mobility',name:'高机动 / 飞坡'},{id:'comms',name:'队内通信'},{id:'focus_fire',name:'集火'},{id:'outpost_rush',name:'速拆前哨'},{id:'base_rush',name:'直取基地'},
];
const MODES:{id:ControlMode;note:string}[]=[
  {id:'team',note:'一个进程控制全队（2027 五台 / 2026 六台），共享 state'},
  {id:'distributed',note:'一次提交每台一份策略，每台独立运行'},
  {id:'squad',note:'每台一份单机策略组成整队'},
  {id:'robot',note:'只控制一个固定编号，等待与队友组队'},
  {id:'adaptive',note:'一台型号的单机策略，可用于自由对战'},
];
const STEPS=['生成者','控制方式','打法','文件','命名'];
type Picked={provider:AgentProvider|null;model:string;manual:boolean};
const readText=(file:File)=>file.text();

// Light client-side check; the server validates the full showcase.json schema.
function previewShowcase(text:string):{ok:true;title:string;tagline:string;phases:number;units:number;provider?:string;model?:string}|{ok:false;error:string}|null{
  if(!text.trim())return null;
  try{const v=JSON.parse(text);if(v?.format!=='rmuc-showcase-v1')return {ok:false,error:'format 必须为 "rmuc-showcase-v1"'};if(!v.title||!v.tagline||!v.summary)return {ok:false,error:'缺少 title / tagline / summary'};if(!v.style||!Array.isArray(v.phases)||!v.phases.length)return {ok:false,error:'缺少 style 或 phases'};
    return {ok:true,title:String(v.title),tagline:String(v.tagline),phases:v.phases.length,units:Array.isArray(v.units)?v.units.length:0,provider:v.generated_by?.provider,model:v.generated_by?.model};}
  catch(e){return {ok:false,error:'不是有效的 JSON：'+(e as Error).message};}
}

export function UploadWizard({onClose,onSave,onGallery,teamLineup,models,initialMode='team',season='2027'}:{onClose:()=>void;onSave:()=>void;onGallery?:()=>void;teamLineup:TeamLineup;models:Record<string,RobotHardware>;initialMode?:ControlMode;season?:Season}){
  // Strategies are written for one rules season: its slots, and for adaptive cards its legal models.
  const slots=SEASON_SLOTS[season];
  const [step,setStep]=useState(0),[agent,setAgent]=useState<Picked>({provider:null,model:'',manual:false});
  const [mode,setMode]=useState<ControlMode>(initialMode),[robot,setRobot]=useState(initialMode==='robot'?'1':'3'),[tactic,setTactic]=useState<Tactic>('balanced'),[tags,setTags]=useState<StrategyTag[]>([]);
  const [codes,setCodes]=useState<Record<string,string>>({}),[fileNames,setFileNames]=useState<Record<string,string>>({}),[slot,setSlot]=useState('1'),[showcase,setShowcase]=useState(''),[showcaseName,setShowcaseName]=useState('');
  const [name,setName]=useState(''),[displayName,setDisplayName]=useState(''),[author,setAuthor]=useState(''),[description,setDescription]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[done,setDone]=useState<string|null>(null),[dragging,setDragging]=useState('');
  const dialog=useRef<HTMLElement>(null),close=useRef(onClose);close.current=onClose;
  const keys=mode==='team'?['team']:mode==='robot'||mode==='adaptive'?[robot]:slots.map(String);
  const detected=agent.model.trim()?detectProvider(agent.model):null;
  const preview=useMemo(()=>previewShowcase(showcase),[showcase]);
  const modelList=useMemo(()=>Object.values(models).filter(m=>mode==='adaptive'?legalIn(m,season):slots.includes(m.slot)).sort((a,b)=>a.slot-b.slot),[models,mode,season,slots]);
  useEffect(()=>{const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){e.preventDefault();close.current();}};document.addEventListener('keydown',key);return()=>document.removeEventListener('keydown',key);},[]);
  useEffect(()=>{dialog.current?.querySelector<HTMLElement>('.uw-body')?.scrollTo({top:0});},[step]);
  // A typed model name picks its maker unless the user chose a tile by hand.
  function typeModel(value:string){const found=value.trim()?detectProvider(value):null;setAgent(a=>({model:value,manual:a.manual,provider:a.manual?a.provider:found}));}
  function pick(provider:AgentProvider){setAgent(a=>({...a,provider,manual:true}));}
  // The agent's self-report in showcase.json fills an empty first answer.
  useEffect(()=>{if(preview?.ok&&preview.provider&&!agent.provider){setAgent(a=>({...a,provider:(preview.provider as AgentProvider) in PROVIDERS?preview.provider as AgentProvider:detectProvider(preview.provider||'')??a.provider,model:a.model||preview.model||''}));}},[preview]);// eslint-disable-line react-hooks/exhaustive-deps
  async function loadCode(key:string,file?:File|null){if(!file)return;if(file.size>512*1024){setError('单份策略不能超过 512 KiB');return;}setCodes(c=>({...c,[key]:''}));const text=await readText(file);setCodes(c=>({...c,[key]:text}));setFileNames(n=>({...n,[key]:file.name}));setError('');}
  async function loadFiles(files:FileList|File[]){
    const list=[...files];const json=list.find(f=>f.name.endsWith('.json'));if(json){setShowcase(await readText(json));setShowcaseName(json.name);}
    const py=list.filter(f=>f.name.endsWith('.py'));
    if(keys.length===1&&py[0])await loadCode(keys[0],py.find(f=>f.name==='strategy.py')||py[0]);
    else for(const f of py){const m=f.name.match(/robot_(\d+)\.py$/);if(m&&keys.includes(m[1]))await loadCode(m[1],f);}
  }
  function drop(e:DragEvent,target:string){e.preventDefault();setDragging('');if(target==='showcase'){const f=e.dataTransfer.files[0];if(f)void readText(f).then(t=>{setShowcase(t);setShowcaseName(f.name);});}else if(target==='all')void loadFiles(e.dataTransfer.files);else void loadCode(target,e.dataTransfer.files[0]);}
  const missingCode=keys.filter(k=>!(codes[k]??'').trim());
  const valid=[!!agent.provider,mode!=='robot'&&mode!=='adaptive'||!!models[robot],true,!missingCode.length&&!!preview?.ok,/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,47}$/.test(name)];
  const hint=['请选择生成者（不确定可选「不确定」）','请选择机器人型号','',missingCode.length?`还缺 ${missingCode.map(k=>k==='team'?'strategy.py':keys.length>1?`robot_${k}.py`:'strategy.py').join('、')}`:!preview?'请上传 showcase.json':preview.ok?'':'showcase.json 有误',name?'版本名只能用字母、数字、- 和 _，以字母或数字开头':'请填写版本名'][step];
  async function submit(){
    setBusy(true);setError('');
    try{
      const entries=Object.fromEntries(keys.map(k=>[k,codes[k]]));
      const profile={agent:{provider:agent.provider,...(agent.model.trim()?{model:agent.model.trim()}:{})},tactic,tags,...(displayName.trim()?{display_name:displayName.trim()}:{}),...(author.trim()?{author:author.trim()}:{}),...(description.trim()?{description:description.trim()}:{})};
      const response=await fetch('/api/submissions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,mode,entries,showcase,profile,season,...(mode==='robot'||mode==='adaptive'?{robot:Number(robot)}:{}),...(mode==='team'?{team_lineup:teamLineup}:{})})});
      const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:Array.isArray(data.detail)?data.detail.map((d:{msg:string;loc:string[]})=>`${d.loc.at(-1)}: ${d.msg}`).join('；'):'提交失败，请检查名称与文件');
      setDone(name);onSave();
    }catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  const chosen=agent.provider,info=chosen?PROVIDERS[chosen]:null;
  return <div className="modal-backdrop uw-backdrop"><section ref={dialog} className="upload-wizard" role="dialog" aria-modal="true" aria-labelledby="uw-title" style={{'--brand':info?.color||'#f2c35b'} as CSSProperties}>
    <header className="uw-head"><div className="uw-head-badge"><AgentBadge provider={chosen||'unknown'} size={54}/></div><div><span className="eyebrow">STRATEGY UPLOAD</span><h2 id="uw-title">上传策略</h2><p>回答几个问题，策略会被正确归类，并在策略库中直观展示。</p></div><button className="icon-button" onClick={onClose} aria-label="关闭"><X size={20}/></button></header>
    {done?<div className="uw-done"><div className="uw-done-badge"><AgentBadge provider={chosen||'unknown'} size={120}/><Check size={34}/></div><h3>「{displayName||done}」已进入策略库</h3><p>{info?.name}{agent.model?` · ${agent.model}`:''} · {MODE_LABELS[mode]} · {TACTICS.find(t=>t.id===tactic)?.name}</p><div className="uw-done-actions">{onGallery&&<button className="primary" onClick={()=>{onGallery();onClose();}}>在策略库查看</button>}<button onClick={onClose}>完成</button></div></div>:<>
    <ol className="uw-steps">{STEPS.map((s,i)=><li key={s} className={i===step?'now':i<step?'done':''}><button disabled={i>step&&!valid.slice(0,i).every(Boolean)} onClick={()=>setStep(i)}><b>{i<step?<Check size={13}/>:i+1}</b>{s}</button></li>)}</ol>
    <div className="uw-body">
      {step===0&&<div className="uw-step"><h3>这个策略是谁生成的？</h3><p className="uw-lead">输入模型名称会自动识别厂商，也可以直接点选。手写的策略选「人类作者」。</p>
        <label className="uw-model"><span>模型名称（可选）</span><input autoFocus placeholder="例如：Claude Opus 5.5、GPT-5、Gemini 3 Pro、Kimi K2、GLM-4.6…" value={agent.model} maxLength={64} onChange={e=>typeModel(e.target.value)}/>{agent.model.trim()&&<em className={detected?'ok':''}>{detected?<><AgentLogo provider={detected} size={16}/>识别为 {PROVIDERS[detected].name}</>:'未能识别，请在下方选择'}</em>}</label>
        <div className="uw-providers" role="radiogroup" aria-label="生成者">{[...LLM_PROVIDERS,'human' as const,'unknown' as const].map(p=><button key={p} role="radio" aria-checked={chosen===p} className={chosen===p?'selected':''} style={{'--c':PROVIDERS[p].color} as CSSProperties} onClick={()=>pick(p)}><AgentLogo provider={p} size={34}/><b>{p==='unknown'?'不确定':PROVIDERS[p].name}</b><small>{PROVIDERS[p].examples}</small>{chosen===p&&<i><Check size={12}/></i>}</button>)}</div></div>}
      {step===1&&<div className="uw-step"><h3>它控制哪些机器人？</h3><p className="uw-lead">决定策略出现在 RM 对战还是自由对战，以及需要几份程序。</p>
        <div className="uw-options">{MODES.map(m=><button key={m.id} className={mode===m.id?'selected':''} aria-pressed={mode===m.id} onClick={()=>{setMode(m.id);if(m.id==='robot'&&!slots.includes(Number(robot)))setRobot('1');}}><b>{MODE_LABELS[m.id]}</b><small>{m.note}</small><span>{m.id==='adaptive'?'自由对战':m.id==='robot'?'组队后参赛':'RM 对战'}</span></button>)}</div>
        {(mode==='robot'||mode==='adaptive')&&<label className="uw-select">{mode==='robot'?'控制的编号 / 型号':'机器人型号'}<select value={robot} onChange={e=>setRobot(e.target.value)}>{mode==='robot'?slots.map(slot=>{const m=models[String(teamLineup[String(slot)])];return <option key={slot} value={slot}>{slot} 号 · {m?`${m.name} · ${ROLE_NAMES[m.role]}`:'—'}</option>;}):modelList.map(m=><option key={m.slot} value={m.slot}>{m.slot} · {m.name} · {ROLE_NAMES[m.role]}</option>)}</select></label>}
        {mode==='team'&&<p className="uw-note">全队策略（{SEASON_LABELS[season]}）随当前共同阵容锁定：{slots.map(s=>`${s}号 ${models[String(teamLineup[String(s)])]?.name||teamLineup[String(s)]}`).join(' · ')}。要换阵容，请先在「选择共同阵容」中调整。</p>}</div>}
      {step===2&&<div className="uw-step"><h3>它怎么打？</h3><p className="uw-lead">选择最接近的主打风格，再勾选它的特色。策略库按这些标签筛选。</p>
        <div className="uw-tactics">{TACTICS.map(t=><button key={t.id} className={tactic===t.id?'selected':''} aria-pressed={tactic===t.id} onClick={()=>setTactic(t.id)}><b>{t.name}</b><small>{t.note}</small></button>)}</div>
        <h4>特色（可多选）</h4><div className="uw-tags">{TAGS.map(t=><button key={t.id} className={tags.includes(t.id)?'selected':''} aria-pressed={tags.includes(t.id)} onClick={()=>setTags(v=>v.includes(t.id)?v.filter(x=>x!==t.id):[...v,t.id])}>{tags.includes(t.id)&&<Check size={12}/>}{t.name}</button>)}</div></div>}
      {step===3&&<div className="uw-step"><h3>上传策略与展示文件</h3><p className="uw-lead">策略库不展示源代码。请同时上传 Agent 按规范写好的 <code>showcase.json</code>，用来呈现打法、阶段、路线和关键决策。<a href="/api/showcase-guide" target="_blank" rel="noreferrer">查看 showcase.json 规范</a></p>
        <div className={`uw-drop ${dragging==='all'?'over':''}`} onDragOver={e=>{e.preventDefault();setDragging('all');}} onDragLeave={()=>setDragging('')} onDrop={e=>drop(e,'all')}><Upload size={20}/><span>把 {keys.length>1?'robot_N.py':'strategy.py'} 和 showcase.json 一起拖到这里</span><label className="uw-pick">选择文件<input type="file" multiple accept=".py,.json" hidden onChange={(e:ChangeEvent<HTMLInputElement>)=>{if(e.target.files)void loadFiles(e.target.files);e.target.value='';}}/></label></div>
        <div className="uw-files">
          <div className="uw-file code"><div className="uw-file-head"><FileCode2 size={16}/><b>策略程序</b>{keys.length>1&&<div className="uw-slot-tabs">{keys.map(k=><button key={k} className={`${slot===k?'active':''} ${codes[k]?.trim()?'ok':''}`} onClick={()=>setSlot(k)}>{k} 号</button>)}</div>}</div>
            {(()=>{const k=keys.length>1?(keys.includes(slot)?slot:keys[0]):keys[0];const label=keys.length>1?`robot_${k}.py`:'strategy.py';return <><div className={`uw-file-drop ${dragging===k?'over':''}`} onDragOver={e=>{e.preventDefault();setDragging(k);}} onDragLeave={()=>setDragging('')} onDrop={e=>drop(e,k)}><span>{fileNames[k]?`已载入 ${fileNames[k]}`:label}</span><label className="uw-pick small">上传<input type="file" accept=".py" hidden onChange={e=>{void loadCode(k,e.target.files?.[0]);e.target.value='';}}/></label>{!codes[k]&&<button className="uw-link" onClick={()=>setCodes(c=>({...c,[k]:TEMPLATE}))}>使用模板</button>}</div>
              <textarea className="uw-code" spellCheck={false} placeholder={`粘贴 ${label}，或上传文件`} value={codes[k]??''} onChange={e=>setCodes(c=>({...c,[k]:e.target.value}))}/><small>{(codes[k]??'').split('\n').length} 行 · {new Blob([codes[k]??'']).size} B · 上限 512 KiB</small></>;})()}
          </div>
          <div className="uw-file json"><div className="uw-file-head"><FileJson size={16}/><b>showcase.json</b>{preview&&<em className={preview.ok?'ok':'bad'}>{preview.ok?'格式正确':'需要修改'}</em>}</div>
            <div className={`uw-file-drop ${dragging==='showcase'?'over':''}`} onDragOver={e=>{e.preventDefault();setDragging('showcase');}} onDragLeave={()=>setDragging('')} onDrop={e=>drop(e,'showcase')}><span>{showcaseName?`已载入 ${showcaseName}`:'showcase.json'}</span><label className="uw-pick small">上传<input type="file" accept=".json,application/json" hidden onChange={e=>{const f=e.target.files?.[0];if(f)void readText(f).then(t=>{setShowcase(t);setShowcaseName(f.name);});e.target.value='';}}/></label></div>
            {preview?.ok?<div className="uw-showcase"><b>{preview.title}</b><span>{preview.tagline}</span><small>{preview.phases} 个阶段 · {preview.units} 个分工{preview.model?` · 自述模型 ${preview.model}`:''}</small><button className="uw-link" onClick={()=>{setShowcase('');setShowcaseName('');}}>重新上传</button></div>:<textarea className="uw-code json" spellCheck={false} placeholder='{"format": "rmuc-showcase-v1", "title": …}' value={showcase} onChange={e=>setShowcase(e.target.value)}/>}
            {preview&&!preview.ok&&<p className="uw-error">{preview.error}</p>}
          </div>
        </div></div>}
      {step===4&&<div className="uw-step"><h3>命名并确认</h3>
        <div className="uw-form"><label>版本名 <small>英文、数字、- 或 _，提交后不可覆盖</small><input autoFocus placeholder="claude-siege-v1" value={name} maxLength={48} onChange={e=>setName(e.target.value)}/></label><label>展示名称 <small>可选，策略库与赛前介绍使用</small><input placeholder={preview?.ok?preview.title:'钢铁洪流'} value={displayName} maxLength={40} onChange={e=>setDisplayName(e.target.value)}/></label><label>作者 <small>可选</small><input placeholder="你的名字或团队" value={author} maxLength={40} onChange={e=>setAuthor(e.target.value)}/></label><label className="wide">补充说明 <small>可选</small><textarea rows={3} maxLength={600} placeholder="开发过程、对手、注意事项…" value={description} onChange={e=>setDescription(e.target.value)}/></label></div>
        <div className="uw-summary"><div><AgentBadge provider={chosen||'unknown'} size={64}/></div><dl><dt>生成者</dt><dd>{info?.name}{agent.model.trim()?` · ${agent.model.trim()}`:''}</dd><dt>控制方式</dt><dd>{MODE_LABELS[mode]}{mode==='robot'||mode==='adaptive'?` · ${models[robot]?.name||robot}`:''}</dd><dt>打法</dt><dd>{TACTICS.find(t=>t.id===tactic)?.name}{tags.length?` · ${tags.map(t=>TAGS.find(x=>x.id===t)?.name).join('、')}`:''}</dd><dt>展示</dt><dd>{preview?.ok?`${preview.title} · ${preview.phases} 个阶段`:'—'}</dd></dl></div></div>}
      {error&&<p className="uw-error" role="alert">{error}</p>}
    </div>
    <footer className="uw-foot"><span>{!valid[step]&&hint}</span>{step>0&&<button onClick={()=>setStep(step-1)}><ArrowLeft size={15}/>上一步</button>}{step<STEPS.length-1?<button className="primary" disabled={!valid[step]} onClick={()=>setStep(step+1)}>下一步<ArrowRight size={15}/></button>:<button className="primary" disabled={busy||!valid.every(Boolean)} onClick={submit}><Upload size={15}/>{busy?'检查并保存…':'检查并提交'}</button>}</footer></>}
  </section></div>;
}
