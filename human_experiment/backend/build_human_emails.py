from pathlib import Path
import html
import re
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

MASTER = ROOT / "data" / "processed" / "master_emails_v2.csv"
RAW = ROOT / "data" / "raw"
OUT = ROOT / "human_experiment" / "data" / "human_emails.csv"


# ============================================================
# TEXT HELPERS
# ============================================================

def normalize(text):
    """
    Normalization used ONLY for matching.

    The original text is never modified by this function.
    """
    if pd.isna(text):
        return ""

    text = html.unescape(str(text))

    # Normalize whitespace for comparison only.
    text = re.sub(r"\s+", " ", text)

    return text.strip().lower()


def clean_display_body(text):
    """
    Convert a raw email into readable text.

    Formatting only:
      - HTML paragraphs -> blank lines
      - <br> -> newline
      - HTML tags removed
      - whitespace cleaned

    URLs remain plain text and are NOT converted into links.
    """

    if pd.isna(text):
        return ""

    text = html.unescape(str(text))

    # HTML line breaks
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)

    # HTML paragraphs
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<p[^>]*>", "", text, flags=re.I)

    # Remove remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Normalize line endings
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    lines = []

    for line in text.split("\n"):
        # Remove trailing whitespace
        line = line.rstrip()

        # Collapse spaces/tabs inside a line
        line = re.sub(r"[ \t]+", " ", line)

        lines.append(line)

    text = "\n".join(lines)

    # Prevent ridiculous blank-line runs
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    return text.strip()


def body_key(text):
    """
    Normalized body used for matching.
    """
    return normalize(text)


def subject_key(text):
    return normalize(text)


def sender_key(text):
    return normalize(text)


# ============================================================
# GENERIC INDEXING
# ============================================================

def add_record(index, source, subject, sender, body):
    """
    Add several matching keys for one raw email.

    This lets us progressively fall back from:
        subject + sender + body
    to:
        subject + body
    to:
        body
    """

    subject = "" if pd.isna(subject) else str(subject)
    sender = "" if pd.isna(sender) else str(sender)
    body = "" if pd.isna(body) else str(body)

    s = subject_key(subject)
    se = sender_key(sender)
    b = body_key(body)

    if not b:
        return

    raw = {
        "subject": subject,
        "sender": sender,
        "body": body,
    }

    # Strongest key
    if s and se:
        index.setdefault(
            (source, "ssb", s, se, b),
            []
        ).append(raw)

    # Subject + body
    if s:
        index.setdefault(
            (source, "sb", s, b),
            []
        ).append(raw)

    # Body only
    index.setdefault(
        (source, "b", b),
        []
    ).append(raw)


def load_csv(path):
    if not path.exists():
        print(f"[missing] {path}")
        return pd.DataFrame()

    print(f"[loading] {path}")

    return pd.read_csv(
        path,
        low_memory=False
    )


def index_standard_csv(index, path, source):
    df = load_csv(path)

    if df.empty:
        return

    for _, row in df.iterrows():

        add_record(
            index,
            source,
            row.get("subject", ""),
            row.get("sender", ""),
            row.get("body", ""),
        )


# ============================================================
# PHISHBOWL
# ============================================================

def strip_phishbowl_notice(text):
    """
    Remove Cornell's warning boilerplate.

    This mirrors the logic used by dataset_v2.py.
    """

    if pd.isna(text):
        return ""

    text = str(text)

    text = re.sub(
        r'<div[^>]*dialog-notice[^>]*>.*?</div>',
        "",
        text,
        flags=re.I | re.S,
    )

    return clean_display_body(text)


def index_phishbowl(index):

    path = RAW / "phishbowl.csv"

    if not path.exists():
        print(f"[missing] {path}")
        return

    print(f"[loading] {path}")

    df = pd.read_csv(
        path,
        low_memory=False
    )

    for _, row in df.iterrows():

        subject = row.get("title", "")
        body = row.get("email_message", "")

        cleaned = strip_phishbowl_notice(body)

        # PhishBowl does not use the same sender representation
        # as the master dataset, so index using subject + body
        # and body alone.

        add_record(
            index,
            "phishbowl",
            subject,
            "",
            cleaned,
        )


