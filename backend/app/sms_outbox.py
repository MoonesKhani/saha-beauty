"""Transactional notice intent, consent checks, and conservative delivery recovery."""
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo
from fastapi import Depends, HTTPException, Request, Query
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from .models import Appointment, Customer, SmsJob
from .customer_auth import begin_write, insert_ignore, session_customer, same_origin
from .sms_provider import SmsUnavailable


def enqueue(db, appointment, customer, kind, due_at):
    key=f'{kind}:{appointment.id}' + (f':{due_at}' if kind=='repair_reminder' else '')
    insert_ignore(db,SmsJob,dict(id=str(uuid4()),dedupe_key=key,appointment_id=appointment.id,
        customer_phone=customer.phone,kind=kind,status='pending',due_at=due_at,
        started_at=None,provider_reference=None,accepted_at=None,error_code=None),['dedupe_key'])


def queue_booking_sms(db, settings, appointment, request):
    if not (settings.sms_notifications_enabled and settings.otp_enabled):return
    customer=session_customer(db,request)
    # An anonymous booking cannot trigger SMS to someone else's number.
    if customer is not None and customer.phone==appointment.phone and customer.sms_consent:
        enqueue(db,appointment,customer,'booking_confirmation',int(time.time()))

class ReminderInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    appointment_id: UUID
    due_at: datetime
    @field_validator('due_at')
    @classmethod
    def aware(cls,value):
        if value.tzinfo is None:raise ValueError('تاریخ باید منطقه زمانی داشته باشد.')
        return value


def mount_sms_outbox(app,settings,session,require_admin):
    def enabled():
        if not settings.sms_notifications_enabled:raise HTTPException(503,'پیامک‌های رزرو و ترمیم هنوز فعال نشده‌اند.')

    @app.get('/api/v1/admin/sms/jobs',dependencies=[Depends(require_admin)])
    def listing(limit:int=Query(default=50,ge=1,le=200),db=Depends(session)):
        enabled()
        return {'items':[{'id':r.id,'appointment_id':r.appointment_id,'kind':r.kind,'status':r.status,'due_at':r.due_at,'error_code':r.error_code,'provider_reference':r.provider_reference} for r in db.scalars(select(SmsJob).order_by(SmsJob.due_at.desc()).limit(limit))]}

    @app.post('/api/v1/admin/sms/repair-reminders',status_code=201,dependencies=[Depends(require_admin)])
    def schedule(data:ReminderInput,request:Request,db=Depends(session)):
        enabled();same_origin(request)
        due=int(data.due_at.timestamp());now=int(time.time())
        if not now<due<=now+366*86400:raise HTTPException(422,'تاریخ ترمیم باید در آینده و حداکثر یک سال بعد باشد.')
        begin_write(db)
        appointment=db.scalar(select(Appointment).where(Appointment.id==str(data.appointment_id)).with_for_update())
        if appointment is None or appointment.status=='cancelled':raise HTTPException(404,'نوبت معتبر پیدا نشد.')
        end=appointment.ends_at if appointment.ends_at.tzinfo else appointment.ends_at.replace(tzinfo=timezone.utc)
        if due<=int(end.timestamp()):raise HTTPException(422,'تاریخ ترمیم باید بعد از پایان نوبت باشد.')
        customer=db.get(Customer,appointment.phone)
        if customer is None or not customer.sms_consent:raise HTTPException(409,'رضایت مشتری با شماره تأییدشده لازم است.')
        # Rescheduling cancels older unsent reminders without deleting their history.
        db.execute(update(SmsJob).where(SmsJob.appointment_id==appointment.id,SmsJob.kind=='repair_reminder',SmsJob.status=='pending',SmsJob.due_at!=due).values(status='cancelled'))
        enqueue(db,appointment,customer,'repair_reminder',due);db.commit()
        return {'scheduled':True,'due_at':due}

    @app.delete('/api/v1/admin/sms/jobs/{identity}',status_code=204,dependencies=[Depends(require_admin)])
    def cancel(identity:UUID,request:Request,db=Depends(session)):
        enabled();same_origin(request)
        result=db.execute(update(SmsJob).where(SmsJob.id==str(identity),SmsJob.status=='pending').values(status='cancelled'));db.commit()
        if result.rowcount!=1:raise HTTPException(409,'فقط پیامک در انتظار را می‌توان لغو کرد.')
        from fastapi import Response
        return Response(status_code=204)


def dispatch_one(engine, provider, settings, now=None):
    """One job; no blind retry after external-send ambiguity or process crash."""
    if not (settings.sms_live_enabled and settings.sms_notifications_enabled and provider.notifications_ready):
        return 'disabled'
    now=int(time.time()) if now is None else now
    with Session(engine) as db:
        begin_write(db)
        # A process that died after sending might have delivered: never resend it.
        db.execute(update(SmsJob).where(SmsJob.status=='processing',SmsJob.started_at<now-600).values(status='uncertain',error_code='worker_interrupted'))
        job=db.scalar(select(SmsJob).where(SmsJob.status=='pending',SmsJob.due_at<=now).order_by(SmsJob.due_at).with_for_update(skip_locked=True).limit(1))
        if job is None:db.commit();return 'empty'
        customer=db.get(Customer,job.customer_phone);appointment=db.get(Appointment,job.appointment_id)
        if (customer is None or not customer.sms_consent or appointment is None or appointment.status=='cancelled'
            or appointment.phone!=job.customer_phone):
            job.status='cancelled';db.commit();return 'cancelled'
        start_at=appointment.starts_at if appointment.starts_at.tzinfo else appointment.starts_at.replace(tzinfo=timezone.utc)
        if job.kind=='booking_confirmation' and (appointment.status!='confirmed' or start_at.timestamp()<=now):
            job.status='cancelled';db.commit();return 'cancelled'
        start=start_at.astimezone(ZoneInfo('Asia/Tehran')).isoformat(timespec='minutes')
        identity=job.id;phone=customer.phone;kind=job.kind
        payload={'appointment_reference':appointment.id,'starts_at':start,'service_code':appointment.service_code}
        job.status='processing';job.started_at=now;db.commit()
    try:
        receipt=provider.send_notice(phone,kind,payload)
    except Exception:
        # No raw exception: URL, OTP or provider diagnostics may include secrets.
        state='uncertain';error='delivery_unconfirmed'
    else:
        state='accepted';error=None
    with Session(engine) as db:
        db.execute(update(SmsJob).where(SmsJob.id==identity,SmsJob.status=='processing').values(status=state,error_code=error,provider_reference=receipt if state=='accepted' else None,accepted_at=now if state=='accepted' else None));db.commit()
    return state
