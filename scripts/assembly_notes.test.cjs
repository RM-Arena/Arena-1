const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
const source=fs.readFileSync(path.join(__dirname,'../frontend/src/assemblyNotes.ts'),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}});
const context={exports:{}};vm.runInNewContext(compiled.outputText,context);
const {assemblyFailText,ASSEMBLY_FAIL_TEXT}=context.exports;

test('every rulebook failure reason has a pilot-facing sentence',()=>{
  // The engine reports these from both seasons: 2027 (card loss, death, pairing, timeout) and the
  // 2026 attempt clock / second-core window.
  for(const reason of ['left_assembly_area','heavy_destroyed','unit_extracted','pair_window','timeout','secondary_window','core_window']){
    assert.ok(ASSEMBLY_FAIL_TEXT[reason],reason);
    assert.notEqual(assemblyFailText(reason),reason,reason);
  }
  assert.match(assemblyFailText('left_assembly_area'),/15 秒/);
  assert.match(assemblyFailText('heavy_destroyed'),/击毁/);
  assert.match(assemblyFailText('unit_extracted'),/取出/);
});

test('unknown or missing reasons still produce something readable',()=>{
  assert.equal(assemblyFailText('engine_only_reason'),'engine_only_reason');
  assert.equal(assemblyFailText(undefined),'装配未完成');
  assert.equal(assemblyFailText(null),'装配未完成');
});
