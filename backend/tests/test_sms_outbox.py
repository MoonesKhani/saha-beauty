from dataclasses import replace
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import time
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from backend.app.models import Appointment,Customer,SmsJob
from backend.app.sms_outbox import dispatch_one
from test_customer_auth import auth_app,login,PHONE,ADMIN

AUTH={'Authorization':'Bearer '+ADMIN}

class Notices:
    notifications_ready=True
    def __init__(self,fail=False):self.calls=[];self.fail=fail
    def send_notice(self,*args):
        self.calls.append(args)
        if self.fail:raise TimeoutError('private-provider-diagnostic-must-not-be-stored')
        return 'offline-receipt-fixture'


def appointment(app):
    identity=str(uuid4())
    with Session(app.state.engine) as db:
        db.add(Appointment(id=identity,phone=PHONE,customer_name='Offline fixture',service_code='hair-braid',staff_code='01',starts_at=datetime.now(timezone.utc)+timedelta(days=1),ends_at=datetime.now(timezone.utc)+timedelta(days=1,hours=1),status='confirmed'))
        db.commit()
    return identity


def schedule(c,identity,due):
    return c.post('/api/v1/admin/sms/repair-reminders',json={'appointment_id':identity,'due_at':due.isoformat()},headers=AUTH)


def test_scheduling_requires_admin_consent_and_is_idempotent(auth_app):
    c,app,settings,_=auth_app;login(c);identity=appointment(app)
    due=datetime.now(timezone.utc)+timedelta(days=20)
    body={'appointment_id':identity,'due_at':due.isoformat()}
    assert c.post('/api/v1/admin/sms/repair-reminders',json=body).status_code==401
    assert schedule(c,identity,due).status_code==409
    c.post('/api/v1/auth/preferences',json={'sms_consent':True})
    assert schedule(c,identity,due).status_code==201
    assert schedule(c,identity,due).status_code==201
    provider=Notices()
    assert dispatch_one(app.state.engine,provider,settings,now=int(time.time()))=='empty'
    with Session(app.state.engine) as db:assert db.scalar(select(func.count()).select_from(SmsJob))==1
    # No guessed default repair interval: only the manager's supplied date is used.
    assert dispatch_one(app.state.engine,provider,settings,now=int(due.timestamp())+1)=='accepted'
    assert len(provider.calls)==1 and provider.calls[0][1]=='repair_reminder'
    assert dispatch_one(app.state.engine,provider,settings,now=int(due.timestamp())+1)=='empty'


def test_rescheduling_and_opt_out_cancel_unsent_jobs(auth_app):
    c,app,settings,_=auth_app;login(c);c.post('/api/v1/auth/preferences',json={'sms_consent':True})
    identity=appointment(app);due=datetime.now(timezone.utc)+timedelta(days=10)
    assert schedule(c,identity,due).status_code==201
    assert schedule(c,identity,due+timedelta(days=1)).status_code==201
    with Session(app.state.engine) as db:
        assert sorted(db.scalars(select(SmsJob.status)))==['cancelled','pending']
    c.post('/api/v1/auth/preferences',json={'sms_consent':False})
    provider=Notices()
    assert dispatch_one(app.state.engine,provider,settings,now=int(due.timestamp())+2*86400)=='cancelled'
    assert provider.calls==[]


def test_uncertain_delivery_is_not_automatically_resent(auth_app):
    c,app,settings,_=auth_app;login(c);c.post('/api/v1/auth/preferences',json={'sms_consent':True})
    identity=appointment(app);due=datetime.now(timezone.utc)+timedelta(days=2)
    schedule(c,identity,due);provider=Notices(fail=True)
    assert dispatch_one(app.state.engine,provider,settings,now=int(due.timestamp())+1)=='uncertain'
    assert dispatch_one(app.state.engine,provider,settings,now=int(due.timestamp())+2)=='empty'
    assert len(provider.calls)==1
    with Session(app.state.engine) as db:
        job=db.scalar(select(SmsJob));assert job.error_code=='delivery_unconfirmed'
        assert 'private-provider' not in str(job.error_code)


