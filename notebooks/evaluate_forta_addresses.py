#!/usr/bin/env python3
"""
Forta Labeled Addresses → Etherscan TX Fetch → V2 Model Evaluation
===================================================================
Downloads transaction data for Forta ground-truth addresses from Etherscan,
computes V2 features, and evaluates the student + teacher models.

Dataset: 7,891 unique malicious ETH addresses from:
  - Etherscan banned labels (exploit, heist, phish-hack)
  - Forta phishing scams
  - Malicious smart contract deployers
"""
import os, sys, time, json, asyncio, random
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

# ── Config ──
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "YNX9YKZ4CJ1EV678NR3KGZU2P6353YT7B8")
ETHERSCAN_BASE = "https://api.etherscan.io/v2/api"
RATE_LIMIT = 4.0  # calls/sec (below 5 free tier limit)
MAX_ADDRESSES = 300  # Sample size (at 4 req/s = ~75s + network overhead)
FORTA_DIR = Path(r'c:\amttp\data\external_validation\forta')
MODELS_DIR = Path(r'C:\Users\Administrator\Downloads\amttp_student_artifacts\amttp_models_20260213_213346')
CACHE_FILE = FORTA_DIR / 'forta_etherscan_txs.parquet'

import xgboost as xgb
import lightgbm as lgb
import joblib
from sklearn.metrics import (
    roc_auc_score, average_precision_score, f1_score,
    precision_score, recall_score, confusion_matrix, precision_recall_curve
)

# Load V2 models
xgb_model = xgb.XGBClassifier()
xgb_model.load_model(str(MODELS_DIR / 'xgboost_fraud.ubj'))
lgb_model = lgb.Booster(model_file=str(MODELS_DIR / 'lightgbm_fraud.txt'))
meta_model = joblib.load(str(MODELS_DIR / 'meta_ensemble.joblib'))
preprocessors = joblib.load(str(MODELS_DIR / 'preprocessors.joblib'))

with open(MODELS_DIR / 'metadata.json') as f:
    metadata = json.load(f)
with open(MODELS_DIR / 'feature_config.json') as f:
    feature_config = json.load(f)

RAW_FEATURES = feature_config['raw_features']
BOOST_FEATURES = feature_config['boost_features']
META_FEATURES = feature_config['meta_features']
OPTIMAL_THRESHOLD = metadata['optimal_threshold']

# Load teacher
TEACHER_PATH = Path(r'c:\amttp\ml\Automation\ml_pipeline\models\trained\xgb.json')
teacher_xgb = xgb.Booster()
teacher_xgb.load_model(str(TEACHER_PATH))
TEACHER_FEATURES = teacher_xgb.feature_names

print(f'✅ Models loaded (Student: {len(RAW_FEATURES)} raw → {len(BOOST_FEATURES)} boost, Teacher: {len(TEACHER_FEATURES)} features)')


# ── Load Forta addresses ──
def load_forta_addresses():
    """Load all Forta labeled addresses with their categories."""
    addrs = {}
    
    # Etherscan banned
    df = pd.read_csv(FORTA_DIR / '1_etherscan_malicious_labels.csv')
    for _, row in df.iterrows():
        addr = row['banned_address'].lower()
        addrs[addr] = {'category': 'banned', 'tag': row.get('wallet_tag', ''), 'source': 'etherscan'}
    
    # Phishing
    df = pd.read_csv(FORTA_DIR / '1_phishing_scams.csv')
    for _, row in df.iterrows():
        addr = row['address'].lower()
        if addr not in addrs:
            addrs[addr] = {'category': 'phishing', 'tag': row.get('etherscan_tag', ''), 'source': 'forta_phishing'}
    
    # Malicious SC creators
    df = pd.read_csv(FORTA_DIR / '1_malicious_smart_contracts.csv')
    for _, row in df.iterrows():
        creator = str(row.get('contract_creator', '')).lower()
        if creator.startswith('0x') and creator not in addrs:
            addrs[creator] = {'category': 'exploit', 'tag': row.get('contract_creator_tag', ''), 'source': 'forta_malicious_sc'}
    
    return addrs

forta_addrs = load_forta_addresses()
print(f'📋 Forta addresses: {len(forta_addrs):,}')
cats = {}
for v in forta_addrs.values():
    cats[v['category']] = cats.get(v['category'], 0) + 1
