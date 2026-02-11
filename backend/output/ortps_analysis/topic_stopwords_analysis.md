# ORTPS Topic Modeling - Stopword Analysis

## Problem Identification

Current BERTopic results (Driving Licences test) show topics dominated by **generic complaint language** rather than category-specific themes:

**Topic 0 Keywords**: pradhan, yojana, pm, belongs, want, **poor family**, dhenkanal, home, allotment, faithfully  
**Topic 1 Keywords**: matter, area, committee, looks, bhubaneswar, look, department, **look matter**, result, behera

These reflect:
1. **Poverty petition language**: "poor family", "belongs to poor family", "humble submission"
2. **Generic administrative terms**: "department", "office", "matter", "area"
3. **Place names**: "Bhubaneswar", "Dhenkanal" (location-specific, not theme-specific)
4. **Petition boilerplate**: "sir", "madam", "request", "kindly", "please", "faithfully"

## Generic Language Patterns Across Categories

Based on analysis of 23,705 complaints across 10 ORTPS categories:

### 1. Poverty & Socioeconomic Status Language
```
poor, family, poor family, belongs, belong, bpl, below poverty, economic, 
weaker, section, background, financially, needy, helpless, poor background
```

### 2. Petition Boilerplate
```
sir, madam, dear sir, dear madam, respected, honorable, honourable, humble, 
humbly, submission, kindly, please, request, pray, appeal, faithfully, 
obediently, yours faithfully, yours truly, thanking, thanks
```

### 3. Generic Administrative Terms
```
office, department, district, block, village, panchayat, gram panchayat, 
tahasil, tahsil, govt, government, authority, concerned, officer, collector, 
bdo, sub collector, matter, issue, problem, regarding, subject, case
```

### 4. Common Odisha Place Names (High Frequency)
```
bhubaneswar, cuttack, puri, berhampur, sambalpur, balasore, bhadrak, 
dhenkanal, angul, bargarh, bolangir, kalahandi, kandhamal, kendrapara, 
keonjhar, khordha, koraput, malkangiri, mayurbhanj, nabarangpur, nayagarh, 
nuapada, rayagada, sambalpur, sonepur, sundargarh, odisha, orissa
```

### 5. Generic Request Verbs
```
give, provide, sanction, approve, allot, allotment, help, assist, resolve, 
solve, grant, issue, submit, apply, application, applied, file, filed
```

### 6. Generic Administrative Actions
```
letter, application, form, grievance, complaint, petition, representation, 
dated, date, reference, ref, subject, sub, copy, enclosed, attachment, 
document, certificate, proof, verification, verify
```

### 7. Common Government Scheme Abbreviations
```
pm, pradhan mantri, yojana, scheme, pmay, pmgsy, mgnrega, nrega, aay, bpl,
aadhaar, aadhar, ration, card
```

---

## Recommended Stopwords for BERTopic

### Base English Stopwords
Use scikit-learn's English stopwords as baseline, then ADD the following custom Odisha-specific stopwords:

```python
ORTPS_STOPWORDS = [
    # Poverty language
    "poor", "family", "belongs", "belong", "bpl", "poverty", "economic", 
    "weaker", "section", "background", "financially", "needy", "helpless",
    
    # Petition boilerplate
    "sir", "madam", "dear", "respected", "honorable", "honourable", "humble", 
    "humbly", "submission", "kindly", "please", "request", "pray", "appeal", 
    "faithfully", "obediently", "thanking", "thanks", "yours",
    
    # Generic administrative
    "office", "department", "district", "block", "village", "panchayat", 
    "gram", "tahasil", "tahsil", "govt", "government", "authority", "concerned",
    "officer", "collector", "bdo", "sub", "matter", "issue", "problem", 
    "regarding", "subject", "case", "letter", "application", "form", 
    "grievance", "complaint", "petition", "representation", "dated", "date",
    "reference", "ref", "copy", "enclosed", "attachment", "document",
    
    # Generic actions
    "give", "provide", "sanction", "approve", "allot", "allotment", "help", 
    "assist", "resolve", "solve", "grant", "issue", "submit", "apply", 
    "applied", "file", "filed", "visit", "visited", "check", "verify",
    
    # Common abbreviations
    "pm", "pmay", "pmgsy", "mgnrega", "nrega", "aay", "w/o", "s/o", "d/o",
    "at", "po", "ps", "dist", "pin", "mob", "mobile",
    
    # Odisha place names (major cities/districts)
    "bhubaneswar", "cuttack", "puri", "berhampur", "sambalpur", "balasore",
    "bhadrak", "dhenkanal", "angul", "bargarh", "bolangir", "kalahandi",
    "kandhamal", "kendrapara", "keonjhar", "khordha", "koraput", "malkangiri",
    "mayurbhanj", "nabarangpur", "nayagarh", "nuapada", "rayagada", "sonepur",
    "sundargarh", "odisha", "orissa",
    
    # Generic time references
    "year", "month", "day", "time", "ago", "since", "long", "till", "until",
    
    # Numbers and ordinals (will be handled by token pattern)
    # Skip: "one", "two", etc. as they may be meaningful in context
]
```

