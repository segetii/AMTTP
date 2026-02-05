# Flutter App Standardization Guide

## Overview

The AMTTP Flutter app has been standardized with consistent patterns, design tokens, and component libraries to ensure maintainability, scalability, and cross-platform consistency.

## Directory Structure

```
lib/
├── amttp.dart              # Main barrel export
├── main.dart               # Full app entry point
├── main_consumer.dart      # Consumer-only entry point
│
├── core/                   # Core infrastructure
│   ├── core.dart           # Core barrel export
│   ├── theme/
│   │   ├── design_tokens.dart    # Colors, radii, shadows
│   │   ├── typography.dart       # Text styles
│   │   └── spacing.dart          # Gaps and padding
│   ├── router/
│   │   ├── route_names.dart      # Centralized route definitions
│   │   ├── app_router.dart       # Full app router
│   │   └── consumer_app_router.dart  # Consumer-only router
│   ├── constants/
│   │   ├── api_endpoints.dart    # API URLs
│   │   └── feature_flags.dart    # Runtime toggles
│   ├── services/
│   │   ├── services.dart         # Services barrel
│   │   ├── api_client.dart       # HTTP client with retry/cache
│   │   ├── api_exception.dart    # Typed exceptions
│   │   └── result.dart           # Success/Failure type
│   ├── auth/                     # Authentication
│   ├── rbac/                     # Role-based access control
│   └── utils/                    # Utilities
│
├── shared/                 # Reusable components
│   ├── shared.dart         # Shared barrel export
│   ├── models/
│   │   ├── models.dart           # Models barrel
│   │   ├── user.dart             # User model
│   │   ├── wallet.dart           # Wallet & token models
│   │   ├── transaction.dart      # Transaction model
│   │   └── risk_assessment.dart  # Risk assessment model
│   ├── widgets/
│   │   ├── widgets.dart          # Widgets barrel
│   │   ├── app_components.dart   # Core UI components
│   │   ├── risk_components.dart  # Risk visualization
│   │   ├── transaction_components.dart  # Transaction UI
│   │   └── wallet_components.dart       # Wallet UI
│   ├── layout/                   # Layout components
│   └── shells/                   # App shells/wrappers
│
└── features/               # Feature modules
    ├── home/
    ├── transfer/
    ├── transactions/
    └── settings/
```

## Design System

### Colors

All colors are defined in `design_tokens.dart` and synchronized with the Next.js Tailwind theme:

```dart
import 'package:amttp/core/core.dart';

// Semantic colors
Container(color: SemanticColors.primary);
Container(color: SemanticColors.surface);
Container(color: SemanticColors.statusSuccess);

// Risk colors (based on score)
Container(color: RiskColors.fromScore(75)); // Returns high risk color
```

### Typography

Standardized text styles in `typography.dart`:

```dart
Text('Headline', style: AppTypography.headlineLarge);
Text('Body text', style: AppTypography.bodyMedium);
Text('Label', style: AppTypography.labelSmall);
```

### Spacing

Consistent spacing using `spacing.dart`:

```dart
Column(
  children: [
    Widget1(),
    Gaps.md,  // 16px gap
    Widget2(),
    Gaps.lg,  // 24px gap
    Widget3(),
  ],
)

Padding(
  padding: Insets.pagePadding,  // Standard page padding
  child: Content(),
)
```

## Standard Components

### Core Components (`app_components.dart`)

```dart
// Cards
AppCard(
  child: content,
  onTap: () {},
  variant: CardVariant.elevated,
)

// Buttons
AppButton(
  label: 'Submit',
  onPressed: () {},
  variant: ButtonVariant.primary,
)

// Text fields
AppTextField(
  label: 'Address',
  controller: controller,
  validator: (value) => value?.isEmpty == true ? 'Required' : null,
)

// Status badges
AppStatusBadge(
  label: 'Confirmed',
  status: BadgeStatus.success,
)

// Loading states
AppLoadingIndicator()
AppLoadingIndicator.overlay(message: 'Processing...')

// Empty states
AppEmptyState(
  icon: Icons.inbox,
  title: 'No transactions',
  message: 'Your transactions will appear here',
  action: AppButton(label: 'Get started', onPressed: () {}),
)

// Error states
AppErrorState(
  title: 'Something went wrong',
  message: error.message,
  onRetry: () => refresh(),
)
```

