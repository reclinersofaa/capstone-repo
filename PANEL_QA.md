# Panel Q&A: defending every design choice

This is prep material, not a document to hand the panel. It answers "where did you
build X, and why does it work that way" for every piece of the simulation, with
exact file:line references so you can pull up the code live if asked. Written so
a cold reader (you, at 11pm before the review) can answer a follow-up without
re-deriving it.

Format: **Q** (what the panel is likely to ask) → **A** (the honest answer) →
**Code** (where to point).

---

## 1. "Where have you actually instantiated these people?"

**A:** Two different places, for two different purposes, and this is a real
distinction you should state up front rather than let the panel discover:

1. **`src/scenarios.py: build_scenario_agents()`** (line 72) — the population behind
   every headline number on the showcase (the 239,250-decision run, `data/simulation_results_v2.csv`).
   Thirty `AgentV2` objects, six departments x five people, built from six hand-set
   department baseline dicts (`DEPARTMENTS`, line 18) plus five **fixed, deterministic
   offsets** per department (`_OFFSETS = [-0.4, -0.2, 0.0, 0.2, 0.4]`, line 59) — not
   random sampling. Same 30 people every run. Agent IDs are `sim_<dept 1-6><person 1-5>`,
   e.g. `sim_11`..`sim_15` = Finance & Accounts Payable, `sim_21`..`sim_25` = IT Service
   Desk, in the order `DEPARTMENTS` is declared.
2. **`src/agent_v2.py: build_correlated_agents()`** (line ~429) — a *different*,
   Gaussian-copula-sampled population, used by the live scorer's generic 30-agent
   default (`server/scorer.py`) and available as an option to `run_simulation_v2()`.
   **Not** used for the headline run. If asked "is this the same 30 people as the
   results," the honest answer is no for the live scorer — say so.

**Why fixed, not random, for the headline run?** Scenario point, not a sample claim.
The docstring at the top of `scenarios.py` is explicit about this: "Randomness in the
simulation is confined to the per-cue decision loop (controlled by seed), and
seed-replication is what the robustness analysis varies." The population is a
*scenario* — "if a workforce looked like this" — not an attempt to approximate a
real company's demographic distribution. If the panel asks "is this representative
of a real org," the answer is no, and the department baseline numbers (age, sleep,
stress, etc. in `DEPARTMENTS`) are **modelling assumptions**, explicitly flagged as
such in the dict's own docstring and in `DEMO_NOTES.md`, not measured data from any
company.

**Also exists, demo-only, separate from the above:** `src/demo_roster.py` loads a
hand-supplied 30-person CSV (`data/scenarios/demo_roster.csv`) for the team-scenario
section on the showcase (`results/demo_scenario_results.csv`). This is a **third**,
separate population, explicitly labelled demo-only and kept out of the main results
(see `DEMO_NOTES.md`). Don't conflate it with `build_scenario_agents()` if asked —
they use different team names (Finance/IT/HR/Marketing/Sales/Operations vs
Finance/IT/HR/Regional Sales/Operations/Customer Support) and different numbers.

---

## 2. "What is 'fatigue' here, mechanically, and why does it rise through the day?"

**A:** Fatigue is a single number in [0,1], built from two independently-computed
pieces that get combined, not simulated as one lump "tiredness" stat.

**Piece 1 — `F_base` (static per agent, set once per day): `compute_f_base()`**
(agent_v2.py:206). A sleep-debt baseline: `F_base = 0.40*SleepFactor + 0.20*QualityFactor`.
`SleepFactor` = `(8 - hours_slept)/4`, clamped to [0,1] — 8+ hours is zero debt, 4 or
fewer hours is maximum debt. This is the Van Dongen dose-response shape (chronic
sleep restriction produces monotone cognitive decline), cited in the module
docstring (agent_v2.py:17). It does **not** change during the day — it's set by
how much sleep the agent got the night before.

**Piece 2 — `F_dynamic` (accumulates across the workday): `advance_workday()`**
(agent_v2.py:337-373). At each 2-hour tick from 8am, `F_dynamic` integrates forward:
`F_dynamic += 0.22 * (EnergyDepletion(t) - Recovery)`, clamped [0,1]. `EnergyDepletion(t)`
(`compute_energy_depletion()`, line 183) is itself a weighted sum of **workload and
time-pressure ramps that rise across the day** (`WORKLOAD_LO→HI = 0.30→0.85`,
`TIMEPRES_LO→HI = 0.20→0.90`, agent_v2.py:64-65), plus task-switching and job
complexity. This is the JD-R (Job Demands-Resources) model (Bakker & Demerouti),
cited at agent_v2.py:19.

