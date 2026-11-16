(()=>{'use strict';
const $=id=>document.getElementById(id);
async function api(path,body){
 const response=await fetch('/api/v1/auth/'+path,{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
 let data={};if(response.status!==204)data=await response.json();
 if(!response.ok){const error=Error(typeof data.detail==='string'?data.detail:'درخواست انجام نشد؛ کمی بعد تلاش کنید.');error.status=response.status;throw error;}
 return data;
}
function digits(value){return value.replace(/[۰-۹]/g,c=>'۰۱۲۳۴۵۶۷۸۹'.indexOf(c));}
const reservation=$('reservation-form');
const bookingPolicy=reservation?fetch('/api/v1/booking/catalog',{cache:'no-store'}).then(async r=>{if(!r.ok)throw Error('بررسی امکان رزرو انجام نشد.');return (await r.json()).requires_login===true;}):null;
// Only known same-origin reservation pages are valid login return targets.
function returnTarget(){
 try{const raw=new URLSearchParams(location.search).get('return_to');if(!raw)return null;const url=new URL(raw,location.origin);return url.origin===location.origin&&['/booking.html','/bridal.html','/birthday.html'].includes(url.pathname)?url.pathname+url.search:null;}catch{return null;}
}
function loginUrl(){return '/login.html?return_to='+encodeURIComponent(location.pathname+location.search);}
function redirectToLogin(){location.assign(loginUrl());}
async function ensureBooking(required){
 if(!reservation)return true;
 if(typeof required!=='boolean')required=await bookingPolicy;
 if(!required)return true;
 try{
  const me=await api('me');const phone=$('reservation-phone');if(phone){phone.value=me.phone;phone.readOnly=true;}return true;
 }catch(error){if(error.status===401){redirectToLogin();return false;}throw error;}
}
window.SahaCustomer={ensureBooking,redirectToLogin};
// Attach the rejection handler immediately even while other deferred assets load.
if(bookingPolicy)bookingPolicy.catch(()=>{});
async function init(){
 if(reservation){
  if(!await ensureBooking())return;
  const capability=await api('capabilities').catch(()=>({enabled:false}));
  if(!capability.enabled||!$('customer-bar'))return;
  $('customer-bar').querySelector('a').href=loginUrl();
  $('customer-bar').hidden=false;
  try{const me=await api('me');$('customer-bar').textContent='شمارهٔ همراه شما تأیید شده است.';if(!$('reservation-phone').value)$('reservation-phone').value=me.phone;}catch{}
  return;
 }
 if(!$('auth-status'))return;
 const capability=await api('capabilities');
 if(!capability.enabled){$('auth-status').textContent='ورود پیامکی هنوز فعال نشده است؛ برای رزرو از صفحهٔ نوبت‌دهی استفاده کنید.';return;}
 let challenge=null;
 const status=text=>{$('auth-status').textContent=text;};
 async function account(){
  const me=await api('me');$('phone-form').hidden=true;$('code-form').hidden=true;$('customer-account').hidden=false;
  $('verified-phone').textContent='شمارهٔ تأییدشده: '+me.phone;$('sms-consent').checked=me.sms_consent;status('با موفقیت وارد شدید.');
  const target=returnTarget();if(target)location.assign(target);
 }
 try{await account();}catch{$('phone-form').hidden=false;status('شمارهٔ همراه خود را وارد کنید.');}
 $('phone-form').addEventListener('submit',async e=>{
  e.preventDefault();const button=$('send-code');button.disabled=true;
  try{
   const data=await api('otp/request',{phone:$('auth-phone').value});challenge=data.challenge_id;
   $('code-form').hidden=false;$('code-expiry').textContent='این کد تا '+data.expires_in+' ثانیه معتبر است.';$('auth-code').value='';$('auth-code').focus();status('کد ورود پیامک شد.');
   let left=data.retry_after;button.textContent='ارسال مجدد پس از '+left+' ثانیه';
   const timer=setInterval(()=>{left--;button.textContent=left>0?'ارسال مجدد پس از '+left+' ثانیه':'ارسال مجدد کد';if(left<=0){clearInterval(timer);button.disabled=false;}},1000);
  }catch(error){status(error.message);button.disabled=false;}
 });
 $('code-form').addEventListener('submit',async e=>{
  e.preventDefault();if(!challenge)return;const button=e.target.querySelector('button');button.disabled=true;
  const code=digits($('auth-code').value.trim());$('auth-code').value='';
  try{await api('otp/verify',{challenge_id:challenge,code});challenge=null;await account();}catch(error){status(error.message);}finally{button.disabled=false;}
 });
 $('save-consent').addEventListener('click',async e=>{e.target.disabled=true;try{await api('preferences',{sms_consent:$('sms-consent').checked});status('انتخاب شما ذخیره شد.');}catch(error){status(error.message);}finally{e.target.disabled=false;}});
 $('customer-logout').addEventListener('click',async e=>{e.target.disabled=true;try{await api('logout',{});location.reload();}catch(error){status(error.message);e.target.disabled=false;}});
}
init().catch(()=>{if($('auth-status'))$('auth-status').textContent='اتصال برقرار نشد؛ کمی بعد دوباره تلاش کنید.';});
})();