def index_spamassassin_full(index):
    """
    Parse the exact SpamAssassin RFC822 corpus used by dataset_v2.py.
    Only easy_ham + hard_ham are included.
    """

    import glob
    import os
    import email
    from email import policy

    root = RAW / "spamassassin_full"

    ham_dirs = [
        root / "easy_ham",
        root / "hard_ham",
    ]

    files = []

    for directory in ham_dirs:
        if not directory.exists():
            continue

        for f in glob.glob(str(directory / "*")):
            if (
                os.path.isfile(f)
                and "__MACOSX" not in f
                and not os.path.basename(f).startswith(".")
            ):
                files.append(f)

    print(f"[spamassassin] found {len(files):,} raw messages")

    for f in files:

        try:
            with open(f, "rb") as fh:
                msg = email.message_from_binary_file(
                    fh,
                    policy=policy.default,
                )

            sender = str(msg.get("from") or "").strip()
            subject = str(msg.get("subject") or "").strip()

            body = ""

            part = msg.get_body(
                preferencelist=("plain",)
            )

            if part:
                body = part.get_content()

            body = re.sub(
                r"\s+",
                " ",
                str(body),
            ).strip()

            if len(body) < 20:
                continue

            add_record(
                index,
                "spamassassin_ham",
                subject,
                sender,
                body,
            )

        except Exception:
            continue

    print("[spamassassin] full corpus indexed")

# ============================================================
# BUILD RAW LOOKUP
# ============================================================

def build_lookup():

    index = {}

    # --------------------------------------------------------
    # Kaggle phishing sources
    # --------------------------------------------------------

    index_standard_csv(
        index,
        RAW / "phishing_email_dataset" / "CEAS_08.csv",
        "ceas08",
    )

    index_standard_csv(
        index,
        RAW / "phishing_email_dataset" / "Nazario.csv",
        "nazario",
    )

    index_standard_csv(
        index,
        RAW / "phishing_email_dataset" / "Nigerian_Fraud.csv",
        "nigerian_fraud",
    )

    # --------------------------------------------------------
    # Enron
    # --------------------------------------------------------

    print("[loading] HuggingFace corbt/enron-emails")

    try:
        from huggingface_hub import hf_hub_download

        enron_path = hf_hub_download(
            "corbt/enron-emails",
            "data/train-00000-of-00003.parquet",
            repo_type="dataset",
        )

        enron = pd.read_parquet(
            enron_path,
            columns=["from", "subject", "body"],
        )

        for _, row in enron.iterrows():
            add_record(
                index,
                "enron_clean",
                row.get("subject", ""),
                row.get("from", ""),
                row.get("body", ""),
            )

        print(f"[enron] indexed {len(enron):,} HuggingFace emails")

    except Exception as ex:
        print(f"[enron] ERROR loading HuggingFace dataset: {ex}")

    # --------------------------------------------------------
    # SpamAssassin
    # --------------------------------------------------------

    index_spamassassin_full(index)

    # Keep the smaller CSV as an additional fallback source.
    index_standard_csv(
        index,
        RAW / "spamassassin_ham_100.csv",
        "spamassassin_ham",
    )

    # --------------------------------------------------------
    # TREC07
    # --------------------------------------------------------

    index_standard_csv(
        index,
        RAW / "trec07" / "TREC_07.csv",
        "trec07_ham",
    )

    # --------------------------------------------------------
    # Plain LLM
    # --------------------------------------------------------

    index_standard_csv(
        index,
        RAW / "plain_llm_phishing.csv",
        "plain_llm",
    )

    index_standard_csv(
        index,
        RAW / "plain_llm_groq.csv",
        "plain_llm",
    )

    # --------------------------------------------------------
    # Hybrid V-Triad
    # --------------------------------------------------------

    index_standard_csv(
        index,
        RAW / "hybrid_vtriad_phishing.csv",
        "hybrid_vtriad",
    )

    index_standard_csv(
        index,
        RAW / "hybrid_vtriad_groq.csv",
        "hybrid_vtriad",
    )

    # --------------------------------------------------------
    # Multi-LLM
    # --------------------------------------------------------

    multi_path = (
        RAW
        / "multi_llm"
        / "data"
        / "llm_corpus_sampled.csv"
    )

    if multi_path.exists():

        df = load_csv(multi_path)

        for _, row in df.iterrows():

            add_record(
                index,
                "multi_llm",
                row.get("subject", ""),
                "",
                row.get("body", ""),
            )

    # --------------------------------------------------------
    # PhishBowl
    # --------------------------------------------------------

    index_phishbowl(index)

    print(f"\nRaw lookup keys: {len(index):,}")

    return index


# ============================================================
# MATCHING
# ============================================================

