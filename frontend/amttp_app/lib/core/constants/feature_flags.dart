/// Feature Flags - Runtime Feature Configuration
///
/// Use these flags to enable/disable features at runtime.
/// Flags can be controlled via environment variables or remote config.
library;

abstract class FeatureFlags {
  // ═══════════════════════════════════════════════════════════════════════════
  // ENVIRONMENT
  // ═══════════════════════════════════════════════════════════════════════════

  /// Current environment
  static const String environment = String.fromEnvironment(
    'ENVIRONMENT',
    defaultValue: 'development',
  );

  static bool get isDevelopment => environment == 'development';
  static bool get isStaging => environment == 'staging';
  static bool get isProduction => environment == 'production';

  // ═══════════════════════════════════════════════════════════════════════════
  // DEBUG FLAGS
  // ═══════════════════════════════════════════════════════════════════════════

  /// Enable debug mode features
  static const bool debugMode = bool.fromEnvironment(
    'DEBUG_MODE',
    defaultValue: true,
  );

  /// Show debug overlay
  static const bool showDebugOverlay = bool.fromEnvironment(
    'SHOW_DEBUG_OVERLAY',
    defaultValue: false,
  );

  /// Enable mock data (ENABLED for demo users)
  static const bool useMockData = bool.fromEnvironment(
    'USE_MOCK_DATA',
    defaultValue: true,
  );

  /// Bypass authentication (for testing)
  static const bool bypassAuth = bool.fromEnvironment(
    'BYPASS_AUTH',
    defaultValue: false,
  );

  // ═══════════════════════════════════════════════════════════════════════════
  // FEATURE FLAGS
  // ═══════════════════════════════════════════════════════════════════════════

  /// Enable NFT swap feature
  static const bool enableNftSwap = bool.fromEnvironment(
    'ENABLE_NFT_SWAP',
    defaultValue: true,
  );

  /// Enable cross-chain transfers
  static const bool enableCrossChain = bool.fromEnvironment(
    'ENABLE_CROSS_CHAIN',
    defaultValue: true,
  );

  /// Enable zkNAF privacy features
  static const bool enableZkNaf = bool.fromEnvironment(
    'ENABLE_ZKNAF',
    defaultValue: true,
  );

  /// Enable session keys (ERC-4337)
  static const bool enableSessionKeys = bool.fromEnvironment(
    'ENABLE_SESSION_KEYS',
    defaultValue: true,
  );

  /// Enable Safe (Gnosis) integration
  static const bool enableSafe = bool.fromEnvironment(
    'ENABLE_SAFE',
    defaultValue: true,
  );

  /// Enable biometric authentication
  static const bool enableBiometrics = bool.fromEnvironment(
    'ENABLE_BIOMETRICS',
    defaultValue: true,
  );

  /// Enable push notifications
  static const bool enablePushNotifications = bool.fromEnvironment(
    'ENABLE_PUSH',
    defaultValue: false,
  );

  // ═══════════════════════════════════════════════════════════════════════════
  // WAR ROOM FLAGS (Institutional)
  // ═══════════════════════════════════════════════════════════════════════════

  /// Enable War Room in Flutter (vs Next.js only)
  static const bool enableFlutterWarRoom = bool.fromEnvironment(
    'ENABLE_FLUTTER_WAR_ROOM',
    defaultValue: false,
  );

  /// Enable Detection Studio
  static const bool enableDetectionStudio = bool.fromEnvironment(
    'ENABLE_DETECTION_STUDIO',
    defaultValue: true,
  );

  /// Enable ML model management
  static const bool enableMlModels = bool.fromEnvironment(
    'ENABLE_ML_MODELS',
    defaultValue: true,
  );

  // ═══════════════════════════════════════════════════════════════════════════
  // NETWORK FLAGS
  // ═══════════════════════════════════════════════════════════════════════════

  /// Enable mainnet
  static const bool enableMainnet = bool.fromEnvironment(
    'ENABLE_MAINNET',
    defaultValue: false,
  );

  /// Enable testnet
  static const bool enableTestnet = bool.fromEnvironment(
    'ENABLE_TESTNET',
    defaultValue: true,
  );

  /// Default to testnet
  static const bool defaultToTestnet = bool.fromEnvironment(
    'DEFAULT_TESTNET',
    defaultValue: true,
  );
}
