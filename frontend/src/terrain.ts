import type {Arena,Terrain} from './types';
export function pointInPolygon(x:number,y:number,points:number[][]){
 let inside=false;
 for(let i=0;i<points.length;i++){
  const a=points[i],b=points[(i+1)%points.length];
  const cross=(x-a[0])*(b[1]-a[1])-(y-a[1])*(b[0]-a[0]);
  if(Math.abs(cross)<1e-8&&x>=Math.min(a[0],b[0])-1e-8&&x<=Math.max(a[0],b[0])+1e-8&&y>=Math.min(a[1],b[1])-1e-8&&y<=Math.max(a[1],b[1])+1e-8)return true;
  if((a[1]>y)!==(b[1]>y)&&x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])inside=!inside;
 }
 return inside;
}
function surface(t:Terrain,x:number,y:number){
 if(t.kind==='ramp'){
  let p=t.axis==='y'?(y-t.y)/t.h:(x-t.x)/t.w;
  if(t.ramp_start&&t.ramp_end){const a=t.ramp_start,b=t.ramp_end,dx=b[0]-a[0],dy=b[1]-a[1];p=((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy);}else if(t.direction<0)p=1-p;
  return (t.base_elevation||0)+(t.elevation-(t.base_elevation||0))*Math.max(0,Math.min(1,p));
 }
 if(t.kind==='bumps'){const phase=((x-t.x)/(t.bump_pitch||.24))%1;return t.elevation+(t.bump_height||0)*(1-Math.cos(2*Math.PI*phase))/2;}
 if(t.edge_ramp_m&&t.polygon){const d=Math.min(...t.polygon.map((a,i)=>{const b=t.polygon![(i+1)%t.polygon!.length];return Math.abs((x-a[0])*(b[1]-a[1])-(y-a[1])*(b[0]-a[0]))/Math.hypot(b[0]-a[0],b[1]-a[1]);}));return (t.base_elevation||0)+(t.elevation-(t.base_elevation||0))*Math.min(1,d/t.edge_ramp_m);}
 return t.elevation;
}
export function terrainHeight(arena:Arena,x:number,y:number){
 const slope=arena.floor_slope_deg??(arena.name==='rmuc2026'?1.5:0);
 const floor=slope?Math.min(y,arena.height-y)*Math.tan(slope*Math.PI/180):0;
 return floor+Math.max(0,...arena.terrain.filter(t=>x>=t.x-1e-8&&x<=t.x+t.w+1e-8&&y>=t.y-1e-8&&y<=t.y+t.h+1e-8&&(!t.polygon||pointInPolygon(x,y,t.polygon))).map(t=>surface(t,x,y)));
}
