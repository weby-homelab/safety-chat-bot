import os
import aiohttp
import logging

logger = logging.getLogger(__name__)

async def send_admin_notification(text: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN_ADMIN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID_ADMIN")
    if not token or not chat_id:
        logger.warning("Admin notifications skipped: TELEGRAM_BOT_TOKEN_ADMIN or TELEGRAM_CHAT_ID_ADMIN not set in environment.")
        return
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    resp_text = await response.text()
                    logger.error(f"Failed to send admin notification: {response.status} {resp_text}")
    except Exception as e:
        logger.error(f"Failed to send admin notification: {e}")
