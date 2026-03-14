# Phishing Detection — Agent-Based Simulation

A research pipeline that models how human cognitive state affects susceptibility to phishing emails. It combines a labelled email dataset, LLM-based cue extraction, and a stochastic agent simulation grounded in occupational psychology research.

---

## What This Project Does

1. **Builds a dataset** of 250 emails across four categories (real phishing, AI-generated phishing variants, and benign)
2. **Extracts phishing cues** from every email using Gemini (LLM) with a regex fallback
3. **Simulates synthetic employees** — each with randomised demographic, psychological, and occupational traits — reading those emails at different points in their workday
4. **Models cognitive vulnerability** through fatigue and job performance equations derived from peer-reviewed research, then measures how often agents click vs report each email type

---

## Dataset

| Source | Count | Class | Description |
|---|---|---|---|
| SpamAssassin Ham | 100 | 0 — Benign | Real benign emails, pre-cleaned |
| Phishbowl | 50 | 1 — Phishing | Real-world phishing emails |
| Plain LLM | 50 | 1 — Phishing | Naive AI-generated phishing |
| Hybrid V-Triad | 50 | 1 — Phishing | Guided AI phishing using V-Triad persuasion framework |

**Master dataset:** `data/processed/master_emails.csv` — 250 rows, 7 columns

Schema: `email_id, subject, sender, body, extracted_urls, source, actual_class`

---

## Phishing Cue Taxonomy

9 cues extracted per email:

| Cue | Detection Method |
|---|---|
| `urgency` | Regex — "act now", "expires today" |
| `threats` | Regex — "account suspended", "legal action" |
| `generic_greeting` | Regex — "Dear Customer", "Hello User" |
| `spelling_grammar` | Regex — known misspellings + homoglyph patterns |
| `emotional_appeal` | Regex — "congratulations", "you've been selected" |
| `too_good_true` | Regex — "you won", "free gift", lottery language |
| `personal_info` | Regex — requests for password, SSN, credit card |
| `suspicious_sender` | Regex + logic — typosquatted brand domains |
| `suspicious_link` | Logic — URL shorteners, suspicious TLDs, brand-domain mismatch |

Cues are first extracted by Gemini (`gemini-2.5-flash`) and cached to disk. Emails that exceed the API quota fall back to the regex extractor automatically.

---

## Agent Architecture

Each synthetic agent is a dataclass (`src/agent.py`) with 20+ fields covering demographics, sleep, psychological state, and job characteristics.

### Fatigue Model

```
Energy Depletion = 2.45 - 0.05·Age + 0.09·Gender - 0.08·EducLevel
                   - 0.01·Tenure - 0.25·JobType + 0.65·JobComplexity

Fatigue = 6.22 - 0.22·TimeAwakening - 0.15·SleepTime + 0.14·SleepQuality
          + 0.44·StressAvg + 0.44·Illness + 0.29·SubjectiveHealth
          + 0.02·Age + 0.17·Depression

Total Fatigue = (Energy Depletion + Fatigue) / 2   → clamped [1, 5]
```

### Job Performance Model

```
JP1 = 2.766 - 0.106·Burnout + 0.301·IntMotivation + 0.298·JobSat
      - 0.153·RoleConflict - 0.076·LeaveIntention

JP2 = 3.238 - 0.022·TimePressure - 0.086·Workload
      - 0.141·LackMotivation - 0.155·RoleAmbiguity

Final JP = (JP1 + JP2) / 2 - (0.34 × Total Fatigue)
```

### Flawed Perception Level (FPL)

Probability [0.0, 0.5] that an agent misidentifies a malicious cue as benign:

```
FPL = 0.5 × fatigue_norm × (1 - jp_norm)
```

FPL is **trait-differentiated per cue**:
- Older / lower-education agents have higher FPL for URL and sender cues
- Desk workers in complex jobs have lower FPL for account-threat cues

### Decision Loop

1. Gemini returns a list of cues present in the email (e.g. `["urgency", "threats", "personal_info"]`)
2. Python shuffles the list and iterates up to `max_cues_processed` (7–12, agent-specific)
3. For each cue: `random() > cue_fpl` → agent perceives it → `suspicion_counter += 1`
4. If `suspicion_counter >= suspicion_threshold` (2–6, agent-specific) → **reported**
5. If max cues processed without reaching threshold → **clicked**

