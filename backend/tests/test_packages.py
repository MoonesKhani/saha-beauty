"""Package prices, owner updates, specialist isolation and transactional reservations."""
from datetime import datetime,timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.app.cli import upgrade_database,seed_database
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import Appointment,BookingPrice,Package
from frontend.build import build

TOKEN='package-test-'+'k'*40
AUTH={'Authorization':'Bearer '+TOKEN}
@pytest.fixture
def client(tmp_path):
    url=f'sqlite:///{tmp_path / "packages.db"}'
    upgrade_database(url);seed_database(url)
    settings=Settings(database_url=url,admin_api_token=TOKEN,booking_enabled=True,frontend_dir=build(tmp_path/'frontend'))
    with TestClient(create_app(settings)) as c:
        yield c,settings

def quote(c,code,codes):
    return c.post('/api/v1/packages/quote',json={'package_code':code,'service_codes':codes})
def tariff(c,code,price):
    old=c.get('/api/v1/services/'+code).json()
    r=c.patch('/api/v1/admin/services/'+code,headers=AUTH,json={'revision':old['revision'],'price_toman':price})
    assert r.status_code==200,r.text

def test_exact_initial_packages_and_unknown_prices(client):
    c,_=client
    packages={p['code']:p for p in c.get('/api/v1/packages').json()['items']}
    assert [packages['bride-'+t]['price_toman'] for t in ['normal','vip','cip']]==[15000000,25000000,45000000]
    assert [packages['engagement-'+t]['price_toman'] for t in ['normal','vip','cip']]==[8000000,15000000,23000000]
    assert [packages['companion-'+t]['price_toman'] for t in ['normal','vip','cip']]==[3000000,3500000,4000000]
    cip=packages['bride-cip']['service_codes']
    assert set(cip)=={'consultation','04','lens-lashes','hair-updo','11','decollete-facial','hand-rejuvenation','02','pedicure','toe-gel','hair-color'}
    assert quote(c,'bride-cip',cip).json()['total_toman']==45000000
    assert quote(c,'companion-normal',[]).json()['total_toman'] is None
    assert quote(c,'birthday',packages['birthday']['service_codes']).json()['total_toman'] is None
    assert all(s['price_toman'] is None for s in c.get('/api/v1/catalog').json()['services'])

def test_added_removed_tariffs_are_authoritative(client):
    c,_=client;codes=['consultation','04','hair-updo','11']
    changed=['consultation','04','hair-updo','02']
    assert quote(c,'bride-normal',changed).json()['missing_prices']==['02','11']
    tariff(c,'02',700000);tariff(c,'11',200000)
    assert quote(c,'bride-normal',changed).json()['total_toman']==15500000
    # Zero is a configured price; absence is not zero.
    tariff(c,'11',0)
    assert quote(c,'bride-normal',changed).json()['total_toman']==15700000
    assert quote(c,'bride-normal',codes+['04']).status_code==422
    assert quote(c,'bride-normal',codes+['fake']).status_code==422
    assert c.post('/api/v1/packages/quote',json={'package_code':'bride-normal','service_codes':codes,'total_toman':1}).status_code==422

def test_birthday_and_companion_can_be_configured_without_inventing_prices(client):
    c,settings=client
    for code,price in [('hair-updo',500000),('04',800000),('02',700000)]:tariff(c,code,price)
    assert quote(c,'birthday',['hair-updo','04','02']).json()['total_toman']==2000000
    p=next(p for p in c.get('/api/v1/admin/packages',headers=AUTH).json()['items'] if p['code']=='companion-vip')
    body={k:p[k] for k in ['name','category','tier','description','price_toman','service_codes','is_active','revision']}
    body['service_codes']=['04','hair-updo']
    assert c.put('/api/v1/admin/packages/companion-vip',headers=AUTH,json=body).status_code==200
    assert c.put('/api/v1/admin/packages/companion-vip',headers=AUTH,json=body).status_code==409
    assert quote(c,'companion-vip',body['service_codes']).json()['total_toman']==3500000
    seed_database(settings.database_url)
    assert quote(c,'companion-vip',body['service_codes']).json()['configured']

def test_gallery_team_and_public_updates(client):
    c,_=client
    body={'title':'عروس تأییدشده','src':'/assets/saha-beauty-portrait.jpg','category':'bride','staff_code':'01','is_active':True}
    assert c.post('/api/v1/admin/gallery',json=body).status_code==401
    for src in ['javascript:alert(1)','data:image/png;base64,abc','/assets/../.env','http://example.com/p.jpg']:
        assert c.post('/api/v1/admin/gallery',headers=AUTH,json={**body,'src':src}).status_code==422
    response=c.post('/api/v1/admin/gallery',headers=AUTH,json=body)
    assert response.status_code==201,response.text
    row=response.json()
    assert c.get('/api/v1/gallery').json()['items'][0]['title']==body['title']
    assert c.get('/api/v1/gallery').headers['cache-control']=='no-store'
    assert c.delete('/api/v1/admin/gallery/'+row['id']+'?revision=1',headers=AUTH).status_code==200
    assert c.get('/api/v1/gallery').json()['items']==[]
    team=c.get('/api/v1/catalog').json()['team']
    assert {m['name'] for m in team if m['parent_code']=='01'}=={'نرجس','ساجده'}
    assert c.post('/api/v1/admin/team',headers=AUTH,json={'name':'دستیار تست','role':'دستیار','bio':'معرفی','parent_code':'unknown'}).status_code==422


