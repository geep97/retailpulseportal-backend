"""add_auth_provider_id

Revision ID: 52a1b2c3d4e5  # You can pick any random string
Revises: None             # Use the ID of your previous migration if you have one
Create Date: 2026-06-04 12:45:00.000000

"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    # This adds the column to your existing table in Supabase
    op.add_column('users', sa.Column('auth_provider_id', sa.String(), nullable=True))

def downgrade():
    # This allows you to 'undo' if you ever need to
    op.drop_column('users', 'auth_provider_id')