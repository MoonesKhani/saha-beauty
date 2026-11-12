"""Footer gesture only: timing, interrupted clicks, and existing UI remain intact."""
import asyncio, os
from playwright.async_api import async_playwright
BASE=os.environ.get('SAHA_TEST_URL','http://127.0.0.1:8039').rstrip('/')
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'],proxy={'server':os.environ['HTTPS_PROXY'],'bypass':'127.0.0.1,localhost'})
  for width in [390,1440]:
   page=await browser.new_page(viewport={'width':width,'height':844},has_touch=width<768,is_mobile=width<768)
   await page.route('**/admin',lambda route:route.fulfill(status=200,body='<h1>Admin route reached</h1>'))
   async def home():
    await page.goto(BASE+'/',wait_until='networkidle');await page.locator('footer [data-admin-entry-logo]').wait_for()
   async def sequence(times,interrupt=False):
    await page.evaluate('''({times,interrupt})=>{
     const logo=document.querySelector('footer [data-admin-entry-logo] span'),original=performance.now;
     try{for(let i=0;i<times.length;i++){performance.now=()=>times[i];logo.click();if(interrupt&&i===2)document.querySelector('footer').click();}}
     finally{performance.now=original;}
    }''',{'times':times,'interrupt':interrupt})
   await home();before=await page.locator('footer').inner_text()
   await sequence([100,200,300,400]);await page.wait_for_timeout(100);assert '/admin' not in page.url
   assert await page.locator('footer').inner_text()==before
   await home();await sequence([100,900,1700,2500,3101]);await page.wait_for_timeout(100);assert '/admin' not in page.url
   await home();await sequence([100,200,300,400,500],True);await page.wait_for_timeout(100);assert '/admin' not in page.url
   await home();await sequence([100,800,1500,2200,3100]);await page.wait_for_url('**/admin')
   await home();logo=page.locator('footer [data-admin-entry-logo]');await logo.scroll_into_view_if_needed()
   for _ in range(5):await logo.click(delay=30)
   await page.wait_for_url('**/admin');print(f'{width}: timing boundary, timeout, interruption, real clicks and unchanged footer passed',flush=True)
   await page.close()
  await browser.close()
asyncio.run(main())
