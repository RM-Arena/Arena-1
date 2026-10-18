import {useEffect,useMemo,useRef,useState,type MutableRefObject} from 'react';
import {useFrame} from '@react-three/fiber';
import {Html} from '@react-three/drei';
import * as THREE from 'three';
import type {MatchEvent,RenderFeed,TeamId} from './types';
import {baseProtected,outpostHolder} from './types';
import {feedAlpha,robotWorld,screenFit,toWorld} from './world';
import {mechanismProgress,type MechanismKind} from './mechanismProgress';
import {LED_COLORS} from './teamMaterials';

const quad=new THREE.PlaneGeometry(1,1),anchor=new THREE.Vector3();
const PLATE_W=1.12,PLATE_H=.16,ASPECT=(PLATE_W/PLATE_H).toFixed(3),LABEL_H=.13;
const TINT={red:new THREE.Color('#f4b3a6'),blue:new THREE.Color('#b4dcf6')},WHITE=new THREE.Color('#ffffff'),DEAD=new THREE.Color('#7d8a93');
const FONT='"SF Pro Display","PingFang SC","Microsoft YaHei",system-ui,sans-serif';

function textTexture(text:string,{weight=760,size=84,italic=false,fill='#fff',stroke='rgba(7,12,17,.82)',width=14,pad=40}:{weight?:number;size?:number;italic?:boolean;fill?:string;stroke?:string;width?:number;pad?:number}={}){
  const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d')!,font=`${italic?'italic ':''}${weight} ${size}px ${FONT}`;
  ctx.font=font;canvas.width=Math.ceil(ctx.measureText(text).width)+pad;canvas.height=Math.ceil(size*1.34);
  ctx.font=font;ctx.textAlign='center';ctx.textBaseline='middle';ctx.lineJoin='round';
  if(width){ctx.lineWidth=width;ctx.strokeStyle=stroke;ctx.strokeText(text,canvas.width/2,canvas.height*.52);}
  ctx.fillStyle=fill;ctx.fillText(text,canvas.width/2,canvas.height*.52);
  const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;texture.anisotropy=4;
  return {texture,aspect:canvas.width/canvas.height,canvas};
}
const labelMaterial=(texture:THREE.Texture,team:TeamId)=>new THREE.MeshBasicMaterial({map:texture,color:TINT[team],transparent:true,depthTest:false,depthWrite:false,toneMapped:false,fog:false});
const overlayMaterial=(texture?:THREE.Texture)=>new THREE.MeshBasicMaterial({...(texture?{map:texture}:{}),transparent:true,depthTest:false,depthWrite:false,toneMapped:false,fog:false});

