import {useEffect,useMemo,useRef,type MutableRefObject} from 'react';
import {useFrame} from '@react-three/fiber';
import * as THREE from 'three';
import type {Frame,MatchEvent,Projectile,RenderFeed,TeamId} from './types';
import {terrainHeight} from './terrain';
import {feedAlpha,robotWorld,toWorld} from './world';

// Last trigger time per key (robot id, `base-red`, `outpost-blue`, `shot:red-3`) so models can flash armour lights and recoil.
export const pulses=new Map<string,number>();
export const pulse=(key:string,span=.22)=>{const t=pulses.get(key);return t===undefined?0:Math.max(0,1-(performance.now()-t)/(span*1000));};

type RGB=[number,number,number];
const rgb=(hex:string):RGB=>{const c=new THREE.Color(hex).convertLinearToSRGB();return [c.r,c.g,c.b];};
const HOT=rgb('#fff5dc'),FLAME=rgb('#ffb04a'),EMBER=rgb('#ff5420'),SMOKE=rgb('#3e3b38'),ASH=rgb('#7c7873'),DUST=rgb('#a39683'),STEAM=rgb('#e2ebee'),GOLD=rgb('#ffd27a'),HEAL=rgb('#7dffa8');
const GLOW:Record<TeamId,RGB>={red:rgb('#ff6b4f'),blue:rgb('#4fb4ff')};
const BALL=rgb('#66ee55');
const rand=(a:number,b:number)=>a+Math.random()*(b-a);
const randomDir=(out=new THREE.Vector3(),up=0)=>{const u=Math.random()*2-1,a=Math.random()*Math.PI*2,s=Math.sqrt(1-u*u);out.set(s*Math.cos(a),u,s*Math.sin(a));if(up)out.y=Math.abs(out.y)*up+out.y*(1-up);return out.normalize();};
const cone=(axis:THREE.Vector3,spread:number)=>randomDir().multiplyScalar(spread).add(axis).normalize();
const aim=(yaw:number,pitch:number,out=new THREE.Vector3())=>out.set(Math.cos(yaw)*Math.cos(pitch),Math.sin(pitch),Math.sin(yaw)*Math.cos(pitch));
const UP=new THREE.Vector3(0,1,0);

type Sprite={p:THREE.Vector3;v:THREE.Vector3;age:number;life:number;s0:number;s1:number;c0:RGB;c1:RGB;a:number;drag:number;g:number;seed:number;fadeIn:number};
type Spark={p:THREE.Vector3;v:THREE.Vector3;age:number;life:number;w:number;tail:number;c0:RGB;c1:RGB;a:number;drag:number;g:number;floor:number};
type Chunk={p:THREE.Vector3;v:THREE.Vector3;r:THREE.Euler;w:THREE.Vector3;age:number;life:number;s:number;c:THREE.Color};
type Ring={p:THREE.Vector3;age:number;life:number;r0:number;r1:number;c:THREE.Color;a:number;delay:number};
type Flash={p:THREE.Vector3;c:THREE.Color;i:number;age:number;life:number;range:number};

class SpritePool{
  items:Sprite[]=[];geometry=new THREE.BufferGeometry();n=0;
  private position:Float32Array;private color:Float32Array;private size:Float32Array;private alpha:Float32Array;private seed:Float32Array;
  constructor(readonly capacity:number,transient:number){
    const total=capacity+transient;this.position=new Float32Array(total*3);this.color=new Float32Array(total*3);this.size=new Float32Array(total);this.alpha=new Float32Array(total);this.seed=new Float32Array(total);
    for(const [name,array,width] of [['position',this.position,3],['aColor',this.color,3],['aSize',this.size,1],['aAlpha',this.alpha,1],['aSeed',this.seed,1]] as const)this.geometry.setAttribute(name,new THREE.BufferAttribute(array,width).setUsage(THREE.DynamicDrawUsage));
    this.geometry.setDrawRange(0,0);
  }
  add(s:Partial<Sprite>&{p:THREE.Vector3}){
    if(this.items.length>=this.capacity)this.items.splice(0,this.items.length-this.capacity+1);
    this.items.push({v:new THREE.Vector3(),age:0,life:.5,s0:.2,s1:.2,c0:HOT,c1:HOT,a:1,drag:0,g:0,seed:Math.random(),fadeIn:0,...s});
  }
  write(p:THREE.Vector3,size:number,c0:RGB,c1:RGB,t:number,alpha:number,seed=0){
    if(this.n>=this.size.length)return;const i=this.n++;
    this.position[i*3]=p.x;this.position[i*3+1]=p.y;this.position[i*3+2]=p.z;
    for(let k=0;k<3;k++)this.color[i*3+k]=c0[k]+(c1[k]-c0[k])*t;
    this.size[i]=size;this.alpha[i]=alpha;this.seed[i]=seed;
  }
  step(dt:number){
    let j=0;
    for(const s of this.items){
      if((s.age+=dt)>=s.life)continue;
      s.v.multiplyScalar(Math.exp(-s.drag*dt));s.v.y-=s.g*dt;s.p.addScaledVector(s.v,dt);
      const t=s.age/s.life,grow=1-(1-t)*(1-t),fade=(s.fadeIn>0?Math.min(1,t/s.fadeIn):1)*Math.pow(1-t,1.3);
      this.write(s.p,s.s0+(s.s1-s.s0)*grow,s.c0,s.c1,t,s.a*fade,s.seed);this.items[j++]=s;
    }
    this.items.length=j;
  }
  commit(){this.geometry.setDrawRange(0,this.n);for(const a of Object.values(this.geometry.attributes))(a as THREE.BufferAttribute).needsUpdate=true;this.n=0;}
}

