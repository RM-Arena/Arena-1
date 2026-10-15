import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const COLORS = {red:0xeb7771, blue:0x6ab8eb, neutral:0xe6b765};
const world = (x,y,height=0) => new THREE.Vector3(x-20,height,y-12);
const material = (color, extra={}) => new THREE.MeshStandardMaterial({color, roughness:.7, metalness:.35, ...extra});

export class ArenaScene {
  constructor(container,onSelect) {
    this.container=container; this.onSelect=onSelect; this.robots=new Map(); this.bullets=new Map(); this.effects=[]; this.zones=new Map(); this.bases=new Map();
    this.scene=new THREE.Scene(); this.scene.background=new THREE.Color(0x17222b); this.scene.fog=new THREE.Fog(0x17222b,50,115);
    this.renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio,2)); this.renderer.shadowMap.enabled=true; this.renderer.shadowMap.type=THREE.PCFSoftShadowMap;
    this.renderer.outputColorSpace=THREE.SRGBColorSpace; this.renderer.toneMapping=THREE.ACESFilmicToneMapping; this.renderer.toneMappingExposure=1.2;
    container.prepend(this.renderer.domElement);
    this.camera=new THREE.PerspectiveCamera(40,1,.1,180); this.camera.position.set(32,38,35);
    this.controls=new OrbitControls(this.camera,this.renderer.domElement); this.controls.target.set(0,0,0); this.controls.enableDamping=true; this.controls.dampingFactor=.07;
    this.controls.minDistance=8; this.controls.maxDistance=80; this.controls.maxPolarAngle=Math.PI*.46;
    this.scene.add(new THREE.HemisphereLight(0xa6d6f1,0x232f36,2.4));
    const light=new THREE.DirectionalLight(0xffedcc,3.1); light.position.set(6,28,12); light.castShadow=true;
    light.shadow.mapSize.set(2048,2048); light.shadow.camera.left=-28; light.shadow.camera.right=28; light.shadow.camera.top=22; light.shadow.camera.bottom=-22;
    light.shadow.camera.far=80; light.shadow.bias=-.0005; this.scene.add(light);
    this.groundGroup=new THREE.Group(); this.scene.add(this.groundGroup); this.mapName=null; this.selected=null; this.mode='orbit';
    this.raycaster=new THREE.Raycaster(); let down;
    this.renderer.domElement.addEventListener('pointerdown', e => {down=[e.clientX,e.clientY];});
    this.renderer.domElement.addEventListener('pointerup', e => {
      if(!down || Math.hypot(e.clientX-down[0],e.clientY-down[1])>5)return;
      const rect=this.renderer.domElement.getBoundingClientRect(); this.raycaster.setFromCamera(new THREE.Vector2((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1),this.camera);
      const hit=this.raycaster.intersectObjects([...this.robots.values()].map(r=>r.group),true).find(h=>h.object.userData.robotId);
      if(hit)this.onSelect(hit.object.userData.robotId);
    });
    new ResizeObserver(()=>this.resize()).observe(container); this.resize();
  }
  resize(){ const {width,height}=this.container.getBoundingClientRect(); this.renderer.setSize(width,height,false);this.camera.aspect=width/height;this.camera.updateProjectionMatrix(); }
  box(parent,size,pos,mat){const mesh=new THREE.Mesh(new THREE.BoxGeometry(...size),mat);mesh.position.set(...pos);mesh.castShadow=true;mesh.receiveShadow=true;parent.add(mesh);return mesh;}
  cylinder(parent,radius,height,pos,mat){const mesh=new THREE.Mesh(new THREE.CylinderGeometry(radius,radius,height,24),mat);mesh.position.set(...pos);mesh.castShadow=true;mesh.receiveShadow=true;parent.add(mesh);return mesh;}
  label(text,color='#c8d5dd',width=256){
    const canvas=document.createElement('canvas'); canvas.width=width;canvas.height=64;const ctx=canvas.getContext('2d');
    ctx.fillStyle=color;ctx.textAlign='center';ctx.textBaseline='middle';ctx.font='600 25px sans-serif';ctx.fillText(text,width/2,32);
    const texture=new THREE.CanvasTexture(canvas);const sprite=new THREE.Sprite(new THREE.SpriteMaterial({map:texture,depthTest:false,transparent:true}));sprite.scale.set(3.5,.875,1);return sprite;
  }
  buildMap(arena){
    this.mapName=arena.name; this.clearGroup(this.groundGroup);this.zones.clear();this.bases.clear();
    const floor=material(0x2f424d),edge=material(0x1b2933),metal=material(0x667b83),gold=material(0xcda963,{emissive:0x3e2f12});
    this.box(this.groundGroup,[42,.7,26],[0,-.6,0],edge); this.box(this.groundGroup,[40,.12,24],[0,-.16,0],floor);
    for(let x=-20;x<=20;x+=2){const l=new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(x,-.085,-12),new THREE.Vector3(x,-.085,12)]),new THREE.LineBasicMaterial({color:0x46616c,transparent:true,opacity:.38}));this.groundGroup.add(l);}
    for(let z=-12;z<=12;z+=2){const l=new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-20,-.085,z),new THREE.Vector3(20,-.085,z)]),new THREE.LineBasicMaterial({color:0x46616c,transparent:true,opacity:.38}));this.groundGroup.add(l);}
    for(const z of [-12.5,12.5])this.box(this.groundGroup,[41,.45,.35],[0,.05,z],metal);
    for(const x of [-20.5,20.5])this.box(this.groundGroup,[.35,.45,24.8],[x,.05,0],metal);
    for(const w of arena.obstacles){
      const p=world(w.x+w.w/2,w.y+w.h/2);this.box(this.groundGroup,[w.w,1.6,w.h],[p.x,.7,p.z],material(0x435963));
      this.box(this.groundGroup,[w.w+.08,.12,w.h+.08],[p.x,1.54,p.z],metal);
      for(const zz of [-w.h/2,w.h/2])this.box(this.groundGroup,[w.w*.72,.08,.05],[p.x,1.64,p.z+zz],gold);
    }
    for(const t of arena.terrain){const p=world(t.x+t.w/2,t.y+t.h/2);this.box(this.groundGroup,[t.w,.035,t.h],[p.x,-.06,p.z],material(0x39545c));for(let i=0;i<t.w;i+=.6)this.box(this.groundGroup,[.05,.04,t.h],[p.x-t.w/2+i,-.04,p.z],material(0x587279));}
    for(const z of arena.zones){
      const g=new THREE.Group();g.position.copy(world(z.x,z.y,.01));this.groundGroup.add(g);
      const ring=new THREE.Mesh(new THREE.RingGeometry(z.radius-.07,z.radius,64),new THREE.MeshBasicMaterial({color:COLORS.neutral,transparent:true,opacity:.65,side:THREE.DoubleSide}));ring.rotation.x=-Math.PI/2;g.add(ring);
      const pad=new THREE.Mesh(new THREE.CircleGeometry(z.radius-.1,64),new THREE.MeshBasicMaterial({color:COLORS.neutral,transparent:true,opacity:.07,depthWrite:false}));pad.rotation.x=-Math.PI/2;g.add(pad);
      this.cylinder(g,.24,.45,[0,.18,0],metal);const beacon=this.cylinder(g,.12,.8,[0,.8,0],material(COLORS.neutral,{emissive:COLORS.neutral,emissiveIntensity:.6}));
      const label=this.label(z.id.toUpperCase());label.position.set(0,1.6,0);label.scale.set(2,.5,1);g.add(label);this.zones.set(z.id,{ring,pad,beacon});
    }
    for(const [team,x] of [['red',1.6],['blue',38.4]]){
      const g=new THREE.Group();g.position.copy(world(x,12));this.groundGroup.add(g);
      const c=COLORS[team],mat=material(c,{emissive:c,emissiveIntensity:.13});
      this.cylinder(g,1.25,.6,[0,.22,0],edge);this.cylinder(g,.9,1.5,[0,1.05,0],metal);const core=this.cylinder(g,.6,.8,[0,2.05,0],mat);
      const cap=new THREE.Mesh(new THREE.ConeGeometry(.85,.55,4),mat);cap.position.y=2.7;g.add(cap);
      const label=this.label(team.toUpperCase()+' BASE',team==='red'?'#ef9994':'#8ccbf1');label.position.y=3.7;g.add(label);this.bases.set(team,{g,core});
      const border=new THREE.Mesh(new THREE.RingGeometry(3.9,4,64),new THREE.MeshBasicMaterial({color:c,opacity:.2,transparent:true,side:THREE.DoubleSide}));border.rotation.x=-Math.PI/2;border.position.y=.02;g.add(border);
    }
    const title=this.label('RMUC  /  ARENA','#819ba9',512);title.position.set(0,-.04,11);title.material.depthTest=true;title.scale.set(9,1.125,1);this.groundGroup.add(title);
  }
  buildRobot(r){
    const g=new THREE.Group(),body=new THREE.Group(),turret=new THREE.Group();g.add(body);body.add(turret);this.scene.add(g);
    const scale=r.role==='hero'?1.15:r.role==='scout'?.82:1;const mat=material(COLORS[r.team]),dark=material(0x26313a),steel=material(0x99adb7);
    this.box(body,[1.04*scale,.3,.82*scale],[0,.32,0],mat);this.box(body,[.8*scale,.1,.68*scale],[0,.54,0],dark);
    const wheels=[];for(const x of [-.35,.35])for(const z of [-.5,.5]){const w=this.cylinder(body,.22,.16,[x,.2,z],dark);w.rotation.x=Math.PI/2;wheels.push(w);}
    turret.position.y=.6;this.cylinder(turret,.3,.22,[0,.03,0],mat);
    if(r.role==='engineer'){
      this.box(turret,[.8,.1,.1],[.38,.2,0],steel);this.box(turret,[.12,.45,.12],[.7,.38,0],material(COLORS.neutral));
    } else {
      const barrels=r.role==='sentry'?[-.14,.14]:[0];
      for(const z of barrels){const barrel=this.cylinder(turret,r.role==='hero'?.1:.055,r.role==='hero'?.95:.7,[.5,.12,z],steel);barrel.rotation.z=Math.PI/2;}
      this.box(turret,[.32,.22,.4],[-.12,.13,0],mat);
    }
    const sprite=this.label((r.team==='red'?'R':'B')+r.slot,r.team==='red'?'#ffa9a1':'#a5daff',128);sprite.position.y=1.8;sprite.scale.set(1.2,.6,1);g.add(sprite);
    const hp=new THREE.Sprite(new THREE.SpriteMaterial({color:COLORS[r.team],depthTest:false}));hp.position.y=1.42;hp.scale.set(.85,.065,1);g.add(hp);
    const select=new THREE.Mesh(new THREE.RingGeometry(.7,.77,32),new THREE.MeshBasicMaterial({color:0xf2cb7f,side:THREE.DoubleSide,transparent:true,opacity:.9}));select.rotation.x=-Math.PI/2;select.position.y=.03;g.add(select);select.visible=false;
    g.traverse(o=>{o.userData.robotId=r.id;});return {group:g,body,turret,hp,sprite,select,wheels,last:world(r.x,r.y)};
  }
  setCamera(mode,selected){this.mode=mode;this.selected=selected||this.selected;this.controls.enabled=mode==='orbit';if(mode==='orbit'){this.controls.target.set(0,0,0);this.camera.position.set(32,38,35);}if(mode==='top'){this.camera.position.set(0,53,.01);this.controls.target.set(0,0,0);this.camera.lookAt(0,0,0);}}
  update(frame,previous,alpha,dt,now){
    if(!frame)return;if(this.mapName!==frame.arena.name)this.buildMap(frame.arena);
    const old=new Map((previous?.robots||[]).map(r=>[r.id,r]));
    for(const r of frame.robots){
      let model=this.robots.get(r.id);if(!model){model=this.buildRobot(r);this.robots.set(r.id,model);}
      const p=old.get(r.id)||r,x=THREE.MathUtils.lerp(p.x,r.x,alpha),y=THREE.MathUtils.lerp(p.y,r.y,alpha);
      model.group.position.copy(world(x,y));model.body.rotation.y=-r.heading;model.turret.rotation.y=-(r.aim-r.heading);
      model.hp.scale.x=.85*r.hp/r.max_hp;model.hp.visible=r.alive;model.sprite.material.opacity=r.alive?1:.3;
      model.body.position.y=r.alive?Math.sin(now*10+r.slot)*.008:-.1;model.body.rotation.z=r.alive?0:.14;
      model.group.traverse(o=>{if(o.isMesh && o!==model.select){o.material.transparent=!r.alive;o.material.opacity=r.alive?1:.32;}});
      model.select.visible=r.id===this.selected;if(r.shield>0){model.select.visible=true;model.select.material.color.setHex(COLORS[r.team]);}else model.select.material.color.setHex(0xf2cb7f);
      const moved=model.last.distanceTo(model.group.position);for(const w of model.wheels)w.rotation.y+=moved*3;model.last.copy(model.group.position);
    }
    const active=new Set();for(const p of frame.projectiles){active.add(p.id);let mesh=this.bullets.get(p.id);if(!mesh){mesh=new THREE.Mesh(new THREE.SphereGeometry(.085,6,6),new THREE.MeshBasicMaterial({color:p.team==='red'?0xffc18a:0x91e1ff}));this.scene.add(mesh);this.bullets.set(p.id,mesh);}mesh.position.copy(world(p.x,p.y,.75));mesh.scale.set(2.2,1,1);mesh.rotation.y=-Math.atan2(p.vy,p.vx);}
    for(const [id,mesh] of this.bullets)if(!active.has(id)){this.scene.remove(mesh);mesh.geometry.dispose();mesh.material.dispose();this.bullets.delete(id);}
    for(const [id,state] of Object.entries(frame.zones)){const z=this.zones.get(id);const color=COLORS[state.owner]||COLORS.neutral;z.ring.material.color.setHex(color);z.pad.material.color.setHex(color);z.pad.material.opacity=.05+Math.abs(state.progress)*.09;z.beacon.material.color.setHex(color);z.beacon.material.emissive.setHex(color);}
    for(const [team,b] of Object.entries(frame.bases)){const model=this.bases.get(team);model.g.scale.y=.8+.2*b.hp/b.max_hp;model.core.material.emissiveIntensity=.2+Math.sin(now*2)*.08;}
    for(let i=this.effects.length-1;i>=0;i--){const e=this.effects[i];e.life-=dt;e.mesh.position.addScaledVector(e.velocity,dt);e.velocity.y-=dt*2;e.mesh.scale.multiplyScalar(1+dt*1.3);e.mesh.material.opacity=Math.max(0,e.life/e.total);if(e.life<=0){this.scene.remove(e.mesh);e.mesh.geometry.dispose();e.mesh.material.dispose();this.effects.splice(i,1);}}
    if(this.mode==='follow'&&this.selected){const r=frame.robots.find(r=>r.id===this.selected);if(r){const target=world(r.x,r.y,.7);this.controls.target.lerp(target,Math.min(1,dt*4));this.camera.position.lerp(target.clone().add(new THREE.Vector3(-8,9,8)),Math.min(1,dt*2));this.camera.lookAt(this.controls.target);}}
    if(this.mode==='cinematic'){const a=now*.055;this.camera.position.set(Math.sin(a)*40,33,Math.cos(a)*34);this.camera.lookAt(0,0,0);}else if(this.mode==='orbit')this.controls.update();
    this.renderer.render(this.scene,this.camera);
  }
  effect(event){
    const n=event.type==='destroy'?24:event.type==='shot'?2:event.type==='skill'?12:6;
    if(!['shot','hit','destroy','impact','skill','base_hit'].includes(event.type))return;
    for(let i=0;i<n;i++){if(this.effects.length>350)break;const color=event.type==='skill'?0x85e2c1:event.type==='shot'?0xffdc88:0xfeb26f;
      const mesh=new THREE.Mesh(new THREE.SphereGeometry(event.type==='destroy'?.12:.055,4,4),new THREE.MeshBasicMaterial({color,transparent:true}));mesh.position.copy(world(event.x,event.y,.65));
      const angle=(i*2.39996+event.tick*.7),speed=event.type==='destroy'?2.8:.8,life=event.type==='shot'?.08:event.type==='destroy'?1.1:.5;
      const velocity=new THREE.Vector3(Math.cos(angle)*speed,1.5+Math.sin(i)*.4,Math.sin(angle)*speed);this.scene.add(mesh);this.effects.push({mesh,velocity,life,total:life});
    }
  }
  clearEffects(){for(const e of this.effects){this.scene.remove(e.mesh);e.mesh.geometry.dispose();e.mesh.material.dispose();}this.effects=[];}
  clearGroup(group){group.traverse(o=>{o.geometry?.dispose();if(o.material){for(const m of Array.isArray(o.material)?o.material:[o.material]){m.map?.dispose();m.dispose();}}});group.clear();}
}
