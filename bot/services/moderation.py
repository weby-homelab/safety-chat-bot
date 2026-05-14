import re

# Fast heuristic first level
BANNED_DOMAINS = {"scam.site", "free-crypto.io"}
DOMAIN_PATTERN = re.compile(r'https?://(?:www\.)?([^/\s]+)')

def check_fast_heuristics(text: str) -> bool:
    domains = DOMAIN_PATTERN.findall(text.lower())
    for d in domains:
        if d in BANNED_DOMAINS:
            return True # Is spam
    return False