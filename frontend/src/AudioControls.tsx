import {Volume2,VolumeX} from 'lucide-react';
export function AudioControls({sound,volume,onToggle,onVolume,compact=false}:{sound:boolean;volume:number;onToggle:()=>void;onVolume:(value:number)=>void;compact?:boolean}){
  return <div className={`audio-controls ${compact?'compact':''}`}><button onClick={onToggle} aria-label={sound?'关闭声音':'开启声音'} aria-pressed={sound}>{sound?<Volume2 size={16}/>:<VolumeX size={16}/>}</button><label><span>BGM <output>{Math.round(volume*100)}%</output></span><input type="range" min={0} max={100} step={1} value={Math.round(volume*100)} onChange={e=>onVolume(Number(e.target.value)/100)} aria-label="BGM音量"/></label></div>;
}