class SparkPool{
  items:Spark[]=[];geometry=new THREE.InstancedBufferGeometry();n=0;
  private start:Float32Array;private end:Float32Array;private color:Float32Array;private width:Float32Array;
  constructor(readonly capacity:number,transient:number){
    const total=capacity+transient;this.start=new Float32Array(total*3);this.end=new Float32Array(total*3);this.color=new Float32Array(total*4);this.width=new Float32Array(total);
    this.geometry.setAttribute('position',new THREE.BufferAttribute(new Float32Array([0,-1,0,0,1,0,1,-1,0,1,1,0]),3));this.geometry.setIndex([0,2,1,2,3,1]);
    for(const [name,array,width] of [['aStart',this.start,3],['aEnd',this.end,3],['aColor',this.color,4],['aWidth',this.width,1]] as const)this.geometry.setAttribute(name,new THREE.InstancedBufferAttribute(array,width).setUsage(THREE.DynamicDrawUsage));
    this.geometry.instanceCount=0;
  }
  add(s:Partial<Spark>&{p:THREE.Vector3;v:THREE.Vector3}){
    if(this.items.length>=this.capacity)this.items.splice(0,this.items.length-this.capacity+1);
    this.items.push({age:0,life:.3,w:.014,tail:.03,c0:HOT,c1:EMBER,a:1,drag:1.5,g:9.8,floor:-Infinity,...s});
  }
  write(from:THREE.Vector3,to:THREE.Vector3,width:number,c:RGB,alpha:number){
    if(this.n>=this.width.length)return;const i=this.n++;
    this.start[i*3]=from.x;this.start[i*3+1]=from.y;this.start[i*3+2]=from.z;this.end[i*3]=to.x;this.end[i*3+1]=to.y;this.end[i*3+2]=to.z;
    this.color[i*4]=c[0];this.color[i*4+1]=c[1];this.color[i*4+2]=c[2];this.color[i*4+3]=alpha;this.width[i]=width;
  }
  step(dt:number){
    let j=0;const tail=new THREE.Vector3(),c:RGB=[0,0,0];
    for(const s of this.items){
      if((s.age+=dt)>=s.life)continue;
      s.v.multiplyScalar(Math.exp(-s.drag*dt));s.v.y-=s.g*dt;s.p.addScaledVector(s.v,dt);
      if(s.p.y<s.floor){s.p.y=s.floor;if(s.v.y<0){s.v.y*=-.35;s.v.x*=.6;s.v.z*=.6;}}
      const t=s.age/s.life;for(let k=0;k<3;k++)c[k]=s.c0[k]+(s.c1[k]-s.c0[k])*Math.min(1,t*1.6);
      tail.copy(s.p).addScaledVector(s.v,-s.tail);this.write(tail,s.p,s.w,c,s.a*(1-t*t));this.items[j++]=s;
    }
    this.items.length=j;
  }
  commit(){this.geometry.instanceCount=this.n;for(const name of ['aStart','aEnd','aColor','aWidth'])(this.geometry.attributes[name] as THREE.BufferAttribute).needsUpdate=true;this.n=0;}
}

const spriteVertex=`attribute float aSize;attribute float aAlpha;attribute vec3 aColor;attribute float aSeed;uniform float uScale;varying vec3 vColor;varying float vAlpha;varying float vSeed;
void main(){vec4 mv=modelViewMatrix*vec4(position,1.);gl_Position=projectionMatrix*mv;gl_PointSize=min(aSize*uScale/max(.05,-mv.z),480.);vColor=aColor;vAlpha=aAlpha;vSeed=aSeed;}`;
const glowFragment=`varying vec3 vColor;varying float vAlpha;
void main(){vec2 c=gl_PointCoord*2.-1.;float r=dot(c,c);if(r>1.)discard;float g=exp(-r*5.)+.35*exp(-r*1.4)*(1.-r);gl_FragColor=vec4(mix(vColor,vec3(1.),exp(-r*16.)*.6)*g*vAlpha,1.);}`;
const smokeFragment=`varying vec3 vColor;varying float vAlpha;varying float vSeed;
void main(){vec2 c=gl_PointCoord*2.-1.;float r=length(c);if(r>1.)discard;float a=atan(c.y,c.x),edge=.66+.12*sin(a*3.+vSeed*17.)+.08*sin(a*5.-vSeed*29.);
float m=1.-smoothstep(edge*.35,edge,r);gl_FragColor=vec4(vColor*(.78+.36*(1.-gl_PointCoord.y)),m*vAlpha);}`;
const sparkVertex=`attribute vec3 aStart;attribute vec3 aEnd;attribute vec4 aColor;attribute float aWidth;uniform float uScale;varying vec2 vCorner;varying vec4 vColor;
void main(){vec3 s=(modelViewMatrix*vec4(aStart,1.)).xyz,e=(modelViewMatrix*vec4(aEnd,1.)).xyz,p=mix(s,e,position.x),d=e-s;float len=length(d);d=len>1e-5?d/len:vec3(0.,1.,0.);
vec3 side=cross(d,normalize(p));float sl=length(side);side=sl>1e-4?side/sl:vec3(1.,0.,0.);float w=max(aWidth,1.6*max(.05,-p.z)/uScale);
p+=side*position.y*w*.5+d*(position.x*2.-1.)*w*.5;gl_Position=projectionMatrix*vec4(p,1.);vCorner=position.xy;vColor=vec4(aColor.rgb,aColor.a*aWidth/w);}`;
const sparkFragment=`varying vec2 vCorner;varying vec4 vColor;
void main(){float across=1.-vCorner.y*vCorner.y,a=across*pow(vCorner.x,1.4)*vColor.a;gl_FragColor=vec4(mix(vColor.rgb,vec3(1.),smoothstep(.55,1.,across)*.55)*a,1.);}`;

