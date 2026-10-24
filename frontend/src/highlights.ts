import type {Frame,MatchEvent,Robot,TeamId} from './types';
import {ROLE_NAMES} from './types';
import {TEAM_LABEL,robotName} from './matchStats';

// One five-second beat of the post-match reel. The reel is built from the referee's own event log, so
// it never invents a moment: every clip points at a tick that really happened.
export interface HighlightClip{
  key:string;
  kind:'kill'|'multi'|'structure'|'objective'|'damage'|'siege'|'air'|'output'|'pressure';
  /** Match seconds of the moment, used for the time stamp. */
  time:number;
  /** Big headline of the clip, e.g. 「三连击」. */
  title:string;
  /** One line of context under the headline. */
  caption:string;
  /** Robot the clip is about (the killer, the chassis carrying the damage, or the drone's hangar). */
  star:string|null;
  /** Drone to ride when the beat is an aerial strike: the camera follows this small body. */
  drone?:string|null;
  /** Robots destroyed inside this clip. */
  victims:string[];
  /** Damage the star dealt inside the clip window. */
  damage:number;
  score:number;
}

const CLIP_SECONDS=5;
// How far before the moment the clip starts, so the shot that kills is seen arriving rather than
// already resolved: 1.5 s of run-up inside the same five-second window.
export const CLIP_PREROLL=1.5;

export {CLIP_SECONDS};
// Six beats keep the reel near half a minute while leaving room for siege damage, a sustained
// burst and the match's top output instead of four single kills.
const MAX_CLIPS=6;
// How far apart two kills may be and still read as one highlight beat.
const COMBO_GAP=8;
const CLIP_WINDOW=COMBO_GAP;

const timeOf=(e:MatchEvent)=>e.time??e.tick*.05;
const structureOf=(id?:string)=>!!id&&(id.includes('outpost')||id.includes('base'));
const isRobotId=(id?:string)=>!!id&&(id.startsWith('red-')||id.startsWith('blue-'));
const teamOf=(id?:string|null):TeamId|null=>id?.startsWith('red')?'red':id?.startsWith('blue')?'blue':null;
// A drone id is `<team>-<slot>-d<index>`; its hangar is the aerial robot that launched it.
const droneParent=(id?:string)=>id&&/-d\d+$/.test(id)?id.slice(0,id.lastIndexOf('-d')):null;
// Which robot gets the credit for an attack event. `hit.robot` is the victim, so only the shooter's
// `source` counts there; structure hits name their attacker in `robot` (2027) or `drone`.
function attackerOf(e:MatchEvent):string|null{
  if(e.type==='hit')return e.source??null;
  if(e.type==='base_hit'||e.type==='outpost_hit')return e.robot??droneParent(e.drone)??null;
  if(e.type==='drone_strike')return droneParent(e.drone)??null;
  return null;
}
const attackerTeam=(e:MatchEvent):TeamId|null=>e.team??teamOf(attackerOf(e))??teamOf(e.robot)??teamOf(e.drone);

function comboTitle(count:number){
  return count>=4?'四连击':count===3?'三连击':count===2?'双杀':'击毁';
}
const labelOf=(r:Robot)=>`${TEAM_LABEL[r.team]} ${r.slot} 号 ${robotName(r)}`;

// Damage the given team dealt in the window around `t`, which is what makes a clip feel big.
function damageIn(events:MatchEvent[],team:TeamId|null,t:number,window=CLIP_WINDOW){
  if(!team)return 0;
  let sum=0;
  for(const e of events){
    if(e.type!=='hit'&&e.type!=='base_hit'&&e.type!=='outpost_hit')continue;
    const at=timeOf(e);if(Math.abs(at-t)>window/2)continue;
    if(attackerTeam(e)!==team)continue;
    sum+=Math.max(0,e.damage||0);
  }
  return sum;
}

