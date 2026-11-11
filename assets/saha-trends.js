(() => {
'use strict';
const root=document.getElementById('standalone-trends'),categories=document.getElementById('trend-services'),status=document.getElementById('trends-status');
const key='saha-trend-likes';let data={categories:[],items:[]},selected=null,likes={};
const node=(tag,text,cls)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;};
try{const stored=JSON.parse(localStorage.getItem(key)||'{}');if(stored&&typeof stored==='object'&&!Array.isArray(stored))likes=Object.fromEntries(Object.entries(stored).filter(([id,value])=>/^\d{1,4}$/.test(id)&&value===true));}catch(_){}
function notice(text){status.textContent=text;status.hidden=!text;}
function paint(){
 categories.querySelectorAll('button').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.category===selected)));
 root.replaceChildren();if(!selected){notice('');return;}
 const items=data.items.filter(item=>item.category===selected);notice(items.length?'':'برای این خدمت هنوز پیشنهاد تأییدشده‌ای ثبت نشده.');
 for(const item of items){
  const card=node('article',undefined,'standalone-trend-card');card.append(node('span',data.categories.find(c=>c.id===item.category).label,'eyebrow'),node('h2',item.title),node('p',item.description));
  const like=node('button',likes[item.id]?'♥ پسندیدی':'♡ دوستش دارم','quiet-button');like.type='button';like.setAttribute('aria-pressed',String(!!likes[item.id]));
  like.addEventListener('click',()=>{likes[item.id]=!likes[item.id];like.setAttribute('aria-pressed',String(likes[item.id]));like.textContent=likes[item.id]?'♥ پسندیدی':'♡ دوستش دارم';try{localStorage.setItem(key,JSON.stringify(likes));}catch(_){notice('پسندت فعلاً فقط در همین صفحه می‌مونه؛ مرورگر اجازه ذخیره نداد.');}});
  const contact=node('a','مشاوره با تیم سها ↗');contact.href='https://wa.me/989168285964';card.append(like,contact);root.append(card);
 }
}
notice('در حال آماده‌سازی پیشنهادها…');
fetch('/assets/saha-trends.json',{cache:'no-store'}).then(async response=>{
 if(!response.ok)throw new Error();const value=await response.json();if(!Array.isArray(value.categories)||!Array.isArray(value.items))throw new Error();
 data.categories=value.categories.slice(0,30).filter(c=>c&&/^\d{2}$/.test(c.id)&&typeof c.label==='string'&&c.label.length<=40&&typeof c.icon==='string'&&c.icon.length<=2000);
 data.items=value.items.slice(0,200).filter(i=>i&&/^\d{1,4}$/.test(i.id)&&data.categories.some(c=>c.id===i.category)&&typeof i.title==='string'&&i.title.length<=120&&typeof i.description==='string'&&i.description.length<=500);
 if(!data.categories.length)throw new Error();
 for(const category of data.categories){const button=node('button',undefined,'standalone-trend-category');button.type='button';button.dataset.category=category.id;button.setAttribute('aria-pressed','false');button.setAttribute('aria-controls','standalone-trends');button.setAttribute('aria-label',category.label);const circle=node('span',undefined,'standalone-trend-circle'),svg=document.createElementNS('http://www.w3.org/2000/svg','svg'),path=document.createElementNS(svg.namespaceURI,'path');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');path.setAttribute('d',category.icon);svg.append(path);circle.append(svg);button.append(circle,node('span',category.label));button.addEventListener('click',()=>{selected=selected===category.id?null:category.id;paint();});categories.append(button);}
 paint();
}).catch(()=>notice('پیشنهادها فعلاً در دسترس نیستند؛ کمی بعد دوباره امتحان کن.'));
})();
