# آزمون رفتاری مرورگر؛ وابستگی توسعه: بسته پایتون Playwright و Chromium.
import asyncio,os,json
from pathlib import Path
from playwright.async_api import async_playwright
BASE=os.environ.get('SAHA_TEST_URL','http://127.0.0.1:8000/')
async def main():
 results=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path=os.environ.get('SAHA_CHROMIUM','/usr/bin/chromium'),args=['--no-sandbox','--disable-dev-shm-usage'],proxy={'server':os.environ['HTTPS_PROXY'],'bypass':'127.0.0.1,localhost'} if os.environ.get('HTTPS_PROXY') else None)
  for width in [320,390,768,1440]:
   context=await browser.new_context(viewport={'width':width,'height':900},device_scale_factor=1,is_mobile=width<650,has_touch=width<650)
   await context.add_init_script("window.__cls=0;new PerformanceObserver(l=>{for(const e of l.getEntries())if(!e.hadRecentInput)window.__cls+=e.value}).observe({type:'layout-shift',buffered:true});")
   page=await context.new_page();errors=[];failed=[]
   page.on('pageerror',lambda e:errors.append(str(e)));page.on('requestfailed',lambda r:failed.append(r.url))
   await page.goto(BASE,wait_until='networkidle',timeout=45000);await page.wait_for_timeout(900)
   root=page.locator('.saha-premium');assert await root.count()==1
   assert 'زیبایی،' in await root.locator('h1').inner_text() and 'به سبک تو' in await root.locator('h1').inner_text()
   assert await root.locator('h1').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
   assert await root.locator('.hero-scene img').evaluate('(e)=>e.complete&&e.naturalWidth>0')
   canvas=root.locator('canvas'); count=int(await canvas.get_attribute('data-particle-count'));assert count==(26 if width<700 else 58)
   starts=await canvas.get_attribute('data-burst-starts');assert starts=='1'
   await page.wait_for_timeout(3200);assert await canvas.get_attribute('data-phase')=='settled'
   # This control must work without interfering with the component state.
   pause=root.locator('.saha-motion-toggle');await pause.click();assert await pause.get_attribute('aria-pressed')=='true';assert await page.locator('html').get_attribute('data-saha-motion')=='paused';await pause.click();assert await pause.get_attribute('aria-pressed')=='false'
   if width in [390,1440]:await page.screenshot(path=f'/tmp/saha-premium-hero-{width}.png')
   art=root.locator('.saha-assembly');before=await art.locator('.gather-a').evaluate('(e)=>getComputedStyle(e).transform');await art.scroll_into_view_if_needed();await page.wait_for_timeout(100);after=await art.locator('.gather-a').evaluate('(e)=>getComputedStyle(e).transform');assert before!=after
   perk=root.locator('#perks .perk').first;await perk.click();assert await root.locator('#perks .perk').first.get_attribute('aria-pressed')=='true'
   cards=root.locator('#services .svc');assert await cards.count()==11
   text=await root.locator('#services').inner_text();assert all(x in text for x in ['موخوره','اسکالپ','ژلیش','خلیجی','لیزر','اصلاح صورت'])
   choices=root.locator('.petal-choice');assert await choices.count()==3
   piece=root.locator('.petal-piece').first;scatter=await piece.get_attribute('style');await choices.nth(1).click();assert scatter!=await root.locator('.petal-piece').first.get_attribute('style');assert await root.locator('.petal-choice').nth(1).get_attribute('aria-pressed')=='true'
   await root.locator('.petal-choice').nth(2).focus();await page.keyboard.press('Enter');assert await root.locator('.petal-choice').nth(2).get_attribute('aria-pressed')=='true'
   detail=root.locator('.saha-package').first;await detail.locator('summary').click();assert await root.locator('.saha-package').first.get_attribute('open') is not None
   like=root.locator('.saha-like').first;await like.click();assert await root.locator('.saha-like').first.get_attribute('aria-pressed')=='true'
   assert json.loads(await page.evaluate("localStorage.getItem('saha-trend-likes')"))['1'] is True
   cold=root.locator('#consult button.opt').filter(has_text='سرد');await cold.click();assert 'بلوند یخی' in await root.locator('#consult').inner_text()
   assert await root.locator('#team .card3').count()==7
   assert 'سهام شحیتی' in await root.locator('#team').inner_text()
   assert await root.locator('a[href="tel:09168285964"]').count()>=1 and await root.locator('a[href="https://wa.me/989165109932"]').count()>=1
   assert await root.locator('.saha-glass-button').count()==3
   assert await root.locator('canvas').get_attribute('data-burst-starts')=='1','انیمیشن با تعامل دوباره شروع شد'
   # Reveal every original section by actually scrolling; no section is silently dropped.
   for section in ['perks','why','popular','services','packages','trends','consult','team','certs','reviews','daily','work','contact']:
    loc=root.locator('#'+section);assert await loc.count()==1
    for item in await loc.locator('.rv').all():
     await item.scroll_into_view_if_needed();await page.wait_for_timeout(50)
   await page.wait_for_timeout(900)
   hidden=await root.locator('.reveal-pending').count();assert hidden==0,hidden
   assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
   await page.emulate_media(reduced_motion='reduce');await page.wait_for_timeout(100)
   assert await root.locator('canvas').evaluate('(e)=>getComputedStyle(e).display')=='none'
   assert await root.locator('.saha-motion-toggle').is_disabled()
   assert await root.locator('.saha-assembly').evaluate('(e)=>getComputedStyle(e).getPropertyValue("--assembly").trim()')=='1'
   assert await root.locator('.petal-piece').first.evaluate('(e)=>getComputedStyle(e).transitionDuration')=='0s'
   await page.emulate_media(reduced_motion='no-preference')
   await root.locator('.hero-actions a').first.click();assert await page.evaluate('location.hash')=='#contact'
   assert not errors,errors;assert not failed,failed
   cls=await page.evaluate('window.__cls');assert cls<.1,cls
   if width in [390,1440]:
    await page.evaluate("scrollTo({top:0,behavior:'instant'})");await page.wait_for_timeout(300);await page.screenshot(path=f'/tmp/saha-premium-full-{width}.png',full_page=True)
   results.append({'عرض':width,'ذرات':count,'جابجایی_چیدمان':round(cls,5),'خطاها':errors,'نتیجه':'موفق'})
   print(json.dumps(results[-1],ensure_ascii=False),flush=True)
   # Personal preferences remain after a real reload.
   if width==390:
    await page.goto(BASE,wait_until='networkidle');assert await page.locator('.saha-premium .saha-like').first.get_attribute('aria-pressed')=='true'
   await context.close()
  await browser.close()
 Path('/tmp/saha-premium-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
asyncio.run(main())