function ringTexture(){
  const canvas=document.createElement('canvas');canvas.width=canvas.height=256;const ctx=canvas.getContext('2d')!,g=ctx.createRadialGradient(128,128,0,128,128,128);
  g.addColorStop(0,'rgba(255,255,255,0)');g.addColorStop(.55,'rgba(255,255,255,.05)');g.addColorStop(.86,'rgba(255,255,255,.95)');g.addColorStop(.93,'rgba(255,255,255,.45)');g.addColorStop(1,'rgba(255,255,255,0)');
  ctx.fillStyle=g;ctx.fillRect(0,0,256,256);const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;return texture;
}

const DEBRIS=180,RINGS=32,LIGHTS=3;
const shell=rgb('#2c333a');

class FxWorld{
  glow=new SpritePool(1100,320);smoke=new SpritePool(800,0);sparks=new SparkPool(1000,320);
  debris:Chunk[]=[];rings:Ring[]=[];flashes:Flash[]=[];later:{at:number;run:()=>void}[]=[];emitters=new Map<string,number>();
  arena:Frame['arena']|null=null;time=0;private previous:Frame|null=null;private projectiles=new Map<number,Projectile>();
  private dummy=new THREE.Object3D();private v=new THREE.Vector3();private w=new THREE.Vector3();private robot=new THREE.Vector3();

  clear(){this.glow.items=[];this.smoke.items=[];this.sparks.items=[];this.debris=[];this.rings=[];this.flashes=[];this.later=[];this.emitters.clear();}
  ground(x:number,z:number){const a=this.arena;return a?terrainHeight(a,x+a.width/2,z+a.height/2):0;}
  light(p:THREE.Vector3,color:RGB|string,i:number,life:number,range=8){
    const c=typeof color==='string'?new THREE.Color(color):new THREE.Color().setRGB(...color,THREE.SRGBColorSpace);
    this.flashes.push({p:p.clone(),c,i,age:0,life,range});if(this.flashes.length>8)this.flashes.shift();
  }
  ring(p:THREE.Vector3,r0:number,r1:number,life:number,color:RGB,a=1,delay=0){
    if(this.rings.length>=RINGS)this.rings.shift();
    this.rings.push({p:new THREE.Vector3(p.x,this.ground(p.x,p.z)+.035,p.z),age:-delay,life,r0,r1,c:new THREE.Color().setRGB(...color,THREE.SRGBColorSpace),a,delay});
  }
  chunk(p:THREE.Vector3,v:THREE.Vector3,size:number,color:RGB){
    if(this.debris.length>=DEBRIS)this.debris.shift();
    this.debris.push({p:p.clone(),v,r:new THREE.Euler(rand(0,6),rand(0,6),rand(0,6)),w:randomDir().multiplyScalar(rand(6,16)),age:0,life:rand(2.6,4.2),s:size,c:new THREE.Color().setRGB(...color,THREE.SRGBColorSpace)});
  }

