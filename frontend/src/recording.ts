import {download,type BroadcastRecorder} from './media';

// Recording is one capture at a time — the broadcast canvas with its soundtrack — plus a queue of
// saves. A capture never waits for its save: once the recorder stops, the field, the ceremony and the
// other pages are usable again while the recording uploads and converts, and the dock reports each
// step with its progress. Two kinds of capture exist:
//   match: the whole match (walk-on to MVP card), filed as MP4 in 比赛与回放.
//   clip:  whatever the viewer records by hand, downloaded as MP4 (WebM when the converter is missing).
export type CaptureKind='match'|'clip';
export interface Capture{kind:CaptureKind;matchId:string|null;startedAt:number}
export type SaveStage='queued'|'uploading'|'transcoding'|'done'|'failed';
export interface SaveJob{id:string;kind:CaptureKind;matchId:string|null;title:string;format:'mp4'|'webm';bytes:number;duration:number;
  stage:SaveStage;progress:number|null;encoded:number|null;eta:number|null;error:string|null;finishedAt:number|null}
export interface RecordingSnapshot{starting:boolean;capture:Capture|null;jobs:SaveJob[]}

const MAX_BYTES=1024*1024*1024;
// A finished save stays in the dock this long before it folds away on its own.
export const DONE_SECONDS=12;

// One upload with byte progress (fetch() cannot report upload progress, so the default is XHR).
// `onSent` fires when the last byte has left: from then on the server is converting.
export type Transport=(url:string,blob:Blob,responseType:'json'|'blob',onUpload:(fraction:number)=>void,onSent:()=>void)=>Promise<{status:number;body:unknown}>;
const xhrTransport:Transport=(url,blob,responseType,onUpload,onSent)=>new Promise((resolve,reject)=>{
  const xhr=new XMLHttpRequest();xhr.open('POST',url);xhr.responseType=responseType;xhr.setRequestHeader('Content-Type','video/webm');
  xhr.upload.onprogress=e=>{if(e.lengthComputable)onUpload(e.loaded/e.total);};
  xhr.upload.onload=()=>onSent();
  xhr.onload=()=>resolve({status:xhr.status,body:xhr.response});
  xhr.onerror=()=>reject(new Error('无法连接本地服务，录像没有保存'));
  xhr.onabort=()=>reject(new Error('录像上传被中断'));
  xhr.send(blob);
});

async function errorText(body:unknown,status:number){
  try{
    const value=(body instanceof Blob?JSON.parse(await body.text()):body) as {detail?:unknown;error?:unknown}|null;
    if(typeof value?.detail==='string')return value.detail;
    if(typeof value?.error==='string')return value.error;
  }catch{/* not JSON: fall through to the status */}
  return `录像保存失败（HTTP ${status}）`;
}
const stamp=()=>new Date().toISOString().slice(0,19).replaceAll(':','-');

interface Options{fetch?:typeof fetch;transport?:Transport;save?:(blob:Blob,name:string)=>void;onSaved?:(job:SaveJob)=>void;poll?:number;later?:(run:()=>void,ms:number)=>void}

export class RecordingSession{
  private snapshot:RecordingSnapshot={starting:false,capture:null,jobs:[]};
  private listeners=new Set<()=>void>();
  // The captured WebM of every unfinished save, kept for a retry or an explicit download. Dropped as
  // soon as the save succeeds — a whole match is several hundred megabytes.
  private blobs=new Map<string,Blob>();
  private format:'mp4'|'webm'='mp4';private stopping=false;private running=false;private serial=0;
  constructor(private recorder:BroadcastRecorder,private options:Options={}){}
  subscribe=(listener:()=>void)=>{this.listeners.add(listener);return()=>{this.listeners.delete(listener);};};
  getSnapshot=()=>this.snapshot;
  // Something the page must not be closed during: a capture, or a save that has not reached the disk.
  get busy(){const s=this.snapshot;return s.starting||!!s.capture||s.jobs.some(j=>j.stage==='queued'||j.stage==='uploading'||j.stage==='transcoding');}
  // Called unbound: window.fetch refuses to run with the session as `this`.
  private request(url:string){return (this.options.fetch??fetch)(url);}
  private later(run:()=>void,ms:number){if(this.options.later)this.options.later(run,ms);else setTimeout(run,ms);}
  private set(patch:Partial<RecordingSnapshot>){this.snapshot={...this.snapshot,...patch};for(const listener of this.listeners)listener();}
  private update(id:string,patch:Partial<SaveJob>){this.set({jobs:this.snapshot.jobs.map(job=>job.id===id?{...job,...patch}:job)});}

