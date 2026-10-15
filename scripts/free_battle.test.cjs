const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const scope={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync('frontend/src/freeBattle.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,scope);
const {isFreeBattle,freeStartOptions}=scope.exports;
test('free replays retain arbitrary lineups when both teams use whole-team strategies',()=>{
 assert.equal(isFreeBattle({match_mode:'deck',teams:{red:{mode:'team'},blue:{mode:'team'}}}),true);
 assert.equal(isFreeBattle({match_mode:'standard',teams:{red:{mode:'team'},blue:{mode:'team'}}}),false);
 assert.equal(isFreeBattle({teams:{red:{mode:'adaptive'},blue:{mode:'adaptive'}}}),true);
 assert.equal(!!isFreeBattle({teams:{red:{mode:'team'},blue:{mode:'team'}}}),false);
});
test('mixed controllers bind a global strategy only to the side that selected team mode',()=>{
 const options=JSON.parse(JSON.stringify(freeStartOptions({red:{mode:'team',strategy:'global-red'},blue:{mode:'independent',strategy:'unused-last-selection'}})));
 assert.deepEqual(options,{red_control:'team',blue_control:'independent',red_team_strategy:'global-red'});
});