  muzzle(p:THREE.Vector3,dir:THREE.Vector3,heavy:boolean){
    // Friction wheels launch plastic balls: a brief green glint and a faint puff,
    // rather than burning propellant or a second stream of orange "projectiles".
    this.glow.add({p:p.clone(),v:dir.clone().multiplyScalar(.5),life:.04,s0:heavy?.10:.045,s1:.025,c0:BALL,c1:BALL,a:.5});
    if(heavy)this.smoke.add({p:p.clone(),v:dir.clone().multiplyScalar(.25),life:.22,s0:.035,s1:.12,c0:DUST,c1:DUST,a:.06,drag:3,fadeIn:.1});
  }
  ricochet(p:THREE.Vector3){
    const floor=this.ground(p.x,p.z);
    this.glow.add({p:p.clone(),life:.05,s0:.14,s1:.2,c0:HOT,c1:FLAME,a:.65});
    for(let i=0;i<4;i++)this.sparks.add({p:p.clone(),v:randomDir(undefined,.6).multiplyScalar(rand(1.5,4)),life:rand(.12,.28),w:.009,tail:.03,drag:2,floor});
    this.smoke.add({p:p.clone(),v:this.w.set(rand(-.2,.2),rand(.15,.4),rand(-.2,.2)).clone(),life:rand(.4,.6),s0:.06,s1:.32,c0:DUST,c1:DUST,a:.28,drag:2,fadeIn:.1});
  }
  armorHit(p:THREE.Vector3,normal:THREE.Vector3,heavy:boolean,team:TeamId){
    const floor=this.ground(p.x,p.z);
    this.glow.add({p:p.clone(),life:heavy?.16:.1,s0:heavy?.95:.45,s1:heavy?1.35:.62,c0:HOT,c1:FLAME,a:1});
    this.glow.add({p:p.clone(),life:heavy?.3:.2,s0:.3,s1:heavy?1.3:.85,c0:GLOW[team],c1:GLOW[team],a:.55});
    for(let i=0;i<(heavy?24:11);i++)this.sparks.add({p:p.clone(),v:cone(normal,.9).multiplyScalar(heavy?rand(4,11):rand(3,8)),life:rand(.18,.45),w:rand(.012,.02),tail:.035,drag:2.2,floor});
    if(heavy){this.light(p,FLAME,10,.25,6);for(let i=0;i<3;i++)this.smoke.add({p:p.clone(),v:normal.clone().multiplyScalar(rand(.3,.8)).add(this.w.set(0,.4,0)),life:rand(.8,1.3),s0:.15,s1:.7,c0:ASH,c1:ASH,a:.35,drag:2,g:-.2,fadeIn:.1});}
  }
  structureHit(p:THREE.Vector3,heavy:boolean){
    const floor=this.ground(p.x,p.z);
    this.glow.add({p:p.clone(),life:.14,s0:heavy?1.1:.7,s1:heavy?1.6:1.05,c0:HOT,c1:FLAME,a:1});
    for(let i=0;i<(heavy?26:14);i++)this.sparks.add({p:p.clone(),v:randomDir(undefined,.3).multiplyScalar(rand(3,heavy?10:7)),life:rand(.25,.6),w:rand(.014,.024),tail:.04,drag:1.8,floor});
    if(heavy)this.light(p,FLAME,12,.3,7);
  }
  explode(p:THREE.Vector3,team:TeamId,k=1){
    const floor=this.ground(p.x,p.z),q=()=>p.clone().add(randomDir().multiplyScalar(rand(0,.3*k)));
    this.light(this.w.copy(p).setY(p.y+.5),FLAME,45*k,.7,10);
    this.glow.add({p:p.clone(),life:.22,s0:1.2*k,s1:3.2*k,a:1});
    this.glow.add({p:p.clone(),life:.45,s0:.8*k,s1:2.4*k,c1:FLAME,a:.9});
    for(let i=0;i<10;i++)this.glow.add({p:q(),v:randomDir(undefined,.5).multiplyScalar(rand(.8,2.4)*k).add(this.w.set(0,1.2,0)),life:rand(.5,.95),s0:.35*k,s1:rand(.9,1.5)*k,c0:HOT,c1:EMBER,a:.85,drag:2.4,g:-.6});
    for(let i=0;i<16;i++)this.smoke.add({p:q(),v:randomDir(undefined,.7).multiplyScalar(rand(.3,1.1)).add(this.w.set(0,rand(.5,1.3),0)),life:rand(2,3.4),s0:.5*k,s1:rand(1.6,2.4)*k,c0:SMOKE,c1:ASH,a:.6,drag:1.1,g:-.25,fadeIn:.12});
    for(let i=0;i<48*k;i++)this.sparks.add({p:p.clone(),v:randomDir(undefined,.45).multiplyScalar(rand(4,12)),life:rand(.5,1.2),w:rand(.016,.03),tail:.045,drag:1.2,floor});
    for(let i=0;i<14*k;i++)this.glow.add({p:q(),v:randomDir(undefined,.8).multiplyScalar(rand(1,3)),life:rand(1,1.8),s0:.06,s1:.02,c0:FLAME,c1:EMBER,a:.9,drag:.6,g:1.5});
    for(let i=0;i<12*k;i++)this.chunk(q(),randomDir(undefined,.6).multiplyScalar(rand(2,5.5)).add(this.w.set(0,2.2,0)),rand(.035,.11),i%3===0?GLOW[team]:i%3===1?ASH:shell);
    this.ring(p,.2,3.2*k,.6,FLAME);this.ring(p,.1,1.8*k,.9,GLOW[team],.7);
  }
  respawn(p:THREE.Vector3,team:TeamId){
    this.ring(p,1.6,.3,.5,GLOW[team]);this.ring(p,.3,2,.7,GLOW[team],.8,.45);this.light(this.w.copy(p).setY(p.y+.6),GLOW[team],8,.9,4);
    for(let i=0;i<28;i++){const a=rand(0,Math.PI*2),r=rand(.1,.5);this.glow.add({p:p.clone().add(this.w.set(Math.cos(a)*r,rand(0,.3),Math.sin(a)*r)),v:new THREE.Vector3(0,rand(1.4,3.2),0),life:rand(.7,1.2),s0:.1,s1:.02,c0:GLOW[team],c1:HOT,a:.9,drag:.4});}
  }
  levelUp(p:THREE.Vector3){
    this.ring(p,.3,1.4,.6,GOLD);
    for(let i=0;i<20;i++){const a=i/20*Math.PI*2;this.glow.add({p:p.clone().add(this.w.set(Math.cos(a)*.55,i/20*.4,Math.sin(a)*.55)),v:new THREE.Vector3(-Math.sin(a)*1.2,rand(1.3,2),Math.cos(a)*1.2),life:rand(.9,1.3),s0:.09,s1:.03,c0:GOLD,c1:HOT,a:.9,drag:1});}
  }
  heal(p:THREE.Vector3){
    this.ring(p,.3,1.3,.7,HEAL,.8);this.light(this.w.copy(p).setY(p.y+.6),HEAL,6,.8,4);
    for(let i=0;i<26;i++){const a=rand(0,Math.PI*2),r=rand(.15,.55);this.glow.add({p:p.clone().add(this.w.set(Math.cos(a)*r,rand(.1,.6),Math.sin(a)*r)),v:new THREE.Vector3(0,rand(.6,1.4),0),life:rand(.8,1.4),s0:.08,s1:.02,c0:HEAL,c1:HOT,a:.85,drag:.6,fadeIn:.15});}
  }
  supply(p:THREE.Vector3){
    this.ring(p,.2,.9,.45,GOLD,.7);
    for(let i=0;i<10;i++){const a=i/10*Math.PI*2;this.glow.add({p:p.clone().add(this.w.set(Math.cos(a)*.35,.25,Math.sin(a)*.35)),v:new THREE.Vector3(0,rand(.8,1.3),0),life:rand(.4,.7),s0:.06,s1:.02,c0:GOLD,c1:HOT,a:.8,drag:1.5});}
  }
  steam(p:THREE.Vector3,count=8){
    for(let i=0;i<count;i++)this.smoke.add({p:p.clone(),v:randomDir(undefined,.8).multiplyScalar(rand(.2,.6)).add(this.w.set(0,rand(.6,1.2),0)),life:rand(.8,1.4),s0:.1,s1:.7,c0:STEAM,c1:STEAM,a:.42,drag:1.6,g:-.4,fadeIn:.1});
  }
  burst(p:THREE.Vector3,color:RGB,count:number){
    this.glow.add({p:p.clone(),life:.25,s0:1.2,s1:2.4,c0:HOT,c1:color,a:1});this.light(p,color,25,.6,12);
    for(let i=0;i<count;i++)this.sparks.add({p:p.clone(),v:randomDir().multiplyScalar(rand(4,6)),life:rand(1.1,1.6),w:.025,tail:.06,c0:HOT,c1:color,drag:1.2,g:3});
  }

