import type {CatalogEntry,Role} from './types';
export type RobotChoice={id:string;card:CatalogEntry};
export type RobotGroup={model:number;name:string;role:Role;choices:RobotChoice[]};
const ORDER={balanced:0,assault:1,guard:2};
export function groupRobotCards(cards:Record<string,CatalogEntry>):RobotGroup[]{
  const groups=new Map<number,RobotGroup>();
  for(const [id,card] of Object.entries(cards)){
    if(card.mode!=='adaptive'||!card.robot)continue;
    let group=groups.get(card.robot);
    if(!group){group={model:card.robot,name:card.model_name||`${card.robot} 型机器人`,role:card.role||'infantry',choices:[]};groups.set(card.robot,group);}
    group.choices.push({id,card});
  }
  return [...groups.values()].sort((a,b)=>a.model-b.model).map(group=>({...group,choices:group.choices.sort((a,b)=>(a.card.preset?ORDER[a.card.preset.id]:3)-(b.card.preset?ORDER[b.card.preset.id]:3)||a.card.name.localeCompare(b.card.name))}));
}
export function filterRobotGroups(groups:RobotGroup[],query:string,role:Role|'all'){
  const search=query.trim().toLocaleLowerCase();
  return groups.filter(group=>(role==='all'||group.role===role)&&(!search||[String(group.model),group.name,...group.choices.flatMap(c=>[c.card.name,c.card.preset?.name||''])].some(text=>text.toLocaleLowerCase().includes(search))));
}
export function applyDeckTactic(deck:string[],cards:Record<string,CatalogEntry>,tactic:string){
  const choices=new Map(groupRobotCards(cards).map(group=>[group.model,group.choices.find(c=>c.card.preset?.id===tactic)?.id]));
  return deck.map(id=>choices.get(cards[id]?.robot||0)||id);
}
export function strategyLabel(card:CatalogEntry){return card.preset?.name||card.name;}
export function summarizeDeck(deck:string[]){
  const counts=new Map<string,number>();
  for(const id of deck)counts.set(id,(counts.get(id)||0)+1);
  return [...counts].map(([id,count])=>({id,count}));
}
