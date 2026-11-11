"""Compact landing navigation, horizontal tracks and separate collection pages."""
import asyncio,json,os
from pathlib import Path
from playwright.async_api import async_playwright
BASE=os.environ.get('SAHA_TEST_URL','http://127.0.0.1:8036').rstrip('/')
async def main():
 results={}
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'],proxy={'server':os.environ['HTTPS_PROXY'],'bypass':'127.0.0.1,localhost'})
  for width in [320,390,768,1440]:
   page=await browser.new_page(viewport={'width':width,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   await page.goto(BASE+'/',wait_until='networkidle');await page.evaluate('document.fonts.ready');await page.locator('#services .svc').first.wait_for()
   names=await page.locator('#services .svc h3').all_text_contents();assert names==['اصلاح','پاکسازی','ناخن'],names
   assert await page.locator('.petal-playground,.beauty-game,#work').count()==0
   results[str(width)]=await page.evaluate('document.documentElement.scrollHeight')
   assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
   await page.screenshot(path=f'/tmp/saha-compact-hero-{width}.png')
   menu=page.locator('.saha-premium header .saha-more');await menu.locator('summary').click();assert await menu.get_by_role('link',name='گالری نمونه‌کارها',exact=True).is_visible();await page.keyboard.press('Escape');assert not await menu.evaluate('(e)=>e.open')
   await page.get_by_role('button',name='مشاهده همه خدمات',exact=True).click();assert await page.locator('#services .svc').count()==10
   names=await page.locator('#services .svc h3').all_text_contents();assert 'ابرو' not in names and 'عروس' not in names and 'تزریق ژل و فیلر' in names
   await page.get_by_role('button',name='خدمات بعدی',exact=True).click();await page.wait_for_timeout(500);assert await page.locator('#service-cards').evaluate('(e)=>Math.abs(e.scrollLeft)>20')
   await page.get_by_role('button',name='نمایش خدمات پرتقاضا',exact=True).click();assert await page.locator('#services .svc').count()==3
   assert await page.locator('#package-cards>.card3').count()==4
   await page.get_by_role('button',name='پکیج بعدی',exact=True).click();await page.wait_for_timeout(500);assert await page.locator('#package-cards').evaluate('(e)=>Math.abs(e.scrollLeft)>20')
   positions=await page.locator('#package-cards>.card3').evaluate_all('(els)=>els.map(e=>Math.round(e.getBoundingClientRect().top))');assert len(set(positions))==1,positions
   music=page.locator('[data-saha-music]');assert await music.get_attribute('aria-pressed')=='false';await music.click();await page.wait_for_function("document.querySelector('[data-saha-music]').getAttribute('aria-pressed')==='true'");assert len((await music.inner_text()).strip())<4;await music.click();assert await music.get_attribute('aria-pressed')=='false'
   await page.locator('#services').screenshot(path=f'/tmp/saha-compact-services-{width}.png')
   await page.locator('#packages').screenshot(path=f'/tmp/saha-compact-packages-{width}.png')
   await menu.locator('summary').click();await menu.get_by_role('link',name='تخفیف و شانس زیبایی ✨',exact=True).click();await page.wait_for_url('**/discounts.html');await page.locator('[data-beauty-petal="1"]').click();assert 'کد یا تخفیف واقعی ایجاد نشد' in await page.locator('.beauty-game-result').inner_text();await page.locator('[data-beauty-reset]').click();assert await page.locator('.beauty-game-result').inner_text()==''
   await page.goto(BASE+'/');await menu.locator('summary').click();await menu.get_by_role('link',name='گالری نمونه‌کارها',exact=True).click();await page.wait_for_url('**/gallery.html');await page.locator('#gallery-empty').wait_for(state='visible');await page.get_by_role('button',name='ناخن',exact=True).click();assert await page.get_by_role('button',name='ناخن',exact=True).get_attribute('aria-pressed')=='true'
   assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth');assert not errors,errors
   print(f'{width}: منو، خدمات بازشونده، ورق‌زدن افقی، موسیقی، تخفیف و گالری موفق؛ ارتفاع صفحه {results[str(width)]}',flush=True);await page.close()
  await browser.close()
 Path('/tmp/saha-compact-after.json').write_text(json.dumps(results))
if __name__=='__main__':asyncio.run(main())
