"""Management and public leisure content; no sample customer data is inserted."""
from alembic import op
import sqlalchemy as sa
revision='0002_management'
down_revision='0001_catalog'
branch_labels=depends_on=None

def upgrade():
    for table in ['services','team_members']:
        with op.batch_alter_table(table) as batch:
            batch.alter_column('code', existing_type=sa.String(2), type_=sa.String(36), existing_nullable=False)
            batch.add_column(sa.Column('is_active',sa.Boolean(),nullable=False,server_default=sa.true()))
            if table=='services': batch.add_column(sa.Column('price_toman',sa.Integer(),nullable=True))
            else: batch.add_column(sa.Column('revision',sa.Integer(),nullable=False,server_default='1'))
    op.create_table('appointments',sa.Column('id',sa.String(36),primary_key=True),sa.Column('customer_name',sa.String(120),nullable=False),sa.Column('phone',sa.String(20),nullable=False),sa.Column('service_code',sa.String(36),sa.ForeignKey('services.code'),nullable=False),sa.Column('staff_code',sa.String(36),sa.ForeignKey('team_members.code')),sa.Column('starts_at',sa.DateTime(timezone=True),nullable=False),sa.Column('ends_at',sa.DateTime(timezone=True),nullable=False),sa.Column('status',sa.String(20),nullable=False,server_default='pending'),sa.Column('revision',sa.Integer(),nullable=False,server_default='1'),sa.CheckConstraint('ends_at > starts_at',name='appointment_time_order'),sa.CheckConstraint("status IN ('pending','confirmed','completed','cancelled')",name='appointment_status'))
    for field in ['service_code','staff_code','starts_at']:op.create_index('ix_appointments_'+field,'appointments',[field])
    op.create_table('consultations',sa.Column('id',sa.String(36),primary_key=True),sa.Column('customer_name',sa.String(120),nullable=False),sa.Column('phone',sa.String(20),nullable=False),sa.Column('topic',sa.String(120),nullable=False),sa.Column('message',sa.Text(),nullable=False,server_default=''),sa.Column('status',sa.String(20),nullable=False,server_default='new'),sa.Column('revision',sa.Integer(),nullable=False,server_default='1'),sa.CheckConstraint("status IN ('new','contacted','closed')",name='consultation_status'))
    op.create_table('offers',sa.Column('id',sa.String(36),primary_key=True),sa.Column('kind',sa.String(20),nullable=False),sa.Column('title',sa.String(120),nullable=False),sa.Column('description',sa.Text(),nullable=False),sa.Column('price_toman',sa.Integer()),sa.Column('audio_url',sa.String(300)),sa.Column('is_active',sa.Boolean(),nullable=False,server_default=sa.true()),sa.Column('revision',sa.Integer(),nullable=False,server_default='1'),sa.CheckConstraint("kind IN ('buffet','playlist','products')",name='offer_kind'),sa.CheckConstraint('price_toman IS NULL OR price_toman >= 0',name='offer_price'))
    op.create_index('ix_offers_kind','offers',['kind'])

def downgrade():
    for table in ['offers','consultations','appointments']:op.drop_table(table)
    for table in ['team_members','services']:
        with op.batch_alter_table(table) as batch:
            batch.drop_column('is_active')
            batch.drop_column('price_toman' if table=='services' else 'revision')
            batch.alter_column('code',existing_type=sa.String(36),type_=sa.String(2),existing_nullable=False)
