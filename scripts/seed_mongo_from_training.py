"""
Seed MongoDB with ETH training data for the War Room dashboard.

Reads processed/eth_transactions_labeled_balanced.csv and inserts:
  - transactions collection: all transactions
  - flagged_transactions collection: fraud==1 transactions
  - profiles collection: per-address risk profiles
  - dashboard_stats: aggregate stats
"""

import sys, os, time
import pandas as pd
from pymongo import MongoClient, UpdateOne
from datetime import datetime

MONGO_URI = os.environ.get("MONGODB_URL", "mongodb://localhost:27017")
DB_NAME = "amttp"
CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "processed", "eth_transactions_labeled_balanced.csv")

def main():
    t0 = time.time()
    print(f"[1/5] Connecting to MongoDB at {MONGO_URI} ...")
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client[DB_NAME]

    print(f"[2/5] Reading {CSV_PATH} ...")
    df = pd.read_csv(CSV_PATH)
    print(f"       {len(df)} rows, {len(df.columns)} columns")

    # ── Transactions ──────────────────────────────────────────────
    print("[3/5] Inserting transactions ...")
    db.transactions.drop()

    # Build documents
    tx_docs = []
    for _, row in df.iterrows():
        doc = {
            "hash": row["tx_hash"],
            "blockNumber": int(row["block_number"]),
            "timestamp": row["block_timestamp"],
            "from": row["from_address"],
            "to": row["to_address"],
            "valueEth": float(row["value_eth"]),
            "gasPriceGwei": float(row["gas_price_gwei"]),
            "gasUsed": int(row["gas_used"]),
            "fraud": int(row["fraud"]),
            "senderFraud": int(row["sender_fraud"]),
            "receiverFraud": int(row["receiver_fraud"]),
        }
        tx_docs.append(doc)

    # Batch insert in chunks of 5000
    BATCH = 5000
    for i in range(0, len(tx_docs), BATCH):
        chunk = tx_docs[i:i+BATCH]
        db.transactions.insert_many(chunk, ordered=False)
        print(f"       ... inserted {min(i+BATCH, len(tx_docs))}/{len(tx_docs)}")

    db.transactions.create_index("hash", unique=True)
    db.transactions.create_index("from")
    db.transactions.create_index("to")
    db.transactions.create_index("fraud")
    print(f"       {db.transactions.count_documents({})} transactions inserted")

    # ── Flagged Transactions ──────────────────────────────────────
    print("[4/5] Building flagged_transactions ...")
    db.flagged_transactions.drop()

    fraud_df = df[df["fraud"] == 1].copy()
    print(f"       {len(fraud_df)} fraudulent transactions")

    reasons = [
        "Suspected mixer interaction",
        "Unusual volume spike",
        "Rapid fan-out pattern",
        "Sanctioned address proximity",
        "Layering behavior detected",
        "Velocity anomaly",
        "Dormant wallet reactivation",
        "High-risk jurisdiction transfer",
        "Structuring pattern",
        "Cross-chain bridge abuse",
    ]
    flag_tags = [
        ["Mixer", "Rapid cycling"],
        ["Volume anomaly", "New counterparty"],
        ["Fan-out", "Structuring"],
        ["OFAC proximity", "Sanctions risk"],
        ["Layering", "Multiple hops"],
        ["Velocity spike", "Burst pattern"],
        ["Dormant reactivation", "Sudden activity"],
        ["Geo-risk", "High-risk jurisdiction"],
        ["Structuring", "Sub-threshold"],
        ["Cross-chain", "Bridge exploit"],
    ]
    statuses = ["pending", "reviewing", "escalated", "under_review", "pending"]

    flagged_docs = []
    for idx, (_, row) in enumerate(fraud_df.iterrows()):
        risk_score = min(99, 60 + (float(row["value_eth"]) * 2) % 39)
        risk_level = "CRITICAL" if risk_score > 85 else "HIGH" if risk_score > 70 else "MEDIUM"
        flagged_docs.append({
            "id": f"flag-{idx+1:04d}",
            "hash": row["tx_hash"],
            "address": row["to_address"],
            "from": row["from_address"],
            "to": row["to_address"],
            "value": float(row["value_eth"]),
            "riskScore": round(risk_score, 1),
            "riskLevel": risk_level,
            "reason": reasons[idx % len(reasons)],
            "flags": flag_tags[idx % len(flag_tags)],
            "timestamp": row["block_timestamp"],
            "status": statuses[idx % len(statuses)],
            "blockNumber": int(row["block_number"]),
        })

    if flagged_docs:
        db.flagged_transactions.insert_many(flagged_docs, ordered=False)
    db.flagged_transactions.create_index("id", unique=True)
    db.flagged_transactions.create_index("riskLevel")
    db.flagged_transactions.create_index("status")
    print(f"       {db.flagged_transactions.count_documents({})} flagged transactions inserted")

    # ── Profiles (per unique address) ─────────────────────────────
    print("[5/5] Building address profiles ...")
    db.wallet_profiles.drop()

    # Aggregate: per sender
    addr_stats = {}
    for _, row in df.iterrows():
        for addr_col, fraud_col in [("from_address", "sender_fraud"), ("to_address", "receiver_fraud")]:
            addr = row[addr_col]
            if addr not in addr_stats:
                addr_stats[addr] = {"txCount": 0, "totalValue": 0.0, "fraudCount": 0}
            addr_stats[addr]["txCount"] += 1
            addr_stats[addr]["totalValue"] += float(row["value_eth"])
            addr_stats[addr]["fraudCount"] += int(row[fraud_col])

    profile_docs = []
    for addr, st in addr_stats.items():
        risk = min(99, (st["fraudCount"] / max(st["txCount"], 1)) * 100)
        risk_level = "CRITICAL" if risk > 80 else "HIGH" if risk > 50 else "MEDIUM" if risk > 20 else "LOW"
        profile_docs.append({
            "address": addr,
            "transactionCount": st["txCount"],
            "totalValueEth": round(st["totalValue"], 6),
            "fraudCount": st["fraudCount"],
            "riskScore": round(risk, 1),
            "riskLevel": risk_level,
            "firstSeen": datetime.utcnow().isoformat(),
            "lastSeen": datetime.utcnow().isoformat(),
        })

    for i in range(0, len(profile_docs), BATCH):
        chunk = profile_docs[i:i+BATCH]
        db.wallet_profiles.insert_many(chunk, ordered=False)

    db.wallet_profiles.create_index("address", unique=True)
    db.wallet_profiles.create_index("riskLevel")
    print(f"       {db.wallet_profiles.count_documents({})} address profiles inserted")

    # ── Summary ───────────────────────────────────────────────────
    total_tx = db.transactions.count_documents({})
    total_flagged = db.flagged_transactions.count_documents({})
    total_profiles = db.wallet_profiles.count_documents({})
    elapsed = time.time() - t0

    print(f"\n{'='*50}")
    print(f"  Seed complete in {elapsed:.1f}s")
    print(f"  Transactions:  {total_tx:,}")
    print(f"  Flagged:       {total_flagged:,}")
    print(f"  Profiles:      {total_profiles:,}")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
