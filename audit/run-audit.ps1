# AMTTP Smart Contract Audit Runner (PowerShell)
# ============================================
# Usage: .\run-audit.ps1 [-Slither] [-Foundry] [-Echidna] [-Mythril] [-All] [-Report]

param(
    [switch]$Slither,
    [switch]$Foundry,
    [switch]$Echidna,
    [switch]$Mythril,
    [switch]$All,
    [switch]$Report
)

# Configuration
$ProjectRoot = Get-Location
$ContractsDir = "$ProjectRoot\contracts"
$AuditDir = "$ProjectRoot\audit"
$TestDir = "$ProjectRoot\test\audit"
$ReportsDir = "$ProjectRoot\reports\audit"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$ReportPath = "$ReportsDir\$Timestamp"

# Create directories
New-Item -ItemType Directory -Force -Path $ReportPath | Out-Null

# ============================================
# LOGGING FUNCTIONS
# ============================================

function Write-Info { param($Message) Write-Host "[INFO] $Message" -ForegroundColor Cyan }
function Write-Success { param($Message) Write-Host "[SUCCESS] $Message" -ForegroundColor Green }
function Write-Warn { param($Message) Write-Host "[WARNING] $Message" -ForegroundColor Yellow }
function Write-Err { param($Message) Write-Host "[ERROR] $Message" -ForegroundColor Red }

# ============================================
# TOOL CHECK FUNCTIONS
# ============================================

function Test-Slither {
    try {
        $null = slither --version 2>$null
        Write-Success "Slither is installed"
        return $true
    } catch {
        Write-Warn "Slither not found. Install with: pip install slither-analyzer"
        return $false
    }
}

function Test-Forge {
    try {
        $null = forge --version 2>$null
        Write-Success "Foundry (forge) is installed"
        return $true
    } catch {
        Write-Warn "Foundry not found. Install from: https://getfoundry.sh"
        return $false
    }
}

function Test-Echidna {
    try {
        $null = echidna-test --version 2>$null
        Write-Success "Echidna is installed"
        return $true
    } catch {
        Write-Warn "Echidna not found. Install from: https://github.com/crytic/echidna"
        return $false
    }
}

function Test-Mythril {
    try {
        $null = myth version 2>$null
        Write-Success "Mythril is installed"
        return $true
    } catch {
        Write-Warn "Mythril not found. Install with: pip install mythril"
        return $false
    }
}

# ============================================
# SLITHER ANALYSIS
# ============================================

function Invoke-Slither {
    Write-Info "Running Slither static analysis..."
    
    if (-not (Test-Slither)) { return }
    
    $SlitherReport = "$ReportPath\slither-report.json"
    $SlitherText = "$ReportPath\slither-report.txt"
    
    # Run Slither
    slither $ContractsDir `
        --config-file "$AuditDir\slither.config.json" `
        --json $SlitherReport 2>&1 | Tee-Object -FilePath $SlitherText
    
    Write-Success "Slither report saved to $SlitherReport"
}

# ============================================
# FOUNDRY TESTS
# ============================================

function Invoke-Foundry {
    Write-Info "Running Foundry audit tests..."
    
    if (-not (Test-Forge)) { return }
    
    $ForgeReport = "$ReportPath\foundry-report.txt"
    $GasReport = "$ReportPath\gas-report.txt"
    
    # Run audit tests
    Write-Info "Running security tests..."
    forge test `
        --match-path "test/audit/*.sol" `
        -vvv `
        --gas-report 2>&1 | Tee-Object -FilePath $ForgeReport
    
    # Run fuzz tests
    Write-Info "Running fuzz tests (1000 runs)..."
    forge test `
        --match-path "test/audit/*.sol" `
        --fuzz-runs 1000 `
        -vv 2>&1 | Tee-Object -FilePath $ForgeReport -Append
    
    # Generate gas report
    forge test `
        --match-path "test/audit/*.sol" `
        --gas-report 2>&1 | Out-File -FilePath $GasReport
    
    Write-Success "Foundry report saved to $ForgeReport"
}

# ============================================
# ECHIDNA FUZZING
# ============================================

