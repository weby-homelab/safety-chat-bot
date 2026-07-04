import re
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from bot.database.models import BannedDomain, BannedKeyword

logger = logging.getLogger(__name__)

# Розширений список заборонених доменів (за замовчуванням)
BANNED_DOMAINS = {
    "scam.site", "free-crypto.io", "bit.ly", "tinyurl.com", 
    "t.me/crypto", "t.me/joinchat", "cutt.ly", "rb.gy",
    "is.gd", "t.co", "bit.do", "vk.cc", "rebrand.ly", "scam.link",
    "free-money.club", "cryptogive.io"
}

# Ключові слова для фільтрації спаму та російської агресії/ботів (за замовчуванням)
SPAM_KEYWORDS = [
    # 1. Spams & Scams (Ukrainian & Russian)
    r"виграш", r"выигрыш",
    r"безкоштовно", r"бесплатно",
    r"заробіток", r"заработок",
    r"дохід", r"доход",
    r"інвестиції", r"инвестиции",
    r"підписуйся", r"подпишись",
    r"робота вдома", r"работа на дому",
    r"швидкі гроші", r"быстрые деньги",
    r"акція", r"акция",
    r"продам", r"куплю",
    r"підробіток", r"подработка",
    r"вакансія", r"вакансия",
    r"переходи по посиланню", r"переходи по ссылке",
    r"слив схем", r"схемы заработка",
    r"казино", r"ставки", r"1xbet",
    r"пишите в лс", r"пишіть в лс",
    r"написать менеджеру", r"написати менеджеру",
    r"в день від", r"в день от",
    r"робота в інтернеті", r"работа в интернете",
    r"іщу співробітників", r"ищу сотрудников",

    # 2. Fake social payouts & charity scams (very high priority in UA chats)
    r"виплати від", r"виплати українцям", r"выплаты украинцам",
    r"грошова допомога", r"соцдопомога", r"соцвиплати", r"соцвыплаты",
    r"єпідтримка", r"еподдержка",
    r"компенсація від", r"компенсация от",
    r"допомога від оон", r"выплаты от оон",
    r"червоний хрест", r"красный крест",
    r"заявка на виплату", r"заявка на выплату",
    r"отримати виплату", r"получить выплату",

    # 3. Russian military propaganda, bot insults & hate speech
    r"хохлы", r"хохол", r"хохлов",
    r"укры", r"укроп", r"укропы", r"укропов",
    r"нацисты", r"нацики",
    r"зеленский", r"зеленского", r"зеля",
    r"бандеровцы", r"бандеры", r"салорейх",
    r"сво", r"путин", r"путина", r"россия", r"россии",
    r"лнр", r"днр", r"денацификация",
    r"малороссия", r"новороссия", r"крым наш", r"русский мир",
    r"кастрюли", r"ватники", r"вата",

    # 4. Russian IPSO, panic spreading, and TCC-related attacks (July 2026 update)
    r"бусификация", r"бусифікація", r"тцк штурмуют", r"облава тцк",
    r"выходим на улицы", r"перекрываем дороги", r"майдан 3",
    r"киевский regime", r"киевский режим", r"укрофашисты", r"нацистский режим", r"марионетка сша",
    r"отключают свет навсегда", r"тарифы геноцид"
]

DOMAIN_PATTERN = re.compile(r'https?://(?:www\.)?([^/\s]+)')
KEYWORDS_PATTERN = re.compile("|".join(SPAM_KEYWORDS), re.IGNORECASE)

PORN_SPAM_KEYWORDS = [
    r"sex", r"porn", r"nude", r"dating", r"onlyfans", r"webcam", r"escort", r"xxx",
    r"секс", r"порно", r"интим", r"інтим", r"знакомств", r"шлюх", r"девственниц", 
    r"проститут", r"сиськ", r"попк", r"эротик", r"еротик", r"минет", r"вирт", r"онлифанс",
    r"взаимные лайки", r"подписка на", r"слив фото", r"сливы"
]
PORN_KEYWORDS_PATTERN = re.compile("|".join(PORN_SPAM_KEYWORDS), re.IGNORECASE)
RTL_PATTERN = re.compile(r'[\u202e\u200f\u202b\u0600-\u06FF]')

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
            all_domains = {row[0].lower() for row in domains_result.all()}
            missing_domains = [d for d in BANNED_DOMAINS if d.lower() not in all_domains]
            if missing_domains:
                logger.info(f"Adding {len(missing_domains)} missing default banned domains to database...")
                for d in missing_domains:
                    session.add(BannedDomain(domain=d))
                await session.commit()
                # Reload all domains
                domains_result = await session.execute(select(BannedDomain.domain))
                DYNAMIC_BANNED_DOMAINS = {row[0].lower() for row in domains_result.all()}
            else:
                DYNAMIC_BANNED_DOMAINS = all_domains

            # Check and seed keywords
            keywords_result = await session.execute(select(BannedKeyword.keyword))
            all_keywords = {row[0].lower() for row in keywords_result.all()}
            missing_keywords = [k for k in SPAM_KEYWORDS if k.lower() not in all_keywords]
            if missing_keywords:
                logger.info(f"Adding {len(missing_keywords)} missing default spam keywords to database...")
                for k in missing_keywords:
                    session.add(BannedKeyword(keyword=k))
                await session.commit()
                # Reload all keywords
                keywords_result = await session.execute(select(BannedKeyword.keyword))
                DYNAMIC_SPAM_KEYWORDS = {row[0].lower() for row in keywords_result.all()}
            else:
                DYNAMIC_SPAM_KEYWORDS = all_keywords

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

def check_suspicious_profile(first_name: str, last_name: str | None, username: str | None) -> tuple[bool, str | None]:
    name_parts = [first_name]
    if last_name:
        name_parts.append(last_name)
    if username:
        name_parts.append(username)
        
    full_text = " ".join(name_parts)
    
    # 1. Перевірка на RTL/арабські символи
    if RTL_PATTERN.search(full_text):
        return True, "RTL or Arabic characters in profile name"
        
    # 2. Перевірка на порно-ключові слова
    if PORN_KEYWORDS_PATTERN.search(full_text):
        return True, "Porn/spam keywords in profile name"
        
    # 3. Перевірка нормалізованого імені на порно-ключові слова
    normalized_name = normalize_text(full_text)
    # Також нормалізуємо ключові слова
    normalized_porn_kws = [normalize_text(kw) for kw in PORN_SPAM_KEYWORDS]
    for kw in normalized_porn_kws:
        if kw and kw in normalized_name:
            return True, f"Normalized profile contains spam keyword: {kw}"
            
    return False, None