const barVertex='varying vec2 vUv;void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}';
// Broadcast robot plate: [number box][segmented health][rank chevrons], after the official overlay.
const plateFragment=`uniform vec3 uColor;uniform float uHp,uTrail,uSegments,uFlash,uRespawn,uDead,uFocus,uTime,uLevel;varying vec2 vUv;
float chevron(vec2 q,float y0){float d=abs(q.x-.5);float yc=y0+.2*(1.-d/.34);return step(d,.34)*(1.-smoothstep(.055,.085,abs(q.y-yc)));}
void main(){
  float A=${ASPECT};vec2 p=vUv*vec2(A,1.);float e=.07;
  vec3 c=vec3(.035,.05,.065);float a=.86;
  bool edge=p.x<e||p.y<e||p.x>A-e||p.y>1.-e;
  if(p.x<1.){c=uDead>.5?vec3(.12,.13,.14):vec3(.07,.09,.11);if(p.x>1.-e*.6)c=vec3(.2,.24,.27);}
  else if(p.x>A-1.){vec2 q=vec2(p.x-(A-1.),p.y);float n=uLevel>=10.?3.:ceil(uLevel/3.);float g=0.;for(int i=0;i<3;i++){if(float(i)<n)g=max(g,chevron(q,.16+float(i)*.22));}
    c=mix(vec3(.06,.07,.08),uLevel>=10.?vec3(1.,.86,.42):vec3(.95,.72,.3),g);}
  else{float x=(p.x-1.-e)/(A-2.-2.*e),y=(p.y-e*2.)/(1.-e*4.);
    if(y<0.||y>1.)c=vec3(.03,.04,.05);
    else{c=vec3(.1,.12,.14);
      if(uDead>.5){if(x<uRespawn)c=mix(vec3(.4,.34,.22),vec3(.8,.66,.42),y);}
      else{if(x<uTrail)c=vec3(1.,.93,.8);if(x<uHp){c=uColor*(.72+.45*y);if(uHp<.3)c*=.8+.3*sin(uTime*10.);c=mix(c,vec3(1.),uFlash*.75);}}
      float s=x*uSegments,d=abs(fract(s+.5)-.5)/uSegments*(A-2.);if(s>.5&&s<uSegments-.5)c*=mix(.18,1.,smoothstep(.03,.03+fwidth(p.x)*1.5,d));}}
  if(edge)c=mix(vec3(.2,.25,.29),vec3(1.,.83,.48),uFocus);
  gl_FragColor=vec4(c,a);
}`;
const structureFragment=`uniform vec3 uColor;uniform float uHp,uTrail,uFlash,uTime,uAspect;varying vec2 vUv;
void main(){vec2 p=vUv*vec2(uAspect,1.);float e=.12;
  if(p.x<e||p.y<e||p.x>uAspect-e||p.y>1.-e){gl_FragColor=vec4(.02,.03,.04,.9);return;}
  float x=(p.x-e)/(uAspect-2.*e),y=(p.y-e)/(1.-2.*e);vec3 c=vec3(.13,.03,.035);if(uColor.b>uColor.r)c=vec3(.02,.06,.12);
  if(x<uTrail)c=vec3(1.,.92,.78);if(x<uHp){c=uColor*(.7+.5*y);c=mix(c,vec3(1.),uFlash*.7);}
  c*=.9+.1*step(.5,fract(p.x*7.));gl_FragColor=vec4(c,.94);}`;

type BarState={hp:number;trail:number;hold:number;flash:number};
// Gold buff glyphs over a robot plate, as on the broadcast: attack, defence, cooling, invulnerable, weakened.
type Buff='attack'|'defense'|'cooling'|'invulnerable'|'weak';
function drawBuffs(ctx:CanvasRenderingContext2D,buffs:Buff[]){
  ctx.clearRect(0,0,320,64);buffs.forEach((b,i)=>{const x=i*64+32,y=32;ctx.save();ctx.translate(x,y);ctx.lineWidth=5;ctx.strokeStyle='rgba(5,8,12,.85)';ctx.fillStyle=b==='invulnerable'?'#9ff1ff':b==='weak'?'#ff6a5a':'#ffcf4a';ctx.beginPath();
    if(b==='attack'){ctx.moveTo(-7,20);ctx.lineTo(-7,-6);ctx.quadraticCurveTo(0,-26,7,-6);ctx.lineTo(7,20);ctx.closePath();}
    else if(b==='defense'||b==='invulnerable'){ctx.moveTo(0,-22);ctx.lineTo(18,-14);ctx.quadraticCurveTo(16,12,0,22);ctx.quadraticCurveTo(-16,12,-18,-14);ctx.closePath();}
    else if(b==='cooling'){ctx.rect(-14,-18,9,36);ctx.rect(5,-18,9,36);}
    else{ctx.moveTo(-16,-6);ctx.lineTo(16,-6);ctx.lineTo(0,18);ctx.closePath();ctx.rect(-6,-22,12,16);}
    ctx.stroke();ctx.fill();ctx.restore();});
}
function damp(s:BarState,hp:number,dt:number){if(s.hp<0)s.hp=s.trail=hp;if(hp<s.hp-.001){s.hold=.45;s.flash=1;}s.hp=hp;if(s.trail<=hp)s.trail=hp;else if((s.hold-=dt)<=0)s.trail=THREE.MathUtils.damp(s.trail,hp,7,dt);s.flash=Math.max(0,s.flash-dt*6);}

