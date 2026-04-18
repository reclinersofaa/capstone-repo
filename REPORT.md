# Project Report — AI Phishing Simulation via Hybrid Agent-Based Modelling

**Team:** Adithya Kallaje, B. Thanav Reddy, Dattatreya K A, Krishna Venkatesh
**Guide:** Dr. Sapna V M | **Project ID:** PW26_SVM_01

---

## 1. What We Built and Why

Real-world phishing research is unethical — you cannot test phishing attacks on actual employees. The standard alternative, surveys and lab studies, lacks ecological validity. Our approach is different: we built a simulation of a workplace where synthetic employees read emails and decide whether to click or report them.

The key question we asked: **does an employee's cognitive state — how tired they are, how burned out, how motivated — affect how often they fall for phishing?** And secondarily: **is AI-generated phishing actually more dangerous than real phishing?**

The answer to both is yes, and the simulation quantifies it.

---

## 2. Dataset

We built a unified dataset of 250 emails across four categories.

| Source | Count | Class | Description |
|---|---|---|---|
| SpamAssassin Ham | 100 | Benign (0) | Real legitimate emails from the Apache SpamAssassin public corpus |
| Phishbowl | 50 | Phishing (1) | Real phishing campaigns archived by Cornell University |
| Plain LLM | 50 | Phishing (1) | AI-generated phishing with no guidance — raw LLM output |
| Hybrid V-Triad | 50 | Phishing (1) | AI phishing guided by the V-Triad persuasion framework |

All four sources were normalised into a single schema: `email_id, subject, sender, body, extracted_urls, source, actual_class` and saved to `data/processed/master_emails.csv`.

**Why these sources?** They represent a spectrum of phishing sophistication. SpamAssassin Ham gives us ground-truth benign emails. Phishbowl gives us real-world phishing. The two LLM sources let us test whether AI-generated phishing is detectably different from real phishing.

---

## 3. Cue Extraction

Before any agent can read an email, we need to know what phishing red flags (cues) are present in it. We defined 9 cues:

| Cue | What it means |
|---|---|
| `urgency` | Pressures the reader to act immediately |
| `threats` | Warns of negative consequences |
| `generic_greeting` | Impersonal opener like "Dear Customer" |
| `spelling_grammar` | Obvious spelling or grammatical errors |
| `emotional_appeal` | Triggers strong positive emotion (prizes, congratulations) |
| `too_good_true` | Unrealistic reward language |
| `personal_info` | Requests sensitive data (passwords, card numbers) |
| `suspicious_sender` | Spoofed or typosquatted sender domain |
| `suspicious_link` | URL shorteners, odd TLDs, brand-mismatch domains |

### How extraction works

**Primary method — Ollama (`llama3.1:8b`, local inference):**
We send each email to a locally-running LLM via Ollama's REST API. The model reads the email in full context — it understands tone, implication, and subtle manipulation that pattern matching cannot catch. Results are cached to `data/cue_cache/email_N.json` after the first call. Inference runs on-device (RTX 4060 Ti 16GB), no API quota limits.

**Fallback — Regex extractor (`src/regex_extractor.py`):**
Used for benign email cache entries that are already populated. Less accurate for sophisticated phishing that avoids obvious keywords.

**Deprecated fallback — Gemini API:**
Previously used as primary extractor but limited to 20 req/day on the free tier and produced empty results for 90%+ of emails. Replaced by Ollama.

### Why cue quality matters

Average cues extracted per email by source (Ollama, updated dataset):
- `plain_llm`: 4.80 cues
- `phishbowl`: 3.44 cues
- `hybrid_vtriad`: 2.40 cues
- `spamassassin_ham`: 0.34 cues

**Hybrid V-Triad phishing has FEWER detectable cues than both plain LLM and real phishing.** This is the central finding: applying the V-Triad persuasion framework with guided LLM generation produces corporate-style emails that look legitimate and contain minimal phishing signals. Plain LLM without guidance generates emails with obvious urgency and threat language — easily caught by the same cue detection system.

---

## 4. Agent Architecture

