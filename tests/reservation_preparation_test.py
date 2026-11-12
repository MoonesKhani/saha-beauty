import asyncio,os
from playwright.async_api import async_playwright
BASE=os.environ.get('SAHA_TEST_URL','http://127.0.0.1:8035').rstrip('/')
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'],proxy={'server':os.environ['HTTPS_PROXY'],'bypass':'127.0.0.1,localhost'})
  for width in [320,390,768,1440]:
   page=await browser.new_page(viewport={'width':width,'height':900});errors=[];writes=[]
   page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:writes.append(r.url) if r.method not in ['GET','HEAD'] else None)
   await page.goto(BASE+'/');await page.locator('.premium-primary[href="/booking.html"]').first.click();await page.wait_for_url('**/booking.html')
   for name in ['بافت','شینیون','اسکالپ','رنگ','موخوره‌گیری','اکستنشن','تزریق ژل و فیلر']:assert await page.get_by_label(name,exact=True).count()==1
   assert await page.get_by_label('عروس',exact=True).count()==0
   await page.get_by_label('بافت',exact=True).check();await page.get_by_label('تزریق ژل و فیلر',exact=True).check();await page.locator('input[name=staff-hair-braid][value="04"]').check();await page.locator('input[name=staff-gel-filler][value="04"]').check()
   await page.locator('#reservation-day').select_option(index=2);summary=await page.locator('#reservation-summary').inner_text();assert 'بافت' in summary and 'ندا عبدالخانی' in summary
   assert await page.locator('input[type=date]').count()==0
   today=await page.locator('#today-persian').inner_text();assert any(m in today for m in ['فروردین','اردیبهشت','خرداد','تیر','مرداد','شهریور','مهر','آبان','آذر','دی','بهمن','اسفند'])
   assert await page.locator('#reserve-confirm').is_disabled();assert await page.get_by_role('button',name='پرداخت · غیرفعال',exact=True).is_disabled()
   assert 'ثبت نوبت بدون تأیید سرور انجام نمی‌شود' in await page.locator('#availability').inner_text();assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
   await page.goto(BASE+'/booking-demo.html');assert await page.locator('#confirm-payment').count()==0;assert await page.locator('#reserve-confirm').is_disabled()
   await page.goto(BASE+'/admin-access.html');await page.wait_for_function("document.querySelector('#admin-availability').textContent.includes('فعال نیست')");assert not await page.locator('#admin-login-link').is_visible()
   assert not errors,errors;assert not writes,writes;assert await page.evaluate('localStorage.length')==0
   print(f'{width}: خدمات اصلاح‌شده، تاریخ شمسی، خلاصه، پرداخت خاموش و جلوگیری از رزرو/ورود غیرواقعی موفق',flush=True);await page.close()
  await browser.close()
if __name__=='__main__':asyncio.run(main())
