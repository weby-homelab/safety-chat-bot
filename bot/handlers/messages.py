import structlog
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from bot.services.moderation import check_fast_heuristics
from bot.database.models import User

logger = structlog.get_logger()
router = Router()

@router.message(Command("karma"))
async def cmd_karma(message: Message, session: AsyncSession):
    user_id = message.from_user.id
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if user and user.total_karma > 0:
        await message.reply(f"Твоя карма: {user.total_karma} 🔥")
    else:
        await message.reply("У тебе поки немає карми. Пиши корисні повідомлення і сусіди віддячать реакціями! 🌱")

@router.message(F.text)
async def process_text_message(message: Message):
    logger.info("Received message", chat_id=message.chat.id, user_id=message.from_user.id, text=message.text[:50])
    
    if check_fast_heuristics(message.text):
        logger.info("Spam detected, deleting", message_id=message.message_id)
        await message.delete()
        # Notify admins logic here
        return