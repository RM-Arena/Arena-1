import {strategyName} from './strategyIdentity';
import {useEffect,useId,useState,type CSSProperties} from 'react';
import {ROLE_NAMES,type Arena,type Showcase,type StrategySummary,type StrategyTag,type StyleKey,type Tactic,type TeamId} from './types';
import './gallery.css';

// Visual pieces of a strategy's showcase.json (docs/STRATEGY_SHOWCASE.md): style radar, 7-minute phase timeline and tactical map.
export type Focus=Showcase['phases'][number]['focus'];
export type ShowcaseUnit=Showcase['units'][number];
// Clockwise from the top, so opposite traits face each other: 进攻↔防守, 目标↔协同, 经济↔应变.
export const STYLE_AXES:[StyleKey,string][]=[['aggression','进攻'],['objective','目标'],['economy','经济'],['defense','防守'],['teamwork','协同'],['adaptability','应变']];
export const FOCUS:Record<Focus,{label:string;color:string}>={attack:{label:'进攻',color:'#ff7a45'},defense:{label:'防守',color:'#4c9dff'},economy:{label:'经济',color:'#f2c35b'},objective:{label:'目标',color:'#b07cff'},support:{label:'支援',color:'#3fd0b8'}};
export const TACTICS:Record<Tactic,{short:string;name:string;color:string;focus:Focus;brief:string;style:Record<StyleKey,number>}>={
  balanced:{short:'均衡',name:'均衡推进',color:'#9fc3d6',focus:'support',brief:'攻守兼顾，按局势逐步推进，不押注单一目标。',style:{aggression:55,defense:55,economy:55,objective:55,teamwork:55,adaptability:62}},
  assault:{short:'突击',name:'正面突击',color:'#ff7a45',focus:'attack',brief:'主动压上交战，用击杀和火力压制打开局面。',style:{aggression:86,defense:30,economy:40,objective:66,teamwork:55,adaptability:48}},
  siege:{short:'攻坚',name:'攻坚拆塔',color:'#b07cff',focus:'objective',brief:'集中火力拆除前哨站与基地，以建筑血量定胜负。',style:{aggression:66,defense:38,economy:48,objective:92,teamwork:62,adaptability:44}},
  guard:{short:'防守',name:'稳守反击',color:'#4c9dff',focus:'defense',brief:'守住己方前哨与基地，拦截来犯之敌后再伺机反击。',style:{aggression:30,defense:88,economy:50,objective:40,teamwork:60,adaptability:55}},
  economy:{short:'经济',name:'经济科技',color:'#f2c35b',focus:'economy',brief:'优先资源、科技装配与能量机关，以经济优势拖垮对手。',style:{aggression:35,defense:55,economy:90,objective:52,teamwork:56,adaptability:50}},
};
export const TAGS:Record<StrategyTag,string>={rune:'能量机关',assembly:'科技装配',rescue:'救援复活',aerial:'空中支援',sniping:'远程狙击',mobility:'高机动',comms:'通信协同',focus_fire:'集火',outpost_rush:'速推前哨',base_rush:'直取基地'};
const TAG_STYLE:Record<StrategyTag,Partial<Record<StyleKey,number>>>={rune:{objective:8,economy:6},assembly:{economy:12},rescue:{teamwork:10,defense:4},aerial:{teamwork:6,adaptability:4},sniping:{objective:8,aggression:4},mobility:{adaptability:12},comms:{teamwork:14},focus_fire:{aggression:8,teamwork:8},outpost_rush:{objective:10,aggression:6},base_rush:{aggression:10,objective:10}};
export const UNIT_COLORS=['#f2c35b','#5fe0b6','#7fdcf0','#c792ff','#ff9d66','#ff7eb6','#b5e35a','#6fa8ff','#ffd98a','#4fd1c5','#e59cff','#ffb38a','#9be7ff','#d4f07a','#ff8f8f','#a3b8ff'];
export const clock=(s:number)=>`${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,'0')}`;

