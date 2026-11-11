(() => {
'use strict';
const key='saha-demo-bookings-v1',seenKey=key+'-seen',catalog=window.SahaGroupCatalog;
const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Tehran',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
function dayAt(offset){const date=new Date(today()+'T12:00:00Z');date.setUTCDate(date.getUTCDate()+offset);return date.toISOString().slice(0,10);}
function valid(row){return row&&typeof row.id==='string'&&/^[\w-]{1,80}$/.test(row.id)&&typeof row.name==='string'&&row.name.trim()&&row.name.length<=80&&Array.isArray(row.services)&&row.services.length>0&&row.services.length<=11&&new Set(row.services).size===row.services.length&&row.services.every(c=>catalog.services.some(s=>s.code===c))&&catalog.team.some(s=>s.code===row.staff)&&typeof row.day==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(row.day)&&Number.isInteger(row.hour)&&row.hour>=9&&row.hour<19&&typeof row.createdAt==='string'&&Number.isFinite(Date.parse(row.createdAt))&&row.payment==='demo';}
function read(){const rows=JSON.parse(localStorage.getItem(key)||'[]');if(!Array.isArray(rows)||rows.length>100||!rows.every(valid))throw new Error('اطلاعات نوبت‌های محلی قابل خواندن نیست.');return rows;}
function occupied(day,hour,staff){return read().some(r=>r.day===day&&r.hour===hour&&r.staff===staff);}
function past(day,hour){const p=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Tehran',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date()).map(x=>[x.type,x.value]));return day<today()||(day===today()&&hour<=Number(p.hour));}
function busy(day,hour,staff){return hour===11||hour===15||past(day,hour)||occupied(day,hour,staff);}
async function add(row){if(!navigator.locks)throw new Error('برای جلوگیری از ثبت هم‌زمان، این آزمایش به مرورگر به‌روز و اتصال امن نیاز دارد.');return navigator.locks.request(key,async()=>{await new Promise(resolve=>setTimeout(resolve,0));if(!valid(row)||row.day<today()||row.day>dayAt(13))throw new Error('اطلاعات انتخاب‌شده معتبر نیست.');const rows=read();if(rows.length>=100)throw new Error('ظرفیت ذخیره محلی پر شده؛ نوبت‌های قبلی را پاک کن.');if(busy(row.day,row.hour,row.staff))throw new Error('این خانه دیگر آزاد نیست؛ ساعت دیگری انتخاب کن.');localStorage.setItem(key,JSON.stringify([row,...rows]));});}
async function remove(id){if(!navigator.locks)throw new Error('مرورگر به‌روز لازم است.');return navigator.locks.request(key,async()=>{await new Promise(resolve=>setTimeout(resolve,0));localStorage.setItem(key,JSON.stringify(read().filter(r=>r.id!==id)));});}
function unseen(){const ids=JSON.parse(localStorage.getItem(seenKey)||'[]');if(!Array.isArray(ids))return read().length;return read().filter(r=>!ids.includes(r.id)).length;}
function markSeen(){localStorage.setItem(seenKey,JSON.stringify(read().map(r=>r.id)));}
window.SahaBookings={key,seenKey,today,dayAt,read,busy,occupied,past,add,remove,unseen,markSeen};
})();
(() => {
if(document.body.dataset.mode!=='demo')return;
const store=window.SahaBookings,catalog=window.SahaGroupCatalog;
const node=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
function notify(){const label=document.querySelector('[data-section="localBookings"] span');if(!label)return;try{const count=store.unseen();label.textContent='رزروهای محلی آزمایشی'+(count?' · '+new Intl.NumberFormat('fa-IR').format(count)+' جدید':'');label.closest('button').setAttribute('aria-label',label.textContent);}catch(_){label.textContent='رزروهای محلی · خطای ذخیره‌سازی';}}
store.renderAdmin=host=>{host.replaceChildren();host.append(node('p','این نوبت‌ها فقط روی همین مرورگر ذخیره شده‌اند؛ پرداخت و رزرو واقعی نیستند.'));try{const rows=store.read();if(!rows.length)host.append(node('p','هنوز رزرو محلی آزمایشی ثبت نشده.'));rows.forEach(row=>{const card=node('article');card.className='panel-card';card.style.marginBottom='16px';card.style.overflowWrap='anywhere';card.append(node('h2',row.name),node('p',row.services.map(c=>catalog.services.find(s=>s.code===c).name).join('، ')),node('p',catalog.team.find(s=>s.code===row.staff).name+' · '+row.day+' · '+row.hour+':۰۰'),node('p','پرداخت آزمایشی · ۰ تومان · کد '+row.id));host.append(card);});store.markSeen();}catch(_){host.append(node('p','داده‌های محلی قابل خواندن نیست یا مرورگر اجازه دسترسی نداده.'));}notify();};
window.addEventListener('DOMContentLoaded',notify);window.addEventListener('storage',event=>{if([store.key,store.seenKey,null].includes(event.key)){notify();const host=document.querySelector('#local-bookings-view');if(host)store.renderAdmin(host);}});
})();
