"""Public reservation uses only owner-configured schedules and server-side locking."""
from datetime import date,datetime,time,timedelta,timezone
from collections import deque
from threading import Lock
import time as clock
from hashlib import sha256
from uuid import UUID
from zoneinfo import ZoneInfo
from fastapi import Depends,HTTPException,Query,Request
from pydantic import Field,model_validator
from sqlalchemy import select,delete,update
from .models import Service,TeamMember,Appointment,AppointmentService,StaffService,StaffSchedule,BookingNotice
from .management import ContactInput,Input
TZ=ZoneInfo('Asia/Tehran')
class Assignment(Input):
 service_code:str=Field(max_length=36)
 duration_minutes:int=Field(ge=1,le=600)
class Window(Input):
 weekday:int=Field(ge=0,le=6)
 start_minute:int=Field(ge=0,lt=1440)
 end_minute:int=Field(gt=0,le=1440)
 step_minutes:int=Field(ge=5,le=120)
 @model_validator(mode='after')
 def ordered(self):
  if self.end_minute<=self.start_minute:raise ValueError('پایان باید بعد از شروع باشد.')
  return self
class Schedule(Input):
 services:list[Assignment]=Field(max_length=30)
 windows:list[Window]=Field(max_length=7)
 @model_validator(mode='after')
 def unique(self):
  if len({s.service_code for s in self.services})!=len(self.services) or len({s.weekday for s in self.windows})!=len(self.windows):raise ValueError('خدمت یا روز تکراری است.')
  return self
class BookingIn(ContactInput):
 request_id:UUID
 service_codes:list[str]=Field(min_length=1,max_length=16)
 staff_code:str=Field(max_length=36)
 starts_at:datetime
 @model_validator(mode='after')
 def valid(self):
  if self.starts_at.tzinfo is None:raise ValueError('منطقه زمانی لازم است.')
  if len(set(self.service_codes))!=len(self.service_codes):raise ValueError('خدمت تکراری است.')
  return self

