"""Analyze the teacher scoring columns in the labeled dataset."""
import json, os
import pandas as pd
import numpy as np

# Teacher XGB model info
model_path = r'c:\amttp\ml\Automation\ml_pipeline\models\trained\xgb.json'
print(f'Teacher XGB exists: {os.path.exists(model_path)}, size: {os.path.getsize(model_path)/(1024*1024):.1f} MB')

schema_path = r'c:\amttp\ml\Automation\ml_pipeline\models\feature_schema.json'
with open(schema_path) as f:
    schema = json.load(f)
feat_names = schema['feature_names']
print(f'Teacher feature schema: {len(feat_names)} features')
print(f'First 20: {feat_names[:20]}')

# Load labeled dataset teacher scoring columns
df = pd.read_parquet(r'c:\amttp\processed\eth_addresses_labeled.parquet', columns=[
    'xgb_raw_score','xgb_normalized','pattern_boost','soph_normalized','hybrid_score',
    'fraud','risk_level','risk_class','sophisticated_score','pattern_count'
])
print(f'\nLabeled dataset shape: {df.shape}')
print(f'Fraud distribution: {df["fraud"].value_counts().to_dict()}')
print(f'Risk level distribution:')
for rl in ['CRITICAL','HIGH','MEDIUM','LOW','MINIMAL']:
    cnt = (df['risk_level']==rl).sum()
    if cnt > 0:
        print(f'  {rl}: {cnt}')

# Teacher scoring columns for fraud=1 addresses
fraud = df[df['fraud']==1]
print(f'\nFraud addresses (n={len(fraud)}):')
for col in ['xgb_raw_score','xgb_normalized','pattern_boost','soph_normalized','hybrid_score']:
    print(f'  {col}: mean={fraud[col].mean():.4f}, min={fraud[col].min():.4f}, max={fraud[col].max():.4f}')

# Non-fraud
clean = df[df['fraud']==0]
print(f'\nClean addresses (n={len(clean)}):')
for col in ['xgb_raw_score','xgb_normalized','pattern_boost','soph_normalized','hybrid_score']:
    print(f'  {col}: mean={clean[col].mean():.6f}, min={clean[col].min():.6f}, max={clean[col].max():.6f}')

# Threshold analysis
print(f'\nMin hybrid_score for fraud=1: {fraud["hybrid_score"].min():.4f}')
print(f'Max hybrid_score for fraud=0: {clean["hybrid_score"].max():.4f}')

# Can we use hybrid_score as teacher probability?
# Normalize to 0-1 range
hs = df['hybrid_score'].values
hs_norm = hs / 100.0  # hybrid_score is 0-100 scale
print(f'\nhybrid_score / 100 as teacher prob:')
print(f'  fraud mean: {hs_norm[df["fraud"]==1].mean():.4f}')
print(f'  clean mean: {hs_norm[df["fraud"]==0].mean():.4f}')

# XGB raw score as teacher XGB component prob
xgb_raw = df['xgb_raw_score'].values
print(f'\nxgb_raw_score as teacher XGB prob:')
print(f'  fraud: mean={xgb_raw[df["fraud"]==1].mean():.6f}, max={xgb_raw[df["fraud"]==1].max():.6f}')
print(f'  clean: mean={xgb_raw[df["fraud"]==0].mean():.6f}, max={xgb_raw[df["fraud"]==0].max():.6f}')
print(f'  non-zero count: {(xgb_raw > 0).sum()}')

# Check if hybrid_score perfectly separates fraud from non-fraud
# (since fraud IS derived from hybrid_score via risk_level)
overlap = (clean['hybrid_score'] >= fraud['hybrid_score'].min()).sum()
print(f'\nClean addresses with hybrid_score >= min fraud hybrid_score: {overlap}')

# What does the teacher XGB alone predict on fraud addresses?
from sklearn.metrics import roc_auc_score
try:
    auc_xgb = roc_auc_score(df['fraud'], df['xgb_raw_score'])
    print(f'\nTeacher XGB raw_score ROC-AUC: {auc_xgb:.4f}')
except:
    print('Cannot compute ROC-AUC for teacher XGB raw_score')

try:
    auc_hybrid = roc_auc_score(df['fraud'], df['hybrid_score'])
    print(f'Teacher hybrid_score ROC-AUC: {auc_hybrid:.4f}')
except:
    print('Cannot compute ROC-AUC for teacher hybrid_score')
