import { ArenaScene } from './scene.js';
import { ArenaAudio, BroadcastRecorder, clock, download } from './media.js';

const $=id=>document.getElementById(id);
const roles={hero:'英雄',engineer:'工程',infantry:'步兵',sentry:'哨兵',scout:'侦察'};
let scene,audio,recorder,frame,previous,received=0,lastRevision=-1,lastTick=-1,metadata=null;
let replay=null,replaySource=null,replayPosition=0,playing=true,speed=1,selected='red-1',eventCount=0,resultShown=false,busy=false,lastPoll=0,lastFrameTime=performance.now();

function showError(message){$('error').textContent=message||'';$('error').hidden=!message;}
async function api(path,data){const response=await fetch(path,data?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}:{});const value=await response.json();if(!response.ok||value.error)throw new Error(value.error||'服务请求失败');return value;}

function selectRobot(id){selected=id;$('follow-select').value=id;$('camera-mode').value='follow';scene.setCamera('follow',id);document.querySelectorAll('.robot-row').forEach(row=>row.classList.toggle('selected',row.dataset.id===id));}

function buildRoster(){for(const team of ['red','blue']){for(let slot=1;slot<=7;slot++){const id=`${team}-${slot}`,button=document.createElement('button');button.className='robot-row';button.dataset.id=id;button.title='跟随 '+id;
  const num=document.createElement('span');num.className='robot-num';num.textContent=slot;
  const info=document.createElement('span');info.className='robot-info';info.innerHTML='<div><span class="robot-role"></span><span class="robot-hp"></span></div><div class="hp-track"><div></div></div>';
  const ammo=document.createElement('span');ammo.className='robot-ammo';button.append(num,info,ammo);button.addEventListener('click',()=>selectRobot(id));$(team+'-roster').append(button);
  const option=document.createElement('option');option.value=id;option.textContent=`${team==='red'?'红':'蓝'}方 ${slot} 号`;$('follow-select').append(option);
}}}

function updateUI(){if(!frame)return;
  for(const team of ['red','blue']){$(team+'-score').textContent=Math.floor(frame.teams[team].score);$(team+'-base').textContent='基地 '+Math.ceil(frame.bases[team].hp);$(team+'-resources').textContent='资源 '+Math.floor(frame.teams[team].resources);if(metadata)$(team+'-name').textContent=metadata.teams[team].name.toUpperCase();}
  $('clock').textContent=clock(frame.remaining);$('match-tag').textContent=`SEED ${frame.seed} · ${frame.arena.name.toUpperCase()}`;
  $('match-state').textContent=replay?(playing?'回放播放中':'回放已暂停'):frame.status==='ready'?(busy?'正在启动策略容器':'等待策略入场'):frame.status==='finished'?'比赛结束':playing?'比赛进行中':'比赛已暂停';
  $('alive-count').textContent=frame.robots.filter(r=>r.alive).length+' / 14';
  for(const r of frame.robots){const row=document.querySelector(`[data-id="${r.id}"]`);row.classList.toggle('dead',!r.alive);row.classList.toggle('selected',r.id===selected);row.querySelector('.robot-role').textContent=roles[r.role]+(r.level>1?` · Lv${r.level}`:'');row.querySelector('.robot-hp').textContent=r.alive?Math.ceil(r.hp):'已退场';const bar=row.querySelector('.hp-track>div');bar.style.width=(r.hp/r.max_hp*100)+'%';bar.style.background=r.team==='red'?'var(--red)':'var(--blue)';row.querySelector('.robot-ammo').textContent=r.alive?r.ammo+' 发':'—';}
  $('elapsed').textContent=clock(frame.time);$('total').textContent=clock(frame.duration);$('timeline').max=replay?replay.frames.length-1:frame.duration*10;$('timeline').value=replay?replayPosition:frame.tick;$('timeline').disabled=!replay;
  $('zone-summary').textContent=Object.entries(frame.zones).map(([id,z])=>({center:'中央',north:'北侧',south:'南侧'}[id]+(z.owner==='red'?' · 红':z.owner==='blue'?' · 蓝':' · 中立'))).join(' / ');
  $('pause').textContent=playing?'Ⅱ 暂停':'▶ 继续';$('start').disabled=busy;$('stop').disabled=!busy||!!replay;
  if(frame.status==='finished'&&!resultShown){resultShown=true;$('result').hidden=false;$('result-title').textContent=frame.winner?(frame.winner==='red'?'红方胜利':'蓝方胜利'):'双方平局';$('result-title').style.color=frame.winner==='red'?'var(--red)':frame.winner==='blue'?'var(--blue)':'var(--gold)';$('result-detail').textContent=({timeout:'比赛时间结束',elimination:'对手全部机器人退场',base_destroyed:'对手基地被摧毁',stopped:'比赛手动结束'}[frame.reason]||'比赛结束')+` · ${Math.floor(frame.teams.red.score)} : ${Math.floor(frame.teams.blue.score)}`;}
}