export function RobotHud({id,team,feed,focus,onSelect}:{id:string;team:TeamId;feed:MutableRefObject<RenderFeed>;focus:boolean;onSelect:(id:string)=>void}){
  const root=useRef<THREE.Group>(null),state=useRef<BarState>({hp:-1,trail:1,hold:0,flash:0}),ammoRef=useRef<THREE.Mesh>(null),buffRef=useRef<THREE.Mesh>(null),shown=useRef({text:'',at:0,buffs:''});
  const buffs=useMemo(()=>{const canvas=document.createElement('canvas');canvas.width=320;canvas.height=64;const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;return {canvas,texture,material:overlayMaterial(texture)};},[]);
  const digit=useMemo(()=>textTexture(id.split('-')[1],{weight:900,size:96,italic:true,width:0,pad:16}),[id]);
  const digitMaterial=useMemo(()=>overlayMaterial(digit.texture),[digit]);
  const ammo=useMemo(()=>{const canvas=document.createElement('canvas');canvas.width=256;canvas.height=64;const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;return {canvas,texture,material:overlayMaterial(texture)};},[]);
  const plate=useMemo(()=>new THREE.ShaderMaterial({vertexShader:barVertex,fragmentShader:plateFragment,transparent:true,depthTest:false,depthWrite:false,
    uniforms:{uColor:{value:new THREE.Color(LED_COLORS[team]).convertLinearToSRGB()},uHp:{value:1},uTrail:{value:1},uSegments:{value:3},uFlash:{value:0},uRespawn:{value:0},uDead:{value:0},uFocus:{value:0},uTime:{value:0},uLevel:{value:1}}}),[team]);
  useEffect(()=>()=>{digit.texture.dispose();digitMaterial.dispose();ammo.texture.dispose();ammo.material.dispose();buffs.texture.dispose();buffs.material.dispose();plate.dispose();},[digit,digitMaterial,ammo,buffs,plate]);
  useFrame(({camera,size,clock},dt)=>{
    const f=feed.current.frame,r=f?.robots.find(r=>r.id===id),g=root.current;if(!g)return;g.visible=!!r;if(!r)return;
    robotWorld(feed.current,r,feedAlpha(feed.current),g.position).y+=r.role==='aerial'?.62:1.0;
    g.quaternion.copy(camera.quaternion);g.scale.setScalar(screenFit(g.position,camera,size,PLATE_W,.075,.15));
    const s=state.current,hasHp=r.max_hp>0,hp=hasHp?THREE.MathUtils.clamp(r.hp/r.max_hp,0,1):r.support_active?1:0;damp(s,hp,dt);
    const u=plate.uniforms;u.uHp.value=s.hp;u.uTrail.value=s.trail;u.uFlash.value=s.flash;u.uSegments.value=hasHp?Math.max(1,Math.round(r.max_hp/50)):1;
    u.uDead.value=r.alive||!hasHp?0:1;u.uRespawn.value=r.respawn_required>0?Math.min(1,r.respawn_progress/r.respawn_required):0;u.uFocus.value=focus?1:0;u.uTime.value=clock.elapsedTime;u.uLevel.value=r.level||1;
    digitMaterial.color.copy(r.alive||!hasHp?WHITE:DEAD);
    const text=r.role==='engineer'?(r.carried_units?`◆ ${r.carried_units}`:''):r.role==='heavy'&&r.launcher!=='fitted'&&r.launcher!=='installed'?(r.carried_units?`◆ ${r.carried_units}`:r.launcher==='installing'?`装配 ${Math.round((r.launcher_progress||0)*100)}%`:''):r.drones?`✈ ${r.drones.filter(d=>d.state==='flying').length}/${r.drones.filter(d=>d.state!=='disabled').length}`:`≡ ${r.ammo}`,now=clock.elapsedTime;
    if(text!==shown.current.text&&now-shown.current.at>.25){shown.current={...shown.current,text,at:now};const ctx=ammo.canvas.getContext('2d')!;ctx.clearRect(0,0,256,64);if(text){ctx.font=`700 40px ${FONT}`;ctx.textBaseline='middle';ctx.lineJoin='round';ctx.lineWidth=8;ctx.strokeStyle='rgba(5,9,13,.85)';ctx.strokeText(text,10,34);ctx.fillStyle='#d3dde4';ctx.fillText(text,10,34);}ammo.texture.needsUpdate=true;}
    if(ammoRef.current)ammoRef.current.visible=!!shown.current.text;
    const x=r as typeof r&{attack_multiplier?:number;defense_buff?:number;crossing_defense?:number;cooling_multiplier?:number};
    const list:Buff[]=r.alive?[...((x.attack_multiplier??1)>1?['attack' as const]:[]),...((x.defense_buff??0)>0||(x.crossing_defense??0)>0?['defense' as const]:[]),...((x.cooling_multiplier??1)>1?['cooling' as const]:[]),...(r.invulnerable?['invulnerable' as const]:[]),...(r.weak?['weak' as const]:[])]:[];
    const key=list.join();if(key!==shown.current.buffs){shown.current.buffs=key;drawBuffs(buffs.canvas.getContext('2d')!,list);buffs.texture.needsUpdate=true;}
    if(buffRef.current)buffRef.current.visible=list.length>0;
  });
  const numberH=PLATE_H*.86;
  return <group ref={root} onClick={e=>{e.stopPropagation();onSelect(id);}}>
    <mesh geometry={quad} material={plate} position={[0,PLATE_H/2,0]} scale={[PLATE_W,PLATE_H,1]} renderOrder={30}/>
    <mesh geometry={quad} material={digitMaterial} position={[-PLATE_W/2+PLATE_H/2,PLATE_H/2,0]} scale={[numberH*digit.aspect,numberH,1]} renderOrder={31}/>
    <mesh ref={ammoRef} geometry={quad} material={ammo.material} position={[-PLATE_W/2+PLATE_H*1.15+.32,-LABEL_H*.62,0]} scale={[LABEL_H*4,LABEL_H,1]} renderOrder={31}/>
    <mesh ref={buffRef} geometry={quad} material={buffs.material} position={[-PLATE_W/2+PLATE_H*1.1+.36,PLATE_H+LABEL_H*.68,0]} scale={[LABEL_H*5,LABEL_H,1]} renderOrder={31} visible={false}/>
  </group>;
}

