#!/usr/bin/env python3
"""
Minimal automation runner to validate Memgraph enrichment path from ml/Automation.
Generates a tiny synthetic DF, normalizes addresses, queries Memgraph via proxy or bolt,
then prints a small sample of enriched features.

Usage:
  python runner.py --proxy-url https://<your-public-url> [--api-key <token>]
  python runner.py --host memgraph --port 7687

You can set PYTHONPATH to ml/Automation to resolve 'src' package:
  $env:PYTHONPATH = "C:\\amttp\\ml\\Automation"  # PowerShell
"""
import argparse
import os
from typing import List

try:
    import polars as pl
    USING_POLARS = True
except Exception:
    import pandas as pl  # type: ignore
    USING_POLARS = False

from src.memgraph_enrich import MemgraphEnricher


def make_df(n: int = 20):
    senders = [f"0xA{i:04X}" for i in range(n)]
    receivers = [f"0xB{i:04X}" for i in range(n)]
    if USING_POLARS:
        df = pl.DataFrame({"from": senders, "to": receivers})
        df = df.with_columns([
            pl.col("from").str.to_lowercase().alias("from_norm"),
            pl.col("to").str.to_lowercase().alias("to_norm"),
        ])
    else:
        df = pl.DataFrame({"from": senders, "to": receivers})
        df["from_norm"] = df["from"].str.lower()
        df["to_norm"] = df["to"].str.lower()
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proxy-url", type=str, default=os.getenv("MEMGRAPH_PROXY_URL"))
    ap.add_argument("--api-key", type=str, default=os.getenv("MEMGRAPH_API_KEY"))
    ap.add_argument("--host", type=str, default=os.getenv("MEMGRAPH_HOST"))
    ap.add_argument("--port", type=int, default=int(os.getenv("MEMGRAPH_PORT", "7687")))
    args = ap.parse_args()

    if not args.proxy_url and not args.host:
        print("No proxy-url or host provided; defaulting to bolt memgraph:7687")
        args.host = "memgraph"
        args.port = 7687

    enricher = MemgraphEnricher(
        host=args.host,
        port=args.port,
        proxy_url=args.proxy_url,
        api_key=args.api_key,
    )

    df = make_df(25)

    # Build batch of addresses
    if USING_POLARS:
        addrs: List[str] = pl.concat([
            df.select(pl.col("from_norm")),
            df.select(pl.col("to_norm")),
        ]).unique().to_series().to_list()
    else:
        addrs = list(set(df["from_norm"].astype(str).tolist() + df["to_norm"].astype(str).tolist()))

    feats = enricher.query_batch_addresses(addrs)
    print("Sample enrichment:")
    for k, v in list(feats.items())[:5]:
        print(k, v)


if __name__ == "__main__":
    main()
