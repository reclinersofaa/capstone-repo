"""
Ollama-based cue extractor — uses a locally-running LLM via Ollama.

Drop-in replacement for CueExtractor when Gemini quota is exhausted.
Requires Ollama running at http://localhost:11434 with a model pulled.

Recommended models for this machine (RTX 4060 Ti 16GB):
  llama3.1:8b  — default; already pulled, good instruction following (~3–5s/call)
  qwen2.5:7b   — better JSON adherence if pulled (ollama pull qwen2.5:7b)
  gemma2:9b    — best overall quality for JSON tasks if pulled

Setup:
  1. Install Ollama: https://ollama.com
  2. Model already pulled: llama3.1:8b
  3. Confirm running: ollama list

To force re-extraction from scratch (recommended after switching extractors):
  1. Delete data/cue_cache/  (or selectively delete files you want re-extracted)
  2. Re-run the simulation cell with RERUN=True
"""

import ast
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

VALID_CUES = [
    "urgency",
    "threats",
    "generic_greeting",
    "spelling_grammar",
    "emotional_appeal",
    "too_good_true",
    "personal_info",
    "suspicious_sender",
    "suspicious_link",
]

_PROMPT = """\
You are a phishing email security analyst. Your job is to identify phishing cues present in the email below.

Return ONLY a valid JSON array using cue names from this exact list:
["urgency", "threats", "generic_greeting", "spelling_grammar", "emotional_appeal", "too_good_true", "personal_info", "suspicious_sender", "suspicious_link"]

Cue definitions:
- urgency: pressures reader to act immediately ("act now", "expires today", "within 24 hours")
- threats: warns of negative consequences ("account suspended", "legal action", "service blocked")
- generic_greeting: impersonal opener ("Dear Customer", "Hello User", "To Whom It May Concern")
- spelling_grammar: contains obvious spelling errors or unnatural grammar
- emotional_appeal: triggers strong emotion ("congratulations!", "you've been selected", "urgent plea")
- too_good_true: unrealistic reward language ("you won", "free gift", "$1000 prize", "lottery winner")
- personal_info: requests sensitive data explicitly ("enter your password", "confirm SSN", "bank account number")
- suspicious_sender: sender domain looks spoofed or mismatched (paypa1.com, amaz0n-security.net)
- suspicious_link: URL shorteners (bit.ly), odd TLDs (.tk, .xyz), or brand-mismatch in domain

Rules:
- Only flag cues that are CLEARLY present. Do not guess.
- Return [] if no cues are found.
- Output ONLY the JSON array — no explanation, no markdown.

Email:
Subject: {subject}
From: {sender}
Body:
{body}
URLs found: {urls}
"""


class OllamaExtractor:
    """
    Extracts phishing cues using a locally-running Ollama LLM.
    Cache-first: results are written to data/cue_cache/email_{id}.json
    and reused on subsequent calls (same interface as CueExtractor).
    """

    def __init__(
        self,
        model: str = "llama3.1:8b",
        cache_dir: str = "data/cue_cache",
        endpoint: str = "http://localhost:11434/api/generate",
        min_interval: float = 0.3,
        timeout: int = 60,
    ):
        self.model = model
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.endpoint = endpoint
        self.min_interval = min_interval
        self.timeout = timeout
        self._last_call_at = 0.0

    # ------------------------------------------------------------------
    # Public interface (mirrors CueExtractor)
    # ------------------------------------------------------------------

    def extract(self, email_id, subject: str, sender: str, body: str, urls) -> list[str]:
        """
        Return list of cue names present in the email.
        Checks disk cache first; calls Ollama only on a cache miss.
        """
        cache_path = self._cache_path(email_id)
        if cache_path.exists():
            return json.loads(cache_path.read_text())

        cues = self._call_ollama(subject, sender, body, urls)
        cache_path.write_text(json.dumps(cues))
        return cues

    def extract_batch(self, emails_df) -> dict:
        """
        Extract cues for every row in a DataFrame.
        Returns {email_id: [cues]} dict. Prints progress every 25 emails.
        """
        results = {}
        total = len(emails_df)

        for i, (_, row) in enumerate(emails_df.iterrows()):
            eid = row["email_id"]

            urls = row.get("extracted_urls", "")
            if isinstance(urls, str) and urls.startswith("["):
                try:
                    urls = ast.literal_eval(urls)
                except Exception:
                    urls = []

            results[eid] = self.extract(
                email_id=eid,
                subject=str(row.get("subject", "")),
                sender=str(row.get("sender", "")),
                body=str(row.get("body", "")),
                urls=urls,
            )

            if (i + 1) % 25 == 0 or (i + 1) == total:
                newly = sum(1 for k, v in results.items()
                            if not (self._cache_path(k).stat().st_size > 0
                                    and json.loads(self._cache_path(k).read_text()) == v))
                print(f"  [{i+1}/{total}] processed (model={self.model})")

        return results

    def is_available(self) -> bool:
        """Returns True if Ollama is reachable and the chosen model is present."""
        try:
            req = urllib.request.Request(
                "http://localhost:11434/api/tags",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            models = [m["name"] for m in data.get("models", [])]
            # Accept both "qwen2.5:7b" and "qwen2.5" style names
            base = self.model.split(":")[0]
            return any(self.model in m or base in m for m in models)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cache_path(self, email_id) -> Path:
        return self.cache_dir / f"email_{email_id}.json"

    def _rate_limit(self):
        elapsed = time.time() - self._last_call_at
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call_at = time.time()

    def _call_ollama(self, subject: str, sender: str, body: str, urls) -> list[str]:
        url_str = ", ".join(urls) if isinstance(urls, list) else str(urls or "none")
        prompt = _PROMPT.format(
            subject=subject or "(none)",
            sender=sender or "(none)",
            body=(body or "")[:2000],   # cap tokens — keeps inference fast
            urls=url_str or "none",
        )

        payload = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,   # low temperature for deterministic JSON
                "num_predict": 64,    # cue array is short, don't need more
            },
        }).encode()

        self._rate_limit()
        try:
            req = urllib.request.Request(
                self.endpoint,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read())

            text = data.get("response", "").strip()

            # Parse JSON array from response — model may add preamble or skip commas
            start = text.find("[")
            end = text.rfind("]") + 1
            if start == -1 or end == 0:
                return []

            raw_array = text[start:end]

            # First try standard parse
            try:
                parsed = json.loads(raw_array)
                if isinstance(parsed, list):
                    return [c for c in parsed if c in VALID_CUES]
            except json.JSONDecodeError:
                pass

            # Fallback: extract quoted strings manually (handles missing commas)
            import re
            found = re.findall(r'"([^"]+)"', raw_array)
            return [c for c in found if c in VALID_CUES]

        except urllib.error.URLError:
            print(f"  [!] Ollama not reachable at {self.endpoint} — returning []")
            return []
        except json.JSONDecodeError as e:
            print(f"  [!] JSON parse error from Ollama: {e}")
            return []
        except Exception as e:
            print(f"  [!] Ollama error: {e}")
            return []
