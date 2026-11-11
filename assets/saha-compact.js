(() => {
'use strict';
if(window.__sahaCompactCleanup)window.__sahaCompactCleanup();
function click(event){if(!(event.target instanceof Element))return;const arrow=event.target.closest('[data-track]');if(arrow){const track=document.getElementById(arrow.dataset.track);if(track)track.scrollBy({left:(arrow.dataset.step==='next'?-1:1)*Math.min(track.clientWidth*.8,330),behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});}document.querySelectorAll('.saha-more[open]').forEach(menu=>{if(!menu.contains(event.target)||event.target.closest('a'))menu.open=false;});}
function key(event){if(event.key==='Escape')document.querySelectorAll('.saha-more[open]').forEach(menu=>{menu.open=false;menu.querySelector('summary').focus();});}
document.addEventListener('click',click);document.addEventListener('keydown',key);window.__sahaCompactCleanup=()=>{document.removeEventListener('click',click);document.removeEventListener('keydown',key);};
})();
