from sqlalchemy import String, Text, Integer, CheckConstraint, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class Service(Base):
    __tablename__ = 'services'
    __table_args__ = (CheckConstraint('revision >= 1', name='service_revision_positive'),)
    code: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, unique=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    price_toman: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class TeamMember(Base):
    __tablename__ = 'team_members'
    code: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(120))
    bio: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)

from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey

class Appointment(Base):
    __tablename__ = 'appointments'
    __table_args__ = (CheckConstraint('ends_at > starts_at', name='appointment_time_order'), CheckConstraint("status IN ('pending','confirmed','completed','cancelled')", name='appointment_status'))
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20))
    service_code: Mapped[str] = mapped_column(ForeignKey('services.code'), index=True)
    staff_code: Mapped[str | None] = mapped_column(ForeignKey('team_members.code'), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default='pending')
    revision: Mapped[int] = mapped_column(Integer, default=1)

class Consultation(Base):
    __tablename__ = 'consultations'
    __table_args__ = (CheckConstraint("status IN ('new','contacted','closed')", name='consultation_status'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20))
    topic: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(20), default='new')
    revision: Mapped[int] = mapped_column(Integer, default=1)

class Offer(Base):
    __tablename__ = 'offers'
    __table_args__ = (CheckConstraint("kind IN ('buffet','playlist','products')", name='offer_kind'), CheckConstraint('price_toman IS NULL OR price_toman >= 0', name='offer_price'))
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    price_toman: Mapped[int | None] = mapped_column(Integer)
    audio_url: Mapped[str | None] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)

from sqlalchemy import JSON
class StaffService(Base):
    __tablename__='staff_services'
    staff_code: Mapped[str] = mapped_column(ForeignKey('team_members.code'), primary_key=True)
    service_code: Mapped[str] = mapped_column(ForeignKey('services.code'), primary_key=True)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    __table_args__=(CheckConstraint('duration_minutes > 0 AND duration_minutes <= 600',name='staff_service_duration'),)

class StaffSchedule(Base):
    __tablename__='staff_schedules'
    staff_code: Mapped[str] = mapped_column(ForeignKey('team_members.code'),primary_key=True)
    weekday: Mapped[int] = mapped_column(Integer,primary_key=True)
    start_minute: Mapped[int] = mapped_column(Integer)
    end_minute: Mapped[int] = mapped_column(Integer)
    step_minutes: Mapped[int] = mapped_column(Integer)
    __table_args__=(CheckConstraint('weekday >= 0 AND weekday <= 6',name='schedule_weekday'),CheckConstraint('start_minute >= 0 AND end_minute <= 1440 AND start_minute < end_minute',name='schedule_window'),CheckConstraint('step_minutes >= 5 AND step_minutes <= 120',name='schedule_step'))

class AppointmentService(Base):
    __tablename__='appointment_services'
    appointment_id: Mapped[str] = mapped_column(ForeignKey('appointments.id'),primary_key=True)
    service_code: Mapped[str] = mapped_column(ForeignKey('services.code'),primary_key=True)

class BookingNotice(Base):
    __tablename__='booking_notices'
    appointment_id: Mapped[str] = mapped_column(ForeignKey('appointments.id'),primary_key=True)
    seen: Mapped[bool] = mapped_column(Boolean,default=False)
