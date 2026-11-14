/* Extend existing cards without changing their layout or navigating away. */
(() => {
 'use strict';
 document.addEventListener('click',async event=>{
  const card=event.target.closest('#team .team-member-card');
  if(card&&!event.target.closest('.team-portfolio')){
   event.preventDefault();
   let dialog=document.getElementById('team-profile-dialog');
   if(!dialog){dialog=document.createElement('dialog');dialog.id='team-profile-dialog';dialog.className='saha-menu-dialog';document.body.append(dialog);dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close();});}
   dialog.replaceChildren();const copy=card.cloneNode(true);copy.classList.remove('rv','reveal-pending');copy.style.width='100%';copy.style.boxSizing='border-box';
   copy.querySelectorAll('a:not(.team-portfolio)').forEach(a=>{const span=document.createElement('span');span.className=a.className;span.append(...a.childNodes);a.replaceWith(span);});
   const title=copy.querySelector('.team-member-name');if(title){title.id='team-profile-title';dialog.setAttribute('aria-labelledby',title.id);}
   const close=document.createElement('button');close.type='button';close.className='refinement-button';close.textContent='بستن';close.addEventListener('click',()=>dialog.close());dialog.append(copy,close);dialog.showModal();
   dialog.addEventListener('close',()=>card.querySelector('.team-member-name')?.focus(),{once:true});
  }
  if(event.target.closest('[data-saha-open-menu]')){
   const menu=document.getElementById('saha-buffet-menu');if(!menu||menu.dataset.loaded)return;
   try{const r=await fetch('/api/v1/leisure/buffet',{cache:'no-store'});if(!r.ok)return;const data=await r.json();if(!data.items.length)return;menu.dataset.loaded='true';menu.querySelector('h2').textContent='منوی بوفه سها';
    for(const item of data.items){const row=document.createElement('article'),h=document.createElement('h3'),p=document.createElement('p');h.textContent=item.title;p.textContent=item.description+' · '+(item.price_toman==null?'قیمت ثبت نشده':new Intl.NumberFormat('fa-IR').format(item.price_toman)+' تومان');row.append(h,p);menu.append(row);}
   }catch(_){}
  }
 });
 // Cards already provide keyboard-operable profile links and a separate gallery link.
})();
