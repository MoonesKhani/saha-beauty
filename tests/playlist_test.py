"""آزمون صفحه پلی‌لیست؛ نیازمند Playwright و Chromium و سرور محلی."""
import asyncio, os
from pathlib import Path
from playwright.async_api import async_playwright
BASE=os.environ.get('SAHA_TEST_URL','http://127.0.0.1:8033').rstrip('/')
ROOT=Path(__file__).resolve().parents[1]
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'],proxy={'server':os.environ['HTTPS_PROXY'],'bypass':'127.0.0.1,localhost'})
  for width in [320,390,768,1440]:
   page=await browser.new_page(viewport={'width':width,'height':900});errors=[];writes=[]
   page.on('pageerror',lambda e:errors.append(str(e)))
   page.on('request',lambda r:writes.append(r.url) if r.method not in ['GET','HEAD'] else None)
   await page.goto(BASE+'/');await page.locator('.saha-premium .perk').filter(has_text='پلی‌لیست مشتری').click();await page.wait_for_url('**/playlist.html')
   await page.get_by_role('button',name='♡ لایک',exact=True).click();await page.get_by_role('button',name='ذخیره',exact=True).click();await page.reload()
   assert await page.get_by_role('button',name='♥ لایک شد',exact=True).get_attribute('aria-pressed')=='true'
   assert await page.get_by_role('button',name='✓ ذخیره شد',exact=True).get_attribute('aria-pressed')=='true'
   await page.locator('#song-list audio').evaluate('(a)=>a.play()');await page.wait_for_timeout(500);assert await page.locator('#song-list audio').evaluate('(a)=>a.currentTime>0 && !a.paused')
   await page.locator('#saved-only').check();await page.get_by_role('button',name='✓ ذخیره شد',exact=True).click();assert await page.locator('#empty-songs').is_visible();await page.locator('#saved-only').uncheck()
   await page.locator('#song-name').fill('<img src=x onerror=alert(1)>');await page.locator('#artist-name').fill('آزمایشی');await page.get_by_role('button',name='پیشنهاد آهنگ ♡').click();assert await page.locator('#suggestions li').count()==1;assert await page.locator('#suggestions img').count()==0
   await page.locator('#audio-file').set_input_files(str(ROOT/'assets/saha-quiet-bloom.mp3'));assert await page.locator('#local-files audio').count()==1;assert (await page.locator('#local-files audio').get_attribute('src')).startswith('blob:')
   await page.locator('#local-files audio').evaluate('(a)=>a.play()');assert await page.locator('#song-list audio').evaluate('(a)=>a.paused')
   await page.get_by_role('button',name='حذف فایل آزمایشی').click();assert await page.locator('#local-files audio').count()==0
   await page.locator('#audio-file').set_input_files({'name':'bad.txt','mimeType':'text/plain','buffer':b'not audio'});assert 'فایل صوتی' in await page.locator('#playlist-status').inner_text()
   assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth');assert not writes,writes;assert not errors,errors
   await page.emulate_media(reduced_motion='reduce');assert await page.locator('.petal').evaluate('(e)=>getComputedStyle(e).animationName')=='none'
   await page.reload();assert await page.locator('#suggestions li').count()==0;assert await page.locator('#local-files audio').count()==0
   await page.evaluate("localStorage.setItem('saha-playlist-preferences-v1','broken')");await page.reload();assert await page.locator('#song-list audio').count()==1
   print(f'{width}: مسیریابی، پخش واقعی، ذخیره مرورگر، پیشنهاد، فایل محلی و کاهش حرکت موفق؛ بدون ارسال داده',flush=True)
   await page.close()
  context=await browser.new_context();await context.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw new Error('blocked')}})")
  page=await context.new_page();await page.goto(BASE+'/playlist.html');await page.get_by_role('button',name='♡ لایک',exact=True).click();assert await page.get_by_role('button',name='♥ لایک شد',exact=True).is_visible();assert 'اجازه ذخیره' in await page.locator('#playlist-status').inner_text()
  await browser.close()
if __name__=='__main__':asyncio.run(main())