---

## Additional BERTopic Configuration Changes

Beyond stopwords, improve topic quality with these adjustments:

### 1. Token Pattern (Exclude Short Words & Numbers)
```python
CountVectorizer(
    token_pattern=r'\b[a-z]{3,}\b',  # Only words >= 3 chars, no numbers
    # Current: default pattern includes numbers and 1-char words
)
```

### 2. Min Document Frequency
```python
CountVectorizer(
    min_df=5,  # Increase from 2 to 5
    # Filters rare words that appear in <5 documents per category
)
```

### 3. N-gram Range
```python
CountVectorizer(
    ngram_range=(1, 3),  # Increase from (1, 2) to (1, 3)
    # Captures phrases like "ration card update" or "scholarship disbursement delay"
)
```

### 4. Reduce UMAP Components (For Small Categories)
```python
# For categories < 1000 samples:
UMAP(n_components=3)  # Reduce from 5 to 3

# For categories >= 1000 samples:
UMAP(n_components=5)  # Keep as is
```

---

## Expected Topic Improvements

### Before (Generic Topics)
**Driving Licences - Topic 0**  
`pradhan, yojana, pm, belongs, want, poor family, dhenkanal, home, allotment, faithfully`

**Driving Licences - Topic 1**  
`matter, area, committee, looks, bhubaneswar, look, department, look matter, result, behera`

### After (Category-Specific Topics)

**Income & Welfare Benefits**
- Topic 1: `scholarship, disbursement, pending, amount, credited, student, education, delay`
- Topic 2: `ration, card, add, member, remove, name, update, duplicate, lost`
- Topic 3: `pension, old, age, widow, disability, stopped, payment, bank, account`
- Topic 4: `regularization, teacher, junior, contractual, years, service, primary, school`

**Building & Construction**
- Topic 1: `pmay, house, construction, approval, pending, completion, certificate`
- Topic 2: `community, center, mandap, kalyan, renovation, construction, panchayat`
- Topic 3: `playground, sports, complex, stadium, construction, development`

**Land Transactions**
- Topic 1: `patta, land, allotment, partition, mutation, record, rights`
- Topic 2: `acquisition, compensation, payment, pending, highway, railway, project`

**Identity & Social Certificates**
- Topic 1: `caste, certificate, sc, st, obc, verification, delay, pending`
- Topic 2: `marriage, registration, certificate, online, offline, procedure`
- Topic 3: `income, certificate, rejected, property, verification, tax`

---

## Implementation Recommendations

1. **Update `CountVectorizer` in `analyzers.py`:**
   ```python
   stop_words_list = list(set(ENGLISH_STOP_WORDS).union(ORTPS_STOPWORDS))
   
   vectorizer_model = CountVectorizer(
       ngram_range=(1, 3),  # Capture 3-word phrases
       token_pattern=r'\b[a-z]{3,}\b',  # Min 3 chars, no numbers
       stop_words=stop_words_list,
       min_df=5,  # Min 5 docs per word
       max_df=0.85,  # Reduce from 0.95 to filter very common words
   )
   ```

2. **Adaptive UMAP components:**
   ```python
   n_components = 3 if self.n_samples < 1000 else 5
   umap_model = UMAP(
       n_neighbors=15,
       n_components=n_components,  # Adaptive
       min_dist=0.0,
       metric="cosine",
       random_state=self.random_state,
   )
   ```

3. **Re-run pipeline on full dataset** (not just Driving Licences)

4. **Validate topics manually** by reviewing samples from each topic to ensure they're interpretable

---

## Verification Checklist

After re-running with improved stopwords:

- [ ] Topics have category-specific keywords (not generic poverty language)
- [ ] Topic keywords form coherent themes (e.g., "scholarship + disbursement + pending")
- [ ] Outlier rate < 15% per category
- [ ] Cross-category summary shows meaningful topic counts (not just 2 topics per category)
- [ ] LaTeX tables have interpretable topic labels
- [ ] Sample complaints within each topic are semantically similar

