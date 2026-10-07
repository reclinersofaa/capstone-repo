"""Build showcase/email_timeline.json: per-email click rate through the workday,
and which simulated employees clicked and why.

For each phishing source the email chosen is the one whose overall click rate is
the median of that source, so the demo does not cherry-pick the most dramatic case.
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.scenarios import DEPARTMENTS  # noqa: E402

RESULTS = ROOT / "data" / "simulation_results_v2.csv"
EVIDENCE = ROOT / "showcase" / "evidence_items.json"
OUT = ROOT / "showcase" / "email_timeline.json"
HOURS = [8.0, 10.0, 12.0, 14.0, 16.0]
PHISHING_SOURCES = ["ceas08", "phishbowl", "hybrid_vtriad", "nazario",
                    "nigerian_fraud", "multi_llm", "plain_llm"]

# agent_id "sim_<dept-index><within-dept-index>" -- see src/scenarios.py build_scenario_agents().
# DEPARTMENTS is an insertion-ordered dict, so index 1..6 matches dept_idx+1 there exactly.
DEPT_NAMES = list(DEPARTMENTS.keys())


def department_of(agent_id: str) -> str:
    digits = agent_id.split("_", 1)[1]  # "11" -> dept 1, within-dept 1
    d_idx = int(digits[0]) - 1
    return DEPT_NAMES[d_idx] if 0 <= d_idx < len(DEPT_NAMES) else "unknown"


def main():
    if not RESULTS.exists():
        sys.exit(f"missing {RESULTS}")
    if not EVIDENCE.exists():
        sys.exit(f"missing {EVIDENCE}; run scripts/build_evidence_items.py first")

    df = pd.read_csv(RESULTS)
    df = df[df["actual_class"] == 1].copy()
    df["clicked"] = (df["decision"] == "clicked").astype(int)
    evidence = {str(e.get("email_id")): e for e in json.loads(EVIDENCE.read_text(encoding="utf-8"))}

    # Email-level click rate, per source, to choose the median email.
    per_email = df.groupby(["source", "email_id"])["clicked"].mean().reset_index()

    emails = []
    for src in PHISHING_SOURCES:
        rows = per_email[per_email["source"] == src].sort_values("clicked").reset_index(drop=True)
        if rows.empty:
            sys.exit(f"no phishing rows for source {src}")
        mid = rows.iloc[len(rows) // 2]
        eid = mid["email_id"]
        sub = df[(df["source"] == src) & (df["email_id"] == eid)]
        ev = evidence.get(str(eid))
        if ev is None:
            # Email has no cues in evidence_items; fall back to the subject/body from the corpus.
            sys.exit(f"email {eid} ({src}) not in evidence_items.json")

        hourly = []
        for h in HOURS:
            hs = sub[sub["workday_hour"] == h]
            hourly.append(round(100 * hs["clicked"].mean(), 1))

        agents = []
        for aid, grp in sub.groupby("agent_id"):
            grp = grp.sort_values("workday_hour")
            steps = []
            for _, r in grp.iterrows():
                cues = r["cues_perceived"]
                cues = [] if pd.isna(cues) else re.findall(r"[a-z_]+", str(cues))
                steps.append({
                    "h": float(r["workday_hour"]),
                    "d": r["decision"],
                    "cues": cues,
                    "s": int(r["suspicion_counter"]),
                    "t": round(float(r["suspicion_threshold"]), 2),
                })
            agents.append({"id": aid, "dept": department_of(aid), "steps": steps})

        # Per-department click rate at each hour (5 agents per dept x 6 depts = 30).
        dept_hourly = {d: [] for d in DEPT_NAMES}
        for h in HOURS:
            hs = sub[sub["workday_hour"] == h].copy()
            hs["dept"] = hs["agent_id"].map(department_of)
            for d in DEPT_NAMES:
                rows_d = hs[hs["dept"] == d]
                dept_hourly[d].append(round(100 * rows_d["clicked"].mean(), 1) if len(rows_d) else None)

        emails.append({
            "source": src,
            "email_id": str(eid),
            "overall_click_pct": round(100 * float(mid["clicked"]), 1),
            "subject": ev.get("subject", ""),
            "sender": ev.get("sender", ""),
            "body": ev.get("body", ""),
            "cues": ev.get("cues", []),
            "hours": HOURS,
            "hourly_click_pct": hourly,
            "dept_hourly": dept_hourly,
            "agents": agents,
        })

    OUT.write_text(json.dumps({"emails": emails}, ensure_ascii=False), encoding="utf-8")
    for e in emails:
        print(f"{e['source']:16s} email {e['email_id']:>6s}  overall {e['overall_click_pct']:5.1f}%  "
              f"hourly {e['hourly_click_pct']}")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
