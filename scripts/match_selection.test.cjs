const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const scope={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync('frontend/src/matchSelection.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,scope);
const {canDeleteMatch,reconcileSelection,selectionSummary,deleteMatchRecords}=scope.exports;
const matches=[{id:'done',status:'finished',replay_bytes:3000},{id:'stopped',status:'stopped',replay_bytes:2000},{id:'broken',status:'error'},{id:'live',status:'running',replay_bytes:1000},{id:'init',status:'initializing'}];
test('select all excludes active matches and totals only selected replay bytes',()=>{
 const summary=selectionSummary(new Set(matches.map(m=>m.id)),matches);
 assert.deepEqual(Array.from(summary.selected,m=>m.id),['done','stopped','broken']);assert.equal(summary.all,true);assert.equal(summary.mixed,false);assert.equal(summary.bytes,5000);
 assert.equal(canDeleteMatch(matches[3]),false);assert.equal(canDeleteMatch(matches[4]),false);
});
test('partial selection is indeterminate and empty journals are not all selected',()=>{
 assert.equal(selectionSummary(new Set(['done']),matches).mixed,true);assert.equal(selectionSummary(new Set(),[]).all,false);
});
test('refresh removes deleted, stale and newly running selections',()=>{
 const ids=reconcileSelection(new Set(['done','live','init','missing','broken']),matches);
 assert.deepEqual(Array.from(ids),['done','broken']);
 assert.deepEqual(Array.from(reconcileSelection(ids,[{id:'done',status:'running'},{id:'broken',status:'error'}])),['broken']);
});
test('partial deletion treats 404 as success, retains failures, and reports monotonic progress',async()=>{
 const progress=[],calls=[];
 const result=await deleteMatchRecords(['ok','gone','busy','network'],async id=>{calls.push(id);if(id==='network')throw Error('offline');return {ok:id==='ok',status:id==='gone'?404:id==='busy'?409:200};},done=>progress.push(done));
 assert.deepEqual([...result.deleted].sort(),['gone','ok']);assert.deepEqual(Array.from(result.failed,item=>item.id).sort(),['busy','network']);
 assert.match(result.failed.find(item=>item.id==='busy').message,/仍在进行/);assert.match(result.failed.find(item=>item.id==='network').message,/连接/);
 assert.deepEqual(progress,[1,2,3,4]);assert.equal(calls.length,4);
 const retry=await deleteMatchRecords(Array.from(result.failed,item=>item.id),async()=>({ok:true,status:200}));assert.equal(retry.deleted.length,2);assert.equal(retry.failed.length,0);
});
test('large batches cap concurrent requests at four and delete every record once',async()=>{
 let active=0,maximum=0;const ids=Array.from({length:37},(_,i)=>String(i)),calls=[];
 const result=await deleteMatchRecords(ids,async id=>{active++;maximum=Math.max(maximum,active);calls.push(id);await new Promise(resolve=>setImmediate(resolve));active--;return {ok:true,status:200};});
 assert.equal(maximum,4);assert.equal(result.deleted.length,37);assert.equal(new Set(calls).size,37);assert.equal(result.failed.length,0);
});