**Piece 3 — combine, don't just add: `compute_total_fatigue()`** (agent_v2.py:223).
`TotalFatigue = F_base + F_dynamic - F_base*F_dynamic` — a noisy-OR, not a plain sum.
**Why noisy-OR and not addition?** Said plainly in the docstring: a plain sum drives
poorly-slept agents to the 1.0 ceiling by early afternoon and flattens the very
spread the model needs. Noisy-OR keeps the result bounded in [0,1] without a hard
clamp, and two partial causes (bad sleep + a hard afternoon) compound sub-additively,
the same way "probability A or B" does when A and B aren't independent.

**Why does this matter for the result, and why mention it was rebuilt?** The
module docstring (agent_v2.py:5-16) is unusually candid about this: the *original*
model (before v2) had a circadian alertness term (Åkerstedt) that peaks around
4:48pm, which **fought** the JD-R accumulation and produced a flat-to-decreasing
workday curve — fatigue barely moved outcomes (correlated -0.06 with click,
wrong-signed -0.05 with FPL). V2 deliberately **removes the circadian term** and
keeps only the monotone JD-R accumulation. If asked "why isn't there a circadian
rhythm, real humans do get a second wind," the honest answer: there was one, it
canceled the effect we were trying to measure, and we cut it rather than tune
around it — stated directly in the code comments, not hidden.

**What the fatigue number actually drives (two channels, not one):**
1. `FPL` (see Q3) — fatigue lowers job performance, which raises the chance of
   missing a cue.
2. The suspicion **threshold itself drifts upward** with `F_dynamic` specifically
   (not `TotalFatigue`): `threshold = clamp(base + 2.0*F_dynamic, 2, 7)`
   (agent_v2.py:370-373). By late afternoon a depleted agent needs roughly one
   additional red flag before they'll stop and report, on top of being more likely
   to miss each individual cue. Two independent mechanisms, not double-counting the
   same number — the code comment at agent_v2.py:367-369 explains why `F_dynamic`
   (not total fatigue) drives this: it resets to ~0 each morning and avoids a
   morning-dip artifact that total fatigue (which includes the static sleep term)
   would introduce.

**Current measured size of the effect (say this if asked for a number):** +3.6
percentage points, 8am→4pm, averaged over all 30 agents, positive for 29 of 30
(showcase/index.html section 03). This is **smaller than an earlier reported
effect**; the earlier, larger effect traced to a roster bug (threshold/perceived-
vulnerability values were inverted in one run) — see the honest framing already on
the showcase and in `DEMO_NOTES.md`. If asked "why is the fatigue effect modest,"
say this directly: with every simulated employee sharing the same suspicion
threshold and perceived-vulnerability starting value (see Q4), the effect you're
isolating is real but intentionally small — a larger effect only appears when you
let *baseline* caution vary between people too, which is a different, noisier claim.

---

## 3. "What is FPL and how does a 'click' actually get decided?"

**A:** FPL = Flawed Perception Level, the base probability of missing a red flag,
before any individual cue's own difficulty is factored in.

**`compute_flawed_perception_level()`** (agent_v2.py:276):
`FPL = TotalFatigue * (1 - JP) * (1 - 0.70*PerceivedVulnerability)`.

- `TotalFatigue` — from Q2.
- `JP` (job performance, `compute_job_performance()`, agent_v2.py:240) — a weighted
  geometric mean: `(1-Fatigue)^0.5 * Motivation^0.3 * RoleClarity^0.2`. Geometric,
  not multiplicative-product, specifically because the old multiplicative form
  compressed JP into a narrow [0.05, 0.39] band (said directly in the docstring,
  agent_v2.py:244) — exponents summing to 1 keep a geometric mean of three [0,1]
  factors itself in [0,1] with full dynamic range, no clamp needed.
