"""add progress and warning to documents

Revision ID: b3c1d2e4f5a6
Revises: 7090c8a56f4d
Create Date: 2026-11-25 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3c1d2e4f5a6'
down_revision: Union[str, None] = '7090c8a56f4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'documents',
        sa.Column('progress', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column('documents', sa.Column('warning', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('documents') as batch:
        batch.drop_column('warning')
        batch.drop_column('progress')
