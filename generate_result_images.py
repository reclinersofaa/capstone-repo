"""
Run this script from the repo root to generate all result images for the presentation.
Output: results/ folder with PNG files ready to paste into slides.

    python generate_result_images.py
"""

import ast
import json
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
import seaborn as sns
import textwrap

ROOT = Path(__file__).parent
OUT = ROOT / "results"
OUT.mkdir(exist_ok=True)

sns.set_theme(style="whitegrid", palette="muted")
plt.rcParams["figure.dpi"] = 150

df = pd.read_csv(ROOT / "data" / "simulation_results.csv")
master = pd.read_csv(ROOT / "data" / "processed" / "master_emails.csv")
phishing_df = df[df["actual_class"] == 1].copy()
phishing_df["clicked"] = (phishing_df["decision"] == "clicked").astype(int)
benign_df = df[df["actual_class"] == 0].copy()

HOUR_LABELS = {8.0: "8am", 10.0: "10am", 12.0: "12pm", 14.0: "2pm", 16.0: "4pm"}
SOURCE_COLORS = {
    "hybrid_vtriad": "#2196F3",
    "phishbowl": "#F44336",
    "plain_llm": "#FF9800",
    "spamassassin_ham": "#4CAF50",
}

# ── 1. Click rate by source across the workday ────────────────────────────────
fig, ax = plt.subplots(figsize=(9, 5))
by_source_hour = (
    phishing_df.groupby(["source", "workday_hour"])["clicked"]
    .mean()
    .reset_index()
    .rename(columns={"clicked": "click_rate"})
)
for source, grp in by_source_hour.groupby("source"):
    ax.plot(
        grp["workday_hour"], grp["click_rate"],
        marker="o", label=source.replace("_", " ").title(),
        color=SOURCE_COLORS.get(source), linewidth=2.5, markersize=7,
    )
ax.set_xlabel("Workday Hour", fontsize=12)
ax.set_ylabel("Click Rate (phishing emails)", fontsize=12)
ax.set_title("Agent Phishing Click Rate Across the Workday by Email Source", fontsize=13, fontweight="bold")
ax.set_xticks([8, 10, 12, 14, 16])
ax.set_xticklabels(["8am", "10am", "12pm", "2pm", "4pm"])
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
ax.legend(fontsize=10)
ax.set_ylim(0.5, 1.05)
plt.tight_layout()
plt.savefig(OUT / "01_click_rate_by_source.png", bbox_inches="tight")
plt.close()
print("Saved 01_click_rate_by_source.png")

# ── 2. Fatigue effect on click rate ──────────────────────────────────────────
phishing_df["fatigue_bin"] = pd.qcut(
    phishing_df["total_fatigue"], q=3, labels=["Low Fatigue", "Medium Fatigue", "High Fatigue"]
)
fatigue_click = (
    phishing_df.groupby(["fatigue_bin", "workday_hour"], observed=True)["clicked"]
    .mean()
    .reset_index()
    .rename(columns={"clicked": "click_rate"})
)
fig, ax = plt.subplots(figsize=(9, 5))
fatigue_colors = {"Low Fatigue": "#4CAF50", "Medium Fatigue": "#FF9800", "High Fatigue": "#F44336"}
for fb, grp in fatigue_click.groupby("fatigue_bin", observed=True):
    ax.plot(
        grp["workday_hour"], grp["click_rate"],
        marker="o", label=str(fb), color=fatigue_colors[str(fb)],
        linewidth=2.5, markersize=7,
    )
ax.set_xlabel("Workday Hour", fontsize=12)
ax.set_ylabel("Click Rate (phishing emails)", fontsize=12)
ax.set_title("Phishing Click Rate by Agent Fatigue Level Across the Workday", fontsize=13, fontweight="bold")
ax.set_xticks([8, 10, 12, 14, 16])
ax.set_xticklabels(["8am", "10am", "12pm", "2pm", "4pm"])
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
ax.legend(fontsize=10)
plt.tight_layout()
plt.savefig(OUT / "02_fatigue_effect.png", bbox_inches="tight")
plt.close()
print("Saved 02_fatigue_effect.png")