### Risk Components (`risk_components.dart`)

```dart
// Circular risk score
AppRiskScore(score: 45.0, label: 'Transaction Risk')

// Horizontal risk bar
AppRiskBar(score: 75.0, showLabel: true)

// Risk factor breakdown
AppRiskFactor(
  name: 'Address Age',
  score: 35.0,
  weight: 0.15,
  description: 'Address created recently',
)

// Full risk summary card
AppRiskSummary(
  overallScore: 45.0,
  factors: [
    RiskFactorData(name: 'Address Age', score: 35, weight: 0.15),
    RiskFactorData(name: 'Transaction Pattern', score: 55, weight: 0.25),
  ],
  onViewDetails: () {},
)
```

### Transaction Components (`transaction_components.dart`)

```dart
// Full transaction card
AppTransactionCard(
  transactionId: '0x123...',
  fromAddress: '0xabc...',
  toAddress: '0xdef...',
  amount: '1.5',
  tokenSymbol: 'ETH',
  status: TransactionStatus.confirmed,
  timestamp: DateTime.now(),
  riskScore: 25.0,
  onTap: () => viewDetails(),
)

// Compact list item
AppTransactionListItem(
  transactionId: '0x123...',
  amount: '1.5',
  status: TransactionStatus.confirmed,
  timestamp: DateTime.now(),
  isSent: true,
  onTap: () {},
)

// Transaction confirmation dialog
AppTransactionConfirmation(
  toAddress: '0xdef...',
  amount: '1.5',
  estimatedFee: 0.005,
  riskScore: 35.0,
  warnings: ['New address detected'],
  onConfirm: () => confirm(),
  onCancel: () => cancel(),
)
```

### Wallet Components (`wallet_components.dart`)

```dart
// Main wallet card
AppWalletCard(
  address: '0x123...',
  balance: '10.5',
  tokenSymbol: 'ETH',
  usdValue: '25,000',
  walletType: WalletType.metamask,
  status: WalletConnectionStatus.connected,
  trustScore: 85.0,
  onSend: () {},
  onReceive: () {},
)

// Wallet selector for connection
AppWalletSelector(
  availableWallets: [WalletType.metamask, WalletType.walletConnect],
  selectedWallet: selectedWallet,
  isConnecting: isConnecting,
  onSelect: (wallet) => connect(wallet),
)

// Compact address display
AppWalletAddress(
  address: '0x123...',
  walletType: WalletType.metamask,
  showCopyButton: true,
)

// Token balance row
AppTokenBalance(
  balance: '100.0',
  symbol: 'USDC',
  usdValue: '100.00',
  change24h: 0.5,
  onTap: () {},
)
```

## Services Layer

### API Client

```dart
import 'package:amttp/core/core.dart';

// Use the singleton
final result = await apiClient.get<User>(
  '/api/user/profile',
  fromJson: User.fromJson,
  useCache: true,
);

result.when(
  success: (user) => print('Hello ${user.displayName}'),
  failure: (error) => print('Error: ${error.message}'),
);

// Or create a custom instance
final customClient = ApiClient(
  baseUrl: 'https://custom-api.example.com',
  timeout: Duration(seconds: 60),
);
```

### Result Type

```dart
// Type-safe error handling
Future<Result<User>> getUser() async {
  return apiClient.get<User>(
    '/api/user',
    fromJson: User.fromJson,
  );
}

// Usage
final result = await getUser();

// Pattern matching
result.when(
  success: (user) => showUser(user),
  failure: (error) => showError(error),
);

// Direct access
if (result.isSuccess) {
  final user = result.valueOrNull;
}

// Chaining
final name = result
    .map((user) => user.displayName)
    .getOrDefault('Unknown');
```

### Exception Types

```dart
// Network errors
throw NetworkException.timeout();
throw NetworkException.noInternet();

// Auth errors
throw AuthException.unauthorized();
throw AuthException.tokenExpired();

// Validation errors
throw ValidationException.fromFieldErrors({
  'email': ['Invalid email format'],
  'amount': ['Must be greater than 0'],
});

// Blockchain errors
throw BlockchainException.insufficientFunds();
throw BlockchainException.transactionFailed(reason: 'Reverted');

// Risk errors
throw RiskEngineException.highRisk(score: 95, factors: ['Blacklisted']);
```

## Models

### User

