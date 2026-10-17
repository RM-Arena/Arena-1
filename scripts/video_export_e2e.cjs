// Optional real-browser recording smoke test. Uses a temporary backend and user profile.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{spawnSync}=require('node:child_process');
const {Backend,runtimeLayout}=require('../desktop/backend.cjs');

(async()=>{
  const root=path.resolve(__dirname,'..'),output=fs.mkdtempSync(path.join(os.tmpdir(),'arena-video-e2e-'));
  process.env.RMUC_STRATEGY_UPDATES='0';
  const layout=runtimeLayout({packaged:false,projectRoot:root});
  const backend=new Backend(layout,path.join(output,'data'),'trusted-local');
  backend.on('crash',result=>console.error('Backend crashed:',result.logs));
  let browser;
  try{
    const url=await backend.start();
    browser=await chromium.launch({headless:true,...(process.env.CHROME_EXECUTABLE?{executablePath:process.env.CHROME_EXECUTABLE}:{}),
      args:['--use-angle=swiftshader','--enable-unsafe-swiftshader','--autoplay-policy=no-user-gesture-required']});
    const page=await browser.newPage({viewport:{width:1600,height:1000},acceptDownloads:true}),errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(url);await page.waitForFunction(()=>window.arenaDiagnostics?.().connected);
    await page.getByRole('button',{name:'RM 对战',exact:true}).first().click();
    await page.locator('#viewport canvas').waitFor({state:'visible'});
    assert.equal(await page.locator('#video-format').inputValue(),'mp4');
    const record=async(name,recover=false)=>{
      console.log('Recording '+name);
      await page.click('#record');await page.waitForFunction(()=>window.arenaDiagnostics().recording);
      assert.equal(await page.locator('#video-format').isDisabled(),true);
      await page.waitForFunction(()=>window.arenaDiagnostics().recordedFrames>=3);
      await page.waitForTimeout(1600);
      let pending;
      if(recover){await page.click('#record');await page.locator('#save-original-video').waitFor();
        assert.equal(await page.getByText(/原始 WebM 已保留/).count(),1);
        pending=page.waitForEvent('download',{timeout:30000});await page.click('#save-original-video');}
      else{pending=page.waitForEvent('download',{timeout:60000});await page.click('#record');}
      let download;
      try{download=await pending;}catch(error){console.error(await page.evaluate(()=>({diagnostics:window.arenaDiagnostics(),text:document.body.innerText.slice(-1800)})));throw error;}
      await download.saveAs(path.join(output,name));
      await page.waitForFunction(()=>!window.arenaDiagnostics().exportingVideo);
      return download.suggestedFilename();
    };
    assert.match(await record('broadcast.mp4'),/\.mp4$/);
    assert.equal(fs.readFileSync(path.join(output,'broadcast.mp4')).subarray(4,8).toString(),'ftyp');
    const executable=spawnSync(layout.python,['-c','from imageio_ffmpeg import get_ffmpeg_exe; print(get_ffmpeg_exe())'],{encoding:'utf8'}).stdout.trim();
    const decoded=spawnSync(executable,['-hide_banner','-i',path.join(output,'broadcast.mp4'),'-f','null','-'],{encoding:'utf8',timeout:60000});
    assert.equal(decoded.status,0,decoded.stderr);
    assert.match(decoded.stderr,/Video: h264/);assert.match(decoded.stderr,/1920x1080/);assert.match(decoded.stderr,/30 fps/);assert.match(decoded.stderr,/Audio: aac/);
    await page.selectOption('#video-format','webm');assert.match(await record('broadcast.webm'),/\.webm$/);
    await page.selectOption('#video-format','mp4');
    await page.route('**/api/video-export*',route=>route.request().method()==='POST'
      ?route.fulfill({status:500,contentType:'application/json',body:'{"detail":"模拟转码失败"}'})
      :route.continue());
    assert.match(await record('preserved.webm',true),/\.webm$/);
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({output,mp4Bytes:fs.statSync(path.join(output,'broadcast.mp4')).size,
      codecs:'H.264/AAC',size:'1920x1080',fps:30,webm:true,failurePreservesOriginal:true,pageErrors:errors},null,2));
  }finally{await browser?.close();await backend.stop();}
})().catch(error=>{console.error(error);process.exitCode=1;});
