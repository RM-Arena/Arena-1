const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const {runtimeLayout} = require('./backend.cjs');
test('Windows bundle uses native executables and read-only resources',()=>{
  const value=runtimeLayout({packaged:true,resourcesPath:'/package/resources',platform:'win32'});
  assert.equal(value.python,path.join('/package','resources','runtime','python','python.exe'));
  assert.equal(value.root,path.join('/package','resources','runtime','app'));
});
test('Unix bundle keeps its standalone interpreter beside app resources',()=>{
  const value=runtimeLayout({packaged:true,resourcesPath:'/package/resources',platform:'darwin'});
  assert.equal(value.python,path.join('/package','resources','runtime','python','bin','python3'));
});
