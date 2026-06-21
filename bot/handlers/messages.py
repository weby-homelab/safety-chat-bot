import logging
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert
from bot.services.moderation import check_fast_heuristics
from bot.database.models import User, BannedDomain, BannedKeyword
from bot.services.user_service import upsert_user, upsert_chat
from bot.services.notifications import send_admin_notification

logger = logging.getLogger(__name__)
router = Router()

# In-memory store for running captcha tasks
# key: (chat_id, user_id) -> (captcha_msg_id, task_object)
captcha_tasks = {}

async def is_admin(message: Message) -> bool:
    # 1087968824 is GroupAnonymousBot, 136817688 is Channel_Bot
    if message.from_user.id in (1087968824, 136817688):
        return True
    try:
        member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in ("creator", "administrator")
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False

async def captcha_timeout_task(bot: Bot, chat_id: int, chat_title: str, user_id: int, full_name: str, username: str | None, join_msg_id: int, captcha_msg_id: int):
    try:
        await asyncio.sleep(180)  # 3 minutes
        logger.info(f"User {user_id} failed captcha in chat {chat_id}. Kicking...")
        
        # Kick user (ban and then unban so they can rejoin)
        try:
            await bot.ban_chat_member(chat_id, user_id)
            await bot.unban_chat_member(chat_id, user_id)
        except Exception as e:
            logger.error(f"Failed to kick user {user_id}: {e}")

        # Delete captcha and join messages
        try:
            await bot.delete_message(chat_id, captcha_msg_id)
        except Exception as e:
            logger.debug(f"Failed to delete captcha message: {e}")

        try:
            await bot.delete_message(chat_id, join_msg_id)
        except Exception as e:
            logger.debug(f"Failed to delete join message: {e}")
            
        # Send admin notification
        username_str = f" (@{username})" if username else ""
        await send_admin_notification(
            f"❌ Користувач <b>{full_name}</b>{username_str} (ID: {user_id}) не пройшов перевірку капчею в чаті <code>{chat_title}</code> та був вилучений."
        )
    except asyncio.CancelledError:
        pass
    finally:
        if (chat_id, user_id) in captcha_tasks:
            del captcha_tasks[(chat_id, user_id)]

@router.message(F.new_chat_members)
async def handle_new_member(message: Message):
    bot = message.bot
    chat_id = message.chat.id
    
    for member in message.new_chat_members:
        if member.is_bot:
            continue
            
        user_id = member.id
        full_name = member.full_name
        username = f" (@{member.username})" if member.username else ""
        
        # 1. Restrict user (mute)
        try:
            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(
                    can_send_messages=False,
                    can_send_media_messages=False,
                    can_send_other_messages=False,
                    can_add_web_page_previews=False
                )
            )
            logger.info(f"Muted new user {user_id} in chat {chat_id}")
        except Exception as e:
            logger.error(f"Failed to restrict user {user_id}: {e}")

        # 2. Send captcha button
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Я людина 👤", callback_data=f"captcha_solve:{user_id}")]
        ])
        
        captcha_msg = await message.answer(
            f"Привіт, {full_name}{username}! 👋\n\n"
            f"Ласкаво просимо до нашої спільноти. Щоб отримати право писати повідомлення, "
            f"будь ласка, підтверди, що ти людина, натиснувши кнопку нижче протягом **3 хвилин**.",
            reply_markup=keyboard
        )
        
        # 3. Schedule timeout
        chat_title = message.chat.title if message.chat.title else f"Chat {chat_id}"
        task = asyncio.create_task(
            captcha_timeout_task(bot, chat_id, chat_title, user_id, member.full_name, member.username, message.message_id, captcha_msg.message_id)
        )
        captcha_tasks[(chat_id, user_id)] = (captcha_msg.message_id, task)

