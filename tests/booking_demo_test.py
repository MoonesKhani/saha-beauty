"""رزرو صرفاً محلی، پرداخت بدون پول، تداخل و اعلان پنل دمو."""
import asyncio,os
from playwright.async_api import async_playwright
BASE=os.environ.get('SAHA_TEST_URL','http://127.0.0.1:8035').rstrip('/')
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'],proxy={'server':os.environ['HTTPS_PROXY'],'bypass':'127.0.0.1,localhost'})
  for width in [int(w) for w in os.environ.get('SAHA_TEST_WIDTHS','320,390,768,1440').split(',')]:
   context=await browser.new_context(viewport={'width':width,'height':900});page=await context.new_page();writes=[];errors=[]
   context.on('request',lambda r:writes.append(r.url) if r.method not in ['GET','HEAD'] else None);page.on('pageerror',lambda e:errors.append(str(e)))
   await page.goto(BASE+'/');links=page.locator('a[href="/booking-demo.html"]');assert await links.count()>5;await page.locator('.premium-primary[href="/booking-demo.html"]').first.click();await page.wait_for_url('**/booking-demo.html')
   admin=await context.new_page();await admin.goto(BASE+'/admin-demo.html');await admin.locator('[data-section="services"]').click()
   await page.locator('#customer').fill('مشتری نمونه رزرو');await page.locator('#booking-services input').nth(1).check();await page.locator('#booking-services input').nth(3).check();await page.locator('#booking-staff').select_option('02')
   tomorrow=await page.evaluate('SahaBookings.dayAt(1)');slot=page.get_by_role('button',name=tomorrow+' ساعت 9 آزاد',exact=True);await slot.click();await page.get_by_role('button',name='پرداخت و تثبیت نوبت',exact=True).click();assert '۰ تومان' in await page.locator('body').inner_text()
   await page.locator('#cancel-payment').click();assert await page.evaluate('SahaBookings.read().length')==0
   await page.get_by_role('button',name='پرداخت و تثبیت نوبت',exact=True).click();await page.locator('#confirm-payment').click();await page.locator('#payment-dialog').wait_for(state='hidden');assert await page.evaluate('SahaBookings.read().length')==1
   assert await page.get_by_role('button',name=tomorrow+' ساعت 9 اشغال محلی',exact=True).is_disabled()
   await admin.wait_for_function("document.querySelector('[data-section=localBookings]').textContent.includes('جدید')")
   await admin.locator('[data-section="localBookings"]').click();assert 'مشتری نمونه رزرو' in await admin.locator('#local-bookings-view').inner_text();assert '۰ تومان' in await admin.locator('#local-bookings-view').inner_text()
   assert 'جدید' not in await admin.locator('[data-section="localBookings"]').inner_text()
   await page.reload();await page.locator('#booking-staff').select_option('02');assert await page.get_by_role('button',name=tomorrow+' ساعت 9 اشغال محلی',exact=True).is_disabled()
   await page.locator('#booking-staff').select_option('03');assert await page.get_by_role('button',name=tomorrow+' ساعت 9 آزاد',exact=True).is_enabled()
   await page.locator('#next-week').click();assert await page.locator('#next-week').is_disabled();await page.locator('#previous-week').click()
   assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth');assert not await admin.evaluate('document.documentElement.scrollWidth>innerWidth')
   # Two tabs attempt the same slot; the browser lock allows exactly one.
   second=await context.new_page();await second.goto(BASE+'/booking-demo.html')
   candidate={'id':'concurrency-a','name':'هم‌زمان آزمایشی','services':['01'],'staff':'01','day':tomorrow,'hour':10,'createdAt':'2026-11-11T00:00:00Z','payment':'demo'}
   run='async r=>{try{await SahaBookings.add(r);return true;}catch(e){return false;}}'
   for attempt in range(5):
    await page.evaluate("async()=>{for(const r of SahaBookings.read())if(r.id.startsWith('concurrency-'))await SahaBookings.remove(r.id);}")
    result=await asyncio.gather(page.evaluate(run,candidate),second.evaluate(run,{**candidate,'id':'concurrency-b'}));assert sorted(result)==[False,True],(result,await page.evaluate("SahaBookings.read()"))
   assert not errors,errors;assert not writes,writes
   print(f'{width}: لینک‌ها، انتخاب خدمات و ساعت، انصراف/تأیید پرداخت، اشغال محلی، اعلان پنل و تداخل هم‌زمان موفق',flush=True)
   await context.close()
  await browser.close()
if __name__=='__main__':asyncio.run(main())
