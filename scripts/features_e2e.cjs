// Real Chromium smoke test for settings, cross-lineup pairing and attached full-broadcast MP4.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),vm=require('node:vm'),ts=require('typescript');
const identity={exports:{}};vm.runInNewContext(ts.transpileModule(require('node:fs').readFileSync(require('node:path').join(__dirname,'../frontend/src/strategyIdentity.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,identity);
const {strategyDisplayName}=identity.exports;
const {spawn}=require('node:child_process'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
(async()=>{
 const root=path.resolve(__dirname,'..'),output=fs.mkdtempSync(path.join(os.tmpdir(),'arena-features-e2e-'));
 const script=`import os,json,socket\nfrom pathlib import Path\nimport uvicorn\nfrom rmuc_arena.server import create_app\nr=Path(os.environ['ARENA_QA_DATA'])\napp=create_app('trusted-local',r/'submissions',r/'data',test_mode=True)\napp.state.arena.prematch_stages=(('self_check',8),('countdown',2))\nwith socket.socket() as s:\n s.bind(('127.0.0.1',0))\n print(json.dumps({'url':f'http://127.0.0.1:{s.getsockname()[1]}'}),flush=True)\n uvicorn.Server(uvicorn.Config(app,log_level='warning')).run(sockets=[s])\n`;
 const backend=spawn(path.join(root,process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python'),['-c',script],{cwd:root,env:{...process.env,RMUC_STRATEGY_UPDATES:'0',ARENA_QA_DATA:output},stdio:['ignore','pipe','pipe']});
 let browser,logs='';backend.stderr.on('data',s=>logs+=s);
 try{
  const url=await new Promise((resolve,reject)=>{let data='';const t=setTimeout(()=>reject(Error('Backend timed out: '+logs)),30000);backend.once('exit',()=>{clearTimeout(t);reject(Error('Backend exited: '+logs));});backend.stdout.on('data',s=>{data+=s;const line=data.split('\n')[0];try{const v=JSON.parse(line);if(v.url){clearTimeout(t);resolve(v.url);}}catch{}});});
  browser=await chromium.launch({headless:true,...(process.env.CHROME_EXECUTABLE?{executablePath:process.env.CHROME_EXECUTABLE}:{}),args:['--use-angle=swiftshader','--enable-unsafe-swiftshader','--autoplay-policy=no-user-gesture-required']});
  const page=await browser.newPage({viewport:{width:1700,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  console.log('Browser ready: '+url);await page.goto(url);await page.waitForFunction(()=>window.arenaDiagnostics?.().connected);
  console.log('Settings');await page.getByRole('button',{name:'战场设置',exact:true}).click();
  const spread=page.getByRole('spinbutton',{name:'17 mm 弹丸散布半角',exact:true});await spread.waitFor();assert.equal(await spread.inputValue(),'1.8');
  await spread.fill('0');await page.getByRole('button',{name:'保存设置',exact:true}).click();await page.getByRole('status').filter({hasText:'已保存'}).waitFor();
  assert.equal((await (await fetch(url+'/api/battle-settings')).json()).overrides['projectile_spread_half_angle_deg.17mm'],0);
  await page.reload();await page.waitForFunction(()=>window.arenaDiagnostics?.().connected);await page.getByRole('button',{name:'战场设置',exact:true}).click();assert.equal(await spread.inputValue(),'0');
  await page.getByRole('button',{name:'恢复默认',exact:true}).click();await page.getByRole('status').filter({hasText:'已恢复'}).waitFor();assert.equal(await spread.inputValue(),'1.8');
  await page.screenshot({path:path.join(output,'settings.png'),fullPage:true});
  console.log('Strategy matchmaker');await page.getByRole('button',{name:'RM 对战',exact:true}).click();await page.locator('#viewport canvas').waitFor();await page.click('#strategy-matchmaker');
  await page.getByRole('dialog',{name:'先看策略，再选对手。',exact:true}).waitFor();await page.getByRole('combobox',{name:'策略赛季',exact:true}).selectOption('all');
  assert.ok(await page.locator('.matchmaker-list article').count()>2);
  const catalog=await (await fetch(url+'/api/catalog')).json(),keys=Object.keys(catalog),a=keys.find(k=>k==='claude_opus55_xhigh_2027_team'),different=keys.find(k=>catalog[k].season==='2026');
  assert.ok(a&&different);
  const cards=page.locator('.matchmaker-list article');
  const pick=async(id,team)=>{const names=await cards.locator('strong').allTextContents();const index=names.indexOf(strategyDisplayName(catalog[id]));assert.ok(index>=0,'missing '+id);await cards.nth(index).getByRole('button',{name:team,exact:true}).click();};
  await pick(a,'红方');await pick(different,'蓝方');assert.equal(await page.getByRole('button',{name:'应用对战组合'}).isDisabled(),true);
  const wrongLineup=keys.find(k=>catalog[k].season==='2027'&&catalog[k].team_lineup&&JSON.stringify(catalog[k].team_lineup)!==JSON.stringify(catalog[a].team_lineup));assert.ok(wrongLineup);
  await pick(wrongLineup,'蓝方');assert.equal(await page.getByRole('button',{name:'应用对战组合'}).isDisabled(),true);
  await cards.locator('input[type="checkbox"]:not(:checked):not(:disabled)').first().check();assert.equal(await cards.locator('input[type="checkbox"]:checked').count(),3);assert.equal(await cards.locator('input[type="checkbox"]:not(:checked)').first().isDisabled(),true);

  await page.screenshot({path:path.join(output,'strategy-comparison.png'),fullPage:true});await pick('claude_opus55_xhigh_2027_hold','蓝方');await page.getByRole('button',{name:'应用对战组合'}).click();assert.equal(await page.locator('#red-select').inputValue(),a);assert.equal(await page.locator('#blue-select').inputValue(),'claude_opus55_xhigh_2027_hold');
  await page.locator('#save-match-mp4').check();
  // Only shorten the match duration. Intro/countdown/post-match recording use production code.
  await page.route('**/api/start',route=>{const body=route.request().postDataJSON();return route.continue({postData:JSON.stringify({...body,duration:2})});});
  console.log('Automatic recording');await page.click('#start');await page.waitForFunction(()=>window.arenaDiagnostics().recording);
  await page.waitForFunction(()=>window.arenaDiagnostics().prematch==='self_check');
  assert.equal(await page.getByRole('button',{name:'跳过',exact:true}).isDisabled(),true);
  const stages=new Set(),sample=async()=>{const d=await page.evaluate(()=>window.arenaDiagnostics());stages.add(d.post||d.prematch||'match');return d;};
  let record;const until=Date.now()+180000;
  while(Date.now()<until){await sample();const matches=await (await fetch(url+'/api/matches')).json();record=matches[0];if(record?.has_video)break;await page.waitForTimeout(1000);}
  console.log('Finished recording stages: '+[...stages]);assert.ok(record?.has_video,JSON.stringify({record,errors,logs,diagnostics:await sample()}));
  assert.ok(stages.has('self_check'));assert.ok(stages.has('results'));assert.ok(stages.has('mvp'));assert.equal(record.video_status,'ready');
  const video=await fetch(url+`/api/matches/${record.id}/video`),bytes=Buffer.from(await video.arrayBuffer());assert.equal(bytes.subarray(4,8).toString(),'ftyp');fs.writeFileSync(path.join(output,'full-match.mp4'),bytes);
  await page.waitForFunction(()=>!window.arenaDiagnostics().exportingVideo);await page.getByRole('button',{name:'比赛与回放',exact:true}).click();await page.getByRole('button',{name:'MP4',exact:true}).click();await page.locator('.mp4-player video').waitFor();await page.waitForFunction(()=>{const v=document.querySelector('.mp4-player video');return v&&v.readyState>=2&&v.videoWidth===1920;});
  await page.screenshot({path:path.join(output,'mp4-playback.png'),fullPage:true});assert.deepEqual(errors,[]);
  console.log(JSON.stringify({output,mp4Bytes:bytes.length,recordedStages:[...stages],pageErrors:errors},null,2));
 }catch(error){console.error('Feature E2E failed:',error);throw error;}finally{backend.kill('SIGTERM');await browser?.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
