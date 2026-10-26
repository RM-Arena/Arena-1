import {BattleSettings} from './BattleSettings';
import {StrategyMatchmaker} from './StrategyMatchmaker';
import {registeredLineup,strategySeason} from './strategyMatchup';
import {version as APP_VERSION} from '../../package.json';
import {strategyDisplayName,strategyName,canonicalStrategyKey} from './strategyIdentity';
import {MatchHistory} from './MatchHistory';
import {deleteMatchRecords} from './matchSelection';
import {matchEventKey,policyErrorText} from './matchDiagnostics';
import {strategyLabel,summarizeDeck} from './deckCatalog';
import {DEFAULT_FREE_CONTROLLERS,freeStartOptions,isFreeBattle,type FreeControllers} from './freeBattle';
import {Home} from './Home';
import {Training,type TrainingMode} from './Training';
import {AudioControls} from './AudioControls';
import {CameraControls,CAMERA_MODES} from './CameraControls';
import {useInterfaceFeedback} from './interfaceFeedback';
import './interaction.css';
import {TeamLineupDialog,DEFAULT_LINEUPS,legalIn,sameLineup,validLineup} from './TeamLineup';
import {SEASON_LABELS,SEASON_SLOTS,frameSeason,seasonOfMap,type RobotHardware,type Season,type TeamLineup} from './types';
import {Suspense,lazy,useCallback,useEffect,useMemo,useRef,useState,useSyncExternalStore,type ChangeEvent,type CSSProperties} from 'react';
import {Home as HomeIcon,GraduationCap,LibraryBig,Palette,Settings2,Activity,ArrowDownToLine,ArrowUpFromLine,ChevronDown,Code2,Crosshair,Eye,History,Layers3,Maximize2,Minimize2,Pause,Play,Radio,RotateCw,Shield,Square,Target,Trophy,Video,Volume2,VolumeX,X,Zap} from 'lucide-react';
import {ArenaScene} from './ArenaScene';
import {DeckBuilder} from './DeckBuilder';
import {UploadWizard} from './UploadWizard';
import {ModelWorkshop,SkinPicker,type CustomModel} from './ModelWorkshop';
import {introAt,introMinimumSeconds,introSchedule,introSeconds,type IntroCut} from './intro';
import {applySkins} from './customModels';
import type {IntroShot} from './ArenaScene';
import {DeleteMatchDialog} from './DeleteMatchDialog';
import {TelemetryPanel} from './TelemetryPanel';
import {ArenaAudio,BroadcastRecorder,clock,download} from './media';
import {RecordingSession} from './recording';
import {RecordingDock} from './RecordingDock';
import {audibleEvents,broadcastMusicCue} from './audioPlaylist';
import {BroadcastDirector,BroadcastHud} from './broadcast';
import {KillAnnouncement} from './KillAnnouncement';
import {HighlightHud,Highlights,MvpCard,Prematch,Results,StartFlash,Victory} from './ceremony';
import {MatchStats,mvp as pickMvp,statsFromFrames,verdict} from './matchStats';
import {robotImage} from './thumbnails';
import {MODE_LABELS,ROLE_NAMES,TEAM_COLORS,type CameraMode,type CatalogEntry,type Frame,type MatchEvent,type MatchRecord,type Metadata,type PilotView,type RenderFeed,type Replay,type Robot,type ServerState,type Standing,type TeamId} from './types';
import {PickRobotCard,LinkHoverCard,PlayerCockpit,SpectatorVitals} from './pilot';
import {CLIP_PREROLL,CLIP_SECONDS,CLIP_SECOND_SHOT,clipRival,highlightReel} from './highlights';
import {RobotPickShot} from './LineupIntro';

// The gallery and its visualisations load on first visit.
const StrategyGallery=lazy(()=>import('./StrategyGallery').then(m=>({default:m.StrategyGallery})));
async function api<T>(path:string,body?:unknown):Promise<T>{const response=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const value=await response.json();if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:value.error||'服务请求失败');return value;}
function eventText(e:MatchEvent){if(e.type==='yellow_card')return `${e.robot} 黄牌警告`;if(e.type==='yellow_both')return '双方黄牌警告';if(e.type==='red_card')return `${e.robot} 红牌罚下`;if(e.type==='overspeed')return `${e.robot} 超弹速锁定`;if(e.type==='launcher_speed_rejected')return `${e.robot} 非法硬件弹速，停止发射`;if(e.type==='base_armor_opened')return `${e.team==='red'?'红':'蓝'}方基地护甲展开`;if(e.type==='forfeit')return `${e.team==='red'?'红':'蓝'}方被判负`;if(e.type==='destroy')return `${e.killer} 击毁 ${e.robot}`;if(e.type==='capture'&&e.team)return `${e.team==='red'?'红':'蓝'}方控制 ${e.zone}`;if(e.type==='upgrade')return `${e.robot} 升级${{damage:'火力',armor:'装甲',mobility:'机动'}[e.branch||'damage']||e.branch}`;if(e.type==='overheat')return `${e.robot} 武器过热`;if(e.type==='policy_error')return policyErrorText(e);if(e.type==='invalid_action')return `${e.robot} 非法动作：${e.reason}`;if(e.type==='ammo_purchase')return `${e.robot} 兑换弹量`;if(e.type==='respawn')return e.instant?`${e.robot} 满血复活 · 花费 ${e.cost??'—'} 金币`:`${e.robot} 自然复活 · 10% 血量`;if(e.type==='level_up')return `${e.robot} 等级提升`;if(e.type==='assembly_success')return `${e.team} 完成科技核心装配`;if(e.type==='rune_activated')return `${e.team} 激活能量机关`;if(e.type==='outpost_rebuilt')return `${e.team} 重建前哨站`;if(e.type==='rescue_grip')return `${e.robot} 机械臂抓住 ${e.target}`;if(e.type==='rescue_complete')return `${e.robot} 扶正 ${e.target}`;if(e.type==='finish')return e.winner?`${e.winner==='red'?'红':'蓝'}方获胜`:'比赛结束';return '';}
// Replays open with the same lineup intro as live matches (its length depends on the robot count) and the 5 s countdown.
const PREROLL={countdown:5};
// A team strategy always runs the lineup it was developed on; every other mode runs the lineup
// chosen in the picker. Both sides may field different hardware, so this only sorts the list.
const usableFor=(entry:CatalogEntry,lineup:TeamLineup)=>!entry.team_lineup||sameLineup(entry.team_lineup,lineup);
type Post=null|'victory'|'results'|'mvp'|'highlight';
// Where the open replay came from, so export can re-read it; full matches are ~450 MB, so their text is never kept in memory.
type ReplaySource={id:string}|{file:File};