@router.callback_query(F.data.startswith("captcha_solve:"))
async def on_captcha_solve(callback: CallbackQuery):
    target_user_id = int(callback.data.split(":")[1])
    clicker_id = callback.from_user.id
    
    if clicker_id != target_user_id:
        await callback.answer("Ця перевірка не для вас! ❌", show_alert=True)
        return
        
    chat_id = callback.message.chat.id
    bot = callback.bot
    
    # Cancel task
    if (chat_id, clicker_id) in captcha_tasks:
        msg_id, task = captcha_tasks[(chat_id, clicker_id)]
        task.cancel()
        
    # Unmute user
    unmuted_ok = False
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=clicker_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_send_polls=True
            )
        )
        logger.info(f"Unmuted user {clicker_id} in chat {chat_id}")
        unmuted_ok = True
    except Exception as e:
        logger.error(f"Failed to unmute user {clicker_id}: {e}")
        
    # Delete captcha message
    try:
        await callback.message.delete()
    except Exception as e:
        logger.debug(f"Failed to delete captcha message: {e}")
        
    await callback.answer("Дякую! Перевірку пройдено, приємного спілкування. 👍", show_alert=True)
    
    # Send admin notification
    if unmuted_ok:
        chat_title = callback.message.chat.title if callback.message.chat.title else f"Chat {chat_id}"
        username_str = f" (@{callback.from_user.username})" if callback.from_user.username else ""
        await send_admin_notification(
            f"✅ Користувач <b>{callback.from_user.full_name}</b>{username_str} (ID: {clicker_id}) успішно пройшов перевірку капчею в чаті <code>{chat_title}</code>."
        )

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.reply("Привіт! Я Safety AI Bot. Я допомагаю з модерацією чату.")

@router.message(Command("ban_domain"))
async def cmd_ban_domain(message: Message, session: AsyncSession):
    if not await is_admin(message):
        await message.reply("Ця команда доступна лише адміністраторам. ❌")
        return
        
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Вкажіть домен, наприклад: `/ban_domain badsite.com`")
        return
        
    domain = args[1].strip().lower()
    stmt = insert(BannedDomain).values(domain=domain).on_conflict_do_nothing()
    await session.execute(stmt)
    await session.commit()
    
    from bot.main import session_pool_global
    if session_pool_global:
        from bot.services.moderation import load_dynamic_blacklists
        await load_dynamic_blacklists(session_pool_global)
        
    await message.reply(f"Домен `{domain}` додано до блекліста. 🚫")

@router.message(Command("unban_domain"))
async def cmd_unban_domain(message: Message, session: AsyncSession):
    if not await is_admin(message):
        await message.reply("Ця команда доступна лише адміністраторам. ❌")
        return
        
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Вкажіть домен, наприклад: `/unban_domain badsite.com`")
        return
        
    domain = args[1].strip().lower()
    await session.execute(delete(BannedDomain).where(BannedDomain.domain == domain))
    await session.commit()
    
    from bot.main import session_pool_global
    if session_pool_global:
        from bot.services.moderation import load_dynamic_blacklists
        await load_dynamic_blacklists(session_pool_global)
        
    await message.reply(f"Домен `{domain}` вилучено з блекліста. ✅")

@router.message(Command("ban_word"))
async def cmd_ban_word(message: Message, session: AsyncSession):
    if not await is_admin(message):
        await message.reply("Ця команда доступна лише адміністраторам. ❌")
        return
        
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Вкажіть слово/фразу, наприклад: `/ban_word крипта`")
        return
        
    keyword = args[1].strip().lower()
    stmt = insert(BannedKeyword).values(keyword=keyword).on_conflict_do_nothing()
    await session.execute(stmt)
    await session.commit()
    
    from bot.main import session_pool_global
    if session_pool_global:
        from bot.services.moderation import load_dynamic_blacklists
        await load_dynamic_blacklists(session_pool_global)
        
    await message.reply(f"Слово/фразу `{keyword}` додано до блекліста. 🚫")

