import asyncio
import structlog
from aiogram import Bot, Dispatcher
from bot.config import load_config
from bot.database.engine import create_db_pool
from bot.middlewares.db import DbSessionMiddleware
from bot.handlers.reactions import router as reactions_router
from bot.handlers.messages import router as messages_router

logger = structlog.get_logger()

async def main():
    config = load_config()
    bot = Bot(token=config.bot_token.get_secret_value())
    dp = Dispatcher()
    
    engine, session_pool = create_db_pool(config.database_url.get_secret_value())
    dp.update.middleware(DbSessionMiddleware(session_pool=session_pool))
    
    # Handlers will be registered here
    dp.include_router(reactions_router)
    dp.include_router(messages_router)
    
    logger.info("Starting bot")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())