"""
groq_client.py — Groq API integration for the phishing simulation.

Two uses:
  1. GroqExtractor — fast, cache-first 9-cue extraction (drop-in for OllamaExtractor,
     but much faster and higher quality via a 70B model on Groq's inference API).
  2. generate_phishing() — expand the synthetic phishing corpora (plain_llm / hybrid_vtriad)
     for the research dataset.

Ethics/scope: this is an authorized academic capstone studying phishing SUSCEPTIBILITY
for defensive purposes (security training / risk analysis). Generation produces
GENERIC, synthetic samples for the research dataset — fictional entities only, no real
brands, people, domains, or working credential-harvesting links. It does not target real
individuals and nothing is deployed.

Setup: add your key to .env  ->  GROQ_API_KEY=gsk_...
"""

import ast
import hashlib
import json
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

VALID_CUES = [
    "urgency", "threats", "generic_greeting", "spelling_grammar",
    "emotional_appeal", "too_good_true", "personal_info",
    "suspicious_sender", "suspicious_link",
]

# Extraction default: llama-4-scout is fast, clean JSON, and has a workable free-tier
# budget. llama-3.3-70b-versatile gives similar quality but its free daily token cap is
# small — it 429s partway through a full corpus, so do NOT use it as the bulk default.
DEFAULT_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
GEN_MODEL = "llama-3.3-70b-versatile"   # generation only (few calls) — best writing quality


def _key() -> str:
    return os.getenv("GROQ_API_KEY", "").strip()


def _client():
    from groq import Groq
    return Groq(api_key=_key())


def is_available() -> bool:
    """True if a key is set and the API answers."""
    if not _key():
        return False
    try:
        _client().chat.completions.create(
            model=DEFAULT_MODEL, max_tokens=5,
            messages=[{"role": "user", "content": "ping"}],
        )
        return True
    except Exception as e:
        print(f"  [groq] not available: {type(e).__name__}: {str(e)[:120]}")
        return False


# ---------------------------------------------------------------------------
# Cue extraction (cache-first; same interface as OllamaExtractor)
# ---------------------------------------------------------------------------
_EXTRACT_PROMPT = """You are a phishing email security analyst. Identify which phishing cues are present in the email.
Return ONLY a JSON array using cue names from this exact list:
["urgency","threats","generic_greeting","spelling_grammar","emotional_appeal","too_good_true","personal_info","suspicious_sender","suspicious_link"]
Definitions:
- urgency: pressures immediate action ("act now","expires today","within 24 hours")
- threats: negative consequences ("account suspended","legal action","service blocked")
- generic_greeting: impersonal opener ("Dear Customer","Hello User")
- spelling_grammar: obvious spelling/grammar errors
- emotional_appeal: strong emotion ("congratulations","you've been selected","urgent plea")
- too_good_true: unrealistic reward ("you won","free gift","$1000 prize")
- personal_info: requests sensitive data ("enter your password","confirm SSN","bank account")
- suspicious_sender: spoofed/mismatched sender domain
- suspicious_link: URL shorteners, odd TLDs, brand-mismatch domains
Only flag cues CLEARLY present. Return [] if none. Output ONLY the JSON array.

Email:
Subject: {subject}
From: {sender}
Body:
{body}
URLs: {urls}"""

_BATCH_PROMPT = """You are a phishing email security analyst. For EACH of the {n} emails below, identify which phishing cues are present.
Valid cue names (use EXACTLY these): ["urgency","threats","generic_greeting","spelling_grammar","emotional_appeal","too_good_true","personal_info","suspicious_sender","suspicious_link"]
Definitions:
- urgency: pressures immediate action ("act now","expires today")
- threats: negative consequences ("account suspended","legal action")
- generic_greeting: impersonal opener ("Dear Customer")
- spelling_grammar: obvious spelling/grammar errors
- emotional_appeal: strong emotion ("congratulations","you've been selected")
- too_good_true: unrealistic reward ("you won","free gift")
- personal_info: requests sensitive data ("enter password","confirm SSN")
- suspicious_sender: spoofed/mismatched sender domain
- suspicious_link: URL shorteners, odd TLDs, brand-mismatch domains
Only flag cues CLEARLY present. Legitimate business email usually has NONE.

Return ONLY a JSON array of exactly {n} arrays — element i is the cue list for EMAIL i, in order. Use [] for an email with no cues. No prose.

{emails}"""