// Floating structure plate: "前哨站 OUTPOST" / "基地 BASE" with a wide health bar, as on the broadcast.
// A 2027 outpost rebuilt by the other team takes that team's colour and says who holds it.
export function StructureHud({team,kind,feed}:{team:TeamId;kind:'base'|'outpost';feed:MutableRefObject<RenderFeed>}){
  const root=useRef<THREE.Group>(null),state=useRef<BarState>({hp:-1,trail:1,hold:0,flash:0}),shieldRef=useRef<THREE.Mesh>(null),labelRef=useRef<THREE.Mesh>(null),holder=useRef<TeamId>(team);
  const labels=useMemo(()=>{const style={weight:700,size:72,width:12};return {own:textTexture(kind==='base'?'基地 BASE':'前哨站 OUTPOST',style),
    red:textTexture('前哨站 · 红方占领',style),blue:textTexture('前哨站 · 蓝方占领',style)};},[kind]);
  const shield=useMemo(()=>textTexture('⛨',{weight:700,size:72,width:10,pad:12}),[]);
  const materials=useMemo(()=>({label:labelMaterial(labels.own.texture,team),shield:overlayMaterial(shield.texture),bar:new THREE.ShaderMaterial({vertexShader:barVertex,fragmentShader:structureFragment,transparent:true,depthTest:false,depthWrite:false,
    uniforms:{uColor:{value:new THREE.Color(LED_COLORS[team]).convertLinearToSRGB()},uHp:{value:1},uTrail:{value:1},uFlash:{value:0},uTime:{value:0},uAspect:{value:9}}})}),[labels,shield,team]);
  useEffect(()=>()=>{Object.values(labels).forEach(l=>l.texture.dispose());shield.texture.dispose();Object.values(materials).forEach(m=>m.dispose());},[labels,shield,materials]);
  useEffect(()=>{holder.current=team;},[team,materials]);
  const h=.16,w=h*9,lh=.15;
  useFrame(({camera,size,clock},dt)=>{
    const f=feed.current.frame,g=root.current,s=(kind==='base'?f?.bases:f?.outposts)?.[team];if(!f||!g||!s)return;
    toWorld(f.arena,s.x,s.y,(s.z||0)+(kind==='base'?1.75:1.85),g.position);g.quaternion.copy(camera.quaternion);g.scale.setScalar(screenFit(g.position,camera,size,1.5,.13,.24));
    damp(state.current,THREE.MathUtils.clamp(s.hp/s.max_hp,0,1),dt);const u=materials.bar.uniforms;u.uHp.value=state.current.hp;u.uTrail.value=state.current.trail;u.uFlash.value=state.current.flash;u.uTime.value=clock.elapsedTime;
    const held=kind==='outpost'?outpostHolder(f,team):team;
    if(held!==holder.current){
      holder.current=held;const label=held===team?labels.own:labels[held];
      u.uColor.value.set(LED_COLORS[held]).convertLinearToSRGB();materials.label.color.copy(TINT[held]);materials.label.map=label.texture;materials.label.needsUpdate=true;
      labelRef.current?.scale.set(lh*label.aspect,lh,1);
    }
    if(shieldRef.current)shieldRef.current.visible=kind==='base'&&s.hp>0&&baseProtected(f,team);
    materials.label.opacity=s.hp>0||kind==='outpost'?1:.6;
  });
  return <group ref={root}>
    <mesh geometry={quad} material={materials.bar} position={[0,h/2,0]} scale={[w,h,1]} renderOrder={28}/>
    <mesh ref={labelRef} geometry={quad} material={materials.label} position={[0,h+.03+lh/2,0]} scale={[lh*labels.own.aspect,lh,1]} renderOrder={29}/>
    <mesh ref={shieldRef} geometry={quad} material={materials.shield} position={[lh*labels.own.aspect/2+lh*.55,h+.03+lh/2,0]} scale={[lh*shield.aspect,lh,1]} renderOrder={29}/>
  </group>;
}

