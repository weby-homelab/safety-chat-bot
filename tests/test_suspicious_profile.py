import pytest
from bot.services.moderation import check_suspicious_profile

def test_legit_profile():
    # Звичайний легітимний профіль
    is_susp_1, reason_1 = check_suspicious_profile("Іван", "Іванов", "ivan_ua")
    assert not is_susp_1
    assert reason_1 is None

    is_susp_2, reason_2 = check_suspicious_profile("Alex", None, "alex_dev")
    assert not is_susp_2
    assert reason_2 is None

def test_porn_keywords():
    # Ім'я з порно-словами
    is_susp_1, reason_1 = check_suspicious_profile("Hot Sex Girl", None, None)
    assert is_susp_1
    assert "Porn/spam keywords" in reason_1

    is_susp_2, reason_2 = check_suspicious_profile("Знакомства Ірина", None, None)
    assert is_susp_2
    assert "Normalized profile contains spam keyword" in reason_2 or "Porn/spam keywords" in reason_2

def test_rtl_characters():
    # Ім'я з арабською в'яззю або RTL символами
    is_susp_1, reason_1 = check_suspicious_profile("محمد", None, None)
    assert is_susp_1
    assert "RTL or Arabic" in reason_1

    is_susp_2, reason_2 = check_suspicious_profile("John\u202eDoe", None, None)
    assert is_susp_2
    assert "RTL or Arabic" in reason_2

def test_homoglyphs_and_normalization():
    # Обхід через латинські літери (омогліфи) або розділювачі
    is_susp_1, reason_1 = check_suspicious_profile("С_е_к_с", None, None)
    assert is_susp_1
    assert "Normalized profile contains spam keyword" in reason_1

    # Заміна літери e (кирилична) на e (латинська) у слові секс
    is_susp_2, reason_2 = check_suspicious_profile("сeкс", None, None) # e - латинська
    assert is_susp_2
    assert "Normalized profile contains spam keyword" in reason_2
