# Legacy-Inspired V3 Pipeline - 2-Day Implementation Plan

## Philosophy

**V2's Problem**: Over-engineered with too many conditional gates, reducing recall
- Urgency+action gate dropped detection significantly
- Strict homoglyph detection (edit distance < 2) was too conservative  
- Header stripping removed legitimate sender signals
- Domain patterns over-fitted to specific providers

**V3's Solution**: Combine legacy's broad detection with modern ML feature engineering
- Simple, broad cue patterns (prioritize recall over precision)
- Rich feature extraction (40+ features for ML models)
- Let ML models learn nuanced patterns instead of hand-crafted rules

---

## Day 1 Morning: Simplify Detection (2-3 hours)

### Remove Over-Engineering
1. **Eliminate urgency+action gate**: Detect urgency OR action independently
2. **Relax homoglyph detection**: Allow edit distance ≤ 3 for common brands
3. **Keep sender headers**: Don't strip display names, they contain valuable signals
4. **Generalize domain patterns**: Match broader TLD patterns, not specific providers

### Implement 10 Core Cues (Broad Patterns)
```python
CORE_CUES = [
    'Suspicious_Sender',      # Mismatch, spoofing indicators
    'Urgency',                # Urgent, immediate, deadline, limited time
    'Action_Required',        # Click, verify, confirm, update (separate from urgency)
    'Threats',                # Suspend, locked, unauthorized, expire
    'Personal_Info_Request',  # SSN, password, credit card, account number
    'Generic_Greeting',       # Dear customer, valued user, account holder
    'Links_Present',          # URLs detected in body
    'Suspicious_Links',       # IP addresses, obfuscated domains
    'Spelling_Errors',        # Typos in subject or body
    'Unusual_Sender_Domain'   # Free email providers for "official" messages
]
```

**Deliverable**: `simplified_cues.ipynb` with 10 core detection functions

---

## Day 1 Afternoon: Feature Engineering (3-4 hours)

### Extract 40+ ML Features

#### Structural Features (10 features)
- Body length, subject length
- Link count, unique domains
- Capitalization ratio, punctuation density
- HTML tag presence
- Attachment count

#### Syntactic Features (8 features)  
- Greeting type (personalized vs generic)
- Sender-domain match
- Display name vs email mismatch
- Reply-to field mismatch
- Signature presence

#### Semantic Features (12 features)
- Urgency score (word frequency)
- Threat score (word frequency)
- Financial terms score
- Personal info request score
- Action verb count
- Question count
- Exclamation count

#### Interaction Features (8 features)
- CTA (call-to-action) count
- Link-to-text ratio
- Form field count
- Button count (HTML)
- Obfuscation indicators (zero-width chars, homoglyphs)

#### Domain Features (5 features)
- TLD category (com/org/gov/edu vs xyz/tk)
- Domain age (if available via lookup)
- HTTPS presence
- Subdomain depth

**Deliverable**: `feature_engineering.ipynb` with extraction pipeline

---

## Day 2 Morning: ML-Ready Dataset (2 hours)

### Create Feature Matrix
1. Apply simplified cues to master_legacy.csv (10 binary features)
2. Extract 40+ engineered features
3. Combine into `labeled_features.csv`:
   - Columns: email_id, source, actual_class + 10 cues + 40 features (~55 cols)
   - Rows: 488 emails

### Validate Feature Separation
```python
# Check feature distributions by class
benign_df = labeled_features[labeled_features['actual_class'] == 'Benign']
phishing_df = labeled_features[labeled_features['actual_class'] == 'Phishing']

# Compare means for top 10 discriminative features
feature_comparison = pd.DataFrame({
    'Benign': benign_df[feature_cols].mean(),
    'Phishing': phishing_df[feature_cols].mean(),
    'Difference': abs(benign_df[feature_cols].mean() - phishing_df[feature_cols].mean())
}).sort_values('Difference', ascending=False)
```

**Deliverable**: `labeled_features.csv` (488 rows × 55 columns)

---

## Day 2 Afternoon: ML Baseline (2-3 hours)

### Train Two Models

#### 1. Logistic Regression (Interpretable Baseline)
```python
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix

X = labeled_features[feature_cols]
y = labeled_features['actual_class'].map({'Benign': 0, 'Phishing': 1})

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)

lr_model = LogisticRegression(class_weight='balanced', max_iter=1000)
lr_model.fit(X_train, y_train)

y_pred = lr_model.predict(X_test)
print(classification_report(y_test, y_pred, target_names=['Benign', 'Phishing']))
```

#### 2. Random Forest (Performance Baseline)
```python
from sklearn.ensemble import RandomForestClassifier

rf_model = RandomForestClassifier(n_estimators=100, class_weight='balanced', random_state=42)
rf_model.fit(X_train, y_train)

y_pred_rf = rf_model.predict(X_test)
print(classification_report(y_test, y_pred_rf, target_names=['Benign', 'Phishing']))

# Feature importance
feature_importance = pd.DataFrame({
    'Feature': feature_cols,
    'Importance': rf_model.feature_importances_
}).sort_values('Importance', ascending=False).head(15)
print(feature_importance)
```

### Evaluate Against V2
- **Target Metrics**:
  - Recall on real phishing (Phishbowl): 90%+ (vs V2's ~65%)
  - F1 score: 85%+ (vs V2's ~70%)
  - Precision: 80%+ (acceptable trade-off for security system)

**Deliverable**: `ml_baseline.ipynb` with trained models and evaluation

---

## Deliverables Summary

1. ✓ `simplified_cues.ipynb`: 10 core cue detection functions (broad patterns)
2. ✓ `feature_engineering.ipynb`: 40+ feature extraction pipeline
3. ✓ `labeled_features.csv`: ML-ready dataset (488 × 55)
4. ✓ `ml_baseline.ipynb`: Logistic Regression + Random Forest baselines
5. ✓ Evaluation report comparing V3 vs V2 performance

---

## Trade-offs & Limitations

### What We Gain
- **Higher Recall**: Broad patterns catch more real phishing (90%+ target)
- **ML Flexibility**: Rich features let models learn nuanced patterns
- **Interpretability**: Feature importance shows what matters most
- **Scalability**: Easy to add new features without rewriting rules

### What We Sacrifice
- **Some Precision**: May get more false positives (80% precision vs V2's 85%)
- **Compute Cost**: ML training/inference slower than rule-based V2
- **Data Dependency**: ML models need diverse training data to generalize

### Why It's Worth It
- Security systems should prioritize recall (catching threats) over precision (avoiding false alarms)
- False positives are manageable (user can ignore), false negatives are catastrophic (user gets phished)
- ML models adapt to new phishing tactics better than rigid rule systems

---

## Next Steps After V3
1. Collect real-world feedback (user reports, false positive analysis)
2. Experiment with advanced models (XGBoost, neural networks)
3. Implement active learning (retrain on misclassified examples)
4. Deploy as hybrid system: V3 ML + human review for edge cases
