import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from bot.config import load_config
from bot.database.engine import create_db_pool
from bot.middlewares.db import DbSessionMiddleware
from bot.handlers.messages import router as messages_router
from bot.services.moderation import load_dynamic_blacklists

from aiogram.types import Update

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Global session pool reference for commands/handlers
session_pool_global = None

async def main():
    global session_pool_global
    config = load_config()
    bot = Bot(token=config.bot_token.get_secret_value())
    dp = Dispatcher()
    
    # Debug: логування абсолютно всіх вхідних апдейтів
    @dp.update.outer_middleware()
    async def update_logger(handler, event: Update, data):
        logger.info(f"DEBUG: Incoming update type: {event.event_type}")
        return await handler(event, data)
    
    engine, session_pool = create_db_pool(config.database_url.get_secret_value())
    session_pool_global = session_pool
    
    # Load dynamic blacklists on startup
    await load_dynamic_blacklists(session_pool)
    
    # Реєстрація мідлварі для різних типів апдейтів
    middleware = DbSessionMiddleware(session_pool=session_pool)
    dp.message.middleware(middleware)
    dp.callback_query.middleware(middleware)
    
    # Handlers
    dp.include_router(messages_router)
    
    logger.info("Starting bot...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())