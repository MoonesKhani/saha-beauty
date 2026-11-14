(() => {
'use strict';
const $=s=>document.querySelector(s),param=new URLSearchParams(location.search).get('service'),single=param!==null;
let packages=[],packageCode=new URLSearchParams(location.search).get('package'),quote=null,quoteGeneration=0,packageReady=false;
let catalog=window.SahaReservationCatalog,live=false,batchLive=false,generation=0,saving=false,requestId=null,fingerprint=null;
const chosen=new Set(),staff=new Map(),times=new Map(),repairCodes=['02','08','09'];
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
const dayFormat=day=>new Intl.DateTimeFormat('fa-IR-u-ca-persian',{timeZone:'Asia/Tehran',dateStyle:'full'}).format(new Date(day+'T12:00:00Z'));
const hour=value=>new Intl.DateTimeFormat('fa-IR',{timeZone:'Asia/Tehran',hour:'2-digit',minute:'2-digit'}).format(new Date(value));
const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Tehran',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
$('#today-persian').textContent='امروز '+dayFormat(today);
for(let i=0;i<14;i++){const date=new Date(today+'T12:00:00Z');date.setUTCDate(date.getUTCDate()+i);const day=date.toISOString().slice(0,10),option=node('option',dayFormat(day));option.value=day;$('#reservation-day').append(option);}
function services(){return catalog.services.filter(s=>chosen.has(s.code));}
function canConfirm(){return (!packageCode||(quote&&quote.total_toman!==null&&quoteReady))&&live&&services().length>0&&(services().length===1||batchLive)&&services().every(s=>staff.has(s.code)&&times.has(s.code));}
function summary(){
 $('#reservation-summary').textContent=services().map(s=>s.name+' · '+(catalog.team.find(m=>m.code===staff.get(s.code))?.name||'متخصص انتخاب نشده')+' · '+(times.has(s.code)?hour(times.get(s.code).starts_at):'ساعت انتخاب نشده')).join('\n')+'\n'+dayFormat($('#reservation-day').value);
 $('#reserve-confirm').disabled=saving||!canConfirm();
 if(live&&services().length>1&&!batchLive)$('#reservation-status').textContent='ثبت هم‌زمان چند خدمت فعلاً در دسترس نیست؛ برای هماهنگی با سالن تماس بگیر.';
 $('#repair-reminder').hidden=!services().some(s=>repairCodes.includes(s.code));
 reminder();
 updatePrice();
}
function reminder(){let on=false;try{const codes=JSON.parse(localStorage.getItem('saha-repair-notes')||'[]');on=Array.isArray(codes)&&services().some(s=>repairCodes.includes(s.code)&&codes.includes(s.code));}catch(_){}
 $('#reminder-toggle').setAttribute('aria-pressed',String(on));$('#reminder-toggle').replaceChildren();
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg'),path=document.createElementNS(svg.namespaceURI,'path');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');path.setAttribute('d','M6 9a6 6 0 0 1 12 0v6l2 3H4l2-3V9m4 12h4');path.setAttribute('fill','none');path.setAttribute('stroke','currentColor');path.setAttribute('stroke-width','1.6');svg.append(path);$('#reminder-toggle').append(svg,document.createTextNode(on?'یادآوری ترمیم · یادداشت شد':'یادآوری ترمیم'));
}
$('#reminder-toggle').addEventListener('click',()=>{try{const raw=JSON.parse(localStorage.getItem('saha-repair-notes')||'[]'),saved=new Set(Array.isArray(raw)?raw:[]),on=$('#reminder-toggle').getAttribute('aria-pressed')==='true';services().filter(s=>repairCodes.includes(s.code)).forEach(s=>on?saved.delete(s.code):saved.add(s.code));localStorage.setItem('saha-repair-notes',JSON.stringify([...saved]));reminder();$('#reminder-status').textContent='یادداشت این خدمت در همین مرورگر ذخیره شد؛ پیامک یا اعلان خودکار ارسال نمی‌شود.';}catch(_){$('#reminder-status').textContent='مرورگر اجازه ذخیره نداد؛ یادداشت ثبت نشد.';}});
function selection(){
 $('#hair-services').replaceChildren();$('#other-services').replaceChildren();
 $('#service-selection').hidden=single&&!packageCode&&param!=='hair';
 const list=single&&!packageCode?catalog.services.filter(s=>param==='hair'?s.category==='مو':s.code===param):catalog.services;
 if(single&&!packageCode&&param!=='hair'){chosen.clear();if(list.length)chosen.add(list[0].code);else $('#reservation-status').textContent='این خدمت در حال حاضر قابل انتخاب نیست؛ با سالن هماهنگ کن.';}
 for(const s of list){const label=node('label'),input=node('input');input.type=single&&!packageCode?'radio':'checkbox';input.name='service';input.value=s.code;input.checked=chosen.has(s.code);input.addEventListener('change',()=>{if(single&&!packageCode)chosen.clear();if(input.checked)chosen.add(s.code);else chosen.delete(s.code);renderChoices();availability();});label.append(input,document.createTextNode(s.name));$(s.category==='مو'?'#hair-services':'#other-services').append(label);}
 $('#other-services').closest('fieldset').hidden=single&&!packageCode&&param==='hair';
 renderChoices();
}
function renderChoices(){
 if(live&&services().length<=1&&$('#reservation-status').textContent.startsWith('ثبت هم‌زمان چند خدمت'))$('#reservation-status').textContent='برای هر خدمت، متخصص و ساعت دلخواهت را انتخاب کن.';
 const host=$('#selected-services');host.replaceChildren();
 if(!services().length)host.append(node('p',single?'خدمت موردنظرت را انتخاب کن.':'خدمات موردنظرت را انتخاب کن.'));
 for(const s of services()){
  const card=node('div',undefined,'reservation-choice');card.append(node('h3',s.name));
  const group=node('div',undefined,'specialist-options');group.setAttribute('role','group');group.setAttribute('aria-label','متخصص '+s.name);
  const eligible=catalog.team.filter(m=>Array.isArray(m.service_codes)&&m.service_codes.includes(s.code)&&(!['02','07','manicure','pedicure','toe-gel','nail-gel'].includes(s.code)||m.code==='02'));
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
 const payload={...(packageCode?{package_code:packageCode,quote_version:quote.quote_version}:{}),customer_name:$('#reservation-name').value.trim(),phone:$('#reservation-phone').value.trim(),items:ordered},next=JSON.stringify(payload);
 if(next!==fingerprint){requestId=crypto.randomUUID();fingerprint=next;}
 saving=true;summary();
 try{const one=ordered.length===1,body=one?{...(packageCode?{package_code:packageCode,quote_version:quote.quote_version}:{}),customer_name:payload.customer_name,phone:payload.phone,...ordered[0],request_id:requestId}:{...payload,request_id:requestId};const r=await fetch(one?'/api/v1/booking/reservations':'/api/v1/booking/reservations/batch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),data=await r.json();if(one&&data.reference)data.references=[data.reference];if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'ثبت نوبت انجام نشد؛ اتصال و اطلاعات را بررسی کن.');if(data.status!=='confirmed'||!Array.isArray(data.references)||data.references.length!==ordered.length)throw new Error('تأیید قطعی همه خدمات دریافت نشد.');$('#reservation-status').textContent='نوبت‌ها در سرور ثبت شدند ♡ کد پیگیری: '+data.references.join('، ')+'؛ پرداختی انجام نشده.';$('#reservation-name').value='';$('#reservation-phone').value='';await availability();}catch(error){$('#reservation-status').textContent=error.message;}finally{saving=false;summary();}
});
let quoteReady=false,priceFingerprint='';
const money=value=>value==null?'تعرفه مشخص نشده':new Intl.NumberFormat('fa-IR').format(value)+' تومان';
const packageHost=node('section',undefined,'package-controls');packageHost.id='package-controls';
$('#reservation-form').before(packageHost);
const total=node('p',undefined,'package-total');total.id='package-total';total.setAttribute('role','status');total.setAttribute('aria-live','polite');$('#reservation-summary').after(total);
function updatePrice(){
 const selected=services().map(s=>s.code),p=packages.find(p=>p.code===packageCode);
 if(!p){quote=null;quoteReady=false;const prices=services().map(s=>s.price_toman);total.textContent=prices.length?'جمع خدمات: '+(prices.some(p=>p==null)?'تعرفه برخی خدمات مشخص نشده':money(prices.reduce((a,b)=>a+b,0))):'';return;}
 const key=JSON.stringify([p.code,selected.map(code=>[code,catalog.services.find(s=>s.code===code)?.price_toman]),p.revision]);
 if(priceFingerprint===key)return;priceFingerprint=key;quoteReady=false;quote=null;$('#reserve-confirm').disabled=true;
 const included=new Set(p.service_codes),chosenSet=new Set(selected),changed=p.price_toman==null?selected:[...new Set([...included,...chosenSet])].filter(c=>included.has(c)!==chosenSet.has(c));
 const missing=changed.some(c=>catalog.services.find(s=>s.code===c)?.price_toman==null);
 let amount=p.price_toman==null?0:p.price_toman;
 for(const code of changed){const tariff=catalog.services.find(s=>s.code===code)?.price_toman;if(tariff!=null)amount+=tariff*(p.price_toman!=null&&included.has(code)?-1:1);}
 total.textContent='قیمت پایه: '+money(p.price_toman)+'\n'+(!p.service_codes.length?'خدمات این پکیج هنوز از پنل تعریف نشده است.':!selected.length?'خدمتی انتخاب نشده است.':missing?'قیمت نهایی: تعرفه برخی خدمات مشخص نشده است.':'قیمت نهایی: '+money(amount));
 if(!p.service_codes.length||!selected.length||missing||!packageReady){$('#reserve-confirm').disabled=true;return;}
 const current=++quoteGeneration;
 fetch('/api/v1/packages/quote',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({package_code:p.code,service_codes:selected})}).then(async r=>{const data=await r.json();if(current!==quoteGeneration||key!==priceFingerprint)return;if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'محاسبه قیمت ممکن نشد.');quote=data;quoteReady=true;total.textContent='قیمت پایه: '+money(data.base_price_toman)+'\nقیمت نهایی: '+money(data.total_toman)+(data.total_toman==null?' · '+data.message:'');$('#reserve-confirm').disabled=saving||!canConfirm();}).catch(e=>{if(current===quoteGeneration&&key===priceFingerprint){quoteReady=false;total.textContent=e.message;$('#reserve-confirm').disabled=true;}});
}
function packageUI(){
 packageHost.replaceChildren();if(!packages.length)return;
 const kind=document.body.dataset.packagePage,category=new URLSearchParams(location.search).get('category');
 const list=packages.filter(p=>kind==='birthday'?p.category==='birthday':kind==='bridal'?p.category!=='birthday':true);
 packageHost.append(node('h2',kind==='birthday'?'خدمات پکیج تولد را انتخاب کن':'مقایسه و انتخاب پکیج'));
 const label=node('label','پکیج'),select=node('select');select.id='package-select';select.setAttribute('aria-label','انتخاب پکیج');const empty=node('option','خدمات دلخواه بدون پکیج');empty.value='';select.append(empty);
 for(const p of list){const option=node('option',p.name+' · '+money(p.price_toman));option.value=p.code;select.append(option);}
 label.append(select);packageHost.append(label);select.value=packageCode||'';
 const details=node('details',undefined,'package-comparison');details.open=!!kind;details.append(node('summary','مقایسه خدمات و قیمت پکیج‌ها'));const table=node('table'),head=node('tr');head.append(node('th','خدمات / پکیج'));
 const compareList=category?list.filter(p=>p.category===category):list;
 compareList.forEach(p=>head.append(node('th',p.name)));const thead=node('thead');thead.append(head);table.append(thead);const tbody=node('tbody'),priceRow=node('tr');priceRow.append(node('th','قیمت پایه'));compareList.forEach(p=>priceRow.append(node('td',money(p.price_toman))));tbody.append(priceRow);
 const codes=[...new Set(compareList.flatMap(p=>p.service_codes))];codes.forEach(code=>{const row=node('tr');row.append(node('th',catalog.services.find(s=>s.code===code)?.name||code));compareList.forEach(p=>row.append(node('td',p.service_codes.includes(code)?'✓':'—')));tbody.append(row);});
 const note=node('tr');note.append(node('th','توضیحات'));compareList.forEach(p=>note.append(node('td',p.service_codes.length?p.description:'خدمات بعداً از پنل تعریف می‌شوند.')));tbody.append(note);table.append(tbody);details.append(table);packageHost.append(details);
 select.addEventListener('change',()=>{packageCode=select.value||null;chosen.clear();staff.clear();times.clear();const p=packages.find(p=>p.code===packageCode);p?.service_codes.forEach(c=>chosen.add(c));priceFingerprint='';quoteGeneration++;selection();availability();});
}
selection();availability();
Promise.all([fetch('/api/v1/packages',{cache:'no-store'}).then(async r=>{if(!r.ok)throw Error();packageReady=true;return (await r.json()).items;}).catch(()=>fetch('/assets/saha-packages.json').then(r=>r.json())),fetch('/api/v1/booking/catalog',{cache:'no-store'}).then(async r=>{if(!r.ok)throw Error();return r.json();}).catch(()=>null)]).then(([data,booking])=>{
 packages=data;if(booking){catalog=booking;live=booking.enabled===true;batchLive=booking.batch_enabled===true;}
 if(!packageCode&&document.body.dataset.packagePage){const category=new URLSearchParams(location.search).get('category');packageCode=packages.find(p=>document.body.dataset.packagePage==='birthday'?p.category==='birthday':category?p.category===category:p.category==='bride')?.code;}
 const p=packages.find(p=>p.code===packageCode);if(p){chosen.clear();p.service_codes.forEach(c=>chosen.add(c));}
 packageUI();selection();availability();
});
fetch('/api/v1/booking/catalog',{cache:'no-store'}).then(async r=>{if(!r.ok)throw new Error();const data=await r.json();if(!Array.isArray(data.services)||!Array.isArray(data.team))throw new Error();catalog=data;priceFingerprint='';live=data.enabled===true;batchLive=data.batch_enabled===true;for(const code of [...chosen])if(!catalog.services.some(s=>s.code===code))chosen.delete(code);$('#reservation-status').textContent=live?'برای هر خدمت، متخصص و ساعت دلخواهت را انتخاب کن.':'بک‌اند متصل است؛ پذیرش آنلاین هنوز از طرف سالن فعال نشده.';selection();availability();}).catch(()=>{$('#reservation-status').textContent='رزرو آنلاین به سرور سالن متصل نیست؛ برای نوبت قطعی با سالن هماهنگ کن.';});
})();