  // Robots render one frame behind the newest state, so event positions are shifted by the robot's rendered offset.
  rendered(feed:RenderFeed,id:string|undefined,alpha:number){
    const r=feed.frame?.robots.find(r=>r.id===id);if(!r)return null;
    robotWorld(feed,r,alpha,this.robot);return {r,offset:this.robot.clone().sub(toWorld(feed.frame!.arena,r.x,r.y,r.z))};
  }
  spawn(e:MatchEvent,feed:RenderFeed,alpha:number){
    const f=feed.frame!,p=toWorld(f.arena,e.x??f.arena.width/2,e.y??f.arena.height/2,e.z??.5),now=performance.now();
    if(e.type==='shot'){
      const s=this.rendered(feed,e.robot,alpha);if(!s)return;pulses.set('shot:'+s.r.id,now);
      const dir=aim(e.angle??s.r.aim,e.pitch??s.r.pitch??0),reach=s.r.muzzle_reach_m??.3;
      p.add(s.offset);if(!e.muzzle_origin)p.addScaledVector(this.v.set(dir.x,0,dir.z),reach);this.muzzle(p,dir,e.role==='hero'||e.role==='heavy');
    }else if(e.type==='impact')this.ricochet(p);
    else if(e.type==='hit'){
      const s=this.rendered(feed,e.robot,alpha);if(s){p.add(s.offset);pulses.set(s.r.id,now);}
      const normal=s?p.clone().sub(this.robot.setY(p.y)):UP.clone();if(normal.lengthSq()<1e-4)normal.copy(UP);
      this.armorHit(p,normal.normalize(),(e.damage??0)>=60,s?.r.team||(e.team==='red'?'blue':'red'));
    }else if(e.type==='base_hit'||e.type==='outpost_hit'){
      if(e.target_team)pulses.set(`${e.type==='base_hit'?'base':'outpost'}-${e.target_team}`,now);
      this.structureHit(p,(e.damage??0)>=100||!!e.weakspot);
    }else if(e.type==='destroy'||e.type==='explosion'){
      const s=this.rendered(feed,e.robot,alpha);if(s)p.add(s.offset);this.explode(p,s?.r.team||e.team||'red',e.type==='destroy'?1:.6);
    }else if(e.type==='collision'){
      const k=THREE.MathUtils.clamp((e.impulse_n_s??20)/40,.25,1);
      for(let i=0;i<2+k*4;i++)this.smoke.add({p:p.clone().setY(this.ground(p.x,p.z)+.05),v:this.w.set(rand(-1,1),rand(.1,.3),rand(-1,1)).multiplyScalar(.4+k*.5).clone(),life:rand(.6,.9),s0:.1,s1:.3+k*.4,c0:DUST,c1:DUST,a:.32,drag:2.5,fadeIn:.1});
      if(k>.6)this.structureHit(p,false);
    }else if(['respawn','level_up','overheat','remote_heal','ammo_purchase'].includes(e.type)){
      const s=this.rendered(feed,e.robot,alpha);if(!s)return;const base=this.robot.clone();
      if(e.type==='respawn')this.respawn(base,s.r.team);
      else if(e.type==='level_up')this.levelUp(base);
      else if(e.type==='remote_heal')this.heal(base);
      else if(e.type==='ammo_purchase')this.supply(base);
      else this.steam(base.setY(base.y+(s.r.muzzle_height_m??.5)).addScaledVector(aim(s.r.aim,0),s.r.muzzle_reach_m??.3));
    }else if(e.type==='rune_activated'&&e.team){
      const targets=f.runes?.[e.team]?.targets as {x:number;y:number;z:number}[]|undefined;if(!targets?.length)return;
      const c=new THREE.Vector3();for(const t of targets)c.add(toWorld(f.arena,t.x,t.y,t.z));c.divideScalar(targets.length);this.burst(c,GLOW[e.team],40);
    }else if(e.type==='outpost_rebuilt'&&e.team){
      const o=f.outposts?.[e.team];if(o)this.respawn(toWorld(f.arena,o.x,o.y,o.z??0),e.team);
    }else if(e.type==='finish'&&e.winner){
      const b=f.bases[e.winner],home=toWorld(f.arena,b.x,b.y,b.z??0);
      for(let i=0;i<4;i++)this.later.push({at:this.time+i*.38,run:()=>this.burst(home.clone().add(this.w.set(rand(-2,2),rand(4,6.5),rand(-2,2))),GLOW[e.winner!],60)});
    }else if(e.type==='skill'||e.type==='capture')this.ring(p,.2,1.6,.7,rgb('#7aebce'));
  }

