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
    
    from_user_is_admin = await is_admin(message)
    
    for member in message.new_chat_members:
        # 1. Якщо це бот, доданий не-адміном -> банимо і бота, і того хто додав
        if member.is_bot:
            if not from_user_is_admin:
                logger.info(f"Non-admin user {message.from_user.id} tried to add bot {member.id} ({member.username}). Banning both...")
                try:
                    await bot.ban_chat_member(chat_id, member.id)
                except Exception as e:
                    logger.error(f"Failed to ban bot {member.id}: {e}")
                
                try:
                    await bot.ban_chat_member(chat_id, message.from_user.id)
                except Exception as e:
                    logger.error(f"Failed to ban user {message.from_user.id} who added the bot: {e}")
                
                try:
                    await message.delete()
                except Exception as e:
                    logger.debug(f"Failed to delete join message for bot: {e}")
                
                username_str = f" (@{message.from_user.username})" if message.from_user.username else ""
                bot_username_str = f" (@{member.username})" if member.username else ""
                chat_title = message.chat.title if message.chat.title else f"Chat {chat_id}"
                await send_admin_notification(
                    f"🚨 <b>Спроба спаму ботами!</b>\n"
                    f"Користувач <b>{message.from_user.full_name}</b>{username_str} (ID: {message.from_user.id}) "
                    f"спробував додати бота <b>{member.full_name}</b>{bot_username_str} (ID: {member.id}) в чат <code>{chat_title}</code>.\n"
                    f"❌ <b>Обидва акаунти були забанені.</b>"
                )
            continue
            
        user_id = member.id
        full_name = member.full_name
        username_val = member.username
        username = f" (@{username_val})" if username_val else ""
        
        # 2. Якщо це звичайний користувач, перевіряємо його профіль на порно-ботів
        from bot.services.moderation import check_suspicious_profile
        is_suspicious, reason = check_suspicious_profile(member.first_name, member.last_name, username_val)
        if is_suspicious:
            logger.info(f"Suspicious profile detected for user {user_id} ({full_name}): {reason}. Banning immediately.")
            try:
                await bot.ban_chat_member(chat_id, user_id)
            except Exception as e:
                logger.error(f"Failed to ban suspicious user {user_id}: {e}")
                
            try:
                await message.delete()
            except Exception as e:
                logger.debug(f"Failed to delete join message for suspicious user: {e}")
                
            chat_title = message.chat.title if message.chat.title else f"Chat {chat_id}"
            await send_admin_notification(
                f"🚨 <b>Виявлено та забанено порно-бота!</b>\n"
                f"Користувач <b>{full_name}</b>{username} (ID: {user_id}) забанений на вході в чат <code>{chat_title}</code>.\n"
                f"🔎 <b>Причина:</b> {reason}"
            )
            continue
            
        # 3. Restrict user (mute)
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

        # 4. Send math captcha button (July 2026 Ukrainian Anti-Botnet Captcha)
        import random
        a = random.randint(1, 10)
        b = random.randint(1, 9)
        operation = random.choice(["+", "-"])
        
        if operation == "+":
            question = f"Скільки буде {a} додати {b}?"
            correct_answer = a + b
        else:
            if a < b:
                a, b = b, a
            question = f"Скільки буде {a} відняти {b}?"
            correct_answer = a - b
            
        options = {correct_answer}
        while len(options) < 3:
            wrong = correct_answer + random.choice([-3, -2, -1, 1, 2, 3, 4])
            if wrong >= 0:
                options.add(wrong)
                
        options_list = list(options)
        random.shuffle(options_list)
        
        buttons = []
        for opt in options_list:
            is_correct = 1 if opt == correct_answer else 0
            buttons.append(InlineKeyboardButton(text=str(opt), callback_data=f"captcha_math:{user_id}:{is_correct}"))
            
        keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons])
        
        captcha_msg = await message.answer(
            f"Привіт, {full_name}{username}! 👋\n\n"
            f"Ласкаво просимо до нашої спільноти. Для захисту від спам-ботів, будь ласка, розв'яжи математичне завдання протягом **3 хвилин**:\n\n"
            f"🧮 <b>{question}</b>",
            reply_markup=keyboard
        )
        
        # 5. Schedule timeout
        chat_title = message.chat.title if message.chat.title else f"Chat {chat_id}"
        task = asyncio.create_task(
            captcha_timeout_task(bot, chat_id, chat_title, user_id, member.full_name, member.username, message.message_id, captcha_msg.message_id)
        )
        captcha_tasks[(chat_id, user_id)] = (captcha_msg.message_id, task)

