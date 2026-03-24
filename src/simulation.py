import random
import ast
import pandas as pd
from pathlib import Path

from .agent import Agent
from .cue_extractor import CueExtractor
from .decision_loop import simulate_email

# Default workday sample points (hours, 8am–5pm)
DEFAULT_HOURS = [8.0, 10.0, 12.0, 14.0, 16.0]


def build_agents(n: int, seed: int = 42) -> list[Agent]:
    """Generate n random agents with reproducible seeds."""
    rng = random.Random(seed)
    agents = []
    for i in range(n):
        agent_seed = rng.randint(0, 10_000)
        agents.append(Agent.random_agent(f"agent_{i:03d}", seed=agent_seed))
    return agents


def run_simulation(
    emails_csv: str = "data/processed/master_emails.csv",
    n_agents: int = 20,
    workday_hours: list[float] = None,
    seed: int = 42,
    cache_dir: str = "data/cue_cache",
) -> pd.DataFrame:
    """
    Full agent simulation pipeline.

    Steps
    -----
    1. Extract cues for every email via Gemini (cached after first run).
    2. Generate n_agents random agents.
    3. For each agent × hour × email → run decision loop.
    4. Return results as a tidy DataFrame.

    Parameters
    ----------
    emails_csv    : path to master_emails.csv
    n_agents      : number of synthetic agents to simulate
    workday_hours : list of hours to simulate (default: 8,10,12,14,16)
    seed          : random seed for reproducibility
    cache_dir     : where to store Gemini response cache

    Returns
    -------
    DataFrame with one row per (agent, hour, email):
        agent_id, email_id, source, actual_class, workday_hour,
        suspicion_threshold, max_cues_processed, age, education_level,
        job_complexity, cues_extracted, decision, suspicion_counter,
        cues_scanned, cues_perceived, total_fatigue, final_jp, fpl
    """
    if workday_hours is None:
        workday_hours = DEFAULT_HOURS

    rng = random.Random(seed)
    emails = pd.read_csv(emails_csv)

    # ------------------------------------------------------------------
    # Step 1: Extract cues for all emails
    # ------------------------------------------------------------------
    extractor = CueExtractor(cache_dir=cache_dir)
    print(f"Step 1 — Extracting cues for {len(emails)} emails...")
    email_cues = extractor.extract_batch(emails)
    cached = sum(1 for eid in email_cues if (Path(cache_dir) / f"email_{eid}.json").exists())
    print(f"  Done. {cached} emails in cache, {len(email_cues) - cached} newly extracted.\n")

    # ------------------------------------------------------------------
    # Step 2: Build agents
    # ------------------------------------------------------------------
    print(f"Step 2 — Building {n_agents} agents...")
    agents = build_agents(n_agents, seed=seed)
    print(f"  Done.\n")

    # ------------------------------------------------------------------
    # Step 3: Simulate
    # ------------------------------------------------------------------
    total_runs = n_agents * len(workday_hours) * len(emails)
    print(f"Step 3 — Simulating {n_agents} agents × {len(workday_hours)} hours × {len(emails)} emails = {total_runs} runs...")

    hour_labels = {8.0: "8am", 10.0: "10am", 12.0: "12pm", 14.0: "2pm", 16.0: "4pm"}

    records = []
    step_id = 0
    for agent in agents:
        for hour in workday_hours:
            agent.advance_workday(hour)
            loop_rng = random.Random(rng.randint(0, 1_000_000))

            for _, row in emails.iterrows():
                eid = row["email_id"]
                cues = email_cues.get(eid, [])
                result = simulate_email(agent, cues, rng=loop_rng)

                records.append({
                    "step_id":              step_id,
                    "agent_id":             agent.agent_id,
                    "email_id":             eid,
                    "source":               row["source"],
                    "actual_class":         row["actual_class"],
                    "workday_hour":         hour,
                    "time_of_day":          hour_labels.get(hour, f"{int(hour)}:00"),
                    "suspicion_threshold":  agent.suspicion_threshold,
                    "max_cues_processed":   agent.max_cues_processed,
                    "age":                  round(agent.age, 1),
                    "education_level":      round(agent.education_level, 1),
                    "job_complexity":       round(agent.job_complexity, 1),
                    "cues_extracted":       len(cues),
                    **result,
                })
                step_id += 1

    df = pd.DataFrame(records)
    print(f"  Done. {len(df):,} rows generated.\n")
    return df


def save_results(df: pd.DataFrame, path: str = "data/simulation_results.csv"):
    """Save simulation results DataFrame to CSV."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"Saved {len(df):,} rows to {path}")


def click_rate_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute click rate (fraction of 'clicked' decisions) grouped by
    source, workday_hour, and actual_class.

    A 'click' on a benign email is correct behaviour.
    A 'click' on a phishing email is a vulnerability.
    """
    df = df.copy()
    df["clicked"] = (df["decision"] == "clicked").astype(int)

    summary = (
        df.groupby(["source", "actual_class", "workday_hour"])["clicked"]
        .agg(click_rate="mean", n="count")
        .reset_index()
    )
    summary["click_rate"] = summary["click_rate"].round(3)
    return summary
