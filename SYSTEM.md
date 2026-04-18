# SYSTEM.md — Technical Codebase Reference

This document is the complete technical map of the codebase. It describes every file, its inputs/outputs, key functions, data contracts, and how components connect. Any coding assistant working in this repo should read this alongside README.md before making changes.

---

## Data Flow (End-to-End)

```
data/raw/*.csv
      │
      ▼
phase2_normalization.ipynb
  → normalises schema, merges sources, extracts URLs
  → outputs: data/processed/master_emails.csv (250 rows)
      │
      ▼
notebooks/02_pattern_testing.ipynb
  → develops and validates 9 regex cue patterns
  → outputs: validated pattern functions (also ported to src/regex_extractor.py)
      │
      ▼
src/cue_extractor.py  (or src/regex_extractor.py fallback)
  → reads master_emails.csv
  → calls Gemini API per email → JSON list of cue names
  → caches to data/cue_cache/email_{id}.json
      │
      ▼
src/agent.py
  → generates N Agent objects with randomised traits
  → computes fatigue, job performance, FPL dynamically
      │
      ▼
src/decision_loop.py
  → for each (agent, email, hour): stochastic cue-processing loop
  → returns decision: "clicked" | "reported"
      │
      ▼
src/simulation.py
  → orchestrates all above steps
  → outputs: data/simulation_results.csv (37,500 rows)
      │
      ▼
notebooks/04_agent_simulation.ipynb
  → loads simulation_results.csv
  → 8 analysis cells: validation, click rates, fatigue effects,
    trait correlations, cue heatmap, summary table
```

---

## File Reference

### `data/processed/master_emails.csv`

The primary input dataset. Do not modify manually.

| Column | Type | Description |
|---|---|---|
| `email_id` | int | Sequential ID 1–250 |
| `subject` | str | Email subject line |
| `sender` | str | Sender address |
| `body` | str | Email body (headers stripped) |
| `extracted_urls` | str (list) | Python list repr of URLs found in body |
| `source` | str | `spamassassin_ham` / `phishbowl` / `plain_llm` / `hybrid_vtriad` |
| `actual_class` | int | 0 = benign, 1 = phishing |

Source counts: 100 benign + 50 phishbowl + 50 plain_llm + 50 hybrid_vtriad = 250 total.

---

### `data/cue_cache/email_{id}.json`

One file per email. Contains a JSON array of cue names extracted by Gemini, e.g.:
```json
["urgency", "generic_greeting", "personal_info"]
```

Empty array `[]` = either no cues found OR API quota was exceeded (regex fallback produced nothing).

**To regenerate:** delete the relevant files and re-run the simulation (cell 2 in notebook 04). The extractor skips files that already exist (cache-first).

**Gemini quota note:** `gemini-2.5-flash` free tier = 20 requests/day on this account. When quota is exhausted, `CueExtractor._call_gemini()` catches the exception and falls through to saving `[]`. The separate `src/regex_extractor.py` was used to backfill those entries.

---

### `data/simulation_results.csv`

37,500 rows. One row per (agent × workday_hour × email).

| Column | Description |
|---|---|
| `agent_id` | e.g. `agent_000` |
| `email_id` | FK to master_emails.csv |
| `source` | Email source |
| `actual_class` | 0/1 |
| `workday_hour` | 8.0 / 10.0 / 12.0 / 14.0 / 16.0 |
| `suspicion_threshold` | Agent's threshold (2–6) |
| `max_cues_processed` | Agent's scan limit (7–12) |
| `age` | Agent age |
| `education_level` | Agent education level (1–5) |
| `job_complexity` | Agent job complexity (1–5) |
| `cues_extracted` | Number of cues in the email's cache entry |
| `decision` | `"clicked"` or `"reported"` |
| `suspicion_counter` | How high the counter got before stopping |
| `cues_scanned` | How many cues were iterated through |
| `cues_perceived` | Python list repr of cues that registered |
| `total_fatigue` | Computed total fatigue (1–5) |
| `final_jp` | Computed final job performance |
| `fpl` | Base flawed perception level (0.0–0.5) |

---

### `src/agent.py`