function Invoke-Echidna {
    Write-Info "Running Echidna property-based fuzzing..."
    
    if (-not (Test-Echidna)) { return }
    
    $EchidnaReport = "$ReportPath\echidna-report.txt"
    
    # Run Echidna
    echidna-test `
        "$TestDir\Invariants.sol" `
        --contract AMTTPInvariants `
        --config "$AuditDir\echidna.yaml" 2>&1 | Tee-Object -FilePath $EchidnaReport
    
    Write-Success "Echidna report saved to $EchidnaReport"
}

# ============================================
# MYTHRIL ANALYSIS
# ============================================

function Invoke-Mythril {
    Write-Info "Running Mythril symbolic execution..."
    
    if (-not (Test-Mythril)) { return }
    
    $MythrilReport = "$ReportPath\mythril-report.txt"
    
    $Contracts = @(
        "AMTTPCore.sol",
        "AMTTPRouter.sol",
        "AMTTPPolicyEngine.sol",
        "AMTTPCrossChain.sol"
    )
    
    foreach ($Contract in $Contracts) {
        Write-Info "Analyzing $Contract..."
        myth analyze `
            "$ContractsDir\$Contract" `
            --execution-timeout 300 `
            --max-depth 50 2>&1 | Tee-Object -FilePath $MythrilReport -Append
    }
    
    Write-Success "Mythril report saved to $MythrilReport"
}

# ============================================
# COMBINED REPORT
# ============================================

function New-AuditReport {
    Write-Info "Generating combined audit report..."
    
    $CombinedReport = "$ReportPath\AUDIT_SUMMARY.md"
    
    $ReportContent = @"
# AMTTP Smart Contract Audit Report

**Generated:** $(Get-Date)
**Project:** AMTTP (Anti-Money Laundering Transaction Trust Protocol)
**Report ID:** $Timestamp

## Executive Summary

This report contains the results of automated security analysis using:
- Slither (Static Analysis)
- Foundry (Unit + Fuzz Tests)
- Echidna (Property-Based Testing)
- Mythril (Symbolic Execution)

## Contracts Analyzed

| Contract | Description |
|----------|-------------|
| AMTTPCore.sol | Core swap functionality |
| AMTTPRouter.sol | Unified routing interface |
| AMTTPPolicyEngine.sol | Risk assessment and policies |
| AMTTPCrossChain.sol | LayerZero cross-chain messaging |
| AMTTPSafeModule.sol | Gnosis Safe integration |
| AMTTPDisputeResolver.sol | Kleros dispute resolution |

## Files Generated

- slither-report.json / slither-report.txt
- foundry-report.txt / gas-report.txt
- echidna-report.txt
- mythril-report.txt

## Next Steps

1. Review all high-severity findings immediately
2. Address medium-severity findings before deployment
3. Document and justify any accepted low-severity findings
4. Re-run audit after fixes are implemented

---
Generated by AMTTP Audit Runner (PowerShell)
"@

    $ReportContent | Out-File -FilePath $CombinedReport -Encoding utf8
    Write-Success "Combined report saved to $CombinedReport"
}

# ============================================
# MAIN EXECUTION
# ============================================

function Show-Banner {
    Write-Host ""
    Write-Host "╔══════════════════════════════════════════════════════════╗" -ForegroundColor Magenta
    Write-Host "║         AMTTP Smart Contract Audit Runner                ║" -ForegroundColor Magenta
    Write-Host "║                                                          ║" -ForegroundColor Magenta
    Write-Host "║  Tools: Slither | Foundry | Echidna | Mythril            ║" -ForegroundColor Magenta
    Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Magenta
    Write-Host ""
}

# Main
Show-Banner

Write-Info "Audit started at $(Get-Date)"
Write-Info "Report directory: $ReportPath"

# Default to all if no specific tool selected
if (-not ($Slither -or $Foundry -or $Echidna -or $Mythril)) {
    $All = $true
}

# Run selected tools
if ($All -or $Slither) { Invoke-Slither }
if ($All -or $Foundry) { Invoke-Foundry }
if ($All -or $Echidna) { Invoke-Echidna }
if ($All -or $Mythril) { Invoke-Mythril }

# Generate report
if ($All -or $Report) { New-AuditReport }

Write-Info "Audit completed at $(Get-Date)"
Write-Success "All reports saved to: $ReportPath"
