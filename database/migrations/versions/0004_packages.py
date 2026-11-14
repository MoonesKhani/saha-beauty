"""Packages, gallery, explicit specialties and assistant relationships."""
from alembic import op
import sqlalchemy as sa
revision='0004_packages'
down_revision='0003_booking'
branch_labels=depends_on=None

def upgrade():
    # SQLite supports ADD COLUMN REFERENCES directly when its default is NULL.
    # Avoid rebuilding a parent table referenced by existing appointments.
    if op.get_bind().dialect.name == 'sqlite':
        op.execute('ALTER TABLE team_members ADD COLUMN parent_code VARCHAR(36) REFERENCES team_members(code)')
    else:
        op.add_column('team_members',sa.Column('parent_code',sa.String(36),nullable=True))
        op.create_foreign_key('team_parent','team_members','team_members',['parent_code'],['code'])
    op.create_table('packages',sa.Column('code',sa.String(36),primary_key=True),sa.Column('name',sa.String(120),nullable=False),sa.Column('category',sa.String(20),nullable=False),sa.Column('tier',sa.String(20),nullable=False),sa.Column('description',sa.Text(),nullable=False),sa.Column('price_toman',sa.Integer()),sa.Column('service_codes',sa.JSON(),nullable=False),sa.Column('is_active',sa.Boolean(),nullable=False),sa.Column('revision',sa.Integer(),nullable=False),sa.Column('sort_order',sa.Integer(),unique=True,nullable=False),sa.CheckConstraint('price_toman IS NULL OR price_toman >= 0',name='package_price'))
    op.create_table('gallery_images',sa.Column('id',sa.String(36),primary_key=True),sa.Column('title',sa.String(120),nullable=False),sa.Column('src',sa.String(500),nullable=False),sa.Column('category',sa.String(20),nullable=False),sa.Column('staff_code',sa.String(36),sa.ForeignKey('team_members.code')),sa.Column('is_active',sa.Boolean(),nullable=False),sa.Column('revision',sa.Integer(),nullable=False))
    op.create_table('staff_expertise',sa.Column('staff_code',sa.String(36),sa.ForeignKey('team_members.code'),primary_key=True),sa.Column('service_code',sa.String(36),sa.ForeignKey('services.code'),primary_key=True))
    op.create_table('booking_prices',sa.Column('request_id',sa.String(36),primary_key=True),sa.Column('selection',sa.JSON(),nullable=False),sa.Column('quote',sa.JSON(),nullable=False))
    # Preserve existing owner-configured assignments as explicit specialties.
    op.execute('INSERT INTO staff_expertise (staff_code, service_code) SELECT staff_code, service_code FROM staff_services')

def downgrade():
    for name in ['booking_prices','staff_expertise','gallery_images','packages']:op.drop_table(name)
    with op.batch_alter_table('team_members') as batch:
        batch.drop_constraint('team_parent',type_='foreignkey')
        batch.drop_column('parent_code')
