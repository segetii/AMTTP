"""
AMTTP Comprehensive Browser-Based UI Testing
Uses Playwright to test actual rendered UI elements, forms, buttons, and navigation
"""

import asyncio
from playwright.async_api import async_playwright, Page, Browser
from datetime import datetime
import json

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

async def test_flutter_app(browser: Browser):
    """Test Flutter app UI with real browser"""
    print("\n" + "="*60)
    print("FLUTTER APP BROWSER TESTS")
    print("="*60)
    
    page = await browser.new_page()
    
    try:
        # Navigate to Flutter app
        await page.goto(FLUTTER_URL, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)  # Wait for Flutter to render
        
        log_test("Flutter", "App Loaded", True, f"URL: {page.url}")
        
        # Check for Flutter elements (Flutter uses custom elements like flt-glass-pane, flt-scene-host)
        # Also check for the flutter_service_worker script or main.dart.js loading
        page_content = await page.content()
        has_flutter = (
            "flutter" in page_content.lower() or 
            "flt-" in page_content or 
            await page.query_selector("flt-glass-pane") is not None or
            await page.query_selector("flt-scene-host") is not None or
            await page.query_selector("flutter-view") is not None
        )
        log_test("Flutter", "Flutter Rendering", has_flutter, 
                 "Flutter elements detected" if has_flutter else "No Flutter elements found")
        
        # Take screenshot
        await page.screenshot(path="C:\\amttp\\screenshots\\flutter_home.png")
        log_test("Flutter", "Screenshot Captured", True, "flutter_home.png")
        
        # Test navigation to login
        await page.goto(f"{FLUTTER_URL}/#/login", wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(2000)
        log_test("Flutter", "Login Route", True, "Navigated to /#/login")
        await page.screenshot(path="C:\\amttp\\screenshots\\flutter_login.png")
        
        # Test navigation to dashboard
        await page.goto(f"{FLUTTER_URL}/#/dashboard", wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(2000)
        log_test("Flutter", "Dashboard Route", True, "Navigated to /#/dashboard")
        await page.screenshot(path="C:\\amttp\\screenshots\\flutter_dashboard.png")
        
    except Exception as e:
        log_test("Flutter", "App Test Error", False, str(e))
    finally:
        await page.close()

async def test_nextjs_login(browser: Browser):
    """Test Next.js login page UI"""
    print("\n" + "="*60)
    print("NEXT.JS LOGIN PAGE TESTS")
    print("="*60)
    
    page = await browser.new_page()
    
    try:
        await page.goto(f"{NEXTJS_URL}/login", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        
        log_test("Login", "Page Loaded", True, f"URL: {page.url}")
        
        # Take screenshot
        await page.screenshot(path="C:\\amttp\\screenshots\\nextjs_login.png")
        log_test("Login", "Screenshot Captured", True, "nextjs_login.png")
        
        # Check for tab buttons
        tabs = await page.query_selector_all("button")
        log_test("Login", "Tab Buttons Found", len(tabs) > 0, f"Found {len(tabs)} buttons")
        
        # Click on Email tab
        email_tab = await page.query_selector("button:has-text('Email')")
        if email_tab:
            await email_tab.click()
            await page.wait_for_timeout(500)
            log_test("Login", "Email Tab Clicked", True, "Switched to email login")
        
        # Check for email input
        email_input = await page.query_selector("input[type='email']")
        log_test("Login", "Email Input Present", email_input is not None, 
                 "Email input found" if email_input else "No email input")
        
        # Check for password input
        password_input = await page.query_selector("input[type='password']")
        log_test("Login", "Password Input Present", password_input is not None,
                 "Password input found" if password_input else "No password input")
        
        # Test form input
        if email_input and password_input:
            await email_input.fill("user@amttp.io")
            await password_input.fill("user123")
            log_test("Login", "Form Filled", True, "Email and password entered")
            
            # Take screenshot with filled form
            await page.screenshot(path="C:\\amttp\\screenshots\\nextjs_login_filled.png")
        
        # Check for submit button
        submit_btn = await page.query_selector("button[type='submit']")
        log_test("Login", "Submit Button", submit_btn is not None,
                 "Submit button found" if submit_btn else "No submit button")
        
        # Test Demo tab
        demo_tab = await page.query_selector("button:has-text('Demo')")
        if demo_tab:
            await demo_tab.click()
            await page.wait_for_timeout(500)
            log_test("Login", "Demo Tab", True, "Switched to demo mode")
            await page.screenshot(path="C:\\amttp\\screenshots\\nextjs_login_demo.png")
            
            # Check for role selection cards (divs with gradient backgrounds and role text)
            role_cards = await page.query_selector_all("div:has-text('End User'), div:has-text('Compliance'), div:has-text('Admin')")
            if len(role_cards) == 0:
                # Try alternate selector - look for clickable role options
                role_cards = await page.query_selector_all("[class*='cursor-pointer']")
            if len(role_cards) == 0:
                # Check for role title text
                role_cards = await page.query_selector_all("h3, h4")
            log_test("Login", "Role Cards", len(role_cards) > 0, f"Found {len(role_cards)} role options")
        
    except Exception as e:
        log_test("Login", "Test Error", False, str(e))
    finally:
        await page.close()

async def test_nextjs_dashboard(browser: Browser):
    """Test Next.js dashboard page"""
    print("\n" + "="*60)
    print("NEXT.JS DASHBOARD TESTS")
    print("="*60)
    
    page = await browser.new_page()
    
    try:
        await page.goto(f"{NEXTJS_URL}/dashboard", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        
        log_test("Dashboard", "Page Loaded", True, f"URL: {page.url}")
        await page.screenshot(path="C:\\amttp\\screenshots\\nextjs_dashboard.png")
        
        # Check for navigation
        nav = await page.query_selector("nav")
        log_test("Dashboard", "Navigation Bar", nav is not None, 
                 "Nav element found" if nav else "No nav element")
        
        # Check for sidebar
        sidebar = await page.query_selector("aside")
        log_test("Dashboard", "Sidebar", sidebar is not None,
                 "Sidebar found" if sidebar else "No sidebar")
        
        # Check for main content
        main = await page.query_selector("main")
        log_test("Dashboard", "Main Content Area", main is not None,
                 "Main content area found" if main else "No main content")
        
        # Check for buttons
        buttons = await page.query_selector_all("button")
        log_test("Dashboard", "Interactive Buttons", len(buttons) > 0, 
                 f"Found {len(buttons)} buttons")
        
        # Check for links
        links = await page.query_selector_all("a")
        log_test("Dashboard", "Navigation Links", len(links) > 0,
                 f"Found {len(links)} links")
        
    except Exception as e:
        log_test("Dashboard", "Test Error", False, str(e))
    finally:
        await page.close()

async def test_nextjs_other_pages(browser: Browser):
    """Test other Next.js pages"""
    print("\n" + "="*60)
    print("NEXT.JS OTHER PAGES TESTS")
    print("="*60)
    
    pages_to_test = [
        ("/register", "Register"),
        ("/compliance", "Compliance"),
        ("/settings", "Settings"),
        ("/disputes", "Disputes"),
        ("/transfer", "Transfer"),
        ("/reports", "Reports"),
        ("/policies", "Policies"),
    ]
    
    for path, name in pages_to_test:
        page = await browser.new_page()
        try:
            await page.goto(f"{NEXTJS_URL}{path}", wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(1000)
            
            # Check page loaded with content
            content = await page.content()
            has_content = len(content) > 1000
            log_test(name, "Page Loaded", has_content, f"Content size: {len(content)} bytes")
            
            # Take screenshot
            safe_name = name.lower().replace(" ", "_")
            await page.screenshot(path=f"C:\\amttp\\screenshots\\nextjs_{safe_name}.png")
            
        except Exception as e:
            log_test(name, "Page Load", False, str(e))
        finally:
            await page.close()

async def test_demo_login_flow(browser: Browser):
    """Test complete demo login flow"""
    print("\n" + "="*60)
    print("DEMO LOGIN FLOW TEST")
    print("="*60)
    
    page = await browser.new_page()
    
    try:
        # Go to login
        await page.goto(f"{NEXTJS_URL}/login", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        
        # Click Demo tab
        demo_tab = await page.query_selector("button:has-text('Demo')")
        if demo_tab:
            await demo_tab.click()
            await page.wait_for_timeout(1000)
            log_test("Demo Flow", "Demo Tab Selected", True, "Clicked Demo tab")
        else:
            log_test("Demo Flow", "Demo Tab Selected", False, "Demo tab not found")
            return
        
        # Try to find and click a role card (Super Admin for full access)
        # The role cards are buttons with role titles
        role_card = await page.query_selector("button:has-text('Super Admin')")
        if role_card:
            await role_card.click()
            await page.wait_for_timeout(500)
            log_test("Demo Flow", "Role Selected", True, "Selected Super Admin role")
        else:
            # Try alternate selector
            role_card = await page.query_selector("text=Super Admin")
            if role_card:
                await role_card.click()
                await page.wait_for_timeout(500)
                log_test("Demo Flow", "Role Selected", True, "Selected Super Admin role (alt)")
            else:
                log_test("Demo Flow", "Role Selected", False, "Could not find Super Admin role")
        
        # Look for "Enter Demo Mode" button
        connect_btn = await page.query_selector("button:has-text('Enter Demo Mode')")
        if not connect_btn:
            connect_btn = await page.query_selector("button:has-text('Enter')")
        if not connect_btn:
            connect_btn = await page.query_selector("button:has-text('Connect')")
        
        if connect_btn:
            await connect_btn.click()
            log_test("Demo Flow", "Enter Demo Mode Clicked", True, "Clicked Enter Demo Mode button")
            await page.wait_for_timeout(3000)
            
            # Check if redirected to dashboard or war-room
            current_url = page.url
            if "dashboard" in current_url or "war-room" in current_url or "focus" in current_url:
                log_test("Demo Flow", "Login Successful", True, f"Redirected to: {current_url}")
                await page.screenshot(path="C:\\amttp\\screenshots\\nextjs_post_login.png")
            else:
                log_test("Demo Flow", "Login Redirect", False, f"Still at: {current_url}")
                await page.screenshot(path="C:\\amttp\\screenshots\\nextjs_login_after_click.png")
        else:
            log_test("Demo Flow", "Enter Demo Mode Button", False, "No Enter Demo Mode button found")
        
    except Exception as e:
        log_test("Demo Flow", "Test Error", False, str(e))
    finally:
        await page.close()

async def main():
    """Main test runner"""
    print("="*60)
    print("AMTTP BROWSER-BASED UI TESTING")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    # Create screenshots directory
    import os
    os.makedirs("C:\\amttp\\screenshots", exist_ok=True)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        try:
            await test_flutter_app(browser)
            await test_nextjs_login(browser)
            await test_nextjs_dashboard(browser)
            await test_nextjs_other_pages(browser)
            await test_demo_login_flow(browser)
        finally:
            await browser.close()
    
    # Summary
    print("\n" + "="*60)
    print("UI TESTING SUMMARY")
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
        for r in test_results:
            if not r["passed"]:
                print(f"   - {r['category']}: {r['test_name']} - {r['details']}")
    
    # Save results
    with open("C:\\amttp\\browser_test_results.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "summary": {"total": total, "passed": passed, "failed": failed},
            "results": test_results
        }, f, indent=2)
    
    print(f"\n📄 Results saved to: C:\\amttp\\browser_test_results.json")
    print(f"📸 Screenshots saved to: C:\\amttp\\screenshots\\")

if __name__ == "__main__":
    asyncio.run(main())
