const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
function compile(name,imports={}){
 const source=fs.readFileSync(path.join(__dirname,'../frontend/src/'+name+'.ts'),'utf8');
 const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 const scope={exports:{},require:n=>{if(!(n in imports))throw new Error('Unexpected import '+n);return imports[n];},Math,Set,Map};vm.runInNewContext(code,scope);return scope.exports;
}
const intro=compile('intro'),agents=compile('agents');
const robots=(red,blue)=>[...Array.from({length:red},(_,i)=>({id:'red-'+(i+1),team:'red',slot:i+1})),...Array.from({length:blue},(_,i)=>({id:'blue-'+(i+1),team:'blue',slot:i+1}))];

test('the intro matches the server length and gives every robot one shot',()=>{
 assert.equal(intro.introSeconds(12),43.1);assert.equal(intro.introSeconds(2),19.1);
 const cuts=intro.introSchedule(robots(6,6).reverse(),intro.introSeconds(12));
 assert.deepEqual(Array.from(cuts,c=>c.segment.kind),['open','team',...Array(6).fill('robot'),'team',...Array(6).fill('robot'),'faceoff']);
 assert.deepEqual(Array.from(cuts.filter(c=>c.segment.kind==='robot'&&c.segment.team==='red'),c=>c.segment.id),['red-1','red-2','red-3','red-4','red-5','red-6']);
 assert.ok(Math.abs(cuts.at(-1).end-43.1)<1e-9);
 for(let i=1;i<cuts.length;i++)assert.ok(Math.abs(cuts[i].start-cuts[i-1].end)<1e-9);
});
test('uneven free-battle lineups scale to the announced duration and long lineups stay bounded',()=>{
 const cuts=intro.introSchedule(robots(4,1),10);assert.equal(cuts.length,1+2+5+1);assert.ok(Math.abs(cuts.at(-1).end-10)<1e-9);
 assert.equal(cuts.find(c=>c.segment.kind==='robot'&&c.segment.team==='blue').segment.count,1);
 assert.ok(intro.introSeconds(40)<60);
});
test('the cut at a moment, before the start and after the end',()=>{
 const cuts=intro.introSchedule(robots(6,6),43.1);
 assert.equal(intro.introAt(cuts,0).cut.segment.kind,'open');
 const shot=intro.introAt(cuts,5+2.4+2.4+1.2);assert.equal(shot.cut.segment.id,'red-2');assert.ok(Math.abs(shot.progress-.5)<1e-9);
 assert.equal(intro.introAt(cuts,99).cut.segment.kind,'faceoff');assert.equal(intro.introAt(cuts,99).progress,1);
 assert.equal(intro.introAt([],1),null);
});
test('model names map to the twelve LLM makers',()=>{
 for(const [model,provider] of [['Claude Opus 5.5','anthropic'],['GPT-5','openai'],['o3-mini','openai'],['Gemini 3 Pro','google'],['Llama 4 Maverick','meta'],['Grok 4','spacexai'],['Kimi K2','moonshot'],['GLM-4.6','zai'],['MiMo-V2-Flash','xiaomi'],['DeepSeek-R2','deepseek'],['Qwen3-Coder','qwen'],['混元 T1','tencent-hy'],['Doubao Seed 1.6','bytedance-seed'],['handwritten',null]])assert.equal(agents.detectProvider(model),provider,model);
 assert.equal(agents.LLM_PROVIDERS.length,12);for(const p of agents.LLM_PROVIDERS)assert.ok(agents.PROVIDERS[p].color);
});
test('a team shows its one maker, the mixed emblem for several, and old replays none',()=>{
 const meta=(red)=>({teams:{red:{name:'r',version:'v',mode:'adaptive'},blue:{name:'b',version:'v',mode:'team',agent:{provider:'openai',model:'GPT-5'}}},agents:{red}});
 const mixed=meta({1:{provider:'anthropic',model:'Claude Opus 5.5'},2:{provider:'qwen'},3:{provider:'anthropic',model:'Claude Opus 5.5'}});
 assert.equal(agents.teamEmblem(mixed,'red'),'mixed');assert.equal(agents.teamAgents(mixed,'red').length,2);
 assert.equal(agents.robotAgent(mixed,'red',2).provider,'qwen');
 assert.equal(agents.teamEmblem(meta({1:{provider:'anthropic',model:'Claude Opus 5.5'},2:{provider:'anthropic',model:'Claude Sonnet 5.5'}}),'red'),'anthropic');
 assert.equal(agents.teamEmblem(mixed,'blue'),'openai');assert.equal(agents.robotAgent(mixed,'blue',4).model,'GPT-5');
 assert.equal(agents.teamEmblem({teams:{red:{name:'old',version:'v',mode:'team'}}},'red'),null);
});
