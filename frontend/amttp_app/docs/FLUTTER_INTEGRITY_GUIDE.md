# Flutter UI Integrity Protection

**Cross-Platform Anti-Bybit Security** - Protecting iOS, Android, Web, and Desktop

---

## 📱 Overview

This document describes the Flutter implementation of UI integrity protection, preventing Bybit-style UI manipulation attacks on mobile and desktop applications.

### Key Features

- ✅ **5-Layer Protection** - Same security as Next.js web app
- ✅ **Cross-Platform** - Works on iOS, Android, Web, Desktop
- ✅ **Lightweight** - Only `crypto` package dependency
- ✅ **Intent-Based Signing** - Users sign actual data, not UI display
- ✅ **Server Verification** - Backend validates all transactions

---

## 🏗️ Architecture

### Files Created

```
amttp_app/
├── lib/
│   ├── core/
│   │   ├── security/
│   │   │   └── ui_integrity_service.dart      # Core integrity service (450 lines)
│   │   └── services/
│   │       └── api_service.dart                # Added integrity API methods
│   ├── features/
│   │   └── transfer/
│   │       └── pages/
│   │           └── transfer_page.dart          # Updated with protection badge
│   └── shared/
│       └── widgets/
│           └── secure_transfer_protected_widget.dart  # Protected payment flow (950 lines)
└── test/
    └── ui_integrity_test.dart                  # Comprehensive tests (520 lines)
```

### 5 Protection Layers (Flutter)

| Layer | Implementation | Attack Prevention |
|-------|----------------|-------------------|
| **1. Widget Hashing** | `captureComponentIntegrity()` | Detects UI tampering |
| **2. Intent Signing** | `createTransactionIntent()` | Signs actual data, not display |
| **3. State Validation** | `validateIntegrity()` | Real-time integrity checks |
| **4. Server Verification** | `evaluateWithIntegrity()` API | Backend validates hashes |
| **5. Visual Confirmation** | Verified detail widgets | User sees hash-verified data |

---

## 🚀 Usage

### Basic Implementation

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:amttp_app/core/security/ui_integrity_service.dart';
import 'package:amttp_app/shared/widgets/secure_transfer_protected_widget.dart';

class MyTransferPage extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Secure Transfer')),
      body: SecureTransferWidget(),  // ✅ Already protected!
    );
  }
}
```

### Custom Protected Widget

```dart
class MyCustomWidget extends StatefulWidget with IntegrityProtectedWidget {
  @override
  String get componentId => 'MyCustomWidget';
  
  @override
  State<MyCustomWidget> createState() => _MyCustomWidgetState();
}

class _MyCustomWidgetState extends State<MyCustomWidget>
    with IntegrityProtectedState<MyCustomWidget> {
  
  final _amountController = TextEditingController();
  
  void _handleSubmit() {
    // Validate integrity before submission
    validateIntegrity(
      componentId: 'MyCustomWidget',
      state: {'amount': _amountController.text},
      handlers: ['onSubmit', 'onCancel'],
    );
    
    if (hasCriticalViolations) {
      // ⛔ BLOCK - integrity compromised
      _showSecurityAlert();
      return;
    }
    
    // ✅ SAFE - proceed with transaction
    _submitTransaction();
  }
  
  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        TextField(controller: _amountController),
        ElevatedButton(
          onPressed: _handleSubmit,
          child: Text('Submit'),
        ),
      ],
    );
  }
}
```

---

## 🔐 Protection Flow

### Stage 1: Input & Capture

```dart
// User enters transaction details
final integrity = UIIntegrityService.captureComponentIntegrity(
  componentId: 'SecureTransfer',
  state: {
    'amount': '1.5',
    'recipient': '0x8ba1f109551bD432803012645Ac136ddd64DBA72',
  },
  handlers: ['onSubmit', 'onCancel'],
);

// Store initial snapshot
_initialIntegrity = integrity;
```

### Stage 2: Intent Creation

```dart
// Create transaction intent (canonical representation)
final intent = UIIntegrityService.createTransactionIntent(
  from: walletAddress,
  to: recipientAddress,
  amount: amountInEth,
  currency: 'ETH',
  memo: 'Payment for services',
);

// Get hash for signing
final intentHash = intent.getIntentHash();
// Returns: 0x3a5b7c... (64 characters)
```

### Stage 3: Integrity Validation

```dart
// Compare current state against trusted snapshot
final violations = UIIntegrityService.validateIntegrity(
  current: currentIntegrity,
  trusted: _initialIntegrity,
);

// Check for critical violations
if (violations.any((v) => v.severity == ViolationSeverity.critical)) {
  // ⛔ BLOCK transaction
  throw SecurityException('UI integrity compromised');
}
```

### Stage 4: Server Verification

```dart
// Send to orchestrator with integrity report
final apiService = ref.read(apiServiceProvider);
final result = await apiService.evaluateWithIntegrity(
  address: walletAddress,
  amount: amount,
  destination: recipient,
  profile: userProfile,
  intentHash: intentHash,
  integrityReport: integrityReport.toJson(),
);