// The classification wins over the preset id, except that an unclassified preset keeps its own tactic.
export function tacticOf(s:Pick<StrategySummary,'profile'|'preset'>):Tactic{const t=s.profile?.tactic||'balanced';return t==='balanced'&&s.preset?.id?s.preset.id:t;}
export function strategyTitle(s:StrategySummary){return strategyName(s.profile?.display_name||s.display_name||s.showcase?.title||(s.preset&&s.model_name?`${s.model_name} · ${s.preset.name}`:s.name));}
export function fallbackStyle(s:Pick<StrategySummary,'profile'|'preset'>){
  const style={...TACTICS[tacticOf(s)].style};
  for(const tag of s.profile?.tags||[])for(const [k,v] of Object.entries(TAG_STYLE[tag]||{}))style[k as StyleKey]=Math.min(100,style[k as StyleKey]+(v||0));
  return style;
}
// A plausible card when the author shipped no showcase.json: tactic → radar, preset/profile text → summary, one phase. No routes are invented.
export function fallbackShowcase(s:StrategySummary):Showcase{
  const meta=TACTICS[tacticOf(s)],summary=s.profile?.description||s.preset?.description||meta.brief,single=s.mode==='adaptive'||s.mode==='robot';
  return {format:'rmuc-showcase-v1',title:strategyTitle(s),tagline:s.preset?.description||(s.profile?.description||meta.brief).slice(0,80),summary,style:fallbackStyle(s),
    phases:[{from:0,to:420,title:meta.name,goal:summary,focus:meta.focus}],units:single?[{name:'本机',role:s.model_name||(s.role?ROLE_NAMES[s.role]:'单机'),task:summary,route:[]}]:[],rules:[],priorities:[],strengths:[],weaknesses:[]};
}

// ---------------------------------------------------------------- radar
export function StyleRadar({style,size=260,thumb=false,color='#e7b971',auto=false,className=''}:{style:Record<StyleKey,number>;size?:number;thumb?:boolean;color?:string;auto?:boolean;className?:string}){
  const pad=thumb?3:size*.2,r=size/2-pad,c=size/2;
  const pt=(i:number,v:number)=>{const a=-Math.PI/2+i*Math.PI/3;return [c+Math.cos(a)*r*v,c+Math.sin(a)*r*v];};
  const ring=(v:number)=>STYLE_AXES.map((_,i)=>pt(i,v).map(n=>n.toFixed(1)).join(',')).join(' ');
  const value=(k:StyleKey)=>Math.max(0,Math.min(100,Number(style?.[k])||0));
  const shape=STYLE_AXES.map(([k],i)=>pt(i,Math.max(.04,value(k)/100)).map(n=>n.toFixed(1)).join(',')).join(' ');
  return <svg className={`sg-radar ${thumb?'thumb':''} ${auto?'auto':''} ${className}`.trim()} viewBox={`0 0 ${size} ${size}`} width={size} height={size} role="img" aria-label={`战术风格：${STYLE_AXES.map(([k,l])=>`${l} ${value(k)}`).join('，')}${auto?'（自动推断）':''}`} style={{'--rc':color} as CSSProperties}>
    {(thumb?[.5,1]:[.25,.5,.75,1]).map(v=><polygon key={v} className={`sg-radar-ring ${v===1?'outer':''}`} points={ring(v)}/>)}
    {STYLE_AXES.map((_,i)=>{const [x,y]=pt(i,1);return <line key={i} className="sg-radar-spoke" x1={c} y1={c} x2={x} y2={y}/>;})}
    <polygon className="sg-radar-shape" points={shape} style={{transformOrigin:`${c}px ${c}px`}}/>
    {!thumb&&STYLE_AXES.map(([k,label],i)=>{
      const [dx,dy]=pt(i,Math.max(.04,value(k)/100)),[lx,ly]=pt(i,1.17),cos=Math.cos(-Math.PI/2+i*Math.PI/3),sin=Math.sin(-Math.PI/2+i*Math.PI/3);
      const anchor=cos>.3?'start':cos<-.3?'end':'middle',top=sin<-.5?-14:sin>.5?16:0;
      return <g key={k}><circle className="sg-radar-dot" cx={dx} cy={dy} r={size/80+1.5}/><text className="sg-radar-label" x={lx} y={ly+top} textAnchor={anchor}>{label}</text><text className="sg-radar-value" x={lx} y={ly+top+size*.065} textAnchor={anchor}>{value(k)}</text></g>;})}
  </svg>;
}

