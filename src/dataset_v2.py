"""
dataset_v2.py — Reproducible assembly of the EXPANDED master dataset.

Non-destructive: writes data/processed/master_emails_v2.csv and never touches the
original 250-row master_emails.csv. Sources are kept clearly segregated by the
`source` column. Re-runnable as new emails are added (more ham via Kaggle, more
LLM phishing via Groq).

Key fix over v1: the Phishbowl raw records prefix each real phish with Cornell's
IT *warning* boilerplate ("This phish typically originates from... Do not reply...").
That anti-phishing language pollutes cue extraction. Here we strip the warning
notice <div> (recovering the spoofed sender from it first) and keep only the real
phish body.
"""

import ast
import hashlib
import html
import re
from pathlib import Path

import pandas as pd

RAW = Path("data/raw")
OUT = Path("data/processed/master_emails_v2.csv")

_URL = re.compile(r'https?://[^\s<>"\')]+')
_NOTICE_DIV = re.compile(r'<div[^>]*dialog-notice[^>]*>.*?</div>', re.S | re.I)
_TAG = re.compile(r'<[^>]+>')
_EMAIL = re.compile(r'[\w.\-]+@[\w.\-]+\.[A-Za-z]{2,}')
_WARN_WORDS = re.compile(r'this phish|do not reply|not a legitimate|beware of|report this', re.I)


def _strip_html(s: str) -> str:
    s = html.unescape(str(s))
    s = _TAG.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def extract_urls(body: str) -> list:
    return _URL.findall(body or "")


def clean_phishbowl(min_body_chars: int = 40) -> pd.DataFrame:
    """Load raw phishbowl (240), strip Cornell warning boilerplate, recover spoofed
    sender, keep the real phish body. Returns normalized rows (drops unusable ones)."""
    df = pd.read_csv(RAW / "phishbowl.csv")
    rows = []
    for _, r in df.iterrows():
        raw_msg = str(r.get("email_message", ""))
        subject = str(r.get("title", "")).strip()

        # Recover the spoofed sender from the warning notice before removing it.
        notice_match = _NOTICE_DIV.search(raw_msg)
        sender = ""
        if notice_match:
            notice_txt = _strip_html(notice_match.group(0))
            m = _EMAIL.search(notice_txt)
            if m:
                sender = m.group(0)

        # Remove the warning notice div, then strip remaining HTML -> real phish body.
        body = _strip_html(_NOTICE_DIV.sub(" ", raw_msg))
        # Edge case: a few records keep residual warning text; drop the leading warning sentence.
        if _WARN_WORDS.search(body[:200]):
            # cut at the first "Dear"/"The "/"Hello"/"Hi " that starts the real email
            m = re.search(r'\b(Dear |Hello |Hi |Greetings|We |You |Your |The )', body)
            if m and m.start() > 30:
                body = body[m.start():]

        if len(body) < min_body_chars:
            continue
        if not sender:
            sender = "unknown@external-sender.com"
        rows.append({"subject": subject, "sender": sender, "body": body,
                     "source": "phishbowl", "actual_class": 1})
    return pd.DataFrame(rows)


def _load_simple(path: Path, source: str, actual_class: int) -> pd.DataFrame:
    """Load one of the already-normalized raw CSVs (id/subject/sender/body)."""
    df = pd.read_csv(path)
    out = pd.DataFrame({
        "subject": df.get("subject", "").astype(str),
        "sender": df.get("sender", "").astype(str) if "sender" in df else "",
        "body": df.get("body", "").astype(str),
        "source": source,
        "actual_class": actual_class,
    })
    return out


def load_ham(path: Path = None) -> pd.DataFrame:
    p = path or (RAW / "spamassassin_ham_100.csv")
    return _load_simple(p, "spamassassin_ham", 0)


_HAM_DIRS = ["easy_ham/easy_ham", "hard_ham/hard_ham"]


