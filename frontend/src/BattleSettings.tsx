import {useEffect,useState} from 'react';
import {Download,RotateCcw,Save} from 'lucide-react';
import {SEASON_LABELS,type Season} from './types';
import './matchTools.css';

type Field={path:string;label:string;group:string;min:number;max:number;step:number;unit:string};
type Settings={season:Season;fields:Field[];defaults:Record<string,number>;values:Record<string,number>;overrides:Record<string,number>};
export function BattleSettings({initialSeason='2027'}:{initialSeason?:Season}){
  const [season,setSeason]=useState<Season>(initialSeason),[data,setData]=useState<Settings|null>(null),[values,setValues]=useState<Record<string,number>>({}),[error,setError]=useState(''),[message,setMessage]=useState(''),[saving,setSaving]=useState(false);
  useEffect(()=>{let active=true;setData(null);setError('');setMessage('');fetch('/api/battle-settings?season='+season).then(async r=>{if(!r.ok)throw new Error('无法读取战场设置');return r.json() as Promise<Settings>;}).then(v=>{if(active){setData(v);setValues(v.values);}}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[season]);
  const valid=!!data&&data.fields.every(f=>Number.isFinite(values[f.path])&&values[f.path]>=f.min&&values[f.path]<=f.max);
  const dirty=!!data&&data.fields.some(f=>values[f.path]!==data.values[f.path]);
  const custom=!!data&&data.fields.some(f=>values[f.path]!==data.defaults[f.path]);
  async function save(next:Record<string,number>){setSaving(true);setError('');setMessage('');try{const r=await fetch('/api/battle-settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({season,values:next})});const v=await r.json();if(!r.ok)throw new Error(v.detail||'保存失败');setData(v);setValues(v.values);setMessage(Object.keys(v.overrides).length?'已保存，将用于此赛季的下一场比赛。':'已恢复当前版本的默认参数。');}catch(e){setError((e as Error).message);}finally{setSaving(false);}}
  function exportSettings(){if(!data)return;const overrides=Object.fromEntries(data.fields.filter(f=>values[f.path]!==data.defaults[f.path]).map(f=>[f.path,values[f.path]]));const url=URL.createObjectURL(new Blob([JSON.stringify(overrides,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`battle-settings-${season}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  return <section className="archive-page battle-settings-page"><div className="archive-heading"><div><span className="eyebrow">BATTLE SETTINGS</span><h1>按你的参数开一场对局。</h1><p>红蓝双方使用同一组参数。非默认参数的比赛标为测试赛，不计 Elo；每场回放保留当时的参数。</p></div><select aria-label="设置赛季" value={season} disabled={saving} onChange={e=>setSeason(e.target.value as Season)}>{(['2027','2026'] as const).map(s=><option key={s} value={s}>{SEASON_LABELS[s]}</option>)}</select></div>
    <div className="settings-actions"><span>{dirty?'有未保存的更改':custom?'已使用自定义参数':'使用默认参数'} · 仅影响下一场比赛</span><button disabled={!data||saving} onClick={()=>save({})}><RotateCcw size={14}/>恢复默认</button><button disabled={!valid||saving} onClick={exportSettings}><Download size={14}/>导出 CLI 参数</button><button className="primary" disabled={!valid||saving||!dirty} onClick={()=>save(values)}><Save size={14}/>{saving?'保存中…':'保存设置'}</button></div>
    {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
    {!data&&!error?<p>载入设置…</p>:data&&[...new Set(data.fields.map(f=>f.group))].map(group=><section key={group} className="settings-group"><h2>{group}</h2><div className="settings-grid">{data.fields.filter(f=>f.group===group).map(f=><label key={f.path}>{f.label}<span><input aria-label={f.label} type="number" min={f.min} max={f.max} step={f.step} value={Number.isFinite(values[f.path])?values[f.path]:''} disabled={saving} onChange={e=>{setValues(v=>({...v,[f.path]:e.target.value===''?NaN:Number(e.target.value)}));setMessage('');}}/><em>{f.unit}</em></span><small>默认 {data.defaults[f.path]}{f.unit} · 范围 {f.min}–{f.max}</small></label>)}</div></section>)}
    <div className="headless-command"><h2>无界面运行</h2><code>uv run --locked python -m rmuc_arena headless --output replays/headless.json</code><p>在终端运行，无需桌面或浏览器，完成后输出结果并保存 JSON 回放。可使用 --red、--blue、--seed、--duration 和 --settings battle-settings-2027.json。运行自己的可信代码时可加 --trusted-local；默认使用 Docker。批量评测使用 batch --games 10 --swap-sides。</p><p>终端计算模式生成可复现的 JSON 回放；完整广播 MP4 在观战页面勾选保存。</p></div>
  </section>;
}