**Class:** `Agent` (dataclass)

All fields set at construction. Workday-dynamic fields (`current_hour`, `time_pressure`, `workload`) are mutated by `advance_workday()`.

**Key methods:**

| Method | Returns | Notes |
|---|---|---|
| `compute_kss()` | float [1,9] | Three Process Model KSS — uses `current_hour`, time-varying |
| `compute_energy_depletion()` | float [1,5] | `f(job_complexity, intrinsic_motivation)` — gender removed |
| `compute_total_fatigue()` | float [1,5] | `(KSS_norm + ED) / 2`, changes with `current_hour` |
| `compute_job_performance()` | float | Uses `time_pressure`, `workload` (dynamic) + fatigue crossover |
| `compute_flawed_perception_level()` | float [0,0.5] | Derived from total_fatigue + JP |
| `get_cue_fpl(cue: str)` | float [0,0.5] | Trait-adjusted FPL for a specific cue |
| `advance_workday(hour: float)` | None | Sets `current_hour`; mutates `time_pressure` and `workload` |
| `Agent.random_agent(agent_id, seed)` | Agent | Classmethod factory |

**Key design note:** `gender` is stored as a field for demographic records but is NOT used in any formula. The previous ED formula included `+0.09*gender` which was removed after review — the Tian et al. paper specifies `ED = f(JobComplexity, PsychologicalEmpowerment)` without gender.

**Fatigue is time-varying:** calling `advance_workday(hour)` updates `current_hour`, so subsequent calls to `compute_kss()`, `compute_total_fatigue()`, and `compute_flawed_perception_level()` return hour-appropriate values. At 8am, KSS ≈ 8–9 (groggy start); by 4pm it falls to ≈ 5–6 as circadian alertness rises.

**Trait adjustments in `get_cue_fpl`:**
- `suspicious_link`, `suspicious_sender`: penalised for age > 30 and education < 3
- `threats`, `personal_info`, `too_good_true`: reduced by 0.08 for desk workers with job_complexity > 3

---

### `src/ollama_extractor.py`

**Class:** `OllamaExtractor`

Drop-in replacement for `CueExtractor` using a locally-running Ollama model. Same cache-first interface.

**Constructor params:**
- `model` (default: `"qwen2.5:7b"`) — any Ollama model; `gemma2:9b` also works well
- `cache_dir` (default: `"data/cue_cache"`)
- `endpoint` (default: `"http://localhost:11434/api/generate"`)
- `min_interval` (default: `0.3` seconds)

**Key methods:**

| Method | Description |
|---|---|
| `extract(email_id, subject, sender, body, urls)` | Cache-first extraction. Returns `list[str]` |
| `extract_batch(emails_df)` | Same as `CueExtractor.extract_batch()` |
| `is_available()` | Checks Ollama is running and model is pulled. Returns `bool` |

**Setup:** `ollama pull qwen2.5:7b` (fits in 16GB VRAM, ~3–5s per call)

**Why prefer over regex:** Ollama understands tone, implication, and subtle manipulation that regex cannot catch. Phishbowl emails in particular score low with regex (0.78 avg cues) because real phishing avoids obvious patterns — Ollama catches what regex misses.

**To use in simulation:** In notebook 04, set `USE_OLLAMA=True` and delete `data/cue_cache/` to force re-extraction.

---

### `src/cue_extractor.py`

**Class:** `CueExtractor`

Calls Gemini to extract cues from a single email. Caches result to `data/cue_cache/email_{id}.json` after first call.

**Constructor params:**
- `cache_dir` (default: `"data/cue_cache"`)
- `min_interval` (default: `1.0` seconds between API calls)

**Key methods:**

| Method | Description |
|---|---|
| `extract(email_id, subject, sender, body, urls)` | Main method. Checks cache first, calls API on miss. Returns `list[str]` |
| `extract_batch(emails_df)` | Iterates a DataFrame, calls `extract()` for each row. Returns `dict {email_id: [cues]}` |
| `_call_gemini(...)` | Raw API call. Returns `[]` silently on any error |
| `_rate_limit()` | Enforces `min_interval` between calls via `time.sleep()` |
| `_cache_path(email_id)` | Returns `Path` to cache JSON file |

