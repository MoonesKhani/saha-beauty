(() => {
'use strict';
if(document.body.dataset.collection!=='invite')return;
const text=document.getElementById('invite-text'),status=document.getElementById('invite-status');
let busy=false;
async function copy(){
 try{if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(text.value);status.textContent='متن دعوت کپی شد ♡';return true;}}catch(_){}
 text.focus();text.select();text.setSelectionRange(0,text.value.length);
 try{if(document.execCommand('copy')){status.textContent='متن دعوت کپی شد ♡';return true;}}catch(_){}
 status.textContent='کپی خودکار ممکن نشد؛ متن انتخاب‌شده رو از منوی گوشی کپی کن.';return false;
}
document.getElementById('copy-invite').addEventListener('click',()=>{if(!busy)copy();});
document.getElementById('share-invite').addEventListener('click',async()=>{
 if(busy)return;busy=true;const button=document.getElementById('share-invite');button.disabled=true;
 try{
  if(navigator.share){await navigator.share({title:'دعوت به سها',text:text.value});status.textContent='متن دعوت با ابزار اشتراک‌گذاری گوشی باز شد ♡';}
  else if(await copy())status.textContent='اشتراک‌گذاری مستقیم اینجا در دسترس نیست؛ متن کپی شد تا هرجا دوست داری بفرستی.';
 }catch(error){status.textContent=error.name==='AbortError'?'اشتراک‌گذاری لغو شد.':'اشتراک‌گذاری انجام نشد؛ می‌تونی متن رو کپی کنی.';}
 finally{busy=false;button.disabled=false;}
});
})();
