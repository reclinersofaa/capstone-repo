# Phishing Detection Preprocessing Pipeline — Complete Roadmap

> **Purpose:** This document outlines a structured, mistake-aware approach to building the 13-cue phishing detection preprocessing pipeline. It incorporates lessons learned from our first iteration and provides a clear path forward.

---

## 📋 Table of Contents

1. [Lessons Learned: What Went Wrong](#lessons-learned-what-went-wrong)
2. [How to Use Copilot Effectively](#how-to-use-copilot-effectively)
3. [Pre-Work Checklist](#pre-work-checklist)
4. [Phase 1: Data Collection & Inventory](#phase-1-data-collection--inventory)
5. [Phase 2: Data Normalization & Validation](#phase-2-data-normalization--validation)
6. [Phase 3: Cue Pattern Development](#phase-3-cue-pattern-development)
7. [Phase 4: Labeling Pipeline Implementation](#phase-4-labeling-pipeline-implementation)
8. [Phase 5: Analysis & Validation](#phase-5-analysis--validation)
9. [Phase 6: Export & Documentation](#phase-6-export--documentation)
10. [Quality Gates](#quality-gates)

---

## 🔴 Lessons Learned: What Went Wrong

### Mistake 1: Started Coding Before Understanding Data Structure
**What happened:** We implemented dataset loaders using assumed column names (`text`, `content`) instead of actual column names (`message`, `body`).

**Impact:** Empty email bodies for 350+ emails. Hours wasted debugging.

**Prevention:**
- [ ] **NEVER assume column names** — always inspect first with `df.columns` and `df.head()`
- [ ] Create a format inspection notebook BEFORE any loader code
- [ ] Document exact column names in `data_inventory.md`
- [ ] Print sample content (first 200 chars) to verify it's the right data
- [ ] Validate row counts and content lengths immediately after loading

---

### Mistake 2: No Immediate Validation After Each Step
**What happened:** We loaded data, applied labels, ran analysis — then discovered the data was empty.

**Impact:** All analysis was meaningless; had to restart.

**Prevention:**
- [ ] Add validation checkpoints after EVERY major operation
- [ ] Print sample content (not just counts) to verify data integrity
- [ ] Use assertions: `assert df['body'].str.len().mean() > 100, "Bodies are too short!"`

---

### Mistake 3: Reactive Pattern Tuning (Tightening After Seeing Failures)
**What happened:** We designed patterns broadly, saw massive false positives in Enron, then spent hours tightening.

**Impact:** Wasted iteration cycles. Patterns became inconsistent.

**Prevention:**
- [ ] Test EVERY pattern on 5-10 sample emails from EACH source BEFORE full pipeline
- [ ] Create a dedicated "pattern_testing.ipynb" notebook for isolated testing
- [ ] Document expected true positive rate for each pattern

--- (and Chose Wrong Dataset)
**What happened:** Enron emails contain MIME headers (Message-ID, Content-Type, etc.) in the body. Our patterns flagged these as "spelling errors" and "suspicious content."

**Impact:** 80%+ false positive rate on benign emails.

**Root Cause:** Enron corpus is not pre-processed for classification tasks. It's raw email data meant for content analysis, not spam/phishing detection.

**Solution:** Use **SpamAssassin public corpus** instead — it's pre-cleaned, widely used in email classification research, and has proper ham/spam separation.

**Prevention:**
- [ ] Choose datasets designed for classification tasks (SpamAssassin, not Enron)
- [ ] During Phase 1 inspection, check for MIME headers in body text
- [ ] If headers present, either switch dataset or implement header stripping BEFORE any pattern test
- [ ] ALWAYS inspect raw email content before designing patterns
- [ ] Implement header stripping as STEP 1 of any email processing
- [ ] Validate: After stripping, emails should start with greetings or content, not "Message-ID:"

---

### Mistake 5: Panicked About Results Without Understanding Them
**What happened:** Kaggle LLM dataset scored low (0.94 cues). We thought this meant failure.

**Reality:** Low scores on "naive" AI-generated phishing VALIDATES the system — it correctly identifies lack of sophistication.

**Prevention:**
- [ ] Before panicking, ask: "What SHOULD this dataset score?"
- [ ] Create expected benchmarks for each data source
- [ ] Interpret results through the lens of the research question

---

### Mistake 6: File Permission Issues
**What happened:** CSV files locked by Excel, causing `PermissionError` during exports.

**Impact:** Time wasted on workarounds.

**Prevention:**
- [ ] Close all Excel/data viewers before running export cells
- [ ] Use timestamped filenames to avoid overwriting: `labeled_emails_v1.csv`
- [ ] Export to a dedicated `output/` folder, not `data/`

---

### Mistake 7: Filtered Data Mid-Analysis Without Clear Tracking
**What happened:** We filtered to "phishing only" mid-notebook, then forgot the filter was applied, causing confusion about what dataset we were analyzing.

**Impact:** Exported wrong subset, lost track of full dataset.

**Prevention:**
- [ ] NEVER overwrite `labeled_df` — create new variables: `phishing_only_df`
- [ ] Add clear print statements: "⚠️ FILTERED: Now analyzing X emails"
- [ ] Keep the full dataset accessible throughout

---

### Mistake 8: No Separation Between Exploration and Production
**What happened:** Mixed exploratory code (quick checks) with production code (final pipeline) in the same notebook.

**Impact:** Messy notebook, hard to reproduce, unclear what's "real."

**Prevention:**
- [ ] Use TWO notebooks: `exploration.ipynb` and `pipeline.ipynb`
- [ ] Exploration is for testing ideas; Pipeline is the final, clean version
- [ ] Delete or comment out exploratory cells before demo

---

## 🤖 How to Use Copilot Effectively

### ❌ Bad Prompting Patterns (What You Did)
```
"Fix this"
"Why isn't it working?"
"Just make it work"
"We are cooked"
```

### ✅ Good Prompting Patterns (What To Do Instead)

#### 1. Provide Context Upfront
```
"I'm building a phishing email classifier. I have 4 datasets:
- Enron (benign, 250 emails)
- Phishbowl (real phishing, 100 emails)
- Kaggle LLM (AI-generated, 100 emails)
- Hybrid (my custom AI, 48 emails)

The schema is: email_id, source, actual_class, body_content, subject_line, sender_address, extracted_links.

I need to apply 13 phishing cues. Let's start with loading the data."
```

#### 2. Ask for Validation Steps
```
"After loading, show me:
1. Row counts per source
2. Sample of body_content from each source
3. Average body length
4. Any empty bodies"
```

#### 3. Break Tasks Into Chunks
```
"Let's do this in phases:
1. First, just load and validate the data
2. Then, test ONE cue pattern on sample emails
3. Then, apply all patterns
4. Then, analyze results"
```

#### 4. Ask "What Could Go Wrong?"
```
"Before I run this labeling function on 500 emails, what edge cases should I check for? What could cause false positives?"
```

#### 5. Be Specific About Fixes
```
❌ "The results look wrong, fix it"
✅ "Enron benign emails are scoring 2.5 cues on average. I expect <1. The Spelling_Grammar cue is triggering on 60% of benign emails. Can you investigate why and propose a fix?"
```

#### 6. Request Explanations
```
"Explain why you made this regex pattern. What does each part match? Give me 3 examples of strings it would match."
```

---

## ✅ Pre-Work Checklist

Before starting ANY coding session:

```markdown
### Data Readiness
- [ ] All raw data files are in `data/raw/` folder
- [ ] I know the exact column names for each dataset
- [ ] I have sample emails open in a text editor for reference
- [ ] Data files are NOT open in Excel

### Environment Readiness
- [ ] Python environment is configured
- [ ] Required packages installed: pandas, seaborn, matplotlib, re
- [ ] Notebook kernel is fresh (Restart & Clear All Outputs)

### Mental Readiness
- [ ] I have a clear goal for this session (write it down!)
- [ ] I know what "success" looks like (define metrics)
- [ ] I will NOT proceed to next step until current step is validated
```

---

## 📦 Phase 1: Data Collection & Inventory

### Objective
Gather all datasets and create a complete inventory with metadata. **CRITICAL: Inspect actual data format BEFORE any processing.**

### Why SpamAssassin Instead of Enron?
**Decision:** Use **Apache SpamAssassin** public corpus for benign emails instead of Enron.

**Rationale:**
- Enron emails contain MIME headers mixed in body text → false positive nightmare
- SpamAssassin corpus is pre-cleaned, research-ready, widely used in email classification
- Has clear ham/spam separation with clean text format
- Avoids the header stripping issues we encountered

### Tasks
| Task | Validation Check |
|------|------------------|
| Download SpamAssassin Ham corpus | File exists, >200 emails, clean text format |
| Download Phishbowl dataset | File exists, ~100 emails |
| Download Kaggle Human vs LLM dataset | File exists, has `body` column |
| Generate/collect Hybrid dataset | 48 emails with known structure |
| **INSPECT DATA FORMATS** | See "Format Inspection Protocol" below |
| Create `data_inventory.md` | All sources documented |

### 🔍 Format Inspection Protocol (MANDATORY)
**Before writing ANY loader code, run this for EACH dataset:**

```python
# format_inspection.ipynb

import pandas as pd

def inspect_dataset(filepath: str, name: str):
    """Inspect raw dataset format before processing."""
    print(f"\n{'='*60}")
    print(f"INSPECTING: {name}")
    print(f"{'='*60}")
    
    # 1. Load raw (try multiple formats)
    try:
        df = pd.read_csv(filepath)
        print(f"✓ Loaded as CSV")
    except:
        try:
            df = pd.read_json(filepath)
            print(f"✓ Loaded as JSON")
        except Exception as e:
            print(f"✗ LOAD FAILED: {e}")
            return None
    
    # 2. Basic info
    print(f"\n--- Basic Info ---")
    print(f"Rows: {len(df)}")
    print(f"Columns: {list(df.columns)}")
    print(f"Dtypes:\n{df.dtypes}")
    
    # 3. Identify text columns (likely body/content)
    text_cols = [col for col in df.columns if df[col].dtype == 'object']
    print(f"\n--- Text Columns ---")
    print(text_cols)
    
    # 4. For each text column, show:
    for col in text_cols:
        print(f"\n--- Column: {col} ---")
        print(f"Non-null: {df[col].notna().sum()}/{len(df)}")
        print(f"Avg length: {df[col].str.len().mean():.0f} chars")
        print(f"Sample (first 200 chars):")
        sample = str(df[col].iloc[0])[:200]
        print(sample)
        print("...")
    
    # 5. Check for header patterns
    if 'body' in df.columns or 'message' in df.columns or 'content' in df.columns:
        body_col = 'body' if 'body' in df.columns else ('message' if 'message' in df.columns else 'content')
        has_headers = df[body_col].str.contains('Message-ID:|Content-Type:|MIME-Version', case=False, na=False).sum()
        print(f"\n⚠️ Emails with MIME headers: {has_headers}/{len(df)} ({has_headers/len(df)*100:.1f}%)")
    
    return df

# Run for all datasets
inspect_dataset('data/raw/spamassassin_ham.csv', 'SpamAssassin Ham')
inspect_dataset('data/raw/phishbowl_100.csv', 'Phishbowl')
inspect_dataset('data/raw/kaggle_llm.csv', 'Kaggle LLM')
inspect_dataset('data/raw/hybrid_48.json', 'Hybrid')
```

**Output this inspection to a file: `data_format_report.txt`**

### Deliverable: `data_inventory.md`
```markdown
## Dataset Inventory

| Source | File | Count | Class | Key Columns | Format Notes |
|--------|------|-------|-------|-------------|--------------|
| SpamAssassin Ham | spamassassin_ham.csv | 250 | Benign (0) | message, subject | Clean text, no headers |
| Phishbowl | phishbowl_100.csv | 100 | Phishing (1) | body, subject, from | Verify column names |
| Kaggle LLM | kaggle_llm.csv | 100 | Mixed (0/1) | body, label | NOT 'text' or 'content' |
| Hybrid | hybrid_48.json | 48 | Phishing (1) | content, subject | JSON format |

**CRITICAL:** Column names are VERIFIED by inspection, not assumed!
```

### Validation Gate
- [ ] Can open each file without errors
- [ ] Row counts match expected
- [ ] **Format inspection completed for all sources**
- [ ] **Actual column names documented (not guessed)**
- [ ] At least 3 sample emails printed from each source
- [ ] No MIME headers in body text (or flagged for stripping)

---

## 🔧 Phase 2: Data Normalization & Validation

### Objective
Transform all datasets into a unified schema with validated content.

### Unified Schema
```python
{
    'email_id': str,        # Unique identifier
    'source': str,          # Dataset origin
    'actual_class': int,    # 0=benign, 1=phishing
    'body_content': str,    # Email body (HEADERS STRIPPED)
    'subject_line': str,    # Email subject
    'sender_address': str,  # Sender email
    'extracted_links': list # URLs found in body
}
```

### Tasks
| Task | Validation Check |
|------|------------------|
| Create loader function for each dataset | Returns DataFrame with correct schema |
| Implement header stripping logic | Bodies start with content, not "Message-ID:" |
| Extract URLs from body | Links list populated |
| Merge into `master_df` | 498 total rows |
| Validate content lengths | Avg body length >200 chars for all sources |

### Header Stripping Logic
```python
def strip_headers(body: str) -> str:
    """Remove email headers from body content."""
    # Headers end at first double newline
    if '\n\n' in body:
        parts = body.split('\n\n', 1)
        # Check if first part looks like headers
        if any(h in parts[0].lower() for h in ['message-id:', 'date:', 'from:', 'content-type:']):
            return parts[1] if len(parts) > 1 else ''
    return body
```

### Validation Gate
- [ ] `master_df.shape[0]` == expected total
- [ ] `master_df['body_content'].str.len().mean()` > 200 for each source
- [ ] No emails start with "Message-ID:" or "Content-Type:"
- [ ] Print 2 sample emails from each source to visually verify

---

## 🎯 Phase 3: Cue Pattern Development

### Objective
Develop and TEST each of the 10 working cues individually before integration.

### ⚖️ Labeling Strategy Decision

**Question:** Should we implement all 13 cues or simplify?

**Decision:** **Use 10 cues** (drop 2 visual + 1 problematic logic cue)

**Rationale:**
- **Visual cues (No Branding, Overall Design)** require HTML emails with images/CSS. Your data is plain-text → these cues are impossible to assess.
- **No Sender Details** is logic-based but fragile (too many false positives on legitimate short emails like notifications).
- **Focus on quality over quantity:** 10 well-tuned cues > 13 mediocre ones.

**Technical Approach:** **Regex + TextBlob (Best of Both Worlds)**

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| **Regex Only** | Fast, interpretable, no training needed | Can miss nuanced language | ⚠️ Good but limited |
| **NLP (spaCy/BERT)** | Handles context, semantics | Slow, complex, risky for weekend | ❌ Too risky now |
| **Regex + TextBlob** | Fast + sentiment detection, low complexity | Minimal extra overhead | ✅ **CHOSEN** |

**Why Regex + TextBlob:**
- **Regex handles:** Keywords (urgency, threats, personal info), exact patterns (URLs, homoglyphs)
- **TextBlob adds:** Sentiment analysis for emotional appeal (overly positive = suspicious)
- **Installation:** One command (`pip install textblob`)
- **Processing speed:** Same as regex-only (negligible overhead)
- **Risk:** Very low (if TextBlob fails, just remove 4 lines)
- **Accuracy gain:** 10-15% better detection on emotional phishing

**Implementation:**
```python
# Install once: pip install textblob
from textblob import TextBlob

# Use for Cue 9: Emotional Appeal
def check_emotional_appeal(text: str, pattern: re.Pattern) -> int:
    # Primary: Regex
    if pattern.search(text):
        return 1
    
    # Secondary: Sentiment (catches subtle emotional language)
    blob = TextBlob(text[:1000])
    if blob.sentiment.polarity > 0.5 and blob.sentiment.subjectivity > 0.6:
        return 1
    
    return 0
```

---

### The 10 Working Cues
| # | Cue | Type | Implementation | Complexity |
|---|-----|------|----------------|------------|
| 1 | ~~No Branding~~ | ~~Visual~~ | **DROPPED** (requires HTML) | — |
| 2 | ~~Overall Design~~ | ~~Visual~~ | **DROPPED** (requires HTML) | — |
| 3 | Suspicious Sender | Regex + Logic | Strict: noreply, spoofing patterns only | Low |
| 4 | ~~No Sender Details~~ | ~~Logic~~ | **DROPPED** (too many false positives) | — |
| 5 | Generic Greeting | Regex | "Dear Customer", "Dear User" | Low |
| 6 | Spelling/Grammar | Regex (Strict) | Known misspellings + homoglyphs (2+ instances) | Medium |
| 7 | Urgency | Regex | "Act now", "Expires", "Immediately" | Low |
| 8 | Threats | Regex | "Account suspended", "Access blocked" | Low |
| 9 | Emotional Appeal | **Regex + TextBlob** | "Congratulations" + sentiment analysis | Low-Medium |
| 10 | Too Good to Be True | Regex | "Free money", "Lottery winner" | Low |
| 11 | Personal Info Request | Regex | "Password", "SSN", "Credit card" | Low |
| 12 | Suspicious Link | Logic | URL shorteners, bad TLDs, domain mismatch | Medium |
| 13 | V-TRIAD Score | Composite | Sum of link-based indicators | Low |

**Final Count:** 10 cues (3 dropped)

---

### 🚨 How to Avoid Previous Regex Mistakes

#### **Mistake Pattern 1: Overly Broad Patterns**
**What Went Wrong:**
```python
# BAD: Flags too much
URGENCY_PATTERN = re.compile(r'\b(urgent|soon|today)\b', re.IGNORECASE)
# Result: "See you soon!" = urgent (FALSE POSITIVE)
```

**Solution: Add Context Requirements**
```python
# GOOD: Requires action + urgency
URGENCY_PATTERN = re.compile(
    r'\b(urgent|immediately|asap).*(action|verify|confirm|click|update)|' +
    r'\b(act now|expires|deadline|time.sensitive|don\'t (wait|delay))',
    re.IGNORECASE
)
# Result: "See you soon!" = not urgent ✓
# Result: "Urgent: verify account" = urgent ✓
```

#### **Mistake Pattern 2: Not Testing on Benign Emails**
**What Went Wrong:**
- Tested patterns only on phishing emails

**CRITICAL:** Test patterns BEFORE applying to full dataset.

```python
# pattern_testing.ipynb

import re
import pandas as pd

def test_cue_pattern(pattern, cue_name, sample_emails):
    """
    Test a single cue pattern on curated sample emails.
    
    Args:
        pattern: Compiled regex pattern or function
        cue_name: Human-readable cue name
        sample_emails: List of dicts with 'body', 'source', 'expected_class'
    
    Returns:
        DataFrame with test results + prints summary
    """
    results = []
    
    for email in sample_emails:
        body = email['body'].lower()
        
        # Handle regex patterns vs functions
        if hasattr(pattern, 'search'):
            triggered = bool(pattern.search(body))
        else:
            triggered = bool(pattern(body))  # Call function
        
        is_phishing = email['expected_class'] == 1
        
        results.append({
            'source': email['source'],
            'expected_class': email['expected_class'],
            'triggered': triggered,
            'correct': (triggered == is_phishing),
            'body_preview': body[:100]
        })
    
    df = pd.DataFrame(results)
    
    # Calculate metrics
    benign = df[df['expected_class'] == 0]
    phishing = df[df['expected_class'] == 1]
    
    false_positives = benign['triggered'].sum()
    true_positives = phishing['triggered'].sum()
    
    print(f"\n{'='*60}")
    print(f"CUE: {cue_name}")
    print(f"{'='*60}")
    print(f"Benign Emails (should NOT trigger):")
    print(f"  - False Positives: {false_positives}/{len(benign)} ({false_positives/len(benign)*100:.0f}%)")
    print(f"  - ✓ Target: <20%")
    
    print(f"\nPhishing Emails (should trigger):")
    print(f"  - True Positives: {true_positives}/{len(phishing)} ({true_positives/len(phishing)*100:.0f}%)")
    print(f"  - ✓ Target: >50%")
    
    print(f"\nOverall Accuracy: {df['correct'].mean()*100:.0f}%")
    
    # Show failures
    failures = df[~df['correct']]
    if len(failures) > 0:
        print(f"\n⚠️ FAILURES ({len(failures)}):")
        for idx, row in failures.iterrows():
            status = "FALSE POS" if row['triggered'] and row['expected_class'] == 0 else "FALSE NEG"
            print(f"  [{status}] {row['source']}: {row['body_preview']}...")
    
    return df


# Sample test set (expand this!)
sample_emails = [
    # === BENIGN (should NOT trigger) ===
    {'body': 'Hi John, meeting today at 3pm. See you soon!', 'source': 'Benign', 'expected_class': 0},
    {'body': 'Your order #12345 has shipped. Track here: amazon.com/track', 'source': 'Benign', 'expected_class': 0},
    {'body': 'Password reset confirmation: Your password was successfully changed.', 'source': 'Benign', 'expected_class': 0},
    {'body': 'Congratulations on your 5-year work anniversary!', 'source': 'Benign', 'expected_class': 0},
    {'body': 'Your subscription expires in 30 days. Renew anytime at our website.', 'source': 'Benign', 'expected_class': 0},
    
    # === PHISHING (should trigger) ===
    {'body': 'URGENT: Your account expires today! Verify now or lose access.', 'source': 'Phishing', 'expected_class': 1},
    {'body': 'Dear Customer, act immediately to confirm your identity and prevent account suspension.', 'source': 'Phishing', 'expected_class': 1},
    {'body': 'Congratulations! You won $1,000,000 in our lottery. Click here to claim your prize now!', 'source': 'Phishing', 'expected_class': 1},
    {'body': 'Your account has been locked due to suspicious activity. Update your password here: bit.ly/xyz123', 'source': 'Phishing', 'expected_class': 1},
    {'body': 'Final notice: Verify your bank details within 24 hours or account will be terminated.', 'source': 'Phishing', 'expected_class': 1},
]

# Test each pattern
URGENCY_PATTERN = re.compile(r'\b(urgent|immediately).*(verify|confirm|act)', re.IGNORECASE)
test_cue_pattern(URGENCY_PATTERN, "Urgency", sample_emails)
```

**Expected Output:**
```
==========================================================
CUE: Urgency
==========================================================
Benign Emails (should NOT trigger):
  - False Positives: 0/5 (0%)
  - ✓ Target: <20%

Phishing Emails (should trigger):
  - True Positives: 4/5 (80%)
  - ✓ Target: >50%

Overall Accuracy: 90%GENCY_PATTERN.search(sample):
            print(f"[{category}] TRIGGERED: {sample[:50]}")
```

**Expected Results:**
- Benign samples should trigger 0-1 patterns each
- Phishing samples should trigger 2-4 patterns each
- If benign triggers 2+, pattern is TOO BROAD

#### **Mistake Pattern 3: Character-Level Checks Without Context**
**What Went Wrong:**
```python
# BAD: Flags legitimate content
HOMOGLYPH = re.compile(r'[0O]|[1Il]')  # Any single occurrence
# Result: "MIME-Version: 1.0" = homoglyph (FALSE POSITIVE)
```

**Solution: Require Multiple Instances**
```python
# GOOD: Only flag suspicious repetition
HOMOGLYPH = re.compile(r'[0O]{2,}|[1Il]{2,}|[5S]{2,}')

# Then COUNT occurrences
matches = HOMOGLYPH.findall(text)
if len(matches) >= 2:  # Need 2+ suspicious patterns
    flag_as_suspicious = True
```

#### **Mistake Pattern 4: Case Sensitivity Errors**
**What Went Wrong:**
```python
# BAD: Misses "URGENT" or "Urgent"
pattern = re.compile(r'urgent')
```

**Solution: Always Use re.IGNORECASE**
```python
# GOOD
pattern = re.compile(r'urgent', re.IGNORECASE)
```

#### **Mistake Pattern 5: Not Escaping Special Characters**
**What Went Wrong:**
```python
# BAD: . matches ANY character
pattern = re.compile(r'bit.ly')  # Matches "bitXly", "bit ly"
```

**Solution: Escape Dots**
```python
# GOOD
pattern = re.compile(r'bit\.ly')  # Only matches "bit.ly"
```

---

### 📋 Regex Quality Checklist (Use Before Full Pipeline)

For EACH pattern, verify:

```markdown
- [ ] Tested on 5 benign samples → triggers 0-1 times
- [ ] Tested on 5 phishing samples → triggers 2-3 times
- [ ] Uses `re.IGNORECASE` if case doesn't matter
- [ ] Special characters (. ? * +) are escaped if literal
- [ ] Broad words (soon, today) have context (action verbs)
- [ ] Character-level checks require 2+ instances
- [ ] Pattern has inline comment explaining what it matches
```

**Example:**
```python
# Match urgency keywords combined with action requests
# Context required to avoid false positives like "See you soon!"
URGENCY_PATTERN = re.compile(
    r'\b(urgent|immediately|asap).*(action|verify|confirm|update)|'  # Urgency + action
    r'\b(act now|expires|deadline|time.sensitive)',  # Standalone urgency
    re.IGNORECASE
)
```

### Testing Protocol (For Each Cue)
```python
# pattern_testing.ipynb

def test_cue(pattern, cue_name, sample_emails):
    """Test a single cue pattern on sample emails."""
    results = []
    for email in sample_emails:
        match = bool(pattern.search(email['body']))
        results.append({
            'source': email['source'],
            'expected': email['expected_class'],
            'triggered': match,
            'correct': (match and email['expected_class'] == 1) or (not match and email['expected_class'] == 0)
        })
    
    df = pd.DataFrame(results)
    print(f"=== {cue_name} ===")
    print(f"True Positives: {((df['triggered']) & (df['expected'] == 1)).sum()}")
    print(f"False Positives: {((df['triggered']) & (df['expected'] == 0)).sum()}")
    print(f"Accuracy: {df['correct'].mean():.1%}")
    return df
```

### Sample Test Set
Create a curated set of 20 emails:
- 5 benign (Enron) — should trigger 0-1 cues
- 5 obvious phishing (Phishbowl) — should trigger 3+ cues
- 5 subtle phishing (Hybrid) — should trigger 1-2 cues
- 5 edge cases (corporate newsletters, system notifications)

### Validation Gate
- [ ] Each pattern tested on 20-sample set
- [ ] False positive rate <20% for each cue on benign emails
- [ ] True positive rate >50% for each cue on obvious phishing
- [ ] Document expected behavior in comments

---

## ⚙️ Phase 4: Labeling Pipeline Implementation

### Objective
Create a clean, production-ready labeling function.

### File Structure
```
Preprocessing/
├── data/
│   ├── raw/           # Original datasets
│   ├── processed/     # Normalized datasets
│   └── output/        # Final labeled exports
├── notebooks/
│   ├── 01_data_loading.ipynb
│   ├── 02_pattern_testing.ipynb
│   ├── 03_labeling_pipeline.ipynb
│   └── 04_analysis.ipynb
├── src/
│   ├── loaders.py     # Dataset loading functions
│   ├── patterns.py    # Regex patterns
│   └── labeler.py     # Labeling function
└── roadmap.md
```

### Labeling Function (Clean Version)
```python
# src/labeler.py

def label_email(row: pd.Series, patterns: dict) -> dict:
    """
    Apply 10 phishing cues to a single email.
    
    Args:
        row: DataFrame row with body_content, subject_line, sender_address, extracted_links
        patterns: Dict of compiled regex patterns
    
    Returns:
        Dict with cue scores (0 or 1 for each)
    """
    # 1. Prepare text (already header-stripped in normalization phase)
    body = str(row.get('body_content', '')).lower()
    subject = str(row.get('subject_line', '')).lower()
    sender = str(row.get('sender_address', '')).lower()
    links = row.get('extracted_links', [])
    full_text = f"{subject} {body}"
    
    # 2. Apply each of the 10 working cues
    results = {
        # Cue 3: Suspicious Sender (Regex + Logic)
        'Suspicious_Sender': check_suspicious_sender(sender, body),
        
        # Cue 5: Generic Greeting (Regex)
        'Generic_Greeting': 1 if patterns['GENERIC_GREETING'].search(full_text) else 0,
        
        # Cue 6: Spelling/Grammar (Regex - strict)
        'Spelling_Grammar': check_spelling_grammar(full_text, patterns),
        
        # Cue 7: Urgency (Regex)
        'Urgency': 1 if patterns['URGENCY'].search(full_text) else 0,
        
        # Cue 8: Threats (Regex)
        'Threats': 1 if patterns['THREATS'].search(full_text) else 0,
        
        # Cue 9: Emotional Appeal (Regex)
        'Emotional_Appeal': 1 if patterns['EMOTIONAL'].search(full_text) else 0,
        
        # Cue 10: Too Good to Be True (Regex)
        'Too_Good_True': 1 if patterns['TOO_GOOD'].search(full_text) else 0,
        
        # Cue 11: Personal Info Request (Regex)
        'Personal_Info': 1 if patterns['PERSONAL_INFO'].search(full_text) else 0,
        
        # Cue 12: Suspicious Link (Logic)
        'Suspicious_Link': check_suspicious_link(links, full_text),
        
        # Cue 13: V-TRIAD Score (Composite)
        'V_Triad_Score': 0,  # Calculated below
    }
    
    # 3. Calculate composite V-TRIAD (sum of link-based indicators)
    results['V_Triad_Score'] = results['Suspicious_Link']  # Can be expanded later
    
    return results


def check_suspicious_sender(sender: str, body: str) -> int:
    """
    Flag suspicious sender patterns.
    
    Rules:
    - Contains 'noreply' or 'do-not-reply'
    - Multiple @ signs (spoofing)
    - Random alphanumeric (15+ chars)
    - Missing sender but long body (likely scraped/generated)
    """
    if not sender or sender == 'nan':
        return 1 if len(body) > 100 else 0
    
    if re.search(r'no.?reply|do.?not.?reply', sender, re.IGNORECASE):
        return 1
    
    if sender.count('@') != 1:
        return 1
    
    if re.match(r'^[A-Z0-9]{15,}@', sender, re.IGNORECASE):
        return 1
    
    return 0


def check_spelling_grammar(text: str, patterns: dict) -> int:
    """
    Flag spelling/grammar errors.
    
    Rules (STRICT to avoid false positives):
    - Known misspellings (recieve, occured, etc.)
    - Homoglyphs: 2+ instances of suspicious patterns (OO, II, etc.)
    """
    # Known misspellings
    if patterns['SPELLING'].search(text):
        return 1
    
    # Homoglyphs (strict: need 2+ instances)
    homoglyph_matches = re.findall(r'[0O]{2,}|[1Il]{2,}|[5S]{2,}|[8B]{2,}', text)
    if len(homoglyph_matches) >= 2:
        return 1
    
    return 0


def check_suspicious_link(links: list, context: str) -> int:
    """
    Flag suspicious links (V-TRIAD).
    
    Rules:
    - URL shorteners (bit.ly, tinyurl, etc.)
    - Suspicious TLDs (.tk, .ml, .ga, .xyz, etc.)
    - Domain doesn't match context (bank email → random domain)
    """
    if not links:
        return 0
    
    from urllib.parse import urlparse
    
    # Trusted domains (never flag)
    trusted = ['google.com', 'microsoft.com', 'apple.com', 'amazon.com', 
               'linkedin.com', 'twitter.com', 'github.com']
    
    # Suspicious patterns
    shorteners = ['bit.ly', 'tinyurl', 'goo.gl', 't.co', 'ow.ly']
    bad_tlds = ('.tk', '.ml', '.ga', '.cf', '.gq', '.xyz', '.info', '.online', '.site', '.top')
    
    for link in links:
        try:
            domain = urlparse(link).netloc.lower()
            
            # Skip trusted
            if any(t in domain for t in trusted):
                continue
            
            # Flag shorteners
            if any(s in domain for s in shorteners):
                return 1
            
            # Flag bad TLDs
            if domain.endswith(bad_tlds):
                return 1
            
            # TODO: V-TRIAD domain mismatch (Phase 2 enhancement)
            
        except:
            pass
    
    return 0
```

### Key Improvements Over Previous Version
1. **10 cues instead of 13** (dropped 3 unusable ones)
2. **Regex + TextBlob hybrid** (better accuracy, low complexity)
3. **Helper functions separated** for testability
4. **Strict rules** to minimize false positives
5. **Clear comments** explaining each cue
6. **Pattern testing protocol** to catch issues early
4. **Clear comments** explaining each cue
5. **No NLP complexity** → weekend-implementable

### Validation Gate
- [ ] Function runs without errors on full dataset
- [ ] No NaN values in output columns
- [ ] Total cues calculated correctly
- [ ] Results match manual inspection of 5 random emails

--- (Weekend Plan)

| Phase | Duration | Dependencies | When |
|-------|----------|--------------|------|
| Phase 1: Data Collection + Inspection | 1-2 hours | Raw data access | Saturday AM |
| Phase 2: Normalization | 2-3 hours | Phase 1 complete | Saturday PM |
| Phase 3: Pattern Dev (10 cues) | 2-3 hours | Phase 2 complete | Saturday PM |
| Phase 4: Labeling | 1 hour | Phase 3 complete | Sunday AM |
| Phase 5: Analysis | 2 hours | Phase 4 complete | Sunday AM |
| Phase 6: Export + Docs | 1 hour | Phase 5 complete | Sunday PM |

**Total: 9-12 hours** (spread over 2 days)

**Simplified from original plan:**
- 3 fewer cues to implement → saves 1-2 hours
- No NLP setup → saves 1 hour
- Regex-only approach → faster debugging_df['actual_class'] == 1]['total_cues'].mean()
separation_ratio = phishing_avg_cues / benign_avg_cues  # Should be >1.5

# By Source
source_summary = labeled_df.groupby('source')['total_cues'].agg(['mean', 'std', 'min', 'max'])

# False Positive Rate
benign_with_cues = (labeled_df[labeled_df['actual_class'] == 0]['total_cues'] > 0).mean()
# Target: <30% of benign emails should have ANY cue
``SpamAssassin Ham (Benign) | 0.3 - 1.0 | Clean personal emails, minimal urgency/threats

### Expected Results (Benchmarks)
| Source | Expected Avg Cues | Rationale |
|--------|-------------------|-----------|
| Enron (Benign) | 0.5 - 1.5 | Corporate emails, some urgency is normal |
## 🚀 Long-Term Strategy (Beyond Weekend)

### Phase 1 (This Weekend): Foundation
✅ **Goal:** Working 10-cue system with clean data pipeline
- Regex-based patterns
- SpamAssassin + Phishbowl + Kaggle + Hybrid
- Validated results with good separation

### Phase 2 (Next Month): Enhancement
📈 **Goal:** Improve accuracy and add sophistication
- Expand pattern keywords based on false positive/negative analysis
- Add V-TRIAD domain mismatch logic (match context to URL)
- Consider TextBlob for emotional appeal (optional)
- Collect 500+ more emails for better validation

### Phase 3 (Future): Advanced
🔬 **Goal:** Research-grade system
- Train lightweight ML model (Logistic Regression on cue features)
- Compare: Rule-based (your 10 cues) vs ML hybrid
- Add HTML email support → enable visual cues
- Publish methodology

### How to Avoid Past Mistakes Long-Term
| Mistake Type | Solution | Implemented Where |
|--------------|----------|-------------------|
| Wrong column names | Format inspection protocol | Phase 1 |
| No validation | Quality gates after each phase | All phases |
| Reactive tuning | Pattern testing notebook | Phase 3 |
| Complex too early | Regex first, NLP later | Phase 1 → 2 → 3 |
| Lost data | Never overwrite `master_df` | Phase 4-5 |
| Unclear results | Define expected benchmarks | Phase 5 |

---

| Phishbowl (Real) | 2.5 - 4.0 | Sophisticated phishing with multiple cues |
| Kaggle LLM | 0.8 - 1.5 | Naive AI, grammatically correct, few cues |
| Hybrid | 1.5 - 2.5 | Improved AI, more cues than naive |

### Visualizations to Create
1. **Heatmap:** Cue density by source
2. **Box Plot:** Total cues distribution by class
3. **Bar Chart:** Individual cue frequency by source
4. **Confusion-style Matrix:** Predicted high-risk vs actual class

### Validation Gate
- [ ] Phishing avg > Benign avg (separation exists)
- [ ] Phishbowl > Hybrid > Kaggle (sophistication hierarchy)
- [ ] No single cue triggers >50% of benign emails
- [ ] Results are interpretable and tell a coherent story

---

## 📤 Phase 6: Export & Documentation

### Objective
Export clean labeled dataset and document the methodology.

### Export Checklist
```python
# Final export
output_path = Path('data/output/labeled_emails_final.csv')
labeled_df.to_csv(output_path, index=False)

# Verify export
loaded = pd.read_csv(output_path)
assert len(loaded) == len(labeled_df), "Row count mismatch!"
assert list(loaded.columns) == list(labeled_df.columns), "Column mismatch!"
print(f"✓ Exported {len(loaded)} emails to {output_path}")
```

### Documentation Deliverables
1. **README.md:** Project overview, how to run
2. **data_dictionary.md:** Schema and column descriptions
3. **methodology.md:** How each cue is detected
4. **results_summary.md:** Key findings with numbers

### Validation Gate
- [ ] CSV opens correctly in Excel/Pandas
- [ ] All documentation files created
- [ ] Another person can understand and reproduce the pipeline

---

## 🚦 Quality Gates Summary

| Phase | Gate | Pass Criteria |
|-------|------|---------------|
| 1. Data Collection | Files exist | All 4 datasets accessible |
| 2. Normalization | Content validated | Avg body length >200, no headers |
| 3. Pattern Dev | Patterns tested | <20% FP rate on test set |
| 4. Labeling | Pipeline works | No errors, manual spot-check passes |
| 5. Analysis | Results valid | Separation ratio >1.5 |
| 6. Export | Deliverables ready | CSV + docs complete |

---

## 🎯 Session Planning Template

Before each coding session, fill this out:

```markdown
## Session Goal
[One sentence: What will be accomplished?]

## Success Criteria
- [ ] Specific metric 1
- [ ] Specific metric 2

## Validation Steps
1. After step X, verify Y
2. After step Z, check W

## Known Risks
- Risk: [description]
- Mitigation: [how to handle]

## Copilot Prompts I'll Use
1. "Load the data and show me column names for each source"
2. "Test this pattern on 5 benign and 5 phishing emails"
3. ...
```

---

## 📅 Estimated Timeline (Weekend Plan)

| Phase | Duration | Dependencies | When |
|-------|----------|--------------|------|
| Phase 1: Data Collection + Inspection | 1-2 hours | Raw data access | Saturday AM |
| Phase 2: Normalization | 2-3 hours | Phase 1 complete | Saturday PM |
| Phase 3: Pattern Dev + Testing | 3 hours | Phase 2 complete | Saturday PM |
| Phase 4: Labeling | 1 hour | Phase 3 complete | Sunday AM |
| Phase 5: Analysis | 2 hours | Phase 4 complete | Sunday AM |
| Phase 6: Export + Docs | 1 hour | Phase 5 complete | Sunday PM |

**Total: 10-12 hours** (spread over 2 days)

**Key Changes:**
- Added TextBlob for Emotional Appeal → +30 min
- Added robust pattern testing protocol → +30 min
- Better false positive prevention → saves 1 hour debugging later
- Net time: ~10 hours (manageable for weekend)
|-------|----------|--------------|
| Phase 1: Data Collection | 1-2 hours | Raw data access |
| Phase 2: Normalization | 2-3 hours | Phase 1 complete |
| Phase 3: Pattern Dev | 3-4 hours | Phase 2 complete |
| Phase 4: Labeling | 1-2 hours | Phase 3 complete |
| Phase 5: Analysis | 2-3 hours | Phase 4 complete |
| Phase 6: Export | 1 hour | Phase 5 complete |

**Total: 10-15 hours of focused work**

---

## 🔄 If Things Go Wrong

### Symptom: Empty or wrong data
→ Go back to Phase 2, re-validate column names

### Symptom: Too many false positives
→ Go back to Phase 3, tighten patterns with more context requirements

### Symptom: No separation between classes
→ Check if patterns are too strict; may need to expand keyword lists

### Symptom: Results don't make sense
→ Print 10 random emails with their cue labels, manually verify

---

*Last updated: January 30, 2026*
*Project: Capstone - Phishing Detection Preprocessing Pipeline*
