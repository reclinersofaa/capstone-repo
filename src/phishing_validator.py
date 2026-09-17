"""
phishing_validator.py — checks whether a generated email actually has an attack path,
instead of trusting the generation label alone.

Why this exists: a panel review found ~43% of the published hybrid_vtriad emails read
as ordinary internal announcements (a calendar update, a benefits notice) with no
requested action, no destination, and no attacker objective — yet were labelled
actual_class=1. A corporate tone is not phishing; phishing requires a concrete action
that benefits an attacker. This is a cheap, auditable gate, not a full NLP classifier —
it is meant to catch the "labelled but harmless" failure mode, not adjudicate borderline
cases with certainty.
"""
import re

# A cue-neutral action/destination signal. Deliberately NOT the 9 perception cues —
# this validates GROUND TRUTH (is there an attack path), which must never leak into the
# agent's 9-cue decision loop or the experiment measuring subtle-cue detection becomes
# circular (the agent would effectively see the validator's own verdict).
_ACTION_PAT = re.compile(
    r"sign.?in|log.?in|verify|confirm your|password|credential|"
    r"download|open the attach|click (here|below|the link)|"
    r"enter your|provide your|update your (payment|billing|account)|"
    r"reply with|respond with|approve|authoriz|"
    r"before (friday|monday|tuesday|wednesday|thursday|saturday|sunday|\d)|"
    r"within \d+ (hour|day)|expir|suspend|deactivat",
    re.I,
)

_DESTINATION_PAT = re.compile(
    r"https?://|portal\.|www\.|\.test/|\.com/|attach(ed|ment)|shared (drive|link)",
    re.I,
)


def has_attack_path(body: str) -> bool:
    """True if the body contains BOTH an actionable request AND some destination or
    response mechanism (a link, an attachment reference, a reply-to ask). Requiring
    both catches pure announcements ("the schedule has been updated") that use one
    urgency-adjacent word but request nothing of the reader.
    """
    body = str(body or "")
    return bool(_ACTION_PAT.search(body)) and bool(_DESTINATION_PAT.search(body))


def validation_report(df, body_col: str = "body"):
    """Returns (passing_mask, fail_count, fail_subjects_sample) for a DataFrame."""
    mask = df[body_col].apply(has_attack_path)
    fails = df.loc[~mask]
    subj_col = "subject" if "subject" in df.columns else None
    sample = fails[subj_col].head(10).tolist() if subj_col else []
    return mask, int((~mask).sum()), sample


if __name__ == "__main__":
    import pandas as pd
    d = pd.read_csv("data/processed/master_emails_v2.csv")
    v = d[d.source == "hybrid_vtriad"]
    mask, n_fail, sample = validation_report(v)
    print(f"hybrid_vtriad: {len(v)} rows, {n_fail} fail (no attack path), {mask.sum()} pass")
    print("failing subjects (sample):")
    for s in sample:
        print(" -", s)
