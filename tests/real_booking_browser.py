"""End-to-end real server/database test with isolated temporary data and credentials."""
import asyncio,json,os,secrets,socket,subprocess,sys,tempfile,urllib.request
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
PYTHON=os.environ.get('SAHA_PYTHON',str(ROOT/'.venv/bin/python'))
async def main():
 with tempfile.TemporaryDirectory() as directory:
  token=secrets.token_hex(32)
  with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
  base=f'http://127.0.0.1:{port}'
  env={**os.environ,'DATABASE_URL':f'sqlite:///{directory}/booking.db','ADMIN_API_TOKEN':token,'SAHA_BOOKING_ENABLED':'1'}
  subprocess.run([PYTHON,'-m','backend.app.cli','init-db'],env=env,cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
  process=subprocess.Popen([PYTHON,'-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port',str(port)],env=env,cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  try:
   for _ in range(100):
    try:urllib.request.urlopen(base+'/health/ready',timeout=1);break
    except OSError:await asyncio.sleep(.1)
   day=(datetime.now(ZoneInfo('Asia/Tehran'))+timedelta(days=1)).date()
   body={'services':[{'service_code':'hair-braid','duration_minutes':45}],'windows':[{'weekday':day.weekday(),'start_minute':540,'end_minute':780,'step_minutes':30}]}
   request=urllib.request.Request(base+'/api/v1/admin/scheduling/01',method='PUT',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
   urllib.request.urlopen(request)
   async with async_playwright() as p:
    browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'],proxy={'server':os.environ['HTTPS_PROXY'],'bypass':'localhost,127.0.0.1'})
    for width in [390,1440]:
     context=await browser.new_context(viewport={'width':width,'height':1000});page=await context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     await page.goto(base+'/booking.html');await page.wait_for_function("document.querySelector('#reservation-status').textContent.includes('دلخواهت')")
     await page.get_by_label('بافت',exact=True).check();await page.locator('input[name=staff-hair-braid][value="01"]').check();await page.locator('#reservation-day').select_option(str(day))
     await page.locator('#availability button:not([disabled])').first.click();await page.locator('#reservation-name').fill('مشتری آزمون مرورگر '+str(width));await page.locator('#reservation-phone').fill('09123456789');await page.locator('#reserve-confirm').click()
     await page.wait_for_function("document.querySelector('#reservation-status').textContent.includes('کد پیگیری')")
     await page.locator('#availability button[disabled]').first.wait_for()
     assert await page.get_by_role('button',name='پرداخت · غیرفعال',exact=True).is_disabled()
     assert await page.evaluate('localStorage.length')==0
     admin=await context.new_page();await admin.goto(base+'/admin');await admin.locator('#admin-token').fill(token);await admin.locator('#login-form button[type=submit]').click();await admin.locator('#admin-app').wait_for(state='visible');await admin.locator('[data-section=appointments]').click();await admin.locator('#records-body tr').first.wait_for()
     assert 'مشتری آزمون مرورگر '+str(width) in await admin.locator('#records-body').inner_text();assert 'بافت' in await admin.locator('#records-body').inner_text()
     await admin.goto(base+'/scheduling.html');await admin.locator('#schedule-token').fill(token);await admin.locator('#schedule-login button').click();await admin.locator('#schedule-form').wait_for(state='visible');assert await admin.locator('[data-service=hair-braid]').input_value()=='45'
     assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth');assert not errors,errors
     await context.close();print(f'{width}: رزرو واقعی در سرور، اشغال ظرفیت، پنل احرازشده و برنامه ذخیره‌شده موفق؛ بدون پرداخت یا ذخیره محلی',flush=True)
    await browser.close()
  finally:process.terminate();process.wait(timeout=10)
if __name__=='__main__':asyncio.run(main())
