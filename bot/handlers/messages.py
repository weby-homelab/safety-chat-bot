import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from bot.services.moderation import check_fast_heuristics
from bot.database.models import User
from bot.services.user_service import upsert_user, upsert_chat

logger = logging.getLogger(__name__)
router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.reply("Привіт! Я Safety AI Bot. Я допомагаю з модерацією та кармою. Спробуй /karma")

@router.message(Command("karma"))
async def cmd_karma(message: Message, session: AsyncSession):
    logger.info(f"Command /karma from user {message.from_user.id}")
    user_id = message.from_user.id
    
    # Спочатку спробуємо зареєструвати юзера, якщо його нема
    await upsert_user(session, user_id, message.from_user.full_name, message.from_user.username)
    
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if user:
        await message.reply(f"Твоя карма: {user.total_karma} 🔥")
    else:
        await message.reply("Помилка отримання даних. Спробуй пізніше.")

@router.message(F.text)
async def process_text_message(message: Message, session: AsyncSession):
    # Register user and chat
    await upsert_user(session, message.from_user.id, message.from_user.full_name, message.from_user.username)
    if message.chat:
        chat_title = message.chat.title if message.chat.title else f"Chat {message.chat.id}"
        await upsert_chat(session, message.chat.id, chat_title)

    logger.info(f"Message from {message.from_user.id} in {message.chat.id}: {message.text[:50]}")
    
    if check_fast_heuristics(message.text):
        logger.info(f"Spam detected from {message.from_user.id}, deleting...")
        try:
            await message.delete()
        except Exception as e:
            logger.error(f"Failed to delete message: {e}")
        return