Workday progression: `time_pressure` and `workload` ramp linearly from 1 at 8am to 5 at 5pm, degrading job performance and increasing FPL as the day advances.

---

## Simulation Results

**30 agents × 5 time points × 250 emails = 37,500 simulation runs**

### Phishing click rate (vulnerability — lower is better)

| Source | 8am | 10am | 12pm | 2pm | 4pm |
|---|---|---|---|---|---|
| `hybrid_vtriad` | 76.9% | 77.6% | 78.6% | 77.2% | 78.8% |
| `phishbowl` | 93.3% | 93.5% | 94.3% | 94.7% | 93.6% |
| `plain_llm` | 98.7% | 98.9% | 98.6% | 99.1% | 99.1% |

### Benign click rate (correct behaviour — higher is better)

| Source | 8am | 10am | 12pm | 2pm | 4pm |
|---|---|---|---|---|---|
| `spamassassin_ham` | 99.2% | 99.0% | 99.1% | 99.2% | 99.0% |

### False positive rate (benign emails incorrectly reported)

~0.8–1.0% across all time points — very low.

### Key findings

- **Sophistication hierarchy holds:** agents click `plain_llm` 99% of the time vs 77% for `hybrid_vtriad` — exactly matching the Phase 3.5 quality audit ranking
- **Workday fatigue signal is present:** `hybrid_vtriad` click rate drifts +2pp from 8am to 4pm
- **Suspicion threshold dominates:** agents with threshold ≥ 6 rarely report any email regardless of FPL because most emails contain fewer than 6 cues
- **FPR is minimal:** benign emails are almost never false-positively reported

---

## Project Structure

```
capstone-preprocess-labels/
├── data/
│   ├── raw/                        # Original source CSVs
│   ├── processed/
│   │   └── master_emails.csv       # Unified 250-email dataset
│   ├── cue_cache/                  # Gemini API responses (JSON, one per email)
│   └── simulation_results.csv      # 37,500-row simulation output
│
├── src/
│   ├── agent.py                    # Agent dataclass + fatigue/JP/FPL math
│   ├── cue_extractor.py            # Gemini API cue extraction with disk cache
│   ├── regex_extractor.py          # Regex fallback cue extractor
│   ├── decision_loop.py            # Stochastic per-cue decision loop
│   └── simulation.py               # Full pipeline orchestration
│
├── notebooks/
│   ├── 02_pattern_testing.ipynb    # Cue pattern development and testing
│   ├── 03_audit_synthetic_vs_real.ipynb  # Dataset quality audit
│   └── 04_agent_simulation.ipynb   # Simulation analysis and visualisations
│
├── .env                            # GEMINI_KEY (required)
├── ROADMAP.md                      # Pipeline decisions and lessons learned
├── SYSTEM.md                       # Technical codebase reference
└── README.md                       # This file
```

---

## Setup

### Requirements

- Python 3.10+
- A Gemini API key from [aistudio.google.com](https://aistudio.google.com) (free tier, no billing needed)

### Install

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install pandas numpy scikit-learn matplotlib seaborn jupyter ipykernel requests python-dotenv google-genai textblob
```

### Register Jupyter kernel

```bash
python -m ipykernel install --user --name=capstone --display-name="Capstone (venv)"
```

### Configure API key

Add to `.env`:
```
GEMINI_KEY=your_key_here
```

### Run

```bash
jupyter notebook notebooks/04_agent_simulation.ipynb
```

Select the **Capstone (venv)** kernel. Cell 2 loads existing results if `data/simulation_results.csv` exists. Set `RERUN = True` to re-simulate.

To re-extract cues (e.g. after quota resets): delete `data/cue_cache/` and rerun cell 2.

---

## Dependencies

| Package | Purpose |
|---|---|
| `pandas`, `numpy` | Data manipulation |
| `google-genai` | Gemini API client |
| `python-dotenv` | Load `.env` credentials |
| `matplotlib`, `seaborn` | Visualisation |
| `textblob` | Sentiment analysis (emotional appeal cue) |
| `scikit-learn` | Available for future ML extensions |
| `jupyter`, `ipykernel` | Notebook runtime |
