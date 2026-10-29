import type {TeamId} from './types';
// Pre-match lineup intro during the referee self-check: an opening, then each team's title card and one camera
// shot per robot, then a face-off. Same constants as INTRO in rmuc_arena/server.py; the server announces the
// self-check length and this schedule spreads it, so replays and live matches share one layout.
export const INTRO={open:5,team:2.4,faceoff:4.5,shot:2.4,shots:28.8,minShot:2};
// No card, chassis or face-off may flash past: each one holds the screen for at least this long. A window
// that is too short is lengthened on the server (`extend_prematch`) instead of being compressed here.
export const MIN_CUT=2;
export const shotSeconds=(robots:number)=>Math.min(INTRO.shot,Math.max(INTRO.minShot,INTRO.shots/Math.max(1,robots)));
export const introSeconds=(robots:number)=>Math.round((INTRO.open+2*INTRO.team+robots*shotSeconds(robots)+INTRO.faceoff)*100)/100;
/** Shortest walk-on that still shows both cards, every chassis and the face-off for `MIN_CUT` seconds. */
export const introMinimumSeconds=(robots:number)=>Math.round((robots+4)*MIN_CUT*100)/100;
export type IntroSegment={kind:'open'}|{kind:'team';team:TeamId}|{kind:'robot';team:TeamId;id:string;index:number;count:number}|{kind:'faceoff'};
export interface IntroCut{segment:IntroSegment;start:number;end:number;key:string}
export function introSchedule(robots:{id:string;team:TeamId;slot:number}[],duration:number):IntroCut[]{
  const shot=shotSeconds(robots.length);
  const layout:{segment:IntroSegment;seconds:number;key:string}[]=[{segment:{kind:'open'},seconds:INTRO.open,key:'open'}];
  for(const team of ['red','blue'] as const){
    const list=robots.filter(r=>r.team===team).sort((a,b)=>a.slot-b.slot);
    layout.push({segment:{kind:'team',team},seconds:INTRO.team,key:'team-'+team});
    list.forEach((r,index)=>layout.push({segment:{kind:'robot',team,id:r.id,index,count:list.length},seconds:shot,key:'robot-'+r.id}));
  }
  layout.push({segment:{kind:'faceoff'},seconds:INTRO.faceoff,key:'faceoff'});
  // The natural layout is 43 s for a full lineup; a shorter window (a picker that ate the clock, a long
  // lineup, a replay cut short) is spread over the same segments, but never below `MIN_CUT` each. The
  // floor wins when the caller did not extend the clock, so the reel still ends on the face-off.
  const floor=layout.length*MIN_CUT,natural=layout.reduce((sum,item)=>sum+item.seconds,0);
  const span=Math.max(floor,duration),spare=span-floor,slack=Math.max(1e-6,natural-floor);
  const cuts:IntroCut[]=[];let at=0;
  for(const item of layout){
    const seconds=MIN_CUT+spare*Math.max(0,item.seconds-MIN_CUT)/slack;
    cuts.push({segment:item.segment,start:at,end:at+seconds,key:item.key});
    at+=seconds;
  }
  return cuts;
}
// The cut playing `elapsed` seconds into the intro, with its progress from 0 to 1.
export function introAt(cuts:IntroCut[],elapsed:number){
  if(!cuts.length)return null;
  const found=cuts.findIndex(c=>elapsed<c.end),i=found<0?cuts.length-1:found,cut=cuts[i];
  return {cut,index:i,progress:Math.max(0,Math.min(1,(elapsed-cut.start)/Math.max(.001,cut.end-cut.start))),length:cut.end-cut.start};
}