// ---------------------------------------------------------------- timeline
export function PhaseTimeline({phases,total=420}:{phases:Showcase['phases'];total?:number}){
  const [hot,setHot]=useState<number|null>(null);
  return <div className="sg-timeline" onMouseLeave={()=>setHot(null)}>
    <div className="sg-tl-track">
      <div className="sg-tl-bar">{phases.map((p,i)=><div key={i} className={`sg-tl-seg ${hot===i?'hot':hot!==null?'dim':''}`} style={{left:`${p.from/total*100}%`,width:`${(p.to-p.from)/total*100}%`,'--fc':FOCUS[p.focus]?.color??FOCUS.support.color,animationDelay:`${i*90}ms`} as CSSProperties} onMouseEnter={()=>setHot(i)} title={`${clock(p.from)}–${clock(p.to)} ${p.title}`}><b>{i+1}</b><span>{p.title}</span></div>)}</div>
      <div className="sg-tl-ticks" aria-hidden="true">{Array.from({length:Math.floor(total/60)+1},(_,m)=><span key={m} className={m%2?'odd':''} style={{left:`${m*60/total*100}%`}}><i/>{m}:00</span>)}</div>
    </div>
    <ol className="sg-tl-phases">{phases.map((p,i)=><li key={i} className={hot===i?'hot':''} style={{'--fc':FOCUS[p.focus]?.color??FOCUS.support.color} as CSSProperties} onMouseEnter={()=>setHot(i)} tabIndex={0} onFocus={()=>setHot(i)} onBlur={()=>setHot(null)}>
      <div className="sg-tl-meta"><b>{String(i+1).padStart(2,'0')}</b><span>{clock(p.from)} – {clock(p.to)}</span><em>{FOCUS[p.focus]?.label??p.focus}</em></div><h4>{p.title}</h4><p>{p.goal}</p></li>)}</ol>
  </div>;
}