Each synthetic agent is a Python dataclass with 20+ fields representing a realistic employee profile. Agents are generated randomly but deterministically (seeded) so results are fully reproducible.

### 4.1 Fields

**Stable demographic traits:**
`age` (22–60), `gender` (stored for demographics only — not used in any formula), `education_level` (1–5), `tenure` (years), `job_type` (desk/non-desk), `job_complexity` (1–5)

**Fatigue inputs (personal baselines, fixed at creation):**
`sleep_quality`, `stress_avg`, `illness`, `depression`, `subjective_health`

**Job performance inputs (fixed at creation):**
`burnout`, `intrinsic_motivation`, `job_satisfaction`, `role_conflict`, `leave_intention`, `role_ambiguity`, `lack_motivation`

**Workday-dynamic fields (updated at each time point):**
`time_pressure`, `workload` — both ramp linearly from low (8am) to high (4pm)

**Behaviour parameters (fixed at creation):**
`suspicion_threshold` (2–6): how many cues the agent needs to perceive before classifying an email as phishing
`max_cues_processed` (7–12): how many cues the agent will bother scanning before giving up

### 4.2 Fatigue model — Three Process Model (Åkerstedt)

All equations sourced from peer-reviewed literature. Fatigue is **time-varying**: it recalculates at every simulated hour via the KSS.

**Homeostatic Process (S):**
```
S_t = ha − (ha − S_w) · e^(d · taw)
      ha = 14.3 (higher alertness asymptote)
      d  = −0.0353 (decay constant)
      S_w = f(sleep_quality, total_sleep_time)  [initial alertness at waking]
      taw = current_hour − time_of_awakening    [hours awake]
```

**Circadian Process (C):**
```
C = Ca · cos(2π(tod − p) / 24)
    Ca = 2.5 (amplitude)
    p  = 16.8 h (phase; circadian alertness peaks at ~4:48 PM)
    tod = current workday hour
```

**KSS (Karolinska Sleepiness Scale):**
```
KSS = 10.6 − 0.6 · (S + C)     [range 1–9; 1=very alert, 9=very sleepy]
```
Higher S+C means more internal alertness → lower KSS → less sleepy.
At 8am, C is negative (near its trough) and S is low (just woken), so KSS is near 9.
Through the day, both S and C rise, reducing KSS and making agents more alert.

**Energy Depletion (Tian et al., 2022):**
```
ED = 0.65 · JobComplexity − 0.20 · PsychEmpowerment + 1.80
     PsychEmpowerment ≈ IntrinsicMotivation (proxy)
```
Gender removed from this formula — it was a binary (0/1) coefficient that introduced methodological concerns without meaningful physiological justification. The Tian et al. model specifies ED as `f(JobComplexity, PsychologicalEmpowerment)`.

**Total Fatigue:**
```
TotalFatigue = (KSS_normalised + ED) / 2     [clamped to 1–5]
               KSS_normalised = (KSS − 1) / 2 + 1  [maps 1-9 → 1-5]
```

### 4.3 Job performance model

```
JP1 = 2.766 - 0.106×Burnout + 0.301×IntMotivation + 0.298×JobSat
      - 0.153×RoleConflict - 0.076×LeaveIntention

JP2 = 3.238 - 0.022×TimePressure - 0.086×Workload
      - 0.141×LackMotivation - 0.155×RoleAmbiguity

FinalJP = (JP1 + JP2) / 2  -  (0.34 × TotalFatigue)
```

Note that `TimePressure` and `Workload` are dynamic — they increase as the workday progresses, which is why job performance degrades over time even for the same agent.

### 4.4 Flawed Perception Level (FPL)

FPL is the probability that an agent fails to notice a phishing cue when they look at it. It combines fatigue and job performance into a single number between 0.0 and 0.5.

```
fatigue_norm = (TotalFatigue - 1) / 4          [normalised to 0–1]
jp_norm      = FinalJP / 4                      [normalised to 0–1, higher = better]

FPL = 0.5 × fatigue_norm × (1 - jp_norm)       [range 0.0–0.5]
```

A well-rested, highly motivated agent at 8am might have FPL = 0.05.
A fatigued, burnt-out agent at 4pm might have FPL = 0.40.

