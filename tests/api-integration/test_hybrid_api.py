"""
Test the Hybrid Multi-Signal API
"""
import requests
import json

# Test several addresses
test_addresses = [
    '0xeae7380dd4cef6fbd1144f49e4d1e6964258a4f4',  # Known high-risk
    '0xa1abfa21f80ecf401bd41365adbb6fef6fefdf09',  # Top threat
    '0x28c6c06298d514db089934071355e5743bf21d60',  # Binance (should be flagged)
    '0x1234567890123456789012345678901234567890',  # Random (should be clean)
]

print('='*70)
print('TESTING HYBRID API')
print('='*70)

for addr in test_addresses:
    try:
        r = requests.post('http://127.0.0.1:8000/score/address', json={'address': addr})
        result = r.json()
        
        print(f"\n{addr[:20]}...")
        print(f"  Risk: {result['risk_level']} | Action: {result['action']}")
        print(f"  Hybrid: {result['hybrid_score']} | Signals: {result['signal_count']}")
        print(f"  ML: {result['ml_score']} | Graph: {result['graph_score']} | Pattern: {result['patterns']}")
    except Exception as e:
        print(f"\n{addr[:20]}... ERROR: {e}")

# Test batch scoring
print('\n' + '='*70)
print('BATCH SCORING TEST')
print('='*70)

batch_result = requests.post(
    'http://127.0.0.1:8000/score/batch',
    json={'addresses': test_addresses[:3]}
).json()

print(f"\nSummary: {batch_result['summary']}")
print(f"Processing time: {batch_result['processing_time_ms']}ms")

# Test transaction scoring
print('\n' + '='*70)
print('TRANSACTION SCORING TEST')
print('='*70)

tx_result = requests.post(
    'http://127.0.0.1:8000/score/transaction',
    json={
        'tx_hash': '0x123abc',
        'from_address': '0xeae7380dd4cef6fbd1144f49e4d1e6964258a4f4',
        'to_address': '0xa1abfa21f80ecf401bd41365adbb6fef6fefdf09',
        'value_eth': 1.5
    }
).json()

print(f"\nFrom: {tx_result['from_score']['action']} ({tx_result['from_score']['risk_level']})")
print(f"To: {tx_result['to_score']['action']} ({tx_result['to_score']['risk_level']})")
print(f"Overall: {tx_result['overall_action']} - Should Block: {tx_result['should_block']}")

# Test smart contract endpoints
print('\n' + '='*70)
print('SMART CONTRACT ENDPOINTS TEST')
print('='*70)

should_block = requests.post(
    'http://127.0.0.1:8000/contract/should-block',
    json={'address': '0xeae7380dd4cef6fbd1144f49e4d1e6964258a4f4'}
).json()

print(f"\nShould Block: {should_block}")

risk_score = requests.post(
    'http://127.0.0.1:8000/contract/risk-score',
    json={'address': '0xeae7380dd4cef6fbd1144f49e4d1e6964258a4f4'}
).json()

print(f"Risk Score (0-1000): {risk_score}")
