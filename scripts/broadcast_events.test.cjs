const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const code=ts.transpileModule(fs.readFileSync('frontend/src/broadcast.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const killCode=ts.transpileModule(fs.readFileSync('frontend/src/killAnnouncements.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const killScope={exports:{}};vm.runInNewContext(killCode,killScope);
const identityScope={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync('frontend/src/strategyIdentity.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,identityScope);
const imports={'./strategyIdentity':identityScope.exports,'./types':{},'./matchStats':{TEAM_LABEL:{red:'红方',blue:'蓝方'}},'./media':{},'./broadcast.css':{},'./killAnnouncements':killScope.exports,'./agentLogos':{},'./agents':{}};
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
