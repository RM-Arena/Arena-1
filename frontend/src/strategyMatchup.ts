import type {CatalogEntry,Season,TeamLineup} from './types';
import {DEFAULT_LINEUPS} from './TeamLineup';
export const strategySeason=(s:CatalogEntry):Season=>s.season||'2026';
export const registeredLineup=(s:CatalogEntry):TeamLineup=>s.team_lineup||DEFAULT_LINEUPS[strategySeason(s)];
// Each side runs the lineup its own strategy was developed on, so only the season has to match.
export function compatibleStrategies(a?:CatalogEntry,b?:CatalogEntry){return !!a&&!!b&&strategySeason(a)===strategySeason(b);}
export const lineupText=(s:CatalogEntry)=>Object.entries(registeredLineup(s)).map(([slot,model])=>`${slot}号:${model}`).join(' / ');
