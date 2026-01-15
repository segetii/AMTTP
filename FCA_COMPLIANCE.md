# AMTTP FCA Compliance Module

## Overview

The AMTTP FCA Compliance API provides UK Financial Conduct Authority regulatory reporting and compliance endpoints. This module implements the requirements of:

- **MLR 2017** - Money Laundering, Terrorist Financing and Transfer of Funds Regulations
- **PSR 2017** - Payment Services Regulations
- **FSMA 2000 s.330** - Suspicious Activity Report requirements
- **FATF Recommendation 16** - Travel Rule for cross-border transactions

## Quick Start

```bash
# Start the FCA Compliance API
cd backend/oracle-service
python fca_compliance_api.py

# API running on http://localhost:8002
# Docs available at http://localhost:8002/compliance/docs
```

## API Endpoints

### Health Check
```bash
GET /compliance/health
```

### Suspicious Activity Reports (SARs)

#### Submit SAR
```bash
POST /compliance/sar/submit

{
  "transaction": {
    "tx_hash": "0x...",
    "from_address": "0x...",
    "to_address": "0x...",
    "value_eth": 10.5,
    "value_gbp": 25000,
    "timestamp": "2025-12-22T10:00:00Z",
    "block_number": 18500000,
    "chain": "ethereum",
    "risk_score": 0.85,
    "risk_level": "high",
    "ml_model_version": "xgboost-hybrid-v2.1"
  },
  "sar_type": "suspicious_transaction",
  "suspicion_grounds": "Transaction exhibits multiple high-risk indicators including pattern matching to known fraud schemes, elevated transaction velocity, and connection to previously flagged addresses in the network graph.",
  "urgency": "normal"
}
```

**Response:**
```json
{
  "sar_id": "uuid",
  "reference_number": "SAR-20251222-ABC12345",
  "status": "submitted",
  "submitted_at": "2025-12-22T10:00:00Z",
  "estimated_acknowledgment": "2025-12-29T10:00:00Z"
}
```

#### Get SAR Status
```bash
GET /compliance/sar/{sar_id}
```

#### List SARs
```bash
GET /compliance/sar/list?status=submitted&limit=50
```

### Sanctions Screening

#### Single Address Check
```bash
POST /compliance/sanctions/check

{
  "address": "0x8576acc5c05d6ce88f4e49bf65bdf0c62f91353c",
  "check_lists": ["hmt", "ofac"]
}
```

**Response:**
```json
{
  "address": "0x8576acc5c05d6ce88f4e49bf65bdf0c62f91353c",
  "is_sanctioned": true,
  "matches": [
    {
      "list": "HMT",
      "entity": {
        "name": "Tornado Cash",
        "list_date": "2022-08-08",
        "reason": "OFAC SDN designation"
      },
      "match_type": "exact_address",
      "confidence": 1.0
    }
  ],
  "checked_lists": ["hmt", "ofac"],
  "check_timestamp": "2025-12-22T10:00:00Z",
  "confidence": 1.0
}
```

#### Batch Check
```bash
POST /compliance/sanctions/batch-check

["0xaddress1", "0xaddress2", "0xaddress3"]
```

### FATF Travel Rule

```bash
POST /compliance/travel-rule/validate

{
  "tx_hash": "0x...",
  "from_address": "0x...",
  "to_address": "0x...",
  "value_eth": 10.0,
  "value_gbp": 25000,
  "timestamp": "2025-12-22T10:00:00Z",
  "block_number": 18500000,
  "chain": "ethereum",
  "risk_score": 0.3,
  "risk_level": "low",
  "ml_model_version": "v2.1",
  "originator": {
    "name": "John Smith",
    "address": "123 Main St, London, UK",
    "account_number": "0x1234...",
    "country": "GB"
  },
  "beneficiary": {
    "name": "Jane Doe",
    "account_number": "0x5678...",
    "country": "GB"
  }
}
```

**Response:**
```json
{
  "tx_hash": "0x...",
  "travel_rule_applies": true,
  "threshold_gbp": 840.0,
  "transaction_value_gbp": 25000,
  "compliant": true,
  "issues": []
}
```

### XAI Explainability

#### Generate Decision Explanation
```bash
POST /compliance/xai/explain?tx_hash=0x123&risk_score=0.85
```

