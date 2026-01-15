"""
OPTIMIZED SOPHISTICATED FRAUD DETECTION
=======================================
Ultra-fast version using:
- NumPy vectorized operations (no Python loops)
- Efficient pandas groupby with pre-computed aggregations
- Batch processing with chunked operations
- Numba JIT compilation for hot paths
- Parallel processing where beneficial

Detects: SMURFING, LAYERING, FAN-OUT, FAN-IN, PEELING, STRUCTURING, VELOCITY
"""
import pandas as pd
import numpy as np
from datetime import datetime
import sys
import io
import warnings
warnings.filterwarnings('ignore')

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Try to import numba for JIT compilation
try:
    from numba import jit, prange
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False
    # Create dummy decorator
    def jit(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    prange = range

print("="*70)
print("OPTIMIZED SOPHISTICATED FRAUD DETECTION")
print("="*70)
print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Numba JIT: {'ENABLED' if HAS_NUMBA else 'DISABLED (install numba for 10x speed)'}")

# Configuration
PARQUET_PATH = r"C:\Users\Administrator\Downloads\eth_merged_dataset.parquet"
OUTPUT_DIR = r"c:\amttp\processed"

# =============================================================================
# OPTIMIZED HELPER FUNCTIONS
# =============================================================================

@jit(nopython=True, parallel=True, cache=True)
def compute_decrease_ratios(values_flat, offsets):
    """Numba-optimized decrease ratio computation for peeling detection."""
    n_addresses = len(offsets) - 1
    ratios = np.zeros(n_addresses, dtype=np.float64)
    
    for i in prange(n_addresses):
        start = offsets[i]
        end = offsets[i + 1]
        if end - start < 2:
            ratios[i] = 0.0
            continue
        
        decreasing = 0
        for j in range(start + 1, end):
            if values_flat[j] < values_flat[j - 1]:
                decreasing += 1
        
        ratios[i] = decreasing / (end - start - 1)
    
    return ratios


@jit(nopython=True, cache=True)
def is_round_amount_vectorized(values):
    """Numba-optimized round amount detection."""
    n = len(values)
    result = np.zeros(n, dtype=np.bool_)
    
    round_amounts = np.array([0.1, 0.5, 1.0, 5.0, 10.0, 50.0, 100.0, 500.0, 1000.0,
                              0.99, 0.999, 9.99, 99.99])
    
    for i in range(n):
        v = values[i]
        if v <= 0:
            continue
        # Check if whole number >= 1
        if v >= 1.0 and v == int(v):
            result[i] = True
            continue
        # Check common amounts
        for r in round_amounts:
            if abs(v - r) < 0.0001:
                result[i] = True
                break
    
    return result


def fast_value_counts(series):
    """Optimized value counts using numpy."""
    values, counts = np.unique(series.values, return_counts=True)
    return pd.Series(counts, index=values)


# =============================================================================
# LOAD DATA
# =============================================================================
print("\n[1/8] Loading data...")
start_time = datetime.now()

df = pd.read_parquet(PARQUET_PATH)
df['from_address'] = df['from_address'].str.lower()
df['to_address'] = df['to_address'].str.lower()

# Convert timestamp efficiently
if not pd.api.types.is_datetime64_any_dtype(df['block_timestamp']):
    df['block_timestamp'] = pd.to_datetime(df['block_timestamp'], utc=True)

# Pre-compute value as numpy array for speed
values_np = df['value_eth'].fillna(0).values.astype(np.float64)

print(f"       Loaded {len(df):,} transactions in {(datetime.now()-start_time).total_seconds():.1f}s")

# =============================================================================
# PRE-COMPUTE AGGREGATIONS (Single pass)
# =============================================================================
print("\n[2/8] Pre-computing aggregations...")
start_time = datetime.now()

# Sender aggregations - single groupby
sender_agg = df.groupby('from_address', sort=False).agg(
    tx_count=('value_eth', 'count'),
    total_sent=('value_eth', 'sum'),
    avg_value=('value_eth', 'mean'),
    std_value=('value_eth', 'std'),
    min_value=('value_eth', 'min'),
    max_value=('value_eth', 'max'),
    unique_receivers=('to_address', 'nunique'),
    first_tx=('block_timestamp', 'min'),
    last_tx=('block_timestamp', 'max')
).reset_index()
sender_agg.columns = ['address', 'tx_count', 'total_sent', 'avg_value', 'std_value',
                      'min_value', 'max_value', 'unique_receivers', 'first_tx', 'last_tx']
sender_agg['std_value'] = sender_agg['std_value'].fillna(0)

# Receiver aggregations - single groupby
receiver_agg = df.groupby('to_address', sort=False).agg(
    rx_count=('value_eth', 'count'),
    total_received=('value_eth', 'sum'),
    avg_received=('value_eth', 'mean'),
    unique_senders=('from_address', 'nunique'),
    first_rx=('block_timestamp', 'min'),
    last_rx=('block_timestamp', 'max')
).reset_index()
receiver_agg.columns = ['address', 'rx_count', 'total_received', 'avg_received',
                        'unique_senders', 'first_rx', 'last_rx']

print(f"       Computed aggregations in {(datetime.now()-start_time).total_seconds():.1f}s")
print(f"       Unique senders: {len(sender_agg):,} | Unique receivers: {len(receiver_agg):,}")

# =============================================================================
# 1. SMURFING DETECTION (Vectorized)
# =============================================================================
print("\n[3/8] Detecting SMURFING patterns...")
start_time = datetime.now()

SMURFING_THRESHOLD = 1.0
MIN_SMALL_TX = 5

# Vectorized computation
sender_agg['time_span_hours'] = (
    (sender_agg['last_tx'] - sender_agg['first_tx']).dt.total_seconds() / 3600
).fillna(0)

# Boolean mask for potential smurfers
smurf_mask = (
    (sender_agg['tx_count'] >= MIN_SMALL_TX) &
    (sender_agg['avg_value'] < SMURFING_THRESHOLD) &
    (sender_agg['total_sent'] > 5) &
    (sender_agg['unique_receivers'] >= 3)
)

# Vectorized score computation
sender_agg['smurf_score'] = np.where(
    smurf_mask,
    np.clip(sender_agg['tx_count'] / 10, 0, 1) * 30 +
    np.clip(1 - sender_agg['avg_value'] / SMURFING_THRESHOLD, 0, 1) * 25 +
    np.clip(sender_agg['unique_receivers'] / 10, 0, 1) * 20 +
    np.clip(sender_agg['total_sent'] / 50, 0, 1) * 25,
    0.0
)

smurfers = sender_agg[sender_agg['smurf_score'] > 30].nlargest(1000, 'smurf_score')
print(f"       Found {len(smurfers)} SMURFING addresses in {(datetime.now()-start_time).total_seconds():.1f}s")

# =============================================================================
# 2. FAN-OUT DETECTION (Vectorized)
# =============================================================================
print("\n[4/8] Detecting FAN-OUT patterns...")
start_time = datetime.now()

fan_out_mask = (sender_agg['unique_receivers'] >= 10) & (sender_agg['tx_count'] >= 10)

sender_agg['fan_out_score'] = np.where(
    fan_out_mask,
    np.clip(sender_agg['unique_receivers'] / 20, 0, 1) * 40 +
    np.clip(sender_agg['tx_count'] / 20, 0, 1) * 30 +
    np.clip(sender_agg['total_sent'] / 100, 0, 1) * 30,
    0.0
)

fan_out = sender_agg[sender_agg['fan_out_score'] > 0].nlargest(1000, 'fan_out_score')
print(f"       Found {len(fan_out)} FAN-OUT addresses in {(datetime.now()-start_time).total_seconds():.1f}s")

# =============================================================================
# 3. FAN-IN DETECTION (Vectorized)
# =============================================================================
print("\n[5/8] Detecting FAN-IN patterns...")
start_time = datetime.now()

fan_in_mask = (receiver_agg['unique_senders'] >= 10) & (receiver_agg['rx_count'] >= 10)

receiver_agg['fan_in_score'] = np.where(
    fan_in_mask,
    np.clip(receiver_agg['unique_senders'] / 20, 0, 1) * 40 +
    np.clip(receiver_agg['rx_count'] / 20, 0, 1) * 30 +
    np.clip(receiver_agg['total_received'] / 100, 0, 1) * 30,
    0.0
)

fan_in = receiver_agg[receiver_agg['fan_in_score'] > 0].nlargest(1000, 'fan_in_score')
print(f"       Found {len(fan_in)} FAN-IN addresses in {(datetime.now()-start_time).total_seconds():.1f}s")

# =============================================================================
# 4. PEELING CHAIN DETECTION (Optimized)
# =============================================================================
print("\n[6/8] Detecting PEELING CHAIN patterns...")
start_time = datetime.now()

# Only check addresses with 3+ transactions
candidates = sender_agg[sender_agg['tx_count'] >= 3]['address'].values

# Sort once
df_sorted = df[['from_address', 'value_eth', 'block_timestamp']].sort_values(
    ['from_address', 'block_timestamp']
)

# Group by address and compute decrease ratio
def compute_peeling_scores(group):
    values = group['value_eth'].values
    if len(values) < 3:
        return pd.Series({'decrease_ratio': 0.0, 'first_value': 0.0, 'last_value': 0.0})
    
    # Vectorized decrease counting
    decreases = np.sum(values[1:] < values[:-1])
    ratio = decreases / (len(values) - 1)
    
    return pd.Series({
        'decrease_ratio': ratio,
        'first_value': values[0],
        'last_value': values[-1],
        'tx_count': len(values)
    })

# Apply in chunks for memory efficiency
chunk_size = 100000
peeling_results = []

for i in range(0, len(df_sorted), chunk_size):
    chunk = df_sorted.iloc[i:i+chunk_size]
    result = chunk.groupby('from_address', sort=False).apply(
        compute_peeling_scores, include_groups=False
    ).reset_index()
    peeling_results.append(result)

if peeling_results:
    peeling_df = pd.concat(peeling_results, ignore_index=True)
    peeling_df = peeling_df.groupby('from_address').agg({
        'decrease_ratio': 'mean',
        'first_value': 'first',
        'last_value': 'last',
        'tx_count': 'sum'
    }).reset_index()
    peeling_df.columns = ['address', 'decrease_ratio', 'first_value', 'last_value', 'tx_count']
    
    # Filter and score
    peeling_df = peeling_df[peeling_df['decrease_ratio'] > 0.6]
    peeling_df['peeling_score'] = (
        peeling_df['decrease_ratio'] * 50 +
        np.clip(peeling_df['tx_count'] / 10, 0, 1) * 50
    )
    peeling_df = peeling_df.nlargest(1000, 'peeling_score')
else:
    peeling_df = pd.DataFrame(columns=['address', 'peeling_score'])

print(f"       Found {len(peeling_df)} PEELING addresses in {(datetime.now()-start_time).total_seconds():.1f}s")

# =============================================================================
# 5. LAYERING DETECTION (Optimized with merge)
# =============================================================================
print("\n[7/8] Detecting LAYERING patterns...")
start_time = datetime.now()

# Merge sender and receiver stats
layering_df = sender_agg[['address', 'tx_count', 'total_sent', 'unique_receivers']].merge(
    receiver_agg[['address', 'rx_count', 'total_received', 'unique_senders']],
    on='address',
    how='inner'
)

# Vectorized pass-through ratio
layering_df['pass_ratio'] = np.minimum(
    layering_df['total_sent'] / layering_df['total_received'].replace(0, 1),
    1.0
)

# Filter pass-through addresses
layering_mask = (
    (layering_df['pass_ratio'] > 0.8) &
    (layering_df['rx_count'] >= 2) &
    (layering_df['tx_count'] >= 2)
)

layering_df['layering_score'] = np.where(
    layering_mask,
    layering_df['pass_ratio'] * 40 +
    np.clip(layering_df['rx_count'] / 5, 0, 1) * 30 +
    np.clip(layering_df['tx_count'] / 5, 0, 1) * 30,
    0.0
)

layering = layering_df[layering_df['layering_score'] > 0].nlargest(1000, 'layering_score')
print(f"       Found {len(layering)} LAYERING addresses in {(datetime.now()-start_time).total_seconds():.1f}s")

# =============================================================================
# 6. ROUND AMOUNT STRUCTURING (Vectorized with Numba)
# =============================================================================
print("\n[8/8] Detecting STRUCTURING patterns...")
start_time = datetime.now()

# Use Numba-optimized function if available, else numpy
if HAS_NUMBA:
    is_round = is_round_amount_vectorized(values_np)
else:
    # Pure numpy version
    whole_numbers = (values_np >= 1) & (values_np == np.floor(values_np))
    common_amounts = np.isin(np.round(values_np, 3), 
                             [0.1, 0.5, 1.0, 5.0, 10.0, 50.0, 100.0, 500.0, 1000.0, 0.99, 9.99, 99.99])
    is_round = whole_numbers | common_amounts

df['is_round'] = is_round

# Aggregate round transactions
round_agg = df[df['is_round']].groupby('from_address', sort=False).agg(
    round_tx_count=('value_eth', 'count'),
    round_total=('value_eth', 'sum')
).reset_index()
round_agg.columns = ['address', 'round_tx_count', 'round_total']

# Merge with total tx
round_agg = round_agg.merge(
    sender_agg[['address', 'tx_count']],
    on='address',
    how='left'
)
round_agg['round_ratio'] = round_agg['round_tx_count'] / round_agg['tx_count']

# Filter and score
structuring_mask = (round_agg['round_tx_count'] >= 3) & (round_agg['round_ratio'] > 0.5)
round_agg['structuring_score'] = np.where(
    structuring_mask,
    round_agg['round_ratio'] * 40 +
    np.clip(round_agg['round_tx_count'] / 10, 0, 1) * 30 +
    np.clip(round_agg['round_total'] / 50, 0, 1) * 30,
    0.0
)

structuring = round_agg[round_agg['structuring_score'] > 0].nlargest(1000, 'structuring_score')
print(f"       Found {len(structuring)} STRUCTURING addresses in {(datetime.now()-start_time).total_seconds():.1f}s")

# =============================================================================
# VELOCITY DETECTION (Efficient hourly aggregation)
# =============================================================================
print("\n       Detecting VELOCITY anomalies...")
start_time = datetime.now()

# Hourly aggregation
df['hour'] = df['block_timestamp'].dt.floor('H')
hourly = df.groupby(['from_address', 'hour'], sort=False).size().reset_index(name='tx_count')

# Compute velocity stats
velocity_stats = hourly.groupby('from_address', sort=False).agg(
    avg_tx_hour=('tx_count', 'mean'),
    max_tx_hour=('tx_count', 'max')
).reset_index()

velocity_stats['velocity_ratio'] = velocity_stats['max_tx_hour'] / velocity_stats['avg_tx_hour'].replace(0, 1)

velocity_mask = (velocity_stats['max_tx_hour'] >= 5) & (velocity_stats['velocity_ratio'] > 3)
velocity_stats['velocity_score'] = np.where(
    velocity_mask,
    np.clip(velocity_stats['velocity_ratio'] / 10, 0, 1) * 50 +
    np.clip(velocity_stats['max_tx_hour'] / 20, 0, 1) * 50,
    0.0
)

velocity = velocity_stats[velocity_stats['velocity_score'] > 0].nlargest(1000, 'velocity_score')
print(f"       Found {len(velocity)} VELOCITY anomalies in {(datetime.now()-start_time).total_seconds():.1f}s")

# =============================================================================
# COMBINE ALL SCORES (Vectorized merge)
# =============================================================================
print("\n" + "="*70)
print("COMBINING SCORES...")
start_time = datetime.now()

# Create base dataframe with all addresses
all_addresses = pd.DataFrame({
    'address': pd.concat([
        sender_agg['address'],
        receiver_agg['address']
    ]).drop_duplicates()
})

# Merge all scores efficiently
score_columns = [
    (smurfers[['address', 'smurf_score']], 'smurf_score'),
    (fan_out[['address', 'fan_out_score']], 'fan_out_score'),
    (fan_in[['address', 'fan_in_score']], 'fan_in_score'),
    (peeling_df[['address', 'peeling_score']] if len(peeling_df) > 0 else None, 'peeling_score'),
    (layering[['address', 'layering_score']], 'layering_score'),
    (structuring[['address', 'structuring_score']], 'structuring_score'),
    (velocity[['address', 'velocity_score']], 'velocity_score'),
]

combined = all_addresses.copy()
for score_df, col_name in score_columns:
    if score_df is not None and len(score_df) > 0:
        combined = combined.merge(score_df, on='address', how='left')
    else:
        combined[col_name] = 0.0

# Fill NaN and compute total
score_cols = ['smurf_score', 'fan_out_score', 'fan_in_score', 'peeling_score', 
              'layering_score', 'structuring_score', 'velocity_score']
combined[score_cols] = combined[score_cols].fillna(0)

combined['sophisticated_score'] = combined[score_cols].sum(axis=1)

# Build pattern string vectorized
pattern_names = ['SMURFING', 'FAN_OUT', 'FAN_IN', 'PEELING', 'LAYERING', 'STRUCTURING', 'VELOCITY']
def build_patterns(row):
    patterns = []
    for col, name in zip(score_cols, pattern_names):
        if row[col] > 0:
            patterns.append(name)
    return ', '.join(patterns)

# Filter to only addresses with patterns
combined = combined[combined['sophisticated_score'] > 0]
combined['patterns'] = combined.apply(build_patterns, axis=1)
combined['pattern_count'] = (combined[score_cols] > 0).sum(axis=1)

# Sort by score
combined = combined.sort_values('sophisticated_score', ascending=False)

print(f"       Combined {len(combined):,} addresses with patterns in {(datetime.now()-start_time).total_seconds():.1f}s")

# =============================================================================
# SAVE RESULTS
# =============================================================================
output_cols = ['address', 'sophisticated_score', 'patterns', 'pattern_count'] + score_cols
combined[output_cols].to_csv(f"{OUTPUT_DIR}/sophisticated_fraud_patterns.csv", index=False)

# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "="*70)
print("RESULTS SUMMARY")
print("="*70)

print(f"\nTotal addresses with patterns: {len(combined):,}")
print(f"Multi-pattern addresses: {len(combined[combined['pattern_count'] > 1]):,}")

print("\nPattern Distribution:")
for col, name in zip(score_cols, pattern_names):
    count = (combined[col] > 0).sum()
    print(f"   {name}: {count:,}")

print(f"\nTOP 20 SOPHISTICATED FRAUD SUSPECTS:")
print("-" * 70)
for i, row in combined.head(20).iterrows():
    print(f"  {row['address']}")
    print(f"    Score: {row['sophisticated_score']:.1f} | Patterns: {row['patterns']}")

print(f"\nResults saved to: {OUTPUT_DIR}/sophisticated_fraud_patterns.csv")
print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