// One attacker's (or one team's) damage inside a five-second bucket.
interface Burst{by:string|null;team:TeamId|null;damage:number;hits:number;peakAt:number;peakDamage:number;targets:Set<string>;drone:string|null}
function addBurst(map:Map<string,Burst>,key:string,by:string|null,team:TeamId|null,at:number,damage:number,extra?:{target?:string;drone?:string}){
  const cell=map.get(key)??{by,team,damage:0,hits:0,peakAt:at,peakDamage:-1,targets:new Set<string>(),drone:null};
  cell.damage+=damage;cell.hits++;
  // The clip is cut at the shot that actually landed hardest, not at the middle of the bucket.
  if(damage>=cell.peakDamage){cell.peakDamage=damage;cell.peakAt=at;}
  if(extra?.target)cell.targets.add(extra.target);
  if(extra?.drone)cell.drone=extra.drone;
  map.set(key,cell);
}
const biggest=(map:Map<string,Burst>,limit:number)=>[...map.values()].sort((a,b)=>b.damage-a.damage||b.hits-a.hits).slice(0,limit);
const peakOf=(map:Map<string,Burst>,by:string)=>{
  let best:Burst|null=null;
  for(const b of map.values()){
    if(b.by!==by)continue;
    if(!best||b.damage>best.damage)best=b;
  }
  return best;
};

// Total damage each robot is known to have put into enemy robots and into enemy structures.
function credits(events:MatchEvent[]){
  const map=new Map<string,{robot:number;structure:number}>();
  const take=(id:string)=>{let c=map.get(id);if(!c){c={robot:0,structure:0};map.set(id,c);}return c;};
  for(const e of events){
    const amount=Math.max(0,e.damage||0);
    if(e.type==='hit'&&e.source)take(e.source).robot+=amount;
    else if((e.type==='base_hit'||e.type==='outpost_hit')&&amount>0){const by=attackerOf(e);if(by)take(by).structure+=amount;}
  }
  return map;
}

/**
 * Picks the post-match highlights out of a finished match. Multi-kills, structure kills, objective
 * plays, sustained fire and heavy structural damage all outrank a single kill on their own; the
 * match's top damage dealer always gets a beat that explains where that output came from, and an
 * aerial strike carries the drone whose chase camera should fly the clip.
 */