// ---------------------------------------------------------------- tactical map
// /api/maps returns the engine arena, which also carries base/outpost points; the spec landmarks are the fallback.
export type MapData=Arena&{bases?:Record<TeamId,number[]>;outposts?:Record<TeamId,number[]>};
let arenaRequest:Promise<Record<string,MapData>|null>|null=null;
// Routes are drawn on the field of the strategy's season (RMUC 2027 by default).
export function useArena(season:'2026'|'2027'='2027'){
  const [arena,setArena]=useState<MapData|null>(null);
  useEffect(()=>{let live=true;arenaRequest??=fetch('/api/maps').then(r=>r.ok?r.json():null).catch(()=>null);
    const request=arenaRequest;request.then(maps=>{if(!maps&&arenaRequest===request)arenaRequest=null;if(live)setArena((maps?.[season==='2026'?'rmuc2026':'rmuc2027']??null) as MapData|null);});return()=>{live=false;};},[season]);
  return arena;
}
const S=40,FIELD_W=28,FIELD_H=15;
const P=(p:number[])=>`${(p[0]*S).toFixed(1)},${(p[1]*S).toFixed(1)}`;
function hexagon(cx:number,cy:number,r:number){return [0,1,2,3,4,5].map(k=>`${(cx+r*Math.cos(k*Math.PI/3+Math.PI/6)).toFixed(1)},${(cy+r*Math.sin(k*Math.PI/3+Math.PI/6)).toFixed(1)}`).join(' ');}
export function TacticalMap({units,arena,focus,onFocus,note}:{units:ShowcaseUnit[];arena:MapData|null;focus:number|null;onFocus?:(i:number|null)=>void;note?:string}){
  const id='sgm'+useId().replace(/[^\w-]/g,''),W=FIELD_W*S,H=FIELD_H*S;
  const bases=arena?.bases??{red:[2.4,7.5],blue:[25.6,7.5]},outposts=arena?.outposts??{red:[11,11.4],blue:[17,3.6]},rune=arena?.rune?[arena.rune.x,arena.rune.y]:[14,7.5];
  const terrain=[...(arena?.terrain||[])].sort((a,b)=>a.elevation-b.elevation);
  const label=(x:number,y:number,text:string,cls='')=><text className={`sg-map-label ${cls}`} x={x*S} y={y*S} textAnchor="middle">{text}</text>;
  return <svg className="sg-map" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`战术地图（己方视角，己方基地在左）：${units.map(u=>u.name).join('、')||'无路线'}`}>
    <defs>
      <pattern id={`${id}g`} width={S} height={S} patternUnits="userSpaceOnUse"><path d={`M${S} 0H0V${S}`} className="sg-map-grid"/></pattern>
      <pattern id={`${id}b`} width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="8" height="8" fill="#26343f"/><line x1="0" y1="0" x2="0" y2="8" stroke="#3a4b58" strokeWidth="3"/></pattern>
      <linearGradient id={`${id}s`} x1="0" x2="1"><stop offset="0" stopColor="#ff4b55" stopOpacity=".2"/><stop offset=".46" stopColor="#ff4b55" stopOpacity="0"/><stop offset=".54" stopColor="#3aa0ff" stopOpacity="0"/><stop offset="1" stopColor="#3aa0ff" stopOpacity=".2"/></linearGradient>
      {units.map((_,i)=><marker key={i} id={`${id}a${i}`} viewBox="0 0 10 10" refX="6" refY="5" markerWidth="4" markerHeight="4" orient="auto" markerUnits="strokeWidth"><path d="M0 0L10 5L0 10L2.5 5z" fill={UNIT_COLORS[i%UNIT_COLORS.length]}/></marker>)}
    </defs>
    <rect width={W} height={H} className="sg-map-bg"/><rect width={W} height={H} fill={`url(#${id}s)`}/><rect width={W} height={H} fill={`url(#${id}g)`}/>
    <g className="sg-map-terrain" aria-hidden="true">
      {terrain.map((t,i)=>{const fill=t.kind==='bumps'?`url(#${id}b)`:`hsl(205 20% ${(13+Math.min(1,t.elevation)*15).toFixed(1)}%)`,cls=`sg-t ${t.kind}`;
        return t.polygon?<polygon key={i} className={cls} points={t.polygon.map(P).join(' ')} fill={fill}/>:<rect key={i} className={cls} x={t.x*S} y={t.y*S} width={t.w*S} height={t.h*S} fill={fill}/>;})}
      {(arena?.obstacles||[]).map((w,i)=><rect key={i} className="sg-map-wall" x={w.x*S} y={w.y*S} width={Math.max(2,w.w*S)} height={Math.max(2,w.h*S)} transform={`rotate(${((w.rotation||0)*180/Math.PI).toFixed(2)} ${((w.x+w.w/2)*S).toFixed(1)} ${((w.y+w.h/2)*S).toFixed(1)})`}/>)}
      <line className="sg-map-mid" x1={W/2} y1={0} x2={W/2} y2={H}/>
      {(['red','blue'] as const).map(t=><g key={t} className={`sg-map-mark ${t}`}><polygon points={hexagon(bases[t][0]*S,bases[t][1]*S,30)}/><rect x={outposts[t][0]*S-11} y={outposts[t][1]*S-11} width="22" height="22" transform={`rotate(45 ${outposts[t][0]*S} ${outposts[t][1]*S})`}/></g>)}
      <g className="sg-map-rune"><circle cx={rune[0]*S} cy={rune[1]*S} r="22"/><circle cx={rune[0]*S} cy={rune[1]*S} r="7"/></g>
      <text className="sg-map-label red" transform={`translate(${.62*S} ${bases.red[1]*S}) rotate(-90)`} textAnchor="middle">己方基地</text><text className="sg-map-label blue" transform={`translate(${(FIELD_W-.62)*S} ${bases.blue[1]*S}) rotate(90)`} textAnchor="middle">敌方基地</text>
      {label(outposts.red[0],outposts.red[1]+1.05,'己方前哨','red')}{label(outposts.blue[0],outposts.blue[1]-.72,'敌方前哨','blue')}{label(rune[0],rune[1]+1.12,'能量机关')}
    </g>
    {units.map((u,i)=>{const color=UNIT_COLORS[i%UNIT_COLORS.length],route=u.route||[],end=u.anchor||route[route.length-1],state=focus===null?'':focus===i?'on':'off';
      return <g key={i} className={`sg-route ${state}`} style={{'--uc':color} as CSSProperties} onMouseEnter={onFocus&&(()=>onFocus(i))} onMouseLeave={onFocus&&(()=>onFocus(null))}>
        {route.length>1&&<><polyline className="sg-route-glow" points={route.map(P).join(' ')}/><polyline className="sg-route-line" points={route.map(P).join(' ')} markerEnd={`url(#${id}a${i})`}/><polyline className="sg-route-flow" points={route.map(P).join(' ')}/>
          {route.slice(1).map((b,k)=>{const a=route[k],len=Math.hypot(b[0]-a[0],b[1]-a[1]);if(len<2.2||k===route.length-2&&len<4)return null;const deg=Math.atan2(b[1]-a[1],b[0]-a[0])*180/Math.PI;
            return <path key={k} className="sg-route-chev" d="M-7 -7L3 0L-7 7" transform={`translate(${((a[0]+b[0])/2*S).toFixed(1)} ${((a[1]+b[1])/2*S).toFixed(1)}) rotate(${deg.toFixed(1)})`}/>;})}</>}
        {route[0]&&<circle className="sg-route-start" cx={route[0][0]*S} cy={route[0][1]*S} r="7"/>}
        {u.anchor&&<circle className="sg-anchor-pulse" cx={u.anchor[0]*S} cy={u.anchor[1]*S} r="15"/>}
        {end&&<g className={`sg-unit-pin ${u.anchor?'anchor':''}`} transform={`translate(${(end[0]*S).toFixed(1)} ${(end[1]*S).toFixed(1)})`}><circle r={u.anchor?15:12}/><text y="1" textAnchor="middle" dominantBaseline="central">{i+1}</text></g>}
      </g>;})}
    {note&&<g className="sg-map-note"><rect x={W/2-230} y={H-92} width="460" height="60" rx="30"/><text x={W/2} y={H-61} textAnchor="middle" dominantBaseline="central">{note}</text></g>}
  </svg>;
}
