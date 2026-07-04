"""drop_karma_records

Revision ID: 5b3d1e8a9f01
Revises: 4a02c4ce276e
Create Date: 2026-07-04 17:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b3d1e8a9f01'
down_revision: Union[str, None] = '4a02c4ce276e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index('idx_karma_message', table_name='karma_records')
    op.drop_index('idx_karma_user_chat', table_name='karma_records')
    op.drop_table('karma_records')


def downgrade() -> None:
    op.create_table('karma_records',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('emoji', sa.String(length=10), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('message_id', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['chat_id'], ['chats.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_karma_user_chat', 'karma_records', ['user_id', 'chat_id'], unique=False)
    op.create_index('idx_karma_message', 'karma_records', ['message_id'], unique=False)
