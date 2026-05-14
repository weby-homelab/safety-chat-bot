import structlog
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from bot.services.moderation import check_fast_heuristics
from bot.services.ai import AIService
from bot.database.models import User

logger = structlog.get_logger()
router = Router()
ai_service = AIService()

@router.message(Command("karma"))
async def cmd_karma(message: Message, session: AsyncSession):
    user_id = message.from_user.id
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if user and user.total_karma > 0:
        await message.reply(f"Твоя карма: {user.total_karma} 🔥")
    else:
        await message.reply("У тебе поки немає карми. Пиши корисні повідомлення і сусіди віддячать реакціями! 🌱")

@router.message(Command("summary"))
async def cmd_summary(message: Message):
    # In a real scenario, you'd fetch the last N messages from the DB for this chat
    # For MVP, we'll return a placeholder or ask for reply
    await message.reply("Функція самарі зараз збирає дані. Спробуйте пізніше, коли в чаті буде більше активності! 📊")

@router.message(Command("factcheck"))
async def cmd_factcheck(message: Message):
    if not message.reply_to_message or not message.reply_to_message.text:
        await message.reply("Будь ласка, зроби reply (відповідь) на повідомлення, яке потрібно перевірити на факти! 🕵️‍♂️")
        return
        
    processing_msg = await message.reply("⏳ Перевіряю факти, зачекайте...")
    try:
        result = await ai_service.factcheck(message.reply_to_message.text)
        await processing_msg.edit_text(result)
    except Exception as e:
        logger.error("Factcheck failed", error=str(e))
        await processing_msg.edit_text("❌ Сталася помилка при перевірці фактів. Можливо, сервіс перевантажений.")

@router.message(F.text)
async def process_text_message(message: Message):
    logger.info("Received message", chat_id=message.chat.id, user_id=message.from_user.id, text=message.text[:50])
    
    if check_fast_heuristics(message.text):
        logger.info("Spam detected, deleting", message_id=message.message_id)
        await message.delete()
        # Notify admins logic here
        return