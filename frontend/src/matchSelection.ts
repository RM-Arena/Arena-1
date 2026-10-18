import type {MatchRecord} from './types';

export function canDeleteMatch(match:MatchRecord){return match.status!=='running'&&match.status!=='initializing'&&match.video_status!=='processing';}
export function reconcileSelection(ids:Set<string>,matches:MatchRecord[]){
  const eligible=new Set(matches.filter(canDeleteMatch).map(m=>m.id));
  return new Set([...ids].filter(id=>eligible.has(id)));
}
export function selectionSummary(ids:Set<string>,matches:MatchRecord[]){
  const eligible=matches.filter(canDeleteMatch),selected=eligible.filter(m=>ids.has(m.id));
  return {eligible,selected,all:eligible.length>0&&selected.length===eligible.length,mixed:selected.length>0&&selected.length<eligible.length,bytes:selected.reduce((sum,m)=>sum+(m.replay_bytes||0)+(m.video_bytes||0),0)};
}

// Bound concurrency so selecting a large journal doesn't flood the control plane.
export async function deleteMatchRecords(ids:string[],request:(id:string)=>Promise<{ok:boolean;status:number}>,onProgress:(done:number)=>void=()=>{}){
  const deleted:string[]=[],failed:{id:string;message:string}[]=[];
  let cursor=0,completed=0;
  await Promise.all(Array.from({length:Math.min(4,ids.length)},async()=>{
    while(cursor<ids.length){
      const id=ids[cursor++];
      try{
        const response=await request(id);
        if(response.ok||response.status===404)deleted.push(id);
        else failed.push({id,message:response.status===409?'比赛仍在进行，结束后才能删除。':'删除失败，请稍后重试。'});
      }catch{failed.push({id,message:'无法连接服务器，请检查连接后重试。'});}
      onProgress(++completed);
    }
  }));
  return {deleted,failed};
}
