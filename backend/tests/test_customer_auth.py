from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4
import os
import pytest
from pydantic import SecretStr
from fastapi.testclient import TestClient
from sqlalchemy import select, func, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from backend.app.config import Settings
from backend.app.cli import upgrade_database,seed_database
from backend.app.main import create_app
from backend.app.models import OtpChallenge,Customer,CustomerSession,AuthLimit
from backend.app.sms_provider import Melipayamak,SmsUnavailable
from frontend.build import build

KEY='offline-provider-fixture-00000000'
SECRET='offline-hmac-secret-'+('s'*40)
CODE='3741437414'
PHONE='09123456789'
ADMIN='offline-admin-'+('a'*40)

@pytest.fixture
def auth_app(tmp_path):
    admin=None;dbname=None
    url=f'sqlite:///{tmp_path / "auth.db"}'
    if os.environ.get('SAHA_TEST_POSTGRES_URL'):
        admin=create_engine(os.environ['SAHA_TEST_POSTGRES_URL'],isolation_level='AUTOCOMMIT');dbname='saha_test_'+uuid4().hex
        with admin.connect() as connection:connection.execute(text('CREATE DATABASE '+dbname))
        url=make_url(os.environ['SAHA_TEST_POSTGRES_URL']).set(database=dbname).render_as_string(hide_password=False)
    upgrade_database(url);seed_database(url)
    settings=Settings(database_url=url,admin_api_token=ADMIN,otp_enabled=True,sms_live_enabled=True,
        otp_contract_confirmed=True,otp_secret=SecretStr(SECRET),melipayamak_api_key=SecretStr(KEY),
        sms_notifications_enabled=True,booking_enabled=True,frontend_dir=build(tmp_path/'frontend'))
    app=create_app(settings);calls=[]
    def transport(url,body):
        assert url=='https://console.melipayamak.com/api/send/otp/'+KEY
        calls.append(body);return {'code':CODE,'status':''}
    app.state.sms_provider=Melipayamak(settings,transport=transport)
    with TestClient(app,base_url='https://testserver') as client:
        yield client,app,settings,calls
    if admin:
        with admin.connect() as connection:connection.execute(text('DROP DATABASE '+dbname+' WITH (FORCE)'))
        admin.dispose()

def challenge(client,phone=PHONE):
    r=client.post('/api/v1/auth/otp/request',json={'phone':phone})
    assert r.status_code==202,r.text
    return r.json()['challenge_id']

def login(client,phone=PHONE):
    identity=challenge(client,phone)
    r=client.post('/api/v1/auth/otp/verify',json={'challenge_id':identity,'code':CODE})
    assert r.status_code==200,r.text
    return identity,r

def test_secure_login_one_use_cookie_consent_and_logout(auth_app,caplog):
    c,app,settings,calls=auth_app
    identity,r=login(c,'+98 912-345-6789')
    assert calls==[{'to':PHONE}]
    assert CODE not in r.text and KEY not in r.text and SECRET not in r.text
    cookie=r.headers['set-cookie'].lower()
    assert all(flag in cookie for flag in ['__host-saha_session=','secure','httponly','samesite=lax','path=/'])
    assert c.get('/api/v1/auth/me').json()=={'phone':PHONE,'verified':True,'sms_consent':False}
    assert c.post('/api/v1/auth/preferences',json={'sms_consent':True}).json()=={'sms_consent':True}
    with Session(app.state.engine) as db:
        record=db.get(OtpChallenge,identity)
        assert record.status=='consumed' and record.code_digest is None
        sessions=list(db.scalars(select(CustomerSession)))
        assert len(sessions)==1 and sessions[0].digest not in cookie
        assert db.get(Customer,PHONE).sms_consent is True
    assert c.post('/api/v1/auth/otp/verify',json={'challenge_id':identity,'code':CODE}).status_code==400
    # A customer cookie never authenticates the salon administrator.
    assert c.get('/api/v1/admin/appointments').status_code==401
    assert c.post('/api/v1/auth/logout',json={}).status_code==204
    assert c.get('/api/v1/auth/me').status_code==401
    assert CODE not in caplog.text and KEY not in caplog.text

def test_code_is_only_hmac_in_storage_and_not_sent_to_browser(auth_app):
    c,app,_,_=auth_app
    r=c.post('/api/v1/auth/otp/request',json={'phone':PHONE})
    assert r.status_code==202 and r.json()['expires_in']<=120
    assert CODE not in r.text
    with Session(app.state.engine) as db:
        row=db.get(OtpChallenge,r.json()['challenge_id'])
        assert len(row.code_digest)==64 and CODE not in row.code_digest

def test_expired_code_cannot_log_in(auth_app,monkeypatch):
    c,_,_,_=auth_app;identity=challenge(c)
    import time
    future=int(time.time())+121
    monkeypatch.setattr('backend.app.customer_auth.time.time',lambda:future)
    assert c.post('/api/v1/auth/otp/verify',json={'challenge_id':identity,'code':CODE}).status_code==400

