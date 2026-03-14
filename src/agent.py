import random
from dataclasses import dataclass, field


@dataclass
class Agent:
    # --- Identity ---
    agent_id: str

    # --- Stable demographic traits ---
    age: float             # years (22–60)
    gender: float          # 0 = female, 1 = male (as encoded in the regression)
    education_level: float # 1–5 scale (1=no degree, 5=postgrad)
    tenure: float          # years at current job
    job_type: float        # 0 = non-desk, 1 = desk job
    job_complexity: float  # 1–5 scale

    # --- Fatigue inputs (personal baselines, stable across workday) ---
    sleep_quality: float      # 1–5
    subjective_health: float  # 1–5
    depression: float         # 1–5
    illness: float            # 0 = healthy, 1 = ill
    stress_avg: float         # 1–5

    # --- Job performance inputs (stable) ---
    burnout: float              # 1–5
    intrinsic_motivation: float # 1–5
    job_satisfaction: float     # 1–5
    role_conflict: float        # 1–5
    leave_intention: float      # 1–5
    role_ambiguity: float       # 1–5
    lack_motivation: float      # 1–5

    # --- Suspicion thresholds (fixed at creation) ---
    suspicion_threshold: int  # 2–6: cues needed to mark email as phishing
    max_cues_processed: int   # 7–12: agent stops scanning after this many cues

    # --- Workday-dynamic state (mutated by advance_workday) ---
    time_of_awakening: float = 7.0   # hour agent woke up (e.g. 7 = 7am)
    total_sleep_time: float = 7.5    # hours slept
    time_pressure: float = 1.0       # 1–5, increases as workday advances
    workload: float = 1.5            # 1–5, increases as workday advances

    # -------------------------------------------------------------------------
    # Internal state calculations
    # -------------------------------------------------------------------------

    def compute_energy_depletion(self) -> float:
        return (
            2.45
            - 0.05 * self.age
            + 0.09 * self.gender
            - 0.08 * self.education_level
            - 0.01 * self.tenure
            - 0.25 * self.job_type
            + 0.65 * self.job_complexity
        )

    def compute_fatigue(self) -> float:
        return (
            6.22
            - 0.22 * self.time_of_awakening
            - 0.15 * self.total_sleep_time
            + 0.14 * self.sleep_quality
            + 0.44 * self.stress_avg
            + 0.44 * self.illness
            + 0.29 * self.subjective_health
            + 0.02 * self.age
            + 0.17 * self.depression
        )

    def compute_total_fatigue(self) -> float:
        """Average of energy depletion and fatigue, clamped to [1, 5]."""
        raw = (self.compute_energy_depletion() + self.compute_fatigue()) / 2
        return max(1.0, min(5.0, raw))

    def compute_job_performance(self) -> float:
        """Final JP = average of JP1 and JP2 minus fatigue crossover penalty."""
        jp1 = (
            2.766
            - 0.106 * self.burnout
            + 0.301 * self.intrinsic_motivation
            + 0.298 * self.job_satisfaction
            - 0.153 * self.role_conflict
            - 0.076 * self.leave_intention
        )
        jp2 = (
            3.238
            - 0.022 * self.time_pressure
            - 0.086 * self.workload
            - 0.141 * self.lack_motivation
            - 0.155 * self.role_ambiguity
        )
        overall = (jp1 + jp2) / 2
        return overall - (0.34 * self.compute_total_fatigue())

    def compute_flawed_perception_level(self) -> float:
        """
        Probability [0.0, 0.5] that agent misidentifies a malicious cue as benign.
        Higher fatigue + lower JP → higher FPL (more errors).
        """
        fatigue = self.compute_total_fatigue()   # 1–5
        jp = self.compute_job_performance()

        fatigue_norm = (fatigue - 1) / 4          # → [0, 1]
        jp_norm = max(0.0, min(1.0, jp / 4.0))    # → [0, 1], higher is better

        fpl = 0.5 * fatigue_norm * (1 - jp_norm)
        return max(0.0, min(0.5, fpl))

    def get_cue_fpl(self, cue: str) -> float:
        """
        Trait-differentiated FPL per cue.

        Older and less-educated agents are worse at URL/sender cues.
        Desk workers in complex jobs are better at account-threat cues.
        """
        base = self.compute_flawed_perception_level()

        if cue in ("suspicious_link", "suspicious_sender"):
            # age penalty: +0–0.15 for 30–60 years old
            age_pen = max(0.0, (self.age - 30) / 200)
            # education penalty: +0–0.1 for low education (1–2)
            edu_pen = max(0.0, (3 - self.education_level) / 20)
            return min(0.5, base + age_pen + edu_pen)

        if cue in ("threats", "personal_info", "too_good_true"):
            # desk + complex job → more aware of account-based lures
            if self.job_type == 1 and self.job_complexity > 3:
                return max(0.0, base - 0.08)

        return base

    # -------------------------------------------------------------------------
    # Workday progression
    # -------------------------------------------------------------------------

    def advance_workday(self, hour: float):
        """
        Simulate state at a given hour of the workday (8am–5pm).
        time_pressure and workload ramp up linearly across the day.
        """
        progress = max(0.0, min(1.0, (hour - 8) / 9))  # 0 at 8am, 1 at 5pm
        self.time_pressure = 1.0 + 4.0 * progress       # 1 → 5
        self.workload = 1.5 + 3.5 * progress             # 1.5 → 5

    # -------------------------------------------------------------------------
    # Factory
    # -------------------------------------------------------------------------

    @classmethod
    def random_agent(cls, agent_id: str, seed: int = None) -> "Agent":
        """Generate a random but demographically plausible agent."""
        rng = random.Random(seed)
        return cls(
            agent_id=agent_id,
            age=rng.uniform(22, 60),
            gender=rng.choice([0, 1]),
            education_level=rng.uniform(1, 5),
            tenure=rng.uniform(0.5, 20),
            job_type=rng.choice([0, 1]),
            job_complexity=rng.uniform(1, 5),
            sleep_quality=rng.uniform(1, 5),
            subjective_health=rng.uniform(1, 5),
            depression=rng.uniform(1, 3),
            illness=rng.choices([0, 1], weights=[3, 1])[0],  # 25% ill
            stress_avg=rng.uniform(1, 5),
            burnout=rng.uniform(1, 4),
            intrinsic_motivation=rng.uniform(1, 5),
            job_satisfaction=rng.uniform(1, 5),
            role_conflict=rng.uniform(1, 4),
            leave_intention=rng.uniform(1, 4),
            role_ambiguity=rng.uniform(1, 4),
            lack_motivation=rng.uniform(1, 4),
            suspicion_threshold=rng.randint(2, 6),
            max_cues_processed=rng.randint(7, 12),
        )
