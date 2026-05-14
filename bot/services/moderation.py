import re
from bot.services.ai import AIService

# Fast heuristic first level
BANNED_DOMAINS = {"scam.site", "free-crypto.io"}
DOMAIN_PATTERN = re.compile(r'https?://(?:www\.)?([^/\s]+)')

def check_fast_heuristics(text: str) -> bool:
    domains = DOMAIN_PATTERN.findall(text.lower())
    for d in domains:
        if d in BANNED_DOMAINS:
            return True # Is spam
    return False

async def analyze_with_ai(ai_service: AIService, text: str) -> bool:
    prompt = f"Does this text contain severe toxicity or phishing? Reply ONLY 'YES' or 'NO'. Text: {text}"
    response = await ai_service.model.generate_content_async(prompt)
    return "YES" in response.text.upper()