function events(list,silent=false){for(const e of list){scene.effect(e);if(!silent)audio.play(e);let text;
  if(e.type==='destroy')text=`${e.killer} 击毁 ${e.robot}`;
  if(e.type==='capture'&&e.team)text=`${e.team==='red'?'红':'蓝'}方占领 ${e.zone}`;
  if(e.type==='upgrade')text=`${e.robot} 装备升级`;
  if(e.type==='finish')text=e.winner?(e.winner==='red'?'红方':'蓝方')+'赢得比赛':'比赛结束';
  if(e.type==='policy_error')text=`${e.team} ${e.slots||'全队'} 策略停用：${e.message}`;
  if(e.type==='invalid_action')text=`${e.robot||e.team} 非法动作：${e.reason}`;
  if(!text)continue;eventCount++;$('event-count').textContent=eventCount;const item=document.createElement('div');item.className='event-item'+(e.type.includes('error')||e.type==='invalid_action'?' error-event':'');const time=document.createElement('time');time.textContent=clock(e.tick*.1);const message=document.createElement('span');message.textContent=text;item.append(time,message);$('events').prepend(item);while($('events').children.length>30)$('events').lastChild.remove();
}}

async function poll(){if(replay)return;try{const data=await api('/api/state?since='+lastTick);$('connection').textContent='仿真引擎已连接';$('connection-dot').style.background='#87c5a2';$('sandbox-label').textContent=data.sandbox==='docker'?'Docker 隔离执行':'本地开发执行';busy=data.busy;playing=!data.paused;speed=data.speed;
  if(data.error)showError(data.error);if(data.revision!==lastRevision){previous=frame;frame=data.frame;received=performance.now();metadata=data.metadata;lastRevision=data.revision;if(frame.tick<lastTick){lastTick=-1;previous=null;}
    if(frame.tick>lastTick){events(data.events||frame.events);lastTick=frame.tick;}updateUI();}else updateUI();
}catch(e){$('connection').textContent='引擎连接断开';$('connection-dot').style.background='#ed7770';showError(e.message);}}

function validateReplay(data){
  if(data.format!=='rmuc-replay-v1'||!Array.isArray(data.frames)||!data.frames.length||data.frames.length>6002)throw new Error('无效的回放文件');
  if(!data.metadata?.teams?.red||!data.metadata?.teams?.blue)throw new Error('回放缺少队伍信息');
  for(const f of data.frames){if(!f.arena||!Array.isArray(f.robots)||f.robots.length!==14||!f.teams?.red||!f.teams?.blue||!f.bases?.red||!f.bases?.blue||!f.zones||!Array.isArray(f.projectiles)||!Array.isArray(f.events))throw new Error('回放帧格式不完整');if(!Number.isFinite(f.time)||!Number.isFinite(f.duration)||!['foundry','crossroads'].includes(f.arena.name))throw new Error('回放帧数据无效');for(const r of f.robots)if(!/^((red|blue)-[1-7])$/.test(r.id)||!Number.isFinite(r.x)||!Number.isFinite(r.y)||!Number.isFinite(r.hp))throw new Error('回放机器人数据无效');}
}
function loadReplay(data,source){validateReplay(data);replay=data;replaySource=source;metadata=data.metadata;replayPosition=0;frame=data.frames[0];previous=null;playing=true;resultShown=false;scene.clearEffects();$('result').hidden=true;$('events').replaceChildren();eventCount=0;$('event-count').textContent=0;$('mode-badge').innerHTML='<i></i> REPLAY';$('timeline-label').textContent='回放 · 可拖动时间轴';$('live').hidden=false;$('start').disabled=busy;showError(null);updateUI();}

try{scene=new ArenaScene($('viewport'),selectRobot);audio=new ArenaAudio();recorder=new BroadcastRecorder(scene,audio);buildRoster();}catch(e){showError('3D 初始化失败：'+e.message);throw e;}
await (async()=>{try{const catalog=await api('/api/catalog');for(const id of ['red-select','blue-select']){for(const [key,c] of Object.entries(catalog)){const o=document.createElement('option');o.value=key;o.textContent=c.name+(c.mode==='squad'?' · 7 独立策略':' · 全队策略');$(id).append(o);}}$('red-select').value='rush';$('blue-select').value='bastion';}catch(e){showError(e.message);}})();
await poll();