export function highlightReel(events:MatchEvent[],frame:Frame|null,limit=MAX_CLIPS):HighlightClip[]{
  if(!events.length||!frame)return [];
  const winner=frame.winner,robots=frame.robots;
  const timed=events.filter(e=>Number.isFinite(timeOf(e))).sort((a,b)=>timeOf(a)-timeOf(b));
  const clips:HighlightClip[]=[];
  // Two clips that sit on top of each other are the same moment: keep the better one. Returns the
  // clip that is actually stored, so a guaranteed beat can be found again after de-duplication.
  const push=(clip:HighlightClip):HighlightClip=>{
    // Two beats less than one clip apart would replay frames the viewer just saw; anything wider
    // is a different moment and deserves its own cut.
    const twin=clips.find(c=>Math.abs(c.time-clip.time)<CLIP_SECONDS);
    if(twin){if(clip.score>twin.score)Object.assign(twin,clip);return twin;}
    clips.push(clip);return clip;
  };

  // ---- kills, grouped per killer so a double or triple reads as one beat
  const kills=timed.filter(e=>e.type==='destroy'&&isRobotId(e.robot)&&!structureOf(e.robot));
  const byKiller=new Map<string,MatchEvent[]>();
  for(const kill of kills){
    const key=kill.killer||`?${kill.tick}`;
    const list=byKiller.get(key)??[];
    const last=list.at(-1);
    if(last&&timeOf(kill)-timeOf(last)>COMBO_GAP)list.length=0;
    list.push(kill);byKiller.set(key,list);
  }
  for(const [killer,list] of byKiller){
    const team=teamOf(killer);
    const at=timeOf(list.at(-1)!);
    const damage=damageIn(timed,team,at);
    const bonus=team&&team===winner?70:0;
    const count=list.length;
    const star=robots.find(r=>r.id===killer);
    // A lone kill is filler, not a highlight: it only enters the reel when the match produced too
    // little else. Multi-kills keep their weight.
    push({
      key:`kill:${killer}:${list[0].tick}`,kind:count>=2?'multi':'kill',time:at,
      title:comboTitle(count),
      caption:count>=2
        ?`${star?labelOf(star):`${TEAM_LABEL[team||'red']} ${killer}`} 在 ${COMBO_GAP} 秒内连续击毁 ${count} 台敌方机器人`
        :`${star?labelOf(star):`${TEAM_LABEL[team||'red']} ${killer}`} 击毁 1 台敌方机器人`,
      star:star?.id??null,victims:list.map(k=>k.robot!),damage,
      score:count>=2?220+count*90+bonus+Math.min(60,damage*.4):70+bonus*.4+Math.min(20,damage*.2),
    });
  }

  // ---- structures: an outpost or a base going down decides matches
  for(const e of timed){
    if(e.type==='outpost_destroyed'){
      const owner=e.team as TeamId|undefined;
      const team=teamOf((e as {by?:string}).by)??teamOf(owner);
      // The event names the outpost's original side; when attacker and side match, the plate had
      // been rebuilt by the enemy and is being taken back.
      const caption=team&&owner
        ?(team===owner?`${TEAM_LABEL[team]}摧毁易主的前哨站，重新夺回点位`:`${TEAM_LABEL[team]}打穿${TEAM_LABEL[owner]}前哨站，控制点易手`)
        :'前哨站被摧毁，控制点易手';
      push({
        key:`outpost:${e.tick}`,kind:'structure',time:timeOf(e),title:'前哨站被摧毁',
        caption,
        star:null,victims:[],damage:damageIn(timed,team,timeOf(e)),score:320,
      });
    }else if(e.type==='base_armor_opened'){
      const owner=e.team as TeamId|undefined,star=isRobotId(e.robot)?e.robot!:null;
      const team=teamOf(star)??teamOf(owner);
      const starRobot=star?robots.find(r=>r.id===star)??null:null;
      push({
        key:`base-open:${e.tick}`,kind:'structure',time:timeOf(e),title:'基地装甲开启',
        caption:`${starRobot?labelOf(starRobot):(team?TEAM_LABEL[team]:'')}顶住基地火力，${owner?TEAM_LABEL[owner]:''}基地装甲被迫打开`,
        star,victims:[],damage:damageIn(timed,team,timeOf(e)),score:240,
      });
    }else if(e.type==='destroy'&&structureOf(e.robot)){
      const team=teamOf(e.killer)??teamOf(e.robot);
      const kind=e.robot!.includes('base')?'基地装甲被打穿':'前哨站被摧毁';
      push({
        key:`struct:${e.robot}:${e.tick}`,kind:'structure',time:timeOf(e),title:kind,
        caption:`${team?TEAM_LABEL[team]:''}完成对${e.robot!.includes('base')?'基地':'前哨站'}的压制，战场天平倾斜`,
        star:e.killer&&isRobotId(e.killer)?e.killer:null,victims:[],damage:damageIn(timed,team,timeOf(e)),
        score:300+(team===winner?60:0),
      });
    }
  }

  // ---- objectives: runes and high-level assembly
  for(const e of timed){
    if(e.type==='rune_activated'){
      const team=e.team as TeamId|undefined;
      push({key:`rune:${e.tick}`,kind:'objective',time:timeOf(e),title:'能量机关激活',
        caption:`${team?TEAM_LABEL[team]:''}触发能量机关，全队获得增益`,star:null,victims:[],
        damage:damageIn(timed,team??null,timeOf(e)),score:150+(team===winner?40:0)});
    }else if(e.type==='assembly_success'){
      const level=(e as {difficulty?:number}).difficulty||1;
      if(level<3)continue;
      const team=e.team as TeamId|undefined;
      push({key:`assembly:${e.tick}`,kind:'objective',time:timeOf(e),title:`${level} 级装配完成`,
        caption:`${team?TEAM_LABEL[team]:''}科技核心升级到 ${level} 级${level===4?'，本场唯一一次四级装配':''}`,
        star:isRobotId(e.robot)?e.robot!:null,victims:[],damage:damageIn(timed,team??null,timeOf(e)),score:160});
    }
  }

  // ---- damage buckets: per attacker (new events carry `source`/`robot`) and per team (older
  // replays only name the attacker's team). The attacker buckets are the source of the sustained
  // fire beats, the siege beats and the top-output beat.
  const attackerBursts=new Map<string,Burst>(),teamBursts=new Map<string,Burst>(),siegeBursts=new Map<string,Burst>(),airBursts=new Map<string,Burst>();
  for(const e of timed){
    const at=timeOf(e),slot=Math.floor(at/CLIP_SECONDS);
    if(e.type==='base_hit'||e.type==='outpost_hit'){
      const amount=Math.max(0,e.damage||0);
      const by=attackerOf(e),team=attackerTeam(e),drone=e.drone??null;
      if(team)addBurst(teamBursts,`${team}:${slot}`,null,team,at,amount);
      if(by){
        addBurst(attackerBursts,`${by}:${slot}`,by,team,at,amount);
        if(drone){
          const hangar=droneParent(drone);
          if(hangar)addBurst(airBursts,`${hangar}:${slot}`,hangar,team,at,amount,{target:e.type==='outpost_hit'?'前哨站':'基地',drone});
        }else addBurst(siegeBursts,`${by}:${slot}`,by,team,at,amount,{target:e.type==='outpost_hit'?'前哨站':'基地'});
      }
    }else if(e.type==='hit'){
      const amount=Math.max(0,e.damage||0),team=attackerTeam(e);
      if(team)addBurst(teamBursts,`${team}:${slot}`,null,team,at,amount);
      if(e.source)addBurst(attackerBursts,`${e.source}:${slot}`,e.source,team,at,amount);
    }
  }

  // ---- siege: a robot pouring fire into a structure. Rounds on a plate are small, so the bar is
  // higher than a single hit but low enough for a real 42 mm sequence to clear it.
  let siegeTop:HighlightClip|null=null;
  for(const b of biggest(siegeBursts,3)){
    if(b.damage<40)break;
    const star=b.by?robots.find(r=>r.id===b.by)??null:null,team=b.team;
    const targets=[...b.targets].join('、')||'建筑';
    const clip=push({
      key:`siege:${b.by??team}:${Math.round(b.peakAt)}`,kind:'siege',time:b.peakAt,
      title:b.damage>=150?'建筑连续爆破':'建筑火力压制',
      caption:`${star?labelOf(star):`${team?TEAM_LABEL[team]:''}全队`}在 5 秒内对${targets}造成 ${Math.round(b.damage)} 点结构伤害（${b.hits} 次命中）`,
      star:star?.id??null,victims:[],damage:b.damage,score:300+b.damage*.5,
    });
    if(clip.kind==='siege')siegeTop??=clip;
  }

  // ---- aerial: drones chewing through armour. This is the one beat whose camera rides a small
  // body rather than the hangar: `drone` names the last drone that struck inside the window.
  let airTop:HighlightClip|null=null;
  for(const b of biggest(airBursts,3)){
    if(b.damage<100&&b.hits<2)continue;
    const star=b.by?robots.find(r=>r.id===b.by)??null:null;
    const targets=[...b.targets].join('、')||'建筑';
    const clip=push({
      key:`air:${b.by}:${Math.round(b.peakAt)}`,kind:'air',time:b.peakAt,
      title:b.hits>=2?'无人机连续破甲':'无人机精准破甲',
      caption:`${star?labelOf(star):'空中机器人'}的无人机在 5 秒内 ${b.hits} 次撞击${targets}，造成 ${Math.round(b.damage)} 点结构伤害`,
      star:star?.id??null,drone:b.drone,victims:[],damage:b.damage,score:340+b.damage*.45,
    });
    if(clip.kind==='air')airTop??=clip;
  }

  // ---- sustained fire: the chassis that kept landing hits, not the one that landed the last one.
  // Aerial hangars are skipped because their drones already own the air beat.
  let pressureTop:HighlightClip|null=null;
  for(const b of biggest(attackerBursts,6)){
    if(!b.by||(b.hits<6&&b.damage<60))continue;
    const star=robots.find(r=>r.id===b.by);
    if(!star||star.role==='aerial')continue;
    const clip=push({
      key:`pressure:${b.by}:${Math.round(b.peakAt)}`,kind:'pressure',time:b.peakAt,title:'连续火力输出',
      caption:`${labelOf(star)}在 5 秒内命中 ${b.hits} 次，打出 ${Math.round(b.damage)} 点伤害，形成连续压制`,
      star:star.id,victims:[],damage:b.damage,score:200+b.damage*.35+b.hits*4,
    });
    if(clip.kind==='pressure')pressureTop??=clip;
  }

  // ---- the match's top damage dealer: one beat that says how much, where it came from, and which
  // five seconds carried the peak. This is the "本局输出高在哪里" card the reel always keeps.
  let outputTop:HighlightClip|null=null;
  const top=robots.reduce<Robot|null>((best,r)=>!best||r.damage>best.damage?r:best,null);
  if(top&&top.damage>0){
    // Only this robot's own attributed windows can explain its output; a team bucket would credit
    // somebody else and the camera would follow the wrong chassis.
    const peak=peakOf(attackerBursts,top.id);
    if(peak&&peak.damage>0){
      const credit=credits(timed).get(top.id)??{robot:0,structure:0};
      const parts:string[]=[];
      if(credit.robot>0)parts.push(`对机器人 ${Math.round(credit.robot)}`);
      if(credit.structure>0)parts.push(`对建筑 ${Math.round(credit.structure)}`);
      const stamp=`${labelOf(top)}全场 ${Math.round(top.damage)} 点伤害${parts.length?`（${parts.join('、')}）`:''}，最高 5 秒 ${Math.round(peak.damage)} 点`;
      // If the peak already is a siege/aerial/continuous beat, fold the output story into that beat
      // instead of cutting the same five seconds twice. The drone camera and kind stay intact.
      const twin=clips.find(c=>Math.abs(c.time-peak.peakAt)<CLIP_SECONDS);
      // A structure/objective beat at the same tick has no star yet: it is the moment this robot's
      // peak landed, so giving it the star both explains the output and gives the clip a camera.
      if(twin&&(!twin.star||twin.star===top.id)){
        twin.star=top.id;
        twin.title=`输出王 · ${twin.title}`;
        twin.caption=`${stamp}。${twin.caption}`;
        twin.score=Math.max(twin.score,480+Math.min(100,top.damage*.05));
        outputTop=twin;
      }else if(!twin){
        outputTop=push({
          key:`output:${top.id}`,kind:'output',time:peak.peakAt,title:'本局输出王',
          caption:`${stamp}，是全场最集中的火力`,
          star:top.id,victims:[],damage:peak.damage,score:480+Math.min(100,top.damage*.05),
        });
      }
    }
  }

  // ---- team-level fallback that guarantees beats even on an older replay whose events never
  // named the shooter. The star is left empty rather than guessed.
  for(const b of biggest(teamBursts,2)){
    if(b.damage<1)break;
    push({
      key:`dmg:${b.team}:${Math.round(b.peakAt)}`,kind:'damage',time:b.peakAt,
      title:`${Math.round(b.damage)} 点火力输出`,
      caption:`${b.team?TEAM_LABEL[b.team]:''}全队在 5 秒内打出这一时段最高火力`,
      star:null,victims:[],damage:b.damage,score:90+b.damage*.25,
    });
  }

  // Pick by score, then make sure the beats the reel must explain survive the cut: the top-output
  // card and the biggest siege/aerial strike replace the lowest-scoring filler when they miss it.
  const max=Math.max(1,Math.min(MAX_CLIPS,limit));
  // A single kill is the last resort: it only appears when the other beats cannot even make a
  // four-beat reel. A match with real siege, air and sustained-fire moments never shows one.
  const meaningful=clips.filter(c=>c.kind!=='kill');
  const pool=meaningful.length>=Math.min(max,4)?meaningful:clips;
  const picked=[...pool].sort((a,b)=>b.score-a.score||b.damage-a.damage||b.time-a.time).slice(0,max);
  const must=[outputTop,siegeTop,airTop,pressureTop].filter((c):c is HighlightClip=>!!c);
  for(const clip of must){
    if(picked.includes(clip))continue;
    if(picked.length<max){picked.push(clip);continue;}
    let index=-1,worst=Number.POSITIVE_INFINITY;
    for(let i=0;i<picked.length;i++){
      if(must.includes(picked[i]))continue;
      if(picked[i].score<worst){worst=picked[i].score;index=i;}
    }
    if(index>=0)picked[index]=clip;
  }
  return picked.sort((a,b)=>a.time-b.time);
}

// Readable time stamp of a clip: match clock, not wall clock.
export function clipClock(seconds:number){
  const total=Math.max(0,Math.round(seconds));const m=Math.floor(total/60),s=total%60;
  return `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
}

export function clipStar(clip:HighlightClip,robots:Robot[]){
  return clip.star?robots.find(r=>r.id===clip.star)??null:null;
}

export function clipRole(clip:HighlightClip,robots:Robot[]){
  const r=clipStar(clip,robots);
  return r?ROLE_NAMES[r.role]:'';
}