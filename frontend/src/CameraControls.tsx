import {Compass,Crosshair,Eye,RotateCw,Video} from 'lucide-react';
import type {CameraMode} from './types';

export const CAMERA_MODES=[
  {id:'orbit',label:'自由',key:'1',icon:RotateCw},
  {id:'top',label:'俯视',key:'2',icon:Eye},
  {id:'follow',label:'跟随',key:'3',icon:Crosshair},
  {id:'fpv',label:'第一视角',key:'4',icon:Compass},
  {id:'cinematic',label:'环绕',key:'5',icon:Video},
] as const;

export function CameraControls({mode,onChange,compact=false}:{mode:CameraMode;onChange:(mode:CameraMode)=>void;compact?:boolean}){
  return <div className={`camera-buttons ${compact?'camera-compact':''}`} role="group" aria-label="镜头模式">
    {CAMERA_MODES.map(({id,label,key,icon:Icon})=><button key={id} title={`${label}视角 (${key})`} aria-label={`${label}视角`} aria-pressed={mode===id} className={mode===id?'active':''} data-cam={id} data-sound="select" onClick={()=>onChange(id)}><Icon size={14}/><span>{label}</span>{compact&&<kbd>{key}</kbd>}</button>)}
  </div>;
}