for c, n in sorted(cats.items()):
    print(f'   {c}: {n:,}')


# ── Etherscan Fetcher (sync, with rate limiting) ──
import requests

session = requests.Session()
session.headers.update({'User-Agent': 'AMTTP-Validator/1.0'})

def fetch_tx_list(address, max_txs=200, retries=3):
    """Fetch recent transactions for an address from Etherscan with retry."""
    params = {
        'chainid': 1,
        'module': 'account',
        'action': 'txlist',
        'address': address,
        'startblock': 0,
        'endblock': 99999999,
        'page': 1,
        'offset': min(max_txs, 200),
        'sort': 'desc',
        'apikey': ETHERSCAN_API_KEY,
    }
    for attempt in range(retries):
        try:
            r = session.get(ETHERSCAN_BASE, params=params, timeout=15)
            data = r.json()
            if data.get('status') == '1':
                return data.get('result', [])
            if 'Max rate limit reached' in str(data.get('result', '')):
                time.sleep(2)  # Back off on rate limit
                continue
            return []
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            return []
        except Exception:
            return []
    return []


def compute_address_features(address, txs):
    """
    Compute V2-compatible features from raw Etherscan transactions.
    Returns a dict mapping feature names to values.
    """
    if not txs:
        return {}
    
    features = {}
    addr_lower = address.lower()
    
    # Separate sent vs received
    sent = [tx for tx in txs if tx.get('from', '').lower() == addr_lower]
    received = [tx for tx in txs if tx.get('to', '').lower() == addr_lower]
    
    def safe_val(tx):
        try:
            return int(tx.get('value', 0)) / 1e18
        except:
            return 0.0
    
    def safe_gas_price(tx):
        try:
            return int(tx.get('gasPrice', 0)) / 1e9
        except:
            return 0.0
    
    def safe_gas_used(tx):
        try:
            return int(tx.get('gasUsed', 0))
        except:
            return 0
    
    sent_vals = [safe_val(tx) for tx in sent]
    recv_vals = [safe_val(tx) for tx in received]
    
    # TX-level features (use most recent tx)
    if txs:
        latest = txs[0]
        features['value_eth'] = safe_val(latest)
        features['gas_price_gwei'] = safe_gas_price(latest)
        features['gas_used'] = safe_gas_used(latest)
        features['gas_limit'] = int(latest.get('gas', 0))
        features['transaction_type'] = 0
        features['nonce'] = int(latest.get('nonce', 0))
        features['transaction_index'] = int(latest.get('transactionIndex', 0))
    
    # Sender aggregate features
    features['sender_sent_count'] = len(sent)
    features['sender_total_sent'] = sum(sent_vals) if sent_vals else 0
    features['sender_avg_sent'] = np.mean(sent_vals) if sent_vals else 0
    features['sender_max_sent'] = max(sent_vals) if sent_vals else 0
    features['sender_min_sent'] = min(sent_vals) if sent_vals else 0
    features['sender_std_sent'] = np.std(sent_vals) if len(sent_vals) > 1 else 0
    
    sent_gas = [safe_gas_used(tx) * safe_gas_price(tx) * 1e-9 for tx in sent]  # in ETH
    features['sender_total_gas_sent'] = sum(sent_gas)
    features['sender_avg_gas_used'] = np.mean([safe_gas_used(tx) for tx in sent]) if sent else 0
    features['sender_avg_gas_price'] = np.mean([safe_gas_price(tx) for tx in sent]) if sent else 0
    
    sent_receivers = set(tx.get('to', '').lower() for tx in sent if tx.get('to'))
    features['sender_unique_receivers'] = len(sent_receivers)
    
    # Sender's received stats  
    features['sender_received_count'] = len(received)
    features['sender_total_received'] = sum(recv_vals) if recv_vals else 0
    features['sender_avg_received'] = np.mean(recv_vals) if recv_vals else 0
    features['sender_max_received'] = max(recv_vals) if recv_vals else 0
    features['sender_min_received'] = min(recv_vals) if recv_vals else 0
    features['sender_std_received'] = np.std(recv_vals) if len(recv_vals) > 1 else 0
    
    recv_senders = set(tx.get('from', '').lower() for tx in received)
    features['sender_unique_senders'] = len(recv_senders)
    
    features['sender_total_transactions'] = len(txs)
    features['sender_balance'] = sum(recv_vals) - sum(sent_vals)
    
    in_count = len(received)
    out_count = len(sent)
    features['sender_in_out_ratio'] = in_count / max(out_count, 1)
    features['sender_unique_counterparties'] = len(sent_receivers | recv_senders)
    features['sender_avg_value'] = np.mean(sent_vals + recv_vals) if (sent_vals + recv_vals) else 0
    features['sender_neighbors'] = len(sent_receivers | recv_senders)
    features['sender_count'] = len(sent)
    features['sender_income'] = sum(recv_vals)
    
    # Time features
    timestamps = sorted([int(tx.get('timeStamp', 0)) for tx in txs])
    if len(timestamps) > 1:
        features['sender_active_duration_mins'] = (timestamps[-1] - timestamps[0]) / 60
    else:
        features['sender_active_duration_mins'] = 0
    
    # Degree features
    features['sender_in_degree'] = len(recv_senders)
    features['sender_out_degree'] = len(sent_receivers)
    features['sender_degree'] = len(sent_receivers | recv_senders)
    features['sender_degree_centrality'] = len(sent_receivers | recv_senders) / max(len(txs), 1)
    features['sender_betweenness_proxy'] = 0  # Can't compute without graph
    
    # Receiver features (mirror — treat as if evaluating the LATEST tx's receiver)
    # For malicious address evaluation, the address IS the sender, so receiver features
    # represent the counterparty. We'll leave most as 0 or copy structure from sent side.
    features['receiver_sent_count'] = 0
    features['receiver_total_sent'] = 0
    features['receiver_avg_sent'] = 0
    features['receiver_max_sent'] = 0
    features['receiver_min_sent'] = 0
    features['receiver_std_sent'] = 0
    features['receiver_total_gas_sent'] = 0
    features['receiver_avg_gas_used'] = 0
    features['receiver_avg_gas_price'] = 0
    features['receiver_unique_receivers'] = 0
    features['receiver_received_count'] = 0
    features['receiver_total_received'] = 0
    features['receiver_avg_received'] = 0
    features['receiver_max_received'] = 0
    features['receiver_min_received'] = 0
    features['receiver_std_received'] = 0
    features['receiver_unique_senders'] = 0
    features['receiver_total_transactions'] = 0
    features['receiver_balance'] = 0
    features['receiver_in_out_ratio'] = 0
    features['receiver_unique_counterparties'] = 0
    features['receiver_avg_value'] = 0
    features['receiver_neighbors'] = 0
    features['receiver_count'] = 0
    features['receiver_income'] = 0
    features['receiver_active_duration_mins'] = 0
    features['receiver_in_degree'] = 0
    features['receiver_out_degree'] = 0
    features['receiver_degree'] = 0
    features['receiver_degree_centrality'] = 0
    features['receiver_betweenness_proxy'] = 0
    
    # Mixer/sanctioned/exchange flags — 0 by default
    # (Could be enriched by checking against known lists)
    
    return features


