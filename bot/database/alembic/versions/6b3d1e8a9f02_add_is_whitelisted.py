"""add_is_whitelisted

Revision ID: 6b3d1e8a9f02
Revises: 5b3d1e8a9f01
Create Date: 2026-07-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6b3d1e8a9f02'
down_revision: Union[str, None] = '5b3d1e8a9f01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('is_whitelisted', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'is_whitelisted')
