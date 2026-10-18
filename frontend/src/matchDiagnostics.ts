import type {MatchEvent,MatchRecord} from './types';

const STATUS:Record<string,string>={finished:'已完成',running:'运行中',initializing:'初始化',stopped:'手动结束',error:'运行错误',interrupted:'中断'};

export function isCleanFinish(match:MatchRecord){
  return match.status==='finished'&&!(match.result?.policy_errors);
}

export function matchStatus(match:MatchRecord){
  const errors=match.result?.policy_errors||0;
  if(match.status==='finished'&&errors>0)return {label:'异常完成',className:'error',detail:`策略异常 ${errors} 次 · 未计入 Elo`};
  return {label:STATUS[match.status]||match.status,className:match.status,detail:errors>0?`策略异常 ${errors} 次`:match.error||''};
}

// Older replay diagnostics have no id. Include team and controlled slots so two
// policies failing on the same tick remain separate events when replayed.
export function matchEventKey(event:MatchEvent){
  return event.id||JSON.stringify([event.tick,event.type,event.team,event.slots,event.robot,event.target,event.x,event.y,event.z,event.message,event.reason]);
}

export function policyErrorText(event:MatchEvent){
  const team=event.team==='red'?'红方':event.team==='blue'?'蓝方':'',scope=event.slots?.length?`${event.slots.join('、')} 号策略`:'全队策略';
  const timeout=event.message==='decision exceeded deadline';
  if(event.disabled===false)return `${team}${scope}：${timeout?'决策超时':event.message||'决策异常'}，本轮跳过，后续继续尝试`;
  // Missing disabled means a legacy diagnostic, recorded when errors always
  // disabled the policy immediately.
  const reason=timeout?(event.consecutive_timeouts?`连续 ${event.consecutive_timeouts} 次决策超时`:'决策超时'):event.message||'运行异常';
  return `${team}${scope}已停用：${reason}`;
}
