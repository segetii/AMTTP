#!/bin/bash
# ============================================
# AMTTP Smart Contract Audit Runner
# ============================================
# This script runs all security audit tools on AMTTP contracts
# 
# Usage: ./run-audit.sh [options]
# Options:
#   --slither    Run Slither static analysis only
#   --foundry    Run Foundry tests only
#   --echidna    Run Echidna fuzzing only
#   --mythril    Run Mythril analysis only
#   --all        Run all tools (default)
#   --report     Generate combined report

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ROOT=$(pwd)
CONTRACTS_DIR="$PROJECT_ROOT/contracts"
AUDIT_DIR="$PROJECT_ROOT/audit"
TEST_DIR="$PROJECT_ROOT/test/audit"
REPORTS_DIR="$PROJECT_ROOT/reports/audit"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create reports directory
mkdir -p "$REPORTS_DIR"
mkdir -p "$REPORTS_DIR/$TIMESTAMP"

# ============================================
# LOGGING FUNCTIONS
# ============================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ============================================
# TOOL CHECK FUNCTIONS
# ============================================

check_slither() {
    if command -v slither &> /dev/null; then
        log_success "Slither is installed"
        return 0
    else
        log_warning "Slither not found. Install with: pip install slither-analyzer"
        return 1
    fi
}

check_forge() {
    if command -v forge &> /dev/null; then
        log_success "Foundry (forge) is installed"
        return 0
    else
        log_warning "Foundry not found. Install with: curl -L https://foundry.paradigm.xyz | bash"
        return 1
    fi
}

check_echidna() {
    if command -v echidna-test &> /dev/null; then
        log_success "Echidna is installed"
        return 0
    else
        log_warning "Echidna not found. Install from: https://github.com/crytic/echidna"
        return 1
    fi
}

check_mythril() {
    if command -v myth &> /dev/null; then
        log_success "Mythril is installed"
        return 0
    else
        log_warning "Mythril not found. Install with: pip install mythril"
        return 1
    fi
}

# ============================================
# SLITHER ANALYSIS
# ============================================

run_slither() {
    log_info "Running Slither static analysis..."
    
    if ! check_slither; then
        return 1
    fi
    
    SLITHER_REPORT="$REPORTS_DIR/$TIMESTAMP/slither-report.json"
    SLITHER_TEXT="$REPORTS_DIR/$TIMESTAMP/slither-report.txt"
    
    # Run Slither with configuration
    slither "$CONTRACTS_DIR" \
        --config-file "$AUDIT_DIR/slither.config.json" \
        --json "$SLITHER_REPORT" \
        2>&1 | tee "$SLITHER_TEXT"
    
    # Parse results
    if [ -f "$SLITHER_REPORT" ]; then
        HIGH_COUNT=$(jq '[.results.detectors[] | select(.impact == "High")] | length' "$SLITHER_REPORT" 2>/dev/null || echo "0")
        MEDIUM_COUNT=$(jq '[.results.detectors[] | select(.impact == "Medium")] | length' "$SLITHER_REPORT" 2>/dev/null || echo "0")
        LOW_COUNT=$(jq '[.results.detectors[] | select(.impact == "Low")] | length' "$SLITHER_REPORT" 2>/dev/null || echo "0")
        
        log_info "Slither Results:"
        log_info "  High: $HIGH_COUNT"
        log_info "  Medium: $MEDIUM_COUNT"
        log_info "  Low: $LOW_COUNT"
        
        if [ "$HIGH_COUNT" -gt 0 ]; then
            log_error "High severity issues found!"
        else
            log_success "No high severity issues found"
        fi
    fi
    
    log_success "Slither report saved to $SLITHER_REPORT"
}

# ============================================
# FOUNDRY TESTS
# ============================================