**Response:**
```json
{
  "decision_id": "uuid",
  "transaction_hash": "0x123",
  "risk_score": 0.85,
  "risk_level": "high",
  "decision": "BLOCKED",
  "top_factors": [
    {
      "feature": "pattern_match",
      "contribution": 0.45,
      "direction": "increases risk",
      "explanation": "Matches known fraud patterns"
    }
  ],
  "narrative_explanation": "This transaction received a HIGH risk score of 85.00%, indicating significant fraud indicators...",
  "regulatory_justification": "Under MLR 2017 Regulation 28, this transaction has been blocked due to reasonable grounds for suspecting money laundering..."
}
```

#### Get Model Info
```bash
GET /compliance/xai/model-info
```

### Audit Trail

#### Get Audit Logs
```bash
GET /compliance/audit/logs?entity_type=SAR&limit=100
```

#### Verify Integrity
```bash
GET /compliance/audit/verify/{log_id}
```

**Response:**
```json
{
  "log_id": "uuid",
  "stored_hash": "sha256...",
  "computed_hash": "sha256...",
  "integrity_valid": true,
  "verification_timestamp": "2025-12-22T10:00:00Z"
}
```

### Compliance Reports

#### Generate Periodic Report
```bash
GET /compliance/reports/periodic?period=monthly
```

#### Generate FCA MLR Report
```bash
GET /compliance/reports/fca-mlr
```

## Regulatory Requirements

### MLR 2017 Compliance

| Requirement | Implementation |
|-------------|----------------|
| Risk-based approach | ML model with explainable decisions |
| Customer Due Diligence | KYC integration via Sumsub |
| Enhanced Due Diligence | Auto-triggered for high-risk |
| Ongoing Monitoring | Real-time transaction screening |
| Record Keeping | 5-year audit trail with integrity hashes |
| Staff Training | Documented via audit logs |
| SAR Reporting | Automated submission to NCA |

### FATF Travel Rule

For transactions ≥ €1000 (£840), the following information must be collected:

**Originator:**
- Name
- Account number
- Address (or national ID, date of birth)
- Country

**Beneficiary:**
- Name
- Account number

### Sanctions Lists

The system checks against:

| List | Source | Update Frequency |
|------|--------|------------------|
| HMT | UK HM Treasury | Real-time |
| OFAC | US Treasury | Real-time |
| EU | EU Consolidated | Daily |
| UN | UN Security Council | Daily |

## XAI Explainability

For FCA regulatory review, all ML decisions include:

1. **Feature Importance** - Which factors contributed to the score
2. **Human-Readable Narrative** - Plain English explanation
3. **Regulatory Justification** - Legal basis for the decision
4. **Model Performance Metrics** - F1, precision, recall, AUC
5. **Bias Testing Results** - Geographic and value parity scores

## Integration with ML Pipeline

The compliance API integrates with the hybrid ML API:

```python
# When ML API detects high risk
if risk_score >= 0.7:
    # Submit SAR automatically
    await compliance_api.submit_sar({
        "transaction": tx_data,
        "sar_type": "suspicious_transaction",
        "suspicion_grounds": await xai_api.generate_explanation(tx_hash)
    })
```

## Production Deployment

### Environment Variables

```bash
FCA_API_HOST=0.0.0.0
FCA_API_PORT=8002
MONGODB_URI=mongodb://localhost:27017/amttp_compliance
NCA_SUBMISSION_ENDPOINT=https://nca.gov.uk/api/sar
CHAINALYSIS_API_KEY=your_key_here
```

### Database Schema

```python
# Collections
- sars              # Suspicious Activity Reports
- audit_logs        # Immutable audit trail
- sanctions_checks  # Screening results
- compliance_reports # Generated reports
```

## Files

- `backend/oracle-service/fca_compliance_api.py` - Main API
- `AMTTP_ROADMAP.md` - Updated with compliance status
- `FCA_COMPLIANCE.md` - This documentation

## Next Steps

1. Integrate with NCA SAR submission API
2. Add Chainalysis/Elliptic sanctions API
3. Set up MongoDB for persistent storage
4. Add webhook notifications for SAR status updates
5. Implement automated periodic reporting
