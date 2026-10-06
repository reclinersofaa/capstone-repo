"""
DEMO ONLY: loads an illustrative team roster (data/scenarios/demo_roster.csv) into
AgentV2 employees. Team profiles are presentation assumptions, not a validated model.
Columns not in the roster take neutral mid-scale defaults.
"""
from pathlib import Path

import pandas as pd

from .agent_v2 import AgentV2, _clamp

ROSTER = Path(__file__).resolve().parent.parent / "data" / "scenarios" / "demo_roster.csv"
NEUTRAL = dict(education_level=3.0, sleep_quality=3.0, subjective_health=3.0, depression=2.0,
               job_satisfaction=3.0, role_conflict=2.5, role_ambiguity=2.5, leave_intention=2.5,
               lack_motivation=2.5)


def load_demo_agents(path: Path = ROSTER) -> list:
    df = pd.read_csv(path)
    agents = []
    for i, r in enumerate(df.itertuples(index=False)):
        jc = float(r.job_complexity)
        a = AgentV2(
            agent_id=f"demo_{i + 1:02d}", age=float(r.age), gender=0,
            tenure=float(r.tenure), job_type=0, job_complexity=jc,
            total_sleep_time=float(r.total_sleep_time), illness=0,
            stress_avg=float(r.stress_avg), burnout=float(r.burnout),
            intrinsic_motivation=float(r.intrinsic_motivation),
            perceived_vulnerability=float(r.perceived_vulnerability),
            base_suspicion_threshold=float(r.threshold), max_cues_processed=9,
            **NEUTRAL,
        )
        a.task_switching = _clamp(0.25 + 0.40 * ((jc - 1) / 4), 0.0, 1.0)
        a.team, a.designation, a.level = r.team, r.designation, r.level
        a.reset_workday()
        agents.append(a)
    return agents
