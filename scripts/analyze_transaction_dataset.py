"""
Comprehensive Data Analysis: transaction_dataset.csv
=====================================================
Statistical, Descriptive, and Advanced Analysis
"""
import pandas as pd
import numpy as np
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

print("=" * 80)
print("COMPREHENSIVE DATA ANALYSIS: transaction_dataset.csv")
print("=" * 80)

# Load data
DATA_PATH = r"C:\Users\Administrator\Desktop\datasetAMTTP\transaction_dataset.csv"
print(f"\nLoading data from: {DATA_PATH}")
df = pd.read_csv(DATA_PATH)

# Clean column names (remove leading/trailing spaces)
df.columns = df.columns.str.strip()

# ============================================================================
# SECTION 1: BASIC DATASET OVERVIEW
# ============================================================================
print("\n" + "=" * 80)
print("1. BASIC DATASET OVERVIEW")
print("=" * 80)

print(f"\nDataset Shape: {df.shape[0]:,} rows × {df.shape[1]} columns")
print(f"Memory Usage: {df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")

# ============================================================================
# SECTION 2: FEATURES AND DATA TYPES
# ============================================================================
print("\n" + "=" * 80)
print("2. ALL FEATURES AND DATA TYPES")
print("=" * 80)

# Categorize columns by type
numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
categorical_cols = df.select_dtypes(include=['object']).columns.tolist()

print(f"\nTotal Features: {len(df.columns)}")
print(f"  - Numeric: {len(numeric_cols)}")
print(f"  - Categorical/Object: {len(categorical_cols)}")

print("\n" + "-" * 80)
print("COMPLETE FEATURE LIST WITH DATA TYPES:")
print("-" * 80)
print(f"{'#':<4} {'Feature Name':<50} {'Data Type':<15} {'Non-Null':<15}")
print("-" * 80)

for i, col in enumerate(df.columns, 1):
    dtype = str(df[col].dtype)
    non_null = df[col].notna().sum()
    null_pct = (df[col].isna().sum() / len(df)) * 100
    null_info = f"{non_null:,}" if null_pct == 0 else f"{non_null:,} ({null_pct:.1f}% null)"
    print(f"{i:<4} {col:<50} {dtype:<15} {null_info:<15}")

# ============================================================================
# SECTION 3: DESCRIPTIVE STATISTICS
# ============================================================================
print("\n" + "=" * 80)
print("3. DESCRIPTIVE STATISTICS (Numeric Features)")
print("=" * 80)

# Key numeric features (exclude index columns)
key_numeric = [c for c in numeric_cols if c not in ['Unnamed: 0', 'Index']]

desc_stats = df[key_numeric].describe().T
desc_stats['missing'] = df[key_numeric].isna().sum()
desc_stats['missing_%'] = (df[key_numeric].isna().sum() / len(df)) * 100
desc_stats['unique'] = df[key_numeric].nunique()

print("\n" + desc_stats[['count', 'mean', 'std', 'min', '25%', '50%', '75%', 'max']].to_string())

# ============================================================================
# SECTION 4: CATEGORICAL FEATURES ANALYSIS
# ============================================================================
print("\n" + "=" * 80)
print("4. CATEGORICAL FEATURES ANALYSIS")
print("=" * 80)

for col in categorical_cols:
    print(f"\n--- {col} ---")
    print(f"Unique values: {df[col].nunique()}")
    print(f"Missing: {df[col].isna().sum()} ({df[col].isna().sum()/len(df)*100:.1f}%)")
    print(f"Top 5 values:")
    print(df[col].value_counts().head(5).to_string())

# ============================================================================
# SECTION 5: TARGET VARIABLE ANALYSIS (FLAG)
# ============================================================================
print("\n" + "=" * 80)
print("5. TARGET VARIABLE ANALYSIS (FLAG)")
print("=" * 80)

if 'FLAG' in df.columns:
    print(f"\nFLAG Distribution:")
    print(df['FLAG'].value_counts())
    print(f"\nClass Distribution (%):")
    print((df['FLAG'].value_counts(normalize=True) * 100).round(2))
    print(f"\nClass Imbalance Ratio: {df['FLAG'].value_counts()[0] / df['FLAG'].value_counts()[1]:.2f}:1")

