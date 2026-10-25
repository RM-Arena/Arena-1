const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
function compile(name,imports={},extras={}){
  const source=fs.readFileSync(path.join(__dirname,'../frontend/src/'+name+'.ts'),'utf8');
  const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const scope={exports:{},require:n=>{if(!(n in imports))throw new Error('Unexpected import '+n);return imports[n];},Blob,Promise,Error,Date,performance,Map,Set,JSON,Math,...extras};
  vm.runInNewContext(code,scope);return scope.exports;
}
const json=(body,status=200)=>new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json'}});
const tick=()=>new Promise(resolve=>setTimeout(resolve,2));
async function until(check,limit=400){for(let i=0;i<limit&&!check();i++)await tick();assert.ok(check(),'condition never became true');}

// The capture engine: a fake MediaRecorder that emits one chunk on start and one on stop.
function captureHarness(startFails=false){
  const stopped=[],track={stop:()=>stopped.push('video')},audioTrack={clone:()=>({stop:()=>stopped.push('cloned-audio')})};
  const tracks=[track],stream={getTracks:()=>tracks,addTrack:t=>tracks.push(t)};
  class Recorder{
    static isTypeSupported(mime){return mime==='video/webm;codecs=vp8,opus';}
    constructor(_stream,options){this.mimeType=options.mimeType;this.state='inactive';}
    start(){if(startFails)throw new Error('encoder start failed');this.state='recording';this.ondataavailable({data:new Blob(['first-'])});}
    stop(){this.state='inactive';this.ondataavailable({data:new Blob(['last'])});this.onstop();}
  }
  const media=compile('media',{'./strategyIdentity':compile('strategyIdentity'),'./audioPlaylist':compile('audioPlaylist'),'./killAnnouncements':compile('killAnnouncements')},{
    document:{createElement:()=>({getContext:()=>({fillRect(){}}),captureStream:()=>stream})},MediaRecorder:Recorder,window:{MediaRecorder:Recorder},
  });
  const recorder=new media.BroadcastRecorder({enable:async()=>{},destination:{stream:{getAudioTracks:()=>[audioTrack]}}});recorder.source={width:1920,height:1080};
  return {media,recorder,stopped};
}
// A session over that capture, with the server replaced by `server(url)` and `transport`.
function sessionHarness({mp4=true,respond,progress=[.25,.5,.75]}={}){
  const {media,recorder,stopped}=captureHarness();
  const saved=[],downloads=[],uploads=[],polls=[];let gate=null;
  const fetch=async url=>{
    if(url==='/api/video-export')return json({mp4});
    if(url.startsWith('/api/video-export/jobs/')){polls.push(url);const value=progress[Math.min(polls.length-1,progress.length-1)];return json({stage:'transcoding',progress:value,encoded:value*10});}
    throw new Error('unexpected '+url);
  };
  const transport=(url,blob,type,onUpload,onSent)=>{uploads.push({url,blob,type});onUpload(.4);onUpload(1);onSent();
    return new Promise(resolve=>{gate=()=>resolve(respond?respond(url):type==='blob'?{status:200,body:new Blob(['mp4'],{type:'video/mp4'})}:{status:200,body:{url:'/api/matches/m/video'}});});};
  const {RecordingSession}=compile('recording',{'./media':media},{setTimeout,clearTimeout,fetch});
  const session=new RecordingSession(recorder,{fetch,transport,poll:1,save:(blob,name)=>downloads.push({blob,name}),onSaved:job=>saved.push(job),
    later:(run,ms)=>{if(ms<1000)setTimeout(run,ms);}});
  return {session,recorder,stopped,saved,downloads,uploads,polls,release:()=>gate?.()};
}

test('the capture flushes its last chunk, reports wall-clock duration and releases its tracks',async()=>{
  const h=captureHarness();await h.recorder.start();assert.equal(h.recorder.active,true);
  await assert.rejects(h.recorder.start(),/已经开始/);
  const {blob,duration,error}=await h.recorder.stop();
  assert.equal(await blob.text(),'first-last');assert.ok(duration>0);assert.equal(error,null);
  assert.equal(h.recorder.active,false);assert.deepEqual(h.stopped.sort(),['cloned-audio','video']);
  const failed=captureHarness(true);await assert.rejects(failed.recorder.start(),/encoder start failed/);
  assert.deepEqual(failed.stopped.sort(),['cloned-audio','video']);assert.equal(failed.recorder.active,false);
});

