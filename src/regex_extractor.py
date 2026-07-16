"""
Regex-based cue extractor — fallback when Gemini API quota is exhausted.

Patterns ported directly from notebooks/02_pattern_testing.ipynb.
Produces the same 9-cue output schema as CueExtractor.
"""

import re
import ast
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Compiled patterns (from 02_pattern_testing.ipynb)
# ---------------------------------------------------------------------------

_SUSPICIOUS_SENDER = re.compile(
    r'paypa[l1]|amaz[o0]n|micr[o0]s[o0]ft|app[l1]e|g[o0]{2}g[l1]e|'
    r'netf[l1][i1]x|[1i][i1]nst[a4]gr[a4]m|[f]aceb[o0]{2}k',
    re.IGNORECASE,
)

_GENERIC_GREETING = re.compile(
    r'\b(dear\s+(customer|user|member|account\s*holder|valued\s*customer|client)|'
    r'hello\s+(user|customer|member)|greetings\s+dear|to\s+whom\s+it\s+may\s+concern)\b',
    re.IGNORECASE,
)

_MISSPELLINGS = re.compile(
    r'\b(verifiy|passwrod|recieve|occured|suspeneded|suspened|acount|'
    r'confrim|validat[ei]on|securty|accout|informaton|immediat[ei]ly|'
    r'activit[y]|unathorized|inconvienence|succesfully|temporarly)\b',
    re.IGNORECASE,
)

_HOMOGLYPH = re.compile(r'[0O]{3,}|[1Il]{3,}|[5S]{3,}|[8B]{3,}')

_URGENCY = re.compile(
    r'\b(urgent(ly)?|immediately|asap|right\s+away|without\s+delay|'
    r'act\s+now|expires?\s+(in|today|soon)|deadline|time[- ]sensitive|'
    r'don\'?t\s+(wait|delay)|last\s+chance|final\s+(notice|warning)|'
    r'within\s+\d+\s+hours?|respond\s+immediately)\b',
    re.IGNORECASE,
)

_THREATS = re.compile(
    r'\b(account\s+(will\s+be\s+)?(suspended|terminated|blocked|locked|'
    r'disabled|deactivated|closed)|access\s+(will\s+be\s+)?revoked|'
    r'legal\s+action|unauthorized\s+access|security\s+(breach|alert|warning)|'
    r'suspicious\s+activity|payment\s+(failed|declined|overdue)|'
    r'verify\s+(or|to\s+avoid)\s+(los|suspend|block))\b',
    re.IGNORECASE,
)

_EMOTIONAL = re.compile(
    r'\b(congratulations?|you\s+(have\s+)?(won|been\s+selected|been\s+chosen)|'
    r'winner|lucky|exclusive\s+(offer|access|invitation)|special\s+(offer|reward)|'
    r'urgent\s+help|help\s+needed|donation|assistance\s+required|'
    r'inheritance|beneficiary|million\s+dollars?)\b',
    re.IGNORECASE,
)

_TOO_GOOD = re.compile(
    r'\b(free\s+(gift|money|iphone|laptop|voucher|prize|reward)|'
    r'won\s+(a\s+)?\$|lottery|jackpot|cash\s+(prize|reward|back)|'
    r'gift\s+card|unclaimed\s+(funds|prize|reward)|'
    r'\$\s*\d{3,}|\d+\s*million|\bprize\b)\b',
    re.IGNORECASE,
)

_PERSONAL_INFO = re.compile(
    r'\b(enter\s+(your\s+)?(password|pin|ssn|social\s+security)|'
    r'provide\s+(your\s+)?(credit\s+card|bank\s+account|social\s+security)|'
    r'confirm\s+(your\s+)?(identity|details|information|password|account)|'
    r'social\s+security\s+number|credit\s+card\s+(number|details)|'
    r'bank\s+(account|details)|date\s+of\s+birth|mother\'?s\s+maiden|'
    r'security\s+question|update\s+(your\s+)?payment|billing\s+information)\b',
    re.IGNORECASE,
)

_URL_SHORTENERS = re.compile(
    r'bit\.ly|tinyurl\.com|goo\.gl|t\.co|ow\.ly|is\.gd|buff\.ly|'
    r'rebrand\.ly|short\.io|cutt\.ly',
    re.IGNORECASE,
)

