import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Keys for SharedPreferences
class SettingsKeys {
  static const String language = 'settings_language';
  static const String theme = 'settings_theme';
  static const String notificationsEnabled = 'settings_notifications_enabled';
  static const String biometricsEnabled = 'settings_biometrics_enabled';
  static const String autoLockMinutes = 'settings_auto_lock_minutes';
  static const String transactionLimit = 'settings_transaction_limit';
  static const String rpcEndpoint = 'settings_rpc_endpoint';
  static const String gasPrice = 'settings_gas_price';
  static const String showRiskWarnings = 'settings_show_risk_warnings';
  static const String requireConfirmation = 'settings_require_confirmation';
  static const String defaultSlippage = 'settings_default_slippage';
}

/// Settings model
class AppSettings {
  final String language;
  final String theme;
  final bool notificationsEnabled;
  final bool biometricsEnabled;
  final int autoLockMinutes;
  final double transactionLimit;
  final String rpcEndpoint;
  final String gasPrice;
  final bool showRiskWarnings;
  final bool requireConfirmation;
  final double defaultSlippage;

  const AppSettings({
    this.language = 'English',
    this.theme = 'Dark',
    this.notificationsEnabled = true,
    this.biometricsEnabled = false,
    this.autoLockMinutes = 5,
    this.transactionLimit = 10000.0,
    this.rpcEndpoint = 'Mainnet',
    this.gasPrice = 'Auto',
    this.showRiskWarnings = true,
    this.requireConfirmation = true,
    this.defaultSlippage = 0.5,
  });

  AppSettings copyWith({
    String? language,
    String? theme,
    bool? notificationsEnabled,
    bool? biometricsEnabled,
    int? autoLockMinutes,
    double? transactionLimit,
    String? rpcEndpoint,
    String? gasPrice,
    bool? showRiskWarnings,
    bool? requireConfirmation,
    double? defaultSlippage,
  }) {
    return AppSettings(
      language: language ?? this.language,
      theme: theme ?? this.theme,
      notificationsEnabled: notificationsEnabled ?? this.notificationsEnabled,
      biometricsEnabled: biometricsEnabled ?? this.biometricsEnabled,
      autoLockMinutes: autoLockMinutes ?? this.autoLockMinutes,
      transactionLimit: transactionLimit ?? this.transactionLimit,
      rpcEndpoint: rpcEndpoint ?? this.rpcEndpoint,
      gasPrice: gasPrice ?? this.gasPrice,
      showRiskWarnings: showRiskWarnings ?? this.showRiskWarnings,
      requireConfirmation: requireConfirmation ?? this.requireConfirmation,
      defaultSlippage: defaultSlippage ?? this.defaultSlippage,
    );
  }
}

/// Settings Notifier with persistence
class SettingsNotifier extends StateNotifier<AppSettings> {
  final SharedPreferences _prefs;

  SettingsNotifier(this._prefs) : super(const AppSettings()) {
    _loadSettings();
  }

  void _loadSettings() {
    state = AppSettings(
      language: _prefs.getString(SettingsKeys.language) ?? 'English',
      theme: _prefs.getString(SettingsKeys.theme) ?? 'Dark',
      notificationsEnabled: _prefs.getBool(SettingsKeys.notificationsEnabled) ?? true,
      biometricsEnabled: _prefs.getBool(SettingsKeys.biometricsEnabled) ?? false,
      autoLockMinutes: _prefs.getInt(SettingsKeys.autoLockMinutes) ?? 5,
      transactionLimit: _prefs.getDouble(SettingsKeys.transactionLimit) ?? 10000.0,
      rpcEndpoint: _prefs.getString(SettingsKeys.rpcEndpoint) ?? 'Mainnet',
      gasPrice: _prefs.getString(SettingsKeys.gasPrice) ?? 'Auto',
      showRiskWarnings: _prefs.getBool(SettingsKeys.showRiskWarnings) ?? true,
      requireConfirmation: _prefs.getBool(SettingsKeys.requireConfirmation) ?? true,
      defaultSlippage: _prefs.getDouble(SettingsKeys.defaultSlippage) ?? 0.5,
    );
  }