@router.message(Command("unban_word"))
async def cmd_unban_word(message: Message, session: AsyncSession):
    if not await is_admin(message):
        await message.reply("Ця команда доступна лише адміністраторам. ❌")
        return
        
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Вкажіть слово/фразу, наприклад: `/unban_word крипта`")
        return
        
    keyword = args[1].strip().lower()
    await session.execute(delete(BannedKeyword).where(BannedKeyword.keyword == keyword))
    await session.commit()
    
    from bot.main import session_pool_global
    if session_pool_global:
        from bot.services.moderation import load_dynamic_blacklists
        await load_dynamic_blacklists(session_pool_global)
        
    await message.reply(f"Слово/фразу `{keyword}` вилучено з блекліста. ✅")

@router.message(Command("report"))
async def cmd_report(message: Message, session: AsyncSession):
    if not message.reply_to_message:
        await message.reply("Ця команда має бути відповіддю на повідомлення, на яке ви скаржитесь. ⚠️")
        return
        
    reporter_id = message.from_user.id
    target_msg = message.reply_to_message
    chat_title = message.chat.title if message.chat.title else f"Chat {message.chat.id}"
    
    is_reporter_admin = await is_admin(message)
    if is_reporter_admin:
        try:
            await target_msg.delete()
            await message.delete()
            logger.info(f"Admin {reporter_id} reported message {target_msg.message_id}. Deleted.")
            
            reporter_username = f" (@{message.from_user.username})" if message.from_user.username else ""
            author_name = target_msg.from_user.full_name if target_msg.from_user else "Unknown"
            author_username = f" (@{target_msg.from_user.username})" if target_msg.from_user and target_msg.from_user.username else ""
            await send_admin_notification(
                f"🛡️ Адміністратор <b>{message.from_user.full_name}</b>{reporter_username} видалив повідомлення від <b>{author_name}</b>{author_username} у чаті <code>{chat_title}</code> через /report."
            )
            return
        except Exception as e:
            logger.error(f"Failed to delete reported message: {e}")
            
    reporter_username = f" (@{message.from_user.username})" if message.from_user.username else ""
    author_name = target_msg.from_user.full_name if target_msg.from_user else "Unknown"
    author_username = f" (@{target_msg.from_user.username})" if target_msg.from_user and target_msg.from_user.username else ""
    target_text = target_msg.text or target_msg.caption or "[медіа/інше]"
    
    await send_admin_notification(
        f"⚠️ Скарга від <b>{message.from_user.full_name}</b>{reporter_username} на повідомлення від <b>{author_name}</b>{author_username} у чаті <code>{chat_title}</code>.\n"
        f"Вміст повідомлення:\n<code>{target_text[:300]}</code>"
    )
            
    await message.reply("Вашу скаргу надіслано. Дякуємо за пильність! 🛡️")

@router.message()
async def process_text_message(message: Message, session: AsyncSession):
    if not message.from_user or message.from_user.is_bot:
        return
        
    await upsert_user(session, message.from_user.id, message.from_user.full_name, message.from_user.username)
    if message.chat:
        chat_title = message.chat.title if message.chat.title else f"Chat {message.chat.id}"
        await upsert_chat(session, message.chat.id, chat_title)

    text_to_check = message.text or message.caption or ""
    if not text_to_check:
        return

    logger.debug(f"Checking message from {message.from_user.id}: {text_to_check[:50]}")
    
    if check_fast_heuristics(text_to_check):
        logger.info(f"Spam detected from {message.from_user.id}, deleting...")
        deleted_ok = False
        try:
            await message.delete()
            deleted_ok = True
        except Exception as e:
            logger.error(f"Failed to delete message: {e}")
            
        if deleted_ok:
            chat_title = message.chat.title if message.chat.title else f"Chat {message.chat.id}"
            username_str = f" (@{message.from_user.username})" if message.from_user.username else ""
            await send_admin_notification(
                f"🚫 Видалено спам від <b>{message.from_user.full_name}</b>{username_str} (ID: {message.from_user.id}) у чаті <code>{chat_title}</code>.\n"
                f"Текст:\n<code>{text_to_check[:300]}</code>"
            )
        return