// Pooled "-20" damage numbers and "LEVEL UP" call-outs that rise from whatever was hit.
type Floater={mesh:THREE.Mesh;material:THREE.MeshBasicMaterial;age:number;life:number;origin:THREE.Vector3;drift:number;size:number;rise:number;active:boolean};
const FLOATERS=48;
export function CombatText({feed}:{feed:MutableRefObject<RenderFeed>}){
  const group=useRef<THREE.Group>(null),seen=useRef(new Set<string>()),generation=useRef(''),stack=useRef(new Map<string,{at:number;n:number}>());
  const textures=useMemo(()=>new Map<string,{texture:THREE.Texture;aspect:number}>(),[]);
  const pool=useMemo<Floater[]>(()=>Array.from({length:FLOATERS},()=>{const material=overlayMaterial();const mesh=new THREE.Mesh(quad,material);mesh.visible=false;mesh.renderOrder=40;return {mesh,material,age:0,life:1,origin:new THREE.Vector3(),drift:0,size:.3,rise:.6,active:false};}),[]);
  useEffect(()=>{const g=group.current;pool.forEach(p=>g?.add(p.mesh));return()=>{pool.forEach(p=>{p.material.dispose();g?.remove(p.mesh);});textures.forEach(t=>t.texture.dispose());};},[pool,textures]);
  const texture=(text:string,style:'damage'|'level')=>{const key=style+text;let t=textures.get(key);if(!t){t=style==='damage'?textTexture(text,{weight:900,size:88,italic:true,fill:'#ff4b42',stroke:'rgba(255,240,235,.92)',width:9,pad:24}):textTexture(text,{weight:900,size:80,italic:true,fill:'#ffd56a',stroke:'rgba(40,24,6,.9)',width:12});textures.set(key,t);if(textures.size>96){const first=textures.keys().next().value!;textures.get(first)!.texture.dispose();textures.delete(first);}}return t;};
  const spawn=(text:string,style:'damage'|'level',at:THREE.Vector3,key:string)=>{
    const slot=pool.find(p=>!p.active)||pool.reduce((a,b)=>a.age/a.life>b.age/b.life?a:b),t=texture(text,style),now=performance.now(),s=stack.current.get(key);
    const n=s&&now-s.at<450?(s.n+1)%3:0;stack.current.set(key,{at:now,n});
    slot.material.map=t.texture;slot.material.needsUpdate=true;slot.mesh.userData.aspect=t.aspect;
    Object.assign(slot,{age:0,life:style==='level'?1.5:.95,drift:(Math.random()-.5)*.24,size:style==='level'?.34:.28,rise:style==='level'?.5:.55,active:true});slot.origin.copy(at).y+=n*.16;
  };
  useFrame(({camera,size},delta)=>{
    const current=feed.current,f=current.frame;if(!f)return;const dt=Math.min(delta,.05);
    if(generation.current!==current.generation){generation.current=current.generation;seen.current.clear();pool.forEach(p=>{p.active=false;p.mesh.visible=false;});}
    const alpha=feedAlpha(current),p=new THREE.Vector3();
    for(const e of current.events){
      const key=e.id||`${e.tick}:${e.type}:${e.robot}:${e.x}`;if(seen.current.has(key))continue;seen.current.add(key);
      if((e.type==='hit'||e.type==='level_up')&&e.robot){const r=f.robots.find(r=>r.id===e.robot);if(!r)continue;robotWorld(current,r,alpha,p).y+=r.role==='aerial'?.95:1.36;spawn(e.type==='hit'?`-${Math.round(e.damage||0)}`:'LEVEL UP',e.type==='hit'?'damage':'level',p,e.robot);}
      else if((e.type==='base_hit'||e.type==='outpost_hit')&&e.target_team){const s=(e.type==='base_hit'?f.bases:f.outposts)?.[e.target_team];if(!s)continue;toWorld(f.arena,s.x,s.y,(s.z||0)+(e.type==='base_hit'?2.35:2.45),p);spawn(`-${Math.round(e.damage||0)}`,'damage',p,e.type+e.target_team);}
    }
    if(seen.current.size>6000)seen.current.clear();
    for(const item of pool){if(!item.active)continue;item.age+=dt;const t=item.age/item.life;if(t>=1){item.active=false;item.mesh.visible=false;continue;}
      const rise=1-Math.pow(1-t,3),pop=t<.12?1.35-t/.12*.35:1;item.mesh.visible=true;item.mesh.position.copy(item.origin).add(p.set(item.drift*t,item.rise*rise,0));item.mesh.quaternion.copy(camera.quaternion);
      const s=screenFit(item.mesh.position,camera,size,item.size,.018,.05)*item.size*pop;item.mesh.scale.set(s*(item.mesh.userData.aspect||2),s,1);item.material.opacity=t<.6?1:1-(t-.6)/.4;}
  });
  return <group ref={group}/>;
}

