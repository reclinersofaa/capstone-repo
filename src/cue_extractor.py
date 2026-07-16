import json
import re
import time
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

load_dotenv()

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
You are a phishing email analyst. Read the email below and identify which phishing cues are present.

Return ONLY a valid JSON array of cue names chosen from this exact list:
["urgency", "threats", "generic_greeting", "spelling_grammar", "emotional_appeal", \
"too_good_true", "personal_info", "suspicious_sender", "suspicious_link"]

Definitions:
- urgency: pressures the reader to act immediately ("act now", "expires today", "last chance")
- threats: warns of negative consequences ("account suspended", "legal action", "access blocked")
- generic_greeting: impersonal opener ("Dear Customer", "Hello User", "Dear Account Holder")
- spelling_grammar: contains obvious spelling mistakes or grammatical errors
- emotional_appeal: triggers strong emotion ("congratulations", "you've been selected", "urgent help needed")
- too_good_true: unrealistic reward ("you won", "free gift", "$1000 prize", "lottery winner")
- personal_info: requests sensitive data ("enter your password", "confirm SSN", "credit card number")
- suspicious_sender: sender domain looks spoofed or mismatched (e.g. paypa1.com, amazn-services.net)
- suspicious_link: contains URL shorteners, odd TLDs (.tk, .xyz), or brand-mismatch domains

Rules:
- Only include cues that are clearly present in the text.
- Return [] if no cues are found.
- Do NOT include any explanation — only the JSON array.

Email:
Subject: {subject}
From: {sender}
Body:
{body}
URLs found: {urls}
"""


class CueExtractor:
    """
    Calls Gemini to extract phishing cues from an email.

    Results are cached to disk — re-running the simulation never re-calls the API
    for emails already processed.
    """

    def __init__(self, cache_dir: str = "data/cue_cache", min_interval: float = 1.0):
        self.client = genai.Client(api_key=os.environ["GEMINI_KEY"])
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._last_call_at = 0.0
        self.min_interval = min_interval  # seconds between API calls (stay inside free tier)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def extract(
        self,
        email_id,
        subject: str,
        sender: str,
        body: str,
        urls,
    ) -> list[str]:
        """
        Return list of cue names present in the email.
        Checks disk cache first; calls Gemini only on a cache miss.
        """
        cache_path = self._cache_path(email_id)
        if cache_path.exists():
            return json.loads(cache_path.read_text())

        cues = self._call_gemini(subject, sender, body, urls)
        cache_path.write_text(json.dumps(cues))
        return cues

    def extract_batch(self, emails_df) -> dict:
        """
        Extract cues for every row in a DataFrame.
        Returns {email_id: [cues]} dict.

        Prints progress every 25 emails.
        """
        import ast

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
                cached = sum(1 for r in results.values() if r is not None)
                print(f"  [{i+1}/{total}] cues extracted (cache hits included)")

        return results

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

    def _call_gemini(self, subject: str, sender: str, body: str, urls) -> list[str]:
        url_str = ", ".join(urls) if isinstance(urls, list) else str(urls or "none")
        prompt = _PROMPT.format(
            subject=subject or "(none)",
            sender=sender or "(none)",
            body=(body or "")[:1500],  # cap tokens
            urls=url_str or "none",
        )

        self._rate_limit()
        try:
            response = self.client.models.generate_content(
                model="models/gemini-2.5-flash",
                contents=prompt,
            )
            raw = response.text.strip()
            # Strip markdown code fences if the model wraps the array
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL).strip()
            cues = json.loads(raw)
            # Guard: only keep names from the approved list
            return [c for c in cues if c in VALID_CUES]

        except json.JSONDecodeError as e:
            print(f"  [!] JSON parse error: {e} — raw response: {raw!r}")
            return []
        except Exception as e:
            print(f"  [!] Gemini API error: {e}")
            return []
