// Exercise the real desktop app. Artifacts and training data stay outside source.
const {_electron} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

(async()=>{
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'arena-desktop-e2e-'));
  const executable=process.env.ARENA_TEST_EXECUTABLE;
  const runtime=await _electron.launch({executablePath:executable||require('electron'),args:executable?[]:['.'],cwd:path.resolve(__dirname,'../..'),
    env:{...process.env,RMUC_DESKTOP_DATA:path.join(output,'data'),ELECTRON_RUN_AS_NODE:''},timeout:90000});
  const errors=[];let backendUrl;
  try {
    const page=await runtime.firstWindow(); page.on('pageerror',error=>errors.push(error.message));
    await page.waitForFunction(()=>{const d=window.arenaDiagnostics?.();return d?.connected&&d.engine==='rust'&&d.robots===12;},{},{timeout:60000});
    backendUrl=new URL(page.url()).origin;
    assert.equal(await page.evaluate(async()=>(await navigator.permissions.query({name:'clipboard-write'})).state),'granted');
    assert.equal(await page.evaluate(()=>window.arenaDiagnostics().engine),'rust');
    assert.equal(await page.evaluate(()=>window.arenaDiagnostics().robots),12);
    const api=async(route,data)=>{
      const response=data===undefined?await page.request.get(new URL(route,page.url()).href):await page.request.post(new URL(route,page.url()).href,{data});
      assert.ok(response.ok(),`${route}: ${response.status()} ${await response.text()}`);return response.json();
    };
    await page.screenshot({path:path.join(output,'home.png')});
    await page.getByRole('button',{name:'RM 对战',exact:true}).first().click();
    await page.waitForSelector('#start');
    await page.selectOption('#red-select','claude_opus55_xhigh_team');await page.selectOption('#blue-select','claude_opus55_xhigh_hold');
    await page.click('#start');
    await page.waitForFunction(()=>window.arenaDiagnostics().prematch);
    await api('/api/control',{command:'skip_prematch'});
    await page.waitForFunction(()=>window.arenaDiagnostics().tick>10,{},{timeout:30000});
    if (!await page.evaluate(()=>window.arenaDiagnostics().audioEnabled)) await page.click('#sound');
    await page.waitForFunction(()=>window.arenaDiagnostics().audioEnabled);
    await page.waitForFunction(()=>window.arenaDiagnostics().music,{},{timeout:30000});
    assert.equal(await page.evaluate(()=>window.arenaDiagnostics().audio.error),null);
    const movie=path.join(output,'broadcast.mp4');
    await runtime.evaluate(({session},filename)=>{
      session.defaultSession.removeAllListeners('will-download');
      session.defaultSession.on('will-download',(_event,item)=>item.setSavePath(filename));
    },movie);
    await page.click('#record');await page.waitForFunction(()=>window.arenaDiagnostics().recording);
    const started=await page.evaluate(()=>window.arenaDiagnostics().tick);
    await page.waitForFunction(tick=>window.arenaDiagnostics().tick>tick+20,started);
    await page.click('#record');
    for(let attempt=0;attempt<100&&!fs.existsSync(movie);attempt++) await new Promise(resolve=>setTimeout(resolve,100));
    assert.ok(fs.existsSync(movie),'Recording should download through the desktop session');
    await page.screenshot({path:path.join(output,'match.png')});
    const features=await page.evaluate(()=>({recording:typeof MediaRecorder==='function',webgl:!!document.createElement('canvas').getContext('webgl2'),
      canvases:document.querySelectorAll('canvas').length,robotRows:document.querySelectorAll('[data-robot-hp]').length}));
    assert.ok(features.recording&&features.webgl);assert.equal(features.robotRows,12);
    await api('/api/control',{command:'stop'});
    await page.waitForFunction(()=>!document.querySelector('#start').disabled,{},{timeout:30000});
    const matches=await api('/api/matches');assert.equal(matches.length,1);assert.ok(matches[0].has_replay);
    const replayResponse=await page.request.get(new URL('/api/replays/'+matches[0].id,page.url()).href);
    assert.ok(replayResponse.ok());const replay=await replayResponse.json();assert.equal(replay.format,'rmuc-replay-v4');
    assert.equal(replay.result.policy_errors,0);fs.writeFileSync(path.join(output,'match.json'),JSON.stringify(replay));
    await page.getByRole('button',{name:'比赛与回放',exact:true}).first().click();
    await page.getByRole('button',{name:'播放',exact:true}).first().click();
    await page.waitForFunction(()=>window.arenaDiagnostics().mode==='replay');
    const workspace=await api('/api/training-workspaces',{name:'desktop-e2e',mode:'team',minutes:5});
    assert.ok(fs.existsSync(workspace.task_file));assert.ok(workspace.workspace.startsWith(fs.realpathSync(path.join(output,'data'))));
    const free=await api('/api/robot-catalog');assert.ok(Object.keys(free).length>=19);
    await page.screenshot({path:path.join(output,'replay.png')});
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({output,features,ticks:replay.actions.length,policyErrors:replay.result.policy_errors,videoBytes:fs.statSync(movie).size,workspace:workspace.workspace,rendererErrors:errors},null,2));
  } finally {
    await runtime.close();
    if (backendUrl) {
      let reachable=false;
      try {await fetch(backendUrl+'/api/desktop/health',{signal:AbortSignal.timeout(1000)});reachable=true;} catch {}
      assert.equal(reachable,false,'Closing the app must stop its private backend');
    }
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