**Model in use:** `models/gemini-2.5-flash`

**Valid cue names** (enforced after parsing):
```python
["urgency", "threats", "generic_greeting", "spelling_grammar",
 "emotional_appeal", "too_good_true", "personal_info",
 "suspicious_sender", "suspicious_link"]
```

**To change model:** edit the string in `_call_gemini()`. Run `client.models.list()` to see available models.

**To change prompt:** edit `_PROMPT` template at the top of the file. The prompt instructs the model to return only a JSON array — do not remove that instruction or JSON parsing will break.

---

### `src/regex_extractor.py`

Standalone regex-based cue extractor. No API calls. Used to backfill `data/cue_cache/` entries that were saved as `[]` due to Gemini quota exhaustion.

**Main function:**
```python
extract_cues_regex(subject, sender, body, urls) -> list[str]
```

Returns the same cue name schema as `CueExtractor`. All 9 patterns are compiled at module load.

**Pattern summary:**

| Cue | Trigger condition |
|---|---|
| `generic_greeting` | Matches "Dear Customer", "Hello User", etc. |
| `urgency` | Urgency keywords with temporal/action context |
| `threats` | Account suspension, access revocation, legal action |
| `emotional_appeal` | Congratulations, winner, inheritance, donation language |
| `too_good_true` | Free gifts, lottery, prize amounts, gift cards |
| `personal_info` | Requests to enter/confirm password, SSN, card number |
| `spelling_grammar` | 1+ known misspelling OR 3+ homoglyph matches |
| `suspicious_sender` | Brand keyword in sender domain not matching legitimate domain |
| `suspicious_link` | URL shorteners, bad TLDs, brand keyword in non-legitimate host |

**Note on accuracy:** regex is less accurate than Gemini for subtle cues (emotional tone, indirect threats). Phishbowl emails in particular score low with regex (0.78 avg cues) because real phishing avoids obvious patterns.

**To backfill cache after quota reset:** delete cache files, re-run `CueExtractor.extract_batch()`. Only the deleted files will be re-called.

---

### `src/decision_loop.py`

**Functions:**

```python
simulate_email(agent, cues, rng=None) -> dict
simulate_email_across_day(agent, cues, hours, rng=None) -> list[dict]
```

`simulate_email` runs one decision loop iteration:
1. Shuffles cue list (via `rng.shuffle`)
2. Iterates up to `agent.max_cues_processed` cues
3. For each cue: rolls `rng.random()` vs `agent.get_cue_fpl(cue)`
4. If roll > FPL: cue perceived, `suspicion_counter += 1`
5. Stops early if `suspicion_counter >= agent.suspicion_threshold`
6. Returns dict with `decision`, `suspicion_counter`, `cues_scanned`, `cues_perceived`, `total_fatigue`, `final_jp`, `fpl`

**Important:** `i` is initialised to `-1` before the loop so `i+1 = 0` when the cue list is empty (emails with no cues always result in `"clicked"` with `cues_scanned=0`).

**To extend:** add new stopping conditions (e.g. time pressure cutoff) inside the for loop. Add to the returned dict as needed — `simulation.py` spreads the entire dict into each row via `**result`.

---

### `src/simulation.py`

**Main function:**
```python
run_simulation(emails_csv, n_agents, workday_hours, seed, cache_dir) -> pd.DataFrame
```

Orchestrates the three steps:
1. `CueExtractor.extract_batch()` — cache-first extraction for all emails
2. `build_agents(n, seed)` — generates `n` reproducible `Agent` objects
3. Triple loop: `agent × hour × email` → `simulate_email()` → appends row to `records`

Returns a flat DataFrame. Each agent gets a fresh `random.Random` per hour to ensure decisions are independent.

**Helper functions:**
```python
build_agents(n, seed) -> list[Agent]     # reproducible agent generation
save_results(df, path)                   # saves DataFrame to CSV
click_rate_summary(df) -> pd.DataFrame   # groups by source/class/hour
```

**To scale up:** increase `n_agents` and/or add more `workday_hours` values. Results grow as `n_agents × len(hours) × 250`. At 30 agents × 5 hours it takes ~1 second after cues are cached.

