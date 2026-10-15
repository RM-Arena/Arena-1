// Storage keys stay stable for saved decks, Elo and imported replays. Every UI
// surface uses a display name, including records written before profiles existed.
export function strategyName(value:string|null|undefined):string{
  if(!value)return '';
  const team=value.match(/^official(?:_(2026|2027))?_(team|hold|squad|distributed)$/i);
  if(team){const labels:Record<string,string>={team:'基线策略',hold:'守家策略',squad:'单机组队',distributed:'多机协同'};return `${team[1]==='2027'&&team[2].toLowerCase()==='hold'?'守势策略':labels[team[2].toLowerCase()]}${team[1]?` ${team[1]}`:''}`;}
  const robot=value.match(/^official(?:_(2026|2027))?_adaptive_(\d+)(?:_(assault|guard))?$/i);
  if(robot)return `${robot[2]} 型 · ${robot[3]?.toLowerCase()==='assault'?'突击':robot[3]?.toLowerCase()==='guard'?'防守':'均衡'}${robot[1]?` ${robot[1]}`:''}`;
  return value.replace(/官方基线/g,'基线策略').replace(/官方守家/g,'守家策略').replace(/官方守势/g,'守势策略').replace(/官方分机/g,'单机组队').replace(/官方分布式/g,'多机协同').replace(/官方/g,'').replace(/(?:\s*·\s*)?official_[a-z0-9_]+/gi,'').replace(/\bofficial\b/gi,'').trim()||'策略';
}
export function strategyDisplayName(entry?:{name?:string;display_name?:string}|null):string{
  return strategyName(entry?.display_name||entry?.name);
}