# ============================================================================
# SECTION 6: MISSING VALUES ANALYSIS
# ============================================================================
print("\n" + "=" * 80)
print("6. MISSING VALUES ANALYSIS")
print("=" * 80)

missing = df.isna().sum()
missing_pct = (missing / len(df)) * 100
missing_df = pd.DataFrame({
    'Missing Count': missing,
    'Missing %': missing_pct
}).sort_values('Missing Count', ascending=False)

missing_cols = missing_df[missing_df['Missing Count'] > 0]
if len(missing_cols) > 0:
    print(f"\nColumns with missing values: {len(missing_cols)}")
    print(missing_cols.to_string())
else:
    print("\n✓ No missing values in the dataset!")

# ============================================================================
# SECTION 7: STATISTICAL TESTS & ADVANCED ANALYSIS
# ============================================================================
print("\n" + "=" * 80)
print("7. ADVANCED STATISTICAL ANALYSIS")
print("=" * 80)

# Key features for analysis
key_features = [
    'total Ether sent', 'total ether received', 'total ether balance',
    'Sent tnx', 'Received Tnx', 'avg val sent', 'avg val received',
    'Unique Sent To Addresses', 'Unique Received From Addresses',
    'Time Diff between first and last (Mins)', 'Number of Created Contracts'
]

# Filter to features that exist
key_features = [f for f in key_features if f in df.columns]

print("\n--- Skewness & Kurtosis (Key Features) ---")
print(f"{'Feature':<45} {'Skewness':>12} {'Kurtosis':>12} {'Distribution':<20}")
print("-" * 90)

for feat in key_features:
    if df[feat].dtype in [np.float64, np.int64]:
        data = df[feat].dropna()
        if len(data) > 0:
            skew = stats.skew(data)
            kurt = stats.kurtosis(data)
            
            if abs(skew) < 0.5:
                dist = "Symmetric"
            elif skew > 0:
                dist = "Right-skewed"
            else:
                dist = "Left-skewed"
                
            print(f"{feat:<45} {skew:>12.3f} {kurt:>12.3f} {dist:<20}")

# ============================================================================
# SECTION 8: CORRELATION ANALYSIS
# ============================================================================
print("\n" + "=" * 80)
print("8. CORRELATION ANALYSIS (Top Correlations)")
print("=" * 80)

if len(key_features) > 1:
    corr_matrix = df[key_features].corr()
    
    corr_pairs = []
    for i in range(len(corr_matrix.columns)):
        for j in range(i+1, len(corr_matrix.columns)):
            corr_pairs.append({
                'Feature 1': corr_matrix.columns[i],
                'Feature 2': corr_matrix.columns[j],
                'Correlation': corr_matrix.iloc[i, j]
            })
    
    corr_df = pd.DataFrame(corr_pairs)
    corr_df = corr_df.sort_values('Correlation', key=abs, ascending=False)
    
    print("\nTop 10 Strongest Correlations:")
    print(corr_df.head(10).to_string(index=False))

# Correlation with FLAG
print("\n--- Correlation with FLAG (Target) ---")
flag_corr = df[key_features + ['FLAG']].corr()['FLAG'].drop('FLAG').sort_values(key=abs, ascending=False)
print(flag_corr.head(15).to_string())

# ============================================================================
# SECTION 9: OUTLIER DETECTION (IQR Method)
# ============================================================================
print("\n" + "=" * 80)
print("9. OUTLIER DETECTION (IQR Method)")
print("=" * 80)

print(f"\n{'Feature':<45} {'Outliers':>10} {'% of Data':>12}")
print("-" * 70)

for feat in key_features:
    if df[feat].dtype in [np.float64, np.int64]:
        data = df[feat].dropna()
        Q1 = data.quantile(0.25)
        Q3 = data.quantile(0.75)
        IQR = Q3 - Q1
        lower = Q1 - 1.5 * IQR
        upper = Q3 + 1.5 * IQR
        outliers = ((data < lower) | (data > upper)).sum()
        pct = (outliers / len(data)) * 100
        print(f"{feat:<45} {outliers:>10,} {pct:>11.2f}%")

# ============================================================================
# SECTION 10: FRAUD vs NON-FRAUD COMPARISON
# ============================================================================
print("\n" + "=" * 80)
print("10. FRAUD vs NON-FRAUD COMPARISON")
print("=" * 80)

