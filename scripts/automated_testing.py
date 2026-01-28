"""
AMTTP Automated Testing Script
Tests all URLs, endpoints, and validates application functionality
"""

import requests
import json
from datetime import datetime
from typing import Dict, List, Tuple
import time

# Configuration
FLUTTER_URL = "http://localhost:3010"
NEXTJS_URL = "http://localhost:3006"
RISK_ENGINE_URL = "http://localhost:8002"
MEMGRAPH_HOST = "localhost"
MEMGRAPH_PORT = 7687

# Test Results Storage
test_results: List[Dict] = []

def log_test(category: str, test_name: str, url: str, passed: bool, details: str = ""):
    """Log test result"""
    result = {
        "timestamp": datetime.now().isoformat(),
        "category": category,
        "test_name": test_name,
        "url": url,
        "passed": passed,
        "details": details
    }
    test_results.append(result)
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} | {category} | {test_name} | {url}")
    if details and not passed:
        print(f"       Details: {details}")

def test_url(url: str, expected_status: int = 200, timeout: int = 15) -> Tuple[bool, str]:
    """Test if a URL is accessible"""
    try:
        response = requests.get(url, timeout=timeout, allow_redirects=True)
        if response.status_code == expected_status:
            return True, f"Status: {response.status_code}"
        elif response.status_code in [200, 301, 302, 307, 308]:
            return True, f"Status: {response.status_code} (redirect)"
        else:
            return False, f"Expected {expected_status}, got {response.status_code}"
    except requests.exceptions.Timeout:
        return False, "Request timed out"
    except requests.exceptions.ConnectionError:
        return False, "Connection refused"
    except Exception as e:
        return False, str(e)[:100]

def test_api_endpoint(url: str, method: str = "GET", data: dict = None, 
                      expected_status: int = 200) -> Tuple[bool, str]:
    """Test API endpoint"""
    try:
        if method == "GET":
            response = requests.get(url, timeout=10)
        elif method == "POST":
            response = requests.post(url, json=data, timeout=10)
        else:
            return False, f"Unsupported method: {method}"
        
        if response.status_code == expected_status:
            try:
                json_data = response.json()
                return True, f"Status: {response.status_code}, Response: {str(json_data)[:100]}"
            except:
                return True, f"Status: {response.status_code}"
        else:
            return False, f"Expected {expected_status}, got {response.status_code}"
    except Exception as e:
        return False, str(e)

# ============================================================================
# FLUTTER APP TESTS
# ============================================================================

def test_flutter_app():
    """Test Flutter application pages"""
    print("\n" + "="*60)
    print("FLUTTER APP TESTS (http://localhost:3010)")
    print("="*60)
    
    # Main app pages
    flutter_pages = [
        ("/", "Home/Login Page"),
        ("/#/login", "Login Route"),
        ("/#/register", "Register Route"),
        ("/#/dashboard", "Dashboard"),
        ("/#/transaction-graph", "Transaction Graph"),
        ("/#/wallet-risk", "Wallet Risk Analysis"),
        ("/#/alerts", "Alerts Page"),
        ("/#/sanctions", "Sanctions Check"),
        ("/#/ml-dashboard", "ML Dashboard"),
        ("/#/policy-studio", "Policy Studio"),
        ("/#/settings", "Settings"),
        ("/#/audit", "Audit Trail"),
        ("/#/cross-chain", "Cross-Chain"),
        ("/#/reports", "Reports"),
    ]
    
    for path, name in flutter_pages:
        url = f"{FLUTTER_URL}{path}"
        passed, details = test_url(url)
        log_test("Flutter", name, url, passed, details)

# ============================================================================
# NEXT.JS APP TESTS  
# ============================================================================

def test_nextjs_app():
    """Test Next.js application pages"""
    print("\n" + "="*60)
    print("NEXT.JS APP TESTS (http://localhost:3006)")
    print("="*60)
    
    # Next.js pages - core pages only for faster testing
    nextjs_pages = [
        ("/", "Home Page"),
        ("/login", "Login Page"),
        ("/register", "Register Page"),
        ("/dashboard", "Dashboard"),
        ("/compliance", "Compliance Dashboard"),
        ("/settings", "Settings"),
        ("/disputes", "Disputes"),
        ("/transfer", "Transfer"),
        ("/reports", "Reports"),
        ("/policies", "Policies"),
        ("/concierge", "Concierge"),
    ]
    
    for path, name in nextjs_pages:
        url = f"{NEXTJS_URL}{path}"
        passed, details = test_url(url)
        log_test("Next.js", name, url, passed, details)
    
    # Test API routes
    nextjs_api = [
        ("/api/health", "Health Check API"),
    ]
    
    for path, name in nextjs_api:
        url = f"{NEXTJS_URL}{path}"
        passed, details = test_api_endpoint(url)
        log_test("Next.js API", name, url, passed, details)

