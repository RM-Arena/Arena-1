import {useCallback,useEffect,useState} from 'react';
import {Check,Copy,Crown,LogOut,Pause,Play,Radio,Shield,Square,Users,Wifi} from 'lucide-react';
import {ROLE_NAMES,type CatalogEntry,type Frame,type LanSeat,type LanStatus,type Season,type ServerState,type TeamId} from './types';
import './lan.css';

async function json<T>(path:string,body?:unknown):Promise<T>{
  const response=await fetch(path,{method:'POST',headers:body===undefined?undefined:{'Content-Type':'application/json'},
    body:body===undefined?undefined:JSON.stringify(body)});
  const value=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:value.error||'联机请求失败');
  return value as T;
}

async function statusNow():Promise<LanStatus>{
  const response=await fetch('/api/lan/status');
  if(!response.ok)throw new Error('无法读取联机状态');
  return await response.json() as LanStatus;
}

const ROLE_LABEL={host:'主机裁判',operator:'操作手',spectator:'观众'} as const;

export function LanLobby({status,onStatus,catalog,frame,live,latency,onEnter}:{
  status:LanStatus|null;
  onStatus:(value:LanStatus,reconnect?:boolean)=>void;
  catalog:Record<string,CatalogEntry>;
  frame:Frame|null;
  live:ServerState|null;
  latency:number|null;
  onEnter:()=>void;
}){
  const [name,setName]=useState(()=>{try{return localStorage.getItem('rmuc-lan-name')||'';}catch{return '';}});
  const [pin,setPin]=useState('');
  const [busy,setBusy]=useState(false);
  const [notice,setNotice]=useState('');
  const [target,setTarget]=useState('');
  const [forfeitTeam,setForfeitTeam]=useState<TeamId>('red');
  useEffect(()=>{if(name.trim())try{localStorage.setItem('rmuc-lan-name',name.trim());}catch{}},[name]);

  const run=useCallback(async(action:()=>Promise<LanStatus>,reconnect=false)=>{
    setBusy(true);setNotice('');
    try{onStatus(await action(),reconnect);}
    catch(error){setNotice((error as Error).message);}
    finally{setBusy(false);}
  },[onStatus]);

  if(!status)return <section className="lan-page"><div className="lan-card lan-empty"><Wifi size={20}/><p>正在读取联机状态…</p></div></section>;
  if(!status.enabled)return <section className="lan-page">
    <header className="lan-head"><div><span className="lan-kicker">LAN LOBBY</span><h1>联机大厅</h1>
      <p>当前服务只监听本机回环地址，其他设备无法加入。</p></div></header>
    <div className="lan-card lan-off"><Wifi size={20}/><div>
      <h2>开启局域网联机</h2>
      <p>浏览器版：<code>python scripts/project.py run --lan</code></p>
      <p>桌面版：菜单「执行模式 → 局域网联机 / LAN lobby」，重启后主页会显示联机地址和 PIN。</p>
      <p>开启后：主机裁判在本机大厅选策略并开始；8 名操作手凭 PIN 各选一台地面机器人；其他设备直接打开地址观战。</p>
    </div></div>
  </section>;

  const lobby=status.lobby,session=status.session,host=session?.role==='host',operator=session?.role==='operator';
  const canSeat=host||operator;
  const red=lobby.seats.filter(seat=>seat.team==='red'),blue=lobby.seats.filter(seat=>seat.team==='blue');
  const robots=frame?.robots??[];
  const mine=(seat:LanSeat)=>!!session?.seat&&session.seat.team===seat.team&&session.seat.slot===seat.slot;
  const join=()=>run(()=>json<LanStatus>('/api/lan/join',{name:name.trim()||'操作手',pin,role:'operator'}),true);
  const leave=()=>run(()=>json<LanStatus>('/api/lan/leave'),true);
  const claim=(seat:LanSeat)=>run(()=>json<LanStatus>('/api/lan/seat',{action:'claim',team:seat.team,slot:seat.slot}));
  const releaseSeat=(seat:LanSeat,force=false)=>run(()=>json<LanStatus>('/api/lan/seat',{action:'release',team:seat.team,slot:seat.slot,force}));
  const ready=()=>run(()=>json<LanStatus>('/api/lan/ready',{ready:!session?.ready}));
  const saveConfig=(patch:Partial<{season:Season;red:string;blue:string;seed:number;duration:number}>)=>run(()=>json<LanStatus>('/api/lan/config',{
    season:patch.season??lobby.config.season,red:patch.red??lobby.config.red,blue:patch.blue??lobby.config.blue,
    seed:patch.seed??lobby.config.seed,duration:patch.duration??lobby.config.duration}));
  const start=()=>run(async()=>{await json('/api/lan/start');return statusNow();});
  const control=(command:string,extra:Record<string,unknown>={})=>run(async()=>{await json('/api/lan/control',{command,...extra});return statusNow();});
  const referee=(kind:string,robot?:string,team?:TeamId)=>run(async()=>{
    await json('/api/lan/referee',{kind,...(robot?{robot}:{}),...(team?{team}:{})});return statusNow();});
  const copy=async()=>{
    const text=`${status.urls[0]||location.origin}  联机 PIN ${status.pin||''}`.trim();
    try{await navigator.clipboard.writeText(text);setNotice('联机地址与 PIN 已复制');}
    catch{setNotice(text);}
  };
  const seatCard=(seat:LanSeat)=>{
    const taken=!!seat.session,isMine=mine(seat),other=taken&&!isMine;
    return <div key={`${seat.team}-${seat.slot}`} className={`lan-seat ${seat.team} ${taken?'taken':''} ${isMine?'mine':''}`}>
      <b>{seat.team==='red'?'R':'B'}{String(seat.slot).padStart(2,'0')}</b>
      <span>{ROLE_NAMES[seat.role]}</span>
      {isMine?<button disabled={busy} onClick={()=>releaseSeat(seat)}>取消</button>
        :canSeat&&!taken?<button disabled={busy} onClick={()=>claim(seat)}>选择</button>
        :host&&other?<button disabled={busy} onClick={()=>releaseSeat(seat,true)}>收回</button>:<i/>}
      <em>{taken?<>{seat.name}{seat.ready?' · 已准备':''}{seat.online?'':' · 离线'}</>:'空闲'}</em>
    </div>;
  };
  const choices=Object.entries(catalog).filter(([,entry])=>entry.season===lobby.config.season&&
    ['team','squad','distributed'].includes(entry.mode));
  for(const key of [lobby.config.red,lobby.config.blue])if(key&&!choices.some(([name])=>name===key))choices.push([key,{name:key,version:'',mode:'team'} as CatalogEntry]);
  const strategyOptions=choices.map(([key,entry])=><option key={key} value={key}>{entry.display_name||entry.name||key}</option>);
  const paused=!!live?.paused,running=lobby.phase==='running';

  return <section className="lan-page">
    <header className="lan-head">
      <div>
        <span className="lan-kicker">LAN LOBBY · 5V5</span>
        <h1>联机大厅</h1>
        <p>{running?'比赛进行中':lobby.phase==='finished'?'上一场已结束，主机可开始下一场':'等待主机裁判开始比赛'}
          {' · '}观众 {lobby.spectators}{' · '}操作手 {lobby.operators}</p>
      </div>
      <div className="lan-head-actions">
        {latency!==null&&<span className="lan-ping">{latency.toFixed(0)} ms</span>}
        <button className="lan-primary" onClick={onEnter}><Play size={14}/>进入战场</button>
      </div>
    </header>
    {notice&&<div className="lan-notice" role="status">{notice}</div>}
    <div className="lan-grid">
      <div className="lan-column">
        {!session&&<div className="lan-card">
          <h2><Wifi size={16}/>加入联机</h2>
          <p>操作手需要主机显示的 6 位 PIN；只想看比赛可以直接进入战场。</p>
          <div className="lan-join-row">
            <input value={name} maxLength={24} placeholder="你的名字" onChange={event=>setName(event.target.value)}/>
            <input value={pin} maxLength={8} inputMode="numeric" placeholder="联机 PIN" onChange={event=>setPin(event.target.value)}/>
            <button disabled={busy||!pin.trim()} onClick={join}>以操作手加入</button>
            <button disabled={busy} onClick={onEnter}>只观战</button>
          </div>
        </div>}
        {session&&<div className="lan-card lan-you">
          <h2><Users size={16}/>{ROLE_LABEL[session.role]} · {session.name}</h2>
          <p>{session.seat?`席位：${session.seat.team==='red'?'红方':'蓝方'} ${session.seat.slot} 号`:'尚未选择机体'}</p>
          <div className="lan-actions">
            {session.seat&&<button disabled={busy} onClick={ready}>{session.ready?<><Check size={14}/>已准备</>:<><Check size={14}/>准备</>}</button>}
            {session.role!=='host'&&<button disabled={busy} onClick={leave}><LogOut size={14}/>退出联机</button>}
          </div>
        </div>}
        <div className="lan-card">
          <h2><Radio size={16}/>操作手席位</h2>
          <div className="lan-teams">
            <div><h3>红方 · RED</h3>{red.map(seatCard)}</div>
            <div><h3>蓝方 · BLUE</h3>{blue.map(seatCard)}</div>
          </div>
          <p className="lan-muted">地面机器人可驾驶；空中机器人由自动飞行系统控制，不占操作手席位。2027 赛季共 8 个席位。</p>
        </div>
      </div>
      <div className="lan-column">
        {host&&<div className="lan-card">
          <h2><Wifi size={16}/>联机信息</h2>
          {status.urls.length?status.urls.map(url=><code key={url}>{url}</code>):<p>未检测到局域网地址：请用 <code>--lan</code> 启动，并确认主机已连接局域网。</p>}
          {status.pin&&<p>联机 PIN <b className="lan-pin">{status.pin}</b></p>}
          <button disabled={busy} onClick={copy}><Copy size={14}/>复制地址与 PIN</button>
          <p className="lan-muted">观众直接打开地址；操作手输入 PIN 后选择红/蓝方地面机器人。</p>
        </div>}
        {host?<div className="lan-card">
          <h2><Crown size={16}/>主机裁判 · 比赛设置</h2>
          <div className="lan-config">
            <label>赛季
              <select value={lobby.config.season} disabled={busy||running} onChange={event=>{
                const season=event.target.value as Season;
                if(season!==lobby.config.season&&!window.confirm('切换赛季会释放所有席位，继续？'))return;
                void saveConfig({season});
              }}><option value="2027">RMUC 2027 · 5v5</option><option value="2026">RMUC 2026 · 6v6</option></select>
            </label>
            <label>红方策略<select value={lobby.config.red} disabled={busy||running} onChange={event=>void saveConfig({red:event.target.value})}>{strategyOptions}</select></label>
            <label>蓝方策略<select value={lobby.config.blue} disabled={busy||running} onChange={event=>void saveConfig({blue:event.target.value})}>{strategyOptions}</select></label>
            <label>时长
              <select value={lobby.config.duration} disabled={busy||running} onChange={event=>void saveConfig({duration:Number(event.target.value)})}>
                {[420,300,180,60].map(value=><option key={value} value={value}>{value} 秒</option>)}
              </select>
            </label>
            <label>种子
              <input type="number" defaultValue={lobby.config.seed} disabled={busy||running} onBlur={event=>{
                const seed=Math.trunc(Number(event.target.value));
                if(Number.isFinite(seed)&&seed!==lobby.config.seed)void saveConfig({seed});
              }}/>
            </label>
          </div>
          <div className="lan-actions">
            <button className="lan-primary" disabled={busy||running} onClick={start}><Play size={14}/>{lobby.phase==='finished'?'再来一局':'开始比赛'}</button>
            {running&&<>
              <button disabled={busy} onClick={()=>control('pause')}>{paused?<><Play size={14}/>继续</>:<><Pause size={14}/>暂停</>}</button>
              <button disabled={busy} onClick={()=>control('stop')}><Square size={14}/>结束</button>
              <select disabled={busy} value={live?.speed??1} onChange={event=>void control('speed',{speed:Number(event.target.value)})}>
                {[.5,1,2,4,8].map(value=><option key={value} value={value}>{value}× 速度</option>)}
              </select>
              {!!live?.prematch&&<button disabled={busy} onClick={()=>control('skip_prematch')}>跳过赛前</button>}
            </>}
          </div>
          <p className="lan-muted">人类驾驶的比赛不计策略 Elo。未选择席位的机体仍由策略控制。</p>
        </div>:<div className="lan-card"><h2><Crown size={16}/>主机裁判</h2>
          <p>比赛设置、开始/暂停和判罚由主机裁判控制。</p>
          <p>{running?'比赛进行中，点击右上角「进入战场」观战。':'等待主机裁判开始比赛。'}</p>
        </div>}
        {host&&<div className="lan-card">
          <h2><Shield size={16}/>裁判判罚</h2>
          <div className="lan-join-row">
            <select value={target} onChange={event=>setTarget(event.target.value)} disabled={busy}>
              <option value="">选择机体</option>
              {robots.map(robot=><option key={robot.id} value={robot.id}>{robot.team==='red'?'红':'蓝'}{robot.slot} · {ROLE_NAMES[robot.role]}</option>)}
            </select>
            <button disabled={busy||!target||!running} onClick={()=>void referee('yellow',target)}>黄牌</button>
            <button disabled={busy||!target||!running} onClick={()=>void referee('red',target)}>红牌</button>
            <button disabled={busy||!running} onClick={()=>void referee('yellow_both')}>双方黄牌</button>
          </div>
          <div className="lan-join-row">
            <select value={forfeitTeam} onChange={event=>setForfeitTeam(event.target.value as TeamId)} disabled={busy}>
              <option value="red">红方判负</option><option value="blue">蓝方判负</option>
            </select>
            <button disabled={busy||!running} onClick={()=>void referee('forfeit',undefined,forfeitTeam)}>判负</button>
          </div>
        </div>}
      </div>
    </div>
  </section>;
}
