import {useEffect,useMemo,useState,type ChangeEvent,type DragEvent} from 'react';
import {Box,Check,Palette,Trash2,Upload,X} from 'lucide-react';
import {ROLE_NAMES,type RobotHardware,type RobotSkin,type TeamId} from './types';
import {RobotPreview} from './RobotPreview';
import {robotImage} from './thumbnails';
import './modelWorkshop.css';

export type CustomModel=RobotSkin&{role?:string;base_name?:string;triangles?:number;meshes?:number};
const AXES:{id:RobotSkin['forward'];label:string}[]=[{id:'+x',label:'+X'},{id:'-x',label:'−X'},{id:'+z',label:'+Z'},{id:'-z',label:'−Z'}];
const ROLE_ORDER=['heavy','hero','engineer','infantry','sentry','aerial'];
const mb=(n=0)=>n>1048576?`${(n/1048576).toFixed(1)} MB`:`${Math.round(n/1024)} KB`;
async function base64(file:File){const bytes=new Uint8Array(await file.arrayBuffer());let out='';for(let i=0;i<bytes.length;i+=0x8000)out+=String.fromCharCode(...bytes.subarray(i,i+0x8000));return btoa(out);}

function Thumb({asset}:{asset:string}){
  const [src,setSrc]=useState('');
  useEffect(()=>{let live=true;robotImage(asset,'red','card').then(png=>{if(live)setSrc(png);}).catch(()=>{});return()=>{live=false;};},[asset]);
  return src?<img src={src} alt=""/>:<span className="mw-thumb-wait"><Box size={22}/></span>;
}

// Upload a GLB as the appearance of one hardware model; the simulated physics stay those of the base model.
export function ModelWorkshop({models,customs,onChanged}:{models:Record<string,RobotHardware>;customs:CustomModel[];onChanged:()=>void}){
  const designs=useMemo(()=>Object.values(models).sort((a,b)=>ROLE_ORDER.indexOf(a.role)-ROLE_ORDER.indexOf(b.role)||a.slot-b.slot),[models]);
  const [file,setFile]=useState<File|null>(null),[blob,setBlob]=useState(''),[name,setName]=useState(''),[base,setBase]=useState('3'),[forward,setForward]=useState<RobotSkin['forward']>('+x'),[author,setAuthor]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[viewing,setViewing]=useState<string|null>(null),[over,setOver]=useState(false);
  useEffect(()=>()=>{if(blob)URL.revokeObjectURL(blob);},[blob]);
  const design=models[base];
  const shown=viewing?customs.find(c=>c.id===viewing):null;
  const previewModel=useMemo(()=>{
    if(shown){const hw=models[String(shown.base_model)];return hw?{...hw,name:shown.name,asset:shown.asset}:null;}
    if(blob&&design)return {...design,name:name||file?.name||design.name,asset:`${blob}#fit=${design.stowed_m.join(',')}&fwd=${forward}`};
    return design||null;
  },[shown,blob,design,forward,name,file,models]);
  function choose(next?:File|null){
    if(!next)return;setError('');setNotice('');
    if(!next.name.toLowerCase().endsWith('.glb')){setError('请上传二进制 glTF（.glb）文件；.gltf 需先导出为 .glb');return;}
    if(next.size>24*1048576){setError('模型不能超过 24 MB');return;}
    if(blob)URL.revokeObjectURL(blob);setBlob(URL.createObjectURL(next));setFile(next);setViewing(null);if(!name)setName(next.name.replace(/\.glb$/i,'').slice(0,40));
  }
  async function upload(){
    if(!file)return;setBusy(true);setError('');
    try{const response=await fetch('/api/custom-models',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name.trim(),base_model:Number(base),forward,...(author.trim()?{author:author.trim()}:{}),glb_base64:await base64(file)})});
      const value=await response.json();if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:'上传失败');
      setNotice(`「${value.name}」已加入模型库，可在对战的「机器人外观」中选用。`);setFile(null);if(blob)URL.revokeObjectURL(blob);setBlob('');setName('');setViewing(value.id);onChanged();
    }catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  async function remove(model:CustomModel){
    if(!window.confirm(`删除外观「${model.name}」？已保存的回放会改用原型号外观。`))return;
    const response=await fetch('/api/custom-models/'+model.id,{method:'DELETE'});if(!response.ok){setError('删除失败');return;}
    if(viewing===model.id)setViewing(null);onChanged();
  }
  function drop(e:DragEvent){e.preventDefault();setOver(false);choose(e.dataTransfer.files[0]);}
  return <section className="model-workshop">
    <div className="mw-editor">
      <div className="mw-stage">{previewModel?<RobotPreview key={previewModel.asset} model={previewModel} slot={previewModel.slot>100?Math.floor(previewModel.slot/100):previewModel.slot} framing={1.05}/>:<div className="mw-empty"><Box size={30}/>加载机器人型号…</div>}
        <span className="mw-stage-tag">{shown?`已上传 · ${shown.name}`:blob?'本地预览 · 尚未上传':`原型号 · ${design?.name||''}`}</span></div>
      <div className="mw-form">
        <div className={`mw-drop ${over?'over':''} ${file?'ready':''}`} onDragOver={e=>{e.preventDefault();setOver(true);}} onDragLeave={()=>setOver(false)} onDrop={drop}>
          <Upload size={22}/><div><b>{file?file.name:'拖入 .glb 模型文件'}</b><small>{file?mb(file.size):'glTF 2.0 二进制，贴图需内嵌，≤ 24 MB'}</small></div>
          <label className="mw-pick">选择文件<input type="file" accept=".glb,model/gltf-binary" hidden onChange={(e:ChangeEvent<HTMLInputElement>)=>{choose(e.target.files?.[0]);e.target.value='';}}/></label></div>
        <label>外观名称<input value={name} maxLength={40} placeholder="例如：赤焰战车" onChange={e=>setName(e.target.value)}/></label>
        <label>替换的机器人型号<select value={base} onChange={e=>{setBase(e.target.value);setViewing(null);}}>{designs.map(m=><option key={m.slot} value={m.slot}>{m.slot} · {m.name} · {ROLE_NAMES[m.role]}</option>)}</select><small>比赛仍按该型号的硬件与规则仿真；模型缩放到 {design?design.stowed_m.map(v=>v.toFixed(2)).join(' × '):'—'} m 的收纳尺寸内。</small></label>
        <div className="mw-axis"><span>模型正前方</span><div role="radiogroup" aria-label="模型正前方">{AXES.map(a=><button key={a.id} role="radio" aria-checked={forward===a.id} className={forward===a.id?'selected':''} onClick={()=>setForward(a.id)}>{a.label}</button>)}</div><small>底座光环上的三角标记是机器人的正前方（炮口方向）；模型朝向不对时换一个轴。</small></div>
        <label>作者 <small>可选</small><input value={author} maxLength={40} onChange={e=>setAuthor(e.target.value)}/></label>
        {error&&<p className="mw-error" role="alert">{error}</p>}{notice&&<p className="mw-notice" role="status"><Check size={14}/>{notice}</p>}
        <button className="primary" disabled={!file||!name.trim()||busy} onClick={upload}><Upload size={15}/>{busy?'正在检查并上传…':'上传到模型库'}</button>
      </div>
    </div>
    <div className="mw-library"><div className="mw-library-head"><Palette size={16}/><b>已上传的外观</b><span>{customs.length} 个</span></div>
      {customs.length?<div className="mw-grid">{customs.map(c=><article key={c.id} className={viewing===c.id?'selected':''}>
        <button className="mw-card" onClick={()=>setViewing(viewing===c.id?null:c.id)} aria-pressed={viewing===c.id}><span className="mw-thumb"><Thumb asset={c.asset}/></span><b>{c.name}</b><small>{c.base_model} 型 · {c.base_name||models[String(c.base_model)]?.name}</small><small>{(c.triangles||0).toLocaleString()} 三角面 · {mb(c.bytes)}{c.author?` · ${c.author}`:''}</small></button>
        <button className="mw-delete" aria-label={`删除 ${c.name}`} title="删除" onClick={()=>remove(c)}><Trash2 size={14}/></button></article>)}</div>
        :<p className="mw-none">还没有自定义外观。上传一个 .glb 模型，选择它替换的型号即可。</p>}
    </div>
  </section>;
}