run_foundry() {
    log_info "Running Foundry audit tests..."
    
    if ! check_forge; then
        return 1
    fi
    
    FORGE_REPORT="$REPORTS_DIR/$TIMESTAMP/foundry-report.txt"
    GAS_REPORT="$REPORTS_DIR/$TIMESTAMP/gas-report.txt"
    
    # Run audit tests
    log_info "Running security tests..."
    forge test \
        --match-path "test/audit/*.sol" \
        -vvv \
        --gas-report \
        2>&1 | tee "$FORGE_REPORT"
    
    # Run invariant tests
    log_info "Running invariant tests..."
    forge test \
        --match-contract "Invariant" \
        -vvv \
        2>&1 | tee -a "$FORGE_REPORT"
    
    # Run fuzz tests
    log_info "Running fuzz tests (1000 runs)..."
    forge test \
        --match-path "test/audit/*.sol" \
        --fuzz-runs 1000 \
        -vv \
        2>&1 | tee -a "$FORGE_REPORT"
    
    # Generate gas report
    forge test \
        --match-path "test/audit/*.sol" \
        --gas-report \
        > "$GAS_REPORT" 2>&1
    
    log_success "Foundry report saved to $FORGE_REPORT"
}

# ============================================
# ECHIDNA FUZZING
# ============================================

run_echidna() {
    log_info "Running Echidna property-based fuzzing..."
    
    if ! check_echidna; then
        return 1
    fi
    
    ECHIDNA_REPORT="$REPORTS_DIR/$TIMESTAMP/echidna-report.txt"
    
    # Run Echidna with configuration
    echidna-test \
        "$TEST_DIR/Invariants.sol" \
        --contract AMTTPInvariants \
        --config "$AUDIT_DIR/echidna.yaml" \
        2>&1 | tee "$ECHIDNA_REPORT"
    
    # Run cross-chain invariants
    echidna-test \
        "$TEST_DIR/Invariants.sol" \
        --contract CrossChainInvariants \
        --config "$AUDIT_DIR/echidna.yaml" \
        2>&1 | tee -a "$ECHIDNA_REPORT"
    
    # Run dispute invariants
    echidna-test \
        "$TEST_DIR/Invariants.sol" \
        --contract DisputeInvariants \
        --config "$AUDIT_DIR/echidna.yaml" \
        2>&1 | tee -a "$ECHIDNA_REPORT"
    
    log_success "Echidna report saved to $ECHIDNA_REPORT"
}

# ============================================
# MYTHRIL ANALYSIS
# ============================================

run_mythril() {
    log_info "Running Mythril symbolic execution..."
    
    if ! check_mythril; then
        return 1
    fi
    
    MYTHRIL_REPORT="$REPORTS_DIR/$TIMESTAMP/mythril-report.json"
    MYTHRIL_TEXT="$REPORTS_DIR/$TIMESTAMP/mythril-report.txt"
    
    # Core contracts to analyze
    CONTRACTS=(
        "AMTTPCore.sol"
        "AMTTPRouter.sol"
        "AMTTPPolicyEngine.sol"
        "AMTTPCrossChain.sol"
        "AMTTPSafeModule.sol"
        "AMTTPDisputeResolver.sol"
    )
    
    for CONTRACT in "${CONTRACTS[@]}"; do
        log_info "Analyzing $CONTRACT..."
        
        myth analyze \
            "$CONTRACTS_DIR/$CONTRACT" \
            --solc-json "$PROJECT_ROOT/mythril.json" \
            --execution-timeout 300 \
            --max-depth 50 \
            -o json \
            >> "$MYTHRIL_REPORT" 2>&1 || true
        
        myth analyze \
            "$CONTRACTS_DIR/$CONTRACT" \
            --solc-json "$PROJECT_ROOT/mythril.json" \
            --execution-timeout 300 \
            --max-depth 50 \
            >> "$MYTHRIL_TEXT" 2>&1 || true
    done
    
    log_success "Mythril report saved to $MYTHRIL_REPORT"
}

# ============================================
# COMBINED REPORT
# ============================================

