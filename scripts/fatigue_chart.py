"""Fatigue across the workday vs click rate, plus each metric's correlation with click rate.
Reads data/simulation_results_v2.csv (main run) and writes results/fatigue_vs_click.png."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
r = pd.read_csv(ROOT / "data" / "simulation_results_v2.csv")
r["clicked"] = (r.decision == "clicked").astype(float)
ph = r[r.actual_class == 1]

by_hour = ph.groupby("workday_hour").agg(click=("clicked", "mean"), fatigue=("total_fatigue", "mean"),
                                         jp=("final_jp", "mean"), fpl=("fpl", "mean"))
# correlation across the 150 agent-hour cells (30 employees x 5 hours), phishing decisions only
cell = ph.groupby(["agent_id", "workday_hour"]).agg(click=("clicked", "mean"), fatigue=("total_fatigue", "mean"),
                                                    jp=("final_jp", "mean"), fpl=("fpl", "mean"),
                                                    pv=("perceived_vulnerability", "mean"),
                                                    threshold=("suspicion_threshold", "mean"),
                                                    p_click=("p_click", "mean"))
corr = cell.corr()["click"].drop("click").sort_values()

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.6))
hrs = by_hour.index
ax1.plot(hrs, by_hour.click * 100, marker="o", color="#c0392b", lw=2.5, label="click rate (%)")
ax1.set_xlabel("hour of the workday"); ax1.set_ylabel("phishing click rate (%)", color="#c0392b")
ax1.set_xticks(hrs); ax1.set_xticklabels(["8am", "10am", "12pm", "2pm", "4pm"])
ax1b = ax1.twinx()
ax1b.plot(hrs, by_hour.fatigue, marker="s", color="#2c3e50", lw=2, ls="--", label="total fatigue (0-1)")
ax1b.plot(hrs, by_hour.jp, marker="^", color="#16a085", lw=2, ls=":", label="job performance (0-1)")
ax1b.set_ylabel("fatigue / job performance")
h1, l1 = ax1.get_legend_handles_labels(); h2, l2 = ax1b.get_legend_handles_labels()
ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8)
ax1.set_title("Across the day: fatigue rises, performance falls, clicks rise")
ax1.grid(alpha=.3)

colors = ["#c0392b" if abs(v) >= 0.3 else "#7f8c8d" for v in corr.values]
ax2.barh([c.replace("_", " ") for c in corr.index], corr.values, color=colors)
ax2.axvline(0, color="black", lw=.8)
ax2.set_xlabel("correlation with click rate (150 employee-hour cells)")
ax2.set_title("Which metrics track clicks")
for y, v in enumerate(corr.values):
    ax2.text(v + (0.02 if v >= 0 else -0.02), y, f"{v:+.2f}", va="center", ha="left" if v >= 0 else "right", fontsize=9)
ax2.set_xlim(-1.05, 1.05); ax2.grid(alpha=.3, axis="x")
plt.tight_layout()
out = ROOT / "results" / "fatigue_vs_click.png"
plt.savefig(out, dpi=150)
print(by_hour.round(3).to_string())
print(corr.round(3).to_string())
print("saved", out)
