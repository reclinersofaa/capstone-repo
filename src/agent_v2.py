"""
agent_v2.py — Unified [0,1] cognitive model for the phishing agent simulation.

This is a NEW, self-contained module. It does NOT modify or import the original
src/agent.py, so notebook 05 and the existing pipeline keep working unchanged.

What changed vs. the original Agent (and why)
---------------------------------------------
The original model was a 3-part hybrid on mixed scales (KSS 1-9 + Tian ED 1-5 +
f_dynamic) whose workday curve came out FLAT/decreasing: the Åkerstedt circadian
term makes agents MORE alert in the late afternoon (peak ~4:48pm), cancelling the
JD-R accumulation. In the shipped results, click rate correlated +0.98 with the
(fixed, arbitrary) suspicion_threshold but only -0.06 with fatigue and -0.05 with
FPL (wrong sign). In other words the cognitive machinery didn't move outcomes.

AgentV2 rebuilds the model on a single normalized [0,1] scale so that fatigue is
monotone across the workday and actually drives clicks:

  ED(t)        = dynamic energy depletion from Workload/TimePressure/TaskSwitching/JobComplexity
                 (RISES across the day — the key lever the static ED lacked)
  F_base       = sleep-debt baseline (duration + quality)          [Van Dongen dose-response]
  F_dynamic    = accumulates ED - Recovery each tick (dt-scaled)   [Bakker & Demerouti JD-R]
  TotalFatigue = noisy-OR(F_base, F_dynamic)   — circadian DROPPED (it caused the flat curve)
  JP           = weighted geometric mean of (1-Fatigue), Motivation, RoleClarity
  FPL          = TotalFatigue * (1-JP) * (1 - λ_pv * PerceivedVulnerability)
  P_click      = centered sigmoid reporting index (fixes the sigmoid(0)=0.5 bug)
  threshold    = base (per-agent) + drift(fatigue, time-pressure)  — PARTLY DYNAMIC

All coefficients marked "modeling choice" below are OUR tuning choices, numerically
constrained to keep every quantity in [0,1] and the workday curve monotone. They are
NOT taken from any paper. Literature only motivates the STRUCTURE and the signs.

Every method mirrors the original Agent's public interface (compute_total_fatigue,
compute_job_performance, compute_flawed_perception_level, get_cue_fpl, advance_workday),
so src/decision_loop.simulate_email works with an AgentV2 with no changes.
"""

import math
import random
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Cue salience — how hard each cue is to MISS. Higher strength -> lower miss prob.
# (Unchanged from the original model; kept here so v2 is self-contained.)
# ---------------------------------------------------------------------------
_CUE_STRENGTH: dict = {
    "suspicious_link":   0.8,
    "suspicious_sender": 0.8,
    "personal_info":     0.7,
    "threats":           0.7,
    "urgency":           0.6,
    "too_good_true":     0.6,
    "emotional_appeal":  0.5,
    "generic_greeting":  0.4,
    "spelling_grammar":  0.4,
}

# ---------------------------------------------------------------------------
# Model constants (all modeling choices; tuned for [0,1] bounds + monotonicity).
# Exposed at module level so the notebook can display / sweep them.
# ---------------------------------------------------------------------------
# Energy Depletion weights: ED = w_W*W + w_TP*TP + w_TS*TS + w_JC*JC + w_int*(W*TP)
ED_W_WORKLOAD      = 0.30
ED_W_TIMEPRESSURE  = 0.25
ED_W_TASKSWITCH    = 0.15
ED_W_JOBCOMPLEXITY = 0.10
ED_W_INTERACTION   = 0.20   # compounding-demands interaction (JD-R)

# Intraday demand ramps (defined directly in [0,1]); p = (hour-8)/8, 8am..4pm.
WORKLOAD_LO,  WORKLOAD_HI  = 0.30, 0.85
TIMEPRES_LO,  TIMEPRES_HI  = 0.20, 0.90

# Fatigue accumulation
FDYN_DT        = 0.22   # forward-Euler step; ~2/9. Fixes the "saturates to 1.0" bug.
RECOVERY_RATE  = 0.15   # JD-R resource recovery gain

