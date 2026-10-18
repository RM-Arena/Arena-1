const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
function compile(name){
 const scope={exports:{}};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(`frontend/src/${name}.ts`,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,scope);
 return scope.exports;
}
const identity=compile('strategyIdentity'),agents=compile('agents');
const plain=value=>JSON.parse(JSON.stringify(value));
test('match selectors and records prefer display names and hide legacy directory keys',()=>{
 assert.equal(identity.strategyDisplayName({name:'claude_opus55_xhigh_2027_team',display_name:'基线策略 2027'}),'基线策略 2027');
 assert.equal(identity.strategyDisplayName({name:'claude_opus55_xhigh_2027_distributed'}),'多机协同 2027');
 assert.equal(identity.strategyName('claude_opus55_xhigh_adaptive_301_guard'),'301 型 · 防守');
 assert.equal(identity.strategyName('claude_opus55_xhigh_2027_adaptive_2731_assault'),'2731 型 · 突击 2027');
 for(const name of ['赛事守势 2027','赛事基线 · claude_opus55_xhigh_team','RULEBOOK TEAM'])assert.doesNotMatch(identity.strategyName(name),/rulebook|赛事/i);
 assert.equal(identity.strategyDisplayName({name:'my-team',display_name:'我的战队'}),'我的战队');
});
test('older 2027 replay teams and per-robot credits show Claude Opus 5.5',()=>{
 const metadata={season:'2027',map:'rmuc2027',teams:{red:{name:'claude_opus55_xhigh_2027_team',agent:{provider:'rulebook'}}},agents:{red:{3:{provider:'rulebook',strategy:'基线策略 2027'}}}};
 assert.equal(agents.teamEmblem(metadata,'red'),'anthropic');
 assert.equal(agents.agentLabel(agents.robotAgent(metadata,'red',3)),'Claude Opus 5.5 xhigh');
 assert.equal(agents.providerOf(agents.robotAgent(metadata,'red',3)),'anthropic');
 const withoutCredits={teams:{red:{name:'claude_opus55_xhigh_2027_squad'}},map:'rmuc2027'};
 assert.equal(agents.teamEmblem(withoutCredits,'red'),'anthropic');
});
test('renamed 2026 strategies carry the confirmed author while arbitrary categories stay unknown',()=>{
 assert.equal(agents.providerOf({provider:'rulebook'}),'unknown');
 const metadata={season:'2026',teams:{red:{name:'claude_opus55_xhigh_team',agent:{provider:'rulebook'}}}};
 assert.equal(agents.robotAgent(metadata,'red',1).model,'Claude Opus 5.5 xhigh');
 assert.equal(agents.PROVIDERS.rulebook,undefined);
});
test('user submissions keep their recorded provider and model',()=>{
 const metadata={season:'2027',teams:{red:{name:'my-team',agent:{provider:'anthropic',model:'Claude Sonnet 5.5'}}}};
 assert.equal(agents.agentLabel(agents.robotAgent(metadata,'red',1)),'Claude Sonnet 5.5');
 assert.equal(agents.robotAgent({season:'2027',teams:{red:{name:'my-team'}}},'red',1),null);
});

test('pre-0.7 strategy identifiers and labels normalize without changing user names',()=>{
 const old='off'+'icial',zh='\u5b98\u65b9';
 assert.equal(identity.canonicalStrategyKey(old+'_2027_team'),'claude_opus55_xhigh_2027_team');
 assert.equal(identity.strategyName(zh+'基线 · '+old+'_team'),'基线策略');
 const metadata={teams:{red:{name:old+'_team',agent:{provider:old}}}};
 assert.equal(agents.robotAgent(metadata,'red',1).model,'Claude Opus 5.5 xhigh');
});
