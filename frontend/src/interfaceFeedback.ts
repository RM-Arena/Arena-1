import {useEffect} from 'react';
import type {ArenaAudio,InterfaceCue} from './media';

const controls='button,a[href],summary,[role="button"],[role="tab"],input[type="checkbox"],input[type="radio"]';
function target(event:Event){return event.target instanceof Element?event.target.closest<HTMLElement>(controls):null;}
function available(el:HTMLElement|null):el is HTMLElement {
  return !!el&&!el.matches(':disabled,[aria-disabled="true"]')&&!el.closest('[inert]');
}
function clickCue(el:HTMLElement):InterfaceCue {
  if(el.dataset.sound)return el.dataset.sound as InterfaceCue;
  if(el.closest('[data-id],.bc-card'))return 'select';
  if(el.matches('.primary,.home-brief-cta,.home-menu-item'))return 'confirm';
  if(el.matches('.dialog-close')||el.getAttribute('aria-label')?.includes('关闭'))return 'back';
  if(el.matches('.team-lineup-button,#edit-decks,#open-submission'))return 'open';
  if(el.closest('nav')||el.matches('[role="tab"],[role="radio"]'))return 'select';
  return 'click';
}

// Capture covers dialogs, keyboard-generated clicks, and controls on every page.
export function useInterfaceFeedback(audio:ArenaAudio){
  useEffect(()=>{
    const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
    const rings=new Set<HTMLElement>();
    const hover=(e:Event)=>{const el=target(e);if(!available(el))return;
      if(e instanceof PointerEvent&&(e.pointerType!=='mouse'||e.relatedTarget instanceof Node&&el.contains(e.relatedTarget)))return;
      audio.ui('hover');};
    const click=(e:MouseEvent)=>{const el=target(e);if(!available(el))return;
      audio.ui(clickCue(el));
      if(reduced.matches)return;
      el.animate([{filter:'brightness(1.45)'},{filter:'brightness(1)'}],{duration:220});
      const box=el.getBoundingClientRect(),ring=document.createElement('i');ring.className='interface-ripple';
      ring.style.left=`${e.detail?e.clientX:box.x+box.width/2}px`;ring.style.top=`${e.detail?e.clientY:box.y+box.height/2}px`;
      (document.fullscreenElement||document.querySelector('.page-fullscreen')||document.body).append(ring);rings.add(ring);
      const animation=ring.animate([{opacity:.8,transform:'translate(-50%,-50%) scale(.3)'},{opacity:0,transform:'translate(-50%,-50%) scale(3)'}],{duration:430,easing:'ease-out'});
      animation.onfinish=()=>{ring.remove();rings.delete(ring);};
    };
    const change=(e:Event)=>{if(e.target instanceof HTMLSelectElement||e.target instanceof HTMLInputElement&&['checkbox','radio','range'].includes(e.target.type))audio.ui('select');};
    document.addEventListener('pointerover',hover,true);document.addEventListener('focusin',hover,true);
    document.addEventListener('click',click,true);document.addEventListener('change',change,true);
    return()=>{document.removeEventListener('pointerover',hover,true);document.removeEventListener('focusin',hover,true);
      document.removeEventListener('click',click,true);document.removeEventListener('change',change,true);for(const ring of rings)ring.remove();};
  },[audio]);
}