  emit(feed:RenderFeed,alpha:number,dt:number){
    for(const r of feed.frame?.robots||[]){
      if(r.max_hp<=0)continue;
      const low=r.alive&&r.hp/r.max_hp<.3,rate=(r.alive?low?2.5:0:7)+(r.alive&&r.overheated?6:0);
      if(!rate){this.emitters.delete(r.id);continue;}
      let acc=(this.emitters.get(r.id)??Math.random())+dt*rate;
      if(acc>=1)robotWorld(feed,r,alpha,this.robot);
      for(;acc>=1;acc--){
        const p=this.robot.clone().add(this.w.set(rand(-.15,.15),.35,rand(-.15,.15)));
        if(r.alive&&r.overheated&&(!low||Math.random()<.7))this.steam(p.setY(this.robot.y+(r.muzzle_height_m??.5)),1);
        else if(r.alive)this.smoke.add({p,v:new THREE.Vector3(rand(-.1,.1),rand(.5,.9),rand(-.1,.1)),life:rand(1,1.5),s0:.1,s1:.55,c0:ASH,c1:ASH,a:.28,drag:.8,g:-.1,fadeIn:.15});
        else{
          this.smoke.add({p,v:new THREE.Vector3(rand(-.15,.15),rand(.7,1.2),rand(-.15,.15)),life:rand(1.8,2.6),s0:.2,s1:1.1,c0:SMOKE,c1:ASH,a:.5,drag:.8,g:-.15,fadeIn:.12});
          if(Math.random()<.25)this.glow.add({p:p.clone(),v:new THREE.Vector3(rand(-.3,.3),rand(.6,1.4),rand(-.3,.3)),life:rand(.6,1.1),s0:.05,s1:.015,c0:FLAME,c1:EMBER,a:.9,drag:.5});
        }
      }
      this.emitters.set(r.id,acc);
    }
  }

  tracers(feed:RenderFeed,alpha:number,balls?:THREE.InstancedMesh){
    const f=feed.frame;if(!f)return;
    if(this.previous!==feed.previous){this.previous=feed.previous;this.projectiles=new Map((feed.previous?.projectiles||[]).map(p=>[p.id,p]));}
    const head=new THREE.Vector3(),tail=new THREE.Vector3();let count=0;
    for(const p of f.projectiles.slice(0,320)){
      const old=this.projectiles.get(p.id),heavy=p.role==='hero'||p.role==='heavy',back=old?0:(1-alpha)*f.dt;
      if(old)toWorld(f.arena,old.x+(p.x-old.x)*alpha,old.y+(p.y-old.y)*alpha,old.z+(p.z-old.z)*alpha,head);
      else toWorld(f.arena,p.x-p.vx*back,p.y-p.vy*back,p.z-p.vz*back,head);
      this.v.set(p.vx,p.vz,p.vy);const speed=this.v.length();if(speed<1e-3)continue;
      tail.copy(head).addScaledVector(this.v,-Math.min(.035,.9/speed));
      this.sparks.write(tail,head,heavy?.045:.022,BALL,.95);this.glow.write(head,heavy?.14:.07,BALL,BALL,0,.65);
      if(balls){this.dummy.position.copy(head);this.dummy.rotation.set(0,0,0);this.dummy.scale.setScalar(p.radius);this.dummy.updateMatrix();balls.setMatrixAt(count++,this.dummy.matrix);}
    }
    if(balls){balls.count=count;balls.instanceMatrix.needsUpdate=true;}
  }

  step(dt:number,feed:RenderFeed,alpha:number,balls?:THREE.InstancedMesh){
    this.time+=dt;
    for(const job of this.later.filter(j=>j.at<=this.time))job.run();this.later=this.later.filter(j=>j.at>this.time);
    if(feed.frame){this.arena=feed.frame.arena;this.emit(feed,alpha,dt);this.tracers(feed,alpha,balls);}
    this.glow.step(dt);this.smoke.step(dt);this.sparks.step(dt);
    this.glow.commit();this.smoke.commit();this.sparks.commit();
  }
  writeDebris(mesh:THREE.InstancedMesh,dt:number){
    let j=0;
    for(const c of this.debris){
      if((c.age+=dt)>=c.life)continue;
      c.v.y-=9.8*dt;c.p.addScaledVector(c.v,dt);c.r.x+=c.w.x*dt;c.r.y+=c.w.y*dt;c.r.z+=c.w.z*dt;
      if(c.p.y<3){const floor=this.ground(c.p.x,c.p.z)+c.s*.5;if(c.p.y<floor){c.p.y=floor;if(c.v.y<0){c.v.y*=-.32;c.v.x*=.55;c.v.z*=.55;c.w.multiplyScalar(.5);}}}
      const fade=Math.min(1,(c.life-c.age)/.6);
      this.dummy.position.copy(c.p);this.dummy.rotation.copy(c.r);this.dummy.scale.set(c.s*fade,c.s*.6*fade,c.s*1.4*fade);this.dummy.updateMatrix();
      mesh.setMatrixAt(j,this.dummy.matrix);mesh.setColorAt(j,c.c);this.debris[j++]=c;
    }
    this.debris.length=j;mesh.count=j;mesh.instanceMatrix.needsUpdate=true;if(mesh.instanceColor)mesh.instanceColor.needsUpdate=true;
  }
  writeRings(mesh:THREE.InstancedMesh,dt:number){
    let j=0;const color=new THREE.Color();
    for(const r of this.rings){
      if((r.age+=dt)>=r.life)continue;this.rings[j++]=r;
      const t=Math.max(0,r.age)/r.life,radius=r.r0+(r.r1-r.r0)*(1-Math.pow(1-t,3)),fade=r.age<0?0:r.a*Math.pow(1-t,1.5);
      this.dummy.position.copy(r.p);this.dummy.rotation.set(0,0,0);this.dummy.scale.set(radius,1,radius);this.dummy.updateMatrix();
      mesh.setMatrixAt(j-1,this.dummy.matrix);mesh.setColorAt(j-1,color.copy(r.c).multiplyScalar(fade));
    }
    this.rings.length=j;mesh.count=j;mesh.instanceMatrix.needsUpdate=true;if(mesh.instanceColor)mesh.instanceColor.needsUpdate=true;
  }
  writeLights(lights:(THREE.PointLight|null)[],dt:number){
    for(const flash of this.flashes)flash.age+=dt;this.flashes=this.flashes.filter(f=>f.age<f.life);
    const strongest=[...this.flashes].sort((a,b)=>b.i*(1-b.age/b.life)-a.i*(1-a.age/a.life));
    lights.forEach((light,i)=>{if(!light)return;const f=strongest[i];if(!f){light.intensity=0;return;}light.position.copy(f.p);light.color.copy(f.c);light.distance=f.range;light.intensity=f.i*Math.pow(1-f.age/f.life,2);});
  }
}

