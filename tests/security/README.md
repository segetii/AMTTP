# Security & Audit Tests

Scripts and tools for smart contract security analysis and vulnerability scanning.

| Tool / Script | What It Does |
|---|---|
| `run_security_audit.py` | Orchestrates Slither + Mythril static analysis on all Solidity contracts |
| `test_security.py` | Automated security test suite: reentrancy, access control, overflow checks |

## Related Artefacts

Full audit configuration and reports live in the top-level `audit/` directory:
- `audit/slither.config.json` — Slither configuration
- `audit/echidna.yaml` — Echidna fuzz-testing config
- `audit/SECURITY_AUDIT_REPORT.md` — Full audit findings
- `audit/AUDIT_CHECKLIST.md` — Checklist against OWASP / SWC registry
- `audit/slither_output.txt` — Latest Slither scan output
- `audit/gas-report.txt` — Gas profiling per function

## Running

```bash
# Run automated security tests
python tests/security/test_security.py

# Run full audit pipeline (requires slither-analyzer + mythril)
python tests/security/run_security_audit.py

# Or use the audit helper script
cd audit && ./run-audit.sh   # Linux/macOS
cd audit && .\run-audit.ps1  # Windows
```
