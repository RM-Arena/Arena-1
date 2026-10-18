const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const scope={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync('frontend/src/matchDiagnostics.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,scope);
const {isCleanFinish,matchStatus,matchEventKey,policyErrorText}=scope.exports;

test('finished legacy records with policy errors are abnormal and excluded from normal finishes',()=>{
 const bad={status:'finished',result:{policy_errors:2}},good={status:'finished',result:{policy_errors:0}};
 assert.equal(isCleanFinish(bad),false);assert.equal(isCleanFinish(good),true);
 assert.equal(matchStatus(bad).label,'异常完成');assert.equal(matchStatus(bad).className,'error');assert.match(matchStatus(bad).detail,/2 次.*未计入 Elo/);
 assert.equal(matchStatus(good).label,'已完成');assert.equal(matchStatus(good).detail,'');
 assert.equal(isCleanFinish({status:'stopped',result:{policy_errors:0}}),false);
 assert.equal(matchStatus({status:'error',error:'Rust engine exited unexpectedly'}).label,'运行错误');
 assert.equal(matchStatus({status:'error',error:'Rust engine exited unexpectedly'}).detail,'Rust engine exited unexpectedly');
 assert.equal(matchStatus({status:'stopped',result:{policy_errors:1}}).detail,'策略异常 1 次');
});

test('legacy errors on the same tick preserve both teams and every independent policy',()=>{
 const base={type:'policy_error',tick:4824,message:'decision exceeded deadline'},events=[{...base,team:'red',slots:null},{...base,team:'blue',slots:null},{...base,team:'red',slots:[3]},{...base,team:'red',slots:[4]}];
 assert.equal(new Set(events.map(matchEventKey)).size,4);
 assert.equal(matchEventKey(events[0]),matchEventKey(JSON.parse(JSON.stringify(events[0]))));
 assert.equal(matchEventKey({...base,id:'policy:red:team:4824'}),'policy:red:team:4824');
});

test('timeout messages distinguish a skipped decision, repeated failure and legacy shutdown',()=>{
 const base={type:'policy_error',tick:4824,team:'red',message:'decision exceeded deadline'};
 const retry=policyErrorText({...base,disabled:false,consecutive_timeouts:1});
 assert.match(retry,/红方全队策略.*本轮跳过.*继续尝试/);assert.doesNotMatch(retry,/停用/);
 assert.match(policyErrorText({...base,disabled:true,consecutive_timeouts:3}),/已停用.*连续 3 次决策超时/);
 assert.match(policyErrorText({...base,team:'blue'}),/蓝方全队策略已停用.*决策超时/);
 assert.match(policyErrorText({...base,slots:[3],message:'broken',disabled:true}),/红方3 号策略已停用：broken/);
});
