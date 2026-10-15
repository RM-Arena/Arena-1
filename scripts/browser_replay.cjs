// Verify that a complete seven-minute replay loads and seeks in the 3D player.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const replay=path.resolve(process.argv[2]||'replays/chapter4-six-vs-six.json');
 const output=path.resolve(process.env.RMUC_REPLAY_QA_OUTPUT||'replays/chapter4-browser-qa');fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({headless:true,...(process.env.CHROME_EXECUTABLE?{executablePath:process.env.CHROME_EXECUTABLE}:{})});
 const page=await browser.newPage({viewport:{width:1600,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(process.env.RMUC_QA_URL||'http://127.0.0.1:8765');
  await page.waitForFunction(()=>window.arenaDiagnostics?.().connected);
  await page.setInputFiles('#replay-file',replay);
  await page.waitForFunction(()=>window.arenaDiagnostics().mode==='replay',{},{timeout:90000});
  const seek=async tick=>{
   await page.locator('#timeline').evaluate((el,value)=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,String(value));el.dispatchEvent(new Event('input',{bubbles:true}));},tick);
   await page.waitForFunction(value=>window.arenaDiagnostics().tick===value,tick);
  };
  assert.equal(await page.locator('#timeline').getAttribute('max'),'8400');
  await seek(6000);
  await page.screenshot({path:path.join(output,'full-replay.png'),fullPage:true});
  await page.selectOption('#speed','8');await page.click('#pause');
  await page.waitForFunction(()=>window.arenaDiagnostics().tick>6010);
  await seek(8400);
  assert.equal(await page.evaluate(()=>window.arenaDiagnostics().robots),12);
  assert.equal(await page.locator('#clock').innerText(),'00:00');
  assert.deepEqual(errors,[]);
  const report={fileBytes:fs.statSync(replay).size,verifiedLastTick:8400,robots:12,seekAndSpeed:true,browserErrors:errors};
  fs.writeFileSync(path.join(output,'full-replay-check.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
