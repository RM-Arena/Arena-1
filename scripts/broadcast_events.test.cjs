const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const code=ts.transpileModule(fs.readFileSync('frontend/src/broadcast.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const killCode=ts.transpileModule(fs.readFileSync('frontend/src/killAnnouncements.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const killScope={exports:{}};vm.runInNewContext(killCode,killScope);
const alertCode=ts.transpileModule(fs.readFileSync('frontend/src/fortressAlert.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const alertScope={exports:{}};vm.runInNewContext(alertCode,{exports:alertScope.exports,require:()=>({pointInPolygon:()=>false})});
const buffsCode=ts.transpileModule(fs.readFileSync('frontend/src/buffs.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const buffsScope={exports:{}};vm.runInNewContext(buffsCode,{exports:buffsScope.exports,require:()=>({frameSeason:()=>'2027'})});
const identityScope={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync('frontend/src/strategyIdentity.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,identityScope);
const imports={'./strategyIdentity':identityScope.exports,'./types':{},'./matchStats':{TEAM_LABEL:{red:'红方',blue:'蓝方'},TEAMS:['red','blue'],other:(t)=>t==='red'?'blue':'red'},'./media':{},'./broadcast.css':{},'./killAnnouncements':killScope.exports,'./agentLogos':{},'./agents':{},'./fortressAlert':alertScope.exports,'./buffs':buffsScope.exports,'./BuffChips':{BuffChips:()=>null}};
const scope={exports:{},performance,require:name=>name in imports?imports[name]:require(name)};vm.runInNewContext(code,scope);
const {BroadcastDirector}=scope.exports;
test('broadcast team headings normalize names recorded in older replays',()=>{
 const metadata={teams:{red:{name:'claude_opus55_xhigh_2027_team',display_name:'赛事基线 2027'}}};
 assert.equal(scope.exports.teamName(metadata,'red'),'基线策略 2027');
});
test('paid revival announces the full-health purchase and its exact coin cost once',()=>{
 const director=new BroadcastDirector(),event={type:'respawn',id:'paid-1',tick:40,team:'red',robot:'red-3',instant:true,cost:120,hp:150,max_hp:150};
 director.events([event],null);director.events([event],null);const toasts=director.active('toast');assert.equal(toasts.length,1);
 assert.match(toasts[0].title,/红方 3号满血复活/);assert.ok(toasts[0].chips.includes('花费 120 金币'));assert.equal(toasts[0].icon,'revive');
});
test('natural revival is never announced as a full-health coin purchase',()=>{
 const director=new BroadcastDirector();director.events([{type:'respawn',id:'natural-1',robot:'blue-4',team:'blue',instant:false,cost:0,hp:15,max_hp:150}],null);assert.equal(director.active('toast').length,0);
});
test('the director presents speech-synchronized highlights, freezes them on pause, and clears a new match',()=>{
 const director=new BroadcastDirector();const a={key:'penta-1',cue:'penta-kill',team:'red',killer:'red-3',victim:'blue-7',at:20,count:5};
 director.announce(a,4);assert.equal(director.highlight.cue,'penta-kill');director.advanceHighlight(1000,false);director.advanceHighlight(10000,true);assert.equal(director.highlight.age,1000);
 director.advanceHighlight(3000,false);assert.equal(director.highlight,null);director.announce(a,4);director.reset();assert.equal(director.highlight,null);
});
test('an enemy stepping onto the fortress announces the capture once, like a lost outpost',()=>{
 const zone='blue_fortress',attacker='red-4';
 const snapshot=(hold,armor=false)=>{const time=200+hold;return {status:'running',tick:4000+Math.round(hold*20),time,dt:.05,season:'2027',remaining:420,
  arena:{name:'rmuc2027',zones:[{id:zone,x:21.4,y:7.5,radius:.56}]},
  bases:{red:{hp:10000,armor_open:false},blue:{hp:8000,armor_open:armor}},
  outposts:{red:{hp:1000,ever_destroyed:false},blue:{hp:0,ever_destroyed:true}},
  zones:{[zone]:{occupants:[attacker],contested:false}},teams:{red:{},blue:{}},
  robots:[{id:attacker,team:'red',role:'infantry',alive:true,weak:false,red_card:false,x:21.4,y:7.5,fortress_hold:hold,fortress_last_contact:time-.05,last_raw_zones:[zone]}]};};
 const director=new BroadcastDirector();
 director.frame(snapshot(0));assert.equal(director.active('banner').length,0,'contact alone is not a capture yet');
 director.frame(snapshot(.05));
 const banners=director.active('banner');
 assert.equal(banners.length,1);assert.match(banners[0].title,/蓝方堡垒正在被占领/);assert.equal(banners[0].team,'blue');
 director.frame(snapshot(3));assert.equal(director.active('banner').length,1,'the announcement is not repeated');
 // The armor opening adds its own banner; the capture announcement itself must not repeat.
 director.frame(snapshot(4,true));
 assert.equal(director.active('banner').filter(b=>/堡垒正在被占领/.test(b.title)).length,1);
});
