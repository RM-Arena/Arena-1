import type {Metadata,TeamId} from './types';
export type FreeController={mode:'team'|'independent';strategy:string};
export type FreeControllers=Record<TeamId,FreeController>;
export type DeckPreset={name:string;decks:Record<TeamId,string[]>;controllers:FreeControllers;updated_at:number};
export const DEFAULT_FREE_CONTROLLERS:FreeControllers={red:{mode:'independent',strategy:'claude_opus55_xhigh_team'},blue:{mode:'independent',strategy:'claude_opus55_xhigh_hold'}};
export function isFreeBattle(meta:Metadata|null|undefined){return meta?.match_mode==='deck'||(!meta?.match_mode&&(meta?.teams.red.mode==='adaptive'||meta?.teams.blue.mode==='adaptive'));}
export function freeStartOptions(controllers:FreeControllers){return {red_control:controllers.red.mode,blue_control:controllers.blue.mode,...(controllers.red.mode==='team'?{red_team_strategy:controllers.red.strategy}:{}),...(controllers.blue.mode==='team'?{blue_team_strategy:controllers.blue.strategy}:{})};}
