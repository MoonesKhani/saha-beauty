(() => {
'use strict';
const $=s=>document.querySelector(s),param=new URLSearchParams(location.search).get('service'),single=param!==null;
let catalog=window.SahaReservationCatalog,live=false,batchLive=false,generation=0,saving=false,requestId=null,fingerprint=null;
const chosen=new Set(),staff=new Map(),times=new Map(),repairCodes=['02','08','09'];
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
const dayFormat=day=>new Intl.DateTimeFormat('fa-IR-u-ca-persian',{timeZone:'Asia/Tehran',dateStyle:'full'}).format(new Date(day+'T12:00:00Z'));
const hour=value=>new Intl.DateTimeFormat('fa-IR',{timeZone:'Asia/Tehran',hour:'2-digit',minute:'2-digit'}).format(new Date(value));
const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Tehran',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
$('#today-persian').textContent='امروز '+dayFormat(today);
for(let i=0;i<14;i++){const date=new Date(today+'T12:00:00Z');date.setUTCDate(date.getUTCDate()+i);const day=date.toISOString().slice(0,10),option=node('option',dayFormat(day));option.value=day;$('#reservation-day').append(option);}
function services(){return catalog.services.filter(s=>chosen.has(s.code));}
function canConfirm(){return live&&services().length>0&&(services().length===1||batchLive)&&services().every(s=>staff.has(s.code)&&times.has(s.code));}
function summary(){
 $('#reservation-summary').textContent=services().map(s=>s.name+' · '+(catalog.team.find(m=>m.code===staff.get(s.code))?.name||'متخصص انتخاب نشده')+' · '+(times.has(s.code)?hour(times.get(s.code).starts_at):'ساعت انتخاب نشده')).join('\n')+'\n'+dayFormat($('#reservation-day').value);
 $('#reserve-confirm').disabled=saving||!canConfirm();
 if(live&&services().length>1&&!batchLive)$('#reservation-status').textContent='ثبت هم‌زمان چند خدمت فعلاً در دسترس نیست؛ برای هماهنگی با سالن تماس بگیر.';
 $('#repair-reminder').hidden=!services().some(s=>repairCodes.includes(s.code));
 reminder();
}
function reminder(){let on=false;try{const codes=JSON.parse(localStorage.getItem('saha-repair-notes')||'[]');on=Array.isArray(codes)&&services().some(s=>repairCodes.includes(s.code)&&codes.includes(s.code));}catch(_){}
 $('#reminder-toggle').setAttribute('aria-pressed',String(on));$('#reminder-toggle').replaceChildren();
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg'),path=document.createElementNS(svg.namespaceURI,'path');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');path.setAttribute('d','M6 9a6 6 0 0 1 12 0v6l2 3H4l2-3V9m4 12h4');path.setAttribute('fill','none');path.setAttribute('stroke','currentColor');path.setAttribute('stroke-width','1.6');svg.append(path);$('#reminder-toggle').append(svg,document.createTextNode(on?'یادآوری ترمیم · یادداشت شد':'یادآوری ترمیم'));
}
$('#reminder-toggle').addEventListener('click',()=>{try{const raw=JSON.parse(localStorage.getItem('saha-repair-notes')||'[]'),saved=new Set(Array.isArray(raw)?raw:[]),on=$('#reminder-toggle').getAttribute('aria-pressed')==='true';services().filter(s=>repairCodes.includes(s.code)).forEach(s=>on?saved.delete(s.code):saved.add(s.code));localStorage.setItem('saha-repair-notes',JSON.stringify([...saved]));reminder();$('#reminder-status').textContent='یادداشت این خدمت در همین مرورگر ذخیره شد؛ پیامک یا اعلان خودکار ارسال نمی‌شود.';}catch(_){$('#reminder-status').textContent='مرورگر اجازه ذخیره نداد؛ یادداشت ثبت نشد.';}});
function selection(){
 $('#hair-services').replaceChildren();$('#other-services').replaceChildren();
 $('#service-selection').hidden=single&&param!=='hair';
 const list=single?catalog.services.filter(s=>param==='hair'?s.category==='مو':s.code===param):catalog.services;
 if(single&&param!=='hair'){chosen.clear();if(list.length)chosen.add(list[0].code);else $('#reservation-status').textContent='این خدمت در حال حاضر قابل انتخاب نیست؛ با سالن هماهنگ کن.';}
 for(const s of list){const label=node('label'),input=node('input');input.type=single?'radio':'checkbox';input.name='service';input.value=s.code;input.checked=chosen.has(s.code);input.addEventListener('change',()=>{if(single)chosen.clear();if(input.checked)chosen.add(s.code);else chosen.delete(s.code);renderChoices();availability();});label.append(input,document.createTextNode(s.name));$(s.category==='مو'?'#hair-services':'#other-services').append(label);}
 if(single&&param==='hair')$('#other-services').closest('fieldset').hidden=true;
 renderChoices();
}
function renderChoices(){
 if(live&&services().length<=1&&$('#reservation-status').textContent.startsWith('ثبت هم‌زمان چند خدمت'))$('#reservation-status').textContent='برای هر خدمت، متخصص و ساعت دلخواهت را انتخاب کن.';
 const host=$('#selected-services');host.replaceChildren();
 if(!services().length)host.append(node('p',single?'خدمت موردنظرت را انتخاب کن.':'خدمات موردنظرت را انتخاب کن.'));
 for(const s of services()){
  const card=node('div',undefined,'reservation-choice');card.append(node('h3',s.name));
  const group=node('div',undefined,'specialist-options');group.setAttribute('role','group');group.setAttribute('aria-label','متخصص '+s.name);
  const eligible=catalog.team.filter(m=>!Array.isArray(m.service_codes)||m.service_codes.includes(s.code));
  if(staff.has(s.code)&&!eligible.some(m=>m.code===staff.get(s.code)))staff.delete(s.code);
  if(!eligible.length)group.append(node('p','هنوز متخصصی با برنامه تأییدشده برای این خدمت ثبت نشده.','muted'));
  for(const m of eligible){const label=node('label',undefined,'specialist-option'),input=node('input');input.type='radio';input.name='staff-'+s.code;input.value=m.code;input.checked=staff.get(s.code)===m.code;input.addEventListener('change',()=>{staff.set(s.code,m.code);availability();});label.append(input,node('strong',m.name),node('small',m.role));group.append(label);}
  card.append(group);host.append(card);
 }
 summary();
}
async function availability(){
 const current=++generation;times.clear();summary();const host=$('#availability');host.replaceChildren();
 if(!live){host.append(node('p','جدول ساعت‌های واقعی هنوز فعال نیست؛ ثبت نوبت بدون تأیید سرور انجام نمی‌شود.'));return;}
 await Promise.all(services().map(async s=>{
  const box=node('section',undefined,'reservation-time-group');box.append(node('h3',s.name));const slots=node('div',undefined,'reservation-time-slots');box.append(slots);host.append(box);
  if(!staff.has(s.code)){slots.append(node('p','متخصص این خدمت را انتخاب کن.'));return;}
  slots.textContent='در حال دریافت ساعت‌ها…';
  try{const q=new URLSearchParams({staff_code:staff.get(s.code),services:s.code,day:$('#reservation-day').value});const r=await fetch('/api/v1/booking/availability?'+q,{cache:'no-store'}),data=await r.json();if(current!==generation)return;if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'دریافت ساعت‌ها ممکن نشد.');if(!Array.isArray(data.slots))throw new Error('جدول دریافتی معتبر نیست.');slots.replaceChildren();if(!data.slots.length)slots.append(node('p','برای این روز ساعت قابل رزروی ثبت نشده.'));
   for(const slot of data.slots){const b=node('button',hour(slot.starts_at)+' · '+(slot.state==='available'?'آزاد':'رزروشده'));b.type='button';b.disabled=slot.state!=='available';b.setAttribute('aria-pressed','false');b.addEventListener('click',()=>{times.set(s.code,slot);slots.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));summary();});slots.append(b);}
  }catch(e){if(current===generation)slots.textContent=e.message;}
 }));
}
$('#reservation-day').addEventListener('change',availability);
$('#reservation-form').addEventListener('submit',async e=>{
 e.preventDefault();if(!canConfirm()||saving)return;
 const ordered=services().map(s=>({service_codes:[s.code],staff_code:staff.get(s.code),starts_at:times.get(s.code).starts_at}));
 const windows=services().map(s=>times.get(s.code));if(windows.some((a,i)=>windows.some((b,j)=>j>i&&new Date(a.starts_at)<new Date(b.ends_at)&&new Date(b.starts_at)<new Date(a.ends_at)))){$('#reservation-status').textContent='ساعت خدماتت هم‌پوشانی دارد؛ برای هر خدمت یک بازه جدا انتخاب کن.';return;}
 const payload={customer_name:$('#reservation-name').value.trim(),phone:$('#reservation-phone').value.trim(),items:ordered},next=JSON.stringify(payload);
 if(next!==fingerprint){requestId=crypto.randomUUID();fingerprint=next;}
 saving=true;summary();
 try{const one=ordered.length===1,body=one?{customer_name:payload.customer_name,phone:payload.phone,...ordered[0],request_id:requestId}:{...payload,request_id:requestId};const r=await fetch(one?'/api/v1/booking/reservations':'/api/v1/booking/reservations/batch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),data=await r.json();if(one&&data.reference)data.references=[data.reference];if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'ثبت نوبت انجام نشد؛ اتصال و اطلاعات را بررسی کن.');if(data.status!=='confirmed'||!Array.isArray(data.references)||data.references.length!==ordered.length)throw new Error('تأیید قطعی همه خدمات دریافت نشد.');$('#reservation-status').textContent='نوبت‌ها در سرور ثبت شدند ♡ کد پیگیری: '+data.references.join('، ')+'؛ پرداختی انجام نشده.';$('#reservation-name').value='';$('#reservation-phone').value='';await availability();}catch(error){$('#reservation-status').textContent=error.message;}finally{saving=false;summary();}
});
selection();availability();
fetch('/api/v1/booking/catalog',{cache:'no-store'}).then(async r=>{if(!r.ok)throw new Error();const data=await r.json();if(!Array.isArray(data.services)||!Array.isArray(data.team))throw new Error();catalog=data;live=data.enabled===true;batchLive=data.batch_enabled===true;for(const code of [...chosen])if(!catalog.services.some(s=>s.code===code))chosen.delete(code);$('#reservation-status').textContent=live?'برای هر خدمت، متخصص و ساعت دلخواهت را انتخاب کن.':'بک‌اند متصل است؛ پذیرش آنلاین هنوز از طرف سالن فعال نشده.';selection();availability();}).catch(()=>{$('#reservation-status').textContent='رزرو آنلاین به سرور سالن متصل نیست؛ برای نوبت قطعی با سالن هماهنگ کن.';});
})();
