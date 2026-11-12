(() => {
'use strict';
if(window.__sahaCompactCleanup)window.__sahaCompactCleanup();
let frame=0,adminClicks=0,adminStarted=0;
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
 if(event.target.closest('footer [data-admin-entry-logo]')){
  const now=performance.now();
  if(!adminClicks||now-adminStarted>3000){adminClicks=0;adminStarted=now;}
  if(++adminClicks===5){adminClicks=0;window.location.assign('/admin');return;}
 }else adminClicks=0;
 const opener=event.target.closest('[data-review-open]');if(opener){document.getElementById('customer-review-dialog')?.showModal();}
 if(event.target.closest('[data-review-close]'))document.getElementById('customer-review-dialog')?.close();
 const link=event.target.closest('a[href^="#"]');
 if(link){const target=document.getElementById(link.getAttribute('href').slice(1)),fold=target?.closest('.compact-fold');if(fold)fold.open=true;}
 const arrow=event.target.closest('[data-track]');
 if(arrow&&!arrow.disabled){const track=document.getElementById(arrow.dataset.track);if(track)track.scrollBy({left:(arrow.dataset.step==='next'?-1:1)*Math.min(track.clientWidth*.8,330),behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});}
 document.querySelectorAll('.saha-more[open]').forEach(menu=>{if(!menu.contains(event.target)||event.target.closest('a'))menu.open=false;});
}
function key(event){if(event.key==='Escape')document.querySelectorAll('.saha-more[open]').forEach(menu=>{menu.open=false;menu.querySelector('summary').focus();});}
let reviewSaving=false,reviewId=null,reviewFingerprint=null;
async function submitReview(event){
 if(event.target.id!=='customer-review-form')return;event.preventDefault();if(reviewSaving)return;
 const form=event.target,status=document.getElementById('customer-review-status'),button=form.querySelector('[type="submit"]'),fields=new FormData(form),payload={customer_name:fields.get('customer_name').trim(),phone:fields.get('phone').trim(),message:fields.get('message').trim()};
 if(!payload.customer_name||!payload.phone||payload.message.length<2){status.textContent='نام، شماره همراه و نظرت را کامل کن.';return;}
 const fingerprint=JSON.stringify(payload);if(fingerprint!==reviewFingerprint){reviewId=crypto.randomUUID();reviewFingerprint=fingerprint;}reviewSaving=true;button.disabled=true;status.textContent='در حال ارسال…';
 try{const response=await fetch('/api/v1/reviews',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...payload,request_id:reviewId})});const data=await response.json();if(!response.ok||data.status!=='received')throw new Error(typeof data.detail==='string'?data.detail:'نظر ارسال نشد؛ اتصال به سرور سالن را بررسی کن.');status.textContent='نظرت برای بررسی به سالن رسید ♡ هنوز عمومی نشده.';form.reset();reviewId=null;reviewFingerprint=null;}catch(e){status.textContent=e instanceof SyntaxError?'نظر ارسال نشد؛ سرور دریافت نظر هنوز متصل نیست.':e.message;}finally{reviewSaving=false;button.disabled=false;}
}
document.addEventListener('submit',submitReview);
const observer=new MutationObserver(schedule);observer.observe(document.documentElement,{childList:true,subtree:true});
document.addEventListener('click',click);document.addEventListener('keydown',key);document.addEventListener('scroll',schedule,true);window.addEventListener('resize',schedule);schedule();
window.__sahaCompactCleanup=()=>{document.removeEventListener('submit',submitReview);observer.disconnect();cancelAnimationFrame(frame);document.removeEventListener('click',click);document.removeEventListener('keydown',key);document.removeEventListener('scroll',schedule,true);window.removeEventListener('resize',schedule);};
})();
