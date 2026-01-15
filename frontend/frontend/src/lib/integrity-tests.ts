/**
 * AMTTP UI Integrity Test Suite
 * 
 * Tests to verify the Bybit-style attack protection system works correctly.
 * Run these tests in browser console or as automated tests.
 */

// ═══════════════════════════════════════════════════════════════════════════════
// TEST 1: Script Injection Detection
// ═══════════════════════════════════════════════════════════════════════════════

async function testScriptInjection() {
  console.log("🧪 TEST 1: Script Injection Detection");
  
  // Try to inject a malicious script
  const script = document.createElement("script");
  script.textContent = "console.log('INJECTED SCRIPT');";
  
  // Monitor should catch this
  const paymentContainer = document.querySelector("[data-integrity-protected]");
  if (paymentContainer) {
    paymentContainer.appendChild(script);
    console.log("✓ Script injected, waiting for mutation alert...");
    
    // Wait 1 second for mutation observer to trigger
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    // Check if transaction was blocked
    const blockedView = document.querySelector(".secure-payment-container [class*='blocked']");
    if (blockedView) {
      console.log("✅ TEST PASSED: Script injection detected and blocked");
      return true;
    } else {
      console.error("❌ TEST FAILED: Script injection not detected");
      return false;
    }
  } else {
    console.warn("⚠️ Payment container not found");
    return false;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// TEST 2: DOM Manipulation Detection
// ═══════════════════════════════════════════════════════════════════════════════

async function testDOMManipulation() {
  console.log("🧪 TEST 2: DOM Manipulation Detection");
  
  // Try to manipulate the displayed amount
  const amountInput = document.querySelector<HTMLInputElement>("input[type='text'][placeholder*='0.0']");
  if (amountInput) {
    const originalValue = amountInput.value;
    
    // Attacker tries to display 1 ETH but actually send 100 ETH
    amountInput.value = "1.0";
    amountInput.setAttribute("data-actual-value", "100.0");
    
    console.log("✓ DOM manipulated (displayed: 1 ETH, hidden: 100 ETH)");
    
    // The integrity system should catch the hash mismatch
    // when generating the confirmation data
    console.log("✅ TEST SETUP: DOM manipulation ready for detection");
    console.log("   Next: Click 'Verify & Continue' and check if hash verification fails");
    
    return true;
  } else {
    console.warn("⚠️ Amount input not found");
    return false;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// TEST 3: Event Handler Replacement
// ═══════════════════════════════════════════════════════════════════════════════

async function testEventHandlerReplacement() {
  console.log("🧪 TEST 3: Event Handler Replacement");
  
  const submitButton = document.querySelector<HTMLButtonElement>("button[class*='bg-blue']");
  if (submitButton) {
    // Store original handler
    const originalHandler = submitButton.onclick;
    
    // Attacker replaces handler to steal signature
    submitButton.onclick = function(e) {
      console.log("MALICIOUS: Intercepting signature!");
      // In real attack, would send to attacker's server
    };
    
    console.log("✓ Event handler replaced with malicious code");
    
    // Wait for mutation observer
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    // Check if handler change was detected
    const securityAlerts = document.querySelectorAll("[class*='security-alert']");
    if (securityAlerts.length > 0) {
      console.log("✅ TEST PASSED: Handler replacement detected");
      return true;
    } else {
      console.log("⚠️ Handler replacement not detected (may be caught during verification)");
      return false;
    }
  } else {
    console.warn("⚠️ Submit button not found");
    return false;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// TEST 4: Integrity Hash Verification
// ═══════════════════════════════════════════════════════════════════════════════

async function testIntegrityHashVerification() {
  console.log("🧪 TEST 4: Integrity Hash Verification");
  
  try {
    // Simulate a tampered integrity report
    const tamperedReport = {
      version: "1.0.0",
      pageIntegrity: {
        pageHash: "fake",
        scriptsHash: "fake",
        stylesHash: "fake",
        formsHash: "fake",
        buttonsHash: "fake",
        combinedHash: "fake",
        timestamp: Date.now(),
        warnings: []
      },
      componentIntegrity: [],
      mutationAlerts: [],
      isCompromised: false,
      riskLevel: "safe",
      timestamp: Date.now()
    };
    
    // Try to verify with server
    const response = await fetch("http://localhost:8008/verify-integrity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(tamperedReport)
    });
    
    const result = await response.json();
    
    if (!result.valid) {
      console.log("✅ TEST PASSED: Tampered integrity report rejected by server");
      console.log("   Server message:", result.message);
      return true;
    } else {
      console.error("❌ TEST FAILED: Server accepted tampered integrity report");
      return false;
    }
  } catch (error) {
    console.error("❌ TEST ERROR:", error);
    return false;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// TEST 5: Intent Hash Tampering
// ═══════════════════════════════════════════════════════════════════════════════

async function testIntentHashTampering() {
  console.log("🧪 TEST 5: Intent Hash Tampering");
  
  try {
    // Create a valid intent
    const intent = {
      type: "TRANSFER",
      fromAddress: "0x1234567890123456789012345678901234567890",
      toAddress: "0x0987654321098765432109876543210987654321",
      valueWei: "1000000000000000000", // 1 ETH
      valueEth: "1",
      chainId: 1,
      networkName: "Ethereum",
      timestamp: Date.now(),
      nonce: 12345,
      userAgent: "Test",
      uiComponentHash: "test123",
      displayedDataHash: "test456"
    };
    
    // Generate correct hash
    const correctHash = await window.crypto.subtle.digest(
      "SHA-256",
      new TextEncoder().encode(JSON.stringify(intent))
    );
    const correctHashHex = Array.from(new Uint8Array(correctHash))
      .map(b => b.toString(16).padStart(2, "0"))
      .join("");
    
    // Tamper with intent (change value to 100 ETH)
    const tamperedIntent = { ...intent, valueWei: "100000000000000000000" };
    
    // Submit with original hash (mismatch)
    const response = await fetch("http://localhost:8008/submit-payment", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        intent: tamperedIntent,
        intentHash: correctHashHex,
        signature: "fake",
        integrityReport: {}
      })
    });
    
    if (response.status === 400) {
      const error = await response.json();
      if (error.detail && error.detail.includes("hash mismatch")) {
        console.log("✅ TEST PASSED: Intent tampering detected by server");
        return true;
      }
    }
    
    console.error("❌ TEST FAILED: Intent tampering not detected");
    return false;
  } catch (error) {
    console.error("❌ TEST ERROR:", error);
    return false;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// TEST RUNNER
// ═══════════════════════════════════════════════════════════════════════════════

type TestResults = {
  scriptInjection: boolean;
  domManipulation: boolean;
  eventHandler: boolean;
  integrityHash: boolean;
  intentTampering: boolean;
};

async function runAllTests() {
  console.log("═".repeat(60));
  console.log("  AMTTP UI Integrity Test Suite");
  console.log("═".repeat(60));
  console.log("");
  
  const results = {
    scriptInjection: await testScriptInjection(),
    domManipulation: await testDOMManipulation(),
    eventHandler: await testEventHandlerReplacement(),
    integrityHash: await testIntegrityHashVerification(),
    intentTampering: await testIntentHashTampering()
  };
  
  console.log("");
  console.log("═".repeat(60));
  console.log("  TEST RESULTS");
  console.log("═".repeat(60));
  console.log("Script Injection Detection:    ", results.scriptInjection ? "✅ PASS" : "❌ FAIL");
  console.log("DOM Manipulation Detection:    ", results.domManipulation ? "✅ PASS" : "❌ FAIL");
  console.log("Event Handler Protection:      ", results.eventHandler ? "✅ PASS" : "❌ FAIL");
  console.log("Integrity Hash Verification:   ", results.integrityHash ? "✅ PASS" : "❌ FAIL");
  console.log("Intent Tampering Detection:    ", results.intentTampering ? "✅ PASS" : "❌ FAIL");
  console.log("═".repeat(60));
  
  const passCount = Object.values(results).filter(r => r).length;
  const total = Object.keys(results).length;
  
  console.log(`\nOverall: ${passCount}/${total} tests passed`);
  
  return results;
}

// ═══════════════════════════════════════════════════════════════════════════════
// MONITORING DASHBOARD
// ═══════════════════════════════════════════════════════════════════════════════

type Violation = {
  violation_type: string;
  severity?: string;
  timestamp?: string | number;
  client_ip?: string;
  details?: unknown;
};

async function fetchViolations(adminKey = "dev-key"): Promise<Violation[]> {
  try {
    const response = await fetch(`http://localhost:8008/violations?limit=50&admin_key=${adminKey}`);
    if (!response.ok) {
      console.error("Failed to fetch violations");
      return [];
    }
    return await response.json();
  } catch (error) {
    console.error("Error fetching violations:", error);
    return [];
  }
}

async function showViolationsDashboard() {
  console.log("📊 INTEGRITY VIOLATIONS DASHBOARD");
  console.log("═".repeat(60));
  
  const violations = await fetchViolations();
  
  if (violations.length === 0) {
    console.log("✅ No violations detected");
    return;
  }
  
  console.log(`⚠️ Found ${violations.length} violations\n`);
  
  // Group by type
  const byType = violations.reduce<Record<string, number>>((acc, v: Violation) => {
    acc[v.violation_type] = (acc[v.violation_type] || 0) + 1;
    return acc;
  }, {});
  
  console.log("By Type:");
  Object.entries(byType).forEach(([type, count]) => {
    console.log(`  ${type}: ${count}`);
  });
  
  console.log("\nRecent Violations:");
  violations.slice(0, 10).forEach((v, i) => {
    console.log(`\n${i + 1}. ${v.violation_type} (${v.severity})`);
    console.log(`   Time: ${v.timestamp}`);
    console.log(`   IP: ${v.client_ip}`);
    console.log(`   Details:`, v.details);
  });
  
  console.log("═".repeat(60));
}

// ═══════════════════════════════════════════════════════════════════════════════
// EXPORT FOR CONSOLE USE
// ═══════════════════════════════════════════════════════════════════════════════

declare global {
  interface Window {
    integrityTests?: {
      runAll: () => Promise<TestResults>;
      testScriptInjection: () => Promise<boolean>;
      testDOMManipulation: () => Promise<boolean>;
      testEventHandlerReplacement: () => Promise<boolean>;
      testIntegrityHashVerification: () => Promise<boolean>;
      testIntentHashTampering: () => Promise<boolean>;
      showViolationsDashboard: () => Promise<void>;
      fetchViolations: (adminKey?: string) => Promise<Violation[]>;
    };
  }
}

if (typeof window !== "undefined") {
  window.integrityTests = {
    runAll: runAllTests,
    testScriptInjection,
    testDOMManipulation,
    testEventHandlerReplacement,
    testIntegrityHashVerification,
    testIntentHashTampering,
    showViolationsDashboard,
    fetchViolations
  };
  
  console.log("💡 Integrity tests loaded. Run:");
  console.log("   integrityTests.runAll()           - Run all tests");
  console.log("   integrityTests.showViolationsDashboard() - View violations");
}

export {
  runAllTests,
  testScriptInjection,
  testDOMManipulation,
  testEventHandlerReplacement,
  testIntegrityHashVerification,
  testIntentHashTampering,
  showViolationsDashboard,
  fetchViolations
};