def compute_teacher_features(address, txs):
    """Compute teacher-compatible features from Etherscan tx data."""
    if not txs:
        return {}
    
    addr_lower = address.lower()
    sent = [tx for tx in txs if tx.get('from', '').lower() == addr_lower]
    received = [tx for tx in txs if tx.get('to', '').lower() == addr_lower]
    
    def safe_val(tx):
        try: return int(tx.get('value', 0)) / 1e18
        except: return 0.0
    
    sent_vals = [safe_val(tx) for tx in sent]
    recv_vals = [safe_val(tx) for tx in received]
    
    timestamps = sorted([int(tx.get('timeStamp', 0)) for tx in txs])
    time_diff = (timestamps[-1] - timestamps[0]) / 60 if len(timestamps) > 1 else 0
    
    sent_receivers = set(tx.get('to', '').lower() for tx in sent if tx.get('to'))
    recv_senders = set(tx.get('from', '').lower() for tx in received)
    
    avg_min_sent, avg_min_recv = 0, 0
    sent_ts = sorted([int(tx.get('timeStamp', 0)) for tx in sent])
    recv_ts = sorted([int(tx.get('timeStamp', 0)) for tx in received])
    if len(sent_ts) > 1:
        diffs = [(sent_ts[i+1] - sent_ts[i])/60 for i in range(len(sent_ts)-1)]
        avg_min_sent = np.mean(diffs)
    if len(recv_ts) > 1:
        diffs = [(recv_ts[i+1] - recv_ts[i])/60 for i in range(len(recv_ts)-1)]
        avg_min_recv = np.mean(diffs)
    
    return {
        'sent_tnx': len(sent),
        'received_tnx': len(received),
        'total_ether_sent': sum(sent_vals),
        'total_ether_received': sum(recv_vals),
        'avg_val_sent': np.mean(sent_vals) if sent_vals else 0,
        'avg_val_received': np.mean(recv_vals) if recv_vals else 0,
        'max_val_sent': max(sent_vals) if sent_vals else 0,
        'max_value_received': max(recv_vals) if recv_vals else 0,
        'min_val_sent': min(sent_vals) if sent_vals else 0,
        'min_value_received': min(recv_vals) if recv_vals else 0,
        'total_ether_balance': sum(recv_vals) - sum(sent_vals),
        'unique_sent_to_addresses': len(sent_receivers),
        'unique_received_from_addresses': len(recv_senders),
        'neighbors': len(sent_receivers | recv_senders),
        'income': sum(recv_vals),
        'time_diff_between_first_and_last_(mins)': time_diff,
        'avg_min_between_sent_tnx': avg_min_sent,
        'avg_min_between_received_tnx': avg_min_recv,
        'count': len(txs),
        'total_transactions_(including_tnx_to_create_contract': len(txs),
        'number_of_created_contracts': sum(1 for tx in sent if not tx.get('to')),
    }