def mount_booking(app,settings,session,require_admin):
 attempts={};guard=Lock()
 def throttle(request):
  identity=sha256(((request.client.host if request.client else "unknown")+settings.admin_api_token).encode()).hexdigest();now=clock.monotonic()
  with guard:
   if len(attempts)>5000:
    for key in [key for key,values in attempts.items() if not values or values[-1]<now-60]:attempts.pop(key,None)
    if len(attempts)>5000:raise HTTPException(429,"درخواست‌ها زیاد است؛ کمی بعد تلاش کنید.")
   values=attempts.setdefault(identity,deque())
   while values and values[0]<now-60:values.popleft()
   if len(values)>=12:raise HTTPException(429,"درخواست‌ها زیاد است؛ یک دقیقه بعد تلاش کنید.",headers={"Retry-After":"60"})
   values.append(now)
 def enabled():
  if not settings.booking_enabled or len(settings.admin_api_token)<32:raise HTTPException(503,'رزرو آنلاین هنوز فعال نشده است؛ با سالن هماهنگ کنید.')
 def lock(db,staff_code):
  if db.bind.dialect.name=='sqlite':db.connection().exec_driver_sql('BEGIN IMMEDIATE')
  member=db.scalar(select(TeamMember).where(TeamMember.code==staff_code).with_for_update())
  if not member or not member.is_active:raise HTTPException(422,'متخصص فعال انتخاب کنید.')
  return member
 def configuration(db,staff_code,codes,day):
  if len(codes)!=len(set(codes)) or not 1<=len(codes)<=16:raise HTTPException(422,'خدمات معتبر انتخاب کنید.')
  if day<datetime.now(TZ).date() or day>datetime.now(TZ).date()+timedelta(days=89):raise HTTPException(422,'تاریخ خارج از بازه مجاز است.')
  member=db.get(TeamMember,staff_code)
  if not member or not member.is_active:raise HTTPException(422,'متخصص فعال انتخاب کنید.')
  services=list(db.scalars(select(Service).where(Service.code.in_(codes),Service.is_active.is_(True))))
  assignments=list(db.scalars(select(StaffService).where(StaffService.staff_code==staff_code,StaffService.service_code.in_(codes))))
  if len(services)!=len(codes) or any(s.code in ['01','06'] for s in services):raise HTTPException(422,'خدمت رزروپذیر انتخاب کنید.')
  if len(assignments)!=len(codes):raise HTTPException(409,'متخصص برای همه خدمات انتخابی برنامه تأییدشده ندارد.')
  duration=sum(a.duration_minutes for a in assignments)
  window=db.get(StaffSchedule,(staff_code,day.weekday()))
  return duration,window
 def slots(db,staff_code,codes,day):
  duration,window=configuration(db,staff_code,codes,day)
  if not window:return []
  start=datetime.combine(day,time(),TZ)+timedelta(minutes=window.start_minute)
  end=datetime.combine(day,time(),TZ)+timedelta(minutes=window.end_minute)
  existing=list(db.scalars(select(Appointment).where(Appointment.staff_code==staff_code,Appointment.status.in_(['pending','confirmed']),Appointment.starts_at<end.astimezone(timezone.utc),Appointment.ends_at>start.astimezone(timezone.utc))))
  rows=[]
  while start+timedelta(minutes=duration)<=end:
   finish=start+timedelta(minutes=duration)
   def aware(value):return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
   busy=any(aware(a.starts_at)<finish and aware(a.ends_at)>start for a in existing)
   if start>datetime.now(TZ):rows.append({'starts_at':start.isoformat(),'ends_at':finish.isoformat(),'state':'occupied' if busy else 'available'})
   start+=timedelta(minutes=window.step_minutes)
  return rows
 @app.get('/api/v1/booking/catalog')
 def catalog(db=Depends(session)):
  return {'enabled':settings.booking_enabled and len(settings.admin_api_token)>=32,'payment_enabled':False,'services':[{'code':s.code,'name':s.name,'category':'مو' if s.code.startswith('hair-') else 'سایر خدمات'} for s in db.scalars(select(Service).where(Service.is_active.is_(True),Service.code.not_in(['01','06'])).order_by(Service.sort_order))],'team':[{'code':s.code,'name':s.name,'role':s.role} for s in db.scalars(select(TeamMember).where(TeamMember.is_active.is_(True)).order_by(TeamMember.sort_order))]}
 @app.get('/api/v1/booking/availability')
 def availability(staff_code:str=Query(max_length=36),services:str=Query(max_length=600),day:date=Query(),db=Depends(session)):
  enabled();return {'slots':slots(db,staff_code,services.split(','),day),'timezone':'Asia/Tehran'}
 @app.post('/api/v1/booking/reservations',status_code=201)
 def reserve(data:BookingIn,request:Request,db=Depends(session)):
  enabled()
  origin=request.headers.get('origin')
  if origin and origin!=str(request.base_url).rstrip('/'):raise HTTPException(403,'درخواست باید از همین سایت ارسال شود.')
  throttle(request)
  lock(db,data.staff_code)
  old=db.get(Appointment,str(data.request_id))
  if old:
   previous=list(db.scalars(select(AppointmentService.service_code).where(AppointmentService.appointment_id==old.id)))
   start=old.starts_at if old.starts_at.tzinfo else old.starts_at.replace(tzinfo=timezone.utc)
   if old.phone!=data.phone or start!=data.starts_at or old.staff_code!=data.staff_code or sorted(previous)!=sorted(data.service_codes):raise HTTPException(409,'شناسه درخواست قبلاً استفاده شده است.')
   return {'reference':old.id,'status':old.status,'payment_required':False}
  choices=slots(db,data.staff_code,data.service_codes,data.starts_at.astimezone(TZ).date())
  chosen=next((s for s in choices if datetime.fromisoformat(s['starts_at'])==data.starts_at),None)
  if not chosen or chosen['state']!='available':raise HTTPException(409,'این بازه آزاد نیست؛ جدول را تازه کنید.')
  appointment=Appointment(id=str(data.request_id),customer_name=data.customer_name,phone=data.phone,service_code=data.service_codes[0],staff_code=data.staff_code,starts_at=data.starts_at.astimezone(timezone.utc),ends_at=datetime.fromisoformat(chosen['ends_at']).astimezone(timezone.utc),status='confirmed')
  db.add(appointment);db.flush()
  db.add(BookingNotice(appointment_id=appointment.id,seen=False))
  db.add_all([AppointmentService(appointment_id=appointment.id,service_code=code) for code in data.service_codes]);db.commit()
  return {'reference':appointment.id,'status':'confirmed','payment_required':False}
 @app.get('/api/v1/admin/booking-notifications',dependencies=[Depends(require_admin)])
 def notices(db=Depends(session)):
  return {'ids':list(db.scalars(select(BookingNotice.appointment_id).where(BookingNotice.seen.is_(False))))}
 @app.post('/api/v1/admin/booking-notifications/seen',dependencies=[Depends(require_admin)])
 def seen(ids:list[UUID],db=Depends(session)):
  if len(ids)>200:raise HTTPException(422,'حداکثر ۲۰۰ اعلان را انتخاب کنید.')
  db.execute(update(BookingNotice).where(BookingNotice.appointment_id.in_([str(x) for x in ids])).values(seen=True));db.commit();return {'status':'saved'}
 @app.get('/api/v1/admin/scheduling/{staff_code}',dependencies=[Depends(require_admin)])
 def schedule(staff_code:str,db=Depends(session)):
  if not db.get(TeamMember,staff_code):raise HTTPException(404,'متخصص پیدا نشد.')
  return {'services':[{'service_code':s.service_code,'duration_minutes':s.duration_minutes} for s in db.scalars(select(StaffService).where(StaffService.staff_code==staff_code))],'windows':[{'weekday':s.weekday,'start_minute':s.start_minute,'end_minute':s.end_minute,'step_minutes':s.step_minutes} for s in db.scalars(select(StaffSchedule).where(StaffSchedule.staff_code==staff_code))]}
 @app.put('/api/v1/admin/scheduling/{staff_code}',dependencies=[Depends(require_admin)])
 def configure(staff_code:str,data:Schedule,db=Depends(session)):
  lock(db,staff_code)
  valid=set(db.scalars(select(Service.code).where(Service.is_active.is_(True),Service.code.not_in(['01','06']))))
  if any(s.service_code not in valid for s in data.services):raise HTTPException(422,'خدمت فعال و رزروپذیر انتخاب کنید.')
  db.execute(delete(StaffService).where(StaffService.staff_code==staff_code));db.execute(delete(StaffSchedule).where(StaffSchedule.staff_code==staff_code))
  db.add_all([StaffService(staff_code=staff_code,**s.model_dump()) for s in data.services]);db.add_all([StaffSchedule(staff_code=staff_code,**s.model_dump()) for s in data.windows]);db.commit();return {'status':'saved'}