$('setup-form').addEventListener('submit',async e=>{e.preventDefault();try{await api('/api/start',{red:$('red-select').value,blue:$('blue-select').value,seed:Number($('seed').value),duration:Number($('duration').value),map:$('map-select').value});replay=null;resultShown=false;frame=null;previous=null;lastTick=-1;lastRevision=-1;$('result').hidden=true;$('events').replaceChildren();eventCount=0;$('event-count').textContent=0;$('mode-badge').innerHTML='<i></i> LIVE ARENA';$('timeline-label').textContent='实时观战';$('live').hidden=true;scene.clearEffects();busy=true;$('start').disabled=true;showError(null);await poll();}catch(e){showError(e.message);}});
$('pause').addEventListener('click',async()=>{if(replay){playing=!playing;updateUI();}else{try{await api('/api/control',{command:'pause'});await poll();}catch(e){showError(e.message);}}});
$('stop').addEventListener('click',async()=>{try{await api('/api/control',{command:'stop'});}catch(e){showError(e.message);}});
$('speed').addEventListener('change',async()=>{speed=Number($('speed').value);if(!replay){try{await api('/api/control',{command:'speed',speed});}catch(e){showError(e.message);}}});
$('camera-mode').addEventListener('change',()=>scene.setCamera($('camera-mode').value,selected));$('follow-select').addEventListener('change',()=>selectRobot($('follow-select').value));
$('sound').addEventListener('click',async()=>{try{if(audio.enabled){audio.disable();$('sound').textContent='♫ 开启音效';$('sound').classList.remove('active');}else{await audio.enable();$('sound').textContent='♫ 音效已开启';$('sound').classList.add('active');}}catch(e){showError(e.message);}});
$('record').addEventListener('click',async()=>{try{if(recorder.active){recorder.stop();$('record').innerHTML='<span class="rec-dot"></span> 开始录像';$('record').classList.remove('recording');$('record-hint').textContent='录像已导出 · WebM / 1080p';}else{await recorder.start();$('sound').textContent='♫ 音效已开启';$('sound').classList.add('active');$('record').textContent='■ 停止并导出录像';$('record').classList.add('recording');showError(null);}}catch(e){showError(e.message);}});
$('download').addEventListener('click',async()=>{try{const source=replay?replaySource:await (await fetch('/api/replay')).text();const data=JSON.parse(source);if(!data.frames?.length)throw new Error('请先运行一场比赛');download(new Blob([source],{type:'application/json'}),`rmuc-replay-${data.metadata.seed}.json`);}catch(e){showError(e.message);}});
$('load').addEventListener('click',()=>$('replay-file').click());$('replay-file').addEventListener('change',async e=>{try{const f=e.target.files[0];if(!f)return;if(f.size>100*1024*1024)throw new Error('回放文件不能超过 100 MiB');const source=await f.text();loadReplay(JSON.parse(source),source);}catch(e){showError(e.message);}finally{e.target.value='';}});
$('live').addEventListener('click',()=>{replay=null;frame=null;lastRevision=-1;lastTick=-1;$('live').hidden=true;$('result').hidden=true;resultShown=false;scene.clearEffects();$('mode-badge').innerHTML='<i></i> LIVE ARENA';$('timeline-label').textContent='实时观战';poll();});
$('timeline').addEventListener('input',()=>{if(!replay)return;replayPosition=Number($('timeline').value);previous=null;frame=replay.frames[Math.floor(replayPosition)];playing=false;scene.clearEffects();resultShown=true;$('result').hidden=true;updateUI();});
$('result-close').addEventListener('click',()=>$('result').hidden=true);

function animate(now){const dt=Math.min(.1,(now-lastFrameTime)/1000);lastFrameTime=now;
  if(replay&&playing){const old=Math.floor(replayPosition);replayPosition=Math.min(replay.frames.length-1,replayPosition+dt*10*speed);const index=Math.floor(replayPosition);for(let i=old+1;i<=index;i++)events(replay.frames[i].events);frame=replay.frames[index];previous=replay.frames[Math.max(0,index-1)];if(index===replay.frames.length-1)playing=false;updateUI();}
  const alpha=replay?(playing?replayPosition%1:1):Math.min(1,(now-received)/(100/speed));scene.update(frame,previous,alpha,dt,now/1000);recorder.draw(frame,metadata);
  if(recorder.active)$('record-hint').textContent='REC '+clock((now-recorder.started)/1000)+' · 1080p / 含音轨';
  if(now-lastPoll>80&&!replay){lastPoll=now;if(!animate.polling){animate.polling=true;poll().finally(()=>animate.polling=false);}}
  requestAnimationFrame(animate);
}
requestAnimationFrame(animate);
// Read-only diagnostics for browser QA; no policy code is exposed here.
window.arenaDiagnostics=()=>({tick:frame?.tick,robots:scene.robots.size,projectiles:scene.bullets.size,effects:scene.effects.length,recording:recorder.active,audioEnabled:audio.enabled,mode:replay?'replay':'live'});
