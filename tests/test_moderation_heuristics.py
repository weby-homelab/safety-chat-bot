import pytest
from bot.services.moderation import (
    check_fast_heuristics,
    clean_and_normalize,
    deobfuscate_spaced_letters,
    check_domains_and_links,
    compile_keywords_pattern,
)

def test_reported_user_false_positives():
    """
    Перевірка реальних випадків помилкового блокування у чаті,
    наведених користувачем. Жодне з цих повідомлень НЕ повинно блокуватись!
    """
    reported_messages = [
        # Tori (04/11/2026 9:06) - раніше блокувалось через 'доход' у 'доходить'
        "Сусід знизу сказав, що в них вода є, то мабудь на гору вона не доходить",
        # Tori (04/11/2026 9:07) - раніше блокувалось через 'доход' у 'доходить'
        "В нас внизу є вода, на гору не доходить",
        # Анна (07/11/2026 8:16) - раніше блокувалось через склеювання 'у Вас воно' -> 'васвоно' -> 'сво'
        "Повезло що у Вас воно хоть було",
        # Рома (08/11/2026 14:35) - раніше блокувалось через склеювання 'у нас в одній' -> 'унасводній' -> 'сво'
        "Так це від стояка залежить)) у нас в одній кімнаті були гаражі, а в інших двох і кухня холодні",
    ]

    for msg in reported_messages:
        assert not check_fast_heuristics(msg), f"False positive on legitimate message: {msg}"

def test_legitimate_everyday_conversations():
    """
    Перевірка поширених побутових повідомлень мешканців будинку,
    які раніше могли помилково викликати спрацювання евристик.
    """
    legit_messages = [
        "Ми вже ванну 2 рази прийняли. В нас водичка є",
        "Яка реакція керуючої компанії на нашу заяву?",
        "У нас у під'їзді нова фракція прихильників ОСББ",
        "Хтось возив дітей до школи на машині?",
        "У нас вологий підвал, треба кликати сантехніка",
        "Дякую, все доходить вчасно і працює",
        "Холодна вода є, а гаряча зникла",
        "Ми все зробили. Рух ліфтів відновлено",
        "До нас в офіс прийшли майстри",
        "Якось в обід зустрінемось біля під'їзду",
    ]

    for msg in legit_messages:
        assert not check_fast_heuristics(msg), f"False positive on legit message: {msg}"

def test_obfuscated_spam_detection():
    """
    Перевірка де-обфускації та виявлення спаму, коли спамери
    намагаються розривати літери пробілами або розділовими знаками.
    """
    spam_cases = [
        # СВО з пробілами та крапками
        "Учасники с . в . о отримують виплати",
        "с в о продовжується на фронті",
        "с_в_о герої росії",
        # Казино з розірваними літерами
        "найкраще к а з и н о 777 для виграшу",
        "ставки на спорт 1 x b e t онлайн",
        # Прямий спам та російська пропаганда
        "гарантований щоденний доход від 1000$ в день",
        "термінові виплати від оон для всіх українців",
        "продам новий диван дешево",
        "бусифікація триває на вулицях",
        "хохлы здавайтесь",
        "салорейх скоро впаде",
        "киевский режим обманює народ",
    ]

    for msg in spam_cases:
        assert check_fast_heuristics(msg), f"Failed to detect spam: {msg}"

def test_deobfuscate_spaced_letters_preserves_words():
    """
    Перевіряє, що deobfuscate_spaced_letters склеює ТІЛЬКИ поодинокі символи,
    але НЕ склеює слова довжиною >= 2.
    """
    # Склеює розірвані літери
    assert "сво" in deobfuscate_spaced_letters("с . в . о")
    assert "казино" in deobfuscate_spaced_letters("к а з и н о")
    assert "1xbet" in deobfuscate_spaced_letters("1 x b e t")

    # Зберігає слова та пробіли
    assert deobfuscate_spaced_letters("у вас воно") == "у вас воно"
    assert deobfuscate_spaced_letters("у нас в одній") == "у нас в одній"
    assert deobfuscate_spaced_letters("в нас водичка є") == "в нас водичка є"

def test_domain_filtering_and_whitelisting():
    """
    Перевірка фільтрації доменів, білого списку та прихованих посилань.
    """
    # Заборонені скам-домени
    assert check_fast_heuristics("заходьте на сайт https://scam.site/win")
    assert check_fast_heuristics("безкоштовні гроші на free-crypto.io")
    assert check_fast_heuristics("вступайте у канал https://t.me/+AbCdEf123")

    # Приховані посилання через extra_urls (entities)
    assert check_fast_heuristics("Неймовірні новини тут!", extra_urls=["https://t.me/+secretinvite"])
    assert check_fast_heuristics("Знижки тут", extra_urls=["https://bit.ly/scam123"])

    # Дозволені домени з білого списку
    assert not check_fast_heuristics("посилання на наш сервіс https://srvrs.top/status")
    assert not check_fast_heuristics("офіційний сайт https://weby.guru/about")
    assert not check_fast_heuristics("код бота відкритий на https://github.com/weby-homelab/safety-chat-bot")

def test_word_boundary_compiler():
    """
    Перевірка коректності компіляції шаблонів з межами слів.
    """
    pattern = compile_keywords_pattern(["доход", "акція", "сво"])
    assert pattern is not None

    # Повинно матчити окремі слова
    assert pattern.search("пасивний доход")
    assert pattern.search("це сво!")
    assert pattern.search("велика акція")

    # НЕ повинно матчити підрядки всередині інших слів
    assert not pattern.search("вода доходить до поверху")
    assert not pattern.search("хімічна реакція")
    assert not pattern.search("нова фракція")
    assert not pattern.search("повезло що у вас воно хоть було")
