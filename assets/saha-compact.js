(() => {
'use strict';
if(window.__sahaCompactCleanup)window.__sahaCompactCleanup();
let frame=0;
function syncArrows(){
 frame=0;
 document.querySelectorAll('[data-track]').forEach(arrow=>{
  const track=document.getElementById(arrow.dataset.track);if(!track)return;
  const max=Math.max(0,track.scrollWidth-track.clientWidth),position=Math.abs(track.scrollLeft);
  arrow.disabled=max<=1||(arrow.dataset.step==='prev'?position<=1:position>=max-1);
  if(arrow.dataset.track==='package-cards'){
   const label=arrow.closest('.compact-controls')?.querySelector('span');
   const text=max<=1?'همه پکیج‌ها اینجا هستن':'برای دیدن پکیج‌ها ورق بزن';
   if(label&&label.textContent!==text)label.textContent=text;
  }
 });
}
function schedule(){if(!frame)frame=requestAnimationFrame(syncArrows);}
function click(event){
 if(!(event.target instanceof Element))return;
 const link=event.target.closest('a[href^="#"]');
 if(link){const target=document.getElementById(link.getAttribute('href').slice(1)),fold=target?.closest('.compact-fold');if(fold)fold.open=true;}
 const arrow=event.target.closest('[data-track]');
 if(arrow&&!arrow.disabled){const track=document.getElementById(arrow.dataset.track);if(track)track.scrollBy({left:(arrow.dataset.step==='next'?-1:1)*Math.min(track.clientWidth*.8,330),behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});}
 document.querySelectorAll('.saha-more[open]').forEach(menu=>{if(!menu.contains(event.target)||event.target.closest('a'))menu.open=false;});
}
function key(event){if(event.key==='Escape')document.querySelectorAll('.saha-more[open]').forEach(menu=>{menu.open=false;menu.querySelector('summary').focus();});}
const observer=new MutationObserver(schedule);observer.observe(document.documentElement,{childList:true,subtree:true});
document.addEventListener('click',click);document.addEventListener('keydown',key);document.addEventListener('scroll',schedule,true);window.addEventListener('resize',schedule);schedule();
window.__sahaCompactCleanup=()=>{observer.disconnect();cancelAnimationFrame(frame);document.removeEventListener('click',click);document.removeEventListener('keydown',key);document.removeEventListener('scroll',schedule,true);window.removeEventListener('resize',schedule);};
})();