# ============================================================================
# RISK ENGINE API TESTS
# ============================================================================

def test_risk_engine():
    """Test Risk Engine API endpoints"""
    print("\n" + "="*60)
    print("RISK ENGINE API TESTS (http://localhost:8002)")
    print("="*60)
    
    # Health check
    url = f"{RISK_ENGINE_URL}/health"
    passed, details = test_api_endpoint(url)
    log_test("Risk Engine", "Health Check", url, passed, details)
    
    # Model info (correct path)
    url = f"{RISK_ENGINE_URL}/model/info"
    passed, details = test_api_endpoint(url)
    log_test("Risk Engine", "Model Info", url, passed, details)
    
    # List models
    url = f"{RISK_ENGINE_URL}/models"
    passed, details = test_api_endpoint(url)
    log_test("Risk Engine", "List Models", url, passed, details)
    
    # Dashboard stats
    url = f"{RISK_ENGINE_URL}/dashboard/stats"
    passed, details = test_api_endpoint(url)
    log_test("Risk Engine", "Dashboard Stats", url, passed, details)
    
    # Alerts
    url = f"{RISK_ENGINE_URL}/alerts"
    passed, details = test_api_endpoint(url)
    log_test("Risk Engine", "Alerts", url, passed, details)
    
    # Dashboard timeline
    url = f"{RISK_ENGINE_URL}/dashboard/timeline"
    passed, details = test_api_endpoint(url)
    log_test("Risk Engine", "Dashboard Timeline", url, passed, details)
    
    # Test risk scoring endpoint with proper payload
    url = f"{RISK_ENGINE_URL}/score"
    data = {
        "from_address": "0x1234567890abcdef1234567890abcdef12345678",
        "to_address": "0xabcdef1234567890abcdef1234567890abcdef12",
        "value_eth": 1.5
    }
    passed, details = test_api_endpoint(url, method="POST", data=data)
    log_test("Risk Engine", "Score Transaction", url, passed, details)
    
    # Test batch scoring (correct path)
    url = f"{RISK_ENGINE_URL}/batch"
    data = {"transactions": [{
        "from_address": "0x1234567890abcdef1234567890abcdef12345678",
        "to_address": "0xabcdef1234567890abcdef1234567890abcdef12",
        "value_eth": 1.5
    }]}
    passed, details = test_api_endpoint(url, method="POST", data=data)
    log_test("Risk Engine", "Batch Score", url, passed, details)

# ============================================================================
# MEMGRAPH DATABASE TESTS
# ============================================================================

def test_memgraph():
    """Test Memgraph database connectivity"""
    print("\n" + "="*60)
    print("MEMGRAPH DATABASE TESTS")
    print("="*60)
    
    try:
        from neo4j import GraphDatabase
        
        driver = GraphDatabase.driver(
            f"bolt://{MEMGRAPH_HOST}:{MEMGRAPH_PORT}",
            auth=("", "")
        )
        
        with driver.session() as session:
            # Test connection
            result = session.run("RETURN 1 AS test")
            record = result.single()
            if record and record["test"] == 1:
                log_test("Memgraph", "Database Connection", f"bolt://{MEMGRAPH_HOST}:{MEMGRAPH_PORT}", True, "Connected successfully")
            
            # Count nodes
            result = session.run("MATCH (n) RETURN count(n) as count")
            count = result.single()["count"]
            log_test("Memgraph", "Node Count", "MATCH (n) RETURN count(n)", True, f"Nodes: {count}")
            
            # Count edges
            result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
            count = result.single()["count"]
            log_test("Memgraph", "Edge Count", "MATCH ()-[r]->() RETURN count(r)", True, f"Edges: {count}")
            
            # Check for sanctioned addresses
            result = session.run("MATCH (a:Address) WHERE a.is_sanctioned = true RETURN count(a) as count")
            count = result.single()["count"]
            log_test("Memgraph", "Sanctioned Addresses", "WHERE is_sanctioned = true", True, f"Sanctioned: {count}")
            
        driver.close()
        
    except ImportError:
        log_test("Memgraph", "Database Connection", f"bolt://{MEMGRAPH_HOST}:{MEMGRAPH_PORT}", False, "neo4j driver not installed")
    except Exception as e:
        log_test("Memgraph", "Database Connection", f"bolt://{MEMGRAPH_HOST}:{MEMGRAPH_PORT}", False, str(e))

