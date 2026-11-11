"""Service-filtered trends, grouped contacts, future AI and safe invitation sharing."""
import asyncio,os
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
BASE=os.environ.get('SAHA_TEST_URL','http://127.0.0.1:8038').rstrip('/')
MOCK="""Object.defineProperty(navigator,'clipboard',{configurable:true,writable:true,value:{writeText:async text=>{window.__copied=text;}}});Object.defineProperty(navigator,'share',{configurable:true,writable:true,value:async payload=>{window.__shared=payload;}});"""
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'],proxy={'server':os.environ['HTTPS_PROXY'],'bypass':'127.0.0.1,localhost'})
  for width in [320,390,412,1440]:
   context=await browser.new_context(viewport={'width':width,'height':900},is_mobile=width<768,has_touch=width<768);await context.add_init_script(MOCK)
   page=await context.new_page();errors=[];posts=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:posts.append(r.url) if r.method not in ['GET','HEAD'] else None)
   await page.goto(BASE+'/',wait_until='networkidle');await page.evaluate('document.fonts.ready');await page.locator('.trend-category').first.wait_for()
   assert await page.locator('.trend-category').count()==10;assert await page.locator('#trends .trend').count()==0
   assert await page.locator('.compact-colour-fold,.friend-invite').count()==0;assert await page.locator('#consult [aria-label*="تصویر کارتونی"]').count()==0
   assert await page.locator('.compact-fold-icon').count()==3
   await page.locator('#trends').screenshot(path=f'/tmp/saha-v3-trends-{width}.png',scale='css')
   for name,count in [('مو',2),('میکاپ',1),('ناخن',1),('پوست',1)]:
    await page.get_by_role('button',name=name,exact=True).click();assert await page.locator('#trends .trend').count()==count,(name,count)
   await page.locator('#trends .saha-like').click();assert await page.locator('#trends .saha-like').get_attribute('aria-pressed')=='true'
   await page.get_by_role('button',name='ژل و فیلر',exact=True).click();assert await page.locator('#trends .trend').count()==0;assert 'هنوز پیشنهاد تأییدشده‌ای' in await page.locator('.trend-empty').inner_text()
   for kind,expected in [('phone',['tel:09168285964','tel:09165109932']),('whatsapp',['https://wa.me/989168285964','https://wa.me/989165109932'])]:
    group=page.locator(f'[data-contact-group="{kind}"]');assert await group.count()==1;assert await group.locator('a').evaluate_all('(els)=>els.map(e=>e.getAttribute("href"))')==expected
    assert (await group.bounding_box())['height']<165
   assert await page.locator('#contact-info .contact-group').count()==4
   await page.locator('#contact-info').screenshot(path=f'/tmp/saha-v3-contacts-{width}.png',scale='css')
   assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
   menu=page.locator('.saha-premium header .saha-more');await menu.locator('summary').click();await menu.get_by_role('link',name='مشاوره هوشمند · به‌زودی',exact=True).click();await page.wait_for_url('**/ai-consultation.html')
   assert await page.locator('#ai-photo').is_disabled();assert await page.get_by_role('button',name='شروع مشاوره · به‌زودی',exact=True).is_disabled();assert 'هیچ عکسی' in await page.locator('#ai-privacy').inner_text()
   await page.screenshot(path=f'/tmp/saha-v3-ai-{width}.png',full_page=True,scale='css')
   await page.get_by_role('link',name='بازگشت به صفحه اصلی ←',exact=True).click();await page.locator('.trend-category').first.wait_for();await menu.locator('summary').click();await menu.get_by_role('link',name='دعوت از دوست ♡',exact=True).click();await page.wait_for_url('**/invite.html')
   text=await page.locator('#invite-text').input_value();assert 'https://sahabeauty.ir/' in text
   await page.screenshot(path=f'/tmp/saha-v3-invite-{width}.png',full_page=True,scale='css')
   await page.locator('#copy-invite').click();assert await page.evaluate('window.__copied')==text;assert 'کپی شد' in await page.locator('#invite-status').inner_text()
   await page.locator('#share-invite').click();assert (await page.evaluate('window.__shared'))['text']==text
   await page.evaluate("()=>{navigator.share=async()=>{throw new DOMException('cancelled','AbortError')};}");await page.locator('#share-invite').click();assert 'لغو شد' in await page.locator('#invite-status').inner_text()
   await page.evaluate('navigator.share=undefined');await page.locator('#share-invite').click();assert 'متن کپی شد' in await page.locator('#invite-status').inner_text()
   await page.evaluate("navigator.clipboard.writeText=async()=>{throw new Error('denied')};document.execCommand=()=>false;");await page.locator('#copy-invite').click();assert 'کپی خودکار ممکن نشد' in await page.locator('#invite-status').inner_text()
   assert not errors,errors;assert not posts,posts;assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
   print(f'{width}: دسته‌بندی ۱۰ خدمت، لایک، تماس‌های ادغام‌شده، AI غیرفعال و کپی/اشتراک/لغو/جایگزین موفق',flush=True);await context.close()
  context=await browser.new_context(viewport={'width':390,'height':900},is_mobile=True,has_touch=True);await context.add_init_script(MOCK);page=await context.new_page();http=[];errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:http.append(r.url) if r.url.startswith('http') else None)
  await page.route(BASE+'/offline-v3.html',lambda route:route.fulfill(body=Path('/tmp/saha-mobile-v3-preview.html').read_text(),content_type='text/html'))
  await page.goto(BASE+'/offline-v3.html',wait_until='networkidle');await page.locator('.trend-category').first.wait_for();assert len(http)==1,http
  await page.get_by_role('button',name='مو',exact=True).click();assert await page.locator('#trends .trend').count()==2
  await page.locator('.saha-premium header .saha-more summary').click();await page.get_by_role('link',name='مشاوره هوشمند · به‌زودی',exact=True).click();await page.wait_for_url('blob:**');assert await page.locator('#ai-photo').is_disabled()
  await page.get_by_role('link',name='بازگشت به صفحه اصلی ←',exact=True).click();await page.locator('.saha-premium header .saha-more summary').click();await page.get_by_role('link',name='دعوت از دوست ♡',exact=True).click();await page.wait_for_url('blob:**');await page.locator('#copy-invite').click();assert 'https://sahabeauty.ir/' in await page.evaluate('window.__copied');assert not errors,errors
  print('پیش‌نمایش مستقل: بدون فایل جانبی، صفحات AI و دعوت و کپی متن سالم‌اند.',flush=True);await browser.close()
if __name__=='__main__':asyncio.run(main())
