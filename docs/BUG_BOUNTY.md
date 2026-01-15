# AMTTP Bug Bounty Program

## Overview

The AMTTP bug bounty program rewards responsible disclosure of security vulnerabilities in the AMTTP protocol, smart contracts, SDK, and backend services.

## Program Status

**Status: ACTIVE**  
**Launch Date: 2025**  
**Platform: Self-hosted + Immunefi (pending)**

## Scope

### In Scope

#### Smart Contracts (Critical Priority)
- `AMTTPCoreSecure.sol` - Core swap logic with security features
- `AMTTPNFT.sol` - NFT minting and ownership
- `AMTTPRouter.sol` - Routing and transaction management  
- `AMTTPPolicyEngine.sol` - Policy rule enforcement
- `AMTTPDisputeResolver.sol` - Kleros dispute integration
- `AMTTPCrossChain.sol` - LayerZero bridge integration

#### Backend Services (High Priority)
- Oracle scoring service (`/api/score`, `/api/validate`)
- Risk assessment endpoints
- KYC integration (Sumsub, Yoti)
- HSM signing operations

#### Client SDK (Medium Priority)
- `@amttp/client-sdk` npm package
- Transaction building and signing
- MEV protection features

### Out of Scope

- Denial of service (DoS) via spamming
- Social engineering attacks
- Physical attacks
- Third-party dependencies (unless leading to AMTTP compromise)
- Issues already reported or known
- Theoretical vulnerabilities without proof of concept
- Frontend UI/UX issues (unless security-related)

## Rewards

Severity is determined by the impact and exploitability:

| Severity | Example Impact | Reward (USD) |
|----------|---------------|--------------|
| Critical | Direct loss of funds, contract upgrade takeover, oracle key compromise, complete bypass of risk controls | $10,000 - $50,000 |
| High     | Unauthorized access to admin functions, partial bypass of risk controls, data manipulation | $2,000 - $10,000 |
| Medium   | Information leakage, partial bypass, minor financial impact, DoS of non-critical services | $500 - $2,000 |
| Low      | Minor bugs, best practice violations, informational issues | $100 - $500 |

### Bonus Multipliers

- First valid critical finding: +50%
- Working exploit code: +25%
- Detailed remediation suggestion: +10%

## How to Report

### Email Submission (Preferred)
- **Email**: security@amttp.org
- **PGP Key**: See `SECURITY_PGP.asc` in repository root (or fetch from keys.openpgp.org)
- **Response SLA**: 24 hours acknowledgment, 7 days initial assessment

### Required Information

1. **Vulnerability Description**: Clear explanation of the issue
2. **Affected Component**: Contract name, function, or service endpoint
3. **Steps to Reproduce**: Detailed reproduction steps
4. **Impact Assessment**: What can an attacker achieve?
5. **Proof of Concept**: Code or transaction demonstrating the issue
6. **Suggested Fix**: Optional but appreciated

### Submission Template

```markdown
## Summary
[One paragraph description]

## Severity
[Critical/High/Medium/Low]

## Affected Component
[Contract/Service/SDK name and version]

## Description
[Detailed technical description]

## Steps to Reproduce
1. 
2. 
3. 

## Impact
[What can an attacker achieve with this vulnerability?]

## Proof of Concept
[Code, transactions, or screenshots]

## Suggested Remediation
[Optional: How would you fix this?]
```

## Rules

### Do's
- Report vulnerabilities promptly and privately
- Provide clear reproduction steps
- Allow reasonable time for fixes (90 days for critical, 180 days for others)
- Verify your findings before reporting

### Don'ts
- Do not exploit vulnerabilities beyond proof of concept
- Do not publicly disclose before fix/acknowledgment
- No automated scanning or spamming production systems
- No testing on mainnet with real user funds
- No social engineering of AMTTP team members

## Safe Harbor

The AMTTP team commits to:

- **No Legal Action**: Good faith research and reporting will not be prosecuted
- **No Retaliation**: We will not terminate accounts or access for researchers
- **Coordination**: We will work with you on disclosure timeline
- **Credit**: With your permission, we'll credit you in the fix announcement

## Response Timeline

| Phase | Timeline |
|-------|----------|
| Acknowledgment | 24 hours |
| Initial Assessment | 7 days |
| Severity Confirmation | 14 days |
| Fix Development | 30-90 days (based on severity) |
| Reward Payment | 14 days after fix deployment |
| Public Disclosure | 90 days after report (negotiable) |

## Hall of Fame

Top researchers who help secure AMTTP will be recognized here (opt-in):

| Researcher | Finding | Date |
|------------|---------|------|
| *Your name here* | *First contributor pending* | - |

## Contact

- **Security Reports**: security@amttp.org
- **General Inquiries**: hello@amttp.org
- **PGP Fingerprint**: TBD (generate with `gpg --gen-key`)

---

For implementation details and security architecture, see:
- [SECURITY_REQUIREMENTS.md](SECURITY_REQUIREMENTS.md) - Full security checklist
- [AUDIT_PACKAGE.md](AUDIT_PACKAGE.md) - Audit preparation materials
- [FORMAL_VERIFICATION.md](FORMAL_VERIFICATION.md) - Formal verification status