  async start(kind:CaptureKind,matchId:string|null=null){
    if(this.snapshot.capture||this.snapshot.starting)throw new Error('录像已经开始');
    this.set({starting:true});
    try{
      // A match recording is filed as MP4, so it needs the converter up front; a clip without one
      // still downloads as WebM.
      const response=await this.request('/api/video-export');
      if(!response.ok)throw new Error(await errorText(await response.json().catch(()=>null),response.status));
      const mp4=!!(await response.json()).mp4;
      if(kind==='match'&&!mp4)throw new Error('MP4 转码组件不可用，无法保存整场录像；请更新应用或重新运行环境安装。');
      await this.recorder.start();
      this.format=mp4?'mp4':'webm';
      this.set({starting:false,capture:{kind,matchId,startedAt:Date.now()}});
    }catch(error){this.set({starting:false});throw error;}
  }
  // The match id is only known once the server accepted the start request.
  attach(matchId:string){const capture=this.snapshot.capture;if(capture)this.set({capture:{...capture,matchId}});}
  // Abandons the capture without saving it (the match it was meant for never started).
  async cancel(){if(!this.snapshot.capture&&!this.snapshot.starting)return;await this.recorder.cancel();this.set({capture:null,starting:false});}

  // Ends the capture and queues its save; resolves as soon as the recorder has flushed.
  async stop(){
    const capture=this.snapshot.capture;if(!capture||this.stopping)return null;
    this.stopping=true;
    try{
      const {blob,duration,error}=await this.recorder.stop();
      const id=`rec-${Date.now().toString(36)}-${(++this.serial).toString(36)}`;
      const job:SaveJob={id,kind:capture.kind,matchId:capture.matchId,format:this.format,bytes:blob.size,duration,stage:'queued',progress:null,encoded:null,eta:null,error:null,finishedAt:null,
        title:capture.kind==='match'?`整场录像 · ${capture.matchId?.slice(0,8)??'未开始的比赛'}`:`录像片段 · ${new Date().toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})}`};
      this.blobs.set(id,blob);
      this.set({capture:null,jobs:[...this.snapshot.jobs,job]});
      if(error)this.fail(id,`${error}，原始 WebM 已保留`);
      else if(capture.kind==='match'&&!capture.matchId)this.fail(id,'这段录像没有对应的比赛，原始 WebM 已保留');
      else void this.pump();
      return job;
    }finally{this.stopping=false;}
  }

  retry(id:string){const job=this.snapshot.jobs.find(j=>j.id===id);if(job?.stage!=='failed'||!this.blobs.has(id))return;this.update(id,{stage:'queued',error:null,progress:null});void this.pump();}
  canRetry(job:SaveJob){return job.stage==='failed'&&this.blobs.has(job.id)&&(job.kind==='clip'||!!job.matchId);}
  hasOriginal(job:SaveJob){return this.blobs.has(job.id);}
  saveOriginal(id:string){const blob=this.blobs.get(id),job=this.snapshot.jobs.find(j=>j.id===id);if(!blob||!job)return;this.output(blob,`${job.matchId?`rmuc-${job.matchId}`:`rmuc-arena-${stamp()}`}.webm`);this.dismiss(id);}
  dismiss(id:string){const job=this.snapshot.jobs.find(j=>j.id===id);if(!job||job.stage==='uploading'||job.stage==='transcoding')return;this.blobs.delete(id);this.set({jobs:this.snapshot.jobs.filter(j=>j.id!==id)});}

