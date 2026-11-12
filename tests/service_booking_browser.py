"""Real isolated DB/browser checks for service shortcuts, specialists, private reviews and team."""
import asyncio,json,os,secrets,socket,subprocess,tempfile,urllib.request
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
  base=f'http://127.0.0.1:{port}';env={**os.environ,'DATABASE_URL':f'sqlite:///{directory}/booking.db','ADMIN_API_TOKEN':token,'SAHA_BOOKING_ENABLED':'1'}
  subprocess.run([PYTHON,'frontend/build.py'],cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL)
  subprocess.run([PYTHON,'-m','backend.app.cli','init-db'],cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  process=subprocess.Popen([PYTHON,'-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  def request(path,body=None,method=None):
   req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,method=method,headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
   with urllib.request.urlopen(req) as r:return json.load(r)
  try:
   for _ in range(100):
    try:request('/health/ready');break
    except OSError:await asyncio.sleep(.1)
   day=(datetime.now(ZoneInfo('Asia/Tehran'))+timedelta(days=1)).date()
   for member,service in [('01','hair-braid'),('02','hair-color'),('03','02')]:
    request('/api/v1/admin/scheduling/'+member,{'services':[{'service_code':service,'duration_minutes':30}],'windows':[{'weekday':day.weekday(),'start_minute':540,'end_minute':1080,'step_minutes':30}]},'PUT')
   async with async_playwright() as p:
    browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'],proxy={'server':os.environ['HTTPS_PROXY'],'bypass':'127.0.0.1,localhost'})
    for index,width in enumerate([320,390,1440]):
     context=await browser.new_context(viewport={'width':width,'height':900},has_touch=width<768,is_mobile=width<768);page=await context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     await page.goto(base+'/',wait_until='networkidle');await page.locator('#services .svc').first.wait_for()
     links=await page.locator('#services .svc').evaluate_all('(els)=>els.map(e=>e.getAttribute("href"))');assert set(links)=={'/booking.html?service=11','/booking.html?service=03','/booking.html?service=02'},links
     assert await page.locator('footer .saha-footer').count()==0
     assert 'تصاویر، تصویرسازی‌های تزئینی' not in await page.locator('#team').inner_text()
     cards=page.locator('.team-member-card');assert await cards.count()==7
     bounds=await cards.first.bounding_box();assert bounds['height']<160,bounds
     await page.locator('#team').screenshot(path=f'/tmp/saha-team-compact-{width}.png',scale='css')
     await page.locator('.team-member-name').first.click();await page.wait_for_url('**/team-member.html?member=01');assert await page.locator('#member-name').inner_text()=='سهام شحیتی'
     await page.goto(base+'/',wait_until='networkidle');await page.locator('#services .svc').first.wait_for();await page.locator('.compact-fold>summary').click();await page.locator('[data-review-open]').click();await page.locator('#customer-review-dialog').wait_for(state='visible')
     await page.locator('#customer-review-form [name=customer_name]').fill('نظر آزمون '+str(width));await page.locator('#customer-review-form [name=phone]').fill('09123456789');await page.locator('#customer-review-form [name=message]').fill('از همراهی تیم سها ممنونم.');await page.locator('#customer-review-form [type=submit]').click();await page.wait_for_function("document.getElementById('customer-review-status').textContent.includes('به سالن رسید')")
     assert any(x['customer_name']=='نظر آزمون '+str(width) for x in request('/api/v1/admin/consultations')['items'])
     await page.locator('[data-review-close]').click();await page.locator('#services a[href="/booking.html?service=02"]').click();await page.wait_for_url('**/booking.html?service=02');await page.wait_for_function("document.querySelector('#reservation-status').textContent.includes('دلخواهت')")
     assert await page.locator('#service-selection').is_hidden();assert await page.locator('.reservation-choice h3').all_text_contents()==['ناخن'];await page.locator('#reminder-toggle').click();assert await page.locator('#reminder-toggle').get_attribute('aria-pressed')=='true'
     await page.locator('input[name=staff-02][value="03"]').check();await page.locator('#reservation-day').select_option(str(day));await page.locator('.reservation-time-slots button:not([disabled])').nth(index).click();await page.locator('#reservation-name').fill('ناخن آزمون '+str(width));await page.locator('#reservation-phone').fill('09123456789');await page.locator('#reserve-confirm').click();await page.wait_for_function("document.querySelector('#reservation-status').textContent.includes('کد پیگیری')")
     single=request('/api/v1/admin/appointments')['items'];record=next(r for r in single if r['customer_name']=='ناخن آزمون '+str(width));assert record['service_codes']==['02']
     await page.goto(base+'/booking.html',wait_until='networkidle');await page.wait_for_function("document.querySelector('#reservation-status').textContent.includes('دلخواهت')")
     await page.get_by_label('بافت',exact=True).check();await page.get_by_label('رنگ',exact=True).check();await page.locator('input[name=staff-hair-braid][value="01"]').check();await page.locator('input[name=staff-hair-color][value="02"]').check();await page.locator('#reservation-day').select_option(str(day));groups=page.locator('.reservation-time-group');await groups.nth(0).locator('button:not([disabled])').nth(index).click();await groups.nth(1).locator('button:not([disabled])').nth(index+6).click();await page.locator('#reservation-name').fill('چندخدمت آزمون '+str(width));await page.locator('#reservation-phone').fill('09123456789');assert await page.get_by_role('button',name='پرداخت · غیرفعال').is_disabled()
     assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');await page.screenshot(path=f'/tmp/saha-booking-multi-{width}.png',full_page=True,scale='css')
     await page.locator('#reserve-confirm').click();await page.wait_for_function("document.querySelector('#reservation-status').textContent.includes('کد پیگیری')")
     records=[r for r in request('/api/v1/admin/appointments')['items'] if r['customer_name']=='چندخدمت آزمون '+str(width)];assert len(records)==2 and {r['staff_code'] for r in records}=={'01','02'}
     admin=await context.new_page();await admin.goto(base+'/admin');await admin.locator('#admin-token').fill(token);await admin.locator('#login-form button[type=submit]').click();await admin.locator('#admin-app').wait_for(state='visible');await admin.locator('[data-section=appointments]').click();await admin.locator('#records-body tr').first.wait_for();assert 'چندخدمت آزمون '+str(width) in await admin.locator('#records-body').inner_text()
     assert not errors,errors;await context.close();print(f'{width}: single service, separate specialists, persisted bookings, private review, team links and responsive layout passed',flush=True)
    await browser.close()
  finally:process.terminate();process.wait(timeout=10)
if __name__=='__main__':asyncio.run(main())
