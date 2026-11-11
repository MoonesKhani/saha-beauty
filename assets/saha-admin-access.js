(() => {
'use strict';
const status=document.getElementById('admin-availability');
fetch('/health/ready',{cache:'no-store'}).then(async response=>{const data=response.ok?await response.json():null;if(data?.database==='ready'){status.textContent='بک‌اند پاسخ می‌دهد؛ برای ورود، اطلاعات مدیریتِ تنظیم‌شده روی سرور لازم است.';document.getElementById('admin-login-link').hidden=false;}else status.textContent='بک‌اند مدیریت هنوز به این سایت متصل نیست؛ ورود ادمین فعلاً فعال نیست.';}).catch(()=>{status.textContent='اتصال به بک‌اند مدیریت برقرار نشد؛ ورود ادمین فعلاً فعال نیست.';});
})();
