const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../frontend/src/RespawnPanel.tsx'),'utf8'),
  {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const scope={exports:{},require:name=>name==='./pilot.css'?{}:name==='./types'?{}:require(name)};
vm.runInNewContext(code,scope);
const {RespawnPanel}=scope.exports;
const robot=(patch={})=>({id:'red-3',team:'red',slot:3,role:'infantry',red_card:false,...patch});
const render=(props)=>renderToStaticMarkup(React.createElement(RespawnPanel,{robot:robot(),respawnLeft:42,respawnShare:.25,gold:0,reviveCost:600,onBuy:()=>{},onFree:()=>{},...props}));

test('the card names the countdown and shows the free-revive progress as a bar and a ring',()=>{
 const html=render({});
 assert.match(html,/class="pilot-respawn team-red"/);
 assert.match(html,/复活中/);
 assert.match(html,/>42s</,'the remaining seconds are the headline figure');
 assert.match(html,/role="progressbar"[^>]*aria-valuenow="25"/);
 assert.match(html,/width:25%/,'the bar width follows the engine progress');
 assert.match(html,/--respawn-progress:90deg/,'the ring sweeps with the same progress');
});

test('the paid option is refused, not hidden, when the team cannot afford it',()=>{
 const poor=render({gold:0,reviveCost:600});
 assert.match(poor,/class="respawn-buy" disabled=""/);
 assert.match(poor,/600 金币不足/);
 assert.match(poor,/aria-label="金币不足：立即复活需 600 金币"/);
 const rich=render({gold:900,reviveCost:100});
 assert.doesNotMatch(rich,/class="respawn-buy" disabled=""/);
 assert.match(rich,/100 金币/);
});

test('the free card carries the Y hotkey and marks itself when chosen',()=>{
 const idle=render({});
 assert.match(idle,/aria-keyshortcuts="Y"/);
 assert.match(idle,/aria-pressed="false"/);
 assert.match(idle,/<kbd>Y<\/kbd>/);
 const chosen=render({freePicked:true});
 assert.match(chosen,/respawn-free picked" aria-pressed="true"/);
 assert.match(chosen,/respawn-bar chosen"/,'the bar confirms the chosen path');
 assert.match(chosen,/lucide-check/,'the picked state shows a check instead of the power glyph');
});

test('a red card replaces the countdown with a card that offers no revive',()=>{
 const html=render({robot:robot({red_card:true})});
 assert.match(html,/penalised/);
 assert.match(html,/判罚离场/);
 assert.match(html,/红牌/);
 assert.doesNotMatch(html,/respawn-choice|respawn-buy|respawn-free/,'a sent-off chassis cannot be bought back');
 assert.match(html,/按 P 打开驾驶面板/);
});

test('both sides get their own accent',()=>{
 assert.match(render({robot:robot()}),/team-red/);
 assert.match(render({robot:robot({id:'blue-4',team:'blue',slot:4})}),/team-blue/);
});
