from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'research' / 'adaptive-friction' / 'pipeline' / 'results'))

try:
    from run_crypto_pairs_v34_full_combined import build_1h_df
except Exception as e:
    print('ERROR importing build_1h_df:', e)
    raise

out_dir = Path(r"C:\amttp\data")
out_dir.mkdir(parents=True, exist_ok=True)

print('Fetching 1h OHLCV (2021-01-01 -> 2026-06-01')
df, has_sol = build_1h_df(start='2021-01-01', end='2026-06-01')
out_path = out_dir / 'godmode_1h_2021_2026.csv'
df.to_csv(out_path)
print('Saved:', out_path)