if 'FLAG' in df.columns:
    print(f"\nMean Values by Class (FLAG):")
    fraud_comparison = df.groupby('FLAG')[key_features].mean()
    print(fraud_comparison.T.to_string())
    
    print("\n--- T-Test Results (Feature differences between Fraud vs Non-Fraud) ---")
    print(f"{'Feature':<45} {'t-statistic':>12} {'p-value':>15} {'Significant':>12}")
    print("-" * 90)
    
    non_fraud = df[df['FLAG'] == 0]
    fraud = df[df['FLAG'] == 1]
    
    for feat in key_features:
        if df[feat].dtype in [np.float64, np.int64]:
            nf_data = non_fraud[feat].dropna()
            f_data = fraud[feat].dropna()
            if len(nf_data) > 1 and len(f_data) > 1:
                t_stat, p_val = stats.ttest_ind(nf_data, f_data)
                sig = "Yes***" if p_val < 0.001 else ("Yes**" if p_val < 0.01 else ("Yes*" if p_val < 0.05 else "No"))
                print(f"{feat:<45} {t_stat:>12.3f} {p_val:>15.2e} {sig:>12}")

# ============================================================================
# SECTION 11: FEATURE IMPORTANCE INDICATORS
# ============================================================================
print("\n" + "=" * 80)
print("11. FEATURE VARIANCE ANALYSIS (Potential Importance)")
print("=" * 80)

variance_df = pd.DataFrame({
    'Feature': key_numeric,
    'Variance': df[key_numeric].var(),
    'Std': df[key_numeric].std(),
    'Mean': df[key_numeric].mean(),
    'CV': df[key_numeric].std() / df[key_numeric].mean().replace(0, np.nan)
}).sort_values('CV', ascending=False)

print("\nTop 15 Features by Coefficient of Variation:")
print(variance_df.head(15)[['Feature', 'Mean', 'Std', 'CV']].to_string(index=False))

# ============================================================================
# SECTION 12: ZERO-VALUE ANALYSIS
# ============================================================================
print("\n" + "=" * 80)
print("12. ZERO-VALUE ANALYSIS")
print("=" * 80)

print(f"\n{'Feature':<50} {'Zero Count':>12} {'% Zeros':>10}")
print("-" * 75)

for col in key_numeric[:20]:
    zeros = (df[col] == 0).sum()
    pct = (zeros / len(df)) * 100
    if pct > 5:  # Only show features with >5% zeros
        print(f"{col:<50} {zeros:>12,} {pct:>9.1f}%")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("ANALYSIS SUMMARY")
print("=" * 80)

fraud_count = df['FLAG'].sum() if 'FLAG' in df.columns else 0
normal_count = len(df) - fraud_count

print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                        DATASET ANALYSIS SUMMARY                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ Dataset:          transaction_dataset.csv                                    ║
║ Total Records:    {df.shape[0]:>10,}                                                ║
║ Total Features:   {df.shape[1]:>10}                                                 ║
║   - Numeric:      {len(numeric_cols):>10}                                                 ║
║   - Categorical:  {len(categorical_cols):>10}                                                 ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ TARGET (FLAG):                                                               ║
║   - Normal (0):   {normal_count:>10,} ({normal_count/len(df)*100:.1f}%)                                    ║
║   - Fraud (1):    {fraud_count:>10,} ({fraud_count/len(df)*100:.1f}%)                                     ║
║   - Imbalance:    {normal_count/fraud_count:.1f}:1                                                   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ Missing Values:   {df.isna().sum().sum():>10,}                                                ║
║ Memory Usage:     {df.memory_usage(deep=True).sum() / 1024**2:>10.2f} MB                                        ║
╚══════════════════════════════════════════════════════════════════════════════╝

RECOMMENDED FOR MODEL TRAINING:
1. Drop columns: 'Unnamed: 0', 'Index', 'Address'
2. Handle categorical: 'ERC20 most sent token type', 'ERC20_most_rec_token_type'
3. Target variable: 'FLAG' (0=normal, 1=fraud)
4. Consider log-transform for highly skewed features
5. Handle class imbalance (SMOTE, class weights, etc.)
""")

print("=" * 80)
print("Analysis Complete!")
print("=" * 80)
