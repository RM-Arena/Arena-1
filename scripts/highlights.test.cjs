const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
const roleNames={hero:'英雄',engineer:'工程',infantry:'步兵',sentry:'哨兵',scout:'侦察',aerial:'空中',heavy:'重装'};
function compile(name,imports={}){
 const source=fs.readFileSync(path.join(__dirname,'../frontend/src/'+name+'.ts'),'utf8');
 const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 const scope={exports:{},require:n=>{if(!(n in imports))throw new Error('Unexpected import '+n);return imports[n];},Map,Set,Math,Number,Object,Array,String,Error,...imports};
 vm.runInNewContext(code,scope);return scope.exports;
}
const highlights=compile('highlights',{
 './types':{ROLE_NAMES:roleNames},
 './matchStats':{TEAM_LABEL:{red:'红方',blue:'蓝方'},robotName:r=>r.design_name||roleNames[r.role]},
});

const robot=(id,team,slot,role,damage=0)=>({id,team,slot,role,damage,design_name:id.toUpperCase()});
const robots=[robot('red-3','red',3,'infantry',900),robot('red-4','red',4,'infantry',200),
 robot('blue-4','blue',4,'infantry',300),robot('blue-5','blue',5,'infantry',100),robot('blue-6','blue',6,'hero',50)];
const events=[];
// Seven attributed hits give the top damage dealer a sustained-fire window.
for(let i=0;i<7;i++)events.push({type:'hit',tick:200+i,time:10+i*.3,robot:'blue-4',source:'red-3',team:'red',damage:30,x:1,y:1});
events.push({type:'destroy',tick:230,time:10.5,robot:'blue-4',killer:'red-3',team:'red'});
events.push({type:'destroy',tick:260,time:13,robot:'blue-5',killer:'red-3',team:'red'});
events.push({type:'destroy',tick:600,time:30,robot:'blue-6',killer:'red-4',team:'red'});
events.push({type:'base_hit',tick:800,time:40,robot:'red-3',team:'red',target_team:'blue',damage:160,x:2,y:2});
events.push({type:'base_hit',tick:806,time:40.3,robot:'red-3',team:'red',target_team:'blue',damage:140,x:2,y:2});
const frame={winner:'red',robots};

test('the reel is three beats long and carries both sides of every exchange',()=>{
 const reel=highlights.highlightReel(events,frame);
 assert.equal(reel.length,3,'the post-match reel is three beats');
 const times=Array.from(reel,c=>c.time);
 assert.deepEqual(times,[...times].sort((a,b)=>a-b),'beats stay in match order');
 for(const clip of reel)assert.ok(clip.rival||clip.rivalTeam,clip.key+' names the receiving side');
 const destroyed=reel.find(c=>c.victims.length>0);
 assert.ok(destroyed,'a kill beat survives the cut');
 assert.ok(destroyed.rival,'the destroyed robot is the receiving unit');
 assert.equal(highlights.clipRival(destroyed),destroyed.rival,'the camera can cut to it');
 assert.ok(destroyed.caption.includes('击毁'),'the receiving unit is named in the caption');
});
