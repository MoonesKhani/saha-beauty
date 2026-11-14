"""Live owner edits, package calculator, specialist cards and gallery on mobile/desktop."""
import asyncio,json,os,secrets,socket,subprocess,tempfile,urllib.request
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
PYTHON=str(ROOT/'.venv/bin/python')
async def main():
 with tempfile.TemporaryDirectory() as directory:
  token=secrets.token_hex(32)
  with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
  base=f'http://127.0.0.1:{port}';env={**os.environ,'DATABASE_URL':f'sqlite:///{directory}/test.db','ADMIN_API_TOKEN':token,'SAHA_BOOKING_ENABLED':'1'}
  subprocess.run([PYTHON,'frontend/build.py'],cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL)
  subprocess.run([PYTHON,'-m','backend.app.cli','init-db'],cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL)
  process=subprocess.Popen([PYTHON,'-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  def api(path,body=None,method=None):
   req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,method=method,headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
   with urllib.request.urlopen(req,timeout=10) as r:return json.load(r)
  try:
   for _ in range(100):
    try:api('/health/ready');break
    except OSError:await asyncio.sleep(.1)
   async with async_playwright() as p:
    browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox','--no-proxy-server'])
    # Only CDN reads pass through the inherited managed proxy with TLS verification.
    async def cdn(route):
     def read():
      with urllib.request.urlopen(route.request.url,timeout=20) as r:return r.read()
     await route.fulfill(body=await asyncio.to_thread(read),content_type='application/javascript')
    for width in [390,1440]:
     service=api('/api/v1/services/02');api('/api/v1/admin/services/02',{'revision':service['revision'],'price_toman':None},'PATCH')
     package=next(p for p in api('/api/v1/admin/packages')['items'] if p['code']=='companion-vip');api('/api/v1/admin/packages/companion-vip',{k:package[k] for k in ['name','category','tier','description','price_toman','is_active','revision']}|{'service_codes':[]},'PUT')
     context=await browser.new_context(viewport={'width':width,'height':1000});await context.route('https://cdn.jsdelivr.net/**',cdn)
     page=await context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     await page.goto(base+'/bridal.html');await page.locator('#package-select').wait_for();await page.wait_for_function("document.querySelector('#package-total').textContent.includes('۱۵٬۰۰۰٬۰۰۰')")
     assert await page.locator('.package-comparison th').count()>9
     assert await page.locator('input[name=service]:checked').count()==4
     await page.locator('input[name=service][value="02"]').check()
     await page.wait_for_function("document.querySelector('#package-total').textContent.includes('تعرفه برخی')")
     assert await page.locator('input[name=staff-02]').count()==1
     assert await page.locator('input[name=staff-02]').get_attribute('value')=='02'
     # Owner enters a tariff through the actual management UI.
     admin=await context.new_page();await admin.goto(base+'/admin');await admin.locator('#admin-token').fill(token);await admin.locator('#login-form button').click();await admin.locator('#admin-app').wait_for(state='visible')
     await admin.locator('[data-section=prices]').click();await admin.get_by_role('button',name='ویرایش ناخن',exact=True).click();await admin.locator('#field-price_toman').fill('700000');await admin.locator('#save-record').click();await admin.locator('#record-dialog').wait_for(state='hidden')
     await page.reload();await page.locator('#package-select').wait_for();await page.locator('input[name=service][value="02"]').check()
     await page.wait_for_function("document.querySelector('#package-total').textContent.includes('۱۵٬۷۰۰٬۰۰۰')")
     await page.locator('#package-select').select_option('companion-vip');await page.wait_for_function("document.querySelector('#package-total').textContent.includes('هنوز از پنل')")
     assert await page.locator('input[name=service]:checked').count()==0
     assert await page.locator('#reserve-confirm').is_disabled()
     # Define the companion services through the panel and observe its public page.
     await admin.locator('[data-section=packages]').click();await admin.get_by_role('button',name='ویرایش همراه عروس · VIP',exact=True).click()
     await admin.locator('[data-package-service="04"]').check();await admin.locator('[data-package-service="hair-updo"]').check();await admin.locator('#save-record').click();await admin.locator('#record-dialog').wait_for(state='hidden')
     await page.goto(base+'/bridal.html?package=companion-vip');await page.wait_for_function("document.querySelector('#package-total').textContent.includes('قیمت نهایی: ۳٬۵۰۰٬۰۰۰')")
     assert await page.locator('input[name=service]:checked').count()==2
     # Reserve the configured package with two real specialists and a captured quote.
     day=(datetime.now(ZoneInfo('Asia/Tehran'))+timedelta(days=1)).date()
     for staff,code in [('03','04'),('01','hair-updo')]:
      api('/api/v1/admin/scheduling/'+staff,{'services':[{'service_code':code,'duration_minutes':30}],'windows':[{'weekday':day.weekday(),'start_minute':540,'end_minute':780,'step_minutes':30}]},'PUT')
     await page.locator('input[name=staff-04][value="03"]').check();await page.locator('input[name=staff-hair-updo][value="01"]').check();await page.locator('#reservation-day').select_option(str(day))
     groups=page.locator('.reservation-time-group');index=0 if width==390 else 2
     await groups.nth(0).locator('button:not([disabled])').nth(index).click();await groups.nth(1).locator('button:not([disabled])').nth(index+1).click()
     await page.locator('#reservation-name').fill('پکیج آزمون '+str(width));await page.locator('#reservation-phone').fill('09123456789');await page.locator('#reserve-confirm').click();await page.wait_for_function("document.querySelector('#reservation-status').textContent.includes('کد پیگیری')")
     records=[r for r in api('/api/v1/admin/appointments')['items'] if r['customer_name']=='پکیج آزمون '+str(width)];assert len(records)==2 and {r['staff_code'] for r in records}=={'03','01'}
     # Existing birthday copy and configurable selections remain together.
     await page.goto(base+'/birthday.html');await page.locator('#package-select').wait_for();assert 'امکان آمدن با دوستان' in await page.locator('body').inner_text()
     assert await page.locator('input[name=service]:checked').count()==3
     # Live team edit propagates to homepage cards; profile opens in place.
     member=next(m for m in api('/api/v1/admin/team')['items'] if m['code']=='01')
     api('/api/v1/admin/team/01',{k:v for k,v in member.items() if k in ['name','role','bio','parent_code','is_active','revision']}|{'bio':'معرفی تأییدشده پنل'},'PUT')
     await page.goto(base+'/',wait_until='networkidle');await page.locator('.team-member-name').first.wait_for()
     assert 'معرفی تأییدشده پنل' in await page.locator('.team-member-card').first.inner_text()
     await page.locator('.team-member-name').first.click();assert page.url==base+'/'
     dialog=page.locator('#team-profile-dialog');assert await dialog.is_visible();assert 'نرجس، ساجده' in await dialog.inner_text()
     await dialog.get_by_role('link',name='مشاهده نمونه‌کارها').click();await page.wait_for_url('**/gallery.html?staff=01')
     await page.locator('[data-gallery-category=bride]').click();assert await page.locator('[data-gallery-category=bride]').get_attribute('aria-pressed')=='true'
     # Image creation and archival in panel affect the live gallery.
     await admin.locator('[data-section=gallery]').click();await admin.locator('#add-record').click();await admin.locator('#field-title').fill('عروس آزمون '+str(width));await admin.locator('#field-src').fill('/assets/saha-beauty-portrait.jpg');await admin.locator('#field-staff_code').select_option('01');await admin.locator('#save-record').click();await admin.locator('#record-dialog').wait_for(state='hidden')
     await page.reload();await page.locator('#gallery-grid article').first.wait_for();assert 'عروس آزمون '+str(width) in await page.locator('#gallery-grid').inner_text()
     # Expertise and working hours use the existing scheduling editor.
     schedule=await context.new_page();await schedule.goto(base+'/scheduling.html');await schedule.locator('#schedule-token').fill(token);await schedule.locator('#schedule-login button').click();await schedule.locator('#schedule-form').wait_for(state='visible')
     assert await schedule.locator('[data-expertise="02"]').count()==0
     await schedule.locator('#schedule-staff').select_option('02');await schedule.locator('[data-expertise="pedicure"]').wait_for();assert await schedule.locator('[data-expertise="02"]').is_checked()
     await schedule.locator('#schedule-staff').select_option('03');await schedule.locator('[data-service="04"]').wait_for();await schedule.locator('[data-service="04"]').fill('30');await schedule.locator('#schedule-form button[type=submit]').click();await schedule.wait_for_function("document.querySelector('#schedule-status').textContent.includes('روی سرور ذخیره')")
     assert api('/api/v1/admin/scheduling/03')['services'][0]['duration_minutes']==30
     await schedule.close()
     # Main buffet modal reads owner records, and 9932 has telephone links only.
     api('/api/v1/admin/offers',{'kind':'buffet','title':'دمنوش آزمون','description':'منوی تعریف‌شده مدیر','price_toman':None,'is_active':True},'POST')
     await page.goto(base+'/',wait_until='networkidle');assert await page.locator('a[href*="wa.me/989165109932"]').count()==0
     assert await page.locator('a[href="tel:09165109932"]').count()>0
     await page.locator('[data-saha-open-menu]').click();await page.get_by_text('منوی تعریف‌شده مدیر',exact=False).first.wait_for()
     await page.keyboard.press('Escape')
     await page.screenshot(path=f'/tmp/saha-packages-home-{width}.png')
     assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
     assert not errors,errors
     await context.close();print(f'{width}: package prices, panel edits, specialist restrictions, team dialog, gallery and buffet passed',flush=True)
    await browser.close()
  finally:process.terminate();process.wait(timeout=10)
if __name__=='__main__':asyncio.run(main())