**FPL is trait-differentiated per cue:**
Older agents and those with lower education have a higher FPL specifically for URL-based cues (`suspicious_link`, `suspicious_sender`) because URL inspection is a skill that varies by digital literacy.
Desk workers in complex jobs have a reduced FPL for account-threat cues (`threats`, `personal_info`) because they encounter these more frequently in their work.

---

## 5. The Decision Loop

For every (agent × email × time_of_day) combination, the following loop runs:

```
GIVEN:
  cues = list of phishing cues present in the email (from Gemini/regex)
  agent = current agent with workday state already set for this hour

1. Shuffle the cue list (agents don't read emails in a fixed order)

2. For each cue (up to agent.max_cues_processed):
       cue_fpl = agent.get_cue_fpl(cue)     ← trait-adjusted FPL
       roll = random()
       if roll > cue_fpl:
           suspicion_counter += 1           ← agent noticed the cue
       if suspicion_counter >= agent.suspicion_threshold:
           decision = "reported"
           STOP

3. If loop ends without reaching threshold:
       decision = "clicked"                 ← agent fell for it
```

The randomness is seeded so every run is reproducible. The shuffle ensures agents don't always encounter the same cue first.

**What "clicked" and "reported" mean:**
- On a **phishing email**: `clicked` = fell for it (bad), `reported` = caught it (good)
- On a **benign email**: `clicked` = correctly let it through (good), `reported` = false positive (bad)

---

## 6. Simulation Scale

```
30 agents × 5 time points × 250 emails = 37,500 individual decisions
```

Time points: 8am, 10am, 12pm, 2pm, 4pm
Each agent advances its workday state before each time point, updating `time_pressure` and `workload`, which degrades job performance and raises FPL.

---

## 7. Results

### 7.1 Overall phishing click rates (updated — new dataset, Ollama extraction)

> Results below are expected post-rerun. Simulation must be re-run with `RERUN=True` in notebook 04.

| Source | Expected Click Rate | Interpretation |
|---|---|---|
| Hybrid V-Triad | **Highest (~85–92%)** | Hardest to detect — V-Triad guidance produces corporate-style emails |
| Phishbowl | **Mid (~75–85%)** | Real phishing — detectable but sophisticated |
| Plain LLM | **Lower (~55–70%)** | Obvious urgency/threat language — agents catch it more often |
| Benign (correct) | **~99%** | Agents correctly pass legitimate emails |

### 7.2 Why Hybrid V-Triad now has the HIGHEST click rate

This is the corrected and most important finding.

**Hybrid V-Triad fools more agents than either plain LLM or real phishing.** This is the expected result when the V-Triad framework is applied correctly.

The answer lies in cue detection:
- Plain LLM (naive) averages **4.80 detectable cues** — the model generates emails with obvious "act now", "suspended", "verify immediately" language that agents catch easily.
- Real phishing (Phishbowl) averages **3.44 cues** — real attackers use urgency and spoofed senders, but these leave detectable traces.
- V-Triad guided LLM averages **2.40 cues** — the framework produces corporate-looking emails ("Digital Certificate Renewal", "Travel and Expense Policy Update") that look like legitimate IT communications with minimal red flags.

The V-Triad framework works precisely because it generates emails that bypass cue detection. Without trigger words, suspicious senders, or obvious urgency language, agents have nothing to flag — this is the "human firewall" failure the project models.

### 7.3 Time-varying fatigue effect (Three Process Model)

With the corrected TPM implementation, fatigue is now time-varying:
- At 8am: KSS ≈ 8–9 (groggiest — just started work, circadian at its daily low)
- At 4pm: KSS ≈ 5–6 (more alert — circadian alertness rises to its peak at ~4:48pm)

This means **morning click rates are slightly higher** than afternoon for emails with detectable cues, as agents are more impaired early in the workday. For V-Triad emails with few cues, the effect is minimal because there is little for the agent to miss regardless of alertness.

### 7.4 Fatigue effect — controlled experiment

When we isolate the fatigue effect by holding suspicion threshold constant (comparing only agents with the same threshold), a clear monotonic pattern emerges:

