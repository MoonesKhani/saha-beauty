"""Login UI only; every HTTP response is mocked. No SMS or external requests."""
import asyncio,json,os
from pathlib import Path
from uuid import uuid4
from playwright.async_api import async_playwright,expect
ROOT=Path(__file__).resolve().parents[1]

async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path=os.environ.get('SAHA_CHROMIUM','/usr/bin/chromium'),args=['--no-sandbox'])
  for width in [390,1440]:
   context=await browser.new_context(viewport={'width':width,'height':900})
   state={'enabled':False,'logged':False,'consent':False,'sends':0,'posts':[],'requires_login':False}
   identity=str(uuid4())
   async def route_handler(route):
    from urllib.parse import urlsplit
    request=route.request;path=urlsplit(request.url).path
    assert urlsplit(request.url).netloc=='saha-test.invalid','Unexpected external request'
    code=200;data={}
    if path.startswith('/api/v1/auth/'):
     action=path.removeprefix('/api/v1/auth/')
     if request.method=='POST':state['posts'].append(action)
     if action=='capabilities':data={'enabled':state['enabled']}
     elif action=='me':
      code=200 if state['logged'] else 401
      data={'phone':'09123456789','sms_consent':state['consent']}
     elif action=='otp/request':
      assert request.post_data_json=={'phone':'09123456789'}
      state['sends']+=1;code=202;data={'challenge_id':identity,'expires_in':120,'retry_after':60}
     elif action=='otp/verify':
      assert request.post_data_json=={'challenge_id':identity,'code':'123456'}
      state['logged']=True;data={'authenticated':True,'phone':'09123456789'}
     elif action=='preferences':state['consent']=request.post_data_json['sms_consent'];data={'sms_consent':state['consent']}
     elif action=='logout':state['logged']=False;code=204
     else:raise AssertionError(action)
     return await route.fulfill(status=code,body='' if code==204 else json.dumps(data),content_type='application/json')
    if path=='/api/v1/booking/catalog':return await route.fulfill(json={'enabled':True,'requires_login':state['requires_login'],'batch_enabled':True,'services':[{'code':'hair-braid','name':'خدمت آزمایشی','category':'مو','price_toman':0}],'team':[]})
    if path=='/api/v1/packages':return await route.fulfill(json={'items':[]})
    if path in ['/login.html','/booking.html','/bridal.html','/birthday.html']:return await route.fulfill(path=ROOT/path.lstrip('/'),content_type='text/html')
    if path.startswith('/assets/'):
     file=(ROOT/path.lstrip('/')).resolve()
     assert file.is_relative_to(ROOT/'assets')
     return await route.fulfill(path=file)
    raise AssertionError(path)
   await context.route('**/*',route_handler)
   page=await context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   await page.goto('https://saha-test.invalid/login.html')
   await expect(page.locator('#auth-status')).to_contain_text('هنوز فعال نشده')
   assert state['sends']==0 and state['posts']==[]
   state['enabled']=True;await page.reload()
   await expect(page.locator('#phone-form')).to_be_visible()
   await page.locator('#auth-phone').fill('09123456789');await page.locator('#send-code').click()
   await expect(page.locator('#code-form')).to_be_visible()
   await expect(page.locator('#send-code')).to_be_disabled()
   await page.locator('#auth-code').fill('۱۲۳۴۵۶');await page.locator('#code-form button').click()
   await expect(page.locator('#customer-account')).to_be_visible()
   assert await page.locator('#auth-code').input_value()==''
   assert await page.evaluate('localStorage.length+sessionStorage.length')==0
   await page.locator('#sms-consent').check();await page.locator('#save-consent').click()
   await expect(page.locator('#auth-status')).to_contain_text('ذخیره شد')
   assert state['consent'] is True and state['sends']==1
   await page.locator('#customer-logout').click()
   await expect(page.locator('#phone-form')).to_be_visible()
   assert state['sends']==1 and not errors,errors
   state['requires_login']=True
   target='/booking.html?service=hair-braid&origin=login-test'
   await page.goto('https://saha-test.invalid'+target)
   await page.wait_for_url('**/login.html?return_to=*')
   await expect(page.locator('#phone-form')).to_be_visible()
   assert state['sends']==1 # Navigation alone must never request a code.
   await page.locator('#auth-phone').fill('09123456789');await page.locator('#send-code').click()
   await expect(page.locator('#code-form')).to_be_visible()
   await page.locator('#auth-code').fill('123456');await page.locator('#code-form button').click()
   await page.wait_for_url('https://saha-test.invalid'+target)
   await expect(page.locator('#reservation-phone')).to_have_value('09123456789')
   assert await page.locator('#reservation-phone').get_attribute('readonly') is not None
   # Even with a valid session, an external return URL is not followed.
   await page.goto('https://saha-test.invalid/login.html?return_to=https%3A%2F%2Fother.invalid%2Fbooking.html')
   await expect(page.locator('#customer-account')).to_be_visible()
   assert page.url.startswith('https://saha-test.invalid/login.html')
   assert state['sends']==2 and not errors,errors

   assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
   print(f'{width}px: OTP login, booking redirect/return, verified phone, safe redirect, consent and logout passed (all requests mocked)')
   await context.close()
  await browser.close()
if __name__=='__main__':asyncio.run(main())
