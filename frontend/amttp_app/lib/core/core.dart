/// Core Module - Barrel Export
/// 
/// Contains fundamental app infrastructure:
/// - Theme & Design System
/// - Router & Navigation
/// - Constants & Configuration
/// - Services & API Client
/// - Providers & State Management
/// - Authentication & Security
/// - RBAC & Permissions
/// - Utilities & Helpers
library;

// Theme & Design System
export 'theme/app_theme.dart';
export 'theme/design_tokens.dart';
export 'theme/typography.dart';
export 'theme/spacing.dart';

// Router & Navigation
export 'router/app_router.dart';
export 'router/consumer_app_router.dart';
export 'router/route_names.dart';

// Constants & Configuration
export 'constants/app_constants.dart';
export 'constants/api_endpoints.dart';
export 'constants/feature_flags.dart';

// Services & API
export 'services/services.dart';

// Providers
export 'providers/settings_provider.dart';

// Auth & Security
export 'auth/auth_provider.dart';
export 'security/security.dart';

// RBAC
export 'rbac/rbac.dart';

// Utilities
export 'utils/utils.dart';

// Web3
export 'web3/wallet_provider.dart';