if (result.action == 'BLOCK') {
  // ⛔ Compliance or integrity failure
  _showBlockMessage(result.reason);
  return;
}
```

### Stage 5: Visual Confirmation

```dart
// Display hash-verified transaction details
Widget _buildVerifiedDetail(String label, String value) {
  return Container(
    decoration: BoxDecoration(
      border: Border.all(color: Colors.green),
    ),
    child: Row(
      children: [
        Icon(Icons.verified, color: Colors.green),
        Column(
          children: [
            Text(label),
            Text(value, style: TextStyle(fontWeight: FontWeight.bold)),
          ],
        ),
      ],
    ),
  );
}
```

---

## 🧪 Testing

### Run Tests

```bash
cd amttp_app
flutter test test/ui_integrity_test.dart
```

### Test Coverage

The test suite covers:

1. **Hash Consistency** - Same input = same hash
2. **State Detection** - Different input = different hash
3. **Handler Detection** - Injected handlers detected
4. **Timestamp Validation** - Stale snapshots flagged
5. **Intent Tampering** - Modified amounts/recipients blocked
6. **Attack Scenarios**:
   - Amount manipulation (Bybit-style)
   - Handler injection
   - Recipient substitution
   - Stale UI replay

### Sample Test Output

```
✓ calculateHash produces consistent SHA-256 (12ms)
✓ captureComponentIntegrity creates valid snapshot (8ms)
✓ getIntentHash changes when amount changes (5ms)
✓ validateIntegrity detects handler hash mismatch (15ms)
✓ Scenario 1: Amount manipulation attack (Bybit-style) (6ms)
✓ Scenario 2: Handler injection attack (9ms)
✓ Scenario 3: Recipient address substitution (7ms)
✓ Scenario 4: Stale UI attack (replay old page) (5ms)

All tests passed! (28 passed, 0 failed)
```

---

## 🔍 Attack Detection

### How Attacks Are Blocked

| Attack Vector | Detection Method | Response |
|---------------|------------------|----------|
| **Amount Change** | Intent hash mismatch | Transaction blocked |
| **Recipient Change** | Intent hash mismatch | Transaction blocked |
| **Handler Injection** | Handler hash mismatch | Critical alert |
| **DOM Manipulation** | State hash mismatch | Warning + review |
| **Stale UI** | Timestamp > 60s | Refresh required |

### Example: Amount Manipulation Attack

```dart
// Attacker tries to display "Send 1 ETH" but actually send 100 ETH

// 1. User creates intent for 1 ETH
final userIntent = TransactionIntent(
  from: wallet,
  to: recipient,
  amount: '1.0',
);
final userHash = userIntent.getIntentHash();
// userHash = 0x3a5b7c...

// 2. Attacker modifies amount to 100 ETH
final attackIntent = TransactionIntent(
  from: wallet,
  to: recipient,
  amount: '100.0',  // ⚠️ MODIFIED
);

// 3. Server validates
final verified = UIIntegrityService.verifyIntentHash(
  intent: attackIntent,
  expectedHash: userHash,
);
// verified = false ❌

// 4. Transaction BLOCKED
if (!verified) {
  throw SecurityException('Intent hash mismatch - possible attack');
}
```

---

## 📊 API Integration

### Backend Endpoints

The Flutter app connects to two endpoints:

#### 1. Integrity Verification (Port 8008)

```dart
POST http://127.0.0.1:8008/verify-integrity
Content-Type: application/json

{
  "componentId": "SecureTransfer",
  "stateHash": "abc123...",
  "handlerHash": "def456...",
  "timestamp": "2026-01-08T12:00:00Z",
  "violations": []
}

Response:
{
  "verified": true,
  "trusted": true,
  "reason": null
}
```

#### 2. Compliance with Integrity (Port 8007)

```dart
POST http://127.0.0.1:8007/evaluate-with-integrity
Content-Type: application/json

{
  "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
  "amount": "1.5",
  "destination": "0x8ba1f109551bD432803012645Ac136ddd64DBA72",
  "profile": "retail_user",
  "intent_hash": "0x3a5b7c...",
  "integrity_report": { ... },
  "metadata": {}
}

Response:
{
  "action": "ALLOW",
  "reason": "Transaction approved",
  "risk_score": 0.25,
  "warnings": [],
  "integrity_verified": true
}
```

---

## 🎨 UI Components

### Security Indicator Badge

```dart
// Shows in app bar when protection is active
Container(
  padding: EdgeInsets.symmetric(horizontal: 8, vertical: 4),
  decoration: BoxDecoration(
    color: Colors.green.withOpacity(0.2),
    borderRadius: BorderRadius.circular(12),
    border: Border.all(color: Colors.green),
  ),
  child: Row(
    children: [
      Icon(Icons.verified_user, color: Colors.green, size: 14),
      SizedBox(width: 4),
      Text('Protected', style: TextStyle(color: Colors.green)),
    ],
  ),
)
```

### Verified Detail Row

```dart
// Shows hash-verified transaction details
Container(
  decoration: BoxDecoration(
    color: Colors.green.withOpacity(0.05),
    border: Border.all(color: Colors.green.withOpacity(0.2)),
    borderRadius: BorderRadius.circular(8),
  ),
  child: Row(
    children: [
      Icon(Icons.verified, color: Colors.green),
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Amount', style: TextStyle(color: Colors.grey)),
          Text('1.5 ETH', style: TextStyle(fontWeight: FontWeight.bold)),
        ],
      ),
    ],
  ),
)
```

---

## 🔧 Configuration

### App Constants

Update `lib/core/constants/app_constants.dart`:

```dart
class AppConstants {
  // API Endpoints
  static const String baseApiUrl = 'http://127.0.0.1:8007';
  static const String integrityServiceUrl = 'http://127.0.0.1:8008';
  
