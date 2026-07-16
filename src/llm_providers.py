"""
llm_providers.py — multi-provider LLM access with automatic fallback.

WHY THIS EXISTS
---------------
Cue extraction needs ~130 batched calls per full corpus run. Relying on a single free
tier is fragile: during development Groq's llama-3.3-70b exhausted its daily token cap
mid-run, then llama-4-scout hit its own 500K TPD ceiling. A single provider WILL stall
eventually — so try several in order and fall through on rate-limit.

Nearly every free provider exposes an OpenAI-compatible /chat/completions endpoint, so
one code path (raw HTTP, no extra SDK) covers all of them. Add a provider = add a row.

SETUP — put any of these in .env; the chain uses whichever are present, in order:
    GROQ_API_KEY       console.groq.com/keys            (fast; per-model daily token caps)
    GEMINI_KEY         aistudio.google.com/app/apikey   (free; large daily request budget)
    NVIDIA_API_KEY     build.nvidia.com                 (no advertised daily cap)
    MISTRAL_API_KEY    console.mistral.ai/api-keys      (monthly, not daily, budget)
    CEREBRAS_API_KEY   cloud.cerebras.ai                (1M tokens/day but only ~5 RPM)

Limits below are as advertised at time of writing and are NOT guarantees — verify in each
console. They are recorded so the fallback ORDER has a stated rationale.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import deque

from dotenv import load_dotenv

load_dotenv()

# Ordered best-first. Rationale for the order:
#   groq     — fastest by far; use while its per-model token budget lasts
#   gemini   — large daily request budget; OpenAI-compat layer; strong JSON adherence
#   nvidia   — no advertised DAILY cap, which is exactly the failure mode that bit us
#   mistral  — monthly budget (structurally unlikely to die mid-run)
#   cerebras — big token budget but ~5 RPM, so it is a slow last resort
PROVIDERS = [
    # tpm: TOKENS-per-minute ceiling, measured from x-ratelimit-limit-tokens. This — not
    # the daily cap — is what actually kills a bulk run: batches are ~4K tokens, so firing
    # them back-to-back exceeds 30K/min within seconds and every call 429s.
    {"name": "groq", "env": "GROQ_API_KEY",
     "base": "https://api.groq.com/openai/v1",
     "model": "meta-llama/llama-4-scout-17b-16e-instruct",
     "tpm": 30000,
     "limits": "30K TPM (binding), 1000 RPD; per-model TPD 3.6K–500K (scout 500K)"},
    {"name": "gemini", "env": "GEMINI_KEY",
     "base": "https://generativelanguage.googleapis.com/v1beta/openai",
     "model": "gemini-2.5-flash",
     "limits": "free tier; ~15 RPM / ~1500 RPD (verify in AI Studio)"},
    {"name": "nvidia", "env": "NVIDIA_API_KEY",
     "base": "https://integrate.api.nvidia.com/v1",
     "model": "meta/llama-3.3-70b-instruct",
     "limits": "~40 RPM; no advertised daily cap"},
    {"name": "mistral", "env": "MISTRAL_API_KEY",
     "base": "https://api.mistral.ai/v1",
     "model": "mistral-small-latest",
     "limits": "free tier; monthly token budget"},
    {"name": "cerebras", "env": "CEREBRAS_API_KEY",
     "base": "https://api.cerebras.ai/v1",
     # NOT gpt-oss-120b or zai-glm-4.7: both are reasoning-only here and return a
     # message with no "content" field, so extraction silently yields nothing.
     # gemma-4-31b is the only model on this key that returns plain JSON.
     "model": "gemma-4-31b",
     "limits": "1M TPD but ~5 RPM — slow fallback only"},
]


class AllProvidersFailed(RuntimeError):
    """Every configured provider refused. Never returns empty output — see groq_client."""


class _TokenPacer:
    """Rolling 60-second token-budget throttle.

    WHY: a 429 from a tokens-per-minute limit means "wait ~12s", NOT "this provider is
    dead" — but the old code treated every 429 as death and fell through to the next
    provider, so a healthy Groq looked exhausted four batches into every run. Pacing
    under the TPM ceiling means we mostly never see the 429 at all.
    """

    def __init__(self, tpm: int, margin: float = 0.85):
        self.budget = int(tpm * margin)  # headroom: our token estimate is approximate
        self.events = deque()            # (timestamp, tokens)

    def acquire(self, tokens: int, verbose: bool = False):
        while True:
            now = time.time()
            while self.events and now - self.events[0][0] > 60.0:
                self.events.popleft()
            used = sum(t for _, t in self.events)
            if not self.events or used + tokens <= self.budget:
                self.events.append((now, tokens))
                return
            wait = 60.0 - (now - self.events[0][0]) + 0.25
            if verbose:
                print(f"  [pacing: {used:,}+{tokens:,} would exceed {self.budget:,} TPM "
                      f"— waiting {wait:.1f}s]", flush=True)
            time.sleep(max(wait, 0.25))


_PACERS = {p["name"]: _TokenPacer(p["tpm"]) for p in PROVIDERS if p.get("tpm")}


def _est_tokens(prompt: str, max_tokens: int) -> int:
    """Rough but deliberately generous — undercounting causes the 429 we're avoiding."""
    return int(len(prompt) / 3.2) + max_tokens


