import pathlib
import sys

root = pathlib.Path(r"C:\\amttp")
needle = "erc20_total_ether_received"
parquets = list(root.rglob("*.parquet"))
print(f"Scanning {len(parquets)} parquet files for column '{needle}'")

matches = []
for path in parquets:
    try:
        import pyarrow.parquet as pq
        schema = pq.read_schema(path)
        names = set(schema.names)
    except Exception:
        try:
            import pandas as pd
            df = pd.read_parquet(path, columns=[needle])
            names = set(df.columns)
        except Exception:
            continue
    if needle in names:
        matches.append(str(path))

print("Matches:")
for m in matches:
    print(m)