  Future<void> setLanguage(String language) async {
    await _prefs.setString(SettingsKeys.language, language);
    state = state.copyWith(language: language);
  }

  Future<void> setTheme(String theme) async {
    await _prefs.setString(SettingsKeys.theme, theme);
    state = state.copyWith(theme: theme);
  }

  Future<void> setNotificationsEnabled(bool enabled) async {
    await _prefs.setBool(SettingsKeys.notificationsEnabled, enabled);
    state = state.copyWith(notificationsEnabled: enabled);
  }

  Future<void> setBiometricsEnabled(bool enabled) async {
    await _prefs.setBool(SettingsKeys.biometricsEnabled, enabled);
    state = state.copyWith(biometricsEnabled: enabled);
  }

  Future<void> setAutoLockMinutes(int minutes) async {
    await _prefs.setInt(SettingsKeys.autoLockMinutes, minutes);
    state = state.copyWith(autoLockMinutes: minutes);
  }

  Future<void> setTransactionLimit(double limit) async {
    await _prefs.setDouble(SettingsKeys.transactionLimit, limit);
    state = state.copyWith(transactionLimit: limit);
  }

  Future<void> setRpcEndpoint(String endpoint) async {
    await _prefs.setString(SettingsKeys.rpcEndpoint, endpoint);
    state = state.copyWith(rpcEndpoint: endpoint);
  }

  Future<void> setGasPrice(String gasPrice) async {
    await _prefs.setString(SettingsKeys.gasPrice, gasPrice);
    state = state.copyWith(gasPrice: gasPrice);
  }

  Future<void> setShowRiskWarnings(bool show) async {
    await _prefs.setBool(SettingsKeys.showRiskWarnings, show);
    state = state.copyWith(showRiskWarnings: show);
  }

  Future<void> setRequireConfirmation(bool require) async {
    await _prefs.setBool(SettingsKeys.requireConfirmation, require);
    state = state.copyWith(requireConfirmation: require);
  }

  Future<void> setDefaultSlippage(double slippage) async {
    await _prefs.setDouble(SettingsKeys.defaultSlippage, slippage);
    state = state.copyWith(defaultSlippage: slippage);
  }

  Future<void> resetToDefaults() async {
    await _prefs.remove(SettingsKeys.language);
    await _prefs.remove(SettingsKeys.theme);
    await _prefs.remove(SettingsKeys.notificationsEnabled);
    await _prefs.remove(SettingsKeys.biometricsEnabled);
    await _prefs.remove(SettingsKeys.autoLockMinutes);
    await _prefs.remove(SettingsKeys.transactionLimit);
    await _prefs.remove(SettingsKeys.rpcEndpoint);
    await _prefs.remove(SettingsKeys.gasPrice);
    await _prefs.remove(SettingsKeys.showRiskWarnings);
    await _prefs.remove(SettingsKeys.requireConfirmation);
    await _prefs.remove(SettingsKeys.defaultSlippage);
    state = const AppSettings();
  }
}

/// Provider for SharedPreferences (must be overridden in main)
final sharedPreferencesProvider = Provider<SharedPreferences>((ref) {
  throw UnimplementedError('SharedPreferences not initialized');
});

/// Settings provider
final settingsProvider = StateNotifierProvider<SettingsNotifier, AppSettings>((ref) {
  final prefs = ref.watch(sharedPreferencesProvider);
  return SettingsNotifier(prefs);
});

/// Language options
const List<String> languageOptions = [
  'English',
  'Spanish',
  'French',
  'German',
  'Chinese',
  'Japanese',
  'Korean',
];

/// Theme options
const List<String> themeOptions = [
  'Dark',
  'Light',
  'System',
];

/// Auto-lock options
const List<int> autoLockOptions = [1, 2, 5, 10, 15, 30];

/// RPC endpoint options
const List<String> rpcEndpointOptions = [
  'Mainnet',
  'Sepolia',
  'Goerli',
  'Localhost',
  'Custom',
];

/// Gas price options  
const List<String> gasPriceOptions = [
  'Auto',
  'Low',
  'Medium',
  'High',
  'Custom',
];