# Sleep baseline: F_base = F1*SleepFactor + F2*QualityFactor
FBASE_W_DURATION = 0.40
FBASE_W_QUALITY  = 0.20
SLEEP_GOOD_HRS   = 8.0   # >= this -> zero sleep debt
SLEEP_BAD_HRS    = 4.0   # <= this -> full sleep debt

# Job performance geometric-mean exponents (sum to 1 -> output stays in [0,1])
JP_EXP_FATIGUE   = 0.50
JP_EXP_MOTIV     = 0.30
JP_EXP_ROLECLAR  = 0.20
JP_TRAIT_FLOOR   = 0.10   # floor on Mot/RC so a zero-trait agent isn't annihilated

# Flawed Perception Level
FPL_LAMBDA_PV    = 0.70   # protective strength of Perceived Vulnerability
CUE_FPL_FLOOR    = 0.02   # universal — even a blatant cue is occasionally missed
CUE_FPL_CAP      = 0.90   # no cue is ever un-catchable
URL_AGE_PENALTY  = 0.12   # max extra miss on URL cues for the oldest agent
URL_EDU_PENALTY  = 0.10   # max extra miss on URL cues for the least-educated agent
EXPOSURE_BONUS   = 0.05   # desk+complex-job familiarity with account-threat cues

# Reporting index (out-of-loop; does NOT drive the decision)
PCLICK_SLOPE     = 6.0    # logistic slope b
PCLICK_CENTER    = 0.34   # FPL0 — re-center to empirical median once fatigue/JP freeze

# Base suspicion threshold: drawn CONTINUOUS in [1.0, 5.5] (not integer). The decision
# loop compares an integer cue counter with `>=`, so the *effective* morning threshold
# is ceil(base) — spanning 2..6 as in the original model. Drawing base continuously
# (rather than as an integer) means different agents cross their next integer boundary
# at different points in the day, which smears the discrete threshold steps into a
# smooth aggregate workday curve instead of one synchronized jump.
BASE_THRESHOLD_LO = 1.0
BASE_THRESHOLD_HI = 5.5

# Partly-dynamic suspicion threshold:
#   T(t) = clamp(base + DRIFT_K * F_dynamic, T_MIN, T_MAX)
# Driven by F_dynamic — the within-day ACCUMULATED depletion, which is reset to ~0
# each morning and rises to ~0.5 by 4pm. So at 8am the threshold ≈ the agent's base
# value (believable morning rates + a real false-positive rate) and it climbs
# monotonically through the day: by late afternoon a depleted agent needs ~1
# additional red flag before they will stop and report. This is the second channel
# (alongside FPL) through which cognitive state drives the workday curve, and using
# F_dynamic (not total load) avoids any morning-dip artifact.
THRESHOLD_DRIFT_K = 2.0
THRESHOLD_MIN     = 2.0
THRESHOLD_MAX     = 7.0


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