# ── V2 Preprocessing & Prediction ──
def preprocess_raw(X_raw):
    X = X_raw.copy().astype(np.float64)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    
    imputer = preprocessors.get('imputer', None)
    if imputer is not None:
        X = imputer.transform(X)
    
    log_mask = preprocessors.get('log_transform_mask', None)
    if log_mask is not None:
        log_mask = np.array(log_mask)
        X[:, log_mask] = np.log1p(np.clip(X[:, log_mask], 0, None))
    
    scaler = preprocessors.get('robust_scaler', None)
    if scaler is not None:
        X = scaler.transform(X)
    
    clip_range = preprocessors.get('clip_range', 5)
    X = np.clip(X, -clip_range, clip_range)
    return X.astype(np.float32)


def predict_student(feature_dicts):
    """Predict with V2 student model on a list of feature dicts."""
    n = len(feature_dicts)
    X_raw = np.zeros((n, len(RAW_FEATURES)), dtype=np.float32)
    for i, fd in enumerate(feature_dicts):
        for j, fname in enumerate(RAW_FEATURES):
            X_raw[i, j] = float(fd.get(fname, 0))
    
    X_preprocessed = preprocess_raw(X_raw)
    X_boost = np.zeros((n, len(BOOST_FEATURES)), dtype=np.float32)
    X_boost[:, :len(RAW_FEATURES)] = X_preprocessed
    
    try:
        xgb_prob = xgb_model.predict_proba(X_boost)[:, 1]
    except:
        dmat = xgb.DMatrix(X_boost)
        xgb_prob = xgb_model.predict(dmat)
    
    lgb_prob = lgb_model.predict(X_boost)
    if lgb_prob.max() > 1.0 or lgb_prob.min() < 0.0:
        from scipy.special import expit
        lgb_prob = expit(lgb_prob)
    
    return xgb_prob, lgb_prob


def predict_teacher_model(feature_dicts):
    """Predict with teacher model on a list of feature dicts."""
    n = len(feature_dicts)
    X = np.zeros((n, len(TEACHER_FEATURES)), dtype=np.float32)
    
    for i, fd in enumerate(feature_dicts):
        for j, fname in enumerate(TEACHER_FEATURES):
            if fname in fd:
                X[i, j] = float(fd[fname])
            elif fname.endswith('_was_missing'):
                core = fname.replace('_was_missing', '')
                if core not in fd:
                    X[i, j] = 1.0
            elif fname.endswith('_not_applicable'):
                core = fname.replace('_not_applicable', '')
                if core not in fd:
                    X[i, j] = 1.0
    
    dmat = xgb.DMatrix(X, feature_names=TEACHER_FEATURES)
    return teacher_xgb.predict(dmat)


