"""The additive migration must preserve existing owner configuration/reservations."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session
from backend.app.config import ROOT
from backend.app.cli import seed_database,upgrade_database
from backend.app.db import make_engine
from backend.app.models import Appointment,Service


def test_auth_migration_preserves_existing_reservation_and_tariff(tmp_path):
    url=f'sqlite:///{tmp_path / "old-schema.db"}'
    cfg=Config(str(ROOT/'database/alembic.ini'));cfg.attributes['database_url']=url
    command.upgrade(cfg,'0004_packages');seed_database(url)
    engine=make_engine(url);identity=str(uuid4());start=datetime.now(timezone.utc)
    with Session(engine) as db:
        service=db.get(Service,'02');service.description='owner-edited-before-otp';service.price_toman=123456
        db.add(Appointment(id=identity,phone='09123456789',customer_name='Migration fixture',service_code='02',staff_code='02',starts_at=start,ends_at=start+timedelta(hours=1),status='confirmed'));db.commit()
    upgrade_database(url)
    with Session(engine) as db:
        assert db.get(Service,'02').description=='owner-edited-before-otp'
        assert db.get(Service,'02').price_toman==123456
        appointment=db.get(Appointment,identity)
        assert appointment.phone=='09123456789' and appointment.status=='confirmed'
    engine.dispose()
