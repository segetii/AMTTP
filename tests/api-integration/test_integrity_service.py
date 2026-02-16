"""Test the integrity service endpoints"""
import requests
import json

BASE_URL = "http://localhost:8008"

def test_verify_integrity_with_tampered_report():
    """Test that server rejects tampered integrity reports"""
    print("=" * 60)
    print("TEST: Tampered Integrity Report Rejection")
    print("=" * 60)
    
    tampered_report = {
        "version": "1.0.0",
        "pageIntegrity": {
            "pageHash": "fake",
            "scriptsHash": "fake",
            "stylesHash": "fake",
            "formsHash": "fake",
            "buttonsHash": "fake",
            "combinedHash": "fake",
            "timestamp": 1737142000000,
            "warnings": []
        },
        "componentIntegrity": [],
        "mutationAlerts": [],
        "isCompromised": False,
        "riskLevel": "safe",
        "timestamp": 1737142000000
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/verify-integrity",
            json=tampered_report,
            timeout=5
        )
        result = response.json()
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(result, indent=2)}")
        
        if not result.get("valid"):
            print("✅ TEST PASSED: Tampered report rejected")
            return True
        else:
            print("❌ TEST FAILED: Server accepted tampered report")
            return False
    except Exception as e:
        print(f"❌ TEST ERROR: {e}")
        return False


def test_submit_payment_with_hash_mismatch():
    """Test that server detects intent hash tampering"""
    print("\n" + "=" * 60)
    print("TEST: Intent Hash Tampering Detection")
    print("=" * 60)
    
    import time
    current_timestamp = int(time.time() * 1000)
    
    # This submission has mismatched intentHash
    tampered_submission = {
        "intent": {
            "type": "TRANSFER",
            "fromAddress": "0x1234567890123456789012345678901234567890",
            "toAddress": "0x0987654321098765432109876543210987654321",
            "valueWei": "100000000000000000000",  # Tampered: 100 ETH
            "valueEth": "100",
            "chainId": 1,
            "networkName": "Ethereum",
            "timestamp": current_timestamp,
            "nonce": 12345,
            "userAgent": "Test",
            "uiComponentHash": "test123",
            "displayedDataHash": "test456"
        },
        "intentHash": "abc123fake_hash_from_1_eth_intent",  # Wrong hash
        "signature": "0x" + "a" * 130,  # Fake signature
        "integrityReport": {
            "version": "1.0.0",
            "pageIntegrity": {
                "pageHash": "valid",
                "scriptsHash": "valid",
                "stylesHash": "valid",
                "formsHash": "valid",
                "buttonsHash": "valid",
                "combinedHash": "valid",
                "timestamp": current_timestamp,
                "warnings": []
            },
            "componentIntegrity": [],
            "mutationAlerts": [],
            "isCompromised": False,
            "riskLevel": "safe",
            "timestamp": current_timestamp
        }
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/submit-payment",
            json=tampered_submission,
            timeout=5
        )
        print(f"Status: {response.status_code}")
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
        
        if response.status_code == 400:
            detail = result.get("detail", "")
            if "hash mismatch" in detail.lower() or "tamper" in detail.lower():
                print("✅ TEST PASSED: Intent tampering detected")
                return True
        
        print("❌ TEST FAILED: Intent tampering NOT detected")
        return False
    except Exception as e:
        print(f"❌ TEST ERROR: {e}")
        return False


def test_stale_report():
    """Test that server rejects stale (old) integrity reports"""
    print("\n" + "=" * 60)
    print("TEST: Stale Report Rejection")
    print("=" * 60)
    
    # Timestamp from 2 minutes ago
    import time
    old_timestamp = int((time.time() - 120) * 1000)
    
    stale_report = {
        "version": "1.0.0",
        "pageIntegrity": {
            "pageHash": "validhash123",
            "scriptsHash": "validhash123",
            "stylesHash": "validhash123",
            "formsHash": "validhash123",
            "buttonsHash": "validhash123",
            "combinedHash": "validhash123",
            "timestamp": old_timestamp,
            "warnings": []
        },
        "componentIntegrity": [],
        "mutationAlerts": [],
        "isCompromised": False,
        "riskLevel": "safe",
        "timestamp": old_timestamp
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/verify-integrity",
            json=stale_report,
            timeout=5
        )
        result = response.json()
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(result, indent=2)}")
        
        if not result.get("valid") and "stale" in result.get("message", "").lower():
            print("✅ TEST PASSED: Stale report rejected")
            return True
        else:
            print("❌ TEST FAILED: Stale report accepted")
            return False
    except Exception as e:
        print(f"❌ TEST ERROR: {e}")
        return False


def test_critical_mutation_alert():
    """Test that server rejects reports with critical mutation alerts"""
    print("\n" + "=" * 60)
    print("TEST: Critical Mutation Alert Detection")
    print("=" * 60)
    
    import time
    current_timestamp = int(time.time() * 1000)
    
    compromised_report = {
        "version": "1.0.0",
        "pageIntegrity": {
            "pageHash": "validhash123",
            "scriptsHash": "validhash123",
            "stylesHash": "validhash123",
            "formsHash": "validhash123",
            "buttonsHash": "validhash123",
            "combinedHash": "validhash123",
            "timestamp": current_timestamp,
            "warnings": []
        },
        "componentIntegrity": [],
        "mutationAlerts": [
            {
                "type": "script_injection",
                "severity": "critical",
                "element": "payment-form",
                "details": "Malicious script injected",
                "timestamp": current_timestamp
            }
        ],
        "isCompromised": True,
        "riskLevel": "compromised",
        "timestamp": current_timestamp
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/verify-integrity",
            json=compromised_report,
            timeout=5
        )
        result = response.json()
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(result, indent=2)}")
        
        if not result.get("valid") and "critical" in result.get("message", "").lower():
            print("✅ TEST PASSED: Critical mutation detected")
            return True
        else:
            print("❌ TEST FAILED: Critical mutation NOT detected")
            return False
    except Exception as e:
        print(f"❌ TEST ERROR: {e}")
        return False


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("   AMTTP UI INTEGRITY SERVICE TESTS")
    print("=" * 60 + "\n")
    
    results = {
        "tampered_report": test_verify_integrity_with_tampered_report(),
        "intent_tampering": test_submit_payment_with_hash_mismatch(),
        "stale_report": test_stale_report(),
        "critical_mutation": test_critical_mutation_alert()
    }
    
    print("\n" + "=" * 60)
    print("   SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {test_name}: {status}")
    
    passed_count = sum(1 for v in results.values() if v)
    total = len(results)
    
    print("=" * 60)
    print(f"  Total: {passed_count}/{total} tests passed")
    print("=" * 60)
    
    if passed_count != total:
        exit(1)
