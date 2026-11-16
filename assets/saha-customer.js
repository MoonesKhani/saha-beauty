(()=>{'use strict';
const $=id=>document.getElementById(id);
async function api(path,body){
 const response=await fetch('/api/v1/auth/'+path,{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
 let data={};if(response.status!==204)data=await response.json();
 if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'درخواست انجام نشد؛ کمی بعد تلاش کنید.');
 return data;
}
function digits(value){return value.replace(/[۰-۹]/g,c=>'۰۱۲۳۴۵۶۷۸۹'.indexOf(c));}
async function init(){
 const capability=await api('capabilities');
 if($('customer-bar')){
  if(!capability.enabled)return;
  $('customer-bar').hidden=false;
  try{const me=await api('me');$('customer-bar').textContent='شمارهٔ همراه شما تأیید شده است.';if(!$('reservation-phone').value)$('reservation-phone').value=me.phone;}catch{}
  return;
 }
 if(!$('auth-status'))return;
 if(!capability.enabled){$('auth-status').textContent='ورود پیامکی هنوز فعال نشده است؛ برای رزرو از صفحهٔ نوبت‌دهی استفاده کنید.';return;}
 let challenge=null;
 const status=text=>{$('auth-status').textContent=text;};
 async function account(){
  const me=await api('me');$('phone-form').hidden=true;$('code-form').hidden=true;$('customer-account').hidden=false;
  $('verified-phone').textContent='شمارهٔ تأییدشده: '+me.phone;$('sms-consent').checked=me.sms_consent;status('با موفقیت وارد شدید.');
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