@dataclass
class AgentV2:
    # --- Identity ---
    agent_id: str

    # --- Stable demographic traits ---
    age: float             # 22-60
    gender: float          # 0/1 — demographics only, NOT used in any formula
    education_level: float # 1-5
    tenure: float          # years
    job_type: float        # 0 = non-desk, 1 = desk
    job_complexity: float  # 1-5

    # --- Fatigue inputs (personal baselines) ---
    sleep_quality: float     # 1-5
    total_sleep_time: float  # hours slept last night (NOW randomized per agent)
    subjective_health: float # 1-5
    depression: float        # 1-5
    illness: float           # 0/1
    stress_avg: float        # 1-5

    # --- Job performance inputs ---
    intrinsic_motivation: float # 1-5  (Motivation in JP)
    role_ambiguity: float       # 1-5  (RoleClarity = 1 - normalized ambiguity)
    # NOTE: burnout/job_satisfaction/role_conflict/leave_intention/lack_motivation
    # are retained on the dataclass for the optional regression-JP sensitivity
    # comparison, but the v2 geometric JP does not use them.
    burnout: float = 2.0
    job_satisfaction: float = 3.0
    role_conflict: float = 2.0
    leave_intention: float = 2.0
    lack_motivation: float = 2.0

    # --- NEW v2 traits ---
    task_switching: float = 0.4        # [0,1] job-demand trait (interruptions/context-switches)
    perceived_vulnerability: float = 0.5  # [0,1] dispositional threat vigilance (Shin-Carley's strongest predictor)

    # --- Behaviour ---
    base_suspicion_threshold: float = 4.0  # 2-6, per-agent baseline
    max_cues_processed: int = 9            # 7-12

    # --- Workday-dynamic state (mutated by advance_workday) ---
    current_hour: float = 8.0
    workload: float = WORKLOAD_LO         # [0,1] in v2 (NOT the 1-5 scale of the old model)
    time_pressure: float = TIMEPRES_LO    # [0,1] in v2
    f_dynamic: float = 0.0                # accumulated situational depletion [0,1]
    suspicion_threshold: float = 4.0      # dynamic; set each tick by advance_workday

    # -------------------------------------------------------------------------
    # Energy Depletion (dynamic) — the key lever the static Tian ED lacked
    # -------------------------------------------------------------------------
    def compute_energy_depletion(self) -> float:
        """
        ED(t) = w_W*W + w_TP*TP + w_TS*TS + w_JC*JC_norm + w_int*(W*TP), clamped [0,1].

        W and TP are dynamic (ramp across the workday), so ED RISES through the day —
        this is what turns the old flat/decreasing fatigue curve into a monotone rise.
        A hard clamp is used (not a sigmoid): weights sum to 1.0 so the linear form is
        already bounded, and a sigmoid would compress the dynamic range.
        """
        jc_norm = (self.job_complexity - 1.0) / 4.0
        W, TP, TS = self.workload, self.time_pressure, self.task_switching
        ed = (
            ED_W_WORKLOAD * W
            + ED_W_TIMEPRESSURE * TP
            + ED_W_TASKSWITCH * TS
            + ED_W_JOBCOMPLEXITY * jc_norm
            + ED_W_INTERACTION * (W * TP)
        )
        return _clamp(ed, 0.0, 1.0)

    # -------------------------------------------------------------------------
    # Sleep baseline fatigue (static per agent) — Van Dongen dose-response
    # -------------------------------------------------------------------------
    def compute_f_base(self) -> float:
        """
        F_base = F1*SleepFactor + F2*QualityFactor, in [0, 0.60] (practical [0,0.50]).
          SleepFactor   = (8 - sleep_hours)/4 clamped [0,1]   (8h -> 0, 4h -> 1)
          QualityFactor = 1 - (sleep_quality-1)/4             (good quality -> 0)
        """
        sleep_factor = _clamp(
            (SLEEP_GOOD_HRS - self.total_sleep_time) / (SLEEP_GOOD_HRS - SLEEP_BAD_HRS),
            0.0, 1.0,
        )
        quality_norm = (self.sleep_quality - 1.0) / 4.0
        quality_factor = 1.0 - quality_norm
        return _clamp(FBASE_W_DURATION * sleep_factor + FBASE_W_QUALITY * quality_factor, 0.0, 1.0)

    # -------------------------------------------------------------------------
    # Total fatigue — noisy-OR combine (no circadian term)
    # -------------------------------------------------------------------------
    def compute_total_fatigue(self) -> float:
        """
        TotalFatigue = F_base + F_dynamic - F_base*F_dynamic   (noisy-OR), in [0,1].

        Noisy-OR (not a plain sum) keeps the result bounded WITHOUT a clamp and
        preserves dynamic range: a plain sum drives poor-sleep agents to the 1.0
        ceiling in the afternoon and destroys the very spread we want.
        The circadian (Åkerstedt) term is deliberately removed — it was the measured
        cause of the flat/decreasing workday curve.
        """
        fb = self.compute_f_base()
        fd = self.f_dynamic
        return _clamp(fb + fd - fb * fd, 0.0, 1.0)

    # -------------------------------------------------------------------------
    # Job performance — weighted geometric mean (restores dynamic range)
    # -------------------------------------------------------------------------
    def compute_job_performance(self) -> float:
        """
        JP = (1-Fat)^0.50 * (0.1+0.9*Mot)^0.30 * (0.1+0.9*RC)^0.20, in [0,1].

        Exponents sum to 1 -> a geometric mean of [0,1] factors is itself in [0,1]
        (no clamp/sigmoid needed). The old multiplicative product (1-Fat)*Mot*RC
        compressed JP into ~[0.05,0.39]; this restores it to ~[0,0.95].
        (1-Fat) is NOT floored, so full exhaustion can still drive JP->0.
        """
        fat = self.compute_total_fatigue()
        mot = (self.intrinsic_motivation - 1.0) / 4.0
        rc = 1.0 - (self.role_ambiguity - 1.0) / 4.0
        vit = max(0.0, 1.0 - fat) ** JP_EXP_FATIGUE                 # NaN-guarded
        m = (JP_TRAIT_FLOOR + (1 - JP_TRAIT_FLOOR) * mot) ** JP_EXP_MOTIV
        r = (JP_TRAIT_FLOOR + (1 - JP_TRAIT_FLOOR) * rc) ** JP_EXP_ROLECLAR
        return _clamp(vit * m * r, 0.0, 1.0)

    def compute_job_performance_regression(self) -> float:
        """
        OPTIONAL sensitivity comparison — the original two-regression JP (Rehman 2015 +
        Basit & Hassan 2017) on a 1-5 scale, provided so the notebook can contrast the
        geometric form against the old one. NOT used by the decision loop.
        """
        jp1 = (2.766 - 0.106 * self.burnout + 0.301 * self.intrinsic_motivation
               + 0.298 * self.job_satisfaction - 0.153 * self.role_conflict
               - 0.076 * self.leave_intention)
        # time_pressure/workload are [0,1] in v2 -> rescale to ~1-5 for this legacy form
        tp5 = 1.0 + 4.0 * self.time_pressure
        wl5 = 1.0 + 4.0 * self.workload
        jp2 = (3.238 - 0.022 * tp5 - 0.086 * wl5 - 0.141 * self.lack_motivation
               - 0.155 * self.role_ambiguity)
        return (jp1 + jp2) / 2.0 - 0.34 * (1.0 + 4.0 * self.compute_total_fatigue())

    # -------------------------------------------------------------------------
    # Flawed Perception Level — now includes Perceived Vulnerability
    # -------------------------------------------------------------------------
    def compute_flawed_perception_level(self) -> float:
        """
        FPL_base = TotalFatigue * (1-JP) * (1 - λ_pv*PV), in [0,1].

        PV enters PROTECTIVELY (higher perceived vulnerability -> more caution ->
        lower miss probability), matching the Shin-Carley regression sign (Damage
        falls with PV) and Protection Motivation Theory. This is the strongest
        cognitive modifier and was entirely absent from the original model.
        """
        fat = self.compute_total_fatigue()
        jp = self.compute_job_performance()
        pv = self.perceived_vulnerability
        fpl = fat * (1.0 - jp) * (1.0 - FPL_LAMBDA_PV * pv)
        return _clamp(fpl, 0.0, 1.0)

    def get_cue_fpl(self, cue: str) -> float:
        """
        Per-cue miss probability consumed by the decision loop:
            cue_fpl = FPL_base * (1 - CueStrength[cue])  + URL/exposure trait modifiers
        Clamped to a UNIVERSAL floor (0.02) and cap (0.90) so no cue is ever certainly
        seen or certainly missed.
        """
        base = self.compute_flawed_perception_level()
        cue_strength = _CUE_STRENGTH.get(cue, 0.5)
        adjusted = base * (1.0 - cue_strength)

        if cue in ("suspicious_link", "suspicious_sender"):
            age01 = _clamp((self.age - 22.0) / 38.0, 0.0, 1.0)
            edu01 = _clamp((self.education_level - 1.0) / 4.0, 0.0, 1.0)
            adjusted += URL_AGE_PENALTY * age01 + URL_EDU_PENALTY * (1.0 - edu01)
        elif cue in ("threats", "personal_info", "too_good_true"):
            if self.job_type == 1 and self.job_complexity > 3:
                adjusted -= EXPOSURE_BONUS

        return _clamp(adjusted, CUE_FPL_FLOOR, CUE_FPL_CAP)

    # -------------------------------------------------------------------------
    # Reporting index — centered sigmoid (fixes sigmoid(0)=0.5). OUT OF LOOP.
    # -------------------------------------------------------------------------
    def compute_agent_fpl(self) -> float:
        """CueStrength-free cognitive-state index: TotalFatigue*(1-JP), in [0,1]."""
        return _clamp(self.compute_total_fatigue() * (1.0 - self.compute_job_performance()), 0.0, 1.0)

    def compute_p_click(self) -> float:
        """
        Agent-level click propensity for reporting/plots (does NOT drive the decision):
            P_click = sigmoid(b*(FPL_agent - FPL0))
        Centered so a perfect agent (FPL_agent=0) no longer reads 0.5.
        """
        return _sigmoid(PCLICK_SLOPE * (self.compute_agent_fpl() - PCLICK_CENTER))

    # -------------------------------------------------------------------------
    # Workday progression: ramps + accumulation + dynamic threshold
    # -------------------------------------------------------------------------
    def _ramps_at(self, hour: float):
        """Workload and TimePressure at a given hour, both in [0,1]."""
        p = _clamp((hour - 8.0) / 8.0, 0.0, 1.0)   # 0 at 8am, 1 at 4pm (8-hour day)
        w = WORKLOAD_LO + (WORKLOAD_HI - WORKLOAD_LO) * p
        tp = TIMEPRES_LO + (TIMEPRES_HI - TIMEPRES_LO) * p
        return w, tp

    def advance_workday(self, hour: float):
        """
        Set the agent's cognitive state at `hour` (8am-4pm).

        F_dynamic is computed by INTEGRATING depletion forward from 8am to `hour` over
        2-hour ticks (left-Riemann), so it is order-independent and free of the
        double-count that a stateful per-call accumulator suffers. Crucially this makes
        F_dynamic == 0 exactly at 8am: an agent starts the day fresh (fatigue = sleep
        debt only, suspicion threshold = base), and depletion accrues through the day.
        """
        self.current_hour = hour
        jc_norm = (self.job_complexity - 1.0) / 4.0
        ts = self.task_switching

        fd = 0.0
        t = 8.0
        while t < hour - 1e-9:                       # ticks: 8->10, 10->12, ... up to `hour`
            w, tp = self._ramps_at(t)                # demands at the tick's start
            ed = _clamp(
                ED_W_WORKLOAD * w + ED_W_TIMEPRESSURE * tp + ED_W_TASKSWITCH * ts
                + ED_W_JOBCOMPLEXITY * jc_norm + ED_W_INTERACTION * (w * tp), 0.0, 1.0)
            recovery = RECOVERY_RATE * (1.0 - w) * (1.0 - fd)
            recovery = min(recovery, ed)             # never recover more than the tick depletes
            fd = _clamp(fd + FDYN_DT * (ed - recovery), 0.0, 1.0)
            t += 2.0
        self.f_dynamic = fd

        # Current-hour demand levels (for ED logging downstream)
        self.workload, self.time_pressure = self._ramps_at(hour)

        # Partly-dynamic threshold: within-day accumulated depletion (F_dynamic) raises
        # the bar for reporting (a second channel for cognitive state alongside FPL).
        # F_dynamic == 0 at 8am -> threshold == base at the start of the day.
        self.suspicion_threshold = _clamp(
            self.base_suspicion_threshold + THRESHOLD_DRIFT_K * self.f_dynamic,
            THRESHOLD_MIN, THRESHOLD_MAX,
        )

    def reset_workday(self):
        """Reset to the start of a fresh day (F_dynamic == 0 at 8am)."""
        self.advance_workday(8.0)

    # -------------------------------------------------------------------------
    # Factory — independent draw (for spot-checks; correlated batch is preferred)
    # -------------------------------------------------------------------------
    @classmethod
    def random_agent(cls, agent_id: str, seed: int = None) -> "AgentV2":
        rng = random.Random(seed)
        jc = rng.uniform(1, 5)
        jt = rng.choice([0, 1])
        agent = cls(
            agent_id=agent_id,
            age=rng.uniform(22, 60),
            gender=rng.choice([0, 1]),
            education_level=rng.uniform(1, 5),
            tenure=rng.uniform(0.5, 20),
            job_type=jt,
            job_complexity=jc,
            sleep_quality=rng.uniform(1, 5),
            total_sleep_time=rng.uniform(5.5, 8.5),   # NOW randomized
            subjective_health=rng.uniform(1, 5),
            depression=rng.uniform(1, 3),
            illness=rng.choices([0, 1], weights=[3, 1])[0],
            stress_avg=rng.uniform(1, 5),
            intrinsic_motivation=rng.uniform(1, 5),
            role_ambiguity=rng.uniform(1, 4),
            burnout=rng.uniform(1, 4),
            job_satisfaction=rng.uniform(1, 5),
            role_conflict=rng.uniform(1, 4),
            leave_intention=rng.uniform(1, 4),
            lack_motivation=rng.uniform(1, 4),
            perceived_vulnerability=rng.uniform(0, 1),
            base_suspicion_threshold=rng.uniform(BASE_THRESHOLD_LO, BASE_THRESHOLD_HI),
            max_cues_processed=rng.randint(7, 12),
        )
        agent.task_switching = _clamp(
            0.25 + 0.40 * ((jc - 1) / 4) + 0.10 * jt + rng.gauss(0, 0.10), 0.0, 1.0
        )
        agent.reset_workday()
        return agent


