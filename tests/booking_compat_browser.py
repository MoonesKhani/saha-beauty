"""Old backend compatibility: one service works, unsupported batch cannot submit."""
import asyncio,os
from playwright.async_api import async_playwright
BASE=os.environ.get('SAHA_TEST_URL','http://127.0.0.1:8039').rstrip('/')
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'],proxy={'server':os.environ['HTTPS_PROXY'],'bypass':'127.0.0.1,localhost'})
  page=await browser.new_page(viewport={'width':390,'height':844});writes=[]
  async def api(route):
   path=route.request.url.split('/api/v1/',1)[1]
   if path=='booking/catalog':await route.fulfill(json={'enabled':True,'services':[{'code':'02','name':'ناخن','category':'سایر خدمات'},{'code':'hair-braid','name':'بافت','category':'مو'}],'team':[{'code':'01','name':'همکار آزمون','role':'متخصص'}]})
   elif path.startswith('booking/availability'):await route.fulfill(json={'slots':[{'starts_at':'2099-01-01T09:00:00+03:30','ends_at':'2099-01-01T09:30:00+03:30','state':'available'}]})
   elif path=='booking/reservations':writes.append(route.request.post_data_json);await route.fulfill(status=201,json={'status':'confirmed','reference':'test-reference','payment_required':False})
   else:await route.fulfill(status=404,body='not found')
  await page.route('**/api/v1/**',api)
  await page.goto(BASE+'/booking.html?service=02');await page.wait_for_function("document.querySelector('#reservation-status').textContent.includes('دلخواهت')");await page.locator('input[name=staff-02]').check();await page.locator('#availability button').first.click();await page.locator('#reservation-name').fill('آزمون');await page.locator('#reservation-phone').fill('09123456789');await page.locator('#reserve-confirm').click();await page.wait_for_function("document.querySelector('#reservation-status').textContent.includes('test-reference')");assert writes[0]['service_codes']==['02']
  await page.goto(BASE+'/booking.html');await page.wait_for_function("document.querySelector('#reservation-status').textContent.includes('دلخواهت')");await page.get_by_label('بافت',exact=True).check();await page.get_by_label('ناخن',exact=True).check();assert await page.locator('#reserve-confirm').is_disabled();assert 'فعلاً در دسترس نیست' in await page.locator('#reservation-status').inner_text();assert len(writes)==1
  await page.goto(BASE+'/booking.html?service=not-real');await page.wait_for_function("document.querySelector('#reservation-status').textContent.includes('قابل انتخاب نیست')");assert await page.locator('#reserve-confirm').is_disabled();assert await page.locator('.reservation-choice').count()==0
  print('Legacy single-service endpoint, unsupported batch guard, unknown service passed',flush=True);await browser.close()
asyncio.run(main())
