from concurrent.futures import ThreadPoolExecutor
import os
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from datetime import datetime,timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo
from dataclasses import replace
import pytest
from fastapi.testclient import TestClient
from backend.app.cli import upgrade_database,seed_database
from backend.app.config import Settings
from backend.app.main import create_app
from frontend.build import build
TOKEN='booking-fixture-'+('k'*40)
AUTH={'Authorization':'Bearer '+TOKEN}
@pytest.fixture
def setup(tmp_path):
 url=f'sqlite:///{tmp_path / "booking.db"}';admin=None;dbname=None
 if os.environ.get('SAHA_TEST_POSTGRES_URL'):
  admin=create_engine(os.environ['SAHA_TEST_POSTGRES_URL'],isolation_level='AUTOCOMMIT');dbname='saha_test_'+uuid4().hex
  with admin.connect() as connection:connection.execute(text('CREATE DATABASE '+dbname))
  url=make_url(os.environ['SAHA_TEST_POSTGRES_URL']).set(database=dbname).render_as_string(hide_password=False)
 upgrade_database(url);seed_database(url)
 settings=Settings(database_url=url,admin_api_token=TOKEN,booking_enabled=True,frontend_dir=build(tmp_path/'frontend'))
 day=(datetime.now(ZoneInfo('Asia/Tehran'))+timedelta(days=1)).date()
 plan={'services':[{'service_code':'hair-braid','duration_minutes':45},{'service_code':'hair-color','duration_minutes':60}],'windows':[{'weekday':day.weekday(),'start_minute':540,'end_minute':780,'step_minutes':30}]}
 with TestClient(create_app(settings)) as c:
  assert c.put('/api/v1/admin/scheduling/01',json=plan,headers=AUTH).status_code==200
  yield c,settings,day
 if admin:
  with admin.connect() as connection:connection.execute(text('DROP DATABASE '+dbname+' WITH (FORCE)'))
  admin.dispose()

def availability(c,day):return c.get('/api/v1/booking/availability',params={'staff_code':'01','services':'hair-braid,hair-color','day':str(day)})
def payload(slot):return {'customer_name':'مشتری تست','phone':'09123456789','service_codes':['hair-braid','hair-color'],'staff_code':'01','starts_at':slot['starts_at'],'request_id':str(uuid4())}

def test_real_booking_persistence_notifications_and_privacy(setup):
 c,settings,day=setup
 response=availability(c,day);assert response.status_code==200,response.text
 slots=response.json()['slots'];assert len(slots)==5 and all(s['state']=='available' for s in slots)
 body=payload(slots[0]);r=c.post('/api/v1/booking/reservations',json=body);assert r.status_code==201,r.text
 assert r.json()['status']=='confirmed' and not r.json()['payment_required']
 assert c.post('/api/v1/booking/reservations',json=body).json()['reference']==r.json()['reference']
 assert c.post('/api/v1/booking/reservations',json={**body,'request_id':str(uuid4())}).status_code==409
 assert 'مشتری تست' not in availability(c,day).text
 assert c.get('/api/v1/admin/booking-notifications').status_code==401
 notice=c.get('/api/v1/admin/booking-notifications',headers=AUTH).json()['ids'];assert notice==[r.json()['reference']]
 record=c.get('/api/v1/admin/appointments',headers=AUTH).json()['items'][0];assert set(record['service_codes'])=={'hair-braid','hair-color'}
 with TestClient(create_app(settings)) as restarted:
  assert availability(restarted,day).json()['slots'][0]['state']=='occupied'
  assert restarted.post('/api/v1/admin/booking-notifications/seen',json=notice,headers=AUTH).status_code==200
  assert restarted.get('/api/v1/admin/booking-notifications',headers=AUTH).json()['ids']==[]

def test_two_clients_cannot_double_book(setup):
 c,settings,day=setup
 slot=availability(c,day).json()['slots'][0]
 def reserve(_):
  with TestClient(create_app(settings)) as other:return other.post('/api/v1/booking/reservations',json=payload(slot)).status_code
 with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(reserve,range(2)))==[201,409]

def test_availability_requires_real_configuration_and_activation(setup):
 c,settings,day=setup
 assert c.get('/api/v1/booking/availability',params={'staff_code':'02','services':'hair-braid','day':str(day)}).status_code==409
 assert c.get('/api/v1/booking/availability',params={'staff_code':'01','services':'06','day':str(day)}).status_code==422
 assert c.put('/api/v1/admin/scheduling/01',json={'services':[],'windows':[]}).status_code==401
 with TestClient(create_app(replace(settings,booking_enabled=False))) as off:assert availability(off,day).status_code==503
 assert c.get('/api/v1/booking/catalog').json()['payment_enabled'] is False

