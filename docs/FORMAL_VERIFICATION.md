# AMTTP Formal Verification Guide

## Overview

This document describes how to set up and run formal verification for AMTTP smart contracts using **Certora** and **Halmos**.

---

## 1. Certora Setup

### Installation

```bash
# Install Certora CLI
pip install certora-cli

# Set API key (get from https://prover.certora.com)
export CERTORAKEY=<your-api-key>
```

### Running Verification

```bash
# Verify AMTTPCoreSecure
certoraRun contracts/AMTTPCoreSecure.sol \
  --verify AMTTPCoreSecure:spec/AMTTPCoreSecure.spec \
  --solc solc8.24 \
  --optimistic_loop \
  --rule_sanity basic
```

### Key Invariants Verified

| Invariant | Description |
|-----------|-------------|
| Swap Lifecycle | Swaps follow valid state transitions |
| Nonce Uniqueness | Each nonce can only be used once |
| Oracle Threshold | oracleThreshold ≤ oracleCount ≤ MAX_ORACLES |
| Upgrade Timelock | Upgrades cannot execute before timelock |
| Fund Conservation | Locked funds can only go to buyer or seller |

---

## 2. Halmos Setup

### Installation

```bash
# Install Halmos
pip install halmos

# Install Foundry (required)
curl -L https://foundry.paradigm.xyz | bash
foundryup
```

### Running Symbolic Tests

```bash
# Run all symbolic tests
halmos --contract AMTTPCoreSecure

# Run specific test
halmos --contract AMTTPCoreSecure --function check_swapLifecycle

# With timeout
halmos --contract AMTTPCoreSecure --solver-timeout-assertion 600
```

### Creating Symbolic Tests

Add tests to `test/symbolic/`:

```solidity
// test/symbolic/AMTTPCoreSecure.t.sol
import "forge-std/Test.sol";
import "../../contracts/AMTTPCoreSecure.sol";

contract AMTTPCoreSecureSymbolic is Test {
    AMTTPCoreSecure core;
    
    function setUp() public {
        core = new AMTTPCoreSecure();
    }
    
    function check_noDoubleComplete(bytes32 swapId, bytes32 preimage) public {
        // Assume swap exists and is approved
        vm.assume(core.swaps(swapId).status == SwapStatus.Approved);
        
        // Complete once
        core.completeSwap(swapId, preimage);
        
        // Try to complete again - should revert
        vm.expectRevert();
        core.completeSwap(swapId, preimage);
    }
}
```

---

## 3. Properties to Verify

### Critical Properties

1. **No Double Spend**
   - A swap can only be completed once
   - A swap can only be refunded once

2. **Access Control**
   - Only owner can modify oracles/approvers
   - Only oracle can submit risk scores
   - Only parties to swap can complete/refund

3. **Replay Protection**
   - Each nonce can only be used once per user
   - Signature expiry is enforced

4. **Upgrade Safety**
   - Upgrades require timelock delay
   - Upgrades require approver authorization

### Economic Properties

1. **Fund Conservation**
   - ETH in ≥ sum of pending swap amounts
   - ETH can only exit via complete/refund

2. **No Griefing**
   - Users cannot lock others' funds indefinitely
   - Timelock enables eventual refund

---

## 4. CI Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/formal-verification.yml
name: Formal Verification

on:
  push:
    branches: [main]
  pull_request:
    paths:
      - 'contracts/**'

jobs:
  certora:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Install Certora
        run: pip install certora-cli
        
      - name: Run Certora
        env:
          CERTORAKEY: ${{ secrets.CERTORA_KEY }}
        run: |
          certoraRun contracts/AMTTPCoreSecure.sol \
            --verify AMTTPCoreSecure:spec/AMTTPCoreSecure.spec

  halmos:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Install Dependencies
        run: |
          pip install halmos
          curl -L https://foundry.paradigm.xyz | bash
          ~/.foundry/bin/foundryup
          
      - name: Run Halmos
        run: halmos --contract AMTTPCoreSecure
```

---

## 5. Verification Status

| Contract | Tool | Status | Last Run |
|----------|------|--------|----------|
| AMTTPCoreSecure | Certora | ⚠️ Pending | - |
| AMTTPCoreSecure | Halmos | ⚠️ Pending | - |
| AMTTPDisputeResolver | Certora | ⚠️ Pending | - |
| AMTTPCrossChain | Certora | ⚠️ Pending | - |

---

## 6. Known Limitations

1. **Loop Unrolling**: Certora requires bounded loops; multi-oracle verification limited to MAX_ORACLES
2. **External Calls**: LayerZero interactions are mocked for verification
3. **Storage Gaps**: Upgrade safety verified manually for storage layout

---

## 7. Next Steps

1. [ ] Obtain Certora API key
2. [ ] Run initial verification
3. [ ] Fix any counterexamples found
4. [ ] Add to CI pipeline
5. [ ] Document verified properties for audit