// Live activation board above the rune: ring total, hits and the remaining window for each side that is activating.
export function RuneBoard({feed}:{feed:MutableRefObject<RenderFeed>}){
  const group=useRef<THREE.Group>(null),root=useRef<HTMLDivElement>(null),cells=useRef<Record<string,HTMLElement|null>>({});
  useFrame(()=>{const f=feed.current.frame,rune=f?.arena.rune,node=root.current;if(!f||!rune||!node||!group.current)return;
    group.current.position.set(rune.x-f.arena.width/2,rune.z+1.25,rune.y-f.arena.height/2);
    const active=(['red','blue'] as const).filter(t=>f.runes?.[t]?.status==='activating');node.style.display=active.length?'flex':'none';if(!active.length)return;
    for(const team of ['red','blue'] as const){const s=f.runes[team],on=s?.status==='activating',el=cells.current[team];if(!el)continue;el.style.display=on?'flex':'none';if(!on)continue;
      el.querySelector('b')!.textContent=`${Math.round(s.ring_sum||0)}环`;el.querySelector('small')!.textContent=`${s.hit_count||0}臂`;el.querySelector('i')!.textContent=`${Math.max(0,Math.ceil((s.hit_deadline||0)-f.time))}s`;}
  });
  return <group ref={group}><Html zIndexRange={[3,1]} center style={{pointerEvents:'none'}}><div ref={root} className="rune-board" style={{display:'none'}}>
    {(['red','blue'] as const).map(team=><div key={team} className={`rune-board-side ${team}`} ref={e=>{cells.current[team]=e;}}><b/><small/><i/></div>)}
  </div></Html></group>;
}