test('a clip uploads, shows transcode progress, downloads the MP4 and frees the capture at once',async()=>{
  const h=sessionHarness();
  await h.session.start('clip');assert.equal(h.session.getSnapshot().capture.kind,'clip');assert.equal(h.session.busy,true);
  const job=await h.session.stop();
  // The capture is over the moment the recorder flushed: a new one could start while this one saves.
  assert.equal(h.session.getSnapshot().capture,null);
  await until(()=>h.polls.length>=2);
  const saving=h.session.getSnapshot().jobs[0];
  assert.equal(saving.stage,'transcoding');assert.ok(saving.progress>0&&saving.progress<1);
  assert.match(h.uploads[0].url,/^\/api\/video-export\?duration=\d+\.\d{3}&job=rec-/);assert.equal(await h.uploads[0].blob.text(),'first-last');
  h.release();await until(()=>h.session.getSnapshot().jobs[0].stage==='done');
  assert.equal(h.downloads.length,1);assert.match(h.downloads[0].name,/^rmuc-arena-.*\.mp4$/);assert.equal(h.downloads[0].blob.type,'video/mp4');
  assert.equal(h.saved[0].id,job.id);assert.equal(h.session.hasOriginal(h.session.getSnapshot().jobs[0]),false);assert.equal(h.session.busy,false);
});

test('without the converter a clip downloads as WebM, and a whole-match recording refuses to start',async()=>{
  const h=sessionHarness({mp4:false});
  await assert.rejects(h.session.start('match'),/MP4 转码组件不可用/);assert.equal(h.session.getSnapshot().starting,false);assert.equal(h.recorder.active,false);
  await h.session.start('clip');await h.session.stop();
  await until(()=>h.session.getSnapshot().jobs[0]?.stage==='done');
  assert.equal(h.uploads.length,0);assert.match(h.downloads[0].name,/\.webm$/);assert.equal(await h.downloads[0].blob.text(),'first-last');
});

test('a match recording is filed under its match without a download',async()=>{
  const h=sessionHarness();
  await h.session.start('match');h.session.attach('match0000000001');
  await h.session.stop();h.release();
  await until(()=>h.session.getSnapshot().jobs[0]?.stage==='done');
  assert.match(h.uploads[0].url,/^\/api\/matches\/match0000000001\/video\?duration=/);assert.equal(h.uploads[0].type,'json');
  assert.equal(h.downloads.length,0);assert.equal(h.saved.length,1);assert.equal(h.saved[0].matchId,'match0000000001');
});

test('a failed save keeps the original for a retry or an explicit download',async()=>{
  let fail=true;
  const h=sessionHarness({respond:()=>fail?{status:500,body:{detail:'MP4 转码失败'}}:{status:200,body:{url:'/x'}}});
  await h.session.start('match');h.session.attach('match0000000002');await h.session.stop();h.release();
  await until(()=>h.session.getSnapshot().jobs[0]?.stage==='failed');
  const failed=h.session.getSnapshot().jobs[0];
  assert.equal(failed.error,'MP4 转码失败');assert.equal(h.session.canRetry(failed),true);assert.equal(h.session.hasOriginal(failed),true);
  fail=false;h.session.retry(failed.id);await until(()=>h.uploads.length===2);h.release();
  await until(()=>h.session.getSnapshot().jobs[0]?.stage==='done');assert.equal(h.saved.length,1);
  fail=true;await h.session.start('clip');await h.session.stop();await until(()=>h.uploads.length===3);h.release();
  await until(()=>h.session.getSnapshot().jobs.at(-1).stage==='failed');
  h.session.saveOriginal(h.session.getSnapshot().jobs.at(-1).id);
  assert.match(h.downloads.at(-1).name,/\.webm$/);assert.equal(await h.downloads.at(-1).blob.text(),'first-last');
  assert.equal(h.session.getSnapshot().jobs.some(j=>j.stage==='failed'),false);
});

test('saves run one at a time and a cancelled capture leaves nothing behind',async()=>{
  const h=sessionHarness();
  await h.session.start('clip');await h.session.stop();
  await h.session.start('clip');await h.session.stop();
  await until(()=>h.uploads.length===1);
  assert.deepEqual([...h.session.getSnapshot().jobs.map(j=>j.stage)],['transcoding','queued']);
  h.release();await until(()=>h.uploads.length===2);h.release();
  await until(()=>h.session.getSnapshot().jobs.every(j=>j.stage==='done'));assert.equal(h.downloads.length,2);
  await h.session.start('match');await h.session.cancel();
  assert.equal(h.session.getSnapshot().capture,null);assert.equal(h.recorder.active,false);assert.equal(h.session.getSnapshot().jobs.length,2);
});