```dart
final user = User.fromJson(json);
print(user.role.isConsumer);  // true for guest/retail/premium
print(user.walletAddress);
```

### Wallet

```dart
final wallet = Wallet.fromJson(json);
print(wallet.shortAddress);  // 0x1234...abcd
print(wallet.totalUsdValue);
print(wallet.isConnected);
```

### Transaction

```dart
final tx = Transaction.fromJson(json);
print(tx.shortHash);
print(tx.timeAgo);  // "5m ago"
print(tx.isSentFrom(myAddress));
```

### RiskAssessment

```dart
final risk = RiskAssessment.fromJson(json);
print(risk.riskLevel);  // RiskLevel.high
print(risk.canProceed);
print(risk.topFactors);  // Top 5 risk factors
```

## Route Names

```dart
import 'package:amttp/core/core.dart';

// Use centralized route names
context.go(AppRoutes.home);
context.push(AppRoutes.transactionDetails(txId));

// Available routes
AppRoutes.home
AppRoutes.transfer
AppRoutes.transactions
AppRoutes.transactionDetails(id)
AppRoutes.settings
AppRoutes.walletConnect
```

## Feature Flags

```dart
import 'package:amttp/core/core.dart';

if (FeatureFlags.zkNafEnabled) {
  // Show ZK-NAF features
}

if (FeatureFlags.federatedLearning) {
  // Enable federated learning
}
```

## Best Practices

### 1. Import Using Barrel Exports

```dart
// ✅ Good - use barrel exports
import 'package:amttp/core/core.dart';
import 'package:amttp/shared/shared.dart';

// ❌ Bad - direct file imports
import 'package:amttp/core/theme/design_tokens.dart';
import 'package:amttp/shared/widgets/app_components.dart';
```

### 2. Use Standard Components

```dart
// ✅ Good - use standard components
AppButton(label: 'Submit', onPressed: submit);
AppCard(child: content);

// ❌ Bad - custom implementations
ElevatedButton(onPressed: submit, child: Text('Submit'));
Container(decoration: ..., child: content);
```

### 3. Handle Errors with Result

```dart
// ✅ Good - use Result type
final result = await apiClient.get<Data>(...);
result.when(
  success: (data) => setState(() => _data = data),
  failure: (error) => showError(error),
);

// ❌ Bad - try/catch for API calls
try {
  final data = await apiClient.get<Data>(...);
} catch (e) {
  showError(e);
}
```

### 4. Use Design Tokens

```dart
// ✅ Good - use design tokens
Container(
  color: SemanticColors.surfaceElevated,
  padding: Insets.cardPadding,
)

// ❌ Bad - hardcoded values
Container(
  color: Color(0xFF1E1E2E),
  padding: EdgeInsets.all(16),
)
```

### 5. Consistent Spacing

```dart
// ✅ Good - use Gaps
Column(children: [
  Widget1(),
  Gaps.md,
  Widget2(),
])

// ❌ Bad - SizedBox with magic numbers
Column(children: [
  Widget1(),
  SizedBox(height: 16),
  Widget2(),
])
```

## Migration Guide

### Migrating Existing Widgets

1. Replace hardcoded colors with `SemanticColors`
2. Replace text styles with `AppTypography`
3. Replace spacing with `Gaps` and `Insets`
4. Replace custom buttons with `AppButton`
5. Replace custom cards with `AppCard`
6. Update error handling to use `Result` type

### Example Migration

Before:
```dart
Container(
  color: Color(0xFF1E1E2E),
  padding: EdgeInsets.all(16),
  child: Column(
    children: [
      Text('Title', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
      SizedBox(height: 8),
      ElevatedButton(onPressed: () {}, child: Text('Action')),
    ],
  ),
)
```

After:
```dart
AppCard(
  child: Column(
    children: [
      Text('Title', style: AppTypography.titleMedium),
      Gaps.sm,
      AppButton(label: 'Action', onPressed: () {}),
    ],
  ),
)
```

## Testing

Components include built-in accessibility support and are designed to be easily testable:

```dart
testWidgets('AppButton responds to tap', (tester) async {
  var tapped = false;
  await tester.pumpWidget(
    MaterialApp(
      home: AppButton(
        label: 'Test',
        onPressed: () => tapped = true,
      ),
    ),
  );
  
  await tester.tap(find.text('Test'));
  expect(tapped, isTrue);
});
```