@router.callback_query(F.data.startswith("captcha_solve:"))
async def on_captcha_solve(callback: CallbackQuery, session: AsyncSession):
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
        
    # Register user in DB
    try:
        from bot.services.user_service import upsert_user
        await upsert_user(session, clicker_id, callback.from_user.full_name, callback.from_user.username)
    except Exception as e:
        logger.error(f"Failed to upsert user after captcha: {e}")
        
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

@router.callback_query(F.data.startswith("captcha_math:"))
async def on_captcha_math_solve(callback: CallbackQuery, session: AsyncSession):
    parts = callback.data.split(":")
    target_user_id = int(parts[1])
    is_correct = int(parts[2])
    clicker_id = callback.from_user.id
    
    if clicker_id != target_user_id:
        await callback.answer("Ця перевірка не для вас! ❌", show_alert=True)
        return
        
    chat_id = callback.message.chat.id
    bot = callback.bot
    
    if is_correct != 1:
        await callback.answer("Відповідь неправильна! Спробуйте ще раз або зверніться до адміна. ❌", show_alert=True)
        logger.info(f"User {clicker_id} failed math captcha with incorrect answer in chat {chat_id}. Banning...")
        
        if (chat_id, clicker_id) in captcha_tasks:
            msg_id, task = captcha_tasks[(chat_id, clicker_id)]
            task.cancel()
            del captcha_tasks[(chat_id, clicker_id)]
            
        try:
            await bot.ban_chat_member(chat_id, clicker_id)
            await bot.unban_chat_member(chat_id, clicker_id)
        except Exception as e:
            logger.error(f"Failed to kick user {clicker_id}: {e}")
            
        try:
            await callback.message.delete()
        except Exception as e:
            logger.debug(f"Failed to delete captcha message: {e}")
            
        chat_title = callback.message.chat.title if callback.message.chat.title else f"Chat {chat_id}"
        await send_admin_notification(
            f"❌ Користувач <b>{callback.from_user.full_name}</b> (ID: {clicker_id}) вибрав неправильну відповідь у капчі в чаті <code>{chat_title}</code> та був вилучений."
        )
        return
        
    if (chat_id, clicker_id) in captcha_tasks:
        msg_id, task = captcha_tasks[(chat_id, clicker_id)]
        task.cancel()
        
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
        
    # Register user in DB
    try:
        from bot.services.user_service import upsert_user
        await upsert_user(session, clicker_id, callback.from_user.full_name, callback.from_user.username)
    except Exception as e:
        logger.error(f"Failed to upsert user after captcha: {e}")
        
    try:
        await callback.message.delete()
    except Exception as e:
        logger.debug(f"Failed to delete captcha message: {e}")
        
    await callback.answer("Правильно! Вітаємо у чаті. 👍", show_alert=True)
    
    if unmuted_ok:
        chat_title = callback.message.chat.title if callback.message.chat.title else f"Chat {chat_id}"
        username_str = f" (@{callback.from_user.username})" if callback.from_user.username else ""
        await send_admin_notification(
            f"✅ Користувач <b>{callback.from_user.full_name}</b>{username_str} (ID: {clicker_id}) успішно розв'язав математичну капчу в чаті <code>{chat_title}</code>."
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

    user_id = message.from_user.id
    chat_id = message.chat.id

    # Check if user already exists in DB — if not, this is first message => show captcha
    from sqlalchemy import select
    result = await session.execute(select(User).where(User.id == user_id))
    existing_user = result.scalar_one_or_none()
    logger.info(f"CAPTCHA CHECK: user={user_id} chat_type={message.chat.type} exists={existing_user is not None}")

    if existing_user is None and message.chat.type in ("group", "supergroup"):
        # Skip captcha for admins
        try:
            member = await message.bot.get_chat_member(message.chat.id, user_id)
            if member.status in ("creator", "administrator"):
                logger.info(f"Skipping captcha for admin {user_id}")
                await upsert_user(session, user_id, message.from_user.full_name, message.from_user.username)
                return
        except Exception:
            pass

        bot = message.bot
        full_name = message.from_user.full_name
        username_val = message.from_user.username
        username = f" (@{username_val})" if username_val else ""

        # Check suspicious profile
        from bot.services.moderation import check_suspicious_profile
        is_suspicious, reason = check_suspicious_profile(message.from_user.first_name, message.from_user.last_name, username_val)
        if is_suspicious:
            logger.info(f"Suspicious profile for user {user_id} ({full_name}): {reason}. Banning.")
            try:
                await bot.ban_chat_member(chat_id, user_id)
            except Exception:
                pass
            try:
                await message.delete()
            except Exception:
                pass
            chat_title = message.chat.title or f"Chat {chat_id}"
            await send_admin_notification(
                f"🚨 <b>Виявлено та забанено порно-бота!</b>\n"
                f"Користувач <b>{full_name}</b>{username} (ID: {user_id}) забанений при першому повідомленні в чаті <code>{chat_title}</code>.\n"
                f"🔎 <b>Причина:</b> {reason}"
            )
            return

        # Mute user
        try:
            await bot.restrict_chat_member(
                chat_id=chat_id, user_id=user_id,
                permissions=ChatPermissions(
                    can_send_messages=False,
                    can_send_media_messages=False,
                    can_send_other_messages=False,
                    can_add_web_page_previews=False
                )
            )
            logger.info(f"Muted new user {user_id} in chat {chat_id} (first-message captcha)")
        except Exception as e:
            logger.error(f"Failed to restrict user {user_id}: {e}")

        # Send math captcha
        import random
        a = random.randint(1, 10)
        b = random.randint(1, 9)
        operation = random.choice(["+", "-"])
        if operation == "+":
            question = f"Скільки буде {a} додати {b}?"
            correct_answer = a + b
        else:
            if a < b:
                a, b = b, a
            question = f"Скільки буде {a} відняти {b}?"
            correct_answer = a - b

        options = {correct_answer}
        while len(options) < 3:
            w = correct_answer + random.choice([-3, -2, -1, 1, 2, 3, 4])
            if w >= 0:
                options.add(w)
        options_list = list(options)
        random.shuffle(options_list)

        buttons = []
        for opt in options_list:
            is_correct = 1 if opt == correct_answer else 0
            buttons.append(InlineKeyboardButton(text=str(opt), callback_data=f"captcha_math:{user_id}:{is_correct}"))
        keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons])

        captcha_msg = await message.answer(
            f"Привіт, {full_name}{username}! 👋\n\n"
            f"Ласкаво просимо до нашої спільноти. Для захисту від спам-ботів, будь ласка, розв'яжи математичне завдання протягом **3 хвилин**:\n\n"
            f"🧮 <b>{question}</b>",
            reply_markup=keyboard
        )

        # Schedule timeout
        chat_title = message.chat.title or f"Chat {chat_id}"
        task = asyncio.create_task(
            captcha_timeout_task(bot, chat_id, chat_title, user_id, full_name, username_val, message.message_id, captcha_msg.message_id)
        )
        captcha_tasks[(chat_id, user_id)] = (captcha_msg.message_id, task)

        # Delete the user's first message (captcha required before chatting)
        try:
            await message.delete()
        except Exception:
            pass

        return

    await upsert_user(session, user_id, message.from_user.full_name, message.from_user.username)
    if message.chat:
        chat_title = message.chat.title if message.chat.title else f"Chat {message.chat.id}"
        await upsert_chat(session, message.chat.id, chat_title)

    text_to_check = message.text or message.caption or ""
    if not text_to_check:
        return

    logger.debug(f"Checking message from {user_id}: {text_to_check[:50]}")
    
    if check_fast_heuristics(text_to_check):
        logger.info(f"Spam detected from {user_id}, deleting...")
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
                f"🚫 Видалено спам від <b>{message.from_user.full_name}</b>{username_str} (ID: {user_id}) у чаті <code>{chat_title}</code>.\n"
                f"Текст:\n<code>{text_to_check[:300]}</code>"
            )
        return