def test_default_provider_and_live_switch_never_send_notifications(auth_app):
    _,app,settings,_=auth_app
    assert dispatch_one(app.state.engine,app.state.sms_provider,settings)=='disabled'
    provider=Notices()
    assert dispatch_one(app.state.engine,provider,replace(settings,sms_live_enabled=False))=='disabled'
    assert provider.calls==[]


def test_stale_processing_job_is_marked_uncertain_without_resend(auth_app):
    c,app,settings,_=auth_app;login(c);c.post('/api/v1/auth/preferences',json={'sms_consent':True})
    identity=appointment(app);due=datetime.now(timezone.utc)+timedelta(days=2)
    schedule(c,identity,due)
    with Session(app.state.engine) as db:
        job=db.scalar(select(SmsJob));job.status='processing';job.started_at=int(time.time())-700;db.commit()
    provider=Notices()
    assert dispatch_one(app.state.engine,provider,settings)=='empty'
    with Session(app.state.engine) as db:assert db.scalar(select(SmsJob)).status=='uncertain'
    assert provider.calls==[]


def test_cancelled_appointment_is_never_sent(auth_app):
    c,app,settings,_=auth_app;login(c);c.post('/api/v1/auth/preferences',json={'sms_consent':True})
    identity=appointment(app);due=datetime.now(timezone.utc)+timedelta(days=2);schedule(c,identity,due)
    with Session(app.state.engine) as db:db.get(Appointment,identity).status='cancelled';db.commit()
    provider=Notices()
    assert dispatch_one(app.state.engine,provider,settings,now=int(due.timestamp())+1)=='cancelled'
    assert provider.calls==[]


def test_booking_confirmation_is_transactional_and_not_duplicated(auth_app):
    c,app,settings,_=auth_app;login(c);c.post('/api/v1/auth/preferences',json={'sms_consent':True})
    from zoneinfo import ZoneInfo
    day=(datetime.now(ZoneInfo('Asia/Tehran'))+timedelta(days=1)).date()
    plan={'services':[{'service_code':'hair-braid','duration_minutes':30}],'windows':[{'weekday':day.weekday(),'start_minute':540,'end_minute':720,'step_minutes':30}]}
    assert c.put('/api/v1/admin/scheduling/01',json=plan,headers=AUTH).status_code==200
    slots=c.get('/api/v1/booking/availability',params={'staff_code':'01','services':'hair-braid','day':str(day)}).json()['slots']
    body={'request_id':str(uuid4()),'customer_name':'Offline fixture','phone':PHONE,'service_codes':['hair-braid'],'staff_code':'01','starts_at':slots[0]['starts_at']}
    assert c.post('/api/v1/booking/reservations',json=body).status_code==201
    assert c.post('/api/v1/booking/reservations',json=body).status_code==201
    with Session(app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(SmsJob))==1
        assert db.scalar(select(SmsJob)).kind=='booking_confirmation'
    # Conflicting/rolled-back bookings never create another SMS job.
    assert c.post('/api/v1/booking/reservations',json={**body,'request_id':str(uuid4())}).status_code==409
    # Knowing a verified number does not let an anonymous user trigger its messages.
    c.post('/api/v1/auth/logout',json={})
    assert c.post('/api/v1/booking/reservations',json={**body,'request_id':str(uuid4()),'starts_at':slots[1]['starts_at']}).status_code==201
    with Session(app.state.engine) as db:assert db.scalar(select(func.count()).select_from(SmsJob))==1

def test_old_booking_confirmation_is_cancelled_instead_of_sent(auth_app):
    c,app,settings,_=auth_app;login(c);c.post('/api/v1/auth/preferences',json={'sms_consent':True})
    identity=appointment(app)
    from backend.app.sms_outbox import enqueue
    with Session(app.state.engine) as db:
        enqueue(db,db.get(Appointment,identity),db.get(Customer,PHONE),'booking_confirmation',int(time.time()));db.commit()
    provider=Notices()
    assert dispatch_one(app.state.engine,provider,settings,now=int(time.time())+2*86400)=='cancelled'
    assert provider.calls==[]