# ===========================================================================
# Correlated agent generation — Gaussian copula
# ===========================================================================
# The original factory draws ~18 traits INDEPENDENTLY, which produces incoherent
# agents (e.g. max burnout + max motivation + max job-satisfaction). A Gaussian
# copula draws a correlated normal vector, maps it through the normal CDF to
# uniforms, then to each trait's existing range — so the MARGINAL ranges are
# preserved exactly while realistic between-trait correlations are imposed.
#
# NOTE: only a subset of these traits drives v2 outcomes (sleep, job_complexity,
# motivation, role_ambiguity, age, education, task_switching, perceived_vulnerability).
# The strain/attitude cluster is correlated for agent coherence and for the optional
# regression-JP comparison; correlating a trait that feeds no formula changes
# outcomes by zero (it is descriptive realism only).

# Continuous trait order for the copula
_COPULA_TRAITS = [
    "stress_avg", "burnout", "depression", "sleep_quality", "subjective_health",
    "intrinsic_motivation", "job_satisfaction", "leave_intention", "role_conflict",
    "role_ambiguity", "lack_motivation", "job_complexity", "education_level",
    "age", "tenure", "total_sleep_time", "perceived_vulnerability",
]
_COPULA_RANGES = {
    "stress_avg": (1, 5), "burnout": (1, 4), "depression": (1, 3),
    "sleep_quality": (1, 5), "subjective_health": (1, 5),
    "intrinsic_motivation": (1, 5), "job_satisfaction": (1, 5),
    "leave_intention": (1, 4), "role_conflict": (1, 4), "role_ambiguity": (1, 4),
    "lack_motivation": (1, 4), "job_complexity": (1, 5), "education_level": (1, 5),
    "age": (22, 60), "tenure": (0.5, 20), "total_sleep_time": (5.5, 8.5),
    "perceived_vulnerability": (0, 1),
}
# Target correlations (modeling choices; magnitudes are literature-plausible, not exact).
_COPULA_CORR = {
    # strain core
    ("stress_avg", "burnout"): 0.60, ("stress_avg", "depression"): 0.45,
    ("stress_avg", "sleep_quality"): -0.40, ("stress_avg", "subjective_health"): -0.35,
    ("stress_avg", "job_satisfaction"): -0.30, ("stress_avg", "role_conflict"): 0.40,
    ("stress_avg", "role_ambiguity"): 0.35, ("stress_avg", "leave_intention"): 0.30,
    ("stress_avg", "intrinsic_motivation"): -0.15, ("stress_avg", "lack_motivation"): 0.25,
    ("stress_avg", "job_complexity"): 0.20,
    ("burnout", "depression"): 0.50, ("burnout", "sleep_quality"): -0.35,
    ("burnout", "subjective_health"): -0.40, ("burnout", "intrinsic_motivation"): -0.35,
    ("burnout", "job_satisfaction"): -0.45, ("burnout", "leave_intention"): 0.45,
    ("burnout", "role_conflict"): 0.40, ("burnout", "role_ambiguity"): 0.35,
    ("burnout", "lack_motivation"): 0.40,
    ("depression", "sleep_quality"): -0.45, ("depression", "subjective_health"): -0.45,
    ("depression", "job_satisfaction"): -0.30, ("depression", "lack_motivation"): 0.30,
    ("depression", "intrinsic_motivation"): -0.25,
    ("sleep_quality", "subjective_health"): 0.35, ("sleep_quality", "job_satisfaction"): 0.15,
    ("subjective_health", "job_satisfaction"): 0.15,
    # motivation / attitude
    ("intrinsic_motivation", "job_satisfaction"): 0.50,
    ("intrinsic_motivation", "leave_intention"): -0.40,
    ("intrinsic_motivation", "lack_motivation"): -0.60,
    ("intrinsic_motivation", "role_ambiguity"): -0.20,
    ("intrinsic_motivation", "job_complexity"): 0.15,
    ("job_satisfaction", "leave_intention"): -0.55, ("job_satisfaction", "role_conflict"): -0.30,
    ("job_satisfaction", "role_ambiguity"): -0.30, ("job_satisfaction", "lack_motivation"): -0.40,
    ("leave_intention", "lack_motivation"): 0.35, ("leave_intention", "role_conflict"): 0.25,
    ("role_conflict", "role_ambiguity"): 0.45, ("role_conflict", "lack_motivation"): 0.20,
    ("role_ambiguity", "lack_motivation"): 0.25,
    # demographic / job design
    ("job_complexity", "education_level"): 0.40, ("education_level", "age"): 0.10,
    ("age", "tenure"): 0.55,
    # new traits
    ("total_sleep_time", "sleep_quality"): 0.50, ("total_sleep_time", "stress_avg"): -0.30,
    ("total_sleep_time", "depression"): -0.30, ("total_sleep_time", "burnout"): -0.25,
    ("perceived_vulnerability", "education_level"): 0.35,
    ("perceived_vulnerability", "tenure"): 0.25,
    ("perceived_vulnerability", "subjective_health"): 0.20,
}


