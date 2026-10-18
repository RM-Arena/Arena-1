const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
function compile(name,imports={},extras={}){
  const source=fs.readFileSync(path.join(__dirname,'../frontend/src/'+name+'.ts'),'utf8');
  const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const scope={exports:{},require:n=>{if(!(n in imports))throw new Error('Unexpected import '+n);return imports[n];},Blob,Promise,Error,Date,performance,...extras};
  vm.runInNewContext(code,scope);return scope.exports;
}
const response=(body,status=200)=>new Response(body,{status,headers:{'Content-Type':body instanceof Blob?body.type:'application/json'}});
const video=fetch=>compile('videoExport',{}, {fetch});

test('WebM export remains local and does not require the MP4 encoder',async()=>{
  const api=video(()=>{throw new Error('must not fetch');}),blob=new Blob(['recording'],{type:'video/webm'});
  await api.checkVideoExport('webm');assert.equal(await api.prepareVideoExport(blob,'webm'),blob);
});
test('MP4 uploads the binary recording and returns a real MP4 response',async()=>{
  const requests=[],progress=[],mp4=new Blob(['ftyp-mp4-data'],{type:'video/mp4'});
  const api=video(async(url,options)=>{requests.push({url,options});return options?response(mp4):response('{"mp4":true}');});
  const source=new Blob(['webm bytes'],{type:'video/webm;codecs=vp8,opus'});
  await api.checkVideoExport('mp4');const output=await api.prepareVideoExport(source,'mp4',value=>progress.push(value));
  assert.equal(output.type,'video/mp4');assert.equal(await output.text(),await mp4.text());
  assert.equal(requests[1].options.body,source);assert.equal(requests[1].options.headers['Content-Type'],'video/webm');
  assert.equal(requests[1].options.method,'POST');assert.equal(progress.length,2);
});
test('missing encoders, failed conversions and incorrect response types are reported',async()=>{
  await assert.rejects(video(async()=>response('{"mp4":false}')).checkVideoExport('mp4'),/转码组件/);
  const source=new Blob(['webm']);
  await assert.rejects(video(async()=>response('{"detail":"视频无效"}',400)).prepareVideoExport(source,'mp4'),/视频无效/);
  await assert.rejects(video(async()=>response('{}')).prepareVideoExport(source,'mp4'),/有效的 MP4/);
});

function recorderHarness(format='mp4',conversionFails=false,startFails=false){
  const downloads=[],requests=[],stopped=[],clones=[];
  const track={stop:()=>stopped.push('video')},audioTrack={clone:()=>{const clone={stop:()=>stopped.push('cloned-audio')};clones.push(clone);return clone;}};
  const tracks=[track],stream={getTracks:()=>tracks,addTrack:t=>tracks.push(t)};
  class Recorder{
    static isTypeSupported(mime){return mime==='video/webm;codecs=vp8,opus';}
    constructor(_stream,options){this.mimeType=options.mimeType;this.state='inactive';}
    start(){if(startFails)throw new Error('encoder start failed');this.state='recording';this.ondataavailable({data:new Blob(['first-'])});}
    stop(){this.state='inactive';this.ondataavailable({data:new Blob(['last'])});this.onstop();}
  }
  const fetch=async(_url,options)=>{requests.push(options);if(options&&_url.includes('/api/matches/')&&!conversionFails)return response(JSON.stringify({url:'/api/matches/test/video'}));return !options?response('{"mp4":true}'):conversionFails?response('{"detail":"转码失败"}',500):response(new Blob(['mp4'],{type:'video/mp4'}));};
  const api=video(fetch),identity=compile('strategyIdentity'),playlist=compile('audioPlaylist'),kills=compile('killAnnouncements');
  const document={createElement:tag=>tag==='canvas'?{getContext:()=>({fillRect(){}}),captureStream:()=>stream}:{click(){downloads.push({name:this.download,blob:this.blob});},remove(){}},body:{append(){}}};
  let latest;
  const {BroadcastRecorder}=compile('media',{'./videoExport':api,'./strategyIdentity':identity,'./audioPlaylist':playlist,'./killAnnouncements':kills},{
    document,MediaRecorder:Recorder,window:{MediaRecorder:Recorder},URL:{createObjectURL:blob=>{latest=blob;return 'blob:recording';},revokeObjectURL(){}},setTimeout(){},
  });
  const original=document.createElement;
  document.createElement=tag=>{const element=original(tag);if(tag==='a')Object.defineProperty(element,'blob',{get:()=>latest});return element;};
  const audio={enable:async()=>{},destination:{stream:{getAudioTracks:()=>[audioTrack]}}};
  const recorder=new BroadcastRecorder(audio);recorder.source={width:1920,height:1080};
  return {recorder,downloads,requests,stopped,clones,format};
}
test('stopping waits for the final chunk, exports MP4 and releases recording tracks',async()=>{
  const h=recorderHarness();await h.recorder.start('mp4');assert.equal(h.recorder.active,true);await h.recorder.stop();
  assert.equal(h.recorder.active,false);assert.equal(await h.requests[1].body.text(),'first-last');
  assert.equal(h.downloads.length,1);assert.match(h.downloads[0].name,/\.mp4$/);assert.equal(h.downloads[0].blob.type,'video/mp4');
  assert.deepEqual(h.stopped.sort(),['cloned-audio','video']);assert.equal(h.recorder.chunks.length,0);
});
test('failed MP4 conversion preserves WebM for an explicit user download',async()=>{
  const h=recorderHarness('mp4',true);await h.recorder.start('mp4');await assert.rejects(h.recorder.stop(),/原始 WebM 已保留/);
  assert.equal(h.downloads.length,0);assert.equal(h.recorder.hasRecovery,true);
  await assert.rejects(h.recorder.start('mp4'),/请先保存或丢弃/);h.recorder.saveOriginal();assert.equal(h.recorder.hasRecovery,false);
  assert.equal(h.downloads.length,1);assert.match(h.downloads[0].name,/\.webm$/);assert.equal(await h.downloads[0].blob.text(),'first-last');
});
test('explicit WebM recordings export without uploading and failed starts release tracks',async()=>{
  const h=recorderHarness('webm');await h.recorder.start('webm');await h.recorder.stop();
  assert.equal(h.requests.length,0);assert.match(h.downloads[0].name,/\.webm$/);
  const failed=recorderHarness('mp4',false,true);await assert.rejects(failed.recorder.start('mp4'),/encoder start failed/);
  assert.deepEqual(failed.stopped.sort(),['cloned-audio','video']);assert.equal(failed.recorder.active,false);
});

test('automatic MP4 attaches the final capture to its match without downloading',async()=>{
  const h=recorderHarness();await h.recorder.start('mp4');await h.recorder.stop(()=>{},'test');
  assert.equal(h.downloads.length,0);assert.equal(await h.requests[1].body.text(),'first-last');
  assert.equal(h.recorder.hasRecovery,false);assert.equal(h.recorder.active,false);
});
test('failed automatic save keeps the match target and original capture; cancel releases tracks',async()=>{
  const h=recorderHarness('mp4',true);await h.recorder.start('mp4');await assert.rejects(h.recorder.stop(()=>{},'test'),/原始 WebM 已保留/);
  assert.equal(h.recorder.canRetrySave,true);await assert.rejects(h.recorder.retrySave(),/转码失败/);assert.equal(h.recorder.hasRecovery,true);
  const clean=recorderHarness();await clean.recorder.start('mp4');await clean.recorder.cancel();assert.equal(clean.recorder.active,false);assert.equal(clean.downloads.length,0);assert.equal(clean.recorder.hasRecovery,false);
});
