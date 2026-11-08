import re
import logging
import unicodedata
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

# Домени білого списку (виключаються з перевірки TLD та підрядків)
WHITELISTED_DOMAINS = {
    "srvrs.top", "srvrs.online", "weby.guru", "github.com", "t.me"
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
DYNAMIC_KEYWORDS_PATTERN = None

def clean_and_normalize(text: str) -> str:
    """
    Нормалізує юнікод (NFKC), видаляє невидимі/RTL символи,
    переводить у нижній регістр та мапить латинські гомогліфи на кирилицю.
    Зберігає пробіли та межі слів.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\uFEFF]", "", text)
    text = text.lower()
    homoglyphs = {
        'a': 'а', 'c': 'с', 'e': 'е', 'i': 'і', 'o': 'о', 'p': 'р', 'x': 'х', 'y': 'у',
        '3': 'з', '0': 'о', '1': 'і', 'k': 'к', 'b': 'б', 'm': 'м', 'h': 'н', 't': 'т'
    }
    for lat, cyr in homoglyphs.items():
        text = text.replace(lat, cyr)
    return text

def deobfuscate_spaced_letters(text: str) -> str:
    """
    Виявляє спроби спамерів розірвати ключові слова через пробіли або розділові знаки
    (наприклад: 'с . в . о' -> 'сво', 'к а з и н о' -> 'казино', '1 x b e t' -> '1xbet').
    Повноцінні слова (довжина >= 2, такі як 'у вас воно' чи 'у нас в одній')
    зберігають свої пробіли та межі слів!
    """
    def replacer(match: re.Match) -> str:
        full = match.group(0)
        tokens = [t for t in re.split(r"[\s._\-*]+", full) if t]
        if all(len(t) == 1 for t in tokens):
            return "".join(tokens)
        return full
    return re.sub(r"\b[\wа-яёіїє](?:[\s._\-*]+[\wа-яёіїє])+\b", replacer, text)

def normalize_text(text: str) -> str:
    """
    Збереження зворотної сумісності normalize_text без втрати меж слів.
    """
    if not text:
        return ""
    cleaned = clean_and_normalize(text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return deobfuscate_spaced_letters(cleaned)

def compile_keywords_pattern(keywords: set[str] | list[str]) -> re.Pattern | None:
    """
    Компілює регулярний вираз для пошуку ключових слів з обов'язковими
    юнікод-межами слів (?<![a-zа-яёіїє0-9]) та (?![a-zа-яёіїє0-9]).
    """
    cleaned_kws = set()
    for kw in keywords:
        c = clean_and_normalize(kw).strip()
        if c:
            parts = [re.escape(p) for p in c.split()]
            cleaned_kws.add(r"\s+".join(parts))
    if not cleaned_kws:
        return None
    sorted_kws = sorted(cleaned_kws, key=len, reverse=True)
    joined = "|".join(sorted_kws)
    return re.compile(rf"(?<![a-zа-яёіїє0-9])(?:{joined})(?![a-zа-яёіїє0-9])", re.IGNORECASE)

# Static pattern compiled on import
STATIC_KEYWORDS_PATTERN = compile_keywords_pattern(SPAM_KEYWORDS)

async def load_dynamic_blacklists(session_pool: async_sessionmaker[AsyncSession]):
    global DYNAMIC_BANNED_DOMAINS, DYNAMIC_SPAM_KEYWORDS, DYNAMIC_KEYWORDS_PATTERN
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
                keywords_result = await session.execute(select(BannedKeyword.keyword))
                DYNAMIC_SPAM_KEYWORDS = {row[0].lower() for row in keywords_result.all()}
            else:
                DYNAMIC_SPAM_KEYWORDS = all_keywords

            # Compile dynamic pattern with word boundaries
            DYNAMIC_KEYWORDS_PATTERN = compile_keywords_pattern(DYNAMIC_SPAM_KEYWORDS)
            logger.info(f"Loaded {len(DYNAMIC_BANNED_DOMAINS)} domains and {len(DYNAMIC_SPAM_KEYWORDS)} keywords into cache.")
    except Exception as e:
        logger.error(f"Error loading dynamic blacklists from database: {e}")
        DYNAMIC_BANNED_DOMAINS = {d.lower() for d in BANNED_DOMAINS}
        DYNAMIC_SPAM_KEYWORDS = {k.lower() for k in SPAM_KEYWORDS}
        DYNAMIC_KEYWORDS_PATTERN = STATIC_KEYWORDS_PATTERN

def check_domains_and_links(text: str, extra_urls: list[str] | None = None) -> bool:
    """
    Перевіряє домени, TLD та посилання-запрошення у тексті та extra_urls (entities).
    """
    urls_to_check = list(extra_urls or [])
    url_pattern = re.compile(r"(?:https?://)?(?:[a-z0-9\-]+\.)+[a-z0-9\-]{2,}(?:/[^\s]*)?", re.IGNORECASE)
    for m in url_pattern.finditer(text or ""):
        urls_to_check.append(m.group(0))

    if text and any(inv in text.lower() for inv in ["t.me/+", "t.me/joinchat"]):
        return True

    for raw in urls_to_check:
        clean = raw.lower().strip()
        clean = re.sub(r"^https?://(?:www\.)?", "", clean)

        if any(inv in clean for inv in ["t.me/+", "t.me/joinchat"]):
            return True

        host = clean.split("/")[0].split(":")[0]

        if any(host == w or host.endswith("." + w) for w in WHITELISTED_DOMAINS):
            continue

        all_banned = BANNED_DOMAINS.union(DYNAMIC_BANNED_DOMAINS)
        for b in all_banned:
            b_clean = b.lower().strip()
            if b_clean.startswith("."):
                if host.endswith(b_clean):
                    return True
            elif host == b_clean or host.endswith("." + b_clean) or b_clean in clean:
                return True

    return False

def check_fast_heuristics(text: str, extra_urls: list[str] | None = None) -> bool:
    if not text and not extra_urls:
        return False

    # 1. Перевірка доменів та посилань
    if check_domains_and_links(text or "", extra_urls=extra_urls):
        return True

    if not text:
        return False

    # 2. Нормалізація тексту зі збереженням меж слів
    normalized_text = clean_and_normalize(text)
    deobfuscated_text = deobfuscate_spaced_letters(normalized_text)

    # 3. Перевірка статичних ключових слів з обов'язковими межами слів
    if STATIC_KEYWORDS_PATTERN:
        if STATIC_KEYWORDS_PATTERN.search(normalized_text) or STATIC_KEYWORDS_PATTERN.search(deobfuscated_text):
            return True

    # 4. Перевірка динамічних ключових слів з обов'язковими межами слів
    if DYNAMIC_KEYWORDS_PATTERN:
        if DYNAMIC_KEYWORDS_PATTERN.search(normalized_text) or DYNAMIC_KEYWORDS_PATTERN.search(deobfuscated_text):
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
    normalized_name = clean_and_normalize(full_text)
    deobfuscated_name = deobfuscate_spaced_letters(normalized_name)
    stripped_name = re.sub(r'[\s\-_*.,!?()\[\]{}|\\/@#+=~`%^&;:\'"<>?₴$€№]', '', normalized_name)

    for kw in PORN_SPAM_KEYWORDS:
        kw_clean = clean_and_normalize(kw).strip()
        if kw_clean:
            if kw_clean in normalized_name or kw_clean in deobfuscated_name or kw_clean in stripped_name:
                return True, f"Normalized profile contains spam keyword: {kw}"
            
    return False, None