def parse_spamassassin_ham(n: int = 300, seed: int = 42,
                           root: Path = RAW / "spamassassin_full") -> pd.DataFrame:
    """Parse RFC822 messages from the full SpamAssassin public corpus (easy_ham +
    hard_ham; spam_2 is excluded — it is spam, not benign). Returns a normalized,
    randomly-sampled ham DataFrame. Falls back to the 100-row CSV if the corpus
    is not downloaded."""
    import email, glob, os, random
    from email import policy

    files = []
    for sub in _HAM_DIRS:
        for f in glob.glob(str(root / sub / "*")):
            if os.path.isfile(f) and "__MACOSX" not in f and not os.path.basename(f).startswith("."):
                files.append(f)
    if not files:
        print("  [ham] full corpus not found — using the 100-row CSV")
        return load_ham()

    random.Random(seed).shuffle(files)
    rows = []
    for f in files:
        if len(rows) >= n:
            break
        try:
            with open(f, "rb") as fh:
                msg = email.message_from_binary_file(fh, policy=policy.default)
            frm = str(msg.get("from") or "").strip()
            subj = str(msg.get("subject") or "").strip()
            body = ""
            b = msg.get_body(preferencelist=("plain",))
            if b:
                body = b.get_content()
            body = re.sub(r"\s+", " ", str(body)).strip()
            if len(body) < 40:
                continue
            rows.append({"subject": subj, "sender": frm, "body": body[:4000],
                         "source": "spamassassin_ham", "actual_class": 0})
        except Exception:
            continue
    print(f"  [ham] parsed {len(rows)} benign emails from the full SpamAssassin corpus")
    return pd.DataFrame(rows)


def load_plain_llm(path: Path = None) -> pd.DataFrame:
    """Base naive-LLM phishing plus any Groq-generated additions (segregated file)."""
    dfs = [_load_simple(path or (RAW / "plain_llm_phishing.csv"), "plain_llm", 1)]
    g = RAW / "plain_llm_groq.csv"
    if g.exists():
        dfs.append(_load_simple(g, "plain_llm", 1))
    return pd.concat(dfs, ignore_index=True)


def load_hybrid_vtriad(path: Path = None) -> pd.DataFrame:
    """Base V-Triad phishing plus any Groq-generated additions (segregated file)."""
    dfs = [_load_simple(path or (RAW / "hybrid_vtriad_phishing.csv"), "hybrid_vtriad", 1)]
    g = RAW / "hybrid_vtriad_groq.csv"
    if g.exists():
        dfs.append(_load_simple(g, "hybrid_vtriad", 1))
    return pd.concat(dfs, ignore_index=True)


def assemble(ham=None, phishbowl=None, plain_llm=None, hybrid_vtriad=None,
             out: Path = OUT) -> pd.DataFrame:
    """Assemble the expanded master. Any source can be passed pre-loaded (e.g. an
    expanded ham or freshly-generated LLM set); omitted sources load from raw."""
    parts = [
        ham if ham is not None else parse_spamassassin_ham(300),
        phishbowl if phishbowl is not None else clean_phishbowl(),
        plain_llm if plain_llm is not None else load_plain_llm(),
        hybrid_vtriad if hybrid_vtriad is not None else load_hybrid_vtriad(),
    ]
    df = pd.concat(parts, ignore_index=True)
    df = df[df["body"].astype(str).str.len() >= 20].reset_index(drop=True)
    df = dedupe_bodies(df)
    df.insert(0, "email_id", range(1, len(df) + 1))
    df["extracted_urls"] = df["body"].apply(lambda b: str(extract_urls(b)))
    df = df[["email_id", "subject", "sender", "body", "extracted_urls", "source", "actual_class"]]
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return df


# ===========================================================================
# Vetted expansion sources (real phishing + clean benign) — see DATA_PROVENANCE.md
# ===========================================================================
_KAGGLE_DIR = RAW / "phishing_email_dataset"
_KAGGLE_FILES = {"nazario": "Nazario.csv", "ceas08": "CEAS_08.csv", "nigerian_fraud": "Nigerian_Fraud.csv"}
_JUNK_RE = re.compile(
    r'internal format of your mail folder|DON.?T DELETE THIS MESSAGE|FOLDER INTERNAL DATA|MAILER-DAEMON',
    re.I)


