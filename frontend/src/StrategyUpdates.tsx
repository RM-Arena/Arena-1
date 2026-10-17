import {useEffect,useState} from 'react';
import {CloudDownload,RotateCw} from 'lucide-react';

type Status={enabled:boolean;checking:boolean;version:string|null;count:number;checked_at:number|null;error:string|null};

export function StrategyUpdates(){
  const [status,setStatus]=useState<Status|null>(null),[requesting,setRequesting]=useState(false),[failed,setFailed]=useState(false);
  useEffect(()=>{let disposed=false,timer=0;
    const poll=async()=>{let checking=false;try{const r=await fetch('/api/strategy-library');if(!r.ok)throw new Error();const value:Status=await r.json();checking=value.checking;if(!disposed){setStatus(value);setFailed(false);}}catch{if(!disposed)setFailed(true);}finally{if(!disposed)timer=window.setTimeout(poll,checking?1500:5000);}};
    void poll();return()=>{disposed=true;window.clearTimeout(timer);};},[]);
  async function sync(){setRequesting(true);try{const r=await fetch('/api/strategy-library/sync',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});if(!r.ok)throw new Error();setStatus(await r.json());setFailed(false);}catch{setFailed(true);}finally{setRequesting(false);}}
  const busy=requesting||status?.checking;
  const message=failed?'暂时无法检查更新，本地策略仍可使用':!status?'正在读取更新状态…':!status.enabled?'在线更新已关闭':busy?'正在检查策略更新…':status.error?'更新暂不可用，继续使用本地策略':status.version?`已同步 ${status.count} 份在线策略`:'启动后自动获取最新策略';
  return <div className="sg-updates" role="status"><span title={status?.error||undefined}><CloudDownload size={14}/>{message}</span><button onClick={()=>void sync()} disabled={!status?.enabled||!!busy}><RotateCw size={13}/>{busy?'检查中…':'检查更新'}</button></div>;
}
