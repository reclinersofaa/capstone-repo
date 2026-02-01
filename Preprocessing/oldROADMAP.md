# Capstone Restart Roadmap

This document captures a concise post-mortem, a safe restart plan from data gathering to labeling, and a practical checklist so you can take the project to an advanced, defensible level.

---

## 1) Post-Mortem — What went wrong
- Garbage-in, insufficient inspection: raw Enron headers and varied formats contaminated analysis.
- Reactive fixes (ad-hoc regex) created brittle logic and sprawl.
- Comparing datasets with different formats (HTML vs plain text) produced misleading metrics.
- Tweaking detection rules to get desired numbers (p-hacking) made results non-replicable.

---

## 2) High-level Restart Principles
1. Normalize all inputs to a single canonical schema before any feature extraction.
2. Prefer parsing and structured extraction (Python `email`, HTML sanitizer) over fragile regex hacks.
3. Validate via EDA and manual spot-checks before labeling or tweaking features.
4. Use NLP (spaCy) for robust linguistic features; use regex only for small, well-defined checks.
5. Let the results stand: report what the data shows instead of forcing an expected outcome.

---

## 3) Concrete Pipeline (phased)

### Phase 1 — Data Engineering (Must be perfect)
- Sources: curated benign (SpamAssassin ham or cleaned Enron), Phishbowl (real phishing), Controlled AI-generated phishing (your own prompts).
- Output: `unified_dataset.json` with schema:
  ```json
  {
    "id": "str",
    "source": "str",
    "subject": "str",
    "text_body": "str",    // cleaned text only
    "has_url": true/false,
    "extracted_links": ["..."],
    "actual_class": 0|1
  }
  ```
- Key step: write an `email_cleaner.py` that uses the `email` stdlib to parse MIME parts, strip headers, remove quoted replies and signatures, and return only the message text.

### Phase 2 — Exploratory Data Analysis (Before labeling)
- Compute: counts, avg words, empty bodies, top n-grams per source, URL prevalence.
- Manual checks: read ~50 random samples per source; fix cleaning bugs found.
- Do not proceed until distributions look consistent across sources (format-wise).

### Phase 3 — Feature Engineering (Use NLP)
- Tools: `spaCy` (medium model), optionally `textstat` for readability metrics, `langdetect` for language.
- Features to extract (examples):
  - Imperative verbs / requests (POS patterns)
  - Named Entities (ORG, PERSON) and whether entities appear in visible link text
  - Presence and type of URLs (shorteners, suspicious TLDs)
  - Semantic intent signals (requests for credentials, transfers) via small rule-based classifiers on dependency patterns
  - Obfuscation cues via character-level checks (but after cleaning headers)

### Phase 4 — Modeling & Evaluation
- Baselines: Logistic Regression, Random Forest.
- Metrics: ROC-AUC, precision@k, confusion matrix, false positive analysis specifically on benign corpora.
- Use stratified CV and a holdout set from each source for generalization testing.

### Phase 5 — Documentation & Demo Prep
- Export final `labeled_dataset.csv` and a short `README.md` explaining cleaning, features, and model steps.
- Produce reproducible notebooks or scripts and a short slide with key findings.

---

## 4) Common Mistakes & How to Avoid Them
- Mistake: treating different formats as equivalent. Fix: canonicalize early.
- Mistake: tuning regex to a dataset. Fix: define linguistic rules from prior research / domain knowledge and test on held-out data.
- Mistake: not unit-testing extraction functions. Fix: add unit tests and small sample-based checks.
- Mistake: hiding or commenting out problematic data sources. Fix: clearly document exclusions and reasons.

---

## 5) How to Use Copilot Efficiently (Working Patterns)
- Use Copilot for: scaffolding scripts, generating unit tests, turning plain-language requests into code blocks, and producing reproducible notebooks.
- Prompts that work best:
  - "Write a Python script that parses raw MIME email files and extracts a clean plain-text body, removing quoted replies and signatures. Include unit tests and example outputs."
  - "Generate 10 representative phishing prompts for an LLM to create high-quality phishing emails, with controlled attributes (urgency, credential request, bank impersonation)."
  - "Create spaCy-based functions to detect imperative sentences and named entities and return boolean features."
- Ask Copilot to generate tests first, then the implementation. Run the tests locally and iterate.

---

## 6) What You Should Learn (2–3 days focused)
- `pandas` basics: cleaning strings, `.str` methods, groupby, sampling.
- Python `email` stdlib + `beautifulsoup4` for HTML-to-text cleaning.
- `spaCy`: tokenization, POS, dependency parsing, named entities.
- Basic ML workflow: train/test split, cross-validation, simple classifiers (LR/RF), and evaluation metrics.

---

## 7) Minimal First Tasks (Next 48 hours)
1. Implement `email_cleaner.py` that outputs `unified_dataset.json` (100% required).
2. Run EDA and manually inspect 50 samples per source.
3. Implement simple `spaCy` features and compute cue counts.
4. Train a baseline LR and produce a one-slide summary.

---

## 8) Notes on Ethics & Safety
- Do not publish raw phishing emails with PII. When sharing examples, redact any personal identifiers.
- When generating AI phishing emails for the dataset, keep them private and tag them clearly as synthetic.

---

If you want, I can now:
- create `email_cleaner.py` (parser + small test set), or
- implement the `unified_dataset.json` writer and a sample EDA notebook.

Pick one and I'll scaffold it next.
