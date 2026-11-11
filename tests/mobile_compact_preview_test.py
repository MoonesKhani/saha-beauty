"""Chrome mobile geometry, real touch scrolling, stale assets and standalone preview."""
import asyncio,json,os,subprocess
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
BASE=os.environ.get('SAHA_TEST_URL','http://127.0.0.1:8037').rstrip('/')
UA='Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36'
async def swipe(context,page,selector):
 target=page.locator(selector);await target.scroll_into_view_if_needed();box=await target.bounding_box();x=box['x']+35;y=box['y']+min(box['height']/2,100)
 session=await context.new_cdp_session(page)
 await session.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]})
 for i in range(1,7):
  await session.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x+i*25,'y':y}]});await page.wait_for_timeout(30)
 await session.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]});await page.wait_for_timeout(400);await session.detach()
async def main():
 results={}
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'],proxy={'server':os.environ['HTTPS_PROXY'],'bypass':'127.0.0.1,localhost'})
  for width in [int(w) for w in os.environ.get('SAHA_TEST_WIDTHS','320,360,390,412,768,1440').split(',') if w.strip()]:
   mobile=width<768;context=await browser.new_context(viewport={'width':width,'height':900},is_mobile=mobile,has_touch=mobile,device_scale_factor=2 if mobile else 1,user_agent=UA if mobile else None)
   page=await context.new_page();errors=[];stale=[];page.on('pageerror',lambda e:errors.append(str(e)))
   async def legacy(route):stale.append(route.request.url);await route.fulfill(body='/* stale asset must not be requested */',content_type='text/css')
   await page.route('**/assets/saha-premium.css',legacy);await page.route('**/assets/saha-premium.js',legacy)
   await page.goto(BASE+'/',wait_until='networkidle');await page.evaluate('document.fonts.ready');await page.locator('[data-music-icon]').wait_for()
   assert await page.locator('meta[name=saha-release]').get_attribute('content')=='mobile-compact-v4-preview'
   assert not stale
   header=page.locator('.saha-premium header');boxes=[await header.locator(s).bounding_box() for s in ['a[href="#top"]','a[href="/booking.html"]','.saha-more summary']]
   assert max(b['y']+b['height']/2 for b in boxes)-min(b['y']+b['height']/2 for b in boxes)<2,boxes
   ordered=sorted(boxes,key=lambda b:b['x']);assert all(a['x']+a['width']<=b['x']+1 for a,b in zip(ordered,ordered[1:])),ordered
   actions=page.locator('.hero-actions-v2>a');action_boxes=await actions.evaluate_all('(els)=>els.map(e=>({y:e.getBoundingClientRect().y,height:e.getBoundingClientRect().height}))');assert len(action_boxes)==2 and abs(action_boxes[0]['y']-action_boxes[1]['y'])<2 and all(b['height']>=44 for b in action_boxes)
   hours=await page.locator('.compact-hours').evaluate('(e)=>({height:e.getBoundingClientRect().height,border:getComputedStyle(e).borderWidth,background:getComputedStyle(e).backgroundColor})');assert hours['height']<30 and hours['border']=='0px'
   assert await page.locator('#services .svc h3').all_text_contents()==['اصلاح','پاکسازی','ناخن'];cards=await page.locator('#services .svc').evaluate_all('(els)=>els.map(e=>({left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right,height:e.getBoundingClientRect().height}))');assert all(c['height']<=170 and c['left']>=0 and c['right']<=inner_width+1 for c in cards for inner_width in [width]),cards
   assert await page.locator('.petal-playground,.beauty-game,#work').count()==0
   assert await page.locator('.saha-assembly').evaluate('(e)=>e.getBoundingClientRect().width')<=74
   results[str(width)]=await page.evaluate('document.documentElement.scrollHeight')
   await page.screenshot(path=f'/tmp/saha-mobile-v4-hero-{width}.png',scale='css')
   await page.locator('#services').screenshot(path=f'/tmp/saha-mobile-v4-services-{width}.png',scale='css')
   await page.locator('#packages').screenshot(path=f'/tmp/saha-mobile-v4-packages-{width}.png',scale='css')
   await page.get_by_role('button',name='مشاهده همه خدمات',exact=True).click();assert await page.locator('#services .svc').count()==10;names=await page.locator('#services .svc h3').all_text_contents();assert 'ابرو' not in names and 'عروس' not in names and 'تزریق ژل و فیلر' in names
   if mobile:await swipe(context,page,'#service-cards')
   else:await page.get_by_role('button',name='خدمات بعدی',exact=True).click();await page.wait_for_timeout(400)
   assert await page.locator('#service-cards').evaluate('(e)=>Math.abs(e.scrollLeft)>15')
   await page.get_by_role('button',name='نمایش خدمات پرتقاضا',exact=True).click();assert await page.locator('#services .svc').count()==3
   overflowing=await page.locator('#package-cards').evaluate('(e)=>e.scrollWidth>e.clientWidth+1')
   if overflowing:
    if mobile:await swipe(context,page,'#package-cards')
    else:await page.get_by_role('button',name='پکیج بعدی',exact=True).click();await page.wait_for_timeout(400)
    assert await page.locator('#package-cards').evaluate('(e)=>Math.abs(e.scrollLeft)>15')
   else:assert await page.get_by_role('button',name='پکیج بعدی',exact=True).is_disabled()
   y=await page.locator('#package-cards>.card3').evaluate_all('(els)=>els.map(e=>Math.round(e.getBoundingClientRect().top))');assert len(set(y))==1
   music=page.locator('[data-saha-music]');assert (await music.inner_text()).strip()=='';assert await music.locator('svg').count()==1
   await music.click();await page.wait_for_function("document.querySelector('[data-saha-music]').getAttribute('aria-pressed')==='true'");await music.click()
   await header.locator('.saha-more summary').click();assert await header.get_by_role('link',name='گالری نمونه‌کارها',exact=True).is_visible();await page.keyboard.press('Escape')

   if await page.locator('a[href="#reviews"]').first.is_visible():await page.locator('a[href="#reviews"]').first.click()
   else:await page.locator('.compact-fold>summary').filter(has_text='نظر مشتریان').click()
   assert await page.locator('#reviews').evaluate('(e)=>e.closest("details").open')
   assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth');assert not errors,errors
   print(f'{width}: Chrome، چیدمان ردیفی، ۳ خدمت کوچک، لمس افقی، آیکون SVG و منو موفق؛ ارتفاع {results[str(width)]}',flush=True)
   await context.close()
  # Serve the downloaded HTML as one document; all application assets must be inline.
  context=await browser.new_context(viewport={'width':390,'height':900},is_mobile=True,has_touch=True,user_agent=UA);page=await context.new_page();requests=[];errors=[];page.on('request',lambda r:requests.append(r.url) if r.url.startswith('http') else None);page.on('pageerror',lambda e:errors.append(str(e)))
  await page.route(BASE+'/standalone-preview.html',lambda route:route.fulfill(body=Path('/tmp/saha-mobile-v4-preview.html').read_text(),content_type='text/html'))
  await page.goto(BASE+'/standalone-preview.html',wait_until='networkidle');await page.locator('#services .svc').first.wait_for();assert await page.locator('#services .svc').count()==3;assert len(requests)==1,requests
  await page.locator('.saha-more summary').click();await page.get_by_role('link',name='تخفیف و شانس زیبایی ✨',exact=True).click();await page.wait_for_url('blob:**');await page.locator('[data-beauty-petal="1"]').click();assert 'نمایشی' in await page.locator('.beauty-game-result').inner_text()
  await page.get_by_role('link',name='بازگشت به صفحه اصلی ←',exact=True).click();await page.locator('#services .svc').first.wait_for();await page.locator('.saha-more summary').click();await page.get_by_role('link',name='گالری نمونه‌کارها',exact=True).click();await page.wait_for_url('blob:**');await page.locator('#gallery-empty').wait_for(state='visible');assert not errors,errors
  print('فایل مستقل: بدون درخواست فایل جانبی؛ تخفیف، گالری و بازگشت به پیش‌نمایش موفق',flush=True)
  await browser.close()
 Path('/tmp/saha-mobile-v4-results.json').write_text(json.dumps(results))
if __name__=='__main__':asyncio.run(main())
