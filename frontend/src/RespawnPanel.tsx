import {Check,Coins,Power} from 'lucide-react';
import type {CSSProperties} from 'react';
import type {Robot} from './types';
import './pilot.css';

/**
 * The pilot's respawn card, laid out like the referee client's: a title with the countdown, the
 * free-revive bar, and the two ways back side by side — buy the revive now, or take the free one
 * when the bar fills. A red-carded chassis never returns, so it gets its own wording instead of a
 * countdown that would never finish.
 */
export function RespawnPanel({robot,respawnLeft,respawnShare,gold,reviveCost,freePicked=false,onBuy,onFree}:{
  robot:Robot;respawnLeft:number;respawnShare:number;gold:number;reviveCost:number;freePicked?:boolean;
  onBuy:()=>void;onFree:()=>void;
}){
  const penalised=!!robot.red_card;
  const seconds=Math.max(0,respawnLeft);
  const share=Math.min(1,Math.max(0,respawnShare));
  return <div className={`pilot-respawn team-${robot.team}${penalised?' penalised':''}`} role="status"
    data-respawn-panel={robot.team} aria-label={penalised?'已判罚离场':'等待复活'}>
    <div className="respawn-head">
      {/* The dot doubles as a second progress readout, so the card reads at a glance from either end. */}
      <i className="respawn-ring" aria-hidden="true" style={{'--respawn-progress':`${Math.round(share*360)}deg`} as CSSProperties}/>
      <strong>{penalised?'判罚离场':'复活中'}</strong>
      <em>{penalised?'红牌':seconds>0?`${seconds}s`:'返场中'}</em>
    </div>
    {penalised
      ? <div className="respawn-tips"><b>TIPS</b><div>
          <p>本局已被红牌罚下，不能再复活；这台机器人不会回到战场。</p>
          <p>按 P 打开驾驶面板，可以选择另一台仍在场的机器人继续驾驶。</p>
        </div></div>
      : <>
        <div className={`respawn-bar${freePicked?' chosen':''}`} role="progressbar" aria-valuemin={0} aria-valuemax={100}
          aria-valuenow={Math.round(share*100)} title={`免费复活进度 ${Math.round(share*100)}%`}>
          <i style={{width:`${share*100}%`}}/>
        </div>
        <div className="respawn-choice">
          <button className="respawn-buy" disabled={gold<reviveCost} onClick={onBuy}
            aria-label={gold<reviveCost?`金币不足：立即复活需 ${reviveCost} 金币`:`花费 ${reviveCost} 金币立即复活`}>
            <Coins size={13}/><b>{gold<reviveCost?`${reviveCost} 金币不足`:`${reviveCost} 金币`}</b>
          </button>
          <span className="respawn-split" aria-hidden="true"/>
          <button className={`respawn-free${freePicked?' picked':''}`} aria-pressed={freePicked} aria-keyshortcuts="Y" onClick={onFree}>
            {freePicked?<Check size={13}/>:<Power size={13}/>}<b>免费复活</b><kbd>Y</kbd>
          </button>
        </div>
        <div className="respawn-tips"><b>TIPS</b><div>
          <p>免费复活：读条结束后返回战场，保留等级与经验，血量恢复 10%，30 秒无敌并进入虚弱（回己方补给区、基地或完全控制的前哨站增益卡解除，无敌至少保留到复活后 10 秒）。</p>
          <p>金币立即复活：血量恢复 100%，保留等级与经验；3 秒虚弱且无敌，4 秒内功率上限翻倍（不超过 200 W）。</p>
        </div></div>
        <small className="respawn-note">费用 = ROUNDUP(已进行分钟数)×80 + 等级×20 · 次数不限 · 复活瞬间镜头直接接到出生姿态</small>
      </>}
  </div>;
}
