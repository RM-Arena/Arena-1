import {useEffect,useRef,useState} from 'react';
import {Trash2,X} from 'lucide-react';
import type {MatchRecord} from './types';
import './archive.css';

export function formatBytes(bytes:number){if(bytes>=1e9)return `${(bytes/1e9).toFixed(1)} GB`;if(bytes>=1e6)return `${Math.round(bytes/1e6)} MB`;if(bytes>=1e3)return `${Math.round(bytes/1e3)} KB`;return `${bytes} B`;}

// Deleting removes the journal row and its replay file from this machine; Elo standings keep the games already rated.
export function DeleteMatchDialog({matches,onCancel,onConfirm}:{matches:MatchRecord[];onCancel:()=>void;onConfirm:(onProgress:(done:number)=>void)=>Promise<void>}){
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[progress,setProgress]=useState(0);
  const dialog=useRef<HTMLElement>(null);
  useEffect(()=>{const onKey=(e:KeyboardEvent)=>{if(e.key==='Escape'&&!busy)onCancel();};window.addEventListener('keydown',onKey);return()=>window.removeEventListener('keydown',onKey);},[busy,onCancel]);
  useEffect(()=>{
    const previous=document.activeElement as HTMLElement|null;
    const trap=(event:KeyboardEvent)=>{if(event.key!=='Tab')return;const buttons=[...(dialog.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')||[])];const first=buttons[0],last=buttons[buttons.length-1];if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}else if(!first)event.preventDefault();};
    document.addEventListener('keydown',trap);return()=>{document.removeEventListener('keydown',trap);if(previous?.isConnected)previous.focus();};
  },[]);
  async function confirm(){setBusy(true);setError('');setProgress(0);try{await onConfirm(setProgress);}catch(e){setError((e as Error).message);setBusy(false);}}
  const count=matches.length,replays=matches.filter(m=>m.has_replay).length,bytes=matches.reduce((sum,m)=>sum+(m.replay_bytes||0),0),match=matches[0];
  const {red,blue}=match.metadata.teams;
  return <div className="modal-backdrop" onClick={e=>{if(e.target===e.currentTarget&&!busy)onCancel();}}><section ref={dialog} className="delete-match-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-match-title" aria-describedby="delete-match-note">
    <div className="dialog-heading"><div><span className="eyebrow">MATCH JOURNAL</span><h2 id="delete-match-title"><Trash2 size={19}/>{count===1?'删除这场比赛？':`删除选中的 ${count} 场比赛？`}</h2></div><button className="icon-button" onClick={onCancel} disabled={busy} aria-label="关闭"><X size={19}/></button></div>
    {count===1?<div className="delete-match-summary"><code>{match.id.slice(0,8)}</code><div><span className="text-red">{red.name}</span><span className="vs"> vs </span><span className="text-blue">{blue.name}</span></div><small>{new Date(match.created_at).toLocaleString()} · {match.metadata.map} · SEED {match.metadata.seed}</small></div>:<><div className="delete-batch-summary"><strong>{count} 场比赛</strong><span>{replays} 份回放 · {formatBytes(bytes)}</span></div><div className="delete-batch-list">{matches.slice(0,5).map(m=><div key={m.id}><code>{m.id.slice(0,8)}</code><span>{m.metadata.teams.red.name} vs {m.metadata.teams.blue.name}</span></div>)}{count>5&&<small>另有 {count-5} 场比赛</small>}</div></>}
    <p id="delete-match-note" className="delete-match-note">{count===1?'比赛记录':`选中的 ${count} 场比赛记录`}{replays>0?'和对应回放文件':''}会从本机永久删除，无法恢复。排行榜积分不受影响。</p>
    {error&&<p className="delete-match-error" role="alert">{error}</p>}
    <div className="delete-match-actions"><button onClick={onCancel} disabled={busy} autoFocus>取消</button><button className="danger" onClick={confirm} disabled={busy}><Trash2 size={14}/>{busy?`正在删除 ${progress} / ${count}…`:count===1?'永久删除':`永久删除 ${count} 场`}</button></div>
  </section></div>;
}