---

### `notebooks/04_agent_simulation.ipynb`

8 analysis cells. Loads from `data/simulation_results.csv` (set `RERUN=False`). Set `RERUN=True` to re-run the full simulation.

| Cell | What it does |
|---|---|
| 0 — Setup | Imports, path setup, `load_dotenv`, seaborn theme |
| 1 — Spot-check | Single agent traits + state at 8am/4pm + decision loop demo |
| 2 — Run simulation | Loads or runs simulation, shows DataFrame head |
| 3 — Cue validation | Boxplot of cues extracted per source |
| 4 — Click rates | Line chart: click rate by source across workday hours |
| 4b — FPR | False positive rate on benign emails by hour |
| 5 — Fatigue effect | Click rate by fatigue tertile across workday |
| 6 — Trait correlations | Heatmap: agent traits vs click rate; FPL and threshold scatters |
| 7 — Cue heatmap | % of trials where each cue was perceived, by source |
| 8 — Summary table | Final click rate pivot tables (phishing + benign) |

---

### `notebooks/02_pattern_testing.ipynb`

Defines and tests all 9 cue patterns on a 60-email stratified sample (15 per source). Contains the original pattern implementations — `src/regex_extractor.py` is the production port of this notebook.

Key functions defined here: `check_suspicious_sender()`, `check_spelling_grammar()`, `check_emotional_appeal()` (uses TextBlob), `check_suspicious_links()`, `extract_urls()`, `test_cue()` (test harness), `compute_v_triad_score()`.

---

### `notebooks/03_audit_synthetic_vs_real.ipynb`

Quality audit comparing real vs AI-generated phishing across 6 dimensions. Key output:

| Source | Avg quality score (/5) |
|---|---|
| Phishbowl | 4.83 |
| Hybrid V-Triad | 2.50 |
| Plain LLM | 1.50 |

This explains why click rates follow the same order — more sophisticated phishing has fewer detectable regex cues.

---

### `phase2_normalization.ipynb`

Loads the 4 raw CSVs, validates content, standardises schema, extracts URLs, merges into `master_emails.csv`. Produces the 250-row dataset consumed by everything downstream. Run only if re-building the dataset from scratch.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GEMINI_KEY` | Yes (for extraction) | API key from aistudio.google.com |
| `KAGGLE_USERNAME` | No | Legacy — used for initial data download only |
| `KAGGLE_KEY` | No | Legacy — used for initial data download only |

---

## Known Limitations and Extension Points

**Cue quality:** 239 of 250 emails use regex-extracted cues rather than Gemini. Real phishing (Phishbowl) averages only 0.78 cues via regex — sophisticated emails evade pattern matching. Gemini extractions are richer. To improve: delete cache and re-extract when daily quota allows.

**Suspicion threshold dominance:** many agents have threshold ≥ 5 but most emails have < 5 cues. These agents can never report those emails regardless of FPL. Consider reducing the threshold range (e.g. 2–4) or increasing cue extraction quality.

**Workday fatigue effect is subtle (~2pp):** the FPL difference across the day is small relative to between-agent variance in threshold. The fatigue effect is most visible when comparing agents by fatigue tertile rather than time of day.

**To add a new cue:**
1. Add the cue name string to `VALID_CUES` in both `src/cue_extractor.py` and `src/regex_extractor.py`
2. Add detection logic in `regex_extractor.py`'s `extract_cues_regex()`
3. Update the Gemini prompt in `src/cue_extractor.py` to include the new cue name and definition
4. Add a trait adjustment in `src/agent.py`'s `get_cue_fpl()` if applicable
5. Delete `data/cue_cache/` to force re-extraction

**To add a new agent trait:**
1. Add field to `Agent` dataclass in `src/agent.py`
2. Add it to `random_agent()` factory
3. Use it in `get_cue_fpl()` or the fatigue/JP formulas as appropriate
4. Add the column to `simulation.py`'s record dict if it should appear in results

**To run on a different dataset:** ensure the CSV has the same 7-column schema as `master_emails.csv`. Pass the new path to `run_simulation(emails_csv=...)`.