// One-shot activation emblem over the rune, with the average ring score for the large rune.
export function RuneBurst({feed}:{feed:MutableRefObject<RenderFeed>}){
  const group=useRef<THREE.Group>(null),seen=useRef(new Set<string>()),generation=useRef(''),[bursts,setBursts]=useState<{key:string;team:TeamId;large:boolean;rings:number|null}[]>([]);
  useFrame(()=>{const f=feed.current.frame,rune=f?.arena.rune;if(!f||!rune||!group.current)return;group.current.position.set(rune.x-f.arena.width/2,rune.z,rune.y-f.arena.height/2);
    if(generation.current!==feed.current.generation){generation.current=feed.current.generation;seen.current.clear();}
    for(const e of feed.current.events){if(e.type!=='rune_activated'||!e.team)continue;const key=e.id||`${e.tick}:${e.team}`;if(seen.current.has(key))continue;seen.current.add(key);
      const large=(e as MatchEvent&{mode?:string}).mode==='large',old=feed.current.previous?.runes?.[e.team],count=old?.hit_count||f.runes?.[e.team]?.hit_count||0,sum=old?.ring_sum||f.runes?.[e.team]?.ring_sum||0;
      const burst={key,team:e.team,large,rings:large&&count?sum/count:null};setBursts(list=>[...list.slice(-1),burst]);window.setTimeout(()=>setBursts(list=>list.filter(b=>b.key!==key)),3200);}
  });
  return <group ref={group}>{bursts.map(b=><Html key={b.key} zIndexRange={[3,1]} center style={{pointerEvents:'none'}}><div className={`rune-burst ${b.team}`}>
    <svg viewBox="-100 -100 200 200" aria-hidden><g>{[0,1,2,3,4].map(i=><g key={i} transform={`rotate(${i*72})`}><path d="M-13 -24 L-17 -86 L17 -86 L13 -24 Z" className="arm"/><rect x="-12" y="-80" width="24" height="16" rx="3" className="lamp"/></g>)}<circle r="24" className="hub"/><circle r="11" className="core"/></g></svg>
    {b.rings!==null&&<b>{b.rings.toFixed(1)}</b>}<span>{b.team==='red'?'红方':'蓝方'}激活{b.large?'大':'小'}能量机关！</span>
  </div></Html>)}</group>;
}

