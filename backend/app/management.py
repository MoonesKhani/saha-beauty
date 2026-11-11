"""Authenticated management; demo content lives exclusively in an offline browser adapter."""
from datetime import datetime, timezone, timedelta
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo
import re
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select, func, or_, update
from .models import Service, TeamMember, Appointment, Consultation, Offer

class Input(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    @field_validator('*',mode='after')
    @classmethod
    def reject_controls(cls,v):
        if isinstance(v,str) and (not v or any(ord(c)<32 and c not in '\n\t' for c in v)):
            raise ValueError('متن معتبر وارد کنید.')
        return v

class ServiceInput(Input):
    name:str=Field(min_length=1,max_length=120)
    description:str=Field(min_length=1,max_length=2000)
    price_toman:int|None=Field(default=None,ge=0,le=2000000000)
    is_active:bool=True

class TeamInput(Input):
    name:str=Field(min_length=1,max_length=120)
    role:str=Field(min_length=1,max_length=120)
    bio:str=Field(min_length=1,max_length=2000)
    is_active:bool=True

class ContactInput(Input):
    customer_name:str=Field(min_length=1,max_length=120)
    phone:str=Field(min_length=1,max_length=20)
    @field_validator('phone')
    @classmethod
    def phone_number(cls,v):
        v=v.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','01234567890123456789')).replace(' ','').replace('-','')
        if v.startswith('+98'):v='0'+v[3:]
        if not re.fullmatch(r'09\d{9}',v):raise ValueError('شماره همراه معتبر وارد کنید.')
        return v

class AppointmentInput(ContactInput):
    service_code:str=Field(max_length=36)
    staff_code:str|None=Field(default=None,max_length=36)
    starts_at:datetime
    ends_at:datetime
    status:Literal['pending','confirmed','completed','cancelled']='pending'
    @field_validator('starts_at','ends_at')
    @classmethod
    def aware_time(cls,v):
        if v.tzinfo is None or v.utcoffset() is None:raise ValueError('منطقه زمانی نوبت لازم است.')
        return v.astimezone(timezone.utc)
    @model_validator(mode='after')
    def time_range(self):
        if self.ends_at<=self.starts_at:raise ValueError('پایان نوبت باید بعد از شروع باشد.')
        return self

class ConsultationInput(ContactInput):
    topic:str=Field(min_length=1,max_length=120)
    message:str|None=Field(default=None,max_length=2000)
    status:Literal['new','contacted','closed']='new'

class OfferInput(Input):
    kind:Literal['buffet','playlist','products']
    title:str=Field(min_length=1,max_length=120)
    description:str=Field(min_length=1,max_length=2000)
    price_toman:int|None=Field(default=None,ge=0,le=2000000000)
    audio_url:Literal['/assets/saha-quiet-bloom.mp3']|None=None
    is_active:bool=True
    @model_validator(mode='after')
    def licensed_track(self):
        if self.kind!='playlist' and self.audio_url is not None:raise ValueError('صدا فقط برای پلی‌لیست است.')
        if self.kind=='playlist' and self.price_toman is not None:raise ValueError('پلی‌لیست قیمت ندارد.')
        return self

ENTITIES={'services':(Service,ServiceInput),'team':(TeamMember,TeamInput),'appointments':(Appointment,AppointmentInput),'consultations':(Consultation,ConsultationInput),'offers':(Offer,OfferInput)}

def out(record):
    data={c.name:getattr(record,c.name) for c in record.__table__.columns}
    for k,v in data.items():
        if isinstance(v,datetime):data[k]=(v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    if isinstance(record,Appointment):
        from sqlalchemy.orm import object_session
        from .models import AppointmentService
        db=object_session(record)
        data['service_codes']=list(db.scalars(select(AppointmentService.service_code).where(AppointmentService.appointment_id==record.id))) or [record.service_code]
    return jsonable_encoder(data)

def mount_management(app,session,require_admin):
    router=APIRouter(prefix='/api/v1/admin',dependencies=[Depends(require_admin)])

    @router.get('/overview')
    def overview(db=Depends(session)):
        now=datetime.now(ZoneInfo('Asia/Tehran'));start=now.replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc);end=start+timedelta(days=1)
        count=lambda model,*filters:db.scalar(select(func.count()).select_from(model).where(*filters))
        return {'services':count(Service,Service.is_active.is_(True)),'team':count(TeamMember,TeamMember.is_active.is_(True)),'today':count(Appointment,Appointment.starts_at>=start,Appointment.starts_at<end,Appointment.status!='cancelled'),'pending':count(Appointment,Appointment.status=='pending'),'consultations':count(Consultation,Consultation.status=='new'),'upcoming':[out(x) for x in db.scalars(select(Appointment).where(Appointment.starts_at>=now.astimezone(timezone.utc),Appointment.status.in_(['pending','confirmed'])).order_by(Appointment.starts_at).limit(6))]}

    def spec(entity):
        if entity not in ENTITIES:raise HTTPException(404,'بخش پیدا نشد.')
        return ENTITIES[entity]

    @router.get('/{entity}')
    def listing(entity:str,q:str=Query(default='',max_length=120),page:int=Query(default=1,ge=1),size:int=Query(default=50,ge=1,le=200),kind:Literal['buffet','playlist','products']|None=None,db=Depends(session)):
        model,_=spec(entity);filters=[]
        if kind is not None:
            if model is not Offer:raise HTTPException(422,'فیلتر نامعتبر است.')
            filters.append(Offer.kind==kind)
        if q:
            fields=[getattr(model,c) for c in ['name','title','description','customer_name','phone','topic','role'] if hasattr(model,c)]
            filters.append(or_(*[func.lower(c).contains(q.lower(),autoescape=True) for c in fields]))
        order=model.starts_at.desc() if model is Appointment else model.sort_order if hasattr(model,'sort_order') else model.id
        total=db.scalar(select(func.count()).select_from(model).where(*filters))
        rows=db.scalars(select(model).where(*filters).order_by(order).offset((page-1)*size).limit(size))
        return {'items':[out(row) for row in rows],'total':total,'page':page,'size':size}

    def validate(entity,payload):
        _,schema=spec(entity)
        from pydantic import ValidationError
        try:return schema.model_validate(payload).model_dump()
        except ValidationError as e:
            errors=[{'field':'.'.join(map(str,x['loc'])),'message':x['msg']} for x in e.errors()]
            raise HTTPException(422,errors) from None

    def write_lock(db):
        if db.bind.dialect.name=='sqlite':db.connection().exec_driver_sql('BEGIN IMMEDIATE')

    def check_appointment(db,data,exclude=None,old_staff=None):
        service=db.get(Service,data['service_code'])
        if service is None or not service.is_active:raise HTTPException(422,'خدمت فعال انتخاب کنید.')
        staff=data.get('staff_code')
        if staff:
            codes=sorted(set([x for x in [staff,old_staff] if x]))
            members=list(db.scalars(select(TeamMember).where(TeamMember.code.in_(codes)).order_by(TeamMember.code).with_for_update()))
            member=next((m for m in members if m.code==staff),None)
            if member is None or not member.is_active:raise HTTPException(422,'همکار فعال انتخاب کنید.')
            if data['status'] in ['pending','confirmed']:
                query=select(Appointment.id).where(Appointment.staff_code==staff,Appointment.status.in_(['pending','confirmed']),Appointment.starts_at<data['ends_at'],Appointment.ends_at>data['starts_at'])
                if exclude:query=query.where(Appointment.id!=exclude)
                if db.scalar(query.limit(1)):raise HTTPException(409,'این بازه برای همکار انتخاب‌شده پر است.')

    @router.post('/{entity}',status_code=201)
    def create(entity:str,payload:dict,db=Depends(session)):
        model,_=spec(entity);data=validate(entity,payload)
        if model is Consultation and data.get('message') is None:data['message']=''
        if model is Appointment:write_lock(db);check_appointment(db,data)
        if hasattr(model,'sort_order'):data['sort_order']=(db.scalar(select(func.max(model.sort_order))) or 0)+1
        identity='code' if hasattr(model,'code') else 'id';data[identity]=uuid4().hex
        row=model(**data);db.add(row);db.commit();db.refresh(row);return out(row)

    @router.put('/{entity}/{identity}')
    def edit(entity:str,identity:str,payload:dict,db=Depends(session)):
        model,_=spec(entity)
        revision=payload.get('revision')
        if type(revision) is not int or revision<1:raise HTTPException(422,'شماره بازبینی لازم است.')
        data=validate(entity,{k:v for k,v in payload.items() if k!='revision'})
        if model is Consultation and data.get('message') is None:data['message']=''
        if model is Appointment:write_lock(db)
        row=db.get(model,identity)
        if row is None:raise HTTPException(404,'رکورد پیدا نشد.')
        if model is Appointment:check_appointment(db,data,identity,row.staff_code)
        key=model.code if hasattr(model,'code') else model.id
        result=db.execute(update(model).where(key==identity,model.revision==revision).values(**data,revision=revision+1))
        if result.rowcount!=1:db.rollback();raise HTTPException(409,'رکورد تغییر کرده؛ تازه‌سازی کنید.')
        db.commit();db.expire_all();return out(db.get(model,identity))

    @router.delete('/{entity}/{identity}')
    def archive(entity:str,identity:str,revision:int=Query(ge=1),db=Depends(session)):
        model,_=spec(entity);key=model.code if hasattr(model,'code') else model.id
        fields={'is_active':False} if hasattr(model,'is_active') else {'status':'cancelled' if model is Appointment else 'closed'}
        result=db.execute(update(model).where(key==identity,model.revision==revision).values(**fields,revision=revision+1))
        if result.rowcount!=1:db.rollback();raise HTTPException(409,'رکورد تغییر کرده یا پیدا نشد.')
        db.commit();return {'status':'archived'}

    app.include_router(router)

    @app.get('/api/v1/leisure/{kind}')
    def leisure(kind:Literal['buffet','playlist','products'],db=Depends(session)):
        return {'items':[{k:v for k,v in out(row).items() if k in ['id','kind','title','description','price_toman','audio_url']} for row in db.scalars(select(Offer).where(Offer.kind==kind,Offer.is_active.is_(True)).order_by(Offer.title))]}
