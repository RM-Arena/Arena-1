import type {MatchEvent} from './types';
export type BgmCue='home'|'setup'|'lobby'|'hangar'|'self_check_free'|'pick'|'countdown'|'match'|'match_alt'|'victory'|'results'|'mvp'|'highlight';
// A cue may be re-scored without touching code: `<cue>-theme.m4a` (or `.mp3`) is tried before the file
// the repository ships, so an uploaded track never has to overwrite a checked-in asset. MP3 stays in
// every chain because some browsers (Chromium builds, VS Code's preview) refuse to decode AAC.
const slot=(cue:string)=>[`/assets/audio/${cue}-theme.m4a`,`/assets/audio/${cue}-theme.mp3`];
// `uploadOnly` marks a cue that deliberately has no shipped track: the in-match theme only exists when
// the operator installs one, and the repository's old competition sting is kept out of the match.
export const MUSIC:Record<BgmCue,{url:string;loop:boolean;gain:number;uploadOnly?:boolean;override?:string|string[];fallback?:string|string[];then?:BgmCue}>={
  home:{url:'/assets/audio/lobby.m4a',loop:true,gain:.68},
  setup:{url:'/assets/audio/home.mp3',loop:true,gain:.68},
  lobby:{url:'/assets/audio/lobby.m4a',loop:true,gain:.68},
  hangar:{url:'/assets/audio/hangar.m4a',loop:true,gain:.62},
  // The pre-match screen is one screen: the walk-on intro with the side/chassis pick drawn over it.
  // `pick-theme.*` scores the whole stretch (from the moment the lineup appears until the countdown),
  // and a machine without an installed track keeps the shipped intro theme instead of going silent.
  pick:{url:'/assets/audio/home.mp3',loop:true,gain:.74,override:slot('pick')},
  self_check_free:{url:'/assets/audio/intro-free.m4a',loop:true,gain:.78},
  countdown:{url:'/assets/audio/countdown.m4a',loop:false,gain:.88,fallback:['/assets/audio/countdown.mp3']},
  // From the moment the countdown shows "5" the match theme plays: the installed recording first,
  // once, and from its end onwards the repository's own sting on loop. The hand-off (`then`) is what
  // keeps the opening reading like a broadcast and the rest of the seven minutes scoring on the theme
  // the arena always had.
  match:{url:'/assets/audio/match-theme.m4a',loop:true,gain:.88,uploadOnly:true,
    fallback:['/assets/audio/match-theme.mp3'],then:'match_alt'},
  // The repository's own sting: the opening track's hand-off target and what a replay plays throughout.
  match_alt:{url:'/assets/audio/summoning-glory.m4a',loop:true,gain:.88,
    fallback:['/assets/audio/summoning-glory.mp3']},
  victory:{url:'/assets/audio/victory.m4a',loop:true,gain:.85,fallback:['/assets/audio/victory.mp3']},
  // The data panel is scored with the shipped intro theme, so the post-match read and the pre-match
  // build sit in one musical family; `results-theme.*` re-scores just this screen.
  results:{url:'/assets/audio/home.mp3',loop:true,gain:.6,override:slot('results')},
  mvp:{url:'/assets/audio/mvp.m4a',loop:true,gain:.78,override:slot('mvp'),
    // victory.m4a keeps the card scored in a browser that refuses AAC rather than leaving it silent.
    fallback:['/assets/audio/victory.m4a']},
  // Post-match highlight reel. Dropping your own licensed track at `highlight.m4a` (the original
  // convention) or `highlight-theme.m4a|mp3` replaces it with no code change; without one the victory
  // sting keeps the reel scored.
  highlight:{url:'/assets/audio/highlight.m4a',loop:true,gain:.8,override:slot('highlight'),
    fallback:['/assets/audio/highlight.mp3','/assets/audio/victory.m4a']},
};
export interface AudioStage {page:string;hangar:boolean;modal?:boolean;free?:boolean;picking?:boolean;prematch:'self_check'|'countdown'|null;post:'victory'|'results'|'mvp'|'highlight'|null;status?:string|null;replay?:boolean;busy?:boolean;started?:boolean}
export function broadcastMusicCue(stage:AudioStage):BgmCue|null{
  if(stage.hangar)return 'hangar';
  if(stage.page==='home')return 'home';
  if(stage.page!=='arena')return 'lobby';
  if(stage.modal)return 'setup';
  if(stage.prematch==='countdown')return 'match';
  // The RM pre-match — walk-on intro plus the side/chassis pick drawn on top — is one cue, so the
  // pick track starts the moment the lineup appears, not when the overlay happens to be up. Free
  // battles keep their own walk-on track, but the pick overlay still switches to the prep music.
  if(stage.picking)return 'pick';
  if(stage.prematch)return stage.free?'self_check_free':'pick';
  if(stage.post)return stage.post;
  // A finished live match leaves its last frame (and the setup panel) on screen while the next one is
  // prepared: that stretch belongs to no cue, so the arena goes quiet instead of looping the data
  // panel's theme. A replay of a finished match still reads as its data panel.
  if(stage.status==='finished')return stage.replay?'results':null;
  if(stage.status==='running'||stage.started)return 'match';
  return 'setup';
}
export function audibleEvents(events:MatchEvent[]){
  const judged=events.filter(e=>['hit','base_hit','outpost_hit'].includes(e.type)&&e.x!==undefined&&e.y!==undefined);
  // The referee emits both a judged hit and a generic contact for the same projectile.
  // Keep the richer steel impact once, rather than adding a second dry tap over it.
  return events.filter(e=>e.type!=='impact'||!judged.some(h=>h.tick===e.tick&&h.team===e.team&&
    Math.abs(h.x!-e.x!)<.002&&Math.abs(h.y!-e.y!)<.002&&Math.abs((h.z??0)-(e.z??0))<.002));
}
