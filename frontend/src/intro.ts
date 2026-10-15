import type {TeamId} from './types';
// Pre-match lineup intro during the referee self-check: an opening, then each team's title card and one camera
// shot per robot, then a face-off. Same constants as INTRO in rmuc_arena/server.py; the server announces the
// self-check length and this schedule scales to it, so replays and live matches share one layout.
export const INTRO={open:5,team:2.4,faceoff:4.5,shot:2.4,shots:28.8,minShot:1};
export const shotSeconds=(robots:number)=>Math.min(INTRO.shot,Math.max(INTRO.minShot,INTRO.shots/Math.max(1,robots)));
export const introSeconds=(robots:number)=>Math.round((INTRO.open+2*INTRO.team+robots*shotSeconds(robots)+INTRO.faceoff)*100)/100;
export type IntroSegment={kind:'open'}|{kind:'team';team:TeamId}|{kind:'robot';team:TeamId;id:string;index:number;count:number}|{kind:'faceoff'};
export interface IntroCut{segment:IntroSegment;start:number;end:number;key:string}
export function introSchedule(robots:{id:string;team:TeamId;slot:number}[],duration:number):IntroCut[]{
  const shot=shotSeconds(robots.length),scale=duration/Math.max(.1,introSeconds(robots.length)),cuts:IntroCut[]=[];let at=0;
  const add=(segment:IntroSegment,seconds:number,key:string)=>{cuts.push({segment,start:at,end:at+seconds*scale,key});at+=seconds*scale;};
  add({kind:'open'},INTRO.open,'open');
  for(const team of ['red','blue'] as const){
    const list=robots.filter(r=>r.team===team).sort((a,b)=>a.slot-b.slot);
    add({kind:'team',team},INTRO.team,'team-'+team);
    list.forEach((r,index)=>add({kind:'robot',team,id:r.id,index,count:list.length},shot,'robot-'+r.id));
  }
  add({kind:'faceoff'},INTRO.faceoff,'faceoff');
  return cuts;
}
// The cut playing `elapsed` seconds into the intro, with its progress from 0 to 1.
export function introAt(cuts:IntroCut[],elapsed:number){
  if(!cuts.length)return null;
  const found=cuts.findIndex(c=>elapsed<c.end),i=found<0?cuts.length-1:found,cut=cuts[i];
  return {cut,index:i,progress:Math.max(0,Math.min(1,(elapsed-cut.start)/Math.max(.001,cut.end-cut.start))),length:cut.end-cut.start};
}
