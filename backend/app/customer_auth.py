"""Persistent, one-use OTP with separate customer sessions. No administrator privileges."""
import hashlib
import hmac
import re
import secrets
import time
from uuid import UUID, uuid4
from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, update
from .models import AuthLimit, Customer, CustomerSession, OtpChallenge
from .sms_provider import SmsUnavailable

COOKIE = '__Host-saha_session'
SESSION_SECONDS = 7*24*3600


def normalize_phone(value):
    value=value.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','01234567890123456789')).replace(' ','').replace('-','')
    if value.startswith('+98'):value='0'+value[3:]
    if not re.fullmatch(r'09[0-9]{9}',value):raise ValueError('شماره همراه معتبر وارد کنید.')
    return value

class PhoneInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    phone: str = Field(max_length=24)
    _phone=field_validator('phone')(normalize_phone)

class VerifyInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    challenge_id: UUID
    code: str = Field(pattern=r'^[0-9]{4,10}$')

class Preferences(BaseModel):
    model_config=ConfigDict(extra='forbid')
    sms_consent: bool


def digest(secret, *parts):
    return hmac.new(secret.encode(),'\0'.join(parts).encode(),hashlib.sha256).hexdigest()


def begin_write(db):
    if db.bind.dialect.name=='sqlite':db.connection().exec_driver_sql('BEGIN IMMEDIATE')


def insert_ignore(db, model, values, keys):
    if db.bind.dialect.name=='postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    db.execute(insert(model).values(**values).on_conflict_do_nothing(index_elements=keys))


def same_origin(request):
    if request.headers.get('origin') not in (None,str(request.base_url).rstrip('/')):
        raise HTTPException(403,'درخواست باید از همین سایت ارسال شود.')


def configured(settings):
    if not (settings.otp_enabled and settings.sms_live_enabled and settings.otp_contract_confirmed
            and re.fullmatch(r'[A-Za-z0-9_-]{16,256}',settings.melipayamak_api_key.get_secret_value())
            and len(settings.otp_secret.get_secret_value())>=32
            and 30<=settings.otp_ttl_seconds<=300):
        raise HTTPException(503,'ورود پیامکی هنوز فعال نشده است.')


def rate(db, secret, scopes, now):
    # Fixed rows, ordered locks, shared by every worker. No user-supplied XFF parsing.
    for scope, maximum, cooldown in sorted(scopes):
        key=digest(secret,'rate',scope)
        insert_ignore(db,AuthLimit,{'key':key,'window_start':now,'count':0,'last_at':0},['key'])
        row=db.scalar(select(AuthLimit).where(AuthLimit.key==key).with_for_update())
        if now-row.window_start>=3600:row.window_start=now;row.count=0
        if row.count>=maximum or (row.last_at and now-row.last_at<cooldown):
            db.rollback()
            raise HTTPException(429,'درخواست‌ها زیاد است؛ کمی بعد تلاش کنید.',headers={'Retry-After':str(max(cooldown,60))})
        row.count+=1;row.last_at=now
        db.flush()


def session_customer(db, request, now=None):
    token=request.cookies.get(COOKIE,'')
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}',token):return None
    now=int(time.time()) if now is None else now
    record=db.get(CustomerSession,hashlib.sha256(token.encode()).hexdigest())
    if record is None or record.expires_at<=now:return None
    return db.get(Customer,record.customer_phone)


def require_booking_customer(db, settings, request, phone):
    if not settings.booking_require_otp:return
    if not settings.otp_enabled:raise HTTPException(503,'ورود پیامکی برای رزرو هنوز فعال نشده است.')
    customer=session_customer(db,request)
    if customer is None:raise HTTPException(401,'برای ثبت نوبت ابتدا شماره همراه خود را تأیید کنید.')
    if customer.phone!=phone:raise HTTPException(403,'شماره رزرو باید با شماره تأییدشده شما یکسان باشد.')