def find_match(index, source, subject, sender, body):

    s = subject_key(subject)
    se = sender_key(sender)
    b = body_key(body)

    # --------------------------------------------------------
    # 1. Exact subject + sender + body
    # --------------------------------------------------------

    if s and se:
        candidates = index.get(
            (source, "ssb", s, se, b),
            []
        )

        if candidates:
            return candidates[0], "subject+sender+body"

    # --------------------------------------------------------
    # 2. Exact subject + body
    # --------------------------------------------------------

    if s:
        candidates = index.get(
            (source, "sb", s, b),
            []
        )

        if candidates:
            return candidates[0], "subject+body"

    # --------------------------------------------------------
    # 3. Exact body
    # --------------------------------------------------------

    candidates = index.get(
        (source, "b", b),
        []
    )

    if candidates:
        return candidates[0], "body"

    return None, None


# ============================================================
# MAIN
# ============================================================

def build():

    if not MASTER.exists():
        raise FileNotFoundError(
            f"Master dataset not found:\n{MASTER}"
        )

    print("Loading master dataset...")

    master = pd.read_csv(
        MASTER,
        low_memory=False
    )

    print(f"Master emails: {len(master):,}")

    print("\nBuilding raw source index...")

    index = build_lookup()

    output = []

    stats = {}

    for _, row in master.iterrows():

        source = str(row["source"])

        subject = (
            ""
            if pd.isna(row["subject"])
            else str(row["subject"])
        )

        sender = (
            ""
            if pd.isna(row["sender"])
            else str(row["sender"])
        )

        master_body = (
            ""
            if pd.isna(row["body"])
            else str(row["body"])
        )

        if source not in stats:
            stats[source] = {
                "total": 0,
                "matched": 0,
                "fallback": 0,
                "methods": {},
            }

        stats[source]["total"] += 1

        raw, method = find_match(
            index,
            source,
            subject,
            sender,
            master_body,
        )

        if raw is not None:

            display_subject = (
                raw["subject"]
                if raw["subject"]
                else subject
            )

            display_sender = (
                raw["sender"]
                if raw["sender"]
                else sender
            )

            display_body = clean_display_body(
                raw["body"]
            )

            stats[source]["matched"] += 1

            stats[source]["methods"][method] = (
                stats[source]["methods"].get(method, 0) + 1
            )

        else:

            # Safe fallback:
            # preserve the master content rather than inventing
            # formatting or wording.

            display_subject = subject
            display_sender = sender
            display_body = clean_display_body(
                master_body
            )

            stats[source]["fallback"] += 1

        # ----------------------------------------------------
        # Extract URLs from the DISPLAY BODY.
        #
        # These are metadata only.
        # The frontend will display the URLs as plain text.
        # ----------------------------------------------------

        urls = re.findall(
            r"https?://[^\s<>'\"]+",
            display_body,
        )

        output.append({
            "email_id": int(row["email_id"]),
            "subject": display_subject,
            "sender": display_sender,
            "body": display_body,
            "extracted_urls": "|".join(urls),
            "source": source,
            "actual_class": int(row["actual_class"]),
        })

    result = pd.DataFrame(output)

    OUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result.to_csv(
        OUT,
        index=False,
        encoding="utf-8",
    )

    # ========================================================
    # REPORT
    # ========================================================

    print("\n")
    print("=" * 70)
    print("HUMAN DATASET CREATED")
    print("=" * 70)

    print(f"Output: {OUT}")
    print(f"Emails: {len(result):,}")

    total_matched = sum(
        x["matched"]
        for x in stats.values()
    )

    total_fallback = sum(
        x["fallback"]
        for x in stats.values()
    )

    print(f"Raw matched: {total_matched:,}")
    print(f"Fallback:    {total_fallback:,}")

    print(
        f"Match rate:  "
        f"{total_matched / len(result) * 100:.1f}%"
    )

    print("\nPer-source reconstruction:")
    print("-" * 70)

    for source, s in stats.items():

        rate = (
            s["matched"] / s["total"] * 100
            if s["total"]
            else 0
        )

        print(
            f"{source:20}"
            f"{s['matched']:4}/{s['total']:<4}"
            f" ({rate:5.1f}%)"
        )

        if s["methods"]:

            for method, count in s["methods"].items():
                print(
                    f"    {method}: {count}"
                )

    print("\nComposition:")
    print(
        result
        .groupby(["source", "actual_class"])
        .size()
        .to_string()
    )


if __name__ == "__main__":
    build()