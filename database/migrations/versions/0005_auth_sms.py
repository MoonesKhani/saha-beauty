"""Add customer OTP, persistent limits/sessions, and SMS outbox. No old data changed."""
from alembic import op
import sqlalchemy as sa
revision = '0005_auth_sms'
down_revision = '0004_packages'
branch_labels = depends_on = None

def upgrade():
    op.create_table('customers', sa.Column('phone',sa.String(11),primary_key=True),sa.Column('verified_at',sa.BigInteger(),nullable=False),sa.Column('sms_consent',sa.Boolean(),nullable=False))
    op.create_table('otp_challenges',sa.Column('id',sa.String(36),primary_key=True),sa.Column('phone',sa.String(11),nullable=False),sa.Column('code_digest',sa.String(64)),sa.Column('status',sa.String(16),nullable=False),sa.Column('created_at',sa.BigInteger(),nullable=False),sa.Column('expires_at',sa.BigInteger(),nullable=False),sa.Column('attempts',sa.Integer(),nullable=False))
    op.create_index('ix_otp_challenges_phone','otp_challenges',['phone'])
    op.create_table('auth_limits',sa.Column('key',sa.String(64),primary_key=True),sa.Column('window_start',sa.BigInteger(),nullable=False),sa.Column('count',sa.Integer(),nullable=False),sa.Column('last_at',sa.BigInteger(),nullable=False))
    op.create_table('customer_sessions',sa.Column('digest',sa.String(64),primary_key=True),sa.Column('customer_phone',sa.String(11),sa.ForeignKey('customers.phone'),nullable=False),sa.Column('expires_at',sa.BigInteger(),nullable=False))
    op.create_index('ix_customer_sessions_customer_phone','customer_sessions',['customer_phone'])
    op.create_index('ix_customer_sessions_expires_at','customer_sessions',['expires_at'])
    op.create_table('sms_jobs',sa.Column('id',sa.String(36),primary_key=True),sa.Column('dedupe_key',sa.String(160),unique=True,nullable=False),sa.Column('appointment_id',sa.String(36),sa.ForeignKey('appointments.id'),nullable=False),sa.Column('customer_phone',sa.String(11),sa.ForeignKey('customers.phone'),nullable=False),sa.Column('kind',sa.String(20),nullable=False),sa.Column('status',sa.String(16),nullable=False),sa.Column('due_at',sa.BigInteger(),nullable=False),sa.Column('started_at',sa.BigInteger()),sa.Column('sent_at',sa.BigInteger()),sa.Column('error_code',sa.String(40)))
    op.create_index('ix_sms_jobs_appointment_id','sms_jobs',['appointment_id'])
    op.create_index('ix_sms_jobs_due_at','sms_jobs',['due_at'])

def downgrade():
    # Explicit maintenance only: auth/session/outbox records would be lost.
    for name in ['sms_jobs','customer_sessions','auth_limits','otp_challenges','customers']:
        op.drop_table(name)