// Per-match appearance choice: each hardware model a team fields may use one uploaded mesh.
export function SkinPicker({models,customs,fielded,value,onChange,onClose,onManage}:{models:Record<string,RobotHardware>;customs:CustomModel[];fielded:Record<TeamId,number[]>;value:Record<TeamId,Record<string,string>>;onChange:(value:Record<TeamId,Record<string,string>>)=>void;onClose:()=>void;onManage:()=>void}){
  useEffect(()=>{const key=(e:KeyboardEvent)=>{if(e.key==='Escape')onClose();};document.addEventListener('keydown',key);return()=>document.removeEventListener('keydown',key);},[onClose]);
  const set=(team:TeamId,model:number,id:string)=>{const next={...value[team]};if(id)next[String(model)]=id;else delete next[String(model)];onChange({...value,[team]:next});};
  return <div className="modal-backdrop"><section className="skin-picker" role="dialog" aria-modal="true" aria-labelledby="skin-title">
    <header><div><span className="eyebrow">ROBOT APPEARANCE</span><h2 id="skin-title">机器人外观</h2><p>为上场的型号换上自定义模型；仿真、装甲与规则保持原型号。</p></div><button className="icon-button" onClick={onClose} aria-label="关闭"><X size={20}/></button></header>
    <div className="skin-teams">{(['red','blue'] as const).map(team=><div key={team} className={`skin-team ${team}`}><h3><span className={`team-dot ${team}`}/>{team==='red'?'红方':'蓝方'}</h3>
      {[...new Set(fielded[team])].sort((a,b)=>a-b).map(model=>{const options=customs.filter(c=>c.base_model===model),chosen=value[team]?.[String(model)];return <label key={model} className={options.length?'':'empty'}><span><b>{model}</b>{models[String(model)]?.name||`${model} 型`}<small>×{fielded[team].filter(m=>m===model).length}</small></span>
        <select value={options.some(o=>o.id===chosen)?chosen:''} disabled={!options.length} onChange={e=>set(team,model,e.target.value)}><option value="">{options.length?'默认外观':'无可用外观'}</option>{options.map(o=><option key={o.id} value={o.id}>{o.name}</option>)}</select></label>;})}
      {!fielded[team].length&&<p className="skin-none">还没有上场机器人</p>}</div>)}</div>
    <footer><button onClick={onManage}><Upload size={14}/>上传新模型</button><button className="primary" onClick={onClose}>完成</button></footer>
  </section></div>;
}
