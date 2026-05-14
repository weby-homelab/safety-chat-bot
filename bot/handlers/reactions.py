import structlog
from aiogram import Router, F
from aiogram.types import MessageReactionUpdated
from sqlalchemy.ext.asyncio import AsyncSession
from bot.services.user_service import upsert_user, upsert_chat

logger = structlog.get_logger()
router = Router()
VALID_REACTIONS = {"🔥", "❤️", "👍", "👏", "🏆", "💯", "⚡️"}

@router.message_reaction()
async def handle_reaction(event: MessageReactionUpdated, session: AsyncSession):
    if not event.user:
        return
        
    await upsert_user(session, event.user.id, event.user.full_name, event.user.username)
    
    if event.chat:
        chat_title = event.chat.title if event.chat.title else f"Chat {event.chat.id}"
        await upsert_chat(session, event.chat.id, chat_title)
    
    old_emojis = {r.emoji for r in event.old_reaction if hasattr(r, 'emoji') and r.emoji in VALID_REACTIONS}
    new_emojis = {r.emoji for r in event.new_reaction if hasattr(r, 'emoji') and r.emoji in VALID_REACTIONS}
    
    added = new_emojis - old_emojis
    removed = old_emojis - new_emojis
    
    total_delta = len(added) - len(removed)
    
    if total_delta == 0:
        return

    # TODO: Add logic to extract original message author id for karma assignment.
    # Currently event.user is the reactor, not the author. 
    # For MVP, we log the karma shift.
    logger.info("Karma shifted", reactor_id=event.user.id, chat_id=event.chat.id, message_id=event.message_id, delta=total_delta)