  private output(blob:Blob,name:string){(this.options.save??download)(blob,name);}
  private fail(id:string,message:string){this.update(id,{stage:'failed',error:message,progress:null,eta:null});}
  private finish(job:SaveJob){
    this.blobs.delete(job.id);
    this.update(job.id,{stage:'done',progress:1,eta:null,finishedAt:Date.now()});
    this.options.onSaved?.(job);
    this.later(()=>this.dismiss(job.id),DONE_SECONDS*1000);
  }
  // Saves run one at a time: the local converter takes one recording at a time.
  private async pump(){
    if(this.running)return;this.running=true;
    try{for(let job=this.snapshot.jobs.find(j=>j.stage==='queued');job;job=this.snapshot.jobs.find(j=>j.stage==='queued'))await this.save(job);}
    finally{this.running=false;}
  }
  private async save(job:SaveJob){
    const blob=this.blobs.get(job.id);
    if(!blob){this.fail(job.id,'原始录像已丢弃');return;}
    const name=job.matchId?`rmuc-${job.matchId}`:`rmuc-arena-${stamp()}`;
    let settled=false;
    try{
      if(!blob.size)throw new Error('录像为空，请录制画面后再保存。');
      if(job.format==='webm'){this.output(blob,`${name}.webm`);this.finish(job);return;}
      if(blob.size>MAX_BYTES)throw new Error('录像超过 1 GiB，无法转成 MP4。');
      const query=`?duration=${job.duration.toFixed(3)}&job=${job.id}`;
      const url=job.kind==='match'?`/api/matches/${encodeURIComponent(job.matchId!)}/video${query}`:`/api/video-export${query}`;
      this.update(job.id,{stage:'uploading',progress:0,error:null});
      const response=await(this.options.transport??xhrTransport)(url,blob,job.kind==='match'?'json':'blob',
        fraction=>{if(!settled)this.update(job.id,{progress:Math.min(1,fraction)});},
        ()=>{if(settled)return;this.update(job.id,{stage:'transcoding',progress:0,encoded:0});void this.watch(job,()=>settled);});
      settled=true;
      if(response.status<200||response.status>=300)throw new Error(await errorText(response.body,response.status));
      if(job.kind==='clip'){
        const mp4=response.body;
        if(!(mp4 instanceof Blob)||!mp4.size||!mp4.type.startsWith('video/mp4'))throw new Error('未能生成有效的 MP4 文件。');
        this.output(mp4,`${name}.mp4`);
      }
      this.finish(job);
    }catch(error){settled=true;this.fail(job.id,(error as Error).message||'录像保存失败');}
  }
  // While the server converts, its progress report is read a few times a second; the remaining time
  // is extrapolated from the encoded fraction once it has moved enough to be meaningful.
  private async watch(job:SaveJob,done:()=>boolean){
    const began=Date.now(),wait=()=>new Promise<void>(resolve=>this.later(resolve,this.options.poll??500));
    while(!done()){
      await wait();if(done())return;
      try{
        const response=await this.request(`/api/video-export/jobs/${job.id}`);
        if(!response.ok||done())continue;
        const state=await response.json() as {stage?:string;progress?:number|null;encoded?:number};
        if(done()||state.stage!=='transcoding')continue;
        const progress=typeof state.progress==='number'?state.progress:null,elapsed=(Date.now()-began)/1000;
        this.update(job.id,{progress,encoded:state.encoded??null,eta:progress&&progress>.03&&progress<1?Math.round(elapsed/progress*(1-progress)):null});
      }catch{/* the next poll tries again; the upload request itself reports failure */}
    }
  }
}
