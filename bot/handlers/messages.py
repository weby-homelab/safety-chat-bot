from aiogram import Router, F
from aiogram.types import Message
from bot.services.moderation import check_fast_heuristics

router = Router()

@router.message(F.text)
async def process_text_message(message: Message):
    if check_fast_heuristics(message.text):
        await message.delete()
        # Notify admins logic here
        return
        
    # AI check can be dispatched asynchronously or for specific users