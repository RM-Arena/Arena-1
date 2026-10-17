export type VideoFormat='mp4'|'webm';
const MAX_BYTES=1024*1024*1024;

async function responseError(response:Response){
  try{const value=await response.json();return typeof value.detail==='string'?value.detail:typeof value.error==='string'?value.error:`视频导出失败（HTTP ${response.status}）`;}catch{return `视频导出失败（HTTP ${response.status}）`;}
}

export async function checkVideoExport(format:VideoFormat){
  if(format==='webm')return;
  const response=await fetch('/api/video-export');
  if(!response.ok)throw new Error(await responseError(response));
  if(!(await response.json()).mp4)throw new Error('MP4 转码组件不可用，请更新应用或重新运行环境安装。');
}

export async function prepareVideoExport(blob:Blob,format:VideoFormat,onProgress:(message:string)=>void=()=>{},duration?:number):Promise<Blob>{
  if(!blob.size)throw new Error('录像为空，请录制画面后再导出。');
  if(format==='webm')return blob;
  if(blob.size>MAX_BYTES)throw new Error('MP4 导出的原始录像不能超过 1 GiB。');
  onProgress('正在生成 MP4，请稍候…');
  const query=duration===undefined?'':`?duration=${duration.toFixed(3)}`;
  const response=await fetch('/api/video-export'+query,{method:'POST',headers:{'Content-Type':'video/webm'},body:blob});
  if(!response.ok)throw new Error(await responseError(response));
  const result=await response.blob();
  if(!result.size||!result.type.startsWith('video/mp4'))throw new Error('未能生成有效的 MP4 文件。');
  onProgress('正在保存 MP4…');
  return result;
}