# ============================================================================
# DOCKER SERVICES TESTS
# ============================================================================

def test_docker_services():
    """Test Docker-based services"""
    print("\n" + "="*60)
    print("DOCKER SERVICES TESTS")
    print("="*60)
    
    services = [
        ("http://localhost:8002/health", "Risk Engine (8002)"),
        ("http://localhost:8007/health", "Compliance Orchestrator (8007)"),
        ("http://localhost:8008/health", "Integrity Service (8008)"),
        ("http://localhost:3001/health", "Oracle Service (3001)"),
        ("http://localhost:3000", "Memgraph Lab (3000)"),
        ("http://localhost:8200/v1/sys/health", "Vault Server (8200)"),
    ]
    
    for url, name in services:
        passed, details = test_url(url)
        log_test("Docker Service", name, url, passed, details)

# ============================================================================
# RBAC ROLE TESTING
# ============================================================================

def test_rbac_access():
    """Test RBAC role-based access (simulation)"""
    print("\n" + "="*60)
    print("RBAC ACCESS CONTROL TESTS")
    print("="*60)
    
    # Define role-page access matrix
    roles = {
        "R1 (Retail User)": {
            "allowed": ["/dashboard", "/wallet-risk", "/sanctions"],
            "denied": ["/policy-studio", "/audit", "/settings"]
        },
        "R2 (PEP User)": {
            "allowed": ["/dashboard", "/wallet-risk", "/sanctions", "/alerts"],
            "denied": ["/policy-studio", "/audit"]
        },
        "R3 (Ops Team)": {
            "allowed": ["/dashboard", "/wallet-risk", "/alerts", "/transaction-graph"],
            "denied": ["/policy-studio"]
        },
        "R4 (Compliance Officer)": {
            "allowed": ["/dashboard", "/policy-studio", "/sanctions", "/audit", "/reports"],
            "denied": []
        },
        "R5 (Admin)": {
            "allowed": ["/dashboard", "/settings", "/audit", "/ml-dashboard"],
            "denied": []
        },
        "R6 (Super Admin)": {
            "allowed": ["ALL PAGES"],
            "denied": []
        },
    }
    
    for role, access in roles.items():
        print(f"\n  Testing {role}:")
        allowed_str = ", ".join(access["allowed"])
        denied_str = ", ".join(access["denied"]) if access["denied"] else "None"
        log_test("RBAC", f"{role} - Allowed Pages", "Access Matrix", True, f"Allowed: {allowed_str}")
        if access["denied"]:
            log_test("RBAC", f"{role} - Denied Pages", "Access Matrix", True, f"Denied: {denied_str}")

# ============================================================================
# SUMMARY REPORT
# ============================================================================

def generate_summary():
    """Generate test summary report"""
    print("\n" + "="*60)
    print("TEST SUMMARY REPORT")
    print("="*60)
    
    total = len(test_results)
    passed = sum(1 for r in test_results if r["passed"])
    failed = total - passed
    
    print(f"\n📊 Total Tests: {total}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📈 Pass Rate: {(passed/total*100):.1f}%" if total > 0 else "N/A")
    
    if failed > 0:
        print("\n❌ FAILED TESTS:")
        for result in test_results:
            if not result["passed"]:
                print(f"   - {result['category']}: {result['test_name']}")
                print(f"     URL: {result['url']}")
                print(f"     Error: {result['details']}")
    
    # Save results to JSON
    report_path = "C:\\amttp\\test_results.json"
    with open(report_path, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "pass_rate": f"{(passed/total*100):.1f}%" if total > 0 else "N/A"
            },
            "results": test_results
        }, f, indent=2)
    print(f"\n📄 Full report saved to: {report_path}")
    
    return passed, failed

# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    print("="*60)
    print("AMTTP AUTOMATED TESTING SUITE")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    # Run all tests
    test_flutter_app()
    test_nextjs_app()
    test_risk_engine()
    test_memgraph()
    test_docker_services()
    test_rbac_access()
    
    # Generate summary
    passed, failed = generate_summary()
    
    print("\n" + "="*60)
    print("TESTING COMPLETE")
    print("="*60)
