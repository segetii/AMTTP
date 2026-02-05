/// AMTTP Shared Widgets
/// 
/// Export all shared widgets for easy import

// =============================================================================
// STANDARD COMPONENTS (New Standardized Design System)
// =============================================================================

// Core app components (AppCard, AppButton, AppTextField, etc.)
export 'app_components.dart';

// Risk visualization components (AppRiskScore, AppRiskBar, etc.)
export 'risk_components.dart';

// Transaction components (AppTransactionCard, AppTransactionListItem, etc.)
export 'transaction_components.dart';

// Wallet components (AppWalletCard, AppWalletSelector, etc.)
export 'wallet_components.dart';

// =============================================================================
// LEGACY WIDGETS (To be migrated to standard components)
// =============================================================================

// Transfer widgets
export 'secure_transfer_widget.dart';
export 'secure_transfer_protected_widget.dart';
export 'secure_transfer_improved.dart';

// Trust & Risk widgets
export 'trust_check_interstitial.dart';
export 'risk_level_indicator.dart';
export 'risk_visualizer_widget.dart';

// Explainability widgets
export 'explainability_widget.dart';

// Multisig widgets
export 'multisig_approval_card.dart';

// Interactive widgets
export 'interactive_wallet_widget.dart';
export 'features_carousel.dart';

// Platform widgets
export 'platform_app_header.dart';
export 'platform_app_switcher.dart';
