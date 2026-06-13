import re
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from bot.database.models import BannedDomain, BannedKeyword

logger = logging.getLogger(__name__)

# Розширений список заборонених доменів (за замовчуванням)
BANNED_DOMAINS = {
    "scam.site", "free-crypto.io", "bit.ly", "tinyurl.com", 
    "t.me/crypto", "t.me/joinchat", "cutt.ly", "rb.gy"
}

# Ключові слова для фільтрації спаму (за замовчуванням)
SPAM_KEYWORDS = [
    r"виграш", r"выигрыш",
    r"крипта", r"криптовалюта",
    r"безкоштовно", r"бесплатно",
    r"заробіток", r"заработок",
    r"дохід", r"доход",
    r"інвестиції", r"инвестиции",
    r"підписуйся", r"подпишись",
    r"робота вдома", r"работа на дому",
    r"швидкі гроші", r"быстрые деньги",
    r"акція", r"акция",
    r"продам", r"куплю",
]

DOMAIN_PATTERN = re.compile(r'https?://(?:www\.)?([^/\s]+)')
KEYWORDS_PATTERN = re.compile("|".join(SPAM_KEYWORDS), re.IGNORECASE)

# Dynamic lists loaded from DB
DYNAMIC_BANNED_DOMAINS = set()
DYNAMIC_SPAM_KEYWORDS = set()
DYNAMIC_NORMALIZED_KEYWORDS = []
DYNAMIC_NORMALIZED_PATTERN = None

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    # Map common Latin lookalikes to Cyrillic
    homoglyphs = {
        'a': 'а', 'c': 'с', 'e': 'е', 'i': 'і', 'o': 'о', 'p': 'р', 'x': 'х', 'y': 'у',
        '3': 'з', '0': 'о', '1': 'і'
    }
    for lat, cyr in homoglyphs.items():
        text = text.replace(lat, cyr)
    # Remove whitespace, punctuation, and bypass noise characters
    text = re.sub(r'[\s\-_*.,!?()\[\]{}|\\/@#+=~`%^&;:\'"<>?₴$€№]', '', text)
    return text

NORMALIZED_SPAM_KEYWORDS = [normalize_text(kw) for kw in SPAM_KEYWORDS]
NORMALIZED_KEYWORDS_PATTERN = re.compile("|".join(NORMALIZED_SPAM_KEYWORDS), re.IGNORECASE)

async def load_dynamic_blacklists(session_pool: async_sessionmaker[AsyncSession]):
    global DYNAMIC_BANNED_DOMAINS, DYNAMIC_SPAM_KEYWORDS, DYNAMIC_NORMALIZED_KEYWORDS, DYNAMIC_NORMALIZED_PATTERN
    try:
        async with session_pool() as session:
            # Check and seed domains
            domains_result = await session.execute(select(BannedDomain.domain))
            all_domains = [row[0] for row in domains_result.all()]
            if not all_domains:
                logger.info("Seeding default banned domains to database...")
                for d in BANNED_DOMAINS:
                    session.add(BannedDomain(domain=d))
                await session.commit()
                DYNAMIC_BANNED_DOMAINS = {d.lower() for d in BANNED_DOMAINS}
            else:
                DYNAMIC_BANNED_DOMAINS = {d.lower() for d in all_domains}

            # Check and seed keywords
            keywords_result = await session.execute(select(BannedKeyword.keyword))
            all_keywords = [row[0] for row in keywords_result.all()]
            if not all_keywords:
                logger.info("Seeding default spam keywords to database...")
                for k in SPAM_KEYWORDS:
                    session.add(BannedKeyword(keyword=k))
                await session.commit()
                DYNAMIC_SPAM_KEYWORDS = {k.lower() for k in SPAM_KEYWORDS}
            else:
                DYNAMIC_SPAM_KEYWORDS = {k.lower() for k in all_keywords}

            # Compile dynamic pattern
            DYNAMIC_NORMALIZED_KEYWORDS = [normalize_text(k) for k in DYNAMIC_SPAM_KEYWORDS]
            if DYNAMIC_NORMALIZED_KEYWORDS:
                DYNAMIC_NORMALIZED_PATTERN = re.compile("|".join(DYNAMIC_NORMALIZED_KEYWORDS), re.IGNORECASE)
            else:
                DYNAMIC_NORMALIZED_PATTERN = None
                
            logger.info(f"Loaded {len(DYNAMIC_BANNED_DOMAINS)} domains and {len(DYNAMIC_SPAM_KEYWORDS)} keywords into cache.")
    except Exception as e:
        logger.error(f"Error loading dynamic blacklists from database: {e}")
        # Fallback to static lists in case of DB failure
        DYNAMIC_BANNED_DOMAINS = {d.lower() for d in BANNED_DOMAINS}
        DYNAMIC_SPAM_KEYWORDS = {k.lower() for k in SPAM_KEYWORDS}
        DYNAMIC_NORMALIZED_PATTERN = NORMALIZED_KEYWORDS_PATTERN

def check_fast_heuristics(text: str) -> bool:
    if not text:
        return False
        
    text_lower = text.lower()
    
    # Mask whitelisted domains to prevent false positives with generic TLD blocks (.top, .online)
    text_for_domains = text_lower
    for whitelist in ["srvrs.top", "srvrs.online"]:
        text_for_domains = text_for_domains.replace(whitelist, "[whitelist]")
    
    # 1. Перевірка за доменами (static + dynamic)
    for banned in BANNED_DOMAINS:
        if banned in text_for_domains:
            return True
    for banned in DYNAMIC_BANNED_DOMAINS:
        if banned in text_for_domains:
            return True
            
    # 2. Перевірка за посиланнями на канали
    if any(banned in text_lower for banned in ["t.me/+", "t.me/joinchat"]):
        return True

    # 3. Перевірка за ключовими словами на сирому тексті
    if KEYWORDS_PATTERN.search(text_lower):
        return True
    if DYNAMIC_NORMALIZED_PATTERN and DYNAMIC_NORMALIZED_PATTERN.search(text_lower):
        return True
        
    # 4. Перевірка за ключовими словами на нормалізованому тексті
    normalized_text = normalize_text(text_lower)
    if NORMALIZED_KEYWORDS_PATTERN.search(normalized_text):
        return True
    if DYNAMIC_NORMALIZED_PATTERN and DYNAMIC_NORMALIZED_PATTERN.search(normalized_text):
        return True
        
    return False