def test_nail_specialties_enforced_on_server_and_catalog(client):
    c,settings=client
    catalog=c.get('/api/v1/booking/catalog').json()
    nails={'02','07','manicure','pedicure','toe-gel','nail-gel'}
    assert all(not nails.intersection(m['service_codes']) or m['code']=='02' for m in catalog['team'])
    assert c.put('/api/v1/admin/expertise/01',headers=AUTH,json={'service_codes':['pedicure']}).status_code==422
    assert c.put('/api/v1/admin/scheduling/01',headers=AUTH,json={'services':[{'service_code':'02','duration_minutes':30}],'windows':[]}).status_code==422
    assert c.put('/api/v1/admin/expertise/02',headers=AUTH,json={'service_codes':['manicure']}).status_code==200
    seed_database(settings.database_url)
    assert c.get('/api/v1/admin/expertise/02',headers=AUTH).json()['service_codes']==['manicure']


def test_multispecialist_package_booking_price_snapshot_and_atomic_overlap(client):
    c,settings=client
    day=(datetime.now(ZoneInfo('Asia/Tehran'))+timedelta(days=1)).date()
    for staff,code in [('03','04'),('01','hair-updo')]:
        r=c.put('/api/v1/admin/scheduling/'+staff,headers=AUTH,json={'services':[{'service_code':code,'duration_minutes':30}],'windows':[{'weekday':day.weekday(),'start_minute':540,'end_minute':720,'step_minutes':30}]})
        assert r.status_code==200,r.text
    # Owner defines the companion services; these values are fixtures only.
    p=next(p for p in c.get('/api/v1/admin/packages',headers=AUTH).json()['items'] if p['code']=='companion-normal')
    body={k:p[k] for k in ['name','category','tier','description','price_toman','service_codes','is_active','revision']};body['service_codes']=['04','hair-updo']
    assert c.put('/api/v1/admin/packages/companion-normal',headers=AUTH,json=body).status_code==200
    def slot(staff,code,index):return c.get('/api/v1/booking/availability',params={'staff_code':staff,'services':code,'day':str(day)}).json()['slots'][index]['starts_at']
    items=[{'staff_code':'03','service_codes':['04'],'starts_at':slot('03','04',0)},{'staff_code':'01','service_codes':['hair-updo'],'starts_at':slot('01','hair-updo',0)}]
    payload={'request_id':str(uuid4()),'customer_name':'آزمون','phone':'09123456789','package_code':'companion-normal','items':items}
    assert c.post('/api/v1/booking/reservations/batch',json=payload).status_code==409
    with Session(c.app.state.engine) as db:assert list(db.scalars(select(Appointment)))==[] and list(db.scalars(select(BookingPrice)))==[]
    items[1]['starts_at']=slot('01','hair-updo',1)
    r=c.post('/api/v1/booking/reservations/batch',json=payload)
    assert r.status_code==201,r.text
    assert r.json()['quote']['total_toman']==3000000
    # Retrying after an owner price change returns the original captured price.
    with Session(c.app.state.engine) as db:
        db.get(Package,'companion-normal').price_toman=4000000;db.commit()
    assert c.post('/api/v1/booking/reservations/batch',json=payload).json()['quote']['total_toman']==3000000
    assert c.post('/api/v1/booking/reservations/batch',json={**payload,'package_code':'bride-normal'}).status_code==409
    assert c.post('/api/v1/booking/reservations/batch',json={**payload,'request_id':str(uuid4())}).status_code==409
    with Session(c.app.state.engine) as db:assert len(list(db.scalars(select(Appointment))))==2


def test_stale_quote_cannot_silently_change_price(client):
    c,_=client
    codes=['consultation','04','hair-updo','11']
    old=quote(c,'bride-normal',codes).json()['quote_version']
    p=next(p for p in c.get('/api/v1/admin/packages',headers=AUTH).json()['items'] if p['code']=='bride-normal')
    body={k:p[k] for k in ['name','category','tier','description','price_toman','service_codes','is_active','revision']};body['price_toman']=16000000
    assert c.put('/api/v1/admin/packages/bride-normal',headers=AUTH,json=body).status_code==200
    day=(datetime.now(ZoneInfo('Asia/Tehran'))+timedelta(days=1)).date()
    r=c.post('/api/v1/booking/reservations',json={'request_id':str(uuid4()),'customer_name':'آزمون','phone':'09123456789','package_code':'bride-normal','quote_version':old,'service_codes':codes,'staff_code':'01','starts_at':str(day)+'T09:00:00+03:30'})
    assert r.status_code==409 and 'تغییر کرده' in r.json()['detail']
    with Session(c.app.state.engine) as db:assert list(db.scalars(select(Appointment)))==[]