def test_public_booking_rate_limit(setup):
 c,settings,day=setup
 body=payload(availability(c,day).json()['slots'][0])
 results=[c.post('/api/v1/booking/reservations',json=body).status_code for _ in range(13)]
 assert results[:12]==[201]*12 and results[-1]==429

def batch_body(c,day):
 plan={'services':[{'service_code':'hair-color','duration_minutes':60}],'windows':[{'weekday':day.weekday(),'start_minute':540,'end_minute':780,'step_minutes':30}]}
 assert c.put('/api/v1/admin/scheduling/02',json=plan,headers=AUTH).status_code==200
 def slot(staff,service,index):return c.get('/api/v1/booking/availability',params={'staff_code':staff,'services':service,'day':str(day)}).json()['slots'][index]
 return {'request_id':str(uuid4()),'customer_name':'مشتری چندخدمت','phone':'09123456789','items':[{'service_codes':['hair-braid'],'staff_code':'01','starts_at':slot('01','hair-braid',0)['starts_at']},{'service_codes':['hair-color'],'staff_code':'02','starts_at':slot('02','hair-color',2)['starts_at']}]}

def test_batch_specialists_atomic_persistent_idempotent(setup):
 c,settings,day=setup;body=batch_body(c,day)
 r=c.post('/api/v1/booking/reservations/batch',json=body);assert r.status_code==201,r.text
 refs=r.json()['references'];assert len(set(refs))==2 and r.json()['status']=='confirmed'
 assert c.post('/api/v1/booking/reservations/batch',json=body).json()['references']==refs
 records=c.get('/api/v1/admin/appointments',headers=AUTH).json()['items'];assert len(records)==2 and {r['staff_code'] for r in records}=={'01','02'}
 assert set(c.get('/api/v1/admin/booking-notifications',headers=AUTH).json()['ids'])==set(refs)
 with TestClient(create_app(settings)) as restarted:assert set(restarted.post('/api/v1/booking/reservations/batch',json=body).json()['references'])==set(refs)
 catalog=c.get('/api/v1/booking/catalog').json();assert 'hair-color' in next(m for m in catalog['team'] if m['code']=='02')['service_codes']

def test_batch_rolls_back_first_if_second_is_busy(setup):
 c,_,day=setup;body=batch_body(c,day)
 busy={**body['items'][1],'request_id':str(uuid4()),'customer_name':'مشتری دیگر','phone':'09123456780'}
 assert c.post('/api/v1/booking/reservations',json=busy).status_code==201
 r=c.post('/api/v1/booking/reservations/batch',json=body);assert r.status_code==409,r.text
 records=c.get('/api/v1/admin/appointments',headers=AUTH).json()['items'];assert len(records)==1 and records[0]['customer_name']=='مشتری دیگر'
 assert c.get('/api/v1/booking/availability',params={'staff_code':'01','services':'hair-braid','day':str(day)}).json()['slots'][0]['state']=='available'

def test_batch_rejects_customer_overlap_and_cross_origin(setup):
 c,_,day=setup;body=batch_body(c,day);body['items'][1]['starts_at']=body['items'][0]['starts_at']
 assert c.post('/api/v1/booking/reservations/batch',json=body).status_code==409
 assert c.get('/api/v1/admin/appointments',headers=AUTH).json()['total']==0
 assert c.post('/api/v1/booking/reservations/batch',json=body,headers={'Origin':'https://other.example'}).status_code==403
 assert c.post('/api/v1/booking/reservations/batch',json={**body,'items':[body['items'][0],body['items'][0]]}).status_code==422

def test_review_is_private_and_visible_to_authenticated_manager(setup):
 c,_,_=setup;body={'request_id':str(uuid4()),'customer_name':'مشتری نظر','phone':'۰۹۱۲۳۴۵۶۷۸۹','message':'برخورد تیم خیلی خوب بود.'}
 r=c.post('/api/v1/reviews',json=body);assert r.status_code==201 and r.json()['published'] is False
 assert c.post('/api/v1/reviews',json=body).json()['reference']==r.json()['reference']
 assert c.get('/api/v1/admin/consultations').status_code==401
 rows=c.get('/api/v1/admin/consultations',headers=AUTH).json()['items'];assert len(rows)==1 and rows[0]['topic']=='نظر مشتری' and rows[0]['message']==body['message']
 assert c.post('/api/v1/reviews',json={**body,'message':'نظر تغییر یافته'}).status_code==409
 assert c.post('/api/v1/reviews',json={**body,'request_id':str(uuid4())},headers={'Origin':'https://other.example'}).status_code==403

def test_batch_two_clients_cannot_double_book(setup):
 c,settings,day=setup;body=batch_body(c,day)
 def reserve(_):
  with TestClient(create_app(settings)) as other:return other.post('/api/v1/booking/reservations/batch',json={**body,'request_id':str(uuid4())}).status_code
 with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(reserve,range(2)))==[201,409]
 assert c.get('/api/v1/admin/appointments',headers=AUTH).json()['total']==2