# ── 3. Summary bar chart — overall click rate by source ──────────────────────
overall = (
    phishing_df.groupby("source")["clicked"]
    .mean()
    .reset_index()
    .rename(columns={"clicked": "click_rate"})
    .sort_values("click_rate")
)
fig, ax = plt.subplots(figsize=(8, 4))
bars = ax.barh(
    overall["source"].str.replace("_", " ").str.title(),
    overall["click_rate"],
    color=[SOURCE_COLORS.get(s, "#999") for s in overall["source"]],
    edgecolor="white", height=0.5,
)
for bar, val in zip(bars, overall["click_rate"]):
    ax.text(val - 0.015, bar.get_y() + bar.get_height() / 2,
            f"{val:.1%}", va="center", ha="right", color="white", fontweight="bold", fontsize=12)
ax.set_xlabel("Average Click Rate across all agents and hours", fontsize=11)
ax.set_title("Overall Agent Click Rate by Email Source\n(phishing emails only — lower = harder to detect)",
             fontsize=12, fontweight="bold")
ax.set_xlim(0, 1.05)
ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
plt.tight_layout()
plt.savefig(OUT / "03_overall_click_rate.png", bbox_inches="tight")
plt.close()
print("Saved 03_overall_click_rate.png")

# ── 4. Correlation heatmap: agent traits vs click rate ───────────────────────
agent_summary = (
    phishing_df.groupby("agent_id")
    .agg(
        click_rate=("clicked", "mean"),
        avg_fatigue=("total_fatigue", "mean"),
        avg_jp=("final_jp", "mean"),
        avg_fpl=("fpl", "mean"),
        age=("age", "first"),
        education_level=("education_level", "first"),
        job_complexity=("job_complexity", "first"),
        suspicion_threshold=("suspicion_threshold", "first"),
    )
    .reset_index()
)
corr_cols = ["click_rate", "avg_fatigue", "avg_jp", "avg_fpl",
             "age", "education_level", "job_complexity", "suspicion_threshold"]
corr = agent_summary[corr_cols].corr()
fig, ax = plt.subplots(figsize=(9, 7))
sns.heatmap(corr, annot=True, fmt=".2f", cmap="RdBu_r", center=0,
            ax=ax, vmin=-1, vmax=1, linewidths=0.5,
            xticklabels=[c.replace("_", "\n") for c in corr_cols],
            yticklabels=[c.replace("_", " ") for c in corr_cols])
ax.set_title("Correlation: Agent Traits vs Phishing Click Rate", fontsize=13, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "04_trait_correlation.png", bbox_inches="tight")
plt.close()
print("Saved 04_trait_correlation.png")

# ── 5. Cue perception heatmap ─────────────────────────────────────────────────
all_cues = [
    "urgency", "threats", "generic_greeting", "spelling_grammar",
    "emotional_appeal", "too_good_true", "personal_info",
    "suspicious_sender", "suspicious_link",
]

def parse_cues(val):
    if isinstance(val, list):
        return val
    try:
        return ast.literal_eval(val)
    except Exception:
        return []

phishing_df = phishing_df.copy()
phishing_df["cues_perceived"] = phishing_df["cues_perceived"].apply(parse_cues)
for cue in all_cues:
    phishing_df[f"p_{cue}"] = phishing_df["cues_perceived"].apply(lambda c: int(cue in c))

perceived_cols = [f"p_{c}" for c in all_cues]
cue_by_source = (phishing_df.groupby("source")[perceived_cols].mean() * 100).round(1)
cue_by_source.columns = all_cues
cue_by_source.index = cue_by_source.index.str.replace("_", " ").str.title()

fig, ax = plt.subplots(figsize=(12, 4))
sns.heatmap(cue_by_source, annot=True, fmt=".0f", cmap="Blues", ax=ax,
            linewidths=0.5, cbar_kws={"label": "% of trials cue was perceived"})
ax.set_title("% of Simulation Trials Where Each Cue Was Perceived — by Email Source",
             fontsize=12, fontweight="bold")