// Hex-cell barrier around a base while its outpost stands (rule 5.5.1); it is only drawn when it appears or breaks.
const domeVertex=`varying vec3 vPos;varying vec3 vNormal;varying vec3 vView;void main(){vPos=position;vec4 w=modelMatrix*vec4(position,1.);vNormal=normalize(mat3(modelMatrix)*normal);vView=normalize(cameraPosition-w.xyz);gl_Position=projectionMatrix*viewMatrix*w;}`;
const domeFragment=`uniform vec3 uColor;uniform float uAlpha,uCrack,uTime,uFlash;varying vec3 vPos;varying vec3 vNormal;varying vec3 vView;
float hexDist(vec2 p){p=abs(p);return max(dot(p,normalize(vec2(1.,1.732))),p.x);}
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
void main(){vec3 n=normalize(vPos);vec2 uv=vec2(atan(n.z,n.x)*2.6,asin(clamp(n.y,-1.,1.))*2.6)*1.7;
  vec2 r=vec2(1.,1.732),h=r*.5,a=mod(uv,r)-h,b=mod(uv-h,r)-h,gv=dot(a,a)<dot(b,b)?a:b,id=uv-gv;
  float rnd=hash(floor(id*10.)),edge=smoothstep(.36,.47,hexDist(gv)),fres=pow(1.-abs(dot(normalize(vNormal),vView)),2.2);
  if(rnd<uCrack)discard;
  float pulse=.5+.5*sin(uTime*7.+rnd*6.283),cell=.12+.18*pulse*step(.82,rnd);
  vec3 c=uColor*(edge*1.8+cell+fres*1.2)+vec3(1.)*uFlash*(.35+edge);
  float alpha=uAlpha*clamp(edge*.85+cell+fres*.7+uFlash*.4,0.,1.)*(1.-smoothstep(.75,1.,uCrack+.2*rnd));
  gl_FragColor=vec4(c*alpha,alpha);}`;
type DomeState={mode:'idle'|'break'|'form';age:number;hp:number;baseHp:number};