def mount_customer_auth(app,settings,session):
    @app.get('/api/v1/auth/capabilities')
    def capabilities():
        try:configured(settings)
        except HTTPException:return {'enabled':False}
        return {'enabled':True,'otp_ttl_seconds':settings.otp_ttl_seconds}

    @app.post('/api/v1/auth/otp/request',status_code=202)
    def request_otp(data:PhoneInput,request:Request,db=Depends(session)):
        configured(settings);same_origin(request)
        now=int(time.time());secret=settings.otp_secret.get_secret_value()
        ip=request.client.host if request.client else 'unknown'
        begin_write(db)
        rate(db,secret,[(f'send-phone:{data.phone}',3,60),(f'send-ip:{ip}',10,0),('send-global',30,0)],now)
        db.execute(update(OtpChallenge).where(OtpChallenge.phone==data.phone,OtpChallenge.status.in_(['sending','active'])).values(status='invalidated',code_digest=None))
        identity=str(uuid4())
        db.add(OtpChallenge(id=identity,phone=data.phone,code_digest=None,status='sending',created_at=now,expires_at=now+settings.otp_ttl_seconds,attempts=0))
        db.commit()  # Release locks BEFORE the external request; reserved rate is not refunded.
        try:
            code=app.state.sms_provider.send_otp(data.phone)
        except SmsUnavailable:
            db.execute(update(OtpChallenge).where(OtpChallenge.id==identity,OtpChallenge.status=='sending').values(status='failed',code_digest=None));db.commit()
            raise HTTPException(503,'ارسال کد انجام نشد یا نتیجه نامشخص است؛ کمی بعد تلاش کنید.') from None
        result=db.execute(update(OtpChallenge).where(OtpChallenge.id==identity,OtpChallenge.status=='sending',OtpChallenge.expires_at>int(time.time())).values(status='active',code_digest=digest(secret,'otp',identity,data.phone,code)))
        db.commit()
        if result.rowcount!=1:raise HTTPException(409,'درخواست منقضی یا جایگزین شده است.')
        return {'challenge_id':identity,'expires_in':max(0,now+settings.otp_ttl_seconds-int(time.time())),'retry_after':60}

    @app.post('/api/v1/auth/otp/verify')
    def verify_otp(data:VerifyInput,request:Request,response:Response,db=Depends(session)):
        configured(settings);same_origin(request)
        now=int(time.time());secret=settings.otp_secret.get_secret_value()
        begin_write(db)
        ip=request.client.host if request.client else 'unknown'
        rate(db,secret,[(f'verify-ip:{ip}',30,0),('verify-global',300,0)],now)
        challenge=db.scalar(select(OtpChallenge).where(OtpChallenge.id==str(data.challenge_id)).with_for_update())
        valid=challenge is not None and challenge.status=='active' and challenge.expires_at>now and challenge.attempts<5
        if not valid:
            db.commit();raise HTTPException(400,'کد نامعتبر یا منقضی شده است.')
        challenge.attempts+=1
        if not hmac.compare_digest(challenge.code_digest or '',digest(secret,'otp',challenge.id,challenge.phone,data.code)):
            if challenge.attempts>=5:challenge.status='locked';challenge.code_digest=None
            db.commit();raise HTTPException(400,'کد نامعتبر یا منقضی شده است.')
        challenge.status='consumed';challenge.code_digest=None
        insert_ignore(db,Customer,{'phone':challenge.phone,'verified_at':now,'sms_consent':False},['phone'])
        db.execute(update(Customer).where(Customer.phone==challenge.phone).values(verified_at=now))
        token=secrets.token_urlsafe(32)
        db.add(CustomerSession(digest=hashlib.sha256(token.encode()).hexdigest(),customer_phone=challenge.phone,expires_at=now+SESSION_SECONDS))
        db.commit()
        response.set_cookie(COOKIE,token,max_age=SESSION_SECONDS,secure=True,httponly=True,samesite='lax',path='/')
        return {'authenticated':True,'phone':challenge.phone}

    @app.get('/api/v1/auth/me')
    def me(request:Request,db=Depends(session)):
        if not settings.otp_enabled:raise HTTPException(401,'ابتدا وارد شوید.')
        customer=session_customer(db,request)
        if customer is None:raise HTTPException(401,'ابتدا وارد شوید.')
        return {'phone':customer.phone,'verified':True,'sms_consent':customer.sms_consent}

    @app.post('/api/v1/auth/preferences')
    def preferences(data:Preferences,request:Request,db=Depends(session)):
        same_origin(request)
        if not settings.otp_enabled:raise HTTPException(401,'ابتدا وارد شوید.')
        customer=session_customer(db,request)
        if customer is None:raise HTTPException(401,'ابتدا وارد شوید.')
        customer.sms_consent=data.sms_consent;db.commit()
        return {'sms_consent':customer.sms_consent}

    @app.post('/api/v1/auth/logout',status_code=204)
    def logout(request:Request,db=Depends(session)):
        same_origin(request)
        token=request.cookies.get(COOKIE,'')
        if re.fullmatch(r'[A-Za-z0-9_-]{43}',token):
            record=db.get(CustomerSession,hashlib.sha256(token.encode()).hexdigest())
            if record:db.delete(record);db.commit()
        response=Response(status_code=204)
        response.delete_cookie(COOKIE,secure=True,httponly=True,samesite='lax',path='/')
        return response