# ── Fetch & Evaluate ──
def main():
    print(f'\n{"="*80}')
    print('  FORTA LABELED ADDRESSES — ETHERSCAN TX FETCH → V2 EVALUATION')
    print(f'{"="*80}')
    
    # Sample addresses (stratified by category)
    addr_list = list(forta_addrs.items())
    random.seed(42)
    random.shuffle(addr_list)
    
    # Take up to MAX_ADDRESSES, stratified
    by_cat = {}
    for addr, info in addr_list:
        cat = info['category']
        by_cat.setdefault(cat, []).append((addr, info))
    
    sampled = []
    per_cat = MAX_ADDRESSES // len(by_cat)
    for cat, items in by_cat.items():
        sampled.extend(items[:per_cat])
    # Fill remainder
    remaining = MAX_ADDRESSES - len(sampled)
    all_remaining = [item for cat_items in by_cat.values() for item in cat_items[per_cat:]]
    sampled.extend(all_remaining[:remaining])
    
    print(f'\nSampled {len(sampled)} addresses for evaluation:')
    cat_counts = {}
    for _, info in sampled:
        cat_counts[info['category']] = cat_counts.get(info['category'], 0) + 1
    for c, n in sorted(cat_counts.items()):
        print(f'  {c}: {n}')
    
    # Check cache
    if CACHE_FILE.exists():
        print(f'\n📦 Loading cached Etherscan data from {CACHE_FILE}...')
        df_cache = pd.read_parquet(CACHE_FILE)
        cached_addrs = set(df_cache['address'].str.lower().unique())
        print(f'   Cached: {len(cached_addrs)} addresses')
    else:
        df_cache = pd.DataFrame()
        cached_addrs = set()
    
    # Fetch missing addresses
    to_fetch = [(addr, info) for addr, info in sampled if addr not in cached_addrs]
    print(f'\n📡 Fetching {len(to_fetch)} addresses from Etherscan (rate: {RATE_LIMIT}/s)...')
    print(f'   Estimated time: {len(to_fetch)/RATE_LIMIT:.0f}s')
    
    results = []
    t0 = time.time()
    success = 0
    empty = 0
    
    for i, (addr, info) in enumerate(to_fetch):
        if i > 0:
            time.sleep(1.0 / RATE_LIMIT)
        
        txs = fetch_tx_list(addr, max_txs=200)
        
        if txs:
            v2_feats = compute_address_features(addr, txs)
            teacher_feats = compute_teacher_features(addr, txs)
            results.append({
                'address': addr,
                'category': info['category'],
                'tag': info['tag'],
                'n_txs': len(txs),
                'v2_features': json.dumps(v2_feats),
                'teacher_features': json.dumps(teacher_feats),
            })
            success += 1
        else:
            empty += 1
        
        if (i + 1) % 50 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            remaining_time = (len(to_fetch) - i - 1) / rate
            print(f'   [{i+1}/{len(to_fetch)}] {success} fetched, {empty} empty ({rate:.1f} addr/s, ~{remaining_time:.0f}s left)')
            # Incremental save every 50
            if results:
                df_inc = pd.DataFrame(results)
                if not df_cache.empty:
                    df_inc = pd.concat([df_cache, df_inc], ignore_index=True)
                df_inc.to_parquet(CACHE_FILE, index=False)
    
    elapsed = time.time() - t0
    print(f'   Done: {success} fetched, {empty} empty in {elapsed:.1f}s')
    
    # Merge with cache
    if results:
        df_new = pd.DataFrame(results)
        if not df_cache.empty:
            df_all = pd.concat([df_cache, df_new], ignore_index=True)
        else:
            df_all = df_new
        df_all.to_parquet(CACHE_FILE, index=False)
        print(f'   💾 Saved {len(df_all)} addresses to cache')
    else:
        df_all = df_cache
    
    # Also include cached addresses that are in our sample
    sampled_addrs = set(addr for addr, _ in sampled)
    df_eval = df_all[df_all['address'].isin(sampled_addrs) & (df_all['n_txs'] > 0)].copy()
    
    print(f'\n📊 Evaluation dataset: {len(df_eval)} addresses with tx data')
    if len(df_eval) < 10:
        print('⚠️  Too few addresses with data. Cannot evaluate reliably.')
        return
    
    # Parse features
    v2_feature_dicts = [json.loads(row['v2_features']) for _, row in df_eval.iterrows()]
    teacher_feature_dicts = [json.loads(row['teacher_features']) for _, row in df_eval.iterrows()]
    
    # All Forta addresses are MALICIOUS (label = 1)
    # We need NORMAL addresses too for AUC calculation.
    # Strategy: also fetch some random non-Forta addresses as negatives.
    print(f'\n📡 Fetching normal addresses for negative class...')
    
    # Use known legitimate addresses (exchanges, big DeFi protocols)
    normal_addresses = [
        '0x28c6c06298d514db089934071355e5743bf21d60',  # Binance 14
        '0x21a31ee1afc51d94c2efccaa2092ad1028285549',  # Binance 7
        '0xdfd5293d8e347dfe59e90efd55b2956a1343963d',  # Binance 8
        '0x56eddb7aa87536c09ccc2793473599fd21a8b17f',  # Coinbase 4
        '0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43',  # Coinbase 2
        '0xbe0eb53f46cd790cd13851d5eff43d12404d33e8',  # Binance
        '0xf977814e90da44bfa03b6295a0616a897441acec',  # Binance 8
        '0x503828976d22510aad0201ac7ec88293211d23da',  # Coinbase Commerce
        '0x3cd751e6b0078be393132286c442345e68ff0aaa',  # Coinbase 11
        '0xd24400ae8bfebb18ca49be86258a3c749cf46853',  # Gemini 4
        '0x564286362092d8e7936f0549571a803b203aaced',  # Binance US
        '0xe93381fb4c4f14bda253907b18fad305d799cee7',  # Huobi 10
        '0xf17aced3c7a8daa29ebb90db8d1b6efdb16930e5',  # Kraken 13 (hot)
        '0x0a869d79a7052c7f1b55a8ebabbea3420f0d1e13',  # Kraken 4
        '0x267be1c1d684f78cb4f6a176c4911a741e4e5e4d',  # Kraken 6
    ]
    
    # Also get some random recent blocks to find normal EOAs
    # For efficiency, use pre-known DeFi user addresses
    normal_extra = [
        '0x1db3439a222c519ab44bb1144fc28167b4fa6ee6',
        '0x189b9cbd4aff470af2c0102f365fc1823d857965',
        '0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc',
        '0x0d0707963952f2fba59dd06f2b425ace40b492fe',
        '0xf5b0a3efb8e8e4c201e2a935f110eaaf3ffecb8d',
        '0x6cc5f688a315f3dc28a7781717a9a798a59fda7b',
        '0xcfc50541c3deaf725ce738ef87ace2ad778ba0c5',
        '0xd8da6bf26964af9d7eed9e03e53415d37aa96045',  # vitalik.eth
        '0x220866b1a2219f40e72f5c628b65d54268ca3a9d',  # Maker
        '0x2faf487a4414fe77e2327f0bf4ae2a264a776ad2',  # FTX (pre-collapse, normal ops)
    ]
    normal_addresses.extend(normal_extra)
    
    # Remove any that might be in Forta list
    normal_addresses = [a.lower() for a in normal_addresses if a.lower() not in forta_addrs]
    
    normal_v2_feats = []
    normal_teacher_feats = []
    normal_fetched = 0
    
    for addr in normal_addresses:
        time.sleep(1.0 / RATE_LIMIT)
        txs = fetch_tx_list(addr, max_txs=200)
        if txs:
            normal_v2_feats.append(compute_address_features(addr, txs))
            normal_teacher_feats.append(compute_teacher_features(addr, txs))
            normal_fetched += 1
        if normal_fetched >= 50:  # Cap at 50 normal addresses
            break
    
    print(f'   Fetched {normal_fetched} normal addresses')
    
    # Combine malicious + normal
    all_v2_feats = v2_feature_dicts + normal_v2_feats
    all_teacher_feats = teacher_feature_dicts + normal_teacher_feats
    y_true = np.array([1] * len(v2_feature_dicts) + [0] * len(normal_v2_feats))
    categories = list(df_eval['category'].values) + ['normal'] * len(normal_v2_feats)
    
    print(f'\n📊 Final evaluation set: {len(y_true)} addresses')
    print(f'   Malicious: {y_true.sum()} | Normal: {(y_true==0).sum()} | Rate: {y_true.mean():.2%}')
    
    # ── Student V2 Predictions ──
    print(f'\n{"="*80}')
    print('  STUDENT V2 MODEL')
    print(f'{"="*80}')
    
    xgb_prob, lgb_prob = predict_student(all_v2_feats)
    
    def report(name, y, prob, threshold=None):
        if threshold is None:
            threshold = OPTIMAL_THRESHOLD
        y_pred = (prob >= threshold).astype(int)
        roc = roc_auc_score(y, prob)
        ap = average_precision_score(y, prob)
        f1 = f1_score(y, y_pred, zero_division=0)
        prec = precision_score(y, y_pred, zero_division=0)
        rec = recall_score(y, y_pred, zero_division=0)
        
        prec_c, rec_c, thr_c = precision_recall_curve(y, prob)
        f1s = 2 * prec_c * rec_c / (prec_c + rec_c + 1e-10)
        best_idx = np.argmax(f1s)
        best_f1 = f1s[best_idx]
        best_thr = thr_c[min(best_idx, len(thr_c)-1)]
        
        cm = confusion_matrix(y, y_pred)
        
        print(f'\n  📊 {name}')
        print(f'  {"─"*60}')
        print(f'    ROC-AUC:    {roc:.4f}')
        print(f'    PR-AUC:     {ap:.4f}')
        print(f'    F1@{threshold:.4f}: {f1:.4f}  (P={prec:.4f} R={rec:.4f})')
        print(f'    Best F1:    {best_f1:.4f} @ threshold={best_thr:.4f}')
        print(f'    Confusion: TN={cm[0,0]} FP={cm[0,1]} FN={cm[1,0]} TP={cm[1,1]}')
        print(f'    Prob dist:  malicious mean={prob[y==1].mean():.4f} | normal mean={prob[y==0].mean():.4f}')
        
        return {'name': name, 'roc_auc': roc, 'pr_auc': ap, 'f1': f1, 'best_f1': best_f1}
    
    r1 = report('Student XGB', y_true, xgb_prob)
    r2 = report('Student LGB', y_true, lgb_prob)
    
    # Meta ensemble
    n = len(all_v2_feats)
    meta_input = np.zeros((n, len(META_FEATURES)), dtype=np.float32)
    meta_input[:, -2] = xgb_prob
    meta_input[:, -1] = lgb_prob
    try:
        meta_prob = meta_model.predict_proba(meta_input)[:, 1]
        r3 = report('Student Meta-Ensemble', y_true, meta_prob)
    except:
        print('  ⚠️ Meta-ensemble failed, skipping')
    
    # ── Teacher Predictions ──
    print(f'\n{"="*80}')
    print('  TEACHER MODEL (Hope_machine XGB)')
    print(f'{"="*80}')
    
    teacher_prob = predict_teacher_model(all_teacher_feats)
    r4 = report('Teacher XGB', y_true, teacher_prob, threshold=0.5)
    
    # Detection rate for malicious only
    print(f'\n  Detection Rates (malicious addresses only):')
    mal_probs_student = xgb_prob[y_true == 1]
    mal_probs_teacher = teacher_prob[y_true == 1]
    
    for thr_name, thr in [('0.5', 0.5), ('V2 optimal', OPTIMAL_THRESHOLD), ('0.3', 0.3), ('0.1', 0.1)]:
        det_s = (mal_probs_student >= thr).mean()
        det_t = (mal_probs_teacher >= thr).mean()
        print(f'    @{thr_name:>12}: Student={det_s:.2%}  Teacher={det_t:.2%}')
    
    # By category
    print(f'\n  Detection by category (Student XGB @ optimal threshold):')
    for cat in sorted(set(categories)):
        mask = np.array([c == cat for c in categories])
        if mask.sum() == 0:
            continue
        cat_prob = xgb_prob[mask]
        det = (cat_prob >= OPTIMAL_THRESHOLD).mean()
        mean_p = cat_prob.mean()
        print(f'    {cat:>12}: {mask.sum():>4} addrs | detect={det:.2%} | mean_prob={mean_p:.4f}')
    
    # Save results
    results_file = FORTA_DIR / 'forta_evaluation_results.json'
    with open(results_file, 'w') as f:
        json.dump({
            'date': datetime.now().isoformat(),
            'n_malicious': int(y_true.sum()),
            'n_normal': int((y_true == 0).sum()),
            'student_xgb': r1,
            'student_lgb': r2,
            'teacher': r4,
        }, f, indent=2)
    print(f'\n📁 Results saved to {results_file}')


if __name__ == '__main__':
    main()
