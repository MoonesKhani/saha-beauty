(() => {
'use strict';
const status=document.getElementById('admin-availability');
async function check(){
 for(const path of ['/api/v1/health/ready','/health/ready']){
  try{const r=await fetch(path,{cache:'no-store'});if(r.ok&&(await r.json()).database==='ready'){status.textContent='بک‌اند پاسخ می‌دهد؛ با کلید مدیریتِ تنظیم‌شده روی سرور وارد شوید.';document.getElementById('admin-login-link').hidden=false;return;}}catch(_){}
 }
 try{const r=await fetch('/api/v1/catalog',{cache:'no-store'});const data=r.ok?await r.json():null;if(Array.isArray(data?.services)&&Array.isArray(data?.team)){status.textContent='سرور فعلی پاسخ می‌دهد؛ قابلیت‌های جدید پنل به به‌روزرسانی بک‌اند نیاز دارند.';document.getElementById('admin-login-link').hidden=false;return;}}catch(_){}
 status.textContent='ارتباط با سرور مدیریت برقرار نشد؛ ورود و ذخیره تغییرات فعلاً ممکن نیست.';
}
check();
})();