class GroqExtractor:
    """Cache-first cue extractor backed by the Groq API. Mirrors OllamaExtractor."""

    # min_interval is a coarse floor only. The REAL throttle is the token-per-minute pacer
    # in llm_providers: Groq's binding limit is 30K tokens/min, and a request-count gap
    # cannot express that (a 4K-token batch every 50ms is 4.8M tokens/min).
    def __init__(self, model: str = DEFAULT_MODEL, cache_dir: str = "data/cue_cache_v2",
                 min_interval: float = 0.05):
        self.model = model
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval = min_interval
        self._last = 0.0
        self._cli = None
        self._last_provider = None

    def is_available(self) -> bool:
        return is_available()

    def _cache_path(self, email_id) -> Path:
        return self.cache_dir / f"email_{email_id}.json"

    def _cache_key(self, subject, body) -> Path:
        """Cache by CONTENT hash, not email_id.

        email_id is positional: adding a source renumbers the corpus and every cached
        entry would then map to a different email — silently serving wrong cues. Hashing
        the content makes the cache immune to composition changes and reusable across runs.
        """
        blob = re.sub(r"\s+", " ", f"{subject}\n{body}".lower()).strip()
        h = hashlib.md5(blob.encode("utf-8", "ignore")).hexdigest()
        return self.cache_dir / f"cue_{h}.json"

    def _rate(self):
        dt = time.time() - self._last
        if dt < self.min_interval:
            time.sleep(self.min_interval - dt)
        self._last = time.time()

    def extract(self, email_id, subject, sender, body, urls) -> list:
        cp = self._cache_path(email_id)
        if cp.exists():
            return json.loads(cp.read_text())
        cues = self._call(subject, sender, body, urls)
        cp.write_text(json.dumps(cues))
        return cues

    def extract_batch(self, emails_df, batch_size: int = 10) -> dict:
        """Cache-first, BATCHED extraction (many emails per API call) — far fewer
        requests, so Groq's rate limit is not the bottleneck. Any batch that fails
        to parse falls back to per-email extraction, so results are never dropped."""
        # NOTE: the API client is created lazily inside _call/_call_batch, so a fully
        # cached corpus needs no key, no network and not even the `groq` package.
        results, todo = {}, []
        for _, row in emails_df.iterrows():
            eid = row["email_id"]
            cp = self._cache_key(row.get("subject", ""), row.get("body", ""))
            if cp.exists():
                results[eid] = json.loads(cp.read_text())
            else:
                todo.append(row)
        total = len(todo)
        print(f"  [groq extract] {len(results)} cached, {total} to extract (batched x{batch_size})", flush=True)
        for i in range(0, total, batch_size):
            batch = todo[i:i + batch_size]
            for row, cues in zip(batch, self._call_batch(batch)):
                self._cache_key(row.get("subject", ""), row.get("body", "")).write_text(json.dumps(cues))
                results[row["email_id"]] = cues
            if (i // batch_size) % 5 == 0 or i + batch_size >= total:
                print(f"  [groq extract] {min(i + batch_size, total)}/{total}", flush=True)
        return results

    def _call_batch(self, batch) -> list:
        """Return a list of cue-lists aligned to `batch`. Falls back to per-email
        extraction if the batched JSON response is malformed or the wrong length."""
        parts = []
        for j, row in enumerate(batch):
            body = str(row.get("body", "") or "")[:1500]
            parts.append(f"### EMAIL {j}\nSubject: {row.get('subject','')}\nFrom: {row.get('sender','')}\nBody: {body}")
        prompt = _BATCH_PROMPT.format(n=len(batch), emails="\n\n".join(parts))
        self._rate()
        try:
            # Route through the multi-provider chain (groq -> gemini -> nvidia -> ...).
            # A single free tier WILL exhaust mid-run; falling through keeps the run alive.
            from .llm_providers import complete
            text, used = complete(prompt, max_tokens=60 * len(batch) + 120, temperature=0.1)
            if used != self._last_provider:
                print(f"  [extracting via {used}]", flush=True)
                self._last_provider = used
            s, e = text.find("["), text.rfind("]") + 1
            parsed = json.loads(text[s:e])
            if isinstance(parsed, list) and len(parsed) == len(batch):
                return [[c for c in (item or []) if c in VALID_CUES] for item in parsed]
            print(f"  [groq batch: len {len(parsed) if isinstance(parsed,list) else '?'} != {len(batch)} -> fallback]", flush=True)
        except Exception as ex:
            print(f"  [groq batch err -> fallback] {type(ex).__name__}: {str(ex)[:80]}", flush=True)
        return [self._call(str(r.get("subject", "")), str(r.get("sender", "")),
                           str(r.get("body", ""))[:2000], "") for r in batch]

    def _call(self, subject, sender, body, urls) -> list:
        url_str = ", ".join(urls) if isinstance(urls, list) else str(urls or "none")
        prompt = _EXTRACT_PROMPT.format(subject=subject or "(none)", sender=sender or "(none)",
                                        body=(body or "")[:2500], urls=url_str or "none")
        self._rate()
        try:
            from .llm_providers import complete
            text, _used = complete(prompt, max_tokens=80, temperature=0.1)
            text = text.strip()
            s, e = text.find("["), text.rfind("]") + 1
            if s == -1 or e == 0:
                return []
            try:
                parsed = json.loads(text[s:e])
                return [c for c in parsed if c in VALID_CUES]
            except json.JSONDecodeError:
                return [c for c in re.findall(r'"([^"]+)"', text[s:e]) if c in VALID_CUES]
        except Exception as ex:
            # NEVER return [] on an API error. An empty result gets written to the cache and
            # is then indistinguishable from a genuine "no cues found" — silently corrupting
            # the corpus (this is exactly what a mid-run 429 did). Fail loudly instead.
            raise RuntimeError(
                f"Groq extraction FAILED ({type(ex).__name__}: {str(ex)[:150]}). model={self.model}. "
                f"Nothing was cached. Fix the cause or switch model — do not accept empty cues."
            ) from ex


# ---------------------------------------------------------------------------
# Synthetic phishing generation (research dataset)
# ---------------------------------------------------------------------------
_SCENARIOS = [
    "IT password / account verification", "HR policy or payroll update",
    "package delivery / shipping notice", "invoice / payment request",
    "cloud storage / shared document", "security alert / unusual sign-in",
    "benefits enrollment / tax form", "software license renewal",
    "meeting invite / calendar update", "expense reimbursement",
]

_PLAIN_PROMPT = """You are generating SYNTHETIC phishing emails for an academic phishing-awareness research dataset.
These are OBVIOUS, naive phishing emails a spam filter should easily catch — they should contain clear red flags:
urgency ("act now"), threats ("account will be suspended"), a generic greeting ("Dear Customer"), an occasional
spelling error, and a suspicious link (a URL shortener like bit.ly or an odd TLD like .xyz). Use FICTIONAL company
names and generic senders — NO real brands, real people, or real domains.

Generate {n} DISTINCT such emails, varied across these themes: {themes}.
Return ONLY a JSON array; each element: {{"subject": "...", "sender": "name@fake-domain.tld", "body": "...", "expected_cues": ["urgency", ...]}}.
Bodies 60-140 words. Output ONLY the JSON array."""

_VTRIAD_PROMPT = """You are generating SYNTHETIC spear-phishing emails for an academic phishing-awareness research dataset.
These are SOPHISTICATED emails that look like legitimate internal corporate communications, using the V-Triad persuasion
framework (Visceral emotion, Tribal in-group trust, Danger/authority) with MINIMAL obvious red flags — corporate tone,
plausible internal context, no spelling errors, no blatant urgency or lottery language. They should read like a real
IT/HR/Finance notification. Use FICTIONAL company names and generic internal senders — NO real brands, people, or domains.

Generate {n} DISTINCT such emails, varied across these themes: {themes}.
Return ONLY a JSON array; each element: {{"subject": "...", "sender": "name@fake-company.com", "body": "...", "expected_cues": [...], "vtriad_tactic": "visceral|tribal|danger"}}.
Bodies 70-160 words, professional and subtle. Output ONLY the JSON array."""


def generate_phishing(style: str, n: int, model: str = GEN_MODEL,
                      batch_size: int = 10, temperature: float = 0.9, seed: int = 0) -> list:
    """Generate `n` synthetic phishing emails. style in {'plain_llm','hybrid_vtriad'}."""
    assert style in ("plain_llm", "hybrid_vtriad")
    prompt_tpl = _PLAIN_PROMPT if style == "plain_llm" else _VTRIAD_PROMPT
    cli = _client()
    out, batch_i = [], 0
    while len(out) < n:
        k = min(batch_size, n - len(out))
        themes = ", ".join(_SCENARIOS[(batch_i * 3) % len(_SCENARIOS):][:5]) or ", ".join(_SCENARIOS[:5])
        prompt = prompt_tpl.format(n=k, themes=themes)
        try:
            resp = cli.chat.completions.create(
                model=model, temperature=temperature, max_tokens=3000,
                messages=[{"role": "system", "content": f"Deterministic-ish batch #{batch_i} (seed {seed})."},
                          {"role": "user", "content": prompt}],
            )
            text = resp.choices[0].message.content
            s, e = text.find("["), text.rfind("]") + 1
            arr = json.loads(text[s:e])
            for item in arr:
                if isinstance(item, dict) and item.get("body"):
                    out.append(item)
            print(f"  [groq gen {style}] {len(out)}/{n}")
        except Exception as ex:
            print(f"  [groq gen err] {type(ex).__name__}: {str(ex)[:120]}")
        batch_i += 1
        if batch_i > n:   # safety
            break
    return out[:n]


def save_generated(rows: list, source: str, out_dir: str = "data/raw") -> Path:
    """Save generated emails to a segregated raw CSV (id/subject/sender/body/expected_cues)."""
    import pandas as pd
    df = pd.DataFrame(rows)
    df.insert(0, "id", range(1, len(df) + 1))
    for col in ["subject", "sender", "body"]:
        if col not in df:
            df[col] = ""
    path = Path(out_dir) / f"{source}_groq.csv"
    df.to_csv(path, index=False)
    print(f"  saved {len(df)} -> {path}")
    return path


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="check Groq availability")
    ap.add_argument("--gen", choices=["plain_llm", "hybrid_vtriad"])
    ap.add_argument("--n", type=int, default=100)
    args = ap.parse_args()
    if args.check:
        print("GROQ_API_KEY set:", bool(_key()), "| API reachable:", is_available())
    elif args.gen:
        rows = generate_phishing(args.gen, args.n)
        save_generated(rows, args.gen)