def load_kaggle_phishing(which: str, n: int = None, seed: int = 42,
                         min_chars: int = 40, max_chars: int = 6000) -> pd.DataFrame:
    """Real, human-authored phishing from the naserabdullahalam Kaggle bundle
    (Nazario / CEAS_08 / Nigerian_Fraud). Filters to label==1, drops mbox junk rows,
    normalizes to the master schema, and seeded-samples to `n`."""
    path = _KAGGLE_DIR / _KAGGLE_FILES[which]
    if not path.exists():
        print(f"  [{which}] not downloaded — skipping"); return pd.DataFrame()
    df = pd.read_csv(path)
    if "label" in df.columns:
        df = df[df["label"] == 1]
    rows = []
    for _, r in df.iterrows():
        body = str(r.get("body", "") or "")
        sender = str(r.get("sender", "") or "")
        if _JUNK_RE.search(body[:500]) or _JUNK_RE.search(sender):
            continue
        body = re.sub(r"\s+", " ", body).strip()[:max_chars]
        if len(body) < min_chars:
            continue
        rows.append({"subject": str(r.get("subject", "") or "").strip(),
                     "sender": sender.strip(), "body": body,
                     "source": which, "actual_class": 1})
    out = pd.DataFrame(rows)
    if n and len(out) > n:
        out = out.sample(n=n, random_state=seed).reset_index(drop=True)
    print(f"  [{which}] {len(out)} real phishing emails")
    return out


def load_enron_clean(n: int = 250, seed: int = 42,
                     min_chars: int = 40, max_chars: int = 6000) -> pd.DataFrame:
    """Benign corporate email from the pre-parsed HF corbt/enron-emails dataset
    (from/subject/body). Fetched at runtime and cached by huggingface_hub. Returns
    an empty frame if HF is unreachable (SpamAssassin then carries the benign class)."""
    try:
        from huggingface_hub import hf_hub_download
        p = hf_hub_download("corbt/enron-emails", "data/train-00000-of-00003.parquet", repo_type="dataset")
        e = pd.read_parquet(p, columns=["from", "subject", "body"])
    except Exception as ex:
        # LOUD on purpose. Skipping here does not error — it silently yields a corpus 200
        # benign emails smaller, so two machines produce different results from identical
        # code and neither looks broken. Missing huggingface_hub/pyarrow is the usual cause.
        print(f"\n  !! [enron_clean] UNAVAILABLE ({type(ex).__name__}: {str(ex)[:60]})\n"
              f"  !! Corpus will be built WITHOUT 200 benign enron emails — results will\n"
              f"  !! NOT match a run where this source loads. Fix with:\n"
              f"  !!     pip install -r requirements.txt\n", flush=True)
        return pd.DataFrame()
    e = e.sample(n=min(len(e), n * 8), random_state=seed)
    rows = []
    for _, r in e.iterrows():
        body = re.sub(r"\s+", " ", str(r.get("body", "") or "")).strip()[:max_chars]
        if len(body) < min_chars:
            continue
        rows.append({"subject": str(r.get("subject", "") or "").strip(),
                     "sender": str(r.get("from", "") or "").strip(), "body": body,
                     "source": "enron_clean", "actual_class": 0})
        if len(rows) >= n:
            break
    print(f"  [enron_clean] {len(rows)} benign emails")
    return pd.DataFrame(rows)


