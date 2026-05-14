from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

def create_db_pool(db_url: str):
    engine = create_async_engine(
        db_url,
        echo=False,
        pool_size=10,
        max_overflow=20,
    )
    session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return engine, session_maker