_SUSPICIOUS_TLD = re.compile(
    r'\.(tk|ml|ga|cf|gq|xyz|top|click|link|online|site|info|biz|'
    r'work|loan|review|win|download|racing|accountant|cricket)(/|$)',
    re.IGNORECASE,
)

_BRAND_MISMATCH_KEYWORDS = re.compile(
    r'paypal|amazon|microsoft|apple|google|netflix|instagram|facebook|'
    r'ebay|dropbox|docusign|chase|wells\s*fargo|bank\s*of\s*america',
    re.IGNORECASE,
)

_ALLOWED_BRAND_DOMAINS = {
    'paypal.com', 'amazon.com', 'microsoft.com', 'apple.com', 'google.com',
    'netflix.com', 'instagram.com', 'facebook.com', 'ebay.com',
    'dropbox.com', 'docusign.com', 'chase.com', 'wellsfargo.com',
}

_EXTRACT_URLS = re.compile(r'https?://[^\s<>"\']+')


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _extract_urls(text: str) -> list[str]:
    return _EXTRACT_URLS.findall(text or '')


def _check_suspicious_sender(sender: str, body: str) -> bool:
    sender = sender or ''
    if not sender or sender == 'nan':
        return False
    # Typosquatted brand in domain part
    domain = sender.split('@')[-1] if '@' in sender else sender
    if _SUSPICIOUS_SENDER.search(domain):
        # Check if the domain is actually the legitimate brand domain
        for legit in _ALLOWED_BRAND_DOMAINS:
            if domain.lower().strip().endswith(legit):
                return False
        return True
    return False


def _check_suspicious_links(links: list[str], full_text: str) -> bool:
    if not links:
        return False
    for link in links:
        try:
            parsed = urlparse(link)
            host = parsed.netloc.lower()
            path = parsed.path.lower()

            # Shorteners
            if _URL_SHORTENERS.search(host):
                return True

            # Suspicious TLDs
            if _SUSPICIOUS_TLD.search(host + '/'):
                return True

            # Brand keyword in host but not the real domain
            if _BRAND_MISMATCH_KEYWORDS.search(host):
                is_legit = any(host.endswith(d) for d in _ALLOWED_BRAND_DOMAINS)
                if not is_legit:
                    return True

        except Exception:
            pass
    return False


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

VALID_CUES = [
    "urgency", "threats", "generic_greeting", "spelling_grammar",
    "emotional_appeal", "too_good_true", "personal_info",
    "suspicious_sender", "suspicious_link",
]


def extract_cues_regex(
    subject: str = '',
    sender: str = '',
    body: str = '',
    urls=None,
) -> list[str]:
    """
    Extract phishing cues using regex patterns.
    Returns a list of cue names (subset of VALID_CUES).
    """
    full_text = f"{subject or ''} {body or ''}"

    # Collect URLs from both the provided list and inline in body
    link_list: list[str] = []
    if isinstance(urls, list):
        link_list.extend(urls)
    elif isinstance(urls, str) and urls.startswith('['):
        try:
            link_list.extend(ast.literal_eval(urls))
        except Exception:
            pass
    link_list.extend(_extract_urls(body or ''))
    link_list = list(set(link_list))

    cues = []

    if _GENERIC_GREETING.search(full_text):
        cues.append('generic_greeting')

    if _URGENCY.search(full_text):
        cues.append('urgency')

    if _THREATS.search(full_text):
        cues.append('threats')

    if _EMOTIONAL.search(full_text):
        cues.append('emotional_appeal')

    if _TOO_GOOD.search(full_text):
        cues.append('too_good_true')

    if _PERSONAL_INFO.search(full_text):
        cues.append('personal_info')

    # Spelling: need 1+ known misspelling OR 3+ homoglyphs
    if _MISSPELLINGS.search(full_text):
        cues.append('spelling_grammar')
    elif len(_HOMOGLYPH.findall(full_text)) >= 3:
        cues.append('spelling_grammar')

    if _check_suspicious_sender(sender, body or ''):
        cues.append('suspicious_sender')

    if _check_suspicious_links(link_list, full_text):
        cues.append('suspicious_link')

    return cues
