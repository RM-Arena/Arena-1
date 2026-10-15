export class ArenaAudio {
  constructor(){this.enabled=false;this.context=null;this.active=0;}
  async enable(){
    if(!this.context){const Audio=window.AudioContext||window.webkitAudioContext;this.context=new Audio();this.master=this.context.createGain();this.master.gain.value=.23;this.master.connect(this.context.destination);this.destination=this.context.createMediaStreamDestination();this.master.connect(this.destination);}
    await this.context.resume();this.enabled=true;
  }
  disable(){this.enabled=false;}
  play(event){
    if(!this.enabled||!this.context||this.active>20)return;
    const settings={shot:[event.role==='hero'?110:220,.07,'triangle'],hit:[500,.06,'square'],base_hit:[150,.13,'triangle'],destroy:[65,.48,'sawtooth'],capture:[680,.28,'sine'],skill:[850,.18,'sine'],finish:[440,.7,'sine']}[event.type];
    if(!settings)return;const [freq,len,type]=settings,t=this.context.currentTime;
    const osc=this.context.createOscillator(),gain=this.context.createGain();osc.type=type;osc.frequency.setValueAtTime(freq,t);osc.frequency.exponentialRampToValueAtTime(event.type==='destroy'?22:freq*.55,t+len);
    gain.gain.setValueAtTime(.001,t);gain.gain.exponentialRampToValueAtTime(event.type==='destroy'?.45:.18,t+.008);gain.gain.exponentialRampToValueAtTime(.001,t+len);
    const pan=this.context.createStereoPanner();pan.pan.value=Math.max(-.8,Math.min(.8,((event.x??20)-20)/25));osc.connect(gain);gain.connect(pan);pan.connect(this.master);osc.start(t);osc.stop(t+len);this.active++;
    osc.onended=()=>{this.active--;osc.disconnect();gain.disconnect();pan.disconnect();};
  }
}

export class BroadcastRecorder {
  constructor(scene,audio){this.scene=scene;this.audio=audio;this.recorder=null;this.canvas=document.createElement('canvas');this.canvas.width=1920;this.canvas.height=1080;this.ctx=this.canvas.getContext('2d');}
  get active(){return this.recorder?.state==='recording';}
  async start(){
    if(!window.MediaRecorder||!this.canvas.captureStream)throw new Error('当前浏览器不支持录像，请使用 Chrome / Edge');
    await this.audio.enable();this.stream=this.canvas.captureStream(30);for(const track of this.audio.destination.stream.getAudioTracks())this.stream.addTrack(track.clone());
    const mime=['video/webm;codecs=vp9,opus','video/webm;codecs=vp8,opus','video/webm'].find(v=>MediaRecorder.isTypeSupported(v));
    if(!mime)throw new Error('当前浏览器不支持 WebM 录像编码');
    this.chunks=[];this.recorder=new MediaRecorder(this.stream,{mimeType:mime,videoBitsPerSecond:7000000});this.started=performance.now();
    this.recorder.ondataavailable=e=>{if(e.data.size)this.chunks.push(e.data);};
    this.recorder.onstop=()=>{const blob=new Blob(this.chunks,{type:mime});download(blob,'rmuc-arena-'+new Date().toISOString().replaceAll(':','-')+'.webm');this.stream.getTracks().forEach(t=>t.stop());this.chunks=[];};this.recorder.start(1000);
  }
  stop(){if(this.active)this.recorder.stop();}
  draw(frame,metadata){
    if(!this.active||!frame)return;const c=this.ctx,source=this.scene.renderer.domElement;
    c.fillStyle='#111920';c.fillRect(0,0,1920,1080);
    const scale=Math.min(1920/source.width,950/source.height),w=source.width*scale,h=source.height*scale;c.drawImage(source,(1920-w)/2,90+(950-h)/2,w,h);
    c.fillStyle='#111920e8';c.fillRect(0,0,1920,92);c.fillRect(0,1025,1920,55);
    c.textBaseline='middle';c.textAlign='left';c.font='bold 27px sans-serif';c.fillStyle='#e8bd73';c.fillText('RMUC / ARENA',32,44);
    c.font='bold 24px sans-serif';c.fillStyle='#ef8f85';c.fillText(`${metadata?.teams?.red?.name||'RED'}   ${Math.floor(frame.teams.red.score)}`,410,44);
    c.textAlign='right';c.fillStyle='#8bc9f1';c.fillText(`${Math.floor(frame.teams.blue.score)}   ${metadata?.teams?.blue?.name||'BLUE'}`,1510,44);
    c.textAlign='center';c.fillStyle='#eef3f7';c.font='32px monospace';c.fillText(clock(frame.remaining),960,43);
    c.font='16px sans-serif';c.fillStyle='#9eb2c0';c.fillText(`SEED ${frame.seed}   ·   ${frame.arena.name.toUpperCase()}   ·   ${frame.status==='finished'?frame.winner?frame.winner.toUpperCase()+' WINS':'DRAW':'7v7 STRATEGY BATTLE'}`,960,1053);
    c.textAlign='left';c.font='15px sans-serif';c.fillText(`RED BASE ${Math.ceil(frame.bases.red.hp)}`,32,1053);c.textAlign='right';c.fillText(`BLUE BASE ${Math.ceil(frame.bases.blue.hp)}`,1888,1053);
    // The health strips are burned into the exported video, independent of DOM panels.
    for(const [side,team] of [[0,'red'],[1,'blue']]){let i=0;for(const r of frame.robots.filter(r=>r.team===team)){const x=side?1794:20,y=140+i++*44;c.fillStyle='#111920bb';c.fillRect(x,y,106,34);c.fillStyle=team==='red'?'#ef8f85':'#8bc9f1';c.font='13px sans-serif';c.textAlign='left';c.fillText(`${team==='red'?'R':'B'}${r.slot} ${r.alive?Math.ceil(r.hp):'OUT'}`,x+8,y+12);c.fillStyle='#3a4c56';c.fillRect(x+8,y+24,90,3);c.fillStyle=team==='red'?'#ef8f85':'#8bc9f1';c.fillRect(x+8,y+24,90*r.hp/r.max_hp,3);}}
  }
}

export function clock(seconds){seconds=Math.ceil(Math.max(0,seconds));return `${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;}
export function download(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);}
