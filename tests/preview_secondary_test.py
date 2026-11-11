"""Unpublished preview: independent optional pages and compact human contact."""
import asyncio,os
from pathlib import Path
from playwright.async_api import async_playwright
BASE=os.environ.get('SAHA_TEST_URL','http://127.0.0.1:8039').rstrip('/')
MOCK="""Object.defineProperty(navigator,'clipboard',{configurable:true,writable:true,value:{writeText:async text=>{window.__copied=text;}}});Object.defineProperty(navigator,'share',{configurable:true,writable:true,value:async payload=>{window.__shared=payload;}});"""
async def open_menu(page,label):
 await page.locator('#services .svc').first.wait_for()
 menu=page.locator('.saha-premium header .saha-more');await menu.locator('summary').click();await menu.get_by_role('link',name=label,exact=True).click()
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'],proxy={'server':os.environ['HTTPS_PROXY'],'bypass':'127.0.0.1,localhost'})
  for width in [320,390,412,1440]:
   context=await browser.new_context(viewport={'width':width,'height':900},is_mobile=width<768,has_touch=width<768);await context.add_init_script(MOCK)
   page=await context.new_page();errors=[];posts=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:posts.append(r.url) if r.method not in ['GET','HEAD'] else None)
   await page.goto(BASE+'/',wait_until='networkidle');await page.evaluate('document.fonts.ready');await page.locator('#services .svc').first.wait_for()
   assert await page.locator('#trends,#popular,#daily,#certs,.compact-colour-fold,.friend-invite').count()==0
   assert await page.locator('.compact-fold-icon').count()==1
   why=await page.locator('#why .gb').evaluate_all('(els)=>els.map(e=>({height:e.getBoundingClientRect().height,left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right}))');assert len(why)==3 and all(w['height']<=140 and w['left']>=0 and w['right']<=width+1 for w in why),why
   assert (await page.locator('#consult').bounding_box())['height']<=190
   arabic=page.locator('.arabic-welcome');assert await arabic.get_attribute('lang')=='ar';assert 'أهلًا وسهلًا بكِ في سَها' in await arabic.inner_text();font=await arabic.evaluate('(e)=>getComputedStyle(e).fontFamily');assert 'Nastaliq' not in font and 'Signature' not in font,font
   left=await arabic.bounding_box();right=await page.locator('.contact-welcome h2').bounding_box();assert abs(left['y']+left['height']/2-right['y']-right['height']/2)<3
   for kind,expected in [('phone',['tel:09168285964','tel:09165109932']),('whatsapp',['https://wa.me/989168285964','https://wa.me/989165109932'])]:
    group=page.locator(f'[data-contact-group="{kind}"]');assert await group.count()==1;assert await group.locator('a').evaluate_all('(els)=>els.map(e=>e.getAttribute("href"))')==expected;assert (await group.bounding_box())['height']<115
   await page.locator('#why').screenshot(path=f'/tmp/saha-v4-why-{width}.png',scale='css');await page.locator('#consult').screenshot(path=f'/tmp/saha-v4-consult-{width}.png',scale='css');await page.locator('#contact').screenshot(path=f'/tmp/saha-v4-contact-{width}.png',scale='css')
   assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
   for label,path,title in [('روزمره سها','daily.html','روزمره سها'),('مدارک و دوره‌ها','certificates.html','مدارک و دوره‌ها')]:
    await open_menu(page,label);await page.wait_for_url('**/'+path);assert await page.get_by_role('heading',name=title,exact=True).is_visible();assert 'در حال آماده‌سازی' in await page.locator('.future-section').inner_text();await page.get_by_role('link',name='بازگشت به صفحه اصلی ←',exact=True).click()
   await open_menu(page,'ترندهای زیبایی');await page.wait_for_url('**/trends.html');await page.locator('.standalone-trend-category').first.wait_for();assert await page.locator('.standalone-trend-category').count()==10
   for name,count in [('مو',2),('میکاپ',1),('ناخن',1),('پوست',1)]:
    await page.get_by_role('button',name=name,exact=True).click();assert await page.locator('.standalone-trend-card').count()==count
   await page.locator('.standalone-trend-card button').click();assert await page.locator('.standalone-trend-card button').get_attribute('aria-pressed')=='true'
   await page.get_by_role('button',name='ژل و فیلر',exact=True).click();assert await page.locator('.standalone-trend-card').count()==0;assert 'هنوز پیشنهاد' in await page.locator('#trends-status').inner_text()
   assert await page.locator('.compact-page-title').evaluate('(e)=>parseFloat(getComputedStyle(e).fontSize)')<=28
   await page.screenshot(path=f'/tmp/saha-v4-trends-{width}.png',full_page=True,scale='css');await page.get_by_role('link',name='بازگشت به صفحه اصلی ←',exact=True).click()
   await open_menu(page,'مشاوره هوشمند · به‌زودی');await page.wait_for_url('**/ai-consultation.html');assert await page.locator('#ai-photo').is_disabled();await page.get_by_role('link',name='بازگشت به صفحه اصلی ←',exact=True).click()
   await open_menu(page,'دعوت از دوست ♡');await page.wait_for_url('**/invite.html');text=await page.locator('#invite-text').input_value();assert 'https://sahabeauty.ir/' in text
   await page.locator('#copy-invite').click();assert await page.evaluate('window.__copied')==text
   await page.locator('#share-invite').click();assert (await page.evaluate('window.__shared'))['text']==text
   await page.evaluate("()=>{navigator.share=async()=>{throw new DOMException('cancelled','AbortError')};}");await page.locator('#share-invite').click();assert 'لغو شد' in await page.locator('#invite-status').inner_text()
   await page.evaluate('navigator.share=undefined');await page.locator('#share-invite').click();assert 'متن کپی شد' in await page.locator('#invite-status').inner_text()
   await page.evaluate("navigator.clipboard.writeText=async()=>{throw new Error('denied')};document.execCommand=()=>false;");await page.locator('#copy-invite').click();assert 'کپی خودکار ممکن نشد' in await page.locator('#invite-status').inner_text()
   assert not errors,errors;assert not posts,posts;assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
   print(f'{width}: حذف بخش‌های اصلی، سه صفحه مستقل، معرفی و گفتگوی کوچک، خوشامد عربی و تماس فشرده موفق',flush=True);await context.close()
  context=await browser.new_context(viewport={'width':390,'height':900},is_mobile=True,has_touch=True);await context.add_init_script(MOCK);page=await context.new_page();http=[];errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:http.append(r.url) if r.url.startswith('http') else None)
  await page.route(BASE+'/offline-v4.html',lambda route:route.fulfill(body=Path('/tmp/saha-mobile-v4-preview.html').read_text(),content_type='text/html'))
  await page.goto(BASE+'/offline-v4.html',wait_until='networkidle');await page.locator('#services .svc').first.wait_for();assert len(http)==1,http
  for label,title in [('روزمره سها','روزمره سها'),('مدارک و دوره‌ها','مدارک و دوره‌ها')]:
   await open_menu(page,label);await page.wait_for_url('blob:**');assert await page.get_by_role('heading',name=title,exact=True).is_visible();await page.get_by_role('link',name='بازگشت به صفحه اصلی ←',exact=True).click()
  await open_menu(page,'ترندهای زیبایی');await page.wait_for_url('blob:**');await page.get_by_role('button',name='مو',exact=True).click();assert await page.locator('.standalone-trend-card').count()==2;await page.get_by_role('link',name='بازگشت به صفحه اصلی ←',exact=True).click()
  await open_menu(page,'دعوت از دوست ♡');await page.wait_for_url('blob:**');await page.locator('#copy-invite').click();assert 'https://sahabeauty.ir/' in await page.evaluate('window.__copied');assert not errors,errors
  print('پیش‌نمایش مستقل: هر سه صفحه جدید بدون فایل جانبی اجرا شدند؛ دعوت و بازگشت هم سالم‌اند.',flush=True);await browser.close()
if __name__=='__main__':asyncio.run(main())
