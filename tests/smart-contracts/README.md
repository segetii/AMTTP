# Smart Contract Tests

## Hardhat Tests (8 suites)

Run all:
```bash
npx hardhat test
```

Run individually:
```bash
npx hardhat test test/AMTTP1.test.mjs              # Core: oracle, escrow, threshold sigs
npx hardhat test test/AMTTPDisputeResolver.test.mjs # Kleros arbitration
npx hardhat test test/AMTTPPolicyEngine.test.mjs    # Policy rules & thresholds
npx hardhat test test/AMTTPRiskRouter.test.cjs      # Multi-chain routing
npx hardhat test test/GasAnalysis.test.mjs          # Gas benchmarks → Table X
npx hardhat test test/ZkNAFVerifierRouter.test.mjs  # zkNAF proof verification
```

## Foundry Fuzz Tests (3 suites)

```bash
forge test --match-path test/foundry/*.sol -vvv
```

- `AMTTPCore.fuzz.t.sol` — Property-based invariant testing of core contract
- `AMTTPPolicyEngine.fuzz.t.sol` — Fuzz testing policy engine edge cases
- `AMTTPzkNAF.t.sol` — Groth16 verifier boundary conditions
