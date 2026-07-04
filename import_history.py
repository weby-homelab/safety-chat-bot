import json
import asyncio
import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from bot.config import load_config
from bot.database.models import User, Chat, Base

# Налаштування логування
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

VALID_REACTIONS = {"🔥", "❤️", "❤", "👍", "👏", "🏆", "💯", "⚡️"}

async def import_history(json_path: str):
    if not os.path.exists(json_path):
        logger.error(f"File {json_path} not found!")
        return

    logger.info(f"Loading history from {json_path}...")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    messages = data.get("messages", [])
    logger.info(f"Found {len(messages)} messages. Processing reactions...")

    user_karma = {} # user_id -> {full_name, karma}
    
    for msg in messages:
        if msg.get("type") != "message":
            continue
        
        from_id = msg.get("from_id")
        if not from_id or not str(from_id).startswith("user"):
            continue
        
        user_id = int(str(from_id).replace("user", ""))
        full_name = msg.get("from", "Unknown User")
        username = None # JSON export might not have username in this field
        
        # Calculate karma for this message
        msg_karma = 0
        reactions = msg.get("reactions", [])
        for r in reactions:
            if r.get("emoji") in VALID_REACTIONS:
                msg_karma += r.get("count", 0)
        
        if msg_karma > 0:
            if user_id not in user_karma:
                user_karma[user_id] = {"full_name": full_name, "karma": 0}
            user_karma[user_id]["karma"] += msg_karma

    logger.info(f"Calculated karma for {len(user_karma)} users. Updating database...")

    # Load DB config
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    config = load_config()
    engine = create_async_engine(config.database_url.get_secret_value())
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with async_session() as session:
        for uid, info in user_karma.items():
            # Upsert user
            stmt = insert(User).values(
                id=uid, 
                full_name=info["full_name"],
                total_karma=info["karma"]
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=['id'],
                set_=dict(
                    full_name=info["full_name"],
                    total_karma=User.total_karma + info["karma"]
                )
            )
            await session.execute(stmt)
        
        await session.commit()
    
    logger.info("Import completed successfully!")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(import_history("result.json"))