def build_correlation_matrix():
    """Return (trait_names, R) — a symmetric PSD correlation matrix for the copula."""
    import numpy as np
    k = len(_COPULA_TRAITS)
    idx = {t: i for i, t in enumerate(_COPULA_TRAITS)}
    R = np.eye(k)
    for (a, b), v in _COPULA_CORR.items():
        i, j = idx[a], idx[b]
        R[i, j] = R[j, i] = v
    # Guard: project to nearest PSD via eigenvalue clipping if needed.
    w = np.linalg.eigvalsh(R)
    if w.min() < 1e-8:
        vals, vecs = np.linalg.eigh(R)
        vals = np.clip(vals, 1e-6, None)
        R = vecs @ np.diag(vals) @ vecs.T
        d = np.sqrt(np.diag(R))
        R = R / np.outer(d, d)   # renormalize to unit diagonal
    return _COPULA_TRAITS, R


def build_correlated_agents(n: int, seed: int = 42) -> list:
    """
    Generate `n` AgentV2 objects with correlated traits via a Gaussian copula.

    Continuous traits are drawn from a correlated multivariate normal, mapped to
    uniforms through the normal CDF, then to each trait's existing range (marginals
    preserved exactly). Discrete traits (job_type, gender, illness, thresholds) are
    drawn independently; task_switching is derived from job_complexity/job_type.
    """
    import numpy as np
    names, R = build_correlation_matrix()
    k = len(names)
    rng = np.random.default_rng(seed)
    prng = random.Random(seed + 1)

    L = np.linalg.cholesky(R)
    Z = rng.standard_normal((n, k)) @ L.T                     # rows ~ N(0, R)
    Phi = np.vectorize(lambda z: 0.5 * (1.0 + math.erf(z / math.sqrt(2.0))))
    U = Phi(Z)                                                # -> uniforms in (0,1)

    agents = []
    for a in range(n):
        vals = {}
        for j, name in enumerate(names):
            lo, hi = _COPULA_RANGES[name]
            vals[name] = lo + (hi - lo) * float(U[a, j])
        jt = prng.choice([0, 1])
        jc = vals["job_complexity"]
        agent = AgentV2(
            agent_id=f"agentv2_{a:03d}",
            age=vals["age"], gender=prng.choice([0, 1]),
            education_level=vals["education_level"], tenure=vals["tenure"],
            job_type=jt, job_complexity=jc,
            sleep_quality=vals["sleep_quality"], total_sleep_time=vals["total_sleep_time"],
            subjective_health=vals["subjective_health"], depression=vals["depression"],
            illness=prng.choices([0, 1], weights=[3, 1])[0], stress_avg=vals["stress_avg"],
            intrinsic_motivation=vals["intrinsic_motivation"], role_ambiguity=vals["role_ambiguity"],
            burnout=vals["burnout"], job_satisfaction=vals["job_satisfaction"],
            role_conflict=vals["role_conflict"], leave_intention=vals["leave_intention"],
            lack_motivation=vals["lack_motivation"],
            perceived_vulnerability=vals["perceived_vulnerability"],
            base_suspicion_threshold=prng.uniform(BASE_THRESHOLD_LO, BASE_THRESHOLD_HI),
            max_cues_processed=prng.randint(7, 12),
        )
        agent.task_switching = _clamp(
            0.25 + 0.40 * ((jc - 1) / 4) + 0.10 * jt + prng.gauss(0, 0.10), 0.0, 1.0
        )
        agent.reset_workday()
        agents.append(agent)
    return agents


