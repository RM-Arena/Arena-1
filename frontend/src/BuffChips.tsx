import {Activity,BatteryCharging,Flame,Lock,Shield,ShieldOff,Sparkles,Swords,Thermometer} from 'lucide-react';
import type {BuffChip,BuffKind} from './buffs';

// The glyph each buff kind draws. Defence is a shield, vulnerability its broken twin, cooling a
// thermometer; the rest name themselves.
const ICONS:Record<BuffKind,typeof Shield>={attack:Swords,defense:Shield,vulnerability:ShieldOff,cooling:Thermometer,
  power:BatteryCharging,invulnerable:Sparkles,weak:Activity,heat:Flame,lock:Lock};

/**
 * A robot's buffs and debuffs as small circles with the final figure in them. `size` is the glyph,
 * the number rides beside it so it stays legible at broadcast scale.
 */
export function BuffChips({chips,size=11,className=''}:{chips:BuffChip[];size?:number;className?:string}){
  if(!chips.length)return null;
  return <span className={`buff-chips ${className}`}>{chips.map(c=>{
    const Icon=ICONS[c.kind];
    return <span key={c.kind} className={`buff-chip ${c.kind}`} title={c.title} aria-label={c.title} data-buff={c.kind}>
      <Icon size={size} strokeWidth={2.3}/><em>{c.text}</em>
    </span>;
  })}</span>;
}