export function App(){
  const [page,setPage]=useState<'home'|'training'|'arena'|'gallery'|'history'|'leaderboard'|'settings'>('home'),[catalog,setCatalog]=useState<Record<string,CatalogEntry>>({}),[live,setLive]=useState<ServerState|null>(null),[connected,setConnected]=useState(false),[error,setError]=useState('');
  const [matchMode,setMatchMode]=useState<'standard'|'deck'>('standard'),[showDecks,setShowDecks]=useState(false),[robotCards,setRobotCards]=useState<Record<string,CatalogEntry>>({}),[deckSets,setDeckSets]=useState<Record<Season,Record<TeamId,string[]>>>(()=>{const load=(key:string)=>{try{const value=JSON.parse(localStorage.getItem(key)||'null');if(value&&['red','blue'].every(t=>Array.isArray(value[t])&&value[t].every((id:unknown)=>typeof id==='string')))return {red:value.red.map(canonicalStrategyKey),blue:value.blue.map(canonicalStrategyKey)};}catch{}return {red:[],blue:[]};};return {'2026':load('rmuc-decks-v1'),'2027':load('rmuc-decks-2027')};});
  useEffect(()=>{localStorage.setItem('rmuc-decks-v1',JSON.stringify(deckSets['2026']));localStorage.setItem('rmuc-decks-2027',JSON.stringify(deckSets['2027']));},[deckSets]);
  const [freeControllers,setFreeControllers]=useState<FreeControllers>(()=>{try{const v=JSON.parse(localStorage.getItem('rmuc-free-controllers-v1')||'null');if(v&&['red','blue'].every(t=>['team','independent'].includes(v[t]?.mode)&&typeof v[t]?.strategy==='string'))return {...v,red:{...v.red,strategy:canonicalStrategyKey(v.red.strategy)},blue:{...v.blue,strategy:canonicalStrategyKey(v.blue.strategy)}};}catch{}return structuredClone(DEFAULT_FREE_CONTROLLERS);});
  useEffect(()=>{localStorage.setItem('rmuc-free-controllers-v1',JSON.stringify(freeControllers));},[freeControllers]);
  const [models,setModels]=useState<Record<string,RobotHardware>>({}),[showTeamLineup,setShowTeamLineup]=useState(false),[lineups,setLineups]=useState<Record<Season,TeamLineup>>(()=>{const load=(key:string,season:Season)=>{try{const v=JSON.parse(localStorage.getItem(key)||'null');if(v&&Object.keys(v).length===SEASON_SLOTS[season].length&&SEASON_SLOTS[season].every(s=>Number.isInteger(v[String(s)])))return v;}catch{}return {...DEFAULT_LINEUPS[season]};};return {'2026':load('rmuc-team-lineup-v1','2026'),'2027':load('rmuc-team-lineup-2027','2027')};});
  useEffect(()=>{localStorage.setItem('rmuc-team-lineup-v1',JSON.stringify(lineups['2026']));localStorage.setItem('rmuc-team-lineup-2027',JSON.stringify(lineups['2027']));},[lineups]);
  const [trainingMode,setTrainingMode]=useState<TrainingMode>('team');
  // Uploaded robot appearances and the per-team choice by hardware model.
  const [customs,setCustoms]=useState<CustomModel[]>([]),[showSkins,setShowSkins]=useState(false),[galleryTab,setGalleryTab]=useState<'strategies'|'models'>('strategies'),[galleryKey,setGalleryKey]=useState(0);
  const [skins,setSkins]=useState<Record<TeamId,Record<string,string>>>(()=>{try{const v=JSON.parse(localStorage.getItem('rmuc-skins-v1')||'null');if(v&&['red','blue'].every(t=>v[t]&&typeof v[t]==='object'))return v;}catch{}return {red:{},blue:{}};});
  useEffect(()=>{try{localStorage.setItem('rmuc-skins-v1',JSON.stringify(skins));}catch{}},[skins]);
  const [bgmVolume,setBgmVolume]=useState(()=>{try{const v=Number(localStorage.getItem('rmuc-bgm-volume-v1')??'0.6');return Number.isFinite(v)?Math.max(0,Math.min(1,v)):.6;}catch{return .6;}});
  const [red,setRed]=useState('claude_opus55_xhigh_2027_team'),[blue,setBlue]=useState('claude_opus55_xhigh_2027_hold'),[seed,setSeed]=useState(42),[duration,setDuration]=useState(420),[map,setMap]=useState<'rmuc2027'|'rmuc2026'>(()=>{try{return localStorage.getItem('rmuc-map-v1')==='rmuc2026'?'rmuc2026':'rmuc2027';}catch{return 'rmuc2027';}});
  // RMUC 2027 is the default field; the selected map decides the season's roster, rules and legal models.
  useEffect(()=>{try{localStorage.setItem('rmuc-map-v1',map);}catch{}},[map]);
  const season=seasonOfMap(map),slots=SEASON_SLOTS[season],teamLineup=lineups[season];
  const setTeamLineup=(value:TeamLineup)=>setLineups(current=>({...current,[season]:value}));
  const decks=deckSets[season],setDecks=(value:Record<TeamId,string[]>)=>setDeckSets(current=>({...current,[season]:value}));
  const seasonCatalog=useMemo(()=>Object.fromEntries(Object.entries(catalog).filter(([,entry])=>(entry.season||'2026')===season)),[catalog,season]);
  // Every strategy of the season is selectable; ones matching the picker lineup are listed first,
  // because a team strategy runs its own locked lineup while other modes use the picker.
  const seasonChoices=useMemo(()=>{
    const all=Object.entries(seasonCatalog);
    const matched=all.filter(([,entry])=>usableFor(entry,teamLineup));
    const rest=all.filter(([,entry])=>!usableFor(entry,teamLineup));
    return [...matched,...rest];
  },[seasonCatalog,teamLineup]);
  const seasonCards=useMemo(()=>Object.fromEntries(Object.entries(robotCards).filter(([,entry])=>(entry.season||'2026')===season&&(!entry.robot||legalIn(models[String(entry.robot)],season)||!Object.keys(models).length))),[robotCards,models,season]);
  const seasonDefault=season==='2027'?['claude_opus55_xhigh_2027_team','claude_opus55_xhigh_2027_hold']:['claude_opus55_xhigh_team','claude_opus55_xhigh_hold'];
  const [camera,setCamera]=useState<CameraMode>('orbit'),[selected,setSelected]=useState('red-1'),[sound,setSound]=useState(true),[showSubmit,setShowSubmit]=useState(false),[post,setPostState]=useState<Post>(null);
  // The robot a human is driving first person; the strategy keeps flying the rest of the team.
  const [pilot,setPilot]=useState<string|null>(null),pilotView=useRef<PilotView|null>(null),pilotRef=useRef(false);pilotRef.current=!!pilot;
  // The cockpit panel doubles as the only way to change camera or release while piloting.
  const [pilotPanel,setPilotPanel]=useState(false);
  // Link Start: the cockpit panel docks to the right edge, the camera drops to the overhead field
  // and the field itself becomes the chassis picker. `linkPending` holds the chassis the pilot has
  // clicked until the confirmation plate is accepted.
  const [linkMode,setLinkMode]=useState(false),[linkHover,setLinkHover]=useState<string|null>(null),[linkPending,setLinkPending]=useState<string|null>(null);
  const linkPrevCamera=useRef<CameraMode>('orbit');
  // The battle HUD is drawn for a ~1000×520 stage, so the viewport publishes a proportional zoom:
  // a smaller window shrinks the whole overlay instead of leaving 420 px chips over a 600 px field.
  // A callback ref (not an effect) is used because the viewport only mounts with the arena frame.
  const viewportResize=useRef<ResizeObserver|null>(null);
  const viewportRef=useCallback((el:HTMLDivElement|null)=>{
    viewportResize.current?.disconnect();
    viewportResize.current=null;
    if(!el)return;
    const apply=()=>{
      const {width,height}=el.getBoundingClientRect();
      if(width<40||height<40)return;
      const scale=Math.min(1.25,Math.max(.55,Math.min(width/1000,height/520)));
      el.style.setProperty('--hud-zoom',scale.toFixed(3));
    };
    apply();
    const observer=new ResizeObserver(apply);
    observer.observe(el);
    viewportResize.current=observer;
  },[]);
  useEffect(()=>()=>viewportResize.current?.disconnect(),[]);
  const [images,setImages]=useState<Record<string,string>>({}),[preroll,setPreroll]=useState<{left:number}|null>(null),[startFlash,setStartFlash]=useState(0),[,setClockTick]=useState(0);
  const stats=useRef(new MatchStats()),director=useRef(new BroadcastDirector()),prerollRef=useRef<{left:number}|null>(null),prerollIntro=useRef(introSeconds(12)),postRef=useRef<Post>(null),requested=useRef(new Set<string>());
  // Every event of the current match, for the post-match highlight reel.
  const allEvents=useRef<MatchEvent[]>([]);
  // The reel is cut once per match, when the MVP card hands over.
  const [highlightClips,setHighlightClips]=useState<ReturnType<typeof highlightReel>>([]);
  // Reel playback: the clips are real moments, so each one is played out of the match's own replay
  // file instead of being drawn as a card. `reelReady` means the frames arrived and the field is
  // driving; without it the card version covers the screen.
  const reelRef=useRef<Replay|null>(null),reelClips=useRef<ReturnType<typeof highlightReel>>([]);
  // Where each clip starts inside the returned window sequence, so seeking is an index copy.
  const reelStarts=useRef<number[]>([]);
  const [reelReady,setReelReady]=useState(false),[reelIndex,setReelIndex]=useState(0),[reelPending,setReelPending]=useState(false);
  // Which side of a clip the camera is showing: the unit dealing the damage or the unit taking it.
  const [reelSide,setReelSide]=useState<'output'|'input'>('output');
  const [matches,setMatches]=useState<MatchRecord[]>([]),[pendingDelete,setPendingDelete]=useState<MatchRecord[]|null>(null),[standings,setStandings]=useState<Standing[]>([]),[log,setLog]=useState<MatchEvent[]>([]),[replay,setReplay]=useState<Replay|null>(null),[replayFrame,setReplayFrame]=useState<Frame|null>(null),[replayPlaying,setReplayPlaying]=useState(true),[replaySpeed,setReplaySpeed]=useState(1),[replayPosition,setReplayPosition]=useState(0);
  const feed=useRef<RenderFeed>({frame:null,previous:null,received:0,speed:1,paused:false,events:[],generation:'initial',replay:false});
  const liveRef=useRef<ServerState|null>(null),replayRef=useRef<Replay|null>(null),sourceRef=useRef<ReplaySource|null>(null),positionRef=useRef(0),playingRef=useRef(true),speedRef=useRef(1),seen=useRef(new Set<string>()),wsMessages=useRef(0),replayGeneration=useRef(0),replayScope=useRef(0),fileInput=useRef<HTMLInputElement>(null);
  const pageRef=useRef(page);pageRef.current=page;
  // A finished match the viewer has walked away from. Coming back to the arena shows the empty field of
  // the selected map (`previews`) instead of freezing on that match's last frame.
  const [dismissed,setDismissed]=useState<string|null>(null),[previews,setPreviews]=useState<Partial<Record<string,Frame>>>({}),idleRef=useRef(false);
  // Last time the snapshot reached React, for the render throttle in `accept`.
  const liveStamp=useRef(0);
  // Smoothed gap between live snapshots. The scene interpolates over this instead of the nominal
  // engine step, so a stream that runs slower than 20 Hz still moves the robots continuously.
  const livePace=useRef(50);
  // Static half of the live frame, sent once per match by the snapshot stream.
  const staticParts=useRef<{match_id:string|null;frame:unknown}>({match_id:null,frame:{}});
  const audio=useMemo(()=>new ArenaAudio(),[]),recorder=useMemo(()=>new BroadcastRecorder(audio),[audio]);
  // The capture and its save queue. A saved match recording refreshes the history it was filed in.
  const savedVideo=useRef(()=>{});
  const session=useMemo(()=>new RecordingSession(recorder,{onSaved:()=>savedVideo.current()}),[recorder]);
  const rec=useSyncExternalStore(session.subscribe,session.getSnapshot);
  const capturing=!!rec.capture||rec.starting,matchCapture=rec.capture?.kind==='match'?rec.capture:null,capturingMatch=!!matchCapture;
  // A start request in flight, so a double click cannot launch two matches.
  const [launching,setLaunching]=useState(false);
  const [saveMp4,setSaveMp4]=useState(()=>localStorage.getItem('rmuc-save-mp4')==='true'),[showMatchmaker,setShowMatchmaker]=useState(false),[videoMatch,setVideoMatch]=useState<string|null>(null);
  // Opting in shows the 3D join screen during the pre-match; opting out leaves the whole match to
  // the strategies. The choice is remembered across sessions.
  const [playerJoin,setPlayerJoin]=useState(()=>localStorage.getItem('rmuc-player-join')!=='false'),[joinHidden,setJoinHidden]=useState(false);
  useEffect(()=>{localStorage.setItem('rmuc-player-join',String(playerJoin));},[playerJoin]);
  // A new match brings the join screen back even if it was dismissed during the previous one.
  useEffect(()=>{setJoinHidden(false);},[live?.match_id]);
  // In the arena the right button is the aim assist, so the browser menu must never open over the
  // field, and a middle click must not start autoscroll. Capture phase, so no other handler can
  // let the default through first.
  useEffect(()=>{
    if(page!=='arena')return;
    const stop=(event:Event)=>event.preventDefault();
    const down=(event:MouseEvent)=>{if(event.button===1||event.button===2)event.preventDefault();};
    window.addEventListener('contextmenu',stop,true);
    window.addEventListener('auxclick',stop,true);
    window.addEventListener('selectstart',stop,true);
    window.addEventListener('dragstart',stop,true);
    window.addEventListener('mousedown',down,true);
    return()=>{window.removeEventListener('contextmenu',stop,true);window.removeEventListener('auxclick',stop,true);window.removeEventListener('selectstart',stop,true);window.removeEventListener('dragstart',stop,true);window.removeEventListener('mousedown',down,true);};
  },[page]);
  useEffect(()=>{localStorage.setItem('rmuc-save-mp4',String(saveMp4));},[saveMp4]);
  // Live save progress for the history rows of the matches being filed.
  const videoSaving=useMemo(()=>Object.fromEntries(rec.jobs.filter(j=>j.matchId&&j.stage!=='done').map(j=>[j.matchId,j.stage==='failed'?'MP4 保存失败 · 见右下角':j.stage==='queued'?'MP4 排队保存':`MP4 ${j.stage==='uploading'?'上传':'转码'} ${Math.floor((j.progress??0)*100)}%`])),[rec.jobs]);
  // Closing the window would lose a capture or a save that has not reached the disk yet.
  const recordingBusy=session.busy;
  useEffect(()=>{if(!recordingBusy)return;const warn=(e:BeforeUnloadEvent)=>{e.preventDefault();};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);},[recordingBusy]);

  useInterfaceFeedback(audio);
  useEffect(()=>{if(error)audio.ui('error');},[error,audio]);
  useEffect(()=>{
    if(!sound){audio.disable();return;}
    let active=true;
    const enable=()=>{void audio.enable().catch(e=>{if(active)setError((e as Error).message);});};
    // Autoplay may suspend Web Audio until a trusted user gesture; keep the user's sound preference on.
    const unlock=()=>{if(audio.context?.state==='suspended')enable();};
    enable();document.addEventListener('pointerdown',unlock,true);document.addEventListener('keydown',unlock,true);
    return()=>{active=false;document.removeEventListener('pointerdown',unlock,true);document.removeEventListener('keydown',unlock,true);};
  },[sound,audio]);
  useEffect(()=>{audio.setBgmVolume(bgmVolume);try{localStorage.setItem('rmuc-bgm-volume-v1',String(bgmVolume));}catch{}},[audio,bgmVolume]);
  useEffect(()=>{if(page!=='arena'){audio.drones(null);audio.cancelAnnouncements();director.current.highlight=null;}},[page,audio]);
  const setPost=useCallback((value:Post)=>{postRef.current=value;setPostState(value);},[]);
  // Post-match sequence: victory animation, then the data panel (which counts down into the MVP card).
  const finishShow=useCallback((f:Frame)=>{if(postRef.current)return;setPost(f.reason==='stopped'?'results':'victory');},[setPost]);
  const feedStats=useCallback((f:Frame,events:MatchEvent[])=>{stats.current.frame(f);stats.current.events(events);director.current.frame(f);
    const announcements=director.current.events(events,f);if(pageRef.current==='arena')for(const announcement of announcements)audio.announce(announcement,seconds=>director.current.announce(announcement,seconds));},[audio]);
  const resetBroadcast=useCallback(()=>{stats.current.reset();director.current.reset();audio.cancelAnnouncements();setStartFlash(0);},[audio]);
  const refreshCatalog=useCallback(()=>Promise.all([api<Record<string,CatalogEntry>>('/api/catalog'),api<Record<string,CatalogEntry>>('/api/robot-catalog'),api<{models:Record<string,RobotHardware>}>('/api/models'),api<CustomModel[]>('/api/custom-models')]).then(([teams,cards,hardware,uploaded])=>{setCatalog(teams);setRobotCards(cards);setModels(hardware.models);setCustoms(uploaded);setGalleryKey(k=>k+1);}).catch(e=>setError(e.message)),[]);
  const refreshHistory=useCallback(()=>Promise.all([api<MatchRecord[]>('/api/matches'),api<Standing[]>('/api/leaderboard')]).then(([m,s])=>{setMatches(m);setStandings(s);}).catch(e=>setError(e.message)),[]);
  savedVideo.current=()=>{void refreshHistory();audio.ui('success');};
  const collectEvents=useCallback((events:MatchEvent[])=>{const fresh=events.filter(e=>{const key=matchEventKey(e);if(seen.current.has(key))return false;seen.current.add(key);return true;});
    // The highlight reel is cut from every event of the match, not from the short display log
    // (which only keeps the ones with a caption), so raw hits and kills are kept here.
    if(fresh.length){const kept=allEvents.current;if(kept.length<40000)kept.push(...fresh);}if(pageRef.current==='arena')for(const event of audibleEvents(fresh))audio.play(event);const important=fresh.filter(e=>eventText(e));if(important.length)setLog(old=>[...important.reverse(),...old].slice(0,60));return fresh;},[audio]);
  const accept=useCallback((raw:ServerState)=>{
    // The snapshot stream carries the static half of the frame (arena geometry, hardware tables,
    // rule text) only once per match, so a slim frame is completed here and every reader below
    // still sees one whole frame.
    const cached=staticParts.current;
    const state:ServerState=!(raw.frame as Partial<Frame>).arena&&cached.match_id===raw.match_id
      ?{...raw,frame:{...raw.frame,...cached.frame as Record<string,unknown>} as Frame}:raw;
    applySkins(state.frame,state.metadata);
    const old=liveRef.current;liveRef.current=state;
    // The 3D view reads `feed` on every animation frame, so React only needs the latest snapshot a
    // dozen times a second; a changed match, pause or status still renders immediately.
    const stamp=performance.now();
    const urgent=!old||old.match_id!==state.match_id||old.frame.status!==state.frame.status
      ||old.paused!==state.paused||old.busy!==state.busy||old.prematch!==state.prematch||!!state.error;
    if(urgent||stamp-liveStamp.current>=(pilotRef.current?140:110)){liveStamp.current=stamp;setLive(state);}
    if(state.error)setError(state.error);
    if(replayRef.current)return;
    // The empty field stays until something new happens: a new match, or this one running again.
    if(idleRef.current&&!state.busy&&state.match_id===old?.match_id)return;
    if(state.match_id!==old?.match_id){seen.current.clear();allEvents.current=[];setLog([]);setPost(null);resetBroadcast();}
    const events=!old||state.match_id!==old.match_id?state.events.filter(e=>(e.time??e.tick*.05)>state.frame.time-.3):state.events;
    // Interpolate over the gap the stream actually keeps, not the engine's nominal step: the engine
    // publishes every 50 ms only when it keeps up, and a slower stream would leave the field frozen
    // between snapshots. The average is smoothed so one late packet does not speed the field up.
    const received=performance.now();
    if(old&&old.match_id===state.match_id&&!state.paused&&received-feed.current.received>4&&received-feed.current.received<600){
      livePace.current=livePace.current*.82+(received-feed.current.received)*.18;
    }else if(old?.match_id!==state.match_id)livePace.current=50;
    feed.current={frame:state.frame,previous:state.frame.tick>0&&old?.match_id===state.match_id?old.frame:null,received,speed:state.speed,paused:state.paused||state.frame.status!=='running',events,generation:'live:'+state.match_id,replay:false,pace:livePace.current};
    feedStats(state.frame,collectEvents(events));
    if(old?.prematch&&!state.prematch&&old.match_id===state.match_id&&state.busy){setStartFlash(performance.now());audio.countdown(0);}
    if(state.frame.status==='finished'&&old?.frame.status!=='finished'&&old?.match_id===state.match_id)finishShow(state.frame);
  },[collectEvents,feedStats,finishShow,resetBroadcast,setPost,audio]);
  useEffect(()=>{refreshCatalog();refreshHistory();api<ServerState>('/api/state').then(accept).catch(e=>setError(e.message));let socket:WebSocket|null=null,timer:number|undefined,disposed=false;
    const connect=()=>{socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/api/ws`);socket.onopen=()=>setConnected(true);socket.onmessage=e=>{const data=JSON.parse(e.data);if(data.type==='static'){staticParts.current=data.state;return;}if(data.type==='snapshot'){wsMessages.current++;accept(data.state);}};socket.onclose=()=>{setConnected(false);if(!disposed)timer=window.setTimeout(connect,1500);};socket.onerror=()=>socket?.close();};connect();
    return()=>{disposed=true;window.clearTimeout(timer);socket?.close();};
  },[accept,refreshCatalog,refreshHistory]);
  useEffect(()=>{if(live?.strategy_version)void refreshCatalog();},[live?.strategy_version,refreshCatalog]);
  useEffect(()=>{if(live?.frame.status==='finished'&&!live.busy)refreshHistory();},[live?.frame.status,live?.busy,refreshHistory]);
  useEffect(()=>{let id:number,last=performance.now(),lastIndex=-1,generation=replayGeneration.current,pending:MatchEvent[]=[];const animate=(now:number)=>{const elapsed=now-last,dt=Math.min(.1,elapsed/1000);last=now;const data=replayRef.current;
    if(generation!==replayGeneration.current){generation=replayGeneration.current;lastIndex=Math.floor(positionRef.current);pending=[];}
    // The pre-roll keeps its own clock that only runs while playing and rendering, like the replay itself.
    if(data){if(prerollRef.current&&playingRef.current)prerollRef.current.left-=elapsed/1000;const rolling=prerollRef.current&&prerollRef.current.left>0;if(prerollRef.current&&!rolling){prerollRef.current=null;setPreroll(null);setStartFlash(now);audio.countdown(0);}
      if(playingRef.current&&!rolling)positionRef.current=Math.min(data.frames.length-1,positionRef.current+dt*speedRef.current/(data.metadata.dt||.05));const index=Math.floor(positionRef.current),f=data.frames[index];if(index!==lastIndex){const span=playingRef.current&&lastIndex>=0&&index>lastIndex?data.frames.slice(lastIndex+1,index+1):null,skipped=span?span.flatMap(f=>f.events):null;if(skipped)collectEvents(skipped);if(span)for(const g of span)feedStats(g,g.events);pending=skipped&&index>lastIndex&&index-lastIndex<=12?skipped:f.events;setReplayFrame(f);setReplayPosition(positionRef.current);lastIndex=index;}
      if(index===data.frames.length-1&&playingRef.current){playingRef.current=false;setReplayPlaying(false);if(f.status==='finished')finishShow(f);}
      feed.current={frame:f,previous:data.frames[Math.max(0,index-1)],received:now,speed:speedRef.current,paused:!playingRef.current,events:pending,generation:'replay:'+data.metadata.match_id+':'+data.metadata.seed+':'+replayGeneration.current,replay:true,alpha:positionRef.current%1};
    }else lastIndex=-1;id=requestAnimationFrame(animate);};id=requestAnimationFrame(animate);return()=>cancelAnimationFrame(id);
  },[collectEvents,feedStats,finishShow,audio]);
  const onCanvas=useCallback((canvas:HTMLCanvasElement)=>{recorder.source=canvas;},[recorder]);
  const onRender=useCallback(()=>{recorder.announcement=director.current.highlight;if(feed.current.frame)recorder.draw(feed.current.frame,replayRef.current?.metadata||liveRef.current?.metadata||null);},[recorder]);
  const selectRobot=useCallback((id:string)=>{if(pilotRef.current||pilotView.current)return;setSelected(id);setCamera('follow');audio.ui('select');},[audio]);
  // Manual takeover: the camera jumps into the robot and the cockpit takes the keyboard.
  const engagePilot=useCallback((id:string)=>{setPilot(id);setSelected(id);setCamera('fpv');audio.ui('select');},[audio]);
  const releasePilot=useCallback(()=>setPilot(null),[]);
  // Entering Link Start keeps the previous camera so backing out returns the broadcast to where it
  // was instead of dumping it at the default pose.
  const toggleLink=useCallback((on:boolean)=>{
    setLinkMode(on);setLinkHover(null);setLinkPending(null);
    if(on){linkPrevCamera.current=camera==='fpv'?'orbit':camera;setCamera('top');}
    else setCamera(linkPrevCamera.current);
    audio.ui('select');
  },[camera,audio]);
  const liveMode=isFreeBattle(live?.metadata)?'deck':'standard';
  // The cockpit is tinted by the chassis the pilot took over, so `red-3` drives a red instrument panel.
  const pilotTeam=(pilot??'').split('-')[0] as TeamId|'';
  const idle=!replay&&!!live&&!live.busy&&(live.match_id===null||live.match_id===dismissed);idleRef.current=idle;
  const previewFrame=previews[map]??(live?.match_id===null&&frameSeason(live.frame)===season?live.frame:null);
  const frame=replay?replayFrame:idle?previewFrame:liveMode===matchMode?live?.frame:null,metadata:Metadata|null=replay?.metadata||(idle?null:live?.metadata)||null,busy=!!live?.busy,playing=replay?replayPlaying:!live?.paused,currentSpeed=replay?replaySpeed:live?.speed||1,focus=frame?.robots.find(r=>r.id===selected);
  // The callback stays stable so the scene memo is not invalidated on every frame; the robot lookup
  // reads the newest frame from a ref.
  const liveFrameRef=useRef(frame);
  liveFrameRef.current=frame;
  // The empty field is fetched once per map and drawn as a still frame of its own generation.
  useEffect(()=>{if(!idle||previews[map])return;let active=true;api<{frame:Frame}>('/api/arena-preview?map='+map).then(v=>{if(active)setPreviews(old=>({...old,[map]:v.frame}));}).catch(()=>{});return()=>{active=false;};},[idle,map,previews]);
  useEffect(()=>{if(idle&&previewFrame)feed.current={frame:previewFrame,previous:null,received:performance.now(),speed:1,paused:true,events:[],generation:'idle:'+map,replay:false};},[idle,previewFrame,map]);
  // A confirmed link hands the field to the pilot, so the docked rail folds away with it; closing
  // the panel, ending the match or opening a replay ends the scan the same way.
  useEffect(()=>{if(pilot)setLinkMode(false),setLinkHover(null),setLinkPending(null);},[pilot]);
  useEffect(()=>{if(!pilotPanel)setLinkMode(false),setLinkHover(null),setLinkPending(null);},[pilotPanel]);
  useEffect(()=>{if(!busy||replay)setLinkMode(false),setLinkHover(null),setLinkPending(null);},[busy,replay]);
  // The overhead scan publishes the chassis under the pointer; the card and the confirmation plate
  // both read from the same live frame.
  const linkHoverRobot=useMemo(()=>linkHover?frame?.robots.find(r=>r.id===linkHover)??null:null,[linkHover,frame]);
  const modelImage=useCallback((r:Robot|null|undefined)=>r?images[`${r.model_asset||`/assets/robot-${r.role}.glb`}|${r.team}`]:undefined,[images]);
  const linkPendingRobot=useMemo(()=>linkPending?frame?.robots.find(r=>r.id===linkPending)??null:null,[linkPending,frame]);
  const pilotRobot=useMemo(()=>pilot?frame?.robots.find(r=>r.id===pilot)??null:null,[pilot,frame]);
  // Audience first person: the camera rides `selected`, so the bottom-left strip follows the same chassis.
  const observeRobot=useMemo(()=>!pilot&&frame?frame.robots.find(r=>r.id===selected)??null:null,[pilot,frame,selected]);
  // A strategy's standing is stored per version (`name:version`), so the side brief reports the whole
  // history of that strategy: every version's games, with the rating weighted by how many each played.
  const standingFor=useCallback((side:TeamId)=>{
    const key=canonicalStrategyKey(metadata?.teams?.[side]?.name||'');
    if(!key)return undefined;
    const rows=standings.filter(s=>s.identity.split(':')[0]===key);
    if(!rows.length)return undefined;
    const games=rows.reduce((n,r)=>n+r.games,0);
    return {
      games,
      wins:rows.reduce((n,r)=>n+r.wins,0),
      losses:rows.reduce((n,r)=>n+r.losses,0),
      draws:rows.reduce((n,r)=>n+r.draws,0),
      rating:games>0?rows.reduce((n,r)=>n+r.rating*r.games,0)/games:rows[0].rating,
    };
  },[metadata,standings]);
  // Side-picker briefs are plain data: the scene renders them over the half each one describes. Keyed
  // on the match's teams and the standings, so a per-tick `frame` never re-renders the scene tree.
  const halfBriefs=useMemo(()=>{
    const brief=(side:TeamId)=>{
      const team=metadata?.teams[side],entry=catalog[side];
      return {
        team:side==='red'?'红方':'蓝方',
        strategy:strategyDisplayName(team)||strategyDisplayName(entry)||(side==='red'?'赤焰阵线':'深蓝阵线'),
        mode:MODE_LABELS[team?.mode||entry?.mode||'team'],
        standing:standingFor(side),
      };
    };
    return {red:brief('red'),blue:brief('blue')};
  },[metadata,catalog,standings,standingFor]);
  const pickRobot=useCallback((id:string)=>{
    const robot=liveFrameRef.current?.robots.find(r=>r.id===id);
    if(!robot||robot.role==='aerial')return;
    // Choosing the chassis closes the picker and lets the inspection sequence play; the takeover
    // itself is deferred until the countdown ends.
    setSelected(id);setPendingJoin(id);setPickDone(true);setPickStage(null);audio.ui('select');
  },[audio]);
  // A selected drone is a follow target too: only fall back when neither a robot nor one of its
  // drones matches, so clicking a small body does not snap the choice back to `red-1`.
  useEffect(()=>{if(frame?.robots.length&&!frame.robots.some(r=>r.id===selected)&&!frame.robots.some(r=>r.drones?.some(d=>d.id===selected)))setSelected(frame.robots[0].id);},[frame,selected]);
  // A finished match or an opened replay hands the robot back to its strategy.
  useEffect(()=>{if(!busy||replay||frame?.status==='finished')setPilot(null);},[busy,replay,frame?.status]);
  useEffect(()=>{(window as Window&{arenaDiagnostics?:()=>unknown}).arenaDiagnostics=()=>({tick:feed.current.frame?.tick,robots:feed.current.frame?.robots.length,engine:feed.current.frame?.engine,recording:rec.capture?.kind??null,recordedFrames:recorder.frames,videoSaves:rec.jobs.map(j=>({stage:j.stage,progress:j.progress})),audioEnabled:audio.enabled,mode:feed.current.replay?'replay':'live',wsMessages:wsMessages.current,pace:Math.round(feed.current.pace??0),render:(window as unknown as {arenaRender?:unknown}).arenaRender??null,connected,prematch:liveRef.current?.prematch?.stage||(prerollRef.current?'preroll':null),post:postRef.current,music:audio.musicPlaying,audio:audio.diagnostics,killAnnouncement:director.current.highlight?.cue??null,page,matchMode,bgmVolume,camera,selected,fullscreen:document.fullscreenElement?.id==='viewport'||!!document.querySelector('.page-fullscreen'),prerollLeft:prerollRef.current?Math.round(prerollRef.current.left*1000)/1000:null,highlights:highlightClips.map(c=>c.key),reel:{ready:reelReady,index:reelIndex,side:reelSide,playing:playingRef.current,position:Math.round(positionRef.current),frames:reelRef.current?.frames.length??0,starts:reelStarts.current},events:allEvents.current.length,eventTypes:allEvents.current.reduce<Record<string,number>>((m,e)=>(m[e.type]=(m[e.type]||0)+1,m),{})});},[audio,recorder,rec,connected,page,matchMode,bgmVolume,camera,selected,reelSide,highlightClips]);
  // Studio renders of every robot model for the cards, kill feed and post-match screens.
  useEffect(()=>{if(!frame)return;const wanted=new Set(frame.robots.map(r=>`${r.model_asset||`/assets/robot-${r.role}.glb`}|${r.team}`));
    if(post)for(const r of frame.robots)wanted.add(`${r.model_asset||`/assets/robot-${r.role}.glb`}|${r.team}|showcase`);
    for(const key of wanted){if(requested.current.has(key))continue;requested.current.add(key);const [url,team,size]=key.split('|');robotImage(url,team as TeamId,size==='showcase'?'showcase':'card').then(png=>setImages(old=>({...old,[key]:png}))).catch(()=>requested.current.delete(key));}
  },[frame,post]);
  // Pre-match pips and phase timing; each phase has its own soundtrack.
  const prematch=replay?(preroll?(()=>{const left=Math.max(0,preroll.left);return left>PREROLL.countdown?{stage:'self_check' as const,remaining:left-PREROLL.countdown,duration:prerollIntro.current,goIn:left}:{stage:'countdown' as const,remaining:Math.max(0,left),duration:PREROLL.countdown,goIn:Math.max(0,left)};})():null)
    :live?.prematch?{...live.prematch,goIn:live.prematch.stage==='self_check'?live.prematch.remaining+5:live.prematch.remaining}:null;
  // Pre-match join prompt: pressing start asks first, then the 3D picker owns the field.
  const [pickStage,setPickStage]=useState<'side'|'robot'|null>(null),[pickTeam,setPickTeam]=useState<TeamId>('red');
  // `pickDone` freezes the picker once a chassis is chosen (or the player opts to spectate), and
  // `pendingJoin` holds that chassis until the countdown ends — the lineup inspection plays in
  // between instead of the picker cutting straight into the cockpit.
  const [pickDone,setPickDone]=useState(false),[pendingJoin,setPendingJoin]=useState<string|null>(null),[introBase,setIntroBase]=useState<number|null>(null);
  // Last `extend_prematch` request, so a slow round trip is not repeated on every snapshot.
  const prematchTopUp=useRef({at:0,total:0});
  const picking=!!prematch&&playerJoin&&!joinHidden&&!pickDone&&!pilot&&!replay&&!!frame;
  const pickMode=picking&&pickStage==='robot';
  const pickView=useMemo(()=>pickStage?{stage:pickStage,team:pickTeam}:null,[pickStage,pickTeam]);
  // The chassis under the pointer gets its own card, exactly like the one the lineup inspection uses,
  // so a pilot can compare numbers before committing to a chassis.
  const [pickHover,setPickHover]=useState<string|null>(null);
  // Which half of the field the pointer is over, so the side prompt can name the side it has
  // highlighted instead of repeating one generic line.
  const [pickHalfHover,setPickHalfHover]=useState<'red'|'blue'|'seat'|null>(null);
  const pickHoverRobot=useMemo(()=>pickHover?frame?.robots.find(r=>r.id===pickHover)??null:null,[pickHover,frame]);
  const pickSide=useCallback((team:TeamId)=>{setPickTeam(team);setPickStage('robot');},[]);
  useEffect(()=>{setPickHover(null);setPickHalfHover(null);},[pickStage]);
  useEffect(()=>{setPickStage(null);setPickTeam('red');setPickDone(false);setPendingJoin(null);setIntroBase(null);prematchTopUp.current={at:0,total:0};},[live?.match_id]);
  // Declared after the per-match reset on purpose: both effects run in the same commit when a page is
  // opened into a running pre-match, and this one has to win so the picker still opens.
  useEffect(()=>{if(!picking){setPickStage(null);return;}setPickStage(stage=>stage??'side');},[picking]);
  // The inspection sequence begins when the picker closes, not while the field is still a menu.
  useEffect(()=>{
    if(!prematch||picking)return;
    if(introBase===null)setIntroBase(Math.max(0,prematch.duration-prematch.remaining));
  },[prematch,picking,introBase]);
  // The chosen chassis is taken over when the countdown ends, so its inspection is not skipped.
  useEffect(()=>{
    if(!pendingJoin||pilot||prematch||!frame)return;
    engagePilot(pendingJoin);
    setPendingJoin(null);
  },[pendingJoin,pilot,prematch,frame,engagePilot]);
  // The picker must not swallow the countdown: it closes itself once the clock starts ticking.
  useEffect(()=>{if(picking&&prematch?.stage==='countdown')setPickDone(true);},[picking,prematch?.stage]);
  // Every card, chassis and the face-off hold the screen for at least two seconds, so the walk-on needs a
  // minimum window of its own. Picking a chassis eats that window and the countdown cannot be postponed,
  // so the self-check clock is stretched while the picker is open: the countdown then starts later and
  // no segment is cut short. Once the picker closes the walk-on is already running inside whatever time
  // is left, so nothing more is added — extending then would only push the countdown around mid-reel.
  const introReserve=frame?introMinimumSeconds(frame.robots.length):0;
  useEffect(()=>{
    if(replay||!picking||!prematch||prematch.stage!=='self_check'||!introReserve)return;
    const short=introReserve-prematch.remaining;
    if(short<=.4)return;
    // One request per shortfall, paced so the round trip lands before the next one is needed: the
    // server adds the seconds to both the clock and the announced length, which re-arms this check.
    // The total is capped, so a viewer who walks away cannot hold the match forever.
    const now=performance.now(),topUp=prematchTopUp.current;
    if(now-topUp.at<1500||topUp.total>=90)return;
    const seconds=Math.min(30,Math.ceil(short));
    topUp.at=now;topUp.total+=seconds;
    void api('/api/control',{command:'extend_prematch',seconds}).catch(()=>{topUp.at=0;});
  },[replay,picking,prematch?.stage,prematch?.remaining,introReserve]);
  const countdownNumber=prematch?.stage==='countdown'?Math.ceil(prematch.remaining-1e-6):null;
  // Nothing of the in-match UI appears until the countdown is over: after the chassis is chosen the
  // field shows the lineup inspection, and the cockpit only mounts when play actually starts.
  const started=!prematch&&!replay;
  // The lineup intro drives the 3D camera: one cut per segment, each framed for its scheduled length.
  const free=isFreeBattle(metadata),robotKey=frame?.robots.map(r=>r.id).join()??'';
  // The sequence starts when the picker closes, so the self-check time already spent is frozen at that
  // moment. It is derived here as well so the first frame after the picker closes already sits at 0 —
  // waiting for the effect would flash one frame of a mid-reel cut.
  const introBaseNow=introBase??(prematch&&!picking?Math.max(0,prematch.duration-prematch.remaining):0);
  const introElapsed=prematch?Math.max(0,(prematch.duration-prematch.remaining)-introBaseNow):0;
  // The walk-on restarts once the picker closes, so its schedule is scaled to the self-check time that
  // is actually left. Without the scale the countdown lands in the middle of the reel — the very
  // symptom of "red card, then straight into 5-4-3-2-1" — and the blue half is never introduced.
  const introSpan=prematch?Math.max(1,prematch.duration-introBaseNow):0;
  const introCuts=useMemo(()=>!picking&&prematch?.stage==='self_check'&&frame?introSchedule(frame.robots,introSpan):null,[picking,prematch?.stage,introSpan,robotKey]);// eslint-disable-line react-hooks/exhaustive-deps
  const introNow=introCuts&&prematch?introAt(introCuts,introElapsed):null;
  const introShot=useMemo<IntroShot|null>(()=>introNow?{key:introNow.cut.key,segment:introNow.cut.segment,length:introNow.length}:null,[introNow?.cut.key,introNow?.length]);// eslint-disable-line react-hooks/exhaustive-deps
  const onIntroCut=useCallback((cut:IntroCut)=>{if(pageRef.current==='arena')audio.sting(cut.segment.kind);},[audio]);
  recorder.overlay=countdownNumber!==null?{kind:'countdown',n:Math.max(1,countdownNumber)}:startFlash?{kind:'countdown',n:0}:post&&frame?.status==='finished'?{kind:'title',title:frame.winner?`${frame.winner==='red'?'红':'蓝'}方胜利`:'比赛结束',sub:verdict(frame).headline,color:frame.winner==='red'?'#ff3b30':frame.winner==='blue'?'#2f8cff':'#f2c35b'}:null;
  if(introNow&&frame){const segment=introNow.cut.segment,robot=segment.kind==='robot'?frame.robots.find(r=>r.id===segment.id):null,team='team' in segment?segment.team:null;
    recorder.overlay={kind:'intro',title:robot?`${robot.team==='red'?'红方':'蓝方'} ${robot.slot} 号 · ${ROLE_NAMES[robot.role]}`:team?`${team==='red'?'红方':'蓝方'}阵容介绍`:'赛前阵容介绍',sub:robot?`${robot.design_name||''} · ${strategyDisplayName(metadata?.teams[robot.team])}`:team?strategyDisplayName(metadata?.teams[team]):`${strategyDisplayName(metadata?.teams.red)}  VS  ${strategyDisplayName(metadata?.teams.blue)}`,lines:robot?[`型号 ${robot.model_slot||robot.slot} · ${metadata?.agents?.[robot.team]?.[String(robot.slot)]?.model||''}`,`生命 ${robot.max_hp} · 初始弹量 ${robot.ammo}`]:['red','blue'].filter(t=>!team||team===t).map(t=>frame.robots.filter(r=>r.team===t).map(r=>`${r.slot}号 ${r.design_name||ROLE_NAMES[r.role]}`).join(' / '))};}
  if(post==='results'&&frame){const line=(label:string,fn:(t:TeamId)=>string|number)=>({label,red:String(fn('red')),blue:String(fn('blue'))});recorder.overlay={kind:'results',headline:verdict(frame).headline+' · '+verdict(frame).detail,rows:[line('基地剩余血量',t=>Math.ceil(frame.bases[t].hp)),...(frameSeason(frame)==='2027'?[line('累计控制度',t=>Math.floor(frame.teams[t].control??0))]:[]),line('前哨站剩余血量',t=>Math.ceil(frame.outposts?.[t]?.hp||0)),line('经济总量',t=>Math.round(stats.current.teams[t].economy)),line('总伤害量',t=>Math.round(frame.teams[t].attack_damage??frame.teams[t].score)),line('击毁机器人',t=>frame.teams[t].kills),line('42 / 17 mm 发弹量',t=>`${stats.current.teams[t].shots42} / ${stats.current.teams[t].shots17}`),line('能量机关 大 / 小',t=>`${stats.current.teams[t].runes.large} / ${stats.current.teams[t].runes.small}`),line('1 / 2 / 3 / 4 级装配次数',t=>stats.current.teams[t].assemblies.join(' / ')),line('最高等级',t=>stats.current.teams[t].levelMax),line('击毁前哨站',t=>stats.current.teams[t==='red'?'blue':'red'].outpostsLost),line('机器人剩余总血量',t=>Math.round(frame.robots.filter(r=>r.team===t).reduce((n,r)=>n+r.hp,0)))]};}
  if(post==='highlight'){
    // The reel owns the frame: the recorder stamps it as the highlight chapter rather than the
    // generic victory title it would otherwise inherit.
    recorder.overlay={kind:'title',title:'HIGHLIGHT',sub:`${highlightClips.length} 段真实对局片段 · 每段 ${CLIP_SECONDS} 秒`,color:'#f2f7fb'};
  }
  if(post==='mvp'&&frame){const winner=pickMvp(frame,stats.current);if(winner)recorder.overlay={kind:'mvp',name:`${winner.robot.slot}号 · ${winner.robot.design_name||ROLE_NAMES[winner.robot.role]}`,team:`${winner.robot.team==='red'?'红方':'蓝方'} · ${strategyDisplayName(metadata?.teams[winner.robot.team])}`,lines:winner.lines.map(l=>`${l.label}   ${l.value} ${l.unit||''}`),image:images[`${winner.robot.model_asset}|${winner.robot.team}|showcase`]};}

  useEffect(()=>{if(countdownNumber&&countdownNumber>0)audio.countdown(countdownNumber);},[countdownNumber,audio]);

  // Playback pause freezes the soundtrack and effects; result screens keep their music.
  // Browsers that refuse element fullscreen (embedded views, iPhone Safari) get the viewport filling the window instead.
  const [nativeFullscreen,setNativeFullscreen]=useState(false),[pageFullscreen,setPageFullscreen]=useState(false),[controlsOpen,setControlsOpen]=useState(false);
  const fullscreen=nativeFullscreen||pageFullscreen;
  useEffect(()=>{const sync=()=>setNativeFullscreen(document.fullscreenElement?.id==='viewport');document.addEventListener('fullscreenchange',sync);return()=>document.removeEventListener('fullscreenchange',sync);},[]);
  // The strip stays folded behind a small tab: fullscreen is also where the ceremony's own buttons
  // sit along the bottom, and a bar that pops back on every mouse move covers them. The tab opens it,
  // leaving the strip folds it, and a quiet timeout closes it even if the pointer never left.
  useEffect(()=>{if(!fullscreen)setControlsOpen(false);},[fullscreen]);
  useEffect(()=>{if(!controlsOpen)return;const timer=window.setTimeout(()=>setControlsOpen(false),8000);return()=>window.clearTimeout(timer);},[controlsOpen]);
  // F toggles fullscreen and Space pauses, unless typing in a form field; a pilot owns the
  // keyboard and mouse, so the global shortcuts stand down while someone is driving.
  const keyActions=useRef({toggleFullscreen,pause:()=>control('pause')});keyActions.current={toggleFullscreen,pause:()=>control('pause')};
  useEffect(()=>{const onKey=(e:KeyboardEvent)=>{const t=e.target as HTMLElement|null;if(pilotRef.current)return;if(e.metaKey||e.ctrlKey||e.altKey||t?.closest('input,textarea,select,[contenteditable="true"],[role="dialog"],[role="alertdialog"]'))return;
    const mode=CAMERA_MODES.find(m=>m.key===e.key);if(page==='arena'&&mode){e.preventDefault();setCamera(mode.id);audio.ui('select');return;}
    if(e.key==='f'||e.key==='F'){e.preventDefault();keyActions.current.toggleFullscreen();}else if(e.key==='Escape')setPageFullscreen(false);else if(e.key===' '&&page==='arena'&&!t?.closest('button,a[href]')){e.preventDefault();keyActions.current.pause();}};
    window.addEventListener('keydown',onKey);return()=>window.removeEventListener('keydown',onKey);},[page,audio]);
  // A replay only advances while the page renders, so a hidden tab freezes its soundtrack too.
  const [hidden,setHidden]=useState(()=>document.hidden);
  useEffect(()=>{const onVisibility=()=>setHidden(document.hidden);document.addEventListener('visibilitychange',onVisibility);return()=>document.removeEventListener('visibilitychange',onVisibility);},[]);
  // Auto-capture needs rendered frames; pause the referee clock while the window is hidden.
  const hiddenPause=useRef(false);
  useEffect(()=>{
    if(!capturingMatch){hiddenPause.current=false;return;}
    const state=liveRef.current;
    if(hidden&&state?.busy&&!state.paused){hiddenPause.current=true;void api('/api/control',{command:'pause'}).catch(e=>setError(e.message));}
    else if(!hidden&&hiddenPause.current){hiddenPause.current=false;if(state?.busy&&state.paused)void api('/api/control',{command:'pause'}).catch(e=>setError(e.message));}
  },[hidden,capturingMatch,live?.busy,live?.paused]);
  const musicCueRaw=broadcastMusicCue({page,hangar:showTeamLineup||showDecks,modal:showSubmit,free,picking,prematch:prematch?.stage??null,post,status:frame?.status,replay:!!replay,busy,started:startFlash>0});
  // Keep the scope short: it is compared on every render, and interpolating the replay text here exhausted memory within seconds.
  // The highlight reel is one continuous soundtrack: every clipped window reuses the first clip's
  // track, so neither its seek nor the replay it rides on is part of the scope. `replayScope` only
  // changes when a different replay is opened — plain seeking keeps the music running too.
  const musicScope=post==='highlight'?'reel':replay?`replay:${replay.metadata.match_id??'file'}:${replayScope.current}`:`live:${live?.match_id??'waiting'}`;
  // The arena's recording is one cue for the whole match: the installed opening track first, then —
  // once it has played out — the repository's own sting on loop. The player does that hand-off itself,
  // so a speed change mid-match never restarts or swaps the music. A replay is the sting throughout.
  const musicCue=musicCueRaw==='match'&&replay?'match_alt':musicCueRaw;
  const musicTimed=musicCue!==null&&['match','match_alt','pick','countdown'].includes(musicCue);
  // An open MP4 carries its own soundtrack: the menu music and the arena's sound wait while it plays.
  const audioPaused=hidden||!!videoMatch||(musicTimed&&!post&&(replay?!replayPlaying:!!live?.paused));
  useEffect(()=>{audio.setPaused(audioPaused);},[audioPaused,audio]);
  useEffect(()=>{audio.bgm(musicCue,musicScope,prematch?.remaining??5,replay?1:live?.speed??1);},[musicCue,musicScope,prematch?.remaining,live?.speed,replay,audio]);
  useEffect(()=>()=>audio.dispose(),[audio]);
  useEffect(()=>{if(!preroll&&!startFlash)return;const id=window.setInterval(()=>setClockTick(n=>n+1),100);return()=>window.clearInterval(id);},[preroll,startFlash]);
  useEffect(()=>{if(post!=='victory'||(capturingMatch&&hidden))return;const id=window.setTimeout(()=>{if(postRef.current==='victory')setPost('results');},6200);return()=>window.clearTimeout(id);},[post,setPost,capturingMatch,hidden]);
  const mvpResult=useMemo(()=>post==='mvp'&&frame?pickMvp(frame,stats.current):null,[post,frame]);
  // The reel is cut when the MVP card hands over, from every event of the match, so leaving and
  // re-entering the screen does not reshuffle it.
  const openHighlights=useCallback(async()=>{
    const clips=highlightReel(allEvents.current,liveFrameRef.current??null);
    reelClips.current=clips;setHighlightClips(clips);setReelIndex(0);setReelReady(false);reelRef.current=null;reelStarts.current=[];
    // The data panel is behind us: going back to it later starts from a still panel, not a countdown.
    sawMvp.current=true;
    setPost('highlight');
    const id=liveRef.current?.match_id;
    if(!clips.length||!id)return;
    setReelPending(true);
    try{
      // Only the measured windows are asked for: a full replay is hundreds of megabytes, and merging
      // its static half into every frame of a seven-minute match froze the tab for seconds.
      const response=await fetch('/api/highlights',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({match_id:id,at:clips.map(c=>c.time),before:CLIP_PREROLL,seconds:CLIP_SECONDS})});
      if(!response.ok)throw new Error('这场比赛已不在内存中');
      const payload=await response.json() as Replay&{windows?:{start:number;count:number}[]};
      if(!Array.isArray(payload.frames)||payload.frames.length<2)throw new Error('回放没有可用的帧');
      const staticHalf=(payload as {static?:Record<string,unknown>}).static??{};
      const data:Replay={...payload,frames:payload.frames.map(frame=>({...staticHalf,...frame}))};
      for(const f of data.frames)applySkins(f,data.metadata);
      reelRef.current=data;
      reelStarts.current=(payload.windows??[]).map(w=>w.start);
      // The reel rides the ordinary replay state, so the scene, the recorder and the transport read
      // it exactly like a loaded replay: it is only seeked per clip, and it has no walk-on pre-roll.
      replayRef.current=data;positionRef.current=0;playingRef.current=false;
      setReplay(data);setReplayFrame(data.frames[0]);setReplayPosition(0);setReplayPlaying(false);
      setReelReady(true);
    }catch{
      // Without frames the reel falls back to the card version, which describes the same moments.
      reelRef.current=null;reelStarts.current=[];
    }finally{setReelPending(false);}
  },[setPost]);
  // Each window already contains 1.5 s of run-up before its moment, so a clip is just a seek.
  const startClip=useCallback((index:number)=>{
    const data=reelRef.current,clip=reelClips.current[index];
    if(!data||!clip)return;
    const at=Math.max(0,Math.min(data.frames.length-1,reelStarts.current[index]??0));
    replayGeneration.current++;positionRef.current=at;playingRef.current=true;
    setReelIndex(index);setReelSide('output');setReplayFrame(data.frames[at]);setReplayPosition(at);setReplayPlaying(true);
    // An aerial beat rides the drone that made the strike; every other beat follows its star.
    const target=clip.drone??clip.star;
    if(target)setSelected(target);
    setCamera(target?'follow':'orbit');
  },[]);
  // Leaving the reel hands the field back to the live frame and continues to the next card: the reel
  // sits between the data panel and the MVP, so `next` is where the ceremony goes afterwards.
  const closeHighlights=useCallback((next:Post=null)=>{
    reelRef.current=null;reelClips.current=[];reelStarts.current=[];
    replayRef.current=null;prerollRef.current=null;playingRef.current=false;
    setReelReady(false);setReelPending(false);setReelIndex(0);setReelSide('output');setReplay(null);setReplayFrame(null);setPreroll(null);
    if(liveRef.current)accept(liveRef.current);
    setPost(next);
  },[accept,setPost]);
  useEffect(()=>{if(!reelReady||post!=='highlight')return;startClip(0);},[reelReady,post,startClip]);
  // A match that produced nothing to replay must not trap the viewer on a blank screen: the ceremony
  // moves on to the MVP card instead, like a skipped reel.
  useEffect(()=>{
    if(post!=='highlight'||reelReady||reelPending||highlightClips.length)return;
    const timer=window.setTimeout(()=>closeHighlights('mvp'),4000);
    return()=>window.clearTimeout(timer);
  },[post,reelReady,reelPending,highlightClips.length,closeHighlights]);
  // One clip per five seconds, on the reel's own clock, so a stalled animation frame cannot stretch
  // a highlight or leave the reel hanging.
  useEffect(()=>{
    if(!reelReady||post!=='highlight'||hidden)return;
    const timer=window.setTimeout(()=>{
      if(reelIndex+1<reelClips.current.length)startClip(reelIndex+1);
      else closeHighlights('mvp');
    },CLIP_SECONDS*1000);
    return()=>window.clearTimeout(timer);
  },[reelReady,post,reelIndex,startClip,closeHighlights,hidden]);
  // A five-second beat has two sides: the output unit's chase view while the shot lands, then a cut
  // to the unit that took it. A receiver that is already destroyed keeps the chase view because the
  // cockpit camera would freeze on its last frame.
  useEffect(()=>{
    if(!reelReady||post!=='highlight'||hidden)return;
    const clip=reelClips.current[reelIndex],rival=clip?clipRival(clip):null;
    if(!rival)return;
    const timer=window.setTimeout(()=>{
      const receiving=feed.current.frame?.robots.find(r=>r.id===rival);
      // A robot that left the frame (or the replay ended) keeps the output view rather than cutting
      // to whatever the selection fallback would land on.
      if(!receiving)return;
      setSelected(rival);setReelSide('input');
      setCamera(receiving.alive===false?'follow':'fpv');
    },CLIP_SECOND_SHOT*1000);
    return()=>window.clearTimeout(timer);
  },[reelReady,post,reelIndex,hidden]);
  // Once the data panel has handed over, coming back to it must not restart its countdown.
  const sawMvp=useRef(false);
  // A match recording runs from the walk-on to the MVP card. It ends eight seconds into the card, as
  // soon as the viewer leaves the card or the ceremony, or when the match fails. The save then runs in
  // the background with its progress in the dock, so no ceremony button ever waits for it.
  const ownMatch=!!matchCapture?.matchId&&matchCapture.matchId===live?.match_id;
  useEffect(()=>{if(!ownMatch||post!=='mvp'||hidden)return;const timer=window.setTimeout(()=>{void session.stop();},8000);return()=>window.clearTimeout(timer);},[ownMatch,post,hidden,session]);
  const lastPost=useRef<Post>(null);
  useEffect(()=>{const before=lastPost.current;lastPost.current=post;if(ownMatch&&before&&(before==='mvp'?post!=='mvp':post===null))void session.stop();},[post,ownMatch,session]);
  useEffect(()=>{if(ownMatch&&live?.error&&!live.busy)void session.stop();},[ownMatch,live?.error,live?.busy,session]);

  useEffect(()=>{if(post==='victory'||post===null)sawMvp.current=false;},[post]);
  useEffect(()=>{if(!startFlash)return;const id=window.setTimeout(()=>setStartFlash(0),1400);return()=>window.clearTimeout(id);},[startFlash]);

  useEffect(()=>{const keys=seasonChoices.map(([k])=>k);if(keys.length){if(!keys.includes(red))setRed(keys.includes(seasonDefault[0])?seasonDefault[0]:keys[0]);if(!keys.includes(blue))setBlue(keys.includes(seasonDefault[1])?seasonDefault[1]:keys[0]);}else if(Object.keys(catalog).length){if(red)setRed('');if(blue)setBlue('');}},[catalog,seasonChoices,teamLineup,red,blue,season]);
  // Hardware each team fields: its strategy's locked lineup, otherwise the picker lineup.
  const sideLineup=(team:TeamId)=>catalog[team==='red'?red:blue]?.team_lineup||teamLineup;
  const fielded:Record<TeamId,number[]>=matchMode==='deck'?{red:decks.red.map(id=>seasonCards[id]?.robot).filter((m):m is number=>!!m),blue:decks.blue.map(id=>seasonCards[id]?.robot).filter((m):m is number=>!!m)}:{red:slots.map(s=>sideLineup('red')[String(s)]),blue:slots.map(s=>sideLineup('blue')[String(s)])};
  const chosenSkins=(team:TeamId)=>Object.fromEntries(Object.entries(skins[team]||{}).filter(([model,id])=>fielded[team].includes(Number(model))&&customs.some(c=>c.id===id&&c.base_model===Number(model))));
  const skinCount=Object.keys(chosenSkins('red')).length+Object.keys(chosenSkins('blue')).length;
  async function start(){
    if(busy||launching||capturing)return;
    setLaunching(true);
    try{
      // The match recording starts before the request so it opens on the walk-on.
      if(saveMp4){await session.start('match');setSound(true);}
      // A team strategy always runs its own locked lineup; the picker only fills in a side whose
      // strategy declares none. Sending both sides separately keeps two different lineups intact.
      const result=await api<{match_id:string}>('/api/start',{red,blue,seed,duration,map,save_mp4:saveMp4,mode:matchMode,red_skins:chosenSkins('red'),blue_skins:chosenSkins('blue'),...(matchMode==='standard'?{team_lineup:teamLineup,red_lineup:catalog[red]?.team_lineup,blue_lineup:catalog[blue]?.team_lineup}:{}),...(matchMode==='deck'?{red_deck:decks.red,blue_deck:decks.blue,...freeStartOptions(freeControllers)}:{})});
      if(saveMp4)session.attach(result.match_id);
      replayRef.current=null;prerollRef.current=null;setPreroll(null);setReplay(null);setReplayFrame(null);seen.current.clear();allEvents.current=[];setLog([]);setPost(null);resetBroadcast();setError('');setPage('arena');feed.current.generation='live:'+result.match_id;
    }catch(e){if(saveMp4)await session.cancel();setError((e as Error).message);}finally{setLaunching(false);}
  }
  async function skipPrematch(){if(replay){if(prerollRef.current)prerollRef.current.left=0;return;}try{await api('/api/control',{command:'skip_prematch'});}catch(e){setError((e as Error).message);}}
  async function control(command:'pause'|'stop'|'speed',value?:number){try{if(replay&&command==='pause'){playingRef.current=!playingRef.current;setReplayPlaying(playingRef.current);return;}if(replay&&command==='speed'){speedRef.current=value!;setReplaySpeed(value!);return;}await api('/api/control',{command,...(value?{speed:value}:{})});}catch(e){setError((e as Error).message);}}
  function toggleFullscreen(){
    if(document.fullscreenElement){void document.exitFullscreen();return;}
    if(pageFullscreen){setPageFullscreen(false);return;}
    const viewport=document.getElementById('viewport');
    if(viewport?.requestFullscreen)viewport.requestFullscreen().catch(()=>setPageFullscreen(true));else setPageFullscreen(true);
  }
  function toggleAudio(){setSound(value=>!value);}
  // A clip is recorded by hand and downloaded as MP4; stopping returns at once and the dock carries the save.
  async function toggleRecording(){
    try{
      if(rec.capture?.kind==='clip'){await session.stop();return;}
      if(capturing)return;
      await session.start('clip');setSound(true);setError('');
    }catch(e){setError((e as Error).message);}
  }
  function loadReplay(data:Replay,origin:ReplaySource){if(!data||typeof data!=='object')throw new Error('无效的回放');if(!['rmuc-replay-v2','rmuc-replay-v3','rmuc-replay-v4'].includes(data.format))throw new Error('播放器接受 v2 / v3 / v4 回放；v1 可用 CLI 验证');if(data.format==='rmuc-replay-v4')data.frames=data.frames.map(frame=>({...data.static,...frame}));if(!Array.isArray(data.frames)||!data.frames.length||data.frames.length>12001||!data.metadata?.teams?.red||!data.metadata?.teams?.blue)throw new Error('无效的回放');const variable=isFreeBattle(data.metadata);const lineup=data.metadata.lineups;if(variable&&(!lineup||!['red','blue'].every(team=>Array.isArray(lineup[team as TeamId])&&lineup[team as TeamId].length>=1&&lineup[team as TeamId].every(d=>Number.isInteger(d.slot)&&d.slot>0&&Number.isInteger(d.model)))))throw new Error('卡组回放缺少阵容');const expectedCount=variable?lineup!.red.length+lineup!.blue.length:frameSeason(data.frames[0])==='2027'?10:(data.format!=='rmuc-replay-v2'?12:14);for(const f of data.frames)applySkins(f,data.metadata);for(const f of data.frames){if(!Array.isArray(f.robots)||f.robots.length!==expectedCount||!Number.isFinite(f.time)||!f.arena||!['rmuc2027','rmuc2026','foundry','crossroads'].includes(f.arena.name)||!f.bases||!f.teams||!Array.isArray(f.events)||!Array.isArray(f.projectiles))throw new Error('回放帧格式不完整');if(new Set(f.robots.map(r=>r.id)).size!==f.robots.length)throw new Error('机器人编号重复');for(const r of f.robots)if(!Number.isFinite(r.x)||!Number.isFinite(r.y)||!Number.isFinite(r.z)||!(variable?/^(red|blue)-[1-9][0-9]{0,9}$/:/^((red|blue)-[1-7])$/).test(r.id)||!['red','blue'].includes(r.team)||!(r.role in ROLE_NAMES))throw new Error('回放位置数据无效');}
    setMatchMode(variable?'deck':'standard');replayGeneration.current++;replayScope.current++;sourceRef.current=origin;replayRef.current=data;setReplay(data);setReplayFrame(data.frames[0]);positionRef.current=0;setReplayPosition(0);playingRef.current=true;setReplayPlaying(true);speedRef.current=1;setReplaySpeed(1);seen.current.clear();allEvents.current=[];setLog([]);setPost(null);resetBroadcast();setPage('arena');setError('');
    prerollIntro.current=introSeconds(data.frames[0].robots.length);const roll={left:prerollIntro.current+PREROLL.countdown};prerollRef.current=roll;setPreroll(roll);}
  async function openReplay(id:string){try{const response=await fetch('/api/replays/'+id);if(!response.ok)throw new Error('回放不存在');loadReplay(await response.json(),{id});}catch(e){setError((e as Error).message);}}
  async function importReplay(e:ChangeEvent<HTMLInputElement>){try{const file=e.target.files?.[0];if(!file)return;if(file.size>512*1024*1024)throw new Error('回放文件不能超过 512 MiB');loadReplay(JSON.parse(await file.text()),{file});}catch(e){setError((e as Error).message);}finally{e.target.value='';}}
  async function exportReplay(){try{const origin=replay?sourceRef.current:null;if(origin&&'file' in origin){download(origin.file,origin.file.name);return;}
    const response=await fetch(origin?'/api/replays/'+origin.id:'/api/replay');if(!response.ok)throw new Error(origin?'回放已被删除':'请先开始比赛');download(await response.blob(),`rmuc-${origin?.id??liveRef.current?.match_id??liveRef.current?.metadata?.seed??'match'}.json`);}catch(e){setError((e as Error).message);}}
  function seek(value:number){if(!replay)return;replayGeneration.current++;positionRef.current=value;playingRef.current=false;setReplayPlaying(false);setReplayPosition(value);setReplayFrame(replay.frames[value]);setPost(null);prerollRef.current=null;setPreroll(null);seen.current.clear();allEvents.current=[];setLog([]);
    audio.cancelAnnouncements();stats.current=statsFromFrames(replay.frames.slice(0,value+1));director.current.reset();director.current.restoreKills(replay.frames.slice(0,value+1));director.current.frame(replay.frames[value]);}
  // Entering the arena from another page: a match that is over (or a replay that has played out) is left
  // behind, so the field opens empty and ready for the next start rather than frozen on its last frame.
  function freshArena(){
    const data=replayRef.current;
    if(data&&postRef.current!=='highlight'&&positionRef.current>=data.frames.length-1)backToLive();
    const state=liveRef.current;
    if(replayRef.current||!state||state.busy||state.frame.status!=='finished')return;
    setDismissed(state.match_id);seen.current.clear();allEvents.current=[];setLog([]);setPost(null);resetBroadcast();
  }
  // The MP4 and the replay under it would play over each other, so the replay pauses first.
  function openVideo(id:string){if(replayRef.current&&playingRef.current){playingRef.current=false;setReplayPlaying(false);}setVideoMatch(id);}
  function backToLive(){replayRef.current=null;prerollRef.current=null;setPreroll(null);setReplay(null);seen.current.clear();allEvents.current=[];setLog([]);setPost(null);resetBroadcast();sourceRef.current=null;setReplayFrame(null);if(liveRef.current)accept(liveRef.current);}
  async function deleteMatches(records:MatchRecord[],onProgress:(done:number)=>void){
    const result=await deleteMatchRecords(records.map(m=>m.id),id=>fetch('/api/matches/'+encodeURIComponent(id),{method:'DELETE'}),onProgress);
    const removed=new Set(result.deleted);
    setMatches(old=>old.filter(m=>!removed.has(m.id)));
    const origin=sourceRef.current;
    if(origin&&'id' in origin&&removed.has(origin.id))backToLive();
    void refreshHistory();
    if(result.failed.length){
      const failed=new Set(result.failed.map(item=>item.id));
      setPendingDelete(records.filter(m=>failed.has(m.id)));
      throw new Error(`${result.deleted.length?`已删除 ${result.deleted.length} 场；`:''}${result.failed.length} 场未能删除。${result.failed[0].message}`);
    }
    audio.ui('success');setPendingDelete(null);
  }
  // A capture draws the arena canvas, so it pins the page; saves continue on any page.
  function navigatePage(value:typeof page){if(capturing&&value!=='arena'){setError(matchCapture?'整场录制进行中：MVP 展示后自动结束，也可以在右下角提前结束录制。':'正在录制片段，停止录制后可切换页面。');return;}if(value==='arena'&&page!=='arena')freshArena();else if(value!=='arena'&&page==='arena'&&postRef.current==='highlight')closeHighlights(null);setPage(value);if(value==='history'||value==='leaderboard'||value==='gallery')refreshHistory();if(value==='gallery')setGalleryKey(k=>k+1);}

  function enterBattle(mode:'standard'|'deck'){if(busy&&mode!==(isFreeBattle(live?.metadata)?'deck':'standard')){setError('当前比赛正在进行，请先结束比赛，再切换对战模式。');return;}setError('');if(replay)backToLive();if(mode!==matchMode)setPost(null);setMatchMode(mode);refreshCatalog();navigatePage('arena');}
  function submitTraining(mode:TrainingMode){setTrainingMode(mode);setShowSubmit(true);}

  return <div className="app-shell">
    <header className="app-header"><a className="brand" href="/" onClick={e=>{e.preventDefault();navigatePage('home');}}><img className="brand-logo" src="/brand/arena-1.png" alt="Arena-1"/><span>ARENA<span className="brand-light">-1</span></span><small>STRATEGY LEAGUE</small></a><nav>{[['home','主页',HomeIcon],['training','训练',GraduationCap],['arena',matchMode==='standard'?'RM 对战':'自由对战',Layers3],['gallery','策略库',LibraryBig],['history','比赛与回放',History],['leaderboard','策略排行榜',Trophy],['settings','战场设置',Settings2]].map(([id,label,Icon])=>{const Component=Icon as typeof Layers3;return <button key={id as string} className={page===id?'active':''} onClick={()=>navigatePage(id as typeof page)}><Component size={15}/>{label as string}</button>;})}</nav><AudioControls sound={sound} volume={bgmVolume} onToggle={toggleAudio} onVolume={setBgmVolume}/><div className={`connection ${connected?'online':''}`}><span/>{connected?'WebSocket 已连接':'正在连接'}<b>v{APP_VERSION}</b></div></header>
    {error&&<div className="global-error"><Shield size={15}/><span>{error}</span><button aria-label="关闭提示" onClick={()=>setError('')}><X size={15}/></button></div>}
    {page==='home'?<Home models={models} catalog={catalog} cards={robotCards} busy={busy} standings={standings} connected={connected} live={busy&&live?.metadata?{red:strategyDisplayName(live.metadata.teams.red),blue:strategyDisplayName(live.metadata.teams.blue)}:null} onTraining={()=>navigatePage('training')} onBattle={enterBattle} onHistory={()=>navigatePage('history')} onRankings={()=>navigatePage('leaderboard')} onGallery={()=>navigatePage('gallery')} onWatch={()=>{backToLive();enterBattle(liveMode);}}/>:page==='training'?<Training models={models} lineup={teamLineup} season={season} onSeason={value=>setMap(value==='2026'?'rmuc2026':'rmuc2027')} onLineup={()=>setShowTeamLineup(true)} onSubmit={submitTraining} onBattle={mode=>enterBattle(mode==='adaptive'?'deck':'standard')} onBack={()=>navigatePage('home')}/>:page==='arena'?<>
    <div className="page-heading"><div><span className="eyebrow">LIVE SIMULATION</span><h1>{matchMode==='standard'?`RM 对战 · ${SEASON_LABELS[season]} · ${slots.length}V${slots.length}`:`自由对战 · ${SEASON_LABELS[season]} · 阵容由你决定`}</h1></div><div className="architecture-tags"><span><Activity size={12}/>Rapier · 120 Hz</span><span><Shield size={12}/>{live?.sandbox==='trusted-local'?'本地开发':'Docker 隔离'}</span><span><Code2 size={12}/>Python · 10 Hz</span></div></div>
    <main className={`arena-layout ${pilot?'pilot-locked':''}`}><aside className="setup-panel"><div className="panel-heading"><span className="eyebrow">MATCH SETUP</span><span className="tiny-badge">{matchMode==='deck'?`${decks.red.length} v ${decks.blue.length}`:`${slots.length} v ${slots.length}`}</span></div><div className="matchup-title">准备上场阵容</div>{matchMode==='standard'&&<button id="strategy-matchmaker" className="team-lineup-button" disabled={busy||launching||capturing} onClick={()=>setShowMatchmaker(true)}>浏览全部策略 / 并排比较与配对</button>}{matchMode==='standard'&&<button className="team-lineup-button" disabled={busy||launching||capturing} onClick={()=>setShowTeamLineup(true)}>调整阵容 / 开始策略开发</button>}<p className="battle-mode-note">{matchMode==='standard'?(season==='2027'?'RMUC 2027：每方一台重型、两台步兵、一套空中机器人系统、一台全自动哨兵。双方可以各用不同型号，但每方阵容必须完整且符合 2027 制作规范。':'RMUC 2026：每方一台英雄、一台工程、一台无人机、三台步兵。双方可以各用不同型号，但每方阵容必须完整。'):`每种机器人都有 3 条预置策略。红蓝双方自由搭配，型号可重复；只列出符合 ${SEASON_LABELS[season]} 制作规范的型号${season==='2027'?'，每方最多一套空中机器人系统':''}。`}</p>{matchMode==='standard'?<><label><span className="team-dot red"/>红方策略<select id="red-select" value={red} onChange={e=>setRed(e.target.value)} disabled={busy}>{seasonChoices.map(([id,c])=><option key={id} value={id}>{strategyDisplayName(c)} · {MODE_LABELS[c.mode]}</option>)}</select></label><div className="strategy-version">{catalog[red]?.version.slice(0,10)}<span>{catalog[red]?.mode==='team'?'1 个策略进程':`${slots.length} 个策略进程`}</span>{catalog[red]?.team_lineup&&<span title={`锁定阵容 ${Object.values(catalog[red]!.team_lineup!).join(' / ')}`}>锁定阵容</span>}</div><label><span className="team-dot blue"/>蓝方策略<select id="blue-select" value={blue} onChange={e=>setBlue(e.target.value)} disabled={busy}>{seasonChoices.map(([id,c])=><option key={id} value={id}>{strategyDisplayName(c)} · {MODE_LABELS[c.mode]}</option>)}</select></label><div className="strategy-version">{catalog[blue]?.version.slice(0,10)}<span>{catalog[blue]?.mode==='team'?'1 个策略进程':`${slots.length} 个策略进程`}</span>{catalog[blue]?.team_lineup&&<span title={`锁定阵容 ${Object.values(catalog[blue]!.team_lineup!).join(' / ')}`}>锁定阵容</span>}</div></>:<div className="deck-setup-summary">{(['red','blue'] as const).map(team=><div key={team}><strong style={{color:TEAM_COLORS[team]}}>{team==='red'?'红方':'蓝方'} · {decks[team].length} 台</strong><small>{freeControllers[team].mode==='team'?`Team 全队 · ${strategyDisplayName(catalog[freeControllers[team].strategy])||'请选择策略'}`:'独立控制 · 每台运行单机策略'}</small><div className="deck-summary-chips">{summarizeDeck(decks[team]).map(({id,count})=><span key={id} title={seasonCards[id]?`${seasonCards[id].model_name} · ${strategyLabel(seasonCards[id])}`:strategyName(id)}>{seasonCards[id]?.robot||'?'} · {seasonCards[id]?strategyLabel(seasonCards[id]):'不可用'}{count>1?` ×${count}`:''}</span>)}{!decks[team].length&&<small>还没有上场机器人</small>}</div></div>)}<button id="edit-decks" disabled={busy} onClick={()=>setShowDecks(true)}>配置机器人与策略</button><small>按型号选择 · 每台策略随时切换</small></div>}<button className="skin-button" disabled={busy} onClick={()=>setShowSkins(true)}><Palette size={14}/>机器人外观<span>{skinCount?`${skinCount} 个自定义`:customs.length?`${customs.length} 个可用`:'上传模型'}</span></button><div className="form-row"><label>随机种子<input id="seed" type="number" value={seed} onChange={e=>setSeed(Number(e.target.value))} disabled={busy}/></label><label>比赛时长<select id="duration" value={duration} onChange={e=>setDuration(Number(e.target.value))} disabled={busy}>{[420].map(s=><option key={s} value={s}>{s} 秒</option>)}</select></label></div><label>比赛地图<select id="map-select" value={map} onChange={e=>setMap(e.target.value as typeof map)} disabled={busy}><option value="rmuc2027">RMUC 2027 / 28 × 15 m（默认）</option><option value="rmuc2026">RMUC 2026 / 28 × 15 m</option></select></label><div className="map-note"><Layers3 size={13}/><span>{season==='2027'?'控制点 · 中央高地 · 制高点 · 机库 · 科技核心':'前哨站 · 能量机关 · 资源区 · 科技核心'}</span></div><label className="save-mp4-option"><input id="save-match-mp4" type="checkbox" checked={saveMp4} disabled={busy||launching||capturing} onChange={e=>setSaveMp4(e.target.checked)}/><span>自动录制整场 MP4<small>从赛前阵容录到 MVP 结算，结束后在后台转码并保存到「比赛与回放」，进度显示在右下角。</small></span></label><button id="start" className="primary start-button" disabled={busy||launching||capturing||(matchMode==='deck'&&(!decks.red.length||!decks.blue.length||[...decks.red,...decks.blue].some(id=>!seasonCards[id])||Object.values(freeControllers).some(c=>c.mode==='team'&&seasonCatalog[c.strategy]?.mode!=='team')))||(matchMode==='standard'&&(!seasonCatalog[red]||!seasonCatalog[blue]||(Object.keys(models).length>0&&!validLineup(teamLineup,models,season))))} onClick={()=>{setPlayerJoin(true);void start();}}><Play size={15} fill="currentColor"/>{busy?'比赛运行中':'开始对战'}</button><button className="submission-button" id="open-submission" onClick={()=>{setTrainingMode(matchMode==='deck'?'adaptive':'team');setShowSubmit(true);}}><Code2 size={14}/>上传策略</button><div className="setup-divider"/><span className="eyebrow">BROADCAST DIRECTOR</span><CameraControls mode={camera} onChange={setCamera}/><label>跟随目标<select id="follow-select" value={selected} onChange={e=>selectRobot(e.target.value)}>{frame?.robots.map(robot=>robot.drones?.length?<optgroup key={robot.id} label={`${robot.team==='red'?'红':'蓝'}方 ${robot.slot} 号 · 空中机器人 / 机库`}><option value={robot.id}>空中机器人（自动跟随无人机）</option>{robot.drones.map(d=><option key={d.id} value={d.id}>{d.index} 号无人机 · {({docked:'待机',flying:'飞行',down:'回收',disabled:'损毁'} as Record<string,string>)[d.state]}</option>)}</optgroup>:<option key={robot.id} value={robot.id}>{robot.team==='red'?'红':'蓝'}方 {robot.slot} 号 · {ROLE_NAMES[robot.role]}{robot.model_slot?` / ${robot.model_slot} 型`:''}</option>)}</select></label><div className="broadcast-buttons"><button id="sound" className={sound?'active':''} onClick={toggleAudio}>{sound?<Volume2 size={15}/>:<VolumeX size={15}/>}音效{sound?'开':'关'}</button><button id="record" className={rec.capture?'recording':''} disabled={rec.starting||capturingMatch} onClick={toggleRecording}>{rec.capture?.kind==='clip'?<Square size={13} fill="currentColor"/>:<Video size={15}/>} {rec.starting?'准备录制…':capturingMatch?'整场录制中':rec.capture?'停止并保存':'录制片段'}</button></div><p className="record-note">1080p / 30 FPS · 含比分与合成音轨 · 停止后转成 MP4 下载</p><div className="sdk-note"><Shield size={15}/><div>只提交策略，规则由引擎裁定。<span>独立单机策略的内部状态独立，通过队内消息配合。</span></div></div></aside>
    <section className="stage-column">{frame?<>
      <div className="scoreboard"><div className="team-score red-score"><div><span className="eyebrow">RED / 攻击伤害</span><h2>{strategyDisplayName(metadata?.teams.red)||strategyDisplayName(catalog[red])||'红方'}</h2><span>{MODE_LABELS[metadata?.teams.red.mode||catalog[red]?.mode||'team']} · 基地 {Math.ceil(frame.bases.red.hp)} / 前哨 {Math.ceil(frame.outposts?.red.hp||0)}</span></div><strong id="red-score">{Math.floor(frame.teams.red.score)}</strong></div><div className="match-clock"><span id="match-state">{replay?'回放模式':frame.status==='ready'?(busy?'启动策略容器':'等待开赛'):frame.status==='finished'?'比赛结束':live?.paused?'比赛已暂停':'比赛进行中'}</span><strong id="clock">{clock(frame.remaining)}</strong><span>SEED {frame.seed}</span></div><div className="team-score blue-score"><strong>{Math.floor(frame.teams.blue.score)}</strong><div><span className="eyebrow">BLUE / 攻击伤害</span><h2>{strategyDisplayName(metadata?.teams.blue)||strategyDisplayName(catalog[blue])||'蓝方'}</h2><span>{MODE_LABELS[metadata?.teams.blue.mode||catalog[blue]?.mode||'team']} · 基地 {Math.ceil(frame.bases.blue.hp)} / 前哨 {Math.ceil(frame.outposts?.blue.hp||0)}</span></div></div></div>
      <div className={`viewport ${pageFullscreen?'page-fullscreen':''} ${introShot?'intro-active':''} ${pilot?'pilot-active':''} ${pilotTeam?`pilot-team-${pilotTeam}`:''} ${post==='highlight'?'highlight-reel':''} ${pilot&&pilotPanel?'pilot-panel-open':''} ${pilot&&!pilotPanel?'pilot-aiming':''} ${pilot&&focus&&!focus.alive?'pilot-dead':''} ${picking?'pilot-picking':''} ${pickMode?'pilot-pick-active':''} ${pickStage==='side'&&pickHalfHover?`pick-half-${pickHalfHover}`:''} ${prematch?'prematch':''} ${linkMode?'link-scan':''}`} id="viewport" ref={viewportRef}><ArenaScene frame={frame} feed={feed} mode={camera} selected={selected} audio={audio} onSelect={selectRobot} onCanvas={onCanvas} onRender={onRender} shot={introShot} pilot={pilot} pick={picking} onPick={pickRobot} onPickHalf={pickSide} onPickHalfHover={setPickHalfHover} onPickHover={setPickHover} pickView={pickView} linkPick={linkMode&&!pilot} onLinkPick={setLinkPending} onLinkHover={setLinkHover} briefs={halfBriefs} onPickSpectate={()=>setJoinHidden(true)}/>{!prematch&&!post&&<BroadcastHud frame={frame} metadata={metadata} stats={stats.current} director={director.current} images={images} selected={selected} onSelect={selectRobot} round="Round 1/1" pilot={pilot?pilot.split('-')[0] as 'red'|'blue':null} player={pilot}/>}<KillAnnouncement director={director.current} frame={frame} images={images} paused={audioPaused||!!prematch}/><div className="viewport-bottom"><span className={`live-badge ${rec.capture?'rec':''}`}><Radio size={11}/>{rec.capture?'RECORDING':replay?'REPLAY':'LIVE ARENA'}</span><span>{linkMode?'悬停查看机体 · 点击机体建立连接':'拖动旋转 · 滚轮缩放 · 点击机器人跟随 · 跟随中可拖动环绕'}</span></div>
      {linkMode&&!pilot&&!linkPending&&linkHoverRobot&&<LinkHoverCard robot={linkHoverRobot} hardware={models?.[String(linkHoverRobot.model_slot??linkHoverRobot.slot)]??frame.robot_models?.[String(linkHoverRobot.model_slot??linkHoverRobot.slot)]} image={modelImage(linkHoverRobot)}/>}
      {!prematch&&!post&&frame.status==='running'&&camera==='fpv'&&observeRobot&&<SpectatorVitals frame={frame} robot={observeRobot} portrait={modelImage(observeRobot)}/>}
      {/* The cockpit owns the pilot's HUD, so it goes away the moment the match is decided: leaving it
          mounted would keep the bottom-left status panel on top of the victory, data and MVP cards
          (and keep the 20 Hz command loop running against a finished match). */}
      {started&&busy&&!replay&&!post&&frame&&frame.status!=='finished'&&<PlayerCockpit frame={frame} active={pilot} onEngage={engagePilot} onRelease={releasePilot} view={pilotView} open={pilotPanel} onOpen={setPilotPanel} paused={!!live?.paused} onError={setError} camera={camera} onCamera={setCamera} onPause={()=>void control('pause')} fullscreen={fullscreen} onFullscreen={toggleFullscreen} link={linkMode} onLink={toggleLink} linkPending={linkPending} onLinkPick={setLinkPending} linkImage={modelImage(linkPendingRobot)} portrait={modelImage(pilotRobot)}/>}
        <button className="fullscreen-toggle" title={fullscreen?'退出全屏 (F / Esc)':'全屏观战 (F)'} aria-label={fullscreen?'退出全屏':'全屏观战'} onClick={toggleFullscreen}>{fullscreen?<Minimize2 size={16}/>:<Maximize2 size={16}/>}<span>{fullscreen?'退出全屏':'全屏'}</span></button>
        {fullscreen&&!controlsOpen&&<button className="fullscreen-tab" onClick={()=>setControlsOpen(true)} aria-expanded={false} aria-label="显示播放控制" title="显示播放控制（暂停 / 进度 / 音量 / 退出全屏）"><i/></button>}
        {fullscreen&&controlsOpen&&<div className="fullscreen-controls" onPointerLeave={()=>setControlsOpen(false)}><button onClick={()=>control('pause')} disabled={!busy&&!replay} aria-label={playing?'暂停':'继续'}>{playing?<Pause size={18}/>:<Play size={18}/>}</button><span>{clock(frame.time)} / {clock(frame.duration)}</span>{replay&&<input type="range" min={0} max={replay.frames.length-1} value={Math.floor(replayPosition)} onChange={e=>seek(Number(e.target.value))} aria-label="回放进度"/>}<select value={currentSpeed} onChange={e=>control('speed',Number(e.target.value))} aria-label="播放速度">{[.5,1,2,4,8].map(v=><option key={v} value={v}>{v}×</option>)}</select><AudioControls compact sound={sound} volume={bgmVolume} onToggle={toggleAudio} onVolume={setBgmVolume}/><button onClick={()=>setControlsOpen(false)} aria-label="收起控制条" title="收起控制条"><ChevronDown size={18}/></button><button onClick={toggleFullscreen} aria-label="退出全屏"><Minimize2 size={18}/></button></div>}{busy&&frame.status==='ready'&&!prematch&&<div className="initializing"><Activity size={16}/>正在准备隔离策略进程…</div>}
        {prematch&&!picking&&<Prematch stage={prematch.stage} remaining={prematch.remaining} duration={prematch.duration} offset={introBaseNow} frame={frame} metadata={metadata} standings={standings} images={images} models={models} free={free} paused={replay?!replayPlaying:!!live?.paused} replay={!!replay} onCut={onIntroCut} onSkip={skipPrematch}/>}
        {pickStage==='side'&&<>
          {/* No banner and no cards: the two halves are named by floating labels anchored over them by
              the scene, and the spectator seat gets one of its own over the stands. The field stays
              unobstructed and a narrow window can no longer squeeze three boxes into one strip. */}
          <div className={`half-seat ${pickHalfHover==='seat'?'active':''}`}>
            <span className="half-seat-hint" role="status">{pickHalfHover==='seat'
              ?'观众席已高亮 · 单击进入观众席，整局交给策略'
              :pickHalfHover
                ?`${pickHalfHover==='red'?'红方':'蓝方'}阵地已高亮 · 单击确认，进入${pickHalfHover==='red'?'红方':'蓝方'}机体选择`
                :'移到战场左 / 右半区选边 · 移到场外观众席则观战'}</span>
            <button onClick={()=>setJoinHidden(true)}><Video size={13}/>观众席</button>
          </div>
        </>}
        {pickMode&&<div className="pilot-pick pick-robot">
          <div className="pilot-pick-head"><span>赛前部署</span><b>选择机体</b><small>CHOOSE YOUR ROBOT</small></div>
          <div className="pilot-pick-actions"><button onClick={()=>setPickStage('side')}>重新选边</button><button onClick={()=>setJoinHidden(true)}>观众席</button></div>
          <p className="pilot-pick-hint">鼠标靠近机体 · 镜头自动贴近该机体，单击选定后进入赛前阵容审视</p>
        </div>}
        {pickMode&&pickHoverRobot&&(()=>{const team=frame.robots.filter(r=>r.team===pickHoverRobot.team&&r.role!=='aerial').sort((a,b)=>a.slot-b.slot);return <RobotPickShot frame={frame} metadata={metadata} r={pickHoverRobot} models={models} index={Math.max(0,team.findIndex(r=>r.id===pickHoverRobot.id))} count={team.length}/>;})()}
        {startFlash>0&&!prematch&&<StartFlash key={startFlash}/>}
        {post==='victory'&&<Victory frame={frame}/>}
        {post==='results'&&<Results paused={capturingMatch&&hidden} frame={frame} metadata={metadata} stats={stats.current} images={images} auto={!sawMvp.current} onNext={openHighlights} onClose={()=>setPost(null)}/>}
        {post==='mvp'&&mvpResult&&<MvpCard mvp={mvpResult} metadata={metadata} image={images[`${mvpResult.robot.model_asset}|${mvpResult.robot.team}|showcase`]} onBack={()=>setPost('results')} onClose={()=>setPost(null)}/>}
        {post==='highlight'&&(reelReady?<HighlightHud clips={highlightClips} index={reelIndex} frame={frame} side={reelSide} onDone={()=>closeHighlights('mvp')}/>:reelPending?<div className="hl-notice"><span className="hl-badge">HIGHLIGHT</span><p>正在从本场回放中剪出高光片段…</p></div>:highlightClips.length&&frame?<Highlights clips={highlightClips} frame={frame} metadata={metadata} images={images} onDone={()=>closeHighlights('mvp')}/>:<div className="hl-notice"><span className="hl-badge">HIGHLIGHT</span><p>{frame?'本局没有留下可用的高光素材：素材从裁判事件里剪，不会凭空补镜头。':'回放数据不可用'}</p><button className="hl-hud-skip" onClick={()=>closeHighlights('mvp')}>进入 MVP 结算</button></div>)}</div>
      <div className="transport"><button id="pause" className="play-button" disabled={!busy&&!replay} onClick={()=>control('pause')}>{playing?<Pause size={16}/>:<Play size={16}/>}<span>{playing?'暂停':'继续'}</span></button><div className="timeline"><input id="timeline" type="range" min={0} max={replay?replay.frames.length-1:frame.duration/(frame.dt||.05)} value={replay?Math.floor(replayPosition):frame.tick} disabled={!replay} onChange={e=>seek(Number(e.target.value))}/><div><span>{clock(frame.time)}</span><span>{replay?'拖动以定位回放':'实时仿真'} / {clock(frame.duration)}</span></div></div><select id="speed" value={currentSpeed} onChange={e=>control('speed',Number(e.target.value))}>{[.5,1,2,4,8].map(s=><option key={s} value={s}>{s}×</option>)}</select><button id="stop" className="icon-button" title="结束比赛" aria-label="结束比赛" disabled={!busy||!!replay} onClick={()=>control('stop')}><Square size={14}/></button><span className="transport-separator"/><button id="download" className="icon-button" title="导出回放" aria-label="导出回放" onClick={exportReplay}><ArrowDownToLine size={17}/></button><button id="load" className="icon-button" title="载入回放" aria-label="载入回放" onClick={()=>fileInput.current?.click()}><ArrowUpFromLine size={17}/></button>{replay&&sourceRef.current&&'id' in sourceRef.current&&matches.some(m=>m.id===(sourceRef.current as {id:string}).id&&m.has_video)&&<button onClick={()=>openVideo((sourceRef.current as {id:string}).id)}>播放 MP4</button>}{replay&&<button id="live" className="back-live" onClick={backToLive}>实时</button>}<input ref={fileInput} id="replay-file" type="file" accept=".json" hidden onChange={importReplay}/></div>
      {focus&&<div className="robot-inspector"><div className="inspector-title"><Crosshair size={16} style={{color:TEAM_COLORS[focus.team]}}/><span>{focus.team==='red'?'R':'B'}{focus.slot}<strong>{ROLE_NAMES[focus.role]}</strong></span><small>LV {focus.level}</small></div><div className="inspector-stat"><span>生命</span><strong>{focus.role==='aerial'?'不适用':Math.ceil(focus.hp)}<small>{focus.role==='aerial'?(focus.support_active?' / 空中支援':' / 停机待命'):` / ${focus.max_hp}`}</small></strong></div><div className="inspector-stat"><span>武器热量</span><div className="stat-meter heat"><i style={{width:`${focus.max_heat>0?focus.heat/focus.max_heat*100:0}%`}}/></div><small>{focus.overheated?'冷却中':Math.ceil(focus.max_heat>0?focus.heat/focus.max_heat*100:0)+'%'}</small></div><div className="inspector-stat"><span>裁判底盘能量</span><div className="stat-meter energy"><i style={{width:`${Math.min(100,(focus.energy||0)/400)}%`}}/></div><small>{Math.floor(Math.min(100,(focus.energy||0)/400))}% / 40 kJ</small></div><div className="inspector-stat"><span>击杀 / 伤害</span><strong>{focus.kills}<small> / {Math.floor(focus.damage)}</small></strong></div><div className="inspector-stat"><span>高程 / 速度</span><strong>{(focus.z||0).toFixed(1)}<small>m / {Math.hypot(focus.vx||0,focus.vy||0).toFixed(1)} m/s</small></strong></div></div>}
      {focus?.mass_kg&&<div className="hardware-inspector"><span>{focus.design_name}</span><span>整机 {focus.mass_kg.toFixed(2)} kg</span><span>驱动 {Math.round(focus.motor_power_w||0)} W</span><span>电池 {(focus.battery_remaining_wh||0).toFixed(1)} Wh</span><span>{focus.role==='aerial'?`支援 / ${focus.support_active?'飞行':'待命'}`:`电容 ${Math.round(focus.supercap_energy_j||0)} / 1800 J`}</span><span>{focus.charging_power_w?`无线充电 ${Math.round(focus.charging_power_w)} W`:focus.grounded?'已接地':'腾空'}</span></div>}
    </>:<div className="loading-app"><Activity size={20}/>{live?'选择阵容与策略，开始这场对战。':'连接 Rust 仿真引擎…'}</div>}</section>
    {frame&&<TelemetryPanel frame={frame} selected={selected} onSelect={selectRobot} replay={!!replay} events={log} eventText={eventText}/>}
    </main></>:page==='settings'?<BattleSettings initialSeason={season}/>:page==='gallery'?
    <section className="archive-page gallery-page"><div className="gallery-tabs" role="tablist" aria-label="策略库内容">{([['strategies','策略',LibraryBig],['models','机器人模型',Palette]] as const).map(([id,label,Icon])=><button key={id} role="tab" aria-selected={galleryTab===id} className={galleryTab===id?'active':''} onClick={()=>setGalleryTab(id)}><Icon size={15}/>{label}{id==='models'&&customs.length?<b>{customs.length}</b>:null}</button>)}</div>
      {galleryTab==='strategies'?<Suspense fallback={<div className="loading-app"><Activity size={20}/>载入策略库…</div>}><StrategyGallery refreshKey={galleryKey} onBattle={entry=>{if(busy||launching||capturing){setError('请等待当前对局或录制结束');return;}if(entry.mode==='adaptive'){setMap(strategySeason(entry)==='2027'?'rmuc2027':'rmuc2026');enterBattle('deck');setShowDecks(true);return;}if(!catalog[entry.key]){setError('这份策略暂不能用于全队对战');return;}const season=strategySeason(entry);setMap(season==='2027'?'rmuc2027':'rmuc2026');setLineups(v=>({...v,[season]:registeredLineup(entry)}));setRed(entry.key);setBlue(entry.key);enterBattle('standard');setShowMatchmaker(true);}} onUpload={()=>{setTrainingMode(matchMode==='deck'?'adaptive':'team');setShowSubmit(true);}}/></Suspense>:<><div className="archive-heading"><div><span className="eyebrow">ROBOT MODELS</span><h1>给机器人换上你的模型。</h1><p>上传 .glb 外观并选择它替换的型号；比赛仍按原型号的硬件与规则仿真，在「机器人外观」中为每方选用。</p></div></div><ModelWorkshop models={models} customs={customs} onChanged={refreshCatalog}/></>}</section>:
    <section className="archive-page"><div className="archive-heading"><div><span className="eyebrow">{page==='history'?'MATCH JOURNAL':'STRATEGY RANKINGS'}</span><h1>{page==='history'?'每一场对战，都有记录。':'让结果决定排名。'}</h1><p>{page==='history'?'比赛结果、策略版本和完整回放保存在本机。':'按策略版本累计 Elo；手动结束和含策略错误的比赛不计分。'}</p></div><button onClick={refreshHistory}><RotateCw size={14}/>刷新</button></div>{page==='history'?<MatchHistory matches={matches} saving={videoSaving} onVideo={openVideo} onReplay={openReplay} onDelete={setPendingDelete} onBattle={()=>navigatePage('arena')}/>:<div className="table-shell"><table><thead><tr><th>排名</th><th>策略 / 版本</th><th>控制模式</th><th>Elo</th><th>胜 / 负 / 平</th><th>胜率</th></tr></thead><tbody>{standings.map((s,i)=><tr key={s.identity}><td className="ranking-number">{String(i+1).padStart(2,'0')}</td><td><strong>{strategyDisplayName(s)}</strong><small>{s.version}</small></td><td>{MODE_LABELS[s.mode]}</td><td className="elo-value">{Math.round(s.rating)}</td><td>{s.wins} / {s.losses} / {s.draws}<small>{s.games} 场</small></td><td>{Math.round(s.wins/s.games*100)}%</td></tr>)}</tbody></table>{!standings.length&&<div className="empty-archive"><Trophy size={28}/><p>两份不同策略完成有效比赛后，排行榜开始累计。</p></div>}</div>}</section>}
    <footer><span>{page==='arena'&&frame?`${frameSeason(frame)==='2027'?'RMUC 2027':'RMUC 2026'} V1.0.0 · ${frame.robots.filter(r=>r.team==='red').length}v${frame.robots.filter(r=>r.team==='blue').length}`:`${SEASON_LABELS[season]} V1.0.0 · ${slots.length}v${slots.length}`} / 忽略飞镖、雷达与电子对抗{(page==='arena'&&frame?frameSeason(frame):season)==='2026'?' / 哨兵统一为步兵':''}</span><span>{rec.capture?'● REC / 1080p':replay?'REPLAY PLAYER':'ROBOT STRATEGY LAB'}</span></footer>
    {showMatchmaker&&<StrategyMatchmaker catalog={catalog} red={red} blue={blue} season={season} onClose={()=>setShowMatchmaker(false)} onApply={(r,b,s,l)=>{setMap(s==='2027'?'rmuc2027':'rmuc2026');setLineups(v=>({...v,[s]:l}));setRed(r);setBlue(b);setShowMatchmaker(false);setMatchMode('standard');navigatePage('arena');}}/>}
    {videoMatch&&<div className="match-tool-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)setVideoMatch(null);}}><section className="mp4-player" role="dialog" aria-modal="true" aria-label="对局 MP4"><header><strong>对局 MP4 · {videoMatch.slice(0,8)}</strong><a href={`/api/matches/${encodeURIComponent(videoMatch)}/video`} download={`rmuc-${videoMatch}.mp4`}>下载 MP4</a><button aria-label="关闭 MP4" onClick={()=>setVideoMatch(null)}><X size={16}/></button></header><video key={videoMatch} controls autoPlay src={`/api/matches/${encodeURIComponent(videoMatch)}/video`}/></section></div>}
    {showDecks&&<DeckBuilder cards={seasonCards} strategies={seasonCatalog} controllers={freeControllers} onControllers={setFreeControllers} decks={decks} onChange={setDecks} onClose={()=>setShowDecks(false)} season={season} models={models}/>}
    {showTeamLineup&&<TeamLineupDialog models={models} value={teamLineup} onChange={setTeamLineup} onClose={()=>setShowTeamLineup(false)} season={season}/>}{pendingDelete&&<DeleteMatchDialog matches={pendingDelete} onCancel={()=>setPendingDelete(null)} onConfirm={onProgress=>deleteMatches(pendingDelete,onProgress)}/>}{showSubmit&&<UploadWizard initialMode={trainingMode} models={models} teamLineup={teamLineup} season={season} onClose={()=>setShowSubmit(false)} onSave={refreshCatalog} onGallery={()=>{setGalleryTab('strategies');navigatePage('gallery');}}/>}
    {/* 开始对战直接进场：45° 俯视就是选边界面，半区即那一方，场外看台即观众席。 */}
    <RecordingDock session={session} onOpenHistory={()=>navigatePage('history')}/>
    {showSkins&&<SkinPicker models={models} customs={customs} fielded={fielded} value={skins} onChange={setSkins} onClose={()=>setShowSkins(false)} onManage={()=>{setShowSkins(false);setGalleryTab('models');navigatePage('gallery');}}/>}
  </div>;
}
