// Capture real product views and a broadcast recording for the README.
const {_electron}=require('playwright');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');

(async()=>{
  const root=path.resolve(__dirname,'../..'),output=path.join(root,'docs/media');
  const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'arena-media-'));
  fs.mkdirSync(output,{recursive:true});
  const app=await _electron.launch({args:['.'],cwd:root,env:{...process.env,RMUC_DESKTOP_DATA:path.join(temporary,'data'),ELECTRON_RUN_AS_NODE:''},timeout:90000});
  const errors=[];
  try {
    const page=await app.firstWindow();await page.setViewportSize({width:1600,height:1000});
    page.on('pageerror',e=>errors.push(e.message));
    await page.waitForFunction(()=>window.arenaDiagnostics?.().engine==='rust'&&window.arenaDiagnostics().connected);
    const snapshot=async name=>{await page.waitForTimeout(1500);await page.screenshot({path:path.join(output,name+'.jpg'),type:'jpeg',quality:92});};
    const api=async(route,data)=>{const r=await page.request.post(new URL(route,page.url()).href,{data});if(!r.ok())throw new Error(await r.text());};
    await snapshot('home');
    await page.getByRole('button',{name:'RM 对战',exact:true}).first().click();
    await page.locator('.team-lineup-button').click();
    await page.waitForSelector('.team-lineup-dialog');await snapshot('lineup');
    await page.getByRole('button',{name:'关闭阵容选择',exact:true}).click();
    await page.selectOption('#red-select','official_squad');
    await page.selectOption('#blue-select','official_distributed');
    await page.click('#start');await page.waitForFunction(()=>window.arenaDiagnostics().prematch);
    await api('/api/control',{command:'skip_prematch'});
    await api('/api/control',{command:'speed',speed:4});
    await page.waitForFunction(()=>window.arenaDiagnostics().tick>1000,{},{timeout:60000});
    const movie=path.join(temporary,'battle.mp4');
    await app.evaluate(({session},filename)=>{session.defaultSession.removeAllListeners('will-download');session.defaultSession.on('will-download',(_e,item)=>item.setSavePath(filename));},movie);
    await page.click('#record');await page.waitForFunction(()=>window.arenaDiagnostics().recording);
    await snapshot('battle');
    await page.waitForTimeout(5000);
    await page.locator('.setup-panel button[aria-label="俯视视角"]').click();
    await snapshot('overview');
    await page.waitForTimeout(2500);await page.click('#record');
    for(let i=0;i<100&&!fs.existsSync(movie);i++)await page.waitForTimeout(100);
    await page.waitForTimeout(700);
    await api('/api/control',{command:'stop'});
    await page.waitForFunction(()=>!document.querySelector('#start').disabled,{},{timeout:30000});
    await page.getByRole('button',{name:'训练',exact:true}).first().click();await snapshot('training');
    await page.getByRole('button',{name:'策略库',exact:true}).first().click();
    await page.waitForTimeout(1200);
    await page.getByRole('button',{name:/Anthropic/}).first().click();await snapshot('strategies');
    await page.getByRole('button',{name:'主页',exact:true}).first().click();
    await page.locator('.home-menu-item').filter({hasText:'自由对战'}).click();
    await page.click('#edit-decks');await snapshot('free-battle');
    console.log(JSON.stringify({output,movie,errors},null,2));
    if(errors.length)throw new Error(errors.join('\n'));
  }finally{await app.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
