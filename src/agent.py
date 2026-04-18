import math
import random
from dataclasses import dataclass


@dataclass
class Agent:
    # --- Identity ---
    agent_id: str

    # --- Stable demographic traits ---
    age: float             # years (22–60)
    gender: float          # 0 = female, 1 = male  NOTE: stored for demographics only, NOT used in any formula
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
    intrinsic_motivation: float # 1–5  (also used as psychological empowerment proxy in ED)
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
    current_hour: float = 8.0        # current simulation hour (set by advance_workday)
    f_dynamic: float = 0.0           # accumulated cognitive depletion [0, 1] (Bakker & Demerouti 2007)

    # -------------------------------------------------------------------------
    # Three Process Model (Åkerstedt) — KSS-based fatigue
    # -------------------------------------------------------------------------

    def compute_kss(self) -> float:
        """
        Karolinska Sleepiness Scale via Åkerstedt's Three Process Model.

        KSS = 10.6 - 0.6 * (S + C + U)   [range 1–9; 1=very alert, 9=very sleepy]

        S  — homeostatic alertness: S_t = ha - (ha - S_w) * e^(d * taw)
               ha=14.3, d=-0.0353, S_w derived from sleep quality/duration
        C  — circadian: Ca * cos(2π(tod - p) / 24)
               Ca=2.5, p=16.8 (peak ~4:48 PM; circadian alertness highest in late afternoon)
        U  — ultradian component (simplified to 0)

        Both S and C represent internal alertness — higher value → lower KSS (more alert).
        The circadian trough at ~4:48 AM means agents are least circadian-alert at 8 AM
        and most alert in the late afternoon, consistent with Åkerstedt empirical data.
        """
        taw = max(0.0, self.current_hour - self.time_of_awakening)

        # Homeostatic process — alertness builds from S_w toward ha as waking hours increase
        ha = 14.3
        d = -0.0353
        # S_w: initial alertness at waking. Better sleep → higher starting alertness.
        S_w = max(1.0, min(8.0,
            2.0 + (self.total_sleep_time - 5.0) * 0.30 + (self.sleep_quality - 1.0) * 0.50
        ))
        S = ha - (ha - S_w) * math.exp(d * taw)

        # Circadian process — peaks at 16.8h (4:48 PM), trough at 4.8 AM
        Ca = 2.5
        p = 16.8
        C = Ca * math.cos(2 * math.pi * (self.current_hour - p) / 24)

        kss = 10.6 - 0.6 * (S + C)   # U = 0 (ultradian simplified)
        return max(1.0, min(9.0, kss))

    # -------------------------------------------------------------------------
    # Energy Depletion (Tian et al., 2022)
    # -------------------------------------------------------------------------

    def compute_energy_depletion(self) -> float:
        """
        ED = f(JobComplexity, PsychologicalEmpowerment)

        High job complexity depletes resources; psychological empowerment buffers it.
        Intrinsic motivation is used as the empowerment proxy (Tian et al.).
        Gender is NOT included — it is not a valid physiological predictor in this model.
        """
        psy_emp = self.intrinsic_motivation  # 1–5 scale
        ed = 0.65 * self.job_complexity - 0.20 * psy_emp + 1.80
        return max(1.0, min(5.0, ed))

    # -------------------------------------------------------------------------
    # Composite fatigue
    # -------------------------------------------------------------------------

    def compute_total_fatigue(self) -> float:
        """
        Combines three fatigue components normalised to [1, 5]:
          1. KSS — biological time-of-day fatigue (Åkerstedt TPM)
          2. ED  — static resource depletion from job characteristics (Tian et al. 2022)
          3. f_dynamic — accumulated situational cognitive load (Bakker & Demerouti 2007)

        f_dynamic adds up to +1.0 fatigue unit as it saturates at 1.0.
        """
        kss = self.compute_kss()                    # 1–9
        kss_norm = (kss - 1.0) / 2.0 + 1.0         # maps 1-9 → 1-5
        ed = self.compute_energy_depletion()         # 1–5
        raw = (kss_norm + ed) / 2.0 + self.f_dynamic * 1.0
        return max(1.0, min(5.0, raw))

    # -------------------------------------------------------------------------
    # Job performance (Rehman 2015 + Basit/Hassan 2017)
    # -------------------------------------------------------------------------

    def compute_job_performance(self) -> float:
        """
        JP_final = (JP1 + JP2) / 2  −  crossover_penalty

        JP1 (Rehman et al.): macro psychological state
        JP2 (Basit & Hassan): micro situational stressors (time_pressure, workload are dynamic)
        Crossover penalty (Hassan & Morsy): −2.442 per point on 0–10 fatigue scale,
            scaled to our 1–5 fatigue range → coefficient ≈ 0.34 per unit.
        """
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
        overall = (jp1 + jp2) / 2.0
        # Crossover penalty: fatigue degrades job performance
        # Original: −2.442/point on 0–10 scale, 0–72 JP. Scaled to our 1–5 fatigue, ~1–4 JP range.
        return overall - (0.34 * self.compute_total_fatigue())

    # -------------------------------------------------------------------------
    # Flawed Perception Level (Shonman / ACT-R / IBLT)
    # -------------------------------------------------------------------------

    def compute_flawed_perception_level(self) -> float:
        """
        P(Misclassification) = FPL  [0.0, 0.5]

        0.0 = perfect observer; 0.5 = guessing at random (Signal Detection Theory).
        FPL rises with fatigue (KSS-based) and falls with job performance.
        The time-varying nature of compute_total_fatigue() means FPL genuinely
        changes across the workday.
        """
        fatigue = self.compute_total_fatigue()   # 1–5
        jp = self.compute_job_performance()

        fatigue_norm = (fatigue - 1.0) / 4.0          # → [0, 1]
        jp_norm = max(0.0, min(1.0, jp / 4.0))        # → [0, 1], higher = better

        fpl = 0.5 * fatigue_norm * (1.0 - jp_norm)
        return max(0.0, min(0.5, fpl))

    # Perceptibility of each cue type: 0.0 = nearly invisible, 1.0 = unmissable.
    # High-strength cues (concrete, verifiable) reduce FPL — agents are harder to fool.
    # Low-strength cues (subtle, contextual) leave FPL near baseline — easy to miss.
    # This is the mechanism by which V-Triad (few, low-strength cues) achieves higher click rates
    # than plain LLM (many, high-strength cues like urgency/threats).
    _CUE_STRENGTH: dict = {
        "suspicious_link":   0.8,  # concrete URL check — high digital-literacy signal
        "suspicious_sender": 0.8,  # verifiable domain mismatch
        "personal_info":     0.7,  # explicit credential request — clear policy violation
        "threats":           0.7,  # overt negative consequence language
        "urgency":           0.6,  # deadline pressure — common but salient
        "too_good_true":     0.6,  # prize/reward language — widely known red flag
        "emotional_appeal":  0.5,  # psychological manipulation — moderate subtlety
        "generic_greeting":  0.4,  # impersonal opener — subtle, normal in bulk email
        "spelling_grammar":  0.4,  # linguistic errors — only salient to attentive readers
    }

    def get_cue_fpl(self, cue: str) -> float:
        """
        Trait- and cue-strength-differentiated FPL.

        FPL_cue = base_fpl * (1 - CueStrength[cue])

        High-strength cues (suspicious_link = 0.8) are nearly unmissable — FPL collapses to
        20% of base. Low-strength cues (generic_greeting = 0.4) leave FPL at 60% of base.
        This is why V-Triad emails (few cues, mostly subtle) produce more clicks than
        plain LLM (many cues, mostly overt).

        Trait modifiers applied after CueStrength scaling:
          - Older/less-educated agents: higher FPL on URL cues (digital literacy gap)
          - Desk workers in complex jobs: lower FPL on account-threat cues (exposure effect)
        """
        base = self.compute_flawed_perception_level()
        cue_strength = self._CUE_STRENGTH.get(cue, 0.5)
        adjusted = base * (1.0 - cue_strength)

        if cue in ("suspicious_link", "suspicious_sender"):
            age_pen = max(0.0, (self.age - 30) / 200)
            edu_pen = max(0.0, (3.0 - self.education_level) / 20.0)
            adjusted = min(0.5, adjusted + age_pen + edu_pen)
        elif cue in ("threats", "personal_info", "too_good_true"):
            if self.job_type == 1 and self.job_complexity > 3:
                adjusted = max(0.0, adjusted - 0.04)

        return max(0.0, min(0.5, adjusted))

    # -------------------------------------------------------------------------
    # Workday progression
    # -------------------------------------------------------------------------

    def advance_workday(self, hour: float):
        """
        Simulate agent state at a given hour (8am–5pm).

        1. Updates time_pressure and workload (linear ramp).
        2. Accumulates f_dynamic — situational cognitive depletion (Bakker & Demerouti 2007).
           Depletion rate is driven by workload, time_pressure, and static ED (JD-R model).
           Recovery attenuates when workload is high and f_dynamic is already elevated.
        3. Stores current_hour for compute_kss() / compute_total_fatigue().
        """
        self.current_hour = hour
        progress = max(0.0, min(1.0, (hour - 8.0) / 9.0))  # 0 at 8am, 1 at 5pm
        self.time_pressure = 1.0 + 4.0 * progress            # 1 → 5
        self.workload = 1.5 + 3.5 * progress                  # 1.5 → 5

        # F_dynamic accumulation — Bakker & Demerouti JD-R (2007)
        w_norm  = (self.workload - 1.0) / 4.0        # [0, 1]
        tp_norm = (self.time_pressure - 1.0) / 4.0   # [0, 1]
        ed_norm = (self.compute_energy_depletion() - 1.0) / 4.0  # [0, 1]
        depletion = 0.30 * w_norm + 0.25 * tp_norm + 0.20 * ed_norm + 0.10 * w_norm * tp_norm
        recovery  = 0.15 * (1.0 - w_norm) * (1.0 - self.f_dynamic)
        dt = 2.0 / 9.0   # ~2-hour ticks over a 9-hour day
        self.f_dynamic = max(0.0, min(1.0, self.f_dynamic + dt * (depletion - recovery)))

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
            gender=rng.choice([0, 1]),           # stored for demographics, not used in formulas
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
