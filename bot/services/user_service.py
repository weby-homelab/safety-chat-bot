from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from bot.database.models import User, Chat

async def upsert_user(session: AsyncSession, id: int, full_name: str, username: str | None = None):
    stmt = insert(User).values(id=id, full_name=full_name, username=username)
    stmt = stmt.on_conflict_do_update(
        index_elements=['id'],
        set_=dict(full_name=full_name, username=username)
    )
    await session.execute(stmt)
    await session.commit()

async def upsert_chat(session: AsyncSession, id: int, title: str):
    stmt = insert(Chat).values(id=id, title=title)
    stmt = stmt.on_conflict_do_update(
        index_elements=['id'],
        set_=dict(title=title)
    )
    await session.execute(stmt)
    await session.commit()