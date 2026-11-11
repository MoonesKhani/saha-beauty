(() => {
'use strict';
const $=s=>document.querySelector(s),catalog=window.SahaReservationCatalog;
const formatDay=day=>new Intl.DateTimeFormat('fa-IR-u-ca-persian',{timeZone:'Asia/Tehran',dateStyle:'full'}).format(new Date(day+'T12:00:00Z'));
const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Tehran',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
const node=(tag,text)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;return el;};
$('#today-persian').textContent='امروز '+formatDay(today);
for(let i=0;i<14;i++){const date=new Date(today+'T12:00:00Z');date.setUTCDate(date.getUTCDate()+i);const day=date.toISOString().slice(0,10),option=node('option',formatDay(day));option.value=day;$('#reservation-day').append(option);}
for(const member of catalog.team){const option=node('option',member.name+' · '+member.role);option.value=member.code;$('#reservation-staff').append(option);}
for(const service of catalog.services){const label=node('label'),input=node('input');input.type='checkbox';input.value=service.code;input.addEventListener('change',summary);label.append(input,document.createTextNode(service.name));$(service.category==='مو'?'#hair-services':'#other-services').append(label);}
function summary(){const services=[...document.querySelectorAll('.reservation-options input:checked')].map(e=>catalog.services.find(s=>s.code===e.value).name);const staff=catalog.team.find(s=>s.code===$('#reservation-staff').value);$('#reservation-summary').textContent=(services.join('، ')||'خدمت انتخاب نشده')+'\n'+(staff?staff.name:'متخصص انتخاب نشده')+'\n'+formatDay($('#reservation-day').value)+'\nساعت: پس از اتصال برنامه سالن';}
function unavailable(){const host=$('#availability');host.replaceChildren(node('p','جدول ساعت‌های واقعی هنوز به سرور سالن متصل نیست؛ ساعت آزاد یا رزروشده‌ای قابل تأیید نیست.'));}
$('#reservation-day').addEventListener('change',summary);$('#reservation-staff').addEventListener('change',summary);summary();unavailable();
// Never infer availability from a browser cache or from an HTML/404 response.
fetch('/health/ready',{cache:'no-store'}).then(async response=>{const data=response.ok?await response.json():null;$('#reservation-status').textContent=data?.database==='ready'?'سرور پاسخ می‌دهد؛ فعال‌سازی ثبت قطعی به برنامه واقعی خدمات و متخصص‌ها نیاز دارد.':'رزرو آنلاین هنوز به سرور سالن متصل نیست؛ برای نوبت قطعی با سالن هماهنگ کن.';}).catch(()=>{$('#reservation-status').textContent='اتصال به سرور سالن برقرار نشد؛ برای نوبت قطعی با سالن هماهنگ کن.';});
})();