def _retry_after(e) -> float:
    """Seconds to wait, read from the response. Groq sends `retry-after` and/or
    `x-ratelimit-reset-tokens` in forms like '12.283s', '1m30s', '3h7m12s'."""
    ra = (e.headers.get("retry-after") or "").strip()
    if ra:
        try:
            return min(float(ra), 90.0)
        except ValueError:
            pass
    raw = (e.headers.get("x-ratelimit-reset-tokens")
           or e.headers.get("x-ratelimit-reset-requests") or "").strip()
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", raw)
    if m and any(m.groups()):
        h, mi, s = m.groups()
        total = int(h or 0) * 3600 + int(mi or 0) * 60 + float(s or 0)
        return min(total + 0.25, 90.0)  # cap: a multi-hour reset is a real cap, not a blip
    return 5.0


def _key(env: str) -> str:
    return (os.getenv(env) or "").strip()


def _is_placeholder(k: str) -> bool:
    """.env templates ship values like ENTER_YOUR_KEY_HERE. Treating one as a real key
    costs a failed round-trip on EVERY call (this is exactly what GEMINI_KEY was doing)."""
    u = k.upper()
    return (not k) or any(s in u for s in ("ENTER_", "YOUR_", "_HERE", "XXX", "CHANGEME", "<"))


def available() -> list:
    """Providers with a usable (non-placeholder) key, in fallback order."""
    return [p for p in PROVIDERS if not _is_placeholder(_key(p["env"]))]


def status() -> str:
    lines = ["provider      key          model                                   limits"]
    for p in PROVIDERS:
        k = _key(p["env"])
        state = "--         " if not k else ("PLACEHOLDER" if _is_placeholder(k) else "set        ")
        lines.append(f"  {p['name']:<11} {state}  {p['model']:<38} {p['limits']}")
    return "\n".join(lines)


def _post(provider: dict, prompt: str, max_tokens: int, temperature: float, timeout: int,
          verbose: bool = False) -> str:
    pacer = _PACERS.get(provider["name"])
    if pacer:
        pacer.acquire(_est_tokens(prompt, max_tokens), verbose=verbose)
    payload = json.dumps({
        "model": provider["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        provider["base"].rstrip("/") + "/chat/completions", data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {_key(provider['env'])}",
                 # Groq sits behind Cloudflare, which returns 403 (code 1010) to requests
                 # with no User-Agent. Every provider accepts this header.
                 "User-Agent": "capstone-phishing-sim/2.0"},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    msg = data["choices"][0]["message"]
    text = msg.get("content") or ""
    if not text.strip():
        raise ValueError("empty content (model may be reasoning-only)")
    return text


def complete(prompt: str, max_tokens: int = 800, temperature: float = 0.1,
             timeout: int = 90, verbose: bool = True, retries_429: int = 4) -> tuple:
    """Try each configured provider in order. Returns (text, provider_name).

    Raises AllProvidersFailed if every one refuses — we never silently return empty
    output, because an empty cue list is indistinguishable from 'no cues found' and
    would corrupt the corpus.
    """
    chain = available()
    if not chain:
        raise AllProvidersFailed(
            "No LLM provider configured. Add at least one key to .env — "
            + ", ".join(p["env"] for p in PROVIDERS))
    errors = []
    for p in chain:
        # A 429 is usually a per-MINUTE limit ("wait ~12s"), not exhaustion. Retrying the
        # same provider is almost always right; falling through on the first 429 is what
        # made a healthy Groq look dead four batches into every run.
        for attempt in range(retries_429 + 1):
            try:
                return _post(p, prompt, max_tokens, temperature, timeout, verbose), p["name"]
            except urllib.error.HTTPError as e:
                body = ""
                try:
                    body = e.read().decode()[:160]
                except Exception:
                    pass
                if e.code == 429 and attempt < retries_429:
                    wait = _retry_after(e)
                    if verbose:
                        print(f"  [{p['name']} 429 — waiting {wait:.1f}s and retrying "
                              f"({attempt + 1}/{retries_429})]", flush=True)
                    time.sleep(wait)
                    continue
                errors.append(f"{p['name']}: HTTP {e.code} {body}")
                if verbose:
                    print(f"  [{p['name']} unavailable: HTTP {e.code}] -> falling through", flush=True)
                break
            except Exception as e:
                errors.append(f"{p['name']}: {type(e).__name__} {str(e)[:80]}")
                if verbose:
                    print(f"  [{p['name']} failed: {type(e).__name__}] -> falling through", flush=True)
                break
    raise AllProvidersFailed("All providers failed:\n  " + "\n  ".join(errors))


if __name__ == "__main__":
    print(status())
    print()
    chain = available()
    print("fallback chain:", " -> ".join(p["name"] for p in chain) if chain else "(none configured)")
    if chain:
        try:
            txt, used = complete('Reply with exactly: ["ok"]', max_tokens=16)
            print(f"live check via {used}: {txt.strip()[:60]!r}")
        except AllProvidersFailed as e:
            print("live check failed —", str(e)[:400])