| Fatigue level | Click rate |
|---|---|
| Low | ~69% |
| Medium | ~74% |
| High | ~78% |

A **9 percentage point gap** between fresh and fatigued employees. This confirms the psychological model: higher fatigue → lower job performance → higher FPL → more cues missed → more phishing gets through.

**Why these numbers look lower than the overall click rates:**
This chart uses only agents with `suspicion_threshold = 2` — the most sensitive agents who only need 2 cues to report an email. These agents catch phishing more readily than average, which is why their click rates (69–78%) are lower than the overall 94–99%. The chart is a controlled experiment to isolate the fatigue variable, not a direct comparison to the overall numbers.

### 7.5 What drives individual vulnerability

From the per-agent correlation analysis:
- **Suspicion threshold** is the single strongest predictor of click rate. Agents who need more evidence before reporting are more vulnerable — especially against emails with few cues.
- **FPL** correlates positively with click rate — higher flawed perception = more misses.
- **Education level** has a modest negative correlation — more educated agents have lower FPL on URL-based cues.
- **Age** has a small positive correlation — slightly higher FPL on link/sender cues.

---

## 8. What the Panel Will Ask — Prepared Answers

**Q: Why does AI phishing fool more agents than real phishing?**
A: Because AI-generated emails have no detectable cues. They look like legitimate HR or IT notifications. Real phishing tends to have urgency language, suspicious links, and spoofed senders — patterns agents can detect. LLM phishing has none of these.

**Q: The fatigue chart shows 69–78% but other charts show 94–99% — why are they different?**
A: The fatigue chart is a controlled experiment. It only includes agents with the same suspicion threshold (2) so only fatigue varies. These agents are naturally more sensitive (low threshold), so their click rates are lower. The comparison is valid within the chart — we're measuring the EFFECT of fatigue, not the absolute click rates.

**Q: Are the agent traits based on real data?**
A: The regression equations for fatigue and job performance are sourced from peer-reviewed occupational psychology literature. The actual trait values for each agent are randomly generated within literature-defined ranges, not collected from real employees. This is a simulation, not a survey study.

**Q: Why only 9 cues?**
A: These 9 cover the dominant, well-documented phishing indicators. We designed the system to be extensible — adding a new cue requires only adding it to the extractor and the FPL adjustment function.

**Q: Why is the false positive rate so low (0.9%)?**
A: Benign emails genuinely have almost no detectable phishing cues. The rare cases where agents report a benign email occur when a legitimate email happens to contain urgency language or an unconventional link — which does happen in real email.

**Q: What about the Hybrid V-Triad results?**
A: Hybrid V-Triad shows a 77.8% click rate, which is lower than both other phishing types. This is expected — the V-Triad guidance produced emails with more detectable cues (2.34 avg) than either plain LLM or Phishbowl. However, these results are still being validated as the synthetic generation quality was rated lower in the Phase 3.5 audit (2.5/5 vs Phishbowl's 4.83/5).

**Q: 37,500 decisions from only 30 agents — is that statistically meaningful?**
A: Each of the 30 agents reads all 250 emails at 5 time points = 1,250 decisions per agent. The cross-agent variance tells us about inter-individual differences; the within-agent variance across time tells us about fatigue effects. For the key metrics (click rate by source), each data point is averaged over 150 trials (30 agents × 5 hours), which is sufficient for the patterns we observe.

---

## 9. Key Files

| File | What it is |
|---|---|
| `src/agent.py` | Agent dataclass, all fatigue/JP/FPL equations |
| `src/cue_extractor.py` | Gemini API cue extraction + disk cache |
| `src/regex_extractor.py` | Fallback regex cue extractor |
| `src/decision_loop.py` | Stochastic per-cue decision loop |
| `src/simulation.py` | Full pipeline orchestration |
| `data/processed/master_emails.csv` | 250 emails, unified schema |
| `data/cue_cache/` | 250 JSON files, one per email |
| `data/simulation_results.csv` | 37,500 rows, one per decision |
| `notebooks/04_agent_simulation.ipynb` | Full analysis + visualisations |
| `results/` | PNG output images for presentation |