def load_multi_llm(n: int = 150, seed: int = 42,
                   min_chars: int = 40, max_chars: int = 6000) -> pd.DataFrame:
    """Modern multi-model AI phishing — GPT-4.1 / DeepSeek-3.2 / Llama-3.3-70b — from the
    Cross-model corpus (Zenodo 10.5281/zenodo.20250116, CC BY 4.0, "for defensive security
    research"). Sampled evenly across the three generating models.

    Only the LLM half is ingested; the corpus's human half is drawn from CEAS-08 / Nazario /
    Nigerian-Fraud / Enron and would duplicate sources already present.

    KNOWN LIMITATION: this corpus ships no sender field, so the `suspicious_sender` cue can
    never fire for these emails — their cue count is therefore not perfectly comparable with
    sources that do carry senders. Recorded in DATA_PROVENANCE.md.
    """
    if n <= 0:
        return pd.DataFrame()
    p = RAW / "multi_llm" / "data" / "llm_corpus_sampled.csv"
    if not p.exists():
        print("  [multi_llm] not downloaded — skipping"); return pd.DataFrame()
    d = pd.read_csv(p)
    per = max(1, n // max(1, d["model"].nunique()))
    d = d.groupby("model", group_keys=False).apply(
        lambda g: g.sample(min(len(g), per), random_state=seed))
    rows = []
    for _, r in d.iterrows():
        body = re.sub(r"\s+", " ", str(r.get("body", "") or "")).strip()[:max_chars]
        if len(body) < min_chars:
            continue
        rows.append({"subject": str(r.get("subject", "") or "").strip(), "sender": "",
                     "body": body, "source": "multi_llm", "actual_class": 1})
    out = pd.DataFrame(rows)
    print(f"  [multi_llm] {len(out)} modern AI phishing emails (3 models)")
    return out


def load_trec07_ham(n: int = 150, seed: int = 42,
                    min_chars: int = 40, max_chars: int = 6000) -> pd.DataFrame:
    """Benign half of the TREC 2007 public corpus (Zenodo 10.5281/zenodo.8339691, CC BY 4.0).
    A third benign source (2007-era mail) for false-positive diversity, and a named, citable
    benchmark — IWSPA-AP 2018, the usual choice, is registration-only and effectively dead.

    The TREC spam half is DELIBERATELY EXCLUDED: spam is not targeted phishing, and labelling
    it `actual_class=1` would corrupt the construct this simulation measures.
    """
    p = RAW / "trec07" / "TREC_07.csv"
    if not p.exists():
        print("  [trec07_ham] not downloaded — skipping"); return pd.DataFrame()
    d = pd.read_csv(p, usecols=["sender", "subject", "body", "label"])
    d = d[d["label"].astype(str).str.strip() == "0"]
    d = d.sample(min(len(d), n * 4), random_state=seed)
    rows = []
    for _, r in d.iterrows():
        body = re.sub(r"\s+", " ", str(r.get("body", "") or "")).strip()[:max_chars]
        if len(body) < min_chars:
            continue
        rows.append({"subject": str(r.get("subject", "") or "").strip(),
                     "sender": str(r.get("sender", "") or "").strip(),
                     "body": body, "source": "trec07_ham", "actual_class": 0})
        if len(rows) >= n:
            break
    out = pd.DataFrame(rows)
    print(f"  [trec07_ham] {len(out)} benign emails (TREC-07 benchmark)")
    return out


def dedupe_bodies(df: pd.DataFrame) -> pd.DataFrame:
    """Drop exact/near-duplicate emails across all sources on a normalized body hash."""
    def _h(b):
        return hashlib.md5(re.sub(r"\s+", " ", str(b).lower()).strip().encode("utf-8", "ignore")).hexdigest()
    before = len(df)
    df = df.assign(_bh=df["body"].map(_h)).drop_duplicates("_bh").drop(columns="_bh").reset_index(drop=True)
    if before != len(df):
        print(f"  [dedupe] removed {before - len(df)} duplicate bodies")
    return df


def build_target_corpus(seed: int = 42, out: Path = OUT, ham_n: int = 500, enron_n: int = 250,
                        ceas_n: int = 250, nazario_n: int = 150, nigerian_n: int = 100,
                        phishbowl_cap: int = None, plain_cap: int = None,
                        vtriad_cap: int = None, multi_llm_n: int = 150,
                        trec07_n: int = 150) -> pd.DataFrame:
    """Assemble the full vetted expansion corpus from every source, deduped.
    Sources stay segregated by `source`. Composition matches the research plan."""
    def _cap(df, n):
        return df.sample(n=n, random_state=seed).reset_index(drop=True) if (n and len(df) > n) else df
    parts = [
        parse_spamassassin_ham(ham_n, seed=seed),
        load_enron_clean(enron_n, seed=seed),
        load_trec07_ham(trec07_n, seed=seed),
        load_kaggle_phishing("ceas08", ceas_n, seed=seed),
        load_kaggle_phishing("nazario", nazario_n, seed=seed),
        load_kaggle_phishing("nigerian_fraud", nigerian_n, seed=seed),
        _cap(clean_phishbowl(), phishbowl_cap),
        _cap(load_plain_llm(), plain_cap),
        _cap(load_hybrid_vtriad(), vtriad_cap),
        load_multi_llm(multi_llm_n, seed=seed),
    ]
    parts = [p for p in parts if p is not None and len(p)]
    df = pd.concat(parts, ignore_index=True)
    df = df[df["body"].astype(str).str.len() >= 20].reset_index(drop=True)
    df = dedupe_bodies(df)
    df.insert(0, "email_id", range(1, len(df) + 1))
    df["extracted_urls"] = df["body"].apply(lambda b: str(extract_urls(b)))
    df = df[["email_id", "subject", "sender", "body", "extracted_urls", "source", "actual_class"]]
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return df


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", action="store_true", help="build the full vetted expansion corpus")
    args = ap.parse_args()
    df = build_target_corpus() if args.target else assemble()
    print(f"\nwrote {OUT}  ({len(df)} emails)")
    print(df.groupby(["source", "actual_class"]).size().to_string())
