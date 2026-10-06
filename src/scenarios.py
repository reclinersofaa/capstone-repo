"""
Department scenarios: a fixed simulated workforce, 6 departments x 5 simulated employees.

Each department is a set of scenario baseline traits (modelling assumptions, NOT
measured data). The five employees in a department are fixed offsets around that
baseline, so the population is identical on every run. Randomness in the simulation
is confined to the per-cue decision loop (controlled by seed), and seed-replication
is what the robustness analysis varies.

Suspicion threshold and perceived vulnerability are deliberately the SAME for all
30 employees. Departments differ in workload, fatigue and job traits only; any
per-team caution profile is left for the team to specify with citations.
"""
import math

from .agent_v2 import AgentV2, BASE_THRESHOLD_LO, BASE_THRESHOLD_HI, _COPULA_RANGES, _clamp

DEPARTMENTS = {
    "Finance & Accounts Payable": dict(
        age=38, tenure=7, education_level=4.0, job_type=0, job_complexity=3.8, gender=0,
        sleep_quality=3.0, total_sleep_time=6.9, subjective_health=3.4, depression=1.8,
        stress_avg=3.3, intrinsic_motivation=3.4, role_ambiguity=2.2, burnout=2.6,
        job_satisfaction=3.2, role_conflict=2.4, leave_intention=2.4, lack_motivation=2.2,
        perceived_vulnerability=0.50, threshold_frac=0.50, max_cues=9),
    "IT Service Desk": dict(
        age=31, tenure=4, education_level=4.0, job_type=1, job_complexity=3.9, gender=1,
        sleep_quality=2.8, total_sleep_time=6.4, subjective_health=3.2, depression=2.0,
        stress_avg=3.8, intrinsic_motivation=3.6, role_ambiguity=2.6, burnout=3.0,
        job_satisfaction=2.9, role_conflict=2.8, leave_intention=2.6, lack_motivation=2.4,
        perceived_vulnerability=0.50, threshold_frac=0.50, max_cues=11),
    "Human Resources": dict(
        age=42, tenure=9, education_level=3.8, job_type=0, job_complexity=2.9, gender=1,
        sleep_quality=3.4, total_sleep_time=7.2, subjective_health=3.7, depression=1.7,
        stress_avg=2.8, intrinsic_motivation=3.9, role_ambiguity=2.0, burnout=2.3,
        job_satisfaction=3.6, role_conflict=2.0, leave_intention=2.0, lack_motivation=1.9,
        perceived_vulnerability=0.50, threshold_frac=0.50, max_cues=9),
    "Regional Sales": dict(
        age=34, tenure=5, education_level=3.0, job_type=0, job_complexity=2.6, gender=0,
        sleep_quality=3.1, total_sleep_time=6.6, subjective_health=3.5, depression=1.9,
        stress_avg=3.1, intrinsic_motivation=4.1, role_ambiguity=2.3, burnout=2.4,
        job_satisfaction=3.7, role_conflict=2.2, leave_intention=2.7, lack_motivation=1.8,
        perceived_vulnerability=0.50, threshold_frac=0.50, max_cues=8),
    "Operations & Logistics (shift)": dict(
        age=45, tenure=12, education_level=2.6, job_type=1, job_complexity=2.4, gender=0,
        sleep_quality=2.5, total_sleep_time=6.0, subjective_health=3.0, depression=2.1,
        stress_avg=3.5, intrinsic_motivation=3.0, role_ambiguity=2.4, burnout=3.0,
        job_satisfaction=2.8, role_conflict=2.6, leave_intention=2.9, lack_motivation=2.6,
        perceived_vulnerability=0.50, threshold_frac=0.50, max_cues=8),
    "Customer Support (contact centre)": dict(
        age=27, tenure=3, education_level=2.9, job_type=1, job_complexity=2.8, gender=1,
        sleep_quality=2.9, total_sleep_time=6.3, subjective_health=3.1, depression=2.2,
        stress_avg=3.9, intrinsic_motivation=3.0, role_ambiguity=2.7, burnout=3.3,
        job_satisfaction=2.6, role_conflict=3.0, leave_intention=3.0, lack_motivation=2.8,
        perceived_vulnerability=0.50, threshold_frac=0.50, max_cues=7),
}

# Deterministic within-department spread: five fixed offsets (no RNG).
_OFFSETS = [-0.4, -0.2, 0.0, 0.2, 0.4]
_CONTINUOUS_1_TO_5 = [
    "education_level", "job_complexity", "sleep_quality", "subjective_health", "depression",
    "stress_avg", "intrinsic_motivation", "role_ambiguity", "burnout", "job_satisfaction",
    "role_conflict", "leave_intention", "lack_motivation",
]


def _value(name: str, base: float, off: float) -> float:
    lo, hi = _COPULA_RANGES.get(name, (1, 5))
    span = hi - lo
    return _clamp(base + off * span / 4.0, lo, hi)


def build_scenario_agents() -> list:
    """Return the 30 fixed simulated employees (6 departments x 5), in stable order."""
    agents = []
    for d_idx, (dept, p) in enumerate(DEPARTMENTS.items()):
        for k, off in enumerate(_OFFSETS):
            v = {}
            for name in _CONTINUOUS_1_TO_5:
                v[name] = _value(name, p[name], off)
            v["total_sleep_time"] = _value("total_sleep_time", p["total_sleep_time"], off)
            v["tenure"] = _value("tenure", p["tenure"], off * 2)
            v["age"] = _value("age", p["age"], off * 2)
            v["perceived_vulnerability"] = p["perceived_vulnerability"]
            jc = v["job_complexity"]
            jt = p["job_type"]
            agent = AgentV2(
                agent_id=f"sim_{d_idx + 1}{k + 1}",
                age=v["age"], gender=p["gender"],
                education_level=v["education_level"], tenure=v["tenure"],
                job_type=jt, job_complexity=jc,
                sleep_quality=v["sleep_quality"], total_sleep_time=v["total_sleep_time"],
                subjective_health=v["subjective_health"], depression=v["depression"],
                illness=0, stress_avg=v["stress_avg"],
                intrinsic_motivation=v["intrinsic_motivation"], role_ambiguity=v["role_ambiguity"],
                burnout=v["burnout"], job_satisfaction=v["job_satisfaction"],
                role_conflict=v["role_conflict"], leave_intention=v["leave_intention"],
                lack_motivation=v["lack_motivation"],
                perceived_vulnerability=v["perceived_vulnerability"],
                base_suspicion_threshold=BASE_THRESHOLD_LO
                    + p["threshold_frac"] * (BASE_THRESHOLD_HI - BASE_THRESHOLD_LO),
                max_cues_processed=p["max_cues"],
            )
            agent.task_switching = _clamp(
                0.25 + 0.40 * ((jc - 1) / 4) + 0.10 * jt, 0.0, 1.0
            )
            agent.department = dept
            agent.reset_workday()
            agents.append(agent)
    return agents