export function Effects({feed}:{feed:MutableRefObject<RenderFeed>}){
  const fx=useMemo(()=>new FxWorld(),[]),seen=useRef(new Set<string>()),generation=useRef(''),debris=useRef<THREE.InstancedMesh>(null),balls=useRef<THREE.InstancedMesh>(null),rings=useRef<THREE.InstancedMesh>(null),lights=useRef<(THREE.PointLight|null)[]>([]);
  const domes=useRef<Record<TeamId,THREE.Mesh|null>>({red:null,blue:null}),domeState=useRef<Record<TeamId,DomeState>>({red:{mode:'idle',age:0,hp:-1,baseHp:-1},blue:{mode:'idle',age:0,hp:-1,baseHp:-1}});
  const domeMaterials=useMemo(()=>({red:new THREE.ShaderMaterial({vertexShader:domeVertex,fragmentShader:domeFragment,transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,side:THREE.DoubleSide,uniforms:{uColor:{value:new THREE.Color('#ff3b30')},uAlpha:{value:0},uCrack:{value:0},uTime:{value:0},uFlash:{value:0}}}),
    blue:new THREE.ShaderMaterial({vertexShader:domeVertex,fragmentShader:domeFragment,transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,side:THREE.DoubleSide,uniforms:{uColor:{value:new THREE.Color('#2f8cff')},uAlpha:{value:0},uCrack:{value:0},uTime:{value:0},uFlash:{value:0}}})}),[]);
  const dome=useMemo(()=>new THREE.SphereGeometry(1.25,48,24,0,Math.PI*2,0,Math.PI/2),[]);
  useEffect(()=>()=>{dome.dispose();domeMaterials.red.dispose();domeMaterials.blue.dispose();},[dome,domeMaterials]);
  const assets=useMemo(()=>{
    const uniforms={uScale:{value:800}};
    return {uniforms,
      glow:new THREE.ShaderMaterial({uniforms,vertexShader:spriteVertex,fragmentShader:glowFragment,transparent:true,depthWrite:false,blending:THREE.AdditiveBlending}),
      smoke:new THREE.ShaderMaterial({uniforms,vertexShader:spriteVertex,fragmentShader:smokeFragment,transparent:true,depthWrite:false}),
      spark:new THREE.ShaderMaterial({uniforms,vertexShader:sparkVertex,fragmentShader:sparkFragment,transparent:true,depthWrite:false,blending:THREE.AdditiveBlending}),
      chunk:new THREE.BoxGeometry(1,1,1),metal:new THREE.MeshStandardMaterial({metalness:.55,roughness:.45}),
      ball:new THREE.SphereGeometry(1,10,6),plastic:new THREE.MeshStandardMaterial({color:'#66ee55',emissive:'#66ee55',emissiveIntensity:.25,roughness:.5}),
      plate:new THREE.PlaneGeometry(2,2).rotateX(-Math.PI/2),ring:new THREE.MeshBasicMaterial({map:ringTexture(),transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,toneMapped:false,fog:false})};
  },[]);
  useEffect(()=>()=>{for(const item of [assets.glow,assets.smoke,assets.spark,assets.chunk,assets.metal,assets.ball,assets.plastic,assets.plate,assets.ring,fx.glow.geometry,fx.smoke.geometry,fx.sparks.geometry])item.dispose();assets.ring.map?.dispose();},[assets,fx]);
  useFrame(({camera,size,gl},delta)=>{
    const dt=Math.min(delta,.05),current=feed.current,f=current.frame,alpha=feedAlpha(current);
    if(generation.current!==current.generation){generation.current=current.generation;fx.clear();seen.current.clear();for(const d of Object.values(domeState.current))Object.assign(d,{mode:'idle',age:0,hp:-1,baseHp:-1});}
    assets.uniforms.uScale.value=size.height*gl.getPixelRatio()/(2*Math.tan(((camera as THREE.PerspectiveCamera).fov||42)*Math.PI/360));
    if(f){fx.arena=f.arena;for(const e of current.events){const key=e.id||`${e.tick}:${e.type}:${e.robot}:${e.x}:${e.y}`;if(seen.current.has(key))continue;seen.current.add(key);fx.spawn(e,current,alpha);}}
    if(f)for(const team of ['red','blue'] as const){
      const d=domeState.current[team],outpost=f.outposts?.[team],base=f.bases[team],mesh=domes.current[team],u=domeMaterials[team].uniforms;
      if(!outpost||!mesh)continue;
      const where=toWorld(f.arena,base.x,base.y,base.z??0),top=toWorld(f.arena,outpost.x,outpost.y,(outpost.z??0)+1.1);
      if(d.hp>=0&&!current.paused){
        if(d.hp>0&&outpost.hp<=0){fx.explode(top,team,1.35);for(let i=0;i<3;i++)fx.later.push({at:fx.time+.18+i*.22,run:()=>fx.burst(top.clone().add(new THREE.Vector3(rand(-.4,.4),rand(0,.8),rand(-.4,.4))),GLOW[team],22)});if(base.hp>0)Object.assign(d,{mode:'break',age:0});}
        else if(d.hp<=0&&outpost.hp>0&&base.hp>0)Object.assign(d,{mode:'form',age:0});
        if(d.baseHp>0&&base.hp<=0){fx.explode(where.clone().setY(where.y+.8),team,2.2);for(let i=0;i<6;i++)fx.later.push({at:fx.time+.25+i*.3,run:()=>fx.explode(where.clone().add(new THREE.Vector3(rand(-.9,.9),rand(.3,1.6),rand(-.9,.9))),team,.8)});fx.ring(where,.3,6,1.2,GLOW[team],.9);}
      }
      d.hp=outpost.hp;d.baseHp=base.hp;
      if(d.mode==='idle'){mesh.visible=false;continue;}
      d.age+=dt;mesh.visible=true;mesh.position.copy(where);u.uTime.value+=dt;
      if(d.mode==='break'){const t=d.age;
        u.uAlpha.value=t<.25?t/.25:1;u.uFlash.value=t<.25?0:t<.7?.5+.5*Math.sin(t*40):Math.max(0,1-(t-.7)*3);u.uCrack.value=t<.7?0:Math.min(1,(t-.7)/.9);mesh.scale.setScalar(t<.25?.9+.1*t/.25:1+Math.max(0,t-.7)*.14);
        if(t>=.7&&t-dt<.7)for(let i=0;i<40;i++){const a=rand(0,Math.PI*2),e=rand(.1,1.4),p=where.clone().add(new THREE.Vector3(Math.cos(a)*Math.cos(e)*1.25,Math.sin(e)*1.25,Math.sin(a)*Math.cos(e)*1.25));fx.sparks.add({p,v:p.clone().sub(where).normalize().multiplyScalar(rand(2,5)),life:rand(.5,1),w:.03,tail:.08,c0:HOT,c1:GLOW[team],drag:1.4,g:2});}
        if(t>1.7)d.mode='idle';}
      else{const t=d.age;u.uCrack.value=Math.max(0,1-t/.8);u.uAlpha.value=t<1.2?1:Math.max(0,1-(t-1.2)/.6);u.uFlash.value=Math.max(0,.6-t);mesh.scale.setScalar(1);if(t>1.8)d.mode='idle';}
    }
    if(seen.current.size>6000)seen.current.clear();
    fx.step(dt,current,alpha,balls.current||undefined);
    if(debris.current)fx.writeDebris(debris.current,dt);if(rings.current)fx.writeRings(rings.current,dt);fx.writeLights(lights.current,dt);
  });
  return <>
    <points geometry={fx.smoke.geometry} material={assets.smoke} frustumCulled={false} renderOrder={5}/>
    <points geometry={fx.glow.geometry} material={assets.glow} frustumCulled={false} renderOrder={6}/>
    <mesh geometry={fx.sparks.geometry} material={assets.spark} frustumCulled={false} renderOrder={7}/>
    <instancedMesh ref={balls} args={[assets.ball,assets.plastic,320]} frustumCulled={false}/>
    <instancedMesh ref={debris} args={[assets.chunk,assets.metal,DEBRIS]} frustumCulled={false} castShadow/>
    <instancedMesh ref={rings} args={[assets.plate,assets.ring,RINGS]} frustumCulled={false} renderOrder={4}/>
    {Array.from({length:LIGHTS},(_,i)=><pointLight key={i} ref={e=>{lights.current[i]=e;}} intensity={0} distance={8} decay={2}/>)}
    {(['red','blue'] as const).map(team=><mesh key={team} ref={e=>{domes.current[team]=e;}} geometry={dome} material={domeMaterials[team]} visible={false} renderOrder={8} frustumCulled={false}/>)}
  </>;
}
