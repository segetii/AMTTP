#!/usr/bin/env python3
"""Check Forta labeled addresses overlap with our training data."""
import pandas as pd
import numpy as np

# Load our training data
print('Loading training data...')
df = pd.read_parquet(r'c:\amttp\processed\eth_transactions_full_labeled.parquet')
our_from = set(df['from_address'].str.lower().unique())
our_to = set(df['to_address'].str.lower().unique())
our_addrs = our_from | our_to
print(f'Our unique addresses: {len(our_addrs):,}')
print(f'Our tx count: {len(df):,}')
print(f'Columns: {list(df.columns[:30])}')

forta_dir = r'c:\amttp\data\external_validation\forta'

# Load all Forta labels
banned = pd.read_csv(f'{forta_dir}/1_etherscan_malicious_labels.csv')
banned_addrs = set(banned['banned_address'].str.lower())

phish = pd.read_csv(f'{forta_dir}/1_phishing_scams.csv')
phish_addrs = set(phish['address'].str.lower())

mal = pd.read_csv(f'{forta_dir}/1_malicious_smart_contracts.csv')
mal_creators = set(mal['contract_creator'].str.lower().dropna())
mal_contracts = set(mal['contract_address'].str.lower().dropna())
mal_all = mal_creators | mal_contracts

all_forta = banned_addrs | phish_addrs | mal_all
print(f'\nForta breakdown:')
print(f'  Etherscan banned: {len(banned_addrs):,}')
print(f'  Phishing scams:   {len(phish_addrs):,}')
print(f'  Malicious SC:     {len(mal_all):,} ({len(mal_creators)} creators + {len(mal_contracts)} contracts)')
print(f'  Total unique:     {len(all_forta):,}')

# Check overlaps
overlap_banned = banned_addrs & our_addrs
overlap_phish = phish_addrs & our_addrs
overlap_mal = mal_all & our_addrs
overlap_all = all_forta & our_addrs

print(f'\nOverlap with our 30-day data:')
print(f'  Banned:    {len(overlap_banned):,}')
print(f'  Phishing:  {len(overlap_phish):,}')
print(f'  Malicious: {len(overlap_mal):,}')
print(f'  Total:     {len(overlap_all):,}')

if len(overlap_all) > 0:
    # Get transactions involving Forta addresses
    df_from = df[df['from_address'].str.lower().isin(overlap_all)]
    df_to = df[df['to_address'].str.lower().isin(overlap_all)]
    
    print(f'\nTransactions FROM Forta addresses: {len(df_from):,}')
    print(f'Transactions TO Forta addresses:   {len(df_to):,}')
    
    if len(df_from) > 0:
        fraud_col = 'fraud' if 'fraud' in df_from.columns else 'label_unified'
        vc = df_from[fraud_col].value_counts().to_dict()
        print(f'  FROM fraud dist: {vc}')
        
    if len(df_to) > 0:
        fraud_col = 'fraud' if 'fraud' in df_to.columns else 'label_unified'
        vc = df_to[fraud_col].value_counts().to_dict()
        print(f'  TO fraud dist: {vc}')
    
    # Save the overlap transactions for evaluation
    df_forta_eval = df_from.copy()
    df_forta_eval['forta_label'] = 'malicious'
    df_forta_eval.to_parquet(r'c:\amttp\data\external_validation\forta\forta_overlap_txs.parquet')
    print(f'\nSaved {len(df_forta_eval):,} transactions to forta_overlap_txs.parquet')
    
    # Also check: how many Forta addresses appear ONLY as receivers (never as sender)?
    from_only = overlap_all & our_from
    to_only = (overlap_all & our_to) - our_from
    both = (overlap_all & our_from) & (overlap_all & our_to)
    print(f'\n  Forta addrs as sender:   {len(from_only):,}')
    print(f'  Forta addrs as receiver only: {len(to_only):,}')

    # Sample some overlap addresses with their labels
    sample_addrs = list(overlap_all)[:10]
    print(f'\nSample overlapping addresses:')
    for addr in sample_addrs:
        tags = []
        if addr in banned_addrs:
            tag = banned[banned['banned_address'].str.lower() == addr]['wallet_tag'].values
            tags.append(f'banned:{tag[0] if len(tag) > 0 else "?"}')
        if addr in phish_addrs:
            tag = phish[phish['address'].str.lower() == addr]['etherscan_tag'].values
            tags.append(f'phish:{tag[0] if len(tag) > 0 else "?"}')
        if addr in mal_all:
            tags.append('malicious_sc')
        n_tx = len(df[df['from_address'].str.lower() == addr])
        print(f'  {addr[:12]}... | {n_tx} txs | {", ".join(tags)}')
else:
    print('\nNo overlap found. Will need to pull tx data from Etherscan API.')
    print('Checking if we can use Etherscan to fetch features for Forta addresses...')