  // Security
  static const int integrityTimeoutSeconds = 60;
  static const int maxIntegrityViolations = 3;
  
  // UI
  static const String appName = 'AMTTP Secure';
}
```

### Production URLs

For production deployment, update to HTTPS:

```dart
// Production
static const String baseApiUrl = 'https://api.amttp.com';
static const String integrityServiceUrl = 'https://integrity.amttp.com';
```

---

## 📦 Dependencies

### pubspec.yaml

```yaml
dependencies:
  flutter:
    sdk: flutter
  
  # Existing
  flutter_riverpod: ^2.4.0
  dio: ^5.3.0
  
  # For integrity protection (already included)
  crypto: ^3.0.3  # SHA-256 hashing
```

No additional dependencies required! ✨

---

## 🚢 Deployment

### iOS Deployment

```bash
cd amttp_app
flutter build ios --release
```

### Android Deployment

```bash
cd amttp_app
flutter build apk --release
```

### Web Deployment

```bash
cd amttp_app
flutter build web --release
```

### Desktop Deployment

```bash
# Windows
flutter build windows --release

# macOS
flutter build macos --release

# Linux
flutter build linux --release
```

---

## 🔒 Security Best Practices

### 1. Always Validate Before Signing

```dart
// ❌ BAD - Sign without validation
await signTransaction(amount);

// ✅ GOOD - Validate integrity first
if (!await _validateIntegrity()) {
  throw SecurityException('Integrity check failed');
}
await signTransaction(amount);
```

### 2. Use Intent Hashing

```dart
// ❌ BAD - Sign UI display value
final signature = await sign(_amountController.text);

// ✅ GOOD - Sign transaction intent hash
final intent = createTransactionIntent(...);
final intentHash = intent.getIntentHash();
final signature = await sign(intentHash);
```

### 3. Show Verified Data

```dart
// ❌ BAD - Show raw form values
Text('Amount: ${_amountController.text}');

// ✅ GOOD - Show hash-verified intent
Text('Amount: ${_intent.amount} ${_intent.currency}');
_buildVerifiedDetail('Amount', '${_intent.amount} ETH');
```

### 4. Handle Violations

```dart
if (hasCriticalViolations) {
  // Log for investigation
  logger.critical('UI integrity violation detected', {
    'violations': violations,
    'timestamp': DateTime.now(),
  });
  
  // Alert user
  showDialog(
    context: context,
    barrierDismissible: false,
    builder: (context) => AlertDialog(
      title: Text('Security Alert'),
      content: Text('UI integrity violation detected. Transaction blocked.'),
    ),
  );
  
  // BLOCK transaction
  return;
}
```

---

## 🐛 Troubleshooting

### Issue: "Integrity verification failed"

**Cause:** Hash mismatch between client and server

**Solution:**
```dart
// 1. Check server is running
curl http://127.0.0.1:8008/health

// 2. Verify timestamp is recent
print('Snapshot age: ${DateTime.now().difference(integrity.timestamp)}');

// 3. Regenerate integrity snapshot
resetTrustedSnapshot(
  componentId: 'SecureTransfer',
  state: getCurrentState(),
  handlers: ['onSubmit', 'onCancel'],
);
```

### Issue: "Intent hash mismatch"

**Cause:** Transaction data changed between creation and signing

**Solution:**
```dart
// Recreate intent immediately before signing
final intent = createTransactionIntent(
  from: wallet.address,
  to: _recipientController.text,
  amount: _amountController.text,
);
final intentHash = intent.getIntentHash();

// Sign immediately (don't delay)
final signature = await signIntent(intentHash);
```

### Issue: Tests failing

**Cause:** Timestamp-sensitive tests

**Solution:**
```dart
// Use fixed timestamps in tests
final fixedTime = DateTime(2026, 1, 1, 12, 0, 0);
final intent = TransactionIntent(
  from: '0x...',
  to: '0x...',
  amount: '1.0',
  timestamp: fixedTime,  // ✅ Deterministic
);
```

---

## 📚 Additional Resources

- [UI Integrity Guide](../../../docs/UI_INTEGRITY_GUIDE.md) - Complete security documentation
- [Production Runbook](../../../docs/PRODUCTION_RUNBOOK.md) - Deployment procedures
- [Architecture Diagram](../../../ARCHITECTURE_DIAGRAM.md) - System overview

---

**Security Contact:** security@amttp.com  
**Version:** 1.0.0  
**Last Updated:** January 2026