def test_five_wrong_codes_lock_the_challenge(auth_app):
    c,app,_,_=auth_app;identity=challenge(c)
    for _ in range(5):
        assert c.post('/api/v1/auth/otp/verify',json={'challenge_id':identity,'code':'0000000000'}).status_code==400
    assert c.post('/api/v1/auth/otp/verify',json={'challenge_id':identity,'code':CODE}).status_code==400
    with Session(app.state.engine) as db:
        assert db.get(OtpChallenge,identity).status=='locked'
        assert db.scalar(select(func.count()).select_from(CustomerSession))==0

def test_persistent_cooldown_survives_process_restart(auth_app):
    c,app,settings,calls=auth_app;challenge(c)
    other=create_app(settings);other.state.sms_provider=app.state.sms_provider
    with TestClient(other,base_url='https://testserver') as restart:
        assert restart.post('/api/v1/auth/otp/request',json={'phone':PHONE}).status_code==429
    assert len(calls)==1

def test_resend_invalidates_old_code(auth_app,monkeypatch):
    c,_,_,_=auth_app;old=challenge(c)
    import time
    future=int(time.time())+61
    monkeypatch.setattr('backend.app.customer_auth.time.time',lambda:future)
    new=challenge(c)
    assert c.post('/api/v1/auth/otp/verify',json={'challenge_id':old,'code':CODE}).status_code==400
    assert c.post('/api/v1/auth/otp/verify',json={'challenge_id':new,'code':CODE}).status_code==200

def test_ip_limits_ignore_spoofed_forwarded_header(auth_app):
    c,_,_,calls=auth_app
    for i in range(10):
        assert c.post('/api/v1/auth/otp/request',json={'phone':f'0912000{i:04d}'}).status_code==202
    assert c.post('/api/v1/auth/otp/request',json={'phone':'09129999999'},headers={'X-Forwarded-For':'8.8.8.8'}).status_code==429
    assert len(calls)==10

def test_concurrent_verification_consumes_only_once(auth_app):
    c,app,_,_=auth_app;identity=challenge(c)
    def verify(_):
        return c.post('/api/v1/auth/otp/verify',json={'challenge_id':identity,'code':CODE}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(verify,range(2)))
    assert sorted(statuses)==[200,400]
    with Session(app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(CustomerSession))==1

def test_disabled_settings_never_call_provider(auth_app):
    _,_,settings,_=auth_app
    disabled=replace(settings,otp_enabled=False,sms_live_enabled=False)
    app=create_app(disabled)
    app.state.sms_provider=Melipayamak(disabled,transport=lambda *_:pytest.fail('network attempt'))
    with TestClient(app,base_url='https://testserver') as c:
        assert c.get('/api/v1/auth/capabilities').json()=={'enabled':False}
        assert c.post('/api/v1/auth/otp/request',json={'phone':PHONE}).status_code==503
        assert c.get('/login.html').status_code==200
    with pytest.raises(SmsUnavailable):app.state.sms_provider.send_otp(PHONE)

def test_provider_timeout_is_not_retried_and_never_exposes_url(auth_app,caplog):
    c,app,settings,_=auth_app;calls=[]
    def failure(url,body):
        calls.append(1);raise TimeoutError(url+' '+CODE)
    app.state.sms_provider=Melipayamak(settings,transport=failure)
    r=c.post('/api/v1/auth/otp/request',json={'phone':PHONE})
    assert r.status_code==503 and calls==[1]
    assert KEY not in r.text+caplog.text and CODE not in r.text+caplog.text
    with Session(app.state.engine) as db:
        assert db.scalar(select(OtpChallenge)).status=='failed'

@pytest.mark.parametrize('payload',[{'code':123456},{'code':CODE,'status':'error'},{'code':'bad'},['not-a-dict']])
def test_provider_error_responses_are_fail_closed(auth_app,payload):
    c,app,settings,_=auth_app
    app.state.sms_provider=Melipayamak(settings,transport=lambda *_:payload)
    assert c.post('/api/v1/auth/otp/request',json={'phone':PHONE}).status_code==503

def test_cross_site_and_invalid_phone_cannot_send(auth_app):
    c,_,_,calls=auth_app
    assert c.post('/api/v1/auth/otp/request',json={'phone':PHONE},headers={'Origin':'https://elsewhere.invalid'}).status_code==403
    assert c.post('/api/v1/auth/otp/request',json={'phone':'invalid'}).status_code==422
    assert calls==[]

def test_rejected_otp_input_is_not_echoed_in_validation_error(auth_app):
    c,_,_,_=auth_app
    submitted='private-invalid-code'
    r=c.post('/api/v1/auth/otp/verify',json={'challenge_id':str(uuid4()),'code':submitted})
    assert r.status_code==422 and submitted not in r.text

def test_logout_revokes_existing_session_even_when_new_logins_disabled(auth_app):
    c,_,settings,_=auth_app;login(c)
    disabled=create_app(replace(settings,otp_enabled=False))
    with TestClient(disabled,base_url='https://testserver') as other:
        other.cookies.update(c.cookies)
        assert other.post('/api/v1/auth/logout',json={}).status_code==204
    assert c.get('/api/v1/auth/me').status_code==401
