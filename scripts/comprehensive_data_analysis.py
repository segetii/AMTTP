"""
Comprehensive Data Analysis: ethereum_clean.csv
================================================
Statistical, Descriptive, and Advanced Analysis
"""
import pandas as pd
import numpy as np
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

print("=" * 80)
print("COMPREHENSIVE DATA ANALYSIS: ethereum_clean.csv")
print("=" * 80)

# Load data
DATA_PATH = r"C:\Users\Administrator\Desktop\datasetAMTTP\ethereum_clean.csv"
print(f"\nLoading data from: {DATA_PATH}")
df = pd.read_csv(DATA_PATH)

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
print(f"{'#':<4} {'Feature Name':<50} {'Data Type':<15} {'Non-Null':<10}")
print("-" * 80)

for i, col in enumerate(df.columns, 1):
    dtype = str(df[col].dtype)
    non_null = df[col].notna().sum()
    null_pct = (df[col].isna().sum() / len(df)) * 100
    null_info = f"{non_null:,}" if null_pct == 0 else f"{non_null:,} ({null_pct:.1f}% null)"
    print(f"{i:<4} {col:<50} {dtype:<15} {null_info:<10}")

# ============================================================================
# SECTION 3: DESCRIPTIVE STATISTICS
# ============================================================================
print("\n" + "=" * 80)
print("3. DESCRIPTIVE STATISTICS (Numeric Features)")
print("=" * 80)

desc_stats = df[numeric_cols].describe().T
desc_stats['missing'] = df[numeric_cols].isna().sum()
desc_stats['missing_%'] = (df[numeric_cols].isna().sum() / len(df)) * 100
desc_stats['unique'] = df[numeric_cols].nunique()

print("\n" + desc_stats[['count', 'mean', 'std', 'min', '25%', '50%', '75%', 'max', 'missing_%']].to_string())

# ============================================================================
# SECTION 4: CATEGORICAL FEATURES ANALYSIS
# ============================================================================
print("\n" + "=" * 80)
print("4. CATEGORICAL FEATURES ANALYSIS")
print("=" * 80)

for col in categorical_cols:
    print(f"\n--- {col} ---")
    print(f"Unique values: {df[col].nunique()}")
    print(f"Top 5 values:")
    print(df[col].value_counts().head(5).to_string())

# ============================================================================
# SECTION 5: TARGET VARIABLE ANALYSIS (label/flag)
# ============================================================================
print("\n" + "=" * 80)
print("5. TARGET VARIABLE ANALYSIS")
print("=" * 80)

for target in ['label', 'label_unified', 'flag']:
    if target in df.columns:
        print(f"\n--- {target} ---")
        print(df[target].value_counts())
        print(f"\nClass Distribution (%):")
        print((df[target].value_counts(normalize=True) * 100).round(2))

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
    print("\nNo missing values in the dataset!")

# ============================================================================
# SECTION 7: STATISTICAL TESTS & ADVANCED ANALYSIS
# ============================================================================
print("\n" + "=" * 80)
print("7. ADVANCED STATISTICAL ANALYSIS")
print("=" * 80)

# Key numeric features for analysis
key_features = [
    'total_ether_sent', 'total_ether_received', 'total_ether_balance',
    'sent_tnx', 'received_tnx', 'avg_val_sent', 'avg_val_received',
    'unique_sent_to_addresses', 'unique_received_from_addresses',
    'time_diff_between_first_and_last_(mins)'
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
            
            # Interpret distribution
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

# Compute correlation matrix for key features
if len(key_features) > 1:
    corr_matrix = df[key_features].corr()
    
    # Get top correlations
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

# Try different label columns
label_col = None
for col in ['flag', 'label', 'label_unified']:
    if col in df.columns and df[col].nunique() <= 10:
        label_col = col
        break

if label_col:
    print(f"\nUsing '{label_col}' as target variable")
    
    # Group by label and compute means
    fraud_comparison = df.groupby(label_col)[key_features].mean()
    print("\nMean Values by Class:")
    print(fraud_comparison.T.to_string())
    
    # Statistical significance test (if binary)
    unique_labels = df[label_col].unique()
    if len(unique_labels) == 2:
        print("\n--- T-Test Results (Feature differences between classes) ---")
        print(f"{'Feature':<45} {'t-statistic':>12} {'p-value':>12} {'Significant':>12}")
        print("-" * 85)
        
        group1 = df[df[label_col] == unique_labels[0]]
        group2 = df[df[label_col] == unique_labels[1]]
        
        for feat in key_features[:10]:  # Limit to first 10
            if df[feat].dtype in [np.float64, np.int64]:
                g1_data = group1[feat].dropna()
                g2_data = group2[feat].dropna()
                if len(g1_data) > 1 and len(g2_data) > 1:
                    t_stat, p_val = stats.ttest_ind(g1_data, g2_data)
                    sig = "Yes***" if p_val < 0.001 else ("Yes**" if p_val < 0.01 else ("Yes*" if p_val < 0.05 else "No"))
                    print(f"{feat:<45} {t_stat:>12.3f} {p_val:>12.6f} {sig:>12}")

# ============================================================================
# SECTION 11: FEATURE IMPORTANCE INDICATORS
# ============================================================================
print("\n" + "=" * 80)
print("11. FEATURE VARIANCE ANALYSIS (Potential Importance)")
print("=" * 80)

# Features with highest variance (normalized by mean) are often important
variance_df = pd.DataFrame({
    'Feature': numeric_cols,
    'Variance': df[numeric_cols].var(),
    'Std': df[numeric_cols].std(),
    'Mean': df[numeric_cols].mean(),
    'CV': df[numeric_cols].std() / df[numeric_cols].mean().replace(0, np.nan)
}).sort_values('CV', ascending=False)

print("\nTop 15 Features by Coefficient of Variation:")
print(variance_df.head(15)[['Feature', 'Mean', 'Std', 'CV']].to_string(index=False))

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("ANALYSIS SUMMARY")
print("=" * 80)

print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                        DATASET ANALYSIS SUMMARY                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ Dataset:          ethereum_clean.csv                                         ║
║ Total Records:    {df.shape[0]:>10,}                                                ║
║ Total Features:   {df.shape[1]:>10}                                                 ║
║   - Numeric:      {len(numeric_cols):>10}                                                 ║
║   - Categorical:  {len(categorical_cols):>10}                                                 ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ Missing Values:   {df.isna().sum().sum():>10,}                                                ║
║ Memory Usage:     {df.memory_usage(deep=True).sum() / 1024**2:>10.2f} MB                                        ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")

print("=" * 80)
print("Analysis Complete!")
print("=" * 80)
