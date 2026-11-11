import pytest
from fastapi.testclient import TestClient
from backend.app.cli import upgrade_database,seed_database
from backend.app.config import Settings
from backend.app.main import create_app
from frontend.build import build

TOKEN='fixture-only-'+('k'*40)
@pytest.fixture
def client(tmp_path):
    url=f'sqlite:///{tmp_path / "admin.db"}'
    upgrade_database(url);seed_database(url)
    with TestClient(create_app(Settings(database_url=url,preview_enabled=True,admin_api_token=TOKEN,frontend_dir=build(tmp_path/'frontend')))) as c:
        yield c

H={'Authorization':'Bearer '+TOKEN}
def get(c,entity):return c.get('/api/v1/admin/'+entity,headers=H).json()['items']
def post(c,entity,data):return c.post('/api/v1/admin/'+entity,json=data,headers=H)
def put(c,entity,row,data):return c.put('/api/v1/admin/'+entity+'/'+(row.get('code') or row['id']),json={**data,'revision':row['revision']},headers=H)

@pytest.mark.parametrize('path',['overview','services','team','appointments','consultations','offers'])
def test_every_management_resource_requires_auth(client,path):
    assert client.get('/api/v1/admin/'+path).status_code==401
    assert client.get('/api/v1/admin/'+path,headers={'Authorization':'Bearer wrong'}).status_code==401


def test_crud_prices_archive_and_public_catalog(client):
    data={'name':'خدمت آزمایشی','description':'فقط آزمون','price_toman':120000,'is_active':True}
    created=post(client,'services',data);assert created.status_code==201
    row=created.json();code=row['code']
    assert any(x['code']==code for x in client.get('/api/v1/catalog').json()['services'])
    result=put(client,'services',row,{**data,'price_toman':240000});assert result.status_code==200
    assert put(client,'services',row,data).status_code==409
    row=result.json();assert row['price_toman']==240000
    cleared=client.patch('/api/v1/admin/services/'+code,json={'revision':2,'price_toman':None},headers=H);assert cleared.status_code==200 and cleared.json()['price_toman'] is None
    assert client.delete('/api/v1/admin/services/'+code+'?revision=3',headers=H).status_code==200
    assert not any(x['code']==code for x in client.get('/api/v1/catalog').json()['services'])
    assert client.post('/api/v1/admin/services',json=data).status_code==401
    assert post(client,'services',{**data,'price_toman':-1}).status_code==422


def test_staff_consultations_and_dashboard(client):
    staff={'name':'همکار آزمایشی','role':'ناخن','bio':'نمونه آزمون','is_active':True}
    response=post(client,'team',staff);assert response.status_code==201
    row=response.json();assert put(client,'team',row,{**staff,'bio':'معرفی تازه'}).status_code==200
    consultation={'customer_name':'متقاضی آزمایشی','phone':'۰۹۱۲۳۴۵۶۷۸۹','topic':'مو','message':None,'status':'new'}
    result=post(client,'consultations',consultation);assert result.status_code==201
    assert result.json()['phone']=='09123456789'
    assert client.get('/api/v1/admin/overview',headers=H).json()['consultations']==1
    assert put(client,'consultations',result.json(),{**consultation,'status':'contacted'}).status_code==200
    assert client.get('/api/v1/admin/overview',headers=H).json()['consultations']==0
    assert client.get('/api/v1/consultations').status_code==404


def test_appointment_times_conflicts_and_private_records(client):
    data={'customer_name':'مراجعه‌کننده آزمایشی','phone':'09123456789','service_code':'01','staff_code':'01','starts_at':'2026-11-11T10:00:00+03:30','ends_at':'2026-11-11T11:00:00+03:30','status':'confirmed'}
    first=post(client,'appointments',data);assert first.status_code==201,first.text
    assert post(client,'appointments',data).status_code==409
    other={**data,'staff_code':'02'};assert post(client,'appointments',other).status_code==201
    bad={**data,'ends_at':'2026-11-11T09:00:00+03:30'};assert post(client,'appointments',bad).status_code==422
    assert post(client,'appointments',{**data,'starts_at':'2026-11-11T10:00:00'}).status_code==422
    assert post(client,'appointments',{**data,'staff_code':'missing'}).status_code==422
    assert put(client,'appointments',first.json(),{**data,'status':'cancelled'}).status_code==200
    assert post(client,'appointments',data).status_code==201
    assert 'مراجعه‌کننده آزمایشی' not in client.get('/api/v1/catalog').text
    assert '09123456789' not in client.get('/buffet').text


def test_content_publication_license_and_demo_isolation(client):
    assert client.get('/api/v1/leisure/buffet').json()=={'items':[]}
    data={'kind':'buffet','title':'دمنوش آزمایشی','description':'نمونه','price_toman':None,'audio_url':None,'is_active':True}
    result=post(client,'offers',data);assert result.status_code==201
    assert client.get('/api/v1/leisure/buffet').json()['items'][0]['title']=='دمنوش آزمایشی'
    row=result.json();assert client.delete('/api/v1/admin/offers/'+row['id']+'?revision=1',headers=H).status_code==200
    assert client.get('/api/v1/leisure/buffet').json()=={'items':[]}
    assert post(client,'offers',{**data,'kind':'playlist','audio_url':'https://unknown.example/music.mp3'}).status_code==422
    assert post(client,'offers',{**data,'kind':'playlist','audio_url':'/assets/saha-quiet-bloom.mp3'}).status_code==201
    for page in ['/admin','/admin/demo','/admin-demo.html','/buffet','/playlist','/products']:
        r=client.get(page);assert r.status_code==200;assert TOKEN not in r.text
    assert get(client,'appointments')==[] and get(client,'consultations')==[]
    assert client.get('/api/v1/admin/overview',headers=H).headers['cache-control']=='no-store'
    assert 'دمنوش نمونه' not in client.get('/buffet').text
    assert 'دمنوش نمونه' in client.get('/buffet?demo=1').text
    assert client.get('/api/v1/admin/services?size=201',headers=H).status_code==422
    assert client.get('/api/v1/admin/services?q=ناخن',headers=H).json()['total']>=1


def test_demo_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv('SAHA_PREVIEW', raising=False)
    settings = Settings(database_url=f'sqlite:///{tmp_path / "private.db"}')
    assert not settings.preview_enabled
    with TestClient(create_app(settings)) as locked:
        for path in ['/admin/demo', '/buffet?demo=1', '/playlist?demo=1', '/products?demo=1']:
            assert locked.get(path).status_code == 404