- `PerceivedVulnerability` (PV) enters **protectively** — higher PV means lower FPL,
  i.e. more caution. This is deliberate and cited: it matches the sign of the
  Shin-Carley regression (PV's effect on "Damage" is negative) and Protection
  Motivation Theory generally (agent_v2.py:281-284). `λ_pv = 0.70` is a tuning
  constant, stated as such — not fit to any dataset.

**Per-cue adjustment: `get_cue_fpl()`** (agent_v2.py:291). FPL is a *base* rate;
each individual cue is easier or harder to miss depending on its inherent salience
(`_CUE_STRENGTH` dict, agent_v2.py:40-50 — e.g. `suspicious_link`/`suspicious_sender`
= 0.8 strength = hard to miss, `spelling_grammar` = 0.4 = easy to miss):
`cue_fpl = FPL_base * (1 - CueStrength[cue])`, then two trait-based nudges (age/
education raise the miss chance for link/sender cues; desk workers with complex
jobs get a small "exposure" discount on threat/personal-info/too-good-true cues —
agent_v2.py:302-308), then floored at 0.02 and capped at 0.90 (agent_v2.py:309) so
no cue is ever completely unmissable or completely uncatchable.

**The decision loop itself: `simulate_email()`** (src/decision_loop.py:5-60). Per
email, per agent, per hour: shuffle the email's extracted cues, walk through up to
`max_cues_processed` of them, for each one draw `random() > cue_fpl` to decide if
it registers, increment a suspicion counter on a hit, stop early if the counter
reaches the agent's current threshold → **"reported"**. If the loop exhausts the
cue list or the cap without crossing threshold → **"clicked"**. The random draw is
seeded (seed=42 for the headline run) so results reproduce exactly.

**Important nuance if pressed:** ground-truth phishing/benign labels **never enter
this function** — the loop only ever sees the extracted cue list. A benign email
with zero cues can never be reported (it's mechanically impossible for suspicion to
rise), which is exactly why benign false-positive rate is 0.0% on the showcase —
that's a structural consequence of the model, not a tuned result.

---

## 4. "Why is perceived vulnerability and the suspicion threshold the SAME for everyone?"

**A:** A deliberate control, not an oversight — and worth stating before it's
challenged. `src/scenarios.py:10-12` (module docstring): "Suspicion threshold and
perceived vulnerability are deliberately the SAME for all 30 employees. Departments
differ in workload, fatigue and job traits only." Every department dict sets
`perceived_vulnerability=0.50, threshold_frac=0.50` (scenarios.py:24, 30, 36, 42, 48,
54) — which maps to `base_suspicion_threshold = 1.0 + 0.50*(5.5-1.0) = 3.25` for
every one of the 30 agents (scenarios.py:99-100, `BASE_THRESHOLD_LO/HI` at
agent_v2.py:107-108).

**Why hold these two constant specifically?** They're the two traits with the
largest documented individual-difference effect on phishing susceptibility
(perceived vulnerability is called out as "Shin-Carley's strongest predictor" at
agent_v2.py:166). If departments varied on these *and* on workload/fatigue/job
traits simultaneously, any workday or department effect you measured would be a
tangle of several causes. Holding PV and threshold fixed isolates the workday/
fatigue/job-trait effect specifically — that's the whole point of this scenario,
and it's why the measured workday effect is modest (Q2) rather than dramatic: it's
the effect of the thing being tested, with the strongest confound removed.

**If asked "but real departments probably DO differ in risk awareness"** — true,
and said as much in the docstring: "any per-team caution profile is left for the
team to specify with citations." This was an earlier, unvalidated version of the
model that over-stated a fatigue effect because of a roster bug that (among other
things) let threshold and PV vary uncontrolled per team — see Q2's note on the
earlier, larger, now-retracted effect size.

---

## 5. "Where do the cues come from, and how do you know the model isn't hallucinating them?"

**A:** `server/scorer.py: extract_cues()` / `src/ollama_extractor.py: OllamaExtractor`.
Local Ollama (`gemma4:12b`) is tried first; if unreachable, a hosted fallback chain
(Groq → Cerebras, `src/llm_providers.py`) runs instead — same prompt, same output
contract. Every one of the 1,595 corpus emails has its cue list **cached** by content
hash (`data/cue_cache_v2/gemma4-12b/cue_<md5 of "subject\nbody">.json`), so the
239,250-decision headline run makes **zero live model calls** — it's deterministic
replay of a committed, inspectable cache. The nine cue categories are fixed and
listed in `server/scorer.py`'s `CUES` map and on the showcase.

**Known, disclosed failure mode (don't let this be a "gotcha" — bring it up first
if it's relevant):** `num_predict`/token-budget-too-small extraction truncation was
a real bug (a cue-rich email's JSON array got cut off mid-list and silently parsed
as `[]`, inverting that email's result) — fixed in `src/ollama_extractor.py`, noted
in CLAUDE.md's "known traps" section. If asked how you know this isn't still
happening: the fix changed "give up on malformed JSON" to "never silently return
empty," and re-verification was done against a deliberately cue-rich test email, not
just a normal one — this is literally what the bootstrap check (`scripts/bootstrap.py`)
exercises with ONE REAL extraction call, specifically so "a key is present" and
"extraction actually works" are never conflated.

**Validator, separate from cue extraction:** `src/phishing_validator.py:
has_attack_path()` — a labeling check, not a cue check. It requires the email to
contain both an action pattern (something asking the reader to do something) and a
destination pattern (a link/address to do it at) before a `hybrid_vtriad` email is
accepted into the corpus as phishing. This fixed a real labeling defect where some
V-Triad-style emails were purely persuasive with no actual attack path and shouldn't
have been labeled phishing at all (see notebook `07_vtriad_validity_fix.ipynb`).

---

## 6. "Why do the phishing links all point to example.com?"

**A:** `example.com` is an IANA/RFC 2606-reserved domain, specifically carved out so
it can appear in documentation and examples and never resolve to anything real. Every
phishing email's link was rewritten to a realistic-looking but inert
`https://<subdomain>.example.com/doc/<hash>` path, so link *realism* doesn't vary
between corpus sources — this controls for "is the link itself a tell" as a
confound, which matters because the model's `suspicious_link` cue partly depends on
how the link looks. `.test` (also RFC 2606 reserved) was tried first and rejected:
the cue extractor flagged `.test` TLDs as inherently suspicious, which would have
biased every email's `suspicious_link` cue by construction. `example.com` doesn't
trigger that false signal.

**If asked "does this inert-link choice change the ranking":** yes, it was checked
directly — a decomposition run (`results/decomposition_v2.csv`) comparing the old
(`.test`) and new (`example.com`) corpus under both the copula and scenario
populations. The corpus fix, not the population choice, was what drove V-Triad's
click rank between the two versions — say this if asked, it's the honest finding,
not a convenient one.

---

## 7. "What's the actual headline number, and what can't you claim from it?"

**A:** Persuasion-guided AI phishing (hybrid_vtriad) ranks **second of seven**
sources by simulated click rate, behind the strongest real-phishing source (ceas08,
94.5%) and ahead of naive/multi-model AI phishing (showcase/index.html section 01,
08). **What this is not:** a claim that AI phishing beats ALL real phishing, or that
the absolute click rates (18–95%) predict real-world click rates — Verizon's DBIR
reports a ~1.4% real-world median; these numbers are an artifact of this model's own
parameterization, not a field prediction. Read the rank order, not the percentages
— this caveat is stated directly on the showcase (section 08, "How to read these
numbers") specifically so it isn't a surprise when the panel pushes on it.

---

## 8. Known, disclosed limitations (bring these up before the panel finds them)

- The workday/fatigue effect (+3.6 pts) is **smaller** than an earlier internal
  version of this result; the larger effect traced to a roster bug, not a genuine
  finding — already corrected, see Q2/Q4.
- Cue extraction coverage on the highlighted-email showcase view is **partial**
  (roughly half of flagged cues get a located text span; the rest show as "cue
  detected, no single phrase located" chips) — the client-side highlighter uses
  regex phrase-matching as an approximation of what the LLM actually flagged, and
  regexes don't catch every phrasing. This is disclosed on the showcase itself
  (dashed "(no phrase located)" chips), not hidden.
- Department baseline traits (age, sleep, stress, etc. in `DEPARTMENTS`) are
  **modelling assumptions**, not measured data from any real organization — stated
  in the docstring and DEMO_NOTES.md.
- The separate demo-roster team scenario (Sales 62.7% down to IT 24.6%) uses a
  **different population** than the headline run and is explicitly kept out of the
  main results — don't let it get conflated with the six-department scenario numbers
  if the panel asks about "the" team breakdown; there are two, for different purposes.
- All model constants (ED weights, FDYN_DT, FPL λ_pv, threshold drift K, etc.) are
  stated directly in the code as **modeling choices**, not fit to any dataset or
  taken from a paper — literature motivates the *structure* and the *sign* of each
  effect, not the exact numbers. If asked "where did 0.70 come from," the honest
  answer is: it's a tuning choice that keeps the quantity in [0,1] and gives the
  sign the cited literature predicts; it was not fit.

---

## 9. Quick map: "show me where X happens" (for live code pull-up)

| Ask | File : line |
|---|---|
| The 30 fixed simulated employees | `src/scenarios.py:72` `build_scenario_agents()` |
| Department baseline traits | `src/scenarios.py:18` `DEPARTMENTS` |
| Energy depletion (rises across the day) | `src/agent_v2.py:183` |
| Sleep-debt baseline | `src/agent_v2.py:206` |
| Total fatigue (noisy-OR) | `src/agent_v2.py:223` |
| Job performance (geometric mean) | `src/agent_v2.py:240` |
| Flawed Perception Level | `src/agent_v2.py:276` |
| Per-cue miss probability | `src/agent_v2.py:291` |
| Threshold drift across the day | `src/agent_v2.py:370` |
| The per-cue decision loop | `src/decision_loop.py:5` |
| Full run orchestration (239,250 decisions) | `src/agent_v2.py:567` `run_simulation_v2()` |
| Cue extraction swapper | `server/scorer.py: extract_cues()` |
| Cue cache | `data/cue_cache_v2/gemma4-12b/` |
| V-Triad labeling validator | `src/phishing_validator.py: has_attack_path()` |
| Inert link corpus rewrite | `DATA_PROVENANCE.md`, notebook on corpus build |
| Demo-only team roster (separate from the above) | `src/demo_roster.py`, `DEMO_NOTES.md` |
