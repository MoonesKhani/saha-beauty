"""آزمون مراجعه گروهی و اشتراک داده محلی با پنل دمو."""
import asyncio,os
from playwright.async_api import async_playwright
BASE=os.environ.get('SAHA_TEST_URL','http://127.0.0.1:8033').rstrip('/')
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'],proxy={'server':os.environ['HTTPS_PROXY'],'bypass':'127.0.0.1,localhost'})
  for width in [320,390,768,1440]:
   context=await browser.new_context(viewport={'width':width,'height':900});page=await context.new_page();errors=[];writes=[]
   context.on('request',lambda r:writes.append(r.url) if r.method not in ['GET','HEAD'] else None);page.on('pageerror',lambda e:errors.append(str(e)))
   admin=await context.new_page();await admin.goto(BASE+'/admin-demo.html');await admin.locator('[data-section="groups"]').click();assert 'هنوز درخواست گروهی' in await admin.locator('#group-requests-view').inner_text()
   await page.goto(BASE+'/');await page.locator('.saha-premium .perk').filter(has_text='مراجعه گروهی').click();await page.wait_for_url('**/group-visit.html')
   await page.get_by_label('نام شما',exact=True).fill('مشتری آزمایشی');card=page.locator('.person-card').first
   await card.get_by_label('خدمت',exact=True).select_option('02');await card.get_by_label('متخصص درخواستی',exact=True).select_option('02')
   await card.get_by_role('button',name='+ خدمت دیگر').click();await card.get_by_label('خدمت',exact=True).nth(1).select_option('04');await card.get_by_label('متخصص درخواستی',exact=True).nth(1).select_option('03')
   await page.locator('#add-person').click();await page.get_by_label('نام همراه',exact=True).fill('<img src=x onerror=alert(1)>');companion=page.locator('.person-card').nth(1);await companion.get_by_label('خدمت',exact=True).select_option('01');await companion.get_by_label('متخصص درخواستی',exact=True).select_option('04')
   assert 'کوثر عبدالخانی' in await page.locator('#group-summary').inner_text();assert await page.locator('#group-summary img').count()==0
   await page.get_by_role('button',name='ذخیره درخواست در مرورگر',exact=True).click();assert 'ذخیره شد' in await page.locator('#group-feedback').inner_text()
   await admin.wait_for_function("document.querySelector('#group-requests-view').textContent.includes('مشتری آزمایشی')");assert 'ندا عبدالخانی' in await admin.locator('#group-requests-view').inner_text();assert await admin.locator('#group-requests-view img').count()==0
   await admin.reload();await admin.locator('[data-section="groups"]').click();assert 'مشتری آزمایشی' in await admin.locator('#group-requests-view').inner_text()
   await page.locator('#open-consultation').click();assert await page.locator('#consultation-dialog').is_visible();assert 'واقعی متصل نیست' in await page.locator('#consultation-dialog').inner_text();assert await page.locator('#chat-target option').count()==4
   await page.locator('#chat-target').select_option('02');await page.locator('#chat-message').fill('برای ناخن مشاوره می‌خوام');await page.get_by_role('button',name='ارسال آزمایشی',exact=True).click();assert 'پاسخ نمایشی' in await page.locator('#chat-messages').inner_text();await page.keyboard.press('Escape');assert not await page.locator('#consultation-dialog').is_visible()
   await page.reload();assert 'مشتری آزمایشی' in await page.locator('#saved-groups').inner_text()
   assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth');assert not await admin.evaluate('document.documentElement.scrollWidth>innerWidth')
   await admin.locator('[data-section="services"]').click();assert await admin.locator('#records-view').is_visible();assert await admin.locator('#records-body tr').count()>0
   assert not errors,errors;assert not writes,writes
   print(f'{width}: ثبت چندنفر و چندخدمت، متخصص مستقل، همگام‌سازی پنل، پایداری داده و گفت‌وگوی نمایشی موفق',flush=True)
   await context.close()
  context=await browser.new_context();page=await context.new_page();await page.goto(BASE+'/admin-demo.html');await page.locator('[data-section="groups"]').click();assert 'هنوز درخواست گروهی' in await page.locator('#group-requests-view').inner_text()
  await page.goto(BASE+'/group-visit.html');await page.evaluate("localStorage.setItem('saha-group-requests-v1','bad')");await page.reload();assert 'قابل خواندن نیست' in await page.locator('#saved-groups').inner_text()
  await context.close();context=await browser.new_context();await context.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw new DOMException('blocked','SecurityError')}})");page=await context.new_page();await page.goto(BASE+'/group-visit.html');await page.get_by_label('نام شما',exact=True).fill('آزمایشی');await page.locator('.person-card').get_by_label('خدمت',exact=True).select_option('01');await page.get_by_role('button',name='ذخیره درخواست در مرورگر',exact=True).click();assert 'ذخیره نشد' in await page.locator('#group-feedback').inner_text()
  await browser.close()
if __name__=='__main__':asyncio.run(main())
