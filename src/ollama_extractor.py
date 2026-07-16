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
import hashlib
import json
import re
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
        cache_path = self._cache_path(subject, body)
        if cache_path.exists():
            return json.loads(cache_path.read_text())

        cues = self._call_ollama(subject, sender, body, urls)
        cache_path.write_text(json.dumps(cues))
        return cues

    def extract_batch(self, emails_df, batch_size: int = 8) -> dict:
        """
        Cache-first, BATCHED extraction (many emails per local model call) — fewer,
        larger calls keep the local GPU busy and cut wall-clock ~2x vs one-at-a-time.
        No external rate limits. Any batch that fails to parse falls back to per-email.
        """
        results, todo = {}, []
        for _, row in emails_df.iterrows():
            eid = row["email_id"]
            cp = self._cache_path(row.get("subject", ""), row.get("body", ""))
            if cp.exists():
                results[eid] = json.loads(cp.read_text())
            else:
                todo.append(row)
        total = len(todo)
        print(f"  [ollama extract] {len(results)} cached, {total} to extract "
              f"(batched x{batch_size}, model={self.model})", flush=True)
        for i in range(0, total, batch_size):
            batch = todo[i:i + batch_size]
            for row, cues in zip(batch, self._call_batch(batch)):
                self._cache_path(row.get("subject", ""), row.get("body", "")).write_text(json.dumps(cues))
                results[row["email_id"]] = cues
            if (i // batch_size) % 5 == 0 or i + batch_size >= total:
                print(f"  [ollama extract] {min(i + batch_size, total)}/{total}", flush=True)
        return results

    def _call_batch(self, batch) -> list:
        """Return a list of cue-lists aligned to `batch`; per-email fallback on failure."""
        from .groq_client import _BATCH_PROMPT
        parts = []
        for j, row in enumerate(batch):
            body = str(row.get("body", "") or "")[:1200]
            parts.append(f"### EMAIL {j}\nSubject: {row.get('subject','')}\nFrom: {row.get('sender','')}\nBody: {body}")
        prompt = _BATCH_PROMPT.format(n=len(batch), emails="\n\n".join(parts))
        payload = json.dumps({
            "model": self.model, "prompt": prompt, "stream": False,
            # think=False is REQUIRED for reasoning models (gemma4, qwen3, deepseek-r1).
            # Without it Ollama spends the whole num_predict budget on hidden reasoning
            # tokens, strips them from "response", and hands back an EMPTY STRING —
            # eval_count=270, done_reason='length', response=''. That looks identical to
            # "model can't do the task" and silently yields zero cues for every email.
            "think": False,
            "options": {"temperature": 0.1, "num_predict": 50 * len(batch) + 120},
        }).encode()
        self._rate_limit()
        try:
            req = urllib.request.Request(self.endpoint, data=payload,
                                         headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=self.timeout * 3) as resp:
                _data = json.loads(resp.read())
            text = _data.get("response", "")
            # Loud failure beats silent zeros: tokens generated but nothing returned means
            # the reasoning channel swallowed the output. Never let that become "no cues".
            if not text.strip() and _data.get("eval_count", 0) > 0:
                raise RuntimeError(
                    f"{self.model} generated {_data['eval_count']} tokens but returned an "
                    f"empty response (done_reason={_data.get('done_reason')!r}). Reasoning "
                    f"output was stripped — 'think': False must be sent for this model.")
            s, e = text.find("["), text.rfind("]") + 1
            parsed = json.loads(text[s:e])
            if isinstance(parsed, list) and len(parsed) == len(batch):
                return [[c for c in (item or []) if c in VALID_CUES] for item in parsed]
            print(f"  [ollama batch: len {len(parsed) if isinstance(parsed,list) else '?'} != {len(batch)} -> fallback]", flush=True)
        except Exception as ex:
            print(f"  [ollama batch err -> fallback] {type(ex).__name__}: {str(ex)[:80]}", flush=True)
        return [self._call_ollama(str(r.get("subject", "")), str(r.get("sender", "")),
                                  str(r.get("body", ""))[:2000], "") for r in batch]

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

    def _cache_path(self, subject, body) -> Path:
        """Key by CONTENT hash, not email_id.

        email_id is POSITIONAL: it is assigned by build_target_corpus() at assembly time,
        so adding or dropping a single source renumbers the entire corpus and every cached
        entry silently maps to a DIFFERENT email — wrong cues, no error. This is not
        hypothetical here: load_enron_clean() drops 200 emails when huggingface_hub/pyarrow
        are missing, which flips the corpus between 1,595 and 1,395 and shifts every id.

        Identical scheme to groq_client._cache_key(), so the same email produces the same
        filename under every extractor and the per-model cache dirs stay comparable.
        """
        blob = re.sub(r"\s+", " ", f"{subject}\n{body}".lower()).strip()
        return self.cache_dir / f"cue_{hashlib.md5(blob.encode('utf-8', 'ignore')).hexdigest()}.json"

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
            "think": False,           # see _call_batch — reasoning eats num_predict, returns ""
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
