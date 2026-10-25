import {useEffect,useState,useSyncExternalStore} from 'react';
import {createPortal} from 'react-dom';
import {ArrowDownToLine,Check,CircleAlert,RotateCw,Square,X} from 'lucide-react';
import {clock} from './media';
import type {RecordingSession,SaveJob} from './recording';
import './recording.css';

const STEPS=['上传录像','转码 MP4','保存'] as const;
const megabytes=(n:number)=>n<1048576?`${Math.max(1,Math.round(n/1024))} KB`:`${(n/1048576).toFixed(n<104857600?1:0)} MB`;
const remaining=(s:number)=>s<60?`约剩 ${Math.max(1,s)} 秒`:`约剩 ${Math.floor(s/60)} 分 ${String(s%60).padStart(2,'0')} 秒`;
function step(job:SaveJob){return job.stage==='uploading'?0:job.stage==='transcoding'?1:job.stage==='done'?3:-1;}
function status(job:SaveJob){
  const pct=job.progress===null?null:Math.floor(job.progress*100);
  if(job.stage==='queued')return '等待前一段录像保存完成…';
  if(job.stage==='uploading')return `上传录像 ${pct??0}% · ${megabytes(job.bytes)}`;
  if(job.stage==='transcoding')return pct===null?`转码 MP4 · 已处理 ${clock(job.encoded??0)}`:`转码 MP4 ${pct}%${job.eta!==null?` · ${remaining(job.eta)}`:''}`;
  if(job.stage==='done')return job.kind==='match'?'已保存到「比赛与回放」':job.format==='mp4'?'MP4 已下载':'WebM 已下载（本机没有 MP4 转码组件）';
  return job.error||'录像保存失败';
}

// The fullscreen viewport is the only element the browser shows, so the dock moves into it.
function useHost(){
  const [host,setHost]=useState<Element>(()=>document.fullscreenElement??document.body);
  useEffect(()=>{const sync=()=>setHost(document.fullscreenElement??document.body);document.addEventListener('fullscreenchange',sync);return()=>document.removeEventListener('fullscreenchange',sync);},[]);
  return host;
}

// One place for everything the recorder is doing: the running capture with its clock, and every save
// with the step it is on and how far along it is. Saves continue in the background, so this is what
// tells the viewer that the app is working rather than stuck.
export function RecordingDock({session,onOpenHistory}:{session:RecordingSession;onOpenHistory:()=>void}){
  const state=useSyncExternalStore(session.subscribe,session.getSnapshot),host=useHost();
  const [now,setNow]=useState(()=>Date.now());
  useEffect(()=>{if(!state.capture)return;setNow(Date.now());const id=window.setInterval(()=>setNow(Date.now()),500);return()=>window.clearInterval(id);},[state.capture]);
  if(!state.capture&&!state.starting&&!state.jobs.length)return null;
  const capture=state.capture;
  return createPortal(<aside className="rec-dock" aria-label="录像" role="status" aria-live="polite">
    {state.starting&&!capture&&<div className="rec-row rec-capture"><span className="rec-dot idle"/><b>准备录制…</b></div>}
    {capture&&<div className="rec-row rec-capture">
      <div className="rec-head"><span className="rec-dot"/><b>REC</b><time>{clock((now-capture.startedAt)/1000)}</time><span className="rec-kind">{capture.kind==='match'?'整场录制':'片段录制'}</span>
        <button className="rec-stop" onClick={()=>void session.stop()}><Square size={11} fill="currentColor"/>{capture.kind==='match'?'提前结束':'停止并保存'}</button></div>
      <p>{capture.kind==='match'?'从赛前阵容录到 MVP 结算，MVP 展示后自动结束并保存到「比赛与回放」。录制中请停留在对战页面。':'停止后自动转成 MP4 并下载；录制中请停留在对战页面。'}</p>
    </div>}
    {state.jobs.map(job=>{const at=step(job);return <div key={job.id} className={`rec-row rec-job ${job.stage}`}>
      <div className="rec-head">{job.stage==='done'?<Check size={14} className="rec-icon ok"/>:job.stage==='failed'?<CircleAlert size={14} className="rec-icon bad"/>:<span className="rec-spinner" aria-hidden="true"/>}
        <b>{job.title}</b>{(job.stage==='done'||job.stage==='failed'&&!session.hasOriginal(job))&&<button className="rec-close" aria-label="关闭" onClick={()=>session.dismiss(job.id)}><X size={13}/></button>}</div>
      {job.stage!=='failed'&&job.format==='mp4'&&<ol className="rec-steps">{STEPS.map((label,i)=><li key={label} className={i<at?'done':i===at?'active':''}>{label}</li>)}</ol>}
      {(job.stage==='uploading'||job.stage==='transcoding'||job.stage==='queued')&&<div className={`rec-bar ${job.progress===null?'indeterminate':''}`}><i style={{width:`${(job.progress??0)*100}%`}}/></div>}
      <p className="rec-status">{status(job)}</p>
      {(job.stage==='uploading'||job.stage==='transcoding')&&<p className="rec-hint">保存在后台进行，可以继续操作；请不要关闭窗口。</p>}
      {job.stage==='done'&&job.kind==='match'&&<div className="rec-actions"><button onClick={()=>{onOpenHistory();session.dismiss(job.id);}}>查看录像</button></div>}
      {job.stage==='failed'&&session.hasOriginal(job)&&<div className="rec-actions">{session.canRetry(job)&&<button onClick={()=>session.retry(job.id)}><RotateCw size={12}/>重试</button>}<button onClick={()=>session.saveOriginal(job.id)}><ArrowDownToLine size={12}/>下载原始 WebM</button><button className="rec-discard" onClick={()=>session.dismiss(job.id)}>丢弃</button></div>}
    </div>;})}
  </aside>,host);
}
