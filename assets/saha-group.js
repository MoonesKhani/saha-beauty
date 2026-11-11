(() => {
'use strict';
const $=s=>document.querySelector(s),catalog=window.SahaGroupCatalog,store=window.SahaGroups;
const people=[{name:'',services:[{service:'',staff:''}]}];
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
const feedback=message=>{$('#group-feedback').textContent=message;};
function button(text,action,cls='quiet-button'){const e=node('button',text,cls);e.type='button';e.addEventListener('click',action);return e;}
function labelSelect(text,choices,value,change){const label=node('label',text),select=node('select');select.setAttribute('aria-label',text);select.required=text==='خدمت';for(const [id,title] of choices){const option=node('option',title);option.value=id;select.append(option);}select.value=value;select.addEventListener('change',()=>{change(select.value);summary();});label.append(select);return label;}
function serviceName(code){return catalog.services.find(x=>x.code===code)?.name||'خدمت انتخاب نشده';}
function staffName(code){return catalog.team.find(x=>x.code===code)?.name||'با پیشنهاد سالن';}
function summary(){const host=$('#group-summary');host.replaceChildren();people.forEach((person,i)=>{host.append(node('strong',person.name.trim()||(i===0?'نام شما':'نام همراه')));const list=node('ul');person.services.forEach(s=>list.append(node('li',serviceName(s.service)+' · '+staffName(s.staff))));host.append(list);});}
function render(){const host=$('#people');host.replaceChildren();people.forEach((person,index)=>{
 const card=node('section',undefined,'group-card person-card'),heading=node('div',undefined,'person-heading');heading.append(node('h2',index===0?'خودت ♡':'همراه '+new Intl.NumberFormat('fa-IR').format(index)));
 if(index>0)heading.append(button('حذف همراه',()=>{people.splice(index,1);render();}));card.append(heading);
 const label=node('label',index===0?'نام شما':'نام همراه'),input=node('input');input.required=true;input.maxLength=80;input.value=person.name;input.autocomplete='off';input.addEventListener('input',()=>{person.name=input.value;summary();});label.append(input);card.append(label);
 person.services.forEach((selection,rowIndex)=>{const line=node('div',undefined,'service-line');line.append(labelSelect('خدمت',[['','انتخاب خدمت'],...catalog.services.map(s=>[s.code,s.name])],selection.service,v=>{selection.service=v;}),labelSelect('متخصص درخواستی',[['','با پیشنهاد سالن'],...catalog.team.map(s=>[s.code,s.name+' · '+s.role])],selection.staff,v=>{selection.staff=v;}));if(person.services.length>1)line.append(button('حذف خدمت',()=>{person.services.splice(rowIndex,1);render();}));card.append(line);});
 const add=button('+ خدمت دیگر',()=>{person.services.push({service:'',staff:''});render();});add.disabled=person.services.length>=6;card.append(add);host.append(card);
 });$('#add-person').disabled=people.length>=8;summary();}
$('#add-person').addEventListener('click',()=>{if(people.length<8){people.push({name:'',services:[{service:'',staff:''}]});render();$('#people .person-card:last-child input').focus();}});
function saved(){const host=$('#saved-groups');host.replaceChildren();try{const rows=store.read();if(!rows.length)host.append(node('p','هنوز درخواستی ذخیره نکردی.'));rows.forEach(row=>{const item=node('div',undefined,'request-item');item.append(node('strong',row.people.map(p=>p.name).join('، ')),node('p','کد درخواست: '+row.id));item.append(button('حذف این درخواست',()=>{try{store.remove(row.id);saved();}catch(_){feedback('مرورگر اجازه تغییر اطلاعات رو نداد.');}}));host.append(item);});}catch(_){host.append(node('p','اطلاعات محلی قابل خواندن نیست یا مرورگر اجازه ذخیره‌سازی نداده.'));}}
$('#group-form').addEventListener('submit',event=>{event.preventDefault();try{const record={id:crypto.randomUUID(),createdAt:new Date().toISOString(),people:people.map(p=>({name:p.name.trim(),services:p.services.map(s=>({...s}))}))};store.add(record);saved();feedback('درخواست در همین مرورگر ذخیره شد؛ در پنل دمو قابل دیدنه و رزرو قطعی نیست ♡');}catch(error){feedback(error.name==='QuotaExceededError'||error.name==='SecurityError'?'مرورگر اجازه ذخیره‌سازی نداد؛ درخواست ذخیره نشد.':error.message);}});
$('#clear-groups').addEventListener('click',()=>{if(!confirm('همه درخواست‌های گروهی این مرورگر پاک بشن؟'))return;try{store.clear();saved();feedback('درخواست‌های محلی پاک شدند.');}catch(_){feedback('پاک‌کردن اطلاعات در این مرورگر ممکن نیست.');}});
const dialog=$('#consultation-dialog');
$('#open-consultation').addEventListener('click',()=>{const target=$('#chat-target');target.replaceChildren();const chosen=new Set(people.flatMap(p=>p.services.map(s=>s.staff)).filter(Boolean));[['support','پشتیبان سالن · آزمایشی'],...catalog.team.filter(s=>chosen.has(s.code)).map(s=>[s.code,s.name+' · آزمایشی'])].forEach(([value,text])=>{const option=node('option',text);option.value=value;target.append(option);});dialog.showModal();});
$('#close-chat').addEventListener('click',()=>dialog.close());
$('#chat-form').addEventListener('submit',event=>{event.preventDefault();const input=$('#chat-message'),text=input.value.trim();if(!text)return;const host=$('#chat-messages');if(host.children.length>=40){host.replaceChildren();}host.append(node('p','تو: '+text),node('p','پاسخ نمایشی برای '+$('#chat-target').selectedOptions[0].textContent+': این فقط یک گفت‌وگوی آزمایشیه؛ برای مشاوره واقعی از راه‌های تماس سالن استفاده کن.'));input.value='';host.scrollTop=host.scrollHeight;});
window.addEventListener('storage',event=>{if(event.key===store.key||event.key===null)saved();});render();saved();
})();
