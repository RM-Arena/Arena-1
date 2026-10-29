const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
const source=fs.readFileSync(path.join(__dirname,'../frontend/src/buffs.ts'),'utf8');
const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
// `buffs.ts` only needs `frameSeason` at runtime; the frame/robot shapes are types.
const types={frameSeason:f=>f.season==='2027'||f.arena?.name==='rmuc2027'?'2027':'2026'};
const scope={exports:{},require:name=>name==='./types'?types:null};
vm.runInNewContext(code,scope);
const {robotBuffs}=scope.exports;
const frame=(season='2027')=>({season,arena:{name:season==='2027'?'rmuc2027':'rmuc2026'},
  robot_models:{'3':{initial_stats:{power_w:100},initial_stats_by_season:{'2027':{power_w:120}}}}});
const robot=(patch={})=>({role:'infantry',model_slot:3,cooling_rate:40,cooling_multiplier:1,cooling_bonus:0,
  attack_multiplier:1,defense_buff:0,vulnerability:0,power_limit:120,shield:0,...patch});
const chip=(chips,kind)=>chips.find(c=>c.kind===kind);

test('fortress gains print the final cooling rate, not the raw bonus',()=>{
 // Own fortress on a 40/s barrel: w = 75 is a flat +75/s, so the effective rate is 115/s = 288 %.
 const own=robotBuffs(robot({defense_buff:.5,cooling_bonus:75}),frame());
 assert.equal(chip(own,'defense').text,'50%');
 assert.equal(chip(own,'cooling').text,'288%');
 assert.match(chip(own,'cooling').title,/40 → 115/);
 // Same-kind cooling takes the maximum of multiplier and flat bonus: 40×5 beats 40+75.
 const rune=robotBuffs(robot({cooling_multiplier:5,cooling_bonus:75}),frame());
 assert.equal(chip(rune,'cooling').text,'500%');
});
test('enemy fortress is shown as vulnerability, and defence stays a separate chip',()=>{
 const enemy=robotBuffs(robot({vulnerability:1}),frame());
 assert.equal(chip(enemy,'vulnerability').text,'100%');
 assert.equal(chip(enemy,'vulnerability').title,'易伤：受到伤害 ×2');
 assert.equal(chip(enemy,'defense'),undefined);
 const both=robotBuffs(robot({defense_buff:.25,vulnerability:.15}),frame());
 assert.equal(chip(both,'defense').text,'25%');
 assert.equal(chip(both,'vulnerability').text,'15%');
});
test('attack, power and status chips use the engine values',()=>{
 const attack=robotBuffs(robot({attack_multiplier:2}),frame());
 assert.equal(chip(attack,'attack').text,'200%');
 const power=robotBuffs(robot({power_limit:150}),frame());
 assert.equal(chip(power,'power').text,'125%','120 W design, 150 W now');
 assert.match(chip(power,'power').title,/120 → 150 W/);
 const status=robotBuffs(robot({invulnerable:true,shield:2.4,overheated:true}),frame());
 assert.equal(chip(status,'invulnerable').text,'3s');
 assert.equal(chip(status,'heat').text,'过热');
});
test('a robot with no gains has no chips, and permanent locks replace the soft ones',()=>{
 assert.equal(robotBuffs(robot(),frame()).length,0);
 const locked=robotBuffs(robot({overheated:true,heat_permanent_lock:true,overspeed_locked:true}),frame());
 assert.deepEqual(Array.from(locked,c=>c.kind),['lock']);
 assert.equal(chip(locked,'lock').text,'禁发');
});