ax.set_ylabel("")
ax.set_xlabel("Phishing Cue", fontsize=11)
plt.tight_layout()
plt.savefig(OUT / "05_cue_heatmap.png", bbox_inches="tight")
plt.close()
print("Saved 05_cue_heatmap.png")

# ── 6. Email showcase — benign vs real phishing vs LLM phishing ──────────────
showcase = {
    "Benign\n(SpamAssassin Ham)": 6,
    "Real Phishing\n(Phishbowl)": 101,
    "LLM Phishing\n(Plain LLM — 0 cues detected)": 152,
}
bg_colors = ["#e8f5e9", "#ffebee", "#fff8e1"]
border_colors = ["#388E3C", "#C62828", "#E65100"]

fig, axes = plt.subplots(1, 3, figsize=(19, 8))
for ax, (label, eid), bg, bc in zip(axes, showcase.items(), bg_colors, border_colors):
    row = master[master["email_id"] == eid].iloc[0]
    try:
        cues = json.loads((ROOT / "data" / "cue_cache" / f"email_{eid}.json").read_text())
    except Exception:
        cues = []

    subset = df[df["email_id"] == eid]
    click_rate = (subset["decision"] == "clicked").mean()

    ax.set_facecolor(bg)
    for spine in ax.spines.values():
        spine.set_edgecolor(bc)
        spine.set_linewidth(3)
    ax.set_xticks([])
    ax.set_yticks([])

    body_wrapped = "\n".join(textwrap.wrap(str(row["body"])[:420], width=42))
    cue_text = ", ".join(cues) if cues else "NONE DETECTED"
    click_text = f"{click_rate:.0%} of agents clicked"

    content = (
        f"Subject: {str(row['subject'])[:50]}\n"
        f"From:    {str(row['sender'])[:45]}\n"
        f"{'─' * 44}\n\n"
        f"{body_wrapped}\n\n"
        f"{'─' * 44}\n"
        f"Cues detected ({len(cues)}): {cue_text}\n\n"
        f"Agent click rate: {click_text}"
    )

    ax.text(0.04, 0.97, content, transform=ax.transAxes,
            fontsize=8.2, verticalalignment="top", fontfamily="monospace",
            linespacing=1.5)
    ax.set_title(label, fontsize=11, fontweight="bold", color=bc, pad=12)

fig.suptitle(
    "Why Agents Fall For It: The Danger of AI-Generated Phishing",
    fontsize=14, fontweight="bold", y=1.01,
)
plt.tight_layout()
plt.savefig(OUT / "06_email_showcase.png", bbox_inches="tight")
plt.close()
print("Saved 06_email_showcase.png")

# ── 7. FPL vs click rate scatter ─────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(12, 5))
axes[0].scatter(agent_summary["avg_fpl"], agent_summary["click_rate"],
                alpha=0.8, s=80, color="#2196F3", edgecolors="white", linewidth=0.5)
axes[0].set_xlabel("Average FPL (Flawed Perception Level)", fontsize=11)
axes[0].set_ylabel("Click Rate on Phishing Emails", fontsize=11)
axes[0].set_title("FPL vs Click Rate per Agent", fontsize=12, fontweight="bold")
axes[0].yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))

axes[1].scatter(agent_summary["suspicion_threshold"], agent_summary["click_rate"],
                alpha=0.8, s=80, color="#F44336", edgecolors="white", linewidth=0.5)
axes[1].set_xlabel("Suspicion Threshold", fontsize=11)
axes[1].set_ylabel("Click Rate on Phishing Emails", fontsize=11)
axes[1].set_title("Suspicion Threshold vs Click Rate per Agent", fontsize=12, fontweight="bold")
axes[1].yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
axes[1].set_xticks([2, 3, 4, 5, 6])

plt.tight_layout()
plt.savefig(OUT / "07_fpl_threshold_scatter.png", bbox_inches="tight")
plt.close()
print("Saved 07_fpl_threshold_scatter.png")

print(f"\nAll images saved to: {OUT}")
print("Files generated:")
for f in sorted(OUT.glob("*.png")):
    print(f"  {f.name}")
