import type {MatchEvent} from './types';
export type BgmCue='home'|'setup'|'lobby'|'hangar'|'self_check'|'self_check_free'|'countdown'|'match'|'victory'|'results'|'mvp';
export const MUSIC:Record<BgmCue,{url:string;loop:boolean;gain:number}>={
  home:{url:'/assets/audio/arena-theme.m4a',loop:true,gain:.68},
  setup:{url:'/assets/audio/home.mp3',loop:true,gain:.68},
  lobby:{url:'/assets/audio/arena-theme.m4a',loop:true,gain:.68},
  hangar:{url:'/assets/audio/hangar.m4a',loop:true,gain:.62},
  // The lineup intro: RM matches use the setup theme, free battles their own track.
  self_check:{url:'/assets/audio/home.mp3',loop:true,gain:.74},
  self_check_free:{url:'/assets/audio/intro-free.m4a',loop:true,gain:.78},
  countdown:{url:'/assets/audio/countdown.m4a',loop:false,gain:.88},
  match:{url:'/assets/audio/summoning-glory.m4a',loop:true,gain:.88},
  victory:{url:'/assets/audio/victory.m4a',loop:true,gain:.85},
  results:{url:'/assets/audio/results-summary.m4a',loop:true,gain:.66},
  mvp:{url:'/assets/audio/mvp-fanfare.m4a',loop:true,gain:.78},
};
export interface AudioStage {page:string;hangar:boolean;modal?:boolean;free?:boolean;prematch:'self_check'|'countdown'|null;post:'victory'|'results'|'mvp'|null;status?:string|null;replay?:boolean;busy?:boolean;started?:boolean}
export function broadcastMusicCue(stage:AudioStage):BgmCue{
  if(stage.hangar)return 'hangar';
  if(stage.page==='home')return 'home';
  if(stage.page!=='arena')return 'lobby';
  if(stage.modal)return 'setup';
  if(stage.prematch)return stage.prematch==='self_check'&&stage.free?'self_check_free':stage.prematch;
  if(stage.post)return stage.post;
  if(stage.status==='finished')return 'results';
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
