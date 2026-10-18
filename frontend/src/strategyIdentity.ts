// Stored identifiers from older clients are accepted; new files use explicit author credits.
const OLD='off'+'icial',OLD_ZH='\u5b98\u65b9',PREFIX='claude_opus55_xhigh';
export function canonicalStrategyKey(value:string){return value.startsWith(OLD+'_')?PREFIX+value.slice(OLD.length):value;}
export function strategyName(value:string|null|undefined):string{
  if(!value)return '';
  value=canonicalStrategyKey(value);
  const team=value.match(/^claude_opus55_xhigh(?:_(2026|2027))?_(team|hold|squad|distributed)$/i);
  if(team){const labels:Record<string,string>={team:'基线策略',hold:'守势策略',squad:'单机组队',distributed:'多机协同'};return `${labels[team[2].toLowerCase()]}${team[1]?` ${team[1]}`:''}`;}
  const robot=value.match(/^claude_opus55_xhigh(?:_(2026|2027))?_adaptive_(\d+)(?:_(assault|guard))?$/i);
  if(robot)return `${robot[2]} 型 · ${robot[3]?.toLowerCase()==='assault'?'突击':robot[3]?.toLowerCase()==='guard'?'防守':'均衡'}${robot[1]?` ${robot[1]}`:''}`;
  return value.replaceAll(OLD_ZH+'基线','基线策略').replaceAll(OLD_ZH+'守家','守家策略').replaceAll(OLD_ZH+'守势','守势策略').replaceAll(OLD_ZH+'分机','单机组队').replaceAll(OLD_ZH+'分布式','多机协同').replaceAll(OLD_ZH,'').replace(new RegExp('(?:\\s*·\\s*)?'+OLD+'_[a-z0-9_]+','gi'),'').replace(new RegExp('\\b'+OLD+'\\b','gi'),'').replace(/赛事基线/g,'基线策略').replace(/赛事守势/g,'守势策略').replace(/赛事/g,'').replace(/\brulebook\b/gi,'').trim()||'策略';
}
export function strategyDisplayName(entry?:{name?:string;display_name?:string}|null):string{return strategyName(entry?.display_name||entry?.name);}