# ===========================================================================
# v2 simulation runner (reuses the existing decision loop, cache-first cues)
# ===========================================================================
def run_simulation_v2(
    emails_csv: str = "data/processed/master_emails.csv",
    n_agents: int = 30,
    workday_hours: list = None,
    seed: int = 42,
    cache_dir: str = "data/cue_cache",
    correlated: bool = True,
    extractor: str = "ollama",
    ollama_model: str = "llama3.1:8b",
    groq_model: str = "meta-llama/llama-4-scout-17b-16e-instruct",
):
    """
    Full v2 pipeline. Cache-first cue extraction (no Ollama call if cache exists),
    correlated AgentV2 agents, the UNCHANGED per-cue decision loop, and extra logged
    columns for the v2 analysis (perceived_vulnerability, base/dynamic threshold,
    energy_depletion, f_dynamic, p_click).
    """
    import pandas as pd
    from .decision_loop import simulate_email

    if workday_hours is None:
        workday_hours = [8.0, 10.0, 12.0, 14.0, 16.0]

    emails = pd.read_csv(emails_csv)
    if extractor == "groq":
        from .groq_client import GroqExtractor
        _ext = GroqExtractor(cache_dir=cache_dir, model=groq_model)
    else:
        from .ollama_extractor import OllamaExtractor
        _ext = OllamaExtractor(model=ollama_model, cache_dir=cache_dir)
    print(f"Step 1 — cue extraction ({extractor}, cache-first) for {len(emails)} emails...")
    email_cues = _ext.extract_batch(emails)

    print(f"Step 2 — building {n_agents} {'correlated' if correlated else 'independent'} agents...")
    if correlated:
        agents = build_correlated_agents(n_agents, seed=seed)
    else:
        base = random.Random(seed)
        agents = [AgentV2.random_agent(f"agentv2_{i:03d}", seed=base.randint(0, 10_000))
                  for i in range(n_agents)]

    total = n_agents * len(workday_hours) * len(emails)
    print(f"Step 3 — simulating {n_agents} x {len(workday_hours)} x {len(emails)} = {total} decisions...")
    master_rng = random.Random(seed)
    records = []
    for agent in agents:
        agent.reset_workday()
        for hour in workday_hours:
            agent.advance_workday(hour)
            loop_rng = random.Random(master_rng.randint(0, 1_000_000))
            ed = agent.compute_energy_depletion()
            pv = agent.perceived_vulnerability
            p_click = agent.compute_p_click()
            for _, row in emails.iterrows():
                eid = row["email_id"]
                cues = email_cues.get(eid, [])
                result = simulate_email(agent, cues, rng=loop_rng)
                records.append({
                    "agent_id": agent.agent_id,
                    "email_id": eid,
                    "source": row["source"],
                    "actual_class": row["actual_class"],
                    "workday_hour": hour,
                    "base_suspicion_threshold": agent.base_suspicion_threshold,
                    "suspicion_threshold": round(agent.suspicion_threshold, 3),
                    "max_cues_processed": agent.max_cues_processed,
                    "age": round(agent.age, 1),
                    "education_level": round(agent.education_level, 1),
                    "job_complexity": round(agent.job_complexity, 1),
                    "perceived_vulnerability": round(pv, 3),
                    "energy_depletion": round(ed, 3),
                    "f_dynamic": round(agent.f_dynamic, 3),
                    "p_click": round(p_click, 3),
                    "cues_extracted": len(cues),
                    **result,
                })
    df = pd.DataFrame(records)
    print(f"  Done. {len(df):,} rows.")
    return df

