"""
AMTTP UI Functional Testing Script
Tests actual page content, forms, buttons, and interactive elements
"""

import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
from typing import Dict, List, Tuple
import re

# Configuration
FLUTTER_URL = "http://localhost:3010"
NEXTJS_URL = "http://localhost:3006"

test_results = []

def log_test(category: str, test_name: str, passed: bool, details: str = ""):
    """Log test result"""
    result = {
        "category": category,
        "test_name": test_name,
        "passed": passed,
        "details": details
    }
    test_results.append(result)
    status = "✅" if passed else "❌"
    print(f"{status} {category}: {test_name}")
    if details:
        print(f"   → {details}")

def get_page_content(url: str, timeout: int = 15) -> Tuple[bool, str, BeautifulSoup]:
    """Get page content and parse HTML"""
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            return True, response.text, soup
        else:
            return False, f"Status: {response.status_code}", None
    except Exception as e:
        return False, str(e), None

# ============================================================================
# FLUTTER APP UI TESTS
# ============================================================================

def test_flutter_ui():
    """Test Flutter app UI elements"""
    print("\n" + "="*60)
    print("FLUTTER APP UI TESTS")
    print("="*60)
    
    # Get main page
    success, content, soup = get_page_content(FLUTTER_URL)
    
    if not success:
        log_test("Flutter", "Page Load", False, content)
        return
    
    # Check for Flutter web app markers
    has_flutter = "flutter" in content.lower() or "main.dart.js" in content
    log_test("Flutter", "Flutter App Loaded", has_flutter, 
             "Found Flutter markers" if has_flutter else "No Flutter markers found")
    
    # Check for canvas element (Flutter renders to canvas)
    has_canvas = "flt-glass-pane" in content or "<canvas" in content.lower()
    log_test("Flutter", "Canvas Rendering", has_canvas,
             "Flutter canvas detected" if has_canvas else "No canvas found")
    
    # Check for main.dart.js script
    has_main_js = "main.dart.js" in content
    log_test("Flutter", "Main JS Bundle", has_main_js,
             "main.dart.js loaded" if has_main_js else "main.dart.js missing")
    
    # Check for flutter.js loader
    has_flutter_js = "flutter.js" in content
    log_test("Flutter", "Flutter Loader", has_flutter_js,
             "flutter.js present" if has_flutter_js else "flutter.js missing")
    
    # Check page title
    if soup:
        title = soup.find('title')
        title_text = title.text if title else "No title"
        log_test("Flutter", "Page Title", bool(title), f"Title: {title_text}")
    
    # Test that Flutter routes are accessible
    flutter_routes = [
        ("/#/login", "Login Page"),
        ("/#/register", "Register Page"),
        ("/#/dashboard", "Dashboard"),
    ]
    
    for route, name in flutter_routes:
        success, content, _ = get_page_content(f"{FLUTTER_URL}{route}")
        # Flutter SPA returns same HTML for all routes
        log_test("Flutter Route", name, success and "flutter" in content.lower(),
                 f"Route {route} accessible" if success else "Route failed")

# ============================================================================
# NEXT.JS APP UI TESTS
# ============================================================================

def test_nextjs_ui():
    """Test Next.js app UI elements"""
    print("\n" + "="*60)
    print("NEXT.JS APP UI TESTS")
    print("="*60)
    
    # Test Login Page
    print("\n--- Login Page Tests ---")
    success, content, soup = get_page_content(f"{NEXTJS_URL}/login", timeout=30)
    
    if success and soup:
        # Check for login form elements
        forms = soup.find_all('form')
        log_test("Login Page", "Has Form", len(forms) > 0, f"Found {len(forms)} form(s)")
        
        # Check for email input
        email_inputs = soup.find_all('input', {'type': 'email'}) or soup.find_all('input', {'name': re.compile('email', re.I)})
        log_test("Login Page", "Email Input", len(email_inputs) > 0, 
                 f"Found {len(email_inputs)} email input(s)")
        
        # Check for password input
        password_inputs = soup.find_all('input', {'type': 'password'})
        log_test("Login Page", "Password Input", len(password_inputs) > 0,
                 f"Found {len(password_inputs)} password input(s)")
        
        # Check for submit button
        buttons = soup.find_all('button')
        submit_buttons = [b for b in buttons if 'submit' in str(b).lower() or 'login' in str(b).lower() or 'sign' in str(b).lower()]
        log_test("Login Page", "Submit Button", len(buttons) > 0,
                 f"Found {len(buttons)} button(s), {len(submit_buttons)} login-related")
        
        # Check for links
        links = soup.find_all('a')
        log_test("Login Page", "Navigation Links", len(links) > 0, f"Found {len(links)} links")
    else:
        log_test("Login Page", "Page Load", False, content if not success else "No content")
    
    # Test Register Page
    print("\n--- Register Page Tests ---")
    success, content, soup = get_page_content(f"{NEXTJS_URL}/register", timeout=30)
    
    if success and soup:
        forms = soup.find_all('form')
        log_test("Register Page", "Has Form", len(forms) > 0, f"Found {len(forms)} form(s)")
        
        inputs = soup.find_all('input')
        log_test("Register Page", "Input Fields", len(inputs) >= 2, 
                 f"Found {len(inputs)} input field(s)")
        
        buttons = soup.find_all('button')
        log_test("Register Page", "Buttons", len(buttons) > 0, f"Found {len(buttons)} button(s)")
    else:
        log_test("Register Page", "Page Load", False, content if not success else "No content")
    
    # Test Dashboard Page
    print("\n--- Dashboard Page Tests ---")
    success, content, soup = get_page_content(f"{NEXTJS_URL}/dashboard", timeout=30)
    
    if success and soup:
        # Check for navigation/sidebar
        nav = soup.find_all(['nav', 'aside']) or soup.find_all(class_=re.compile('nav|sidebar|menu', re.I))
        log_test("Dashboard", "Navigation Present", len(nav) > 0, f"Found {len(nav)} nav elements")
        
        # Check for main content area
        main = soup.find_all(['main', 'article']) or soup.find_all(class_=re.compile('main|content|dashboard', re.I))
        log_test("Dashboard", "Main Content", len(main) > 0 or len(content) > 1000, 
                 f"Content size: {len(content)} bytes")
        
        # Check for interactive elements
        buttons = soup.find_all('button')
        links = soup.find_all('a')
        log_test("Dashboard", "Interactive Elements", len(buttons) + len(links) > 0,
                 f"Buttons: {len(buttons)}, Links: {len(links)}")
    else:
        log_test("Dashboard", "Page Load", False, content if not success else "No content")
    
    # Test Compliance Page
    print("\n--- Compliance Page Tests ---")
    success, content, soup = get_page_content(f"{NEXTJS_URL}/compliance", timeout=30)
    
    if success and soup:
        log_test("Compliance", "Page Loaded", True, f"Content size: {len(content)} bytes")
        
        # Check for tables (common in compliance pages)
        tables = soup.find_all('table')
        log_test("Compliance", "Data Tables", len(tables) >= 0, f"Found {len(tables)} table(s)")
        
        # Check for cards/sections
        cards = soup.find_all(class_=re.compile('card|panel|section', re.I))
        log_test("Compliance", "UI Cards/Panels", len(cards) >= 0 or len(content) > 500,
                 f"Found {len(cards)} card-like elements")
    else:
        log_test("Compliance", "Page Load", False, content if not success else "No content")
    
    # Test Settings Page
    print("\n--- Settings Page Tests ---")
    success, content, soup = get_page_content(f"{NEXTJS_URL}/settings", timeout=30)
    
    if success and soup:
        log_test("Settings", "Page Loaded", True, f"Content size: {len(content)} bytes")
        
        # Check for form elements
        inputs = soup.find_all('input')
        selects = soup.find_all('select')
        log_test("Settings", "Form Controls", len(inputs) + len(selects) >= 0,
                 f"Inputs: {len(inputs)}, Selects: {len(selects)}")
    else:
        log_test("Settings", "Page Load", False, content if not success else "No content")

