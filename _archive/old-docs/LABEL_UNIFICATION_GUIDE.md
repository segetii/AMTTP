# Label Unification Guide: Bitcoin Heist + Ethereum Phishing

## Problem Statement

Your merged dataset contains two different types of fraudulent transaction labels:

1. **Bitcoin Heist (BTC)**: Ransomware taxonomy (family names)
   - `label_raw`: Specific ransomware families (e.g., "CryptoWall", "Locky", etc.)
   - `white`: Legitimate transactions
   - ~2.9M rows

2. **Ethereum (ETH)**: Binary phishing labels
   - `label`: 1 = phishing, 0 = legitimate
   - ~10K rows

These are **different threat types** (ransomware vs phishing) with different label formats.

---

## Dataset Composition

```
Total Rows: 2,926,538
├── BTC: 2,916,697 (99.66%)
│   ├── Legitimate (white): 2,875,284 (98.25%)
│   ├── Ransomware (41 families): 41,413 (1.41%)
│   └── Family examples: CryptoWall, Locky, CryptoTorLocker, DMALocker, etc.
│
└── ETH: 9,841 (0.34%)
    ├── Legitimate (label=0): 7,662 (77.88%)
    └── Phishing (label=1): 2,179 (22.12%)
```

**Label Imbalance:**
- Legitimate: 2,882,946 (98.51%)
- Malicious: 43,592 (1.49%)

---

## Solution: Unified Binary Label

### Strategy: Aggregated Malicious Classification

Create a unified `label_unified` column:

```python
0 = Legitimate
1 = Malicious (ransomware OR phishing)
```

### Implementation

```python
# Create unified label
df['label_unified'] = 0  # Default to legitimate

# For Bitcoin: Map ransomware families to 1
btc_mask = df['chain'] == 'BTC'
ransomware_mask = btc_mask & (df['label_raw'] != 'white') & (df['label_raw'].notna())
df.loc[ransomware_mask, 'label_unified'] = 1

# For Ethereum: Use existing phishing label
eth_mask = df['chain'] == 'ETH'
phishing_mask = eth_mask & (df['label'] == 1.0)
df.loc[phishing_mask, 'label_unified'] = 1
```

### Results

| Class | Count | Percentage |
|-------|-------|-----------|
| Legitimate (0) | 2,882,946 | 98.51% |
| Malicious (1) | 43,592 | 1.49% |

| Dataset | Legitimate | Malicious | Total |
|---------|-----------|----------|-------|
| BTC | 2,875,284 | 41,413 | 2,916,697 |
| ETH | 7,662 | 2,179 | 9,841 |
| **Total** | **2,882,946** | **43,592** | **2,926,538** |

---

## Alternative Strategies

### Option 2: Multi-Class Labels (Advanced)

If you want to distinguish threat types:

```python
df['label_threat'] = 'legitimate'

# Bitcoin ransomware
btc_ransomware = (df['chain'] == 'BTC') & (df['label_raw'] != 'white')
df.loc[btc_ransomware, 'label_threat'] = 'ransomware'

# Ethereum phishing
eth_phishing = (df['chain'] == 'ETH') & (df['label'] == 1.0)
df.loc[eth_phishing, 'label_threat'] = 'phishing'

# Convert to codes: 0=legitimate, 1=ransomware, 2=phishing
label_mapping = {'legitimate': 0, 'ransomware': 1, 'phishing': 2}
df['label_threat_code'] = df['label_threat'].map(label_mapping)
```

**Result Distribution:**
- Legitimate: 2,882,946 (98.51%)
- Ransomware: 41,413 (1.42%)
- Phishing: 2,179 (0.07%)

**Challenge:** Class imbalance requires:
- Weighted loss function
- SMOTE or oversampling
- Stratified cross-validation

### Option 3: Keep Ransomware Families (Maximum Info)

For deep analysis, preserve family information:

```python
# One-hot encode top families
df['is_ransomware'] = (df['label_raw'] != 'white') & (df['label_raw'].notna())
df['ransomware_family'] = df['label_raw'].fillna('legitimate')

# Get top 10 families
top_families = df[df['is_ransomware']]['ransomware_family'].value_counts().head(10).index
for family in top_families:
    df[f'family_{family}'] = (df['ransomware_family'] == family).astype(int)
```

---

## Recommendations

### ✅ Use Unified Binary Label When:
- Training a general fraud detector
- Need simplicity and interpretability
- Limited computational resources
- Acceptable to treat ransomware + phishing as one class

### 🔄 Use Multi-Class When:
- Need to distinguish threat types
- Have resources for class balancing
- Want separate model for ransomware vs phishing
- Business requires threat-specific alerts

### 🔬 Keep Family Info When:
- Performing threat intelligence analysis
- Need specific ransomware family detection
- Building explainability features
- Research/academic purposes

---

## Implementation in train_baseline_merged_only.py

### Option A: Modify Script (Recommended)

Add to the data loading section:

```python
# Unify labels
df['label'] = 0
btc_mask = df['chain'] == 'BTC'
ransomware_mask = btc_mask & (df['label_raw'] != 'white') & (df['label_raw'].notna())
df.loc[ransomware_mask, 'label'] = 1

eth_mask = df['chain'] == 'ETH'
phishing_mask = eth_mask & (df['label'] == 1.0)
df.loc[phishing_mask, 'label'] = 1
```

### Option B: Pre-process Dataset

Save unified dataset to new file:

```python
df['label_unified'] = 0
# ... apply same logic as above ...
df.to_parquet('merged_clean_unified_label.parquet', index=False)
```

Then train on new file.

---

## Validation

After unification, check:

```python
# Distribution
print(df['label_unified'].value_counts())

# Cross-check with original labels
print(pd.crosstab(df['chain'], df['label_unified']))

# Verify no data loss
print(f"Total rows: {len(df)}")
assert len(df) == 2_926_538

# Check for nulls
print(f"Null labels: {df['label_unified'].isna().sum()}")
assert df['label_unified'].isna().sum() == 0
```

---

## Next Steps

1. **Choose strategy** (Recommended: Unified Binary)
2. **Apply unification** to merged dataset
3. **Save processed dataset** (optional)
4. **Update training script** to use unified label
5. **Train model** with `train_baseline_merged_only.py`
6. **Monitor metrics** for any label quality issues

---

## References

- **Bitcoin Heist**: https://www.kaggle.com/datasets/ellipticco/elliptic-data-set
- **Ethereum Phishing**: https://www.kaggle.com/datasets/nkshirsagar/ethereum-phishing-dataset
- **Combined Dataset**: Your `merged_clean.parquet`

