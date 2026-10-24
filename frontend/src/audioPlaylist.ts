import type {MatchEvent} from './types';
export type BgmCue='home'|'setup'|'lobby'|'hangar'|'self_check_free'|'pick'|'countdown'|'match'|'match_alt'|'victory'|'results'|'mvp'|'highlight';
// A cue's theme is a project asset: `*-theme.m4a` is committed next to the generated tracks, and the
// same recording is shipped as `.mp3` because some browsers (Chromium builds, VS Code's preview,
// the desktop shell) refuse to decode AAC. A machine may re-score any cue without touching code by
// dropping `<cue>-custom.m4a` (then `.mp3`) beside it — that slot is per-machine and never committed.
const theme=(cue:string)=>`/assets/audio/${cue}-theme.m4a`;
const themeMp3=(cue:string)=>`/assets/audio/${cue}-theme.mp3`;
const custom=(cue:string)=>[`/assets/audio/${cue}-custom.m4a`,`/assets/audio/${cue}-custom.mp3`];
// Playback level is derived from each recording's integrated loudness instead of being tuned by ear.
// The shipped masters span almost 30 dB (`mvp-theme` ≈ -36.8 LUFS, the `summoning-glory` sting
// ≈ -8.0 LUFS), so one fader position used to leave the post-match set nearly inaudible while the
// sting jumped 8.6 dB louder than the opening it follows. `lufs` below is the whole-file reading from
// `ffmpeg -af loudnorm=print_format=json`; `musicGain` turns it into the amplitude that puts every
// cue at MUSIC_LEVEL on the music bus. Re-measure and update that number after replacing a track —
// do not hand-tune a gain.
export const MUSIC_LEVEL=-16.5;
export const musicGain=(lufs:number)=>Math.round(Math.pow(10,(MUSIC_LEVEL-lufs)/20)*1000)/1000;
// Files a cue can play outside its own theme (`victory.m4a` is the silent-card fallback) carry their
// own reading so the fallback is not replayed at the cue's boost.
export const FALLBACK_LUFS:Record<string,number>={'/assets/audio/victory.m4a':-17.76};
export const MUSIC:Record<BgmCue,{url:string;loop:boolean;lufs:number;loopEnd?:number;override?:string|string[];fallback?:string|string[];then?:BgmCue}>={
  home:{url:'/assets/audio/arena-theme.m4a',loop:true,lufs:-18.21},
  setup:{url:'/assets/audio/home.mp3',loop:true,lufs:-17.73},
  lobby:{url:'/assets/audio/arena-theme.m4a',loop:true,lufs:-18.21},
  hangar:{url:'/assets/audio/hangar.m4a',loop:true,lufs:-17.91},
  // The pre-match screen is one screen: the walk-on intro with the side/chassis pick drawn over it,
  // scored by the prep theme from the moment the lineup appears until the countdown.
  pick:{url:theme('pick'),loop:true,lufs:-17.61,fallback:[themeMp3('pick')],override:custom('pick')},
  self_check_free:{url:'/assets/audio/intro-free.m4a',loop:true,lufs:-17.07},
  countdown:{url:'/assets/audio/countdown.m4a',loop:false,lufs:-15.59,fallback:['/assets/audio/countdown.mp3']},
  // From the moment the countdown shows "5" the match theme plays: its own recording once, and from
  // its end onwards the arena's long-standing sting on loop. The hand-off (`then`) is what keeps the
  // opening reading like a broadcast and the rest of the seven minutes scoring on the familiar theme.
  match:{url:theme('match'),loop:true,lufs:-16.58,fallback:[themeMp3('match')],override:custom('match'),
    then:'match_alt'},
  // The looping sting: the opening track's hand-off target and what a replay plays throughout. The
  // recording fades out into 2.6 s of silence, so the loop ends with the music: wrapping through the
  // tail would drop a hole into the middle of the match every time the sting repeated.
  match_alt:{url:'/assets/audio/summoning-glory.m4a',loop:true,lufs:-7.98,loopEnd:111.25,
    fallback:['/assets/audio/summoning-glory.mp3']},
  victory:{url:'/assets/audio/victory.m4a',loop:true,lufs:-17.76,fallback:['/assets/audio/victory.mp3']},
  // The post-match read sits in the same musical family as the pre-match build.
  results:{url:'/assets/audio/results-summary.m4a',loop:true,lufs:-18.06,fallback:[themeMp3('results')],override:custom('results')},
  mvp:{url:'/assets/audio/mvp-fanfare.m4a',loop:true,lufs:-18.02,fallback:[themeMp3('mvp'),
    // victory.m4a keeps the card scored in a browser that refuses AAC rather than leaving it silent.
    '/assets/audio/victory.m4a'],override:custom('mvp')},
  // Post-match highlight reel. The legacy `highlight.m4a` / `.mp3` drop-in names still work.
  highlight:{url:theme('highlight'),loop:true,lufs:-32.17,
    fallback:[themeMp3('highlight'),'/assets/audio/highlight.m4a','/assets/audio/highlight.mp3',
      '/assets/audio/victory.m4a'],override:custom('highlight')},
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
