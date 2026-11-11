"""Initial public catalog. No customer, health, payment or booking data."""
from alembic import op
import sqlalchemy as sa

revision = '0001_catalog'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('services',
        sa.Column('code', sa.String(2), primary_key=True),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, unique=True),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='1'),
        sa.CheckConstraint('revision >= 1', name='service_revision_positive'))
    op.create_table('team_members',
        sa.Column('code', sa.String(2), primary_key=True),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('role', sa.String(120), nullable=False),
        sa.Column('bio', sa.Text(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, unique=True))

def downgrade():
    op.drop_table('team_members')
    op.drop_table('services')
