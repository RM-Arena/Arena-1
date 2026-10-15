const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const scope={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync('frontend/src/deckCatalog.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,scope);
const {groupRobotCards,filterRobotGroups,applyDeckTactic,summarizeDeck}=scope.exports;
const plain=x=>JSON.parse(JSON.stringify(x));
const cards={
 custom:{mode:'adaptive',robot:305,model_name:'串联腿步兵',role:'infantry',name:'自定义305',version:'custom'},
 b:{mode:'adaptive',robot:305,model_name:'串联腿步兵',role:'infantry',name:'b',preset:{id:'balanced',name:'均衡推进'}},
 g:{mode:'adaptive',robot:305,model_name:'串联腿步兵',role:'infantry',name:'g',preset:{id:'guard',name:'阵地防守'}},
 a:{mode:'adaptive',robot:305,model_name:'串联腿步兵',role:'infantry',name:'a',preset:{id:'assault',name:'前线突击'}},
 eng:{mode:'adaptive',robot:2,role:'engineer',model_name:'工程机器人',name:'eng',preset:{id:'guard',name:'救援优先'}},
 team:{mode:'team',name:'whole team'}
};
test('many versions form one model, with three presets before custom strategies',()=>{
 const groups=groupRobotCards(cards);assert.deepEqual(plain(groups.map(g=>g.model)),[2,305]);assert.deepEqual(plain(groups[1].choices.map(c=>c.id)),['b','a','g','custom']);
});
test('search finds model names, numbers, preset names and custom names, together with role filtering',()=>{
 const groups=groupRobotCards(cards);for(const query of ['305','串联腿','阵地防守','自定义'])assert.deepEqual(plain(filterRobotGroups(groups,query,'all').map(g=>g.model)),[305]);
 assert.equal(filterRobotGroups(groups,'305','engineer').length,0);assert.equal(filterRobotGroups(groups,'  救援  ','engineer').length,1);
});
test('bulk tactic preserves duplicate counts and missing cards without crossing model types',()=>{
 const original=['custom','b','eng','missing','custom'];assert.deepEqual(plain(applyDeckTactic(original,cards,'guard')),['g','g','eng','missing','g']);assert.equal(original[0],'custom');
 assert.deepEqual(plain(applyDeckTactic(original,cards,'assault')),['a','a','eng','missing','a']);
});
test('compact match summary groups only identical strategies',()=>{assert.deepEqual(plain(summarizeDeck(['a','b','a','g','b'])),[{id:'a',count:2},{id:'b',count:2},{id:'g',count:1}]);});