generate_report() {
    log_info "Generating combined audit report..."
    
    COMBINED_REPORT="$REPORTS_DIR/$TIMESTAMP/AUDIT_SUMMARY.md"
    
    cat > "$COMBINED_REPORT" << EOF
# AMTTP Smart Contract Audit Report

**Generated:** $(date)
**Project:** AMTTP (Anti-Money Laundering Transaction Trust Protocol)
**Report ID:** $TIMESTAMP

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

## Tool Results

### Slither Analysis
$(if [ -f "$REPORTS_DIR/$TIMESTAMP/slither-report.txt" ]; then
    echo '```'
    head -100 "$REPORTS_DIR/$TIMESTAMP/slither-report.txt"
    echo '```'
else
    echo "Not run"
fi)

### Foundry Tests
$(if [ -f "$REPORTS_DIR/$TIMESTAMP/foundry-report.txt" ]; then
    echo '```'
    grep -E "(PASS|FAIL|Test result)" "$REPORTS_DIR/$TIMESTAMP/foundry-report.txt" | head -50
    echo '```'
else
    echo "Not run"
fi)

### Echidna Fuzzing
$(if [ -f "$REPORTS_DIR/$TIMESTAMP/echidna-report.txt" ]; then
    echo '```'
    grep -E "(passed|failed|fuzzing)" "$REPORTS_DIR/$TIMESTAMP/echidna-report.txt" | head -50
    echo '```'
else
    echo "Not run"
fi)

### Mythril Analysis
$(if [ -f "$REPORTS_DIR/$TIMESTAMP/mythril-report.txt" ]; then
    echo '```'
    head -100 "$REPORTS_DIR/$TIMESTAMP/mythril-report.txt"
    echo '```'
else
    echo "Not run"
fi)

## Recommendations

1. Review all high-severity findings immediately
2. Address medium-severity findings before deployment
3. Document and justify any accepted low-severity findings
4. Re-run audit after fixes are implemented

## Files

- Slither: slither-report.json, slither-report.txt
- Foundry: foundry-report.txt, gas-report.txt
- Echidna: echidna-report.txt
- Mythril: mythril-report.json, mythril-report.txt

---
Generated by AMTTP Audit Runner
EOF

    log_success "Combined report saved to $COMBINED_REPORT"
}

# ============================================
# MAIN EXECUTION
# ============================================

print_banner() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║         AMTTP Smart Contract Audit Runner                ║"
    echo "║                                                          ║"
    echo "║  Tools: Slither | Foundry | Echidna | Mythril            ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo ""
}

main() {
    print_banner
    
    # Parse arguments
    RUN_SLITHER=false
    RUN_FOUNDRY=false
    RUN_ECHIDNA=false
    RUN_MYTHRIL=false
    RUN_ALL=true
    GEN_REPORT=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --slither)
                RUN_SLITHER=true
                RUN_ALL=false
                shift
                ;;
            --foundry)
                RUN_FOUNDRY=true
                RUN_ALL=false
                shift
                ;;
            --echidna)
                RUN_ECHIDNA=true
                RUN_ALL=false
                shift
                ;;
            --mythril)
                RUN_MYTHRIL=true
                RUN_ALL=false
                shift
                ;;
            --all)
                RUN_ALL=true
                shift
                ;;
            --report)
                GEN_REPORT=true
                shift
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    log_info "Audit started at $(date)"
    log_info "Report directory: $REPORTS_DIR/$TIMESTAMP"
    
    # Run selected tools
    if [ "$RUN_ALL" = true ] || [ "$RUN_SLITHER" = true ]; then
        run_slither || log_warning "Slither analysis had issues"
    fi
    
    if [ "$RUN_ALL" = true ] || [ "$RUN_FOUNDRY" = true ]; then
        run_foundry || log_warning "Foundry tests had issues"
    fi
    
    if [ "$RUN_ALL" = true ] || [ "$RUN_ECHIDNA" = true ]; then
        run_echidna || log_warning "Echidna fuzzing had issues"
    fi
    
    if [ "$RUN_ALL" = true ] || [ "$RUN_MYTHRIL" = true ]; then
        run_mythril || log_warning "Mythril analysis had issues"
    fi
    
    # Generate combined report
    if [ "$RUN_ALL" = true ] || [ "$GEN_REPORT" = true ]; then
        generate_report
    fi
    
    log_info "Audit completed at $(date)"
    log_success "All reports saved to: $REPORTS_DIR/$TIMESTAMP"
}

main "$@"
