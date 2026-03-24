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

**Primary method — Gemini API (`gemini-2.5-flash`):**
We send each email to Gemini with a structured prompt asking it to return a JSON array of cue names present in the email. Gemini reads the email in full context — it understands tone, implication, and subtle manipulation that pattern matching cannot catch. Results are cached to `data/cue_cache/email_N.json` after the first call, so subsequent runs never hit the API again.

**Fallback — Regex extractor (`src/regex_extractor.py`):**
When the Gemini free tier quota is exhausted (20 requests/day), the system falls back to compiled regex patterns. This is less accurate — particularly for sophisticated phishing that avoids obvious keywords — but requires no API.

### Why cue quality matters

Average cues extracted per email by source:
- `hybrid_vtriad`: 2.34 cues
- `phishbowl`: 0.78 cues
- `plain_llm`: 0.42 cues
- `spamassassin_ham`: ~0.10 cues

**Plain LLM phishing has FEWER detectable cues than real phishing.** This is the central finding of the dataset audit and is confirmed by the simulation results.

---

## 4. Agent Architecture

Each synthetic agent is a Python dataclass with 20+ fields representing a realistic employee profile. Agents are generated randomly but deterministically (seeded) so results are fully reproducible.

### 4.1 Fields

**Stable demographic traits:**
`age` (22–60), `gender`, `education_level` (1–5), `tenure` (years), `job_type` (desk/non-desk), `job_complexity` (1–5)

**Fatigue inputs (personal baselines, fixed at creation):**
`sleep_quality`, `stress_avg`, `illness`, `depression`, `subjective_health`

**Job performance inputs (fixed at creation):**
`burnout`, `intrinsic_motivation`, `job_satisfaction`, `role_conflict`, `leave_intention`, `role_ambiguity`, `lack_motivation`

**Workday-dynamic fields (updated at each time point):**
`time_pressure`, `workload` — both ramp linearly from low (8am) to high (4pm)

**Behaviour parameters (fixed at creation):**
`suspicion_threshold` (2–6): how many cues the agent needs to perceive before classifying an email as phishing
`max_cues_processed` (7–12): how many cues the agent will bother scanning before giving up

### 4.2 Fatigue model

All equations are sourced from peer-reviewed occupational psychology literature.

**Energy Depletion:**
```
ED = 2.45 - 0.05×Age + 0.09×Gender - 0.08×EducLevel
     - 0.01×Tenure - 0.25×JobType + 0.65×JobComplexity
```

**Fatigue:**
```
F = 6.22 - 0.22×TimeAwakening - 0.15×SleepTime + 0.14×SleepQuality
    + 0.44×Stress + 0.44×Illness + 0.29×Health + 0.02×Age + 0.17×Depression
```

**Total Fatigue:**
```
TotalFatigue = (ED + F) / 2     [clamped to range 1–5]
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

### 7.1 Overall phishing click rates

| Source | Click Rate | Interpretation |
|---|---|---|
| Plain LLM | **98.9%** | Nearly every agent fell for it, every time |
| Phishbowl | **93.9%** | 9 in 10 agents fell for it |
| Hybrid V-Triad | **77.8%** | 3 in 4 agents fell for it (results still being validated) |
| Benign (correct) | **99.1%** | Agents almost never false-positively reported legitimate email |
| False positive rate | **0.9%** | Less than 1% of benign emails wrongly flagged |

### 7.2 Why plain_llm has a HIGHER click rate than real phishing

This is the most important and counterintuitive finding.

**Plain LLM phishing fools more agents (99%) than real phishing (94%).** This seems wrong — shouldn't real phishing, crafted by actual attackers, be more convincing?

The answer lies in cue detection:
- Real phishing (Phishbowl) averages **0.78 detectable cues** per email. Real attackers use urgency, spoofed senders, and suspicious links — patterns that Gemini and agents can identify.
- LLM phishing averages **0.42 detectable cues** per email. The LLM produces emails that look like legitimate corporate HR notices — no urgency language, no suspicious links, no generic greetings. **There is nothing for the agent to catch.**

In other words: LLM phishing is more dangerous precisely because it mimics legitimate email so well that it produces zero red flags. A simulated employee cannot distinguish it from a real company notification.

This is the threat the project is designed to demonstrate.

### 7.3 Click rate does not vary much across the workday

| Source | 8am | 10am | 12pm | 2pm | 4pm |
|---|---|---|---|---|---|
| Plain LLM | 98.7% | 98.9% | 98.6% | 99.1% | 99.1% |
| Phishbowl | 93.3% | 93.5% | 94.3% | 94.7% | 93.6% |

**Why the flat line for plain_llm:** An email with zero detectable cues cannot be caught regardless of how alert the agent is. FPL only matters when there are cues to miss — there are none.

**Why phishbowl drifts slightly:** Phishbowl emails have ~0.78 cues. As fatigue increases through the day, agents are slightly more likely to miss those cues, so the click rate nudges upward by ~1.4pp.

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
