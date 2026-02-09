# AMTTP zkNAF Comprehensive Test Suite
# Runs Hardhat tests, Slither analysis, and Foundry tests

Write-Host "`n"
Write-Host "=" * 70
Write-Host "  AMTTP zkNAF - Comprehensive Security Testing Suite"
Write-Host "=" * 70
Write-Host "`n"

$ErrorActionPreference = "Continue"
$results = @{}

# Test 1: Hardhat Unit Tests
Write-Host "`n--- HARDHAT UNIT TESTS ---`n" -ForegroundColor Cyan

try {
    $output = npx hardhat test test/ZkNAFVerifierRouter.test.mjs 2>&1
    Write-Host $output
    if ($LASTEXITCODE -eq 0) {
        $results["Hardhat Tests"] = "PASSED"
    } else {
        $results["Hardhat Tests"] = "FAILED"
    }
} catch {
    $results["Hardhat Tests"] = "ERROR: $_"
}

# Test 2: Slither Security Analysis
Write-Host "`n--- SLITHER SECURITY ANALYSIS ---`n" -ForegroundColor Cyan

try {
    $output = slither contracts/zknaf/ZkNAFVerifierRouter.sol --compile-force-framework hardhat --exclude-dependencies 2>&1
    Write-Host $output
    $results["Slither Analysis"] = "COMPLETED"
} catch {
    Write-Host "Slither error: $_" -ForegroundColor Yellow
    $results["Slither Analysis"] = "SKIPPED"
}

# Test 3: Contract Size Check
Write-Host "`n--- CONTRACT SIZE CHECK ---`n" -ForegroundColor Cyan

try {
    $output = npx hardhat compile --force 2>&1
    
    # Check artifacts for size
    $artifacts = @(
        "artifacts/contracts/zknaf/ZkNAFVerifierRouter.sol/ZkNAFVerifierRouter.json",
        "artifacts/contracts/zknaf/sanctions_non_membership_verifier.sol/Groth16Verifier.json",
        "artifacts/contracts/zknaf/risk_range_proof_verifier.sol/Groth16Verifier.json",
        "artifacts/contracts/zknaf/kyc_credential_verifier.sol/Groth16Verifier.json"
    )
    
    foreach ($artifact in $artifacts) {
        if (Test-Path $artifact) {
            $json = Get-Content $artifact | ConvertFrom-Json
            $bytecodeSize = ($json.bytecode.Length - 2) / 2  # Remove 0x and divide by 2
            $name = Split-Path $artifact -Leaf
            Write-Host "  $name : $bytecodeSize bytes"
            
            if ($bytecodeSize -gt 24576) {
                Write-Host "    WARNING: Exceeds EIP-170 limit (24KB)" -ForegroundColor Red
            }
        }
    }
    $results["Size Check"] = "COMPLETED"
} catch {
    $results["Size Check"] = "ERROR: $_"
}

# Test 4: Gas Analysis
Write-Host "`n--- GAS ANALYSIS ---`n" -ForegroundColor Cyan

try {
    Write-Host "Running gas estimation..."
    $output = npx hardhat run --network localhost scripts/deploy-zknaf-verifiers.cjs 2>&1
    Write-Host $output
    $results["Gas Analysis"] = "COMPLETED"
} catch {
    $results["Gas Analysis"] = "SKIPPED (no local node)"
}

# Summary
Write-Host "`n"
Write-Host "=" * 70
Write-Host "  TEST RESULTS SUMMARY"
Write-Host "=" * 70
Write-Host "`n"

foreach ($test in $results.Keys) {
    $status = $results[$test]
    if ($status -eq "PASSED" -or $status -eq "COMPLETED") {
        Write-Host "  [PASS] $test : $status" -ForegroundColor Green
    } elseif ($status -eq "SKIPPED") {
        Write-Host "  [SKIP] $test : $status" -ForegroundColor Yellow
    } else {
        Write-Host "  [FAIL] $test : $status" -ForegroundColor Red
    }
}

Write-Host "`n"
