"""Explicit real scheduling and multiple services; no imaginary capacity is seeded."""
from alembic import op
import sqlalchemy as sa
revision='0003_booking'
down_revision='0002_management'
branch_labels=depends_on=None

def upgrade():
 op.create_table('booking_notices',sa.Column('appointment_id',sa.String(36),sa.ForeignKey('appointments.id'),primary_key=True),sa.Column('seen',sa.Boolean(),nullable=False,server_default=sa.false()))
 op.create_table('staff_services',sa.Column('staff_code',sa.String(36),sa.ForeignKey('team_members.code'),primary_key=True),sa.Column('service_code',sa.String(36),sa.ForeignKey('services.code'),primary_key=True),sa.Column('duration_minutes',sa.Integer(),nullable=False),sa.CheckConstraint('duration_minutes > 0 AND duration_minutes <= 600',name='staff_service_duration'))
 op.create_table('staff_schedules',sa.Column('staff_code',sa.String(36),sa.ForeignKey('team_members.code'),primary_key=True),sa.Column('weekday',sa.Integer(),primary_key=True),sa.Column('start_minute',sa.Integer(),nullable=False),sa.Column('end_minute',sa.Integer(),nullable=False),sa.Column('step_minutes',sa.Integer(),nullable=False),sa.CheckConstraint('weekday >= 0 AND weekday <= 6',name='schedule_weekday'),sa.CheckConstraint('start_minute >= 0 AND end_minute <= 1440 AND start_minute < end_minute',name='schedule_window'),sa.CheckConstraint('step_minutes >= 5 AND step_minutes <= 120',name='schedule_step'))
 op.create_table('appointment_services',sa.Column('appointment_id',sa.String(36),sa.ForeignKey('appointments.id'),primary_key=True),sa.Column('service_code',sa.String(36),sa.ForeignKey('services.code'),primary_key=True))

def downgrade():
 for table in ['appointment_services','staff_schedules','staff_services','booking_notices']:op.drop_table(table)