// Camera-facing text for structures; the parent group must stay unrotated.
export function PickupHud({id,feed}:{id:string;feed:MutableRefObject<RenderFeed>}){
  const root=useRef<HTMLDivElement>(null),text=useRef<HTMLSpanElement>(null),bar=useRef<HTMLElement>(null);
  useFrame(()=>{const r=feed.current.frame?.robots.find(r=>r.id===id),s=r?.unit_pickup;if(!root.current)return;
    root.current.style.display=s?'block':'none';if(!s)return;
    const names:Record<string,string>={approaching:'对准能量单元',gripping:'夹爪闭合',lifting:'夹取抬升',stowing:'收臂入仓'};
    if(text.current)text.current.textContent=`${names[s.stage]||s.stage} · ${s.elapsed.toFixed(1)}s`;
    if(bar.current)bar.current.style.transform=`scaleX(${s.progress})`;
  });
  return <Html zIndexRange={[3,1]} center position={[0,1.5,0]} style={{pointerEvents:'none'}}><div ref={root} className="mechanism-hud" data-mechanism={id+'-pickup'} style={{display:'none'}}>
    <span ref={text}/><div className="mechanism-progress-track"><i ref={bar}/></div>
  </div></Html>;
}

export function Label({text,team,position}:{text:string;team:TeamId;position:[number,number,number]}){
  const mesh=useRef<THREE.Mesh>(null),tag=useMemo(()=>textTexture(text),[text]),material=useMemo(()=>labelMaterial(tag.texture,team),[tag,team]);
  useEffect(()=>()=>{tag.texture.dispose();material.dispose();},[tag,material]);
  useFrame(({camera,size})=>{const m=mesh.current;if(!m)return;m.quaternion.copy(camera.quaternion);const s=screenFit(m.getWorldPosition(anchor),camera,size,.3,.02,.042);m.scale.set(.3*tag.aspect*s,.3*s,1);});
  return <mesh ref={mesh} geometry={quad} material={material} position={position} renderOrder={29}/>;
}

export function MechanismHud({team,kind,feed}:{team:TeamId;kind:MechanismKind;feed:MutableRefObject<RenderFeed>}){
  const group=useRef<THREE.Group>(null),root=useRef<HTMLDivElement>(null),label=useRef<HTMLSpanElement>(null),detail=useRef<HTMLElement>(null),value=useRef<HTMLElement>(null),bar=useRef<HTMLElement>(null),track=useRef<HTMLDivElement>(null);
  useFrame(()=>{
    const f=feed.current.frame,g=group.current,node=root.current;if(!f||!g||!node)return;
    const display=mechanismProgress(f,team,kind);node.style.display=display?'block':'none';if(!display)return;
    if(kind==='outpost'){
      const p=f.outposts[team];g.position.set(p.x-f.arena.width/2,(p.z||0)+2.6,p.y-f.arena.height/2);
    }else{
      const p=f.arena.assembly_frames?.[team];if(!p){node.style.display='none';return;}
      g.position.set(p.origin[0]-f.arena.width/2,(p.z0_m||0)+1.8,p.origin[1]-f.arena.height/2);
    }
    if(label.current)label.current.textContent=display.label;
    if(detail.current)detail.current.textContent=display.detail;
    if(value.current)value.current.textContent=`${Math.round(display.progress*100)}%`;
    if(bar.current)bar.current.style.transform=`scaleX(${display.progress})`;
    track.current?.setAttribute('aria-valuenow',String(Math.round(display.progress*100)));
  });
  return <group ref={group}><Html zIndexRange={[3,1]} center style={{pointerEvents:'none'}}><div ref={root} className={`mechanism-hud ${kind} ${team}`} data-mechanism={`${team}-${kind}`} style={{display:'none'}}>
    <div>{kind==='outpost'&&<span ref={label}/>}<b ref={value}/></div>
    <div ref={track} className="mechanism-progress-track" role="progressbar" aria-label={kind==='outpost'?'前哨站重建进度':'工程兑矿进度'} aria-valuemin={0} aria-valuemax={100}><i ref={bar}/></div>
    {kind==='outpost'&&<small ref={detail}/>}
  </div></Html></group>;
}