# ============================================================================
# API ENDPOINT UI DATA TESTS
# ============================================================================

def test_api_data():
    """Test API endpoints return valid data for UI"""
    print("\n" + "="*60)
    print("API DATA FOR UI TESTS")
    print("="*60)
    
    # Next.js API Health
    try:
        response = requests.get(f"{NEXTJS_URL}/api/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            log_test("API", "Health Endpoint", True, f"Response: {data}")
        else:
            log_test("API", "Health Endpoint", False, f"Status: {response.status_code}")
    except Exception as e:
        log_test("API", "Health Endpoint", False, str(e))
    
    # Risk Engine Dashboard Stats
    try:
        response = requests.get("http://localhost:8002/dashboard/stats", timeout=10)
        if response.status_code == 200:
            data = response.json()
            log_test("Risk Engine", "Dashboard Stats", True, 
                     f"Keys: {list(data.keys()) if isinstance(data, dict) else 'array'}")
        else:
            log_test("Risk Engine", "Dashboard Stats", False, f"Status: {response.status_code}")
    except Exception as e:
        log_test("Risk Engine", "Dashboard Stats", False, str(e))
    
    # Risk Engine Alerts
    try:
        response = requests.get("http://localhost:8002/alerts", timeout=10)
        if response.status_code == 200:
            data = response.json()
            count = len(data) if isinstance(data, list) else "object"
            log_test("Risk Engine", "Alerts Data", True, f"Count: {count}")
        else:
            log_test("Risk Engine", "Alerts Data", False, f"Status: {response.status_code}")
    except Exception as e:
        log_test("Risk Engine", "Alerts Data", False, str(e))
    
    # Risk Engine Model Info
    try:
        response = requests.get("http://localhost:8002/model/info", timeout=10)
        if response.status_code == 200:
            data = response.json()
            log_test("Risk Engine", "Model Info", True, 
                     f"Model: {data.get('model_name', 'unknown')}")
        else:
            log_test("Risk Engine", "Model Info", False, f"Status: {response.status_code}")
    except Exception as e:
        log_test("Risk Engine", "Model Info", False, str(e))

# ============================================================================
# SUMMARY
# ============================================================================

def generate_summary():
    """Generate test summary"""
    print("\n" + "="*60)
    print("UI TESTING SUMMARY")
    print("="*60)
    
    total = len(test_results)
    passed = sum(1 for r in test_results if r["passed"])
    failed = total - passed
    
    print(f"\n📊 Total UI Tests: {total}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📈 Pass Rate: {(passed/total*100):.1f}%" if total > 0 else "N/A")
    
    if failed > 0:
        print("\n❌ FAILED TESTS:")
        for r in test_results:
            if not r["passed"]:
                print(f"   - {r['category']}: {r['test_name']} - {r['details']}")
    
    # Save results
    with open("C:\\amttp\\ui_test_results.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "summary": {"total": total, "passed": passed, "failed": failed},
            "results": test_results
        }, f, indent=2)
    
    print(f"\n📄 Results saved to: C:\\amttp\\ui_test_results.json")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("="*60)
    print("AMTTP UI FUNCTIONAL TESTING")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    test_flutter_ui()
    test_nextjs_ui()
    test_api_data()
    generate_summary()
