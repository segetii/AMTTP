import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../core/providers/settings_provider.dart';
import '../../../../shared/layout/premium_centered_page.dart';

class SettingsPage extends ConsumerWidget {
  const SettingsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final settings = ref.watch(settingsProvider);

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: PremiumCenteredPage(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Header row (replaces AppBar for premium shell)
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'Settings',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.restore, color: Colors.white70),
                  onPressed: () => _showResetDialog(context, ref),
                  tooltip: 'Reset to defaults',
                ),
              ],
            ),
            const SizedBox(height: 16),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  _buildSettingsSection('General', [
                    _buildSelectSettingsItem(
                      context: context,
                      icon: Icons.language_rounded,
                      title: 'Language',
                      value: settings.language,
                      options: languageOptions,
                      onSelected: (value) => ref.read(settingsProvider.notifier).setLanguage(value),
                    ),
                    _buildSelectSettingsItem(
                      context: context,
                      icon: Icons.palette_rounded,
                      title: 'Theme',
                      value: settings.theme,
                      options: themeOptions,
                      onSelected: (value) => ref.read(settingsProvider.notifier).setTheme(value),
                    ),
                    _buildSwitchSettingsItem(
                      icon: Icons.notifications_rounded,
                      title: 'Notifications',
                      value: settings.notificationsEnabled,
                      onChanged: (value) => ref.read(settingsProvider.notifier).setNotificationsEnabled(value),
                    ),
                  ]),
                  const SizedBox(height: 24),
                  _buildSettingsSection('Security', [
                    _buildSwitchSettingsItem(
                      icon: Icons.fingerprint_rounded,
                      title: 'Biometrics',
                      value: settings.biometricsEnabled,
                      onChanged: (value) => ref.read(settingsProvider.notifier).setBiometricsEnabled(value),
                    ),
                    _buildSelectSettingsItem(
                      context: context,
                      icon: Icons.lock_rounded,
                      title: 'Auto-lock',
                      value: '${settings.autoLockMinutes} min',
                      options: autoLockOptions.map((m) => '$m min').toList(),
                      onSelected: (value) {
                        final minutes = int.parse(value.replaceAll(' min', ''));
                        ref.read(settingsProvider.notifier).setAutoLockMinutes(minutes);
                      },
                    ),
                    _buildNumberSettingsItem(
                      context: context,
                      ref: ref,
                      icon: Icons.shield_rounded,
                      title: 'Transaction Limit',
                      value: '\$${settings.transactionLimit.toStringAsFixed(0)}',
                      onChanged: (value) => ref.read(settingsProvider.notifier).setTransactionLimit(value),
                    ),
                  ]),
                  const SizedBox(height: 24),
                  _buildSettingsSection('Network', [
                    _buildSelectSettingsItem(
                      context: context,
                      icon: Icons.lan_rounded,
                      title: 'RPC Endpoint',
                      value: settings.rpcEndpoint,
                      options: rpcEndpointOptions,
                      onSelected: (value) => ref.read(settingsProvider.notifier).setRpcEndpoint(value),
                    ),
                    _buildSelectSettingsItem(
                      context: context,
                      icon: Icons.speed_rounded,
                      title: 'Gas Price',
                      value: settings.gasPrice,
                      options: gasPriceOptions,
                      onSelected: (value) => ref.read(settingsProvider.notifier).setGasPrice(value),
                    ),
                  ]),
                  const SizedBox(height: 24),
                  _buildSettingsSection('Compliance', [
                    _buildSwitchSettingsItem(
                      icon: Icons.warning_rounded,
                      title: 'Show Risk Warnings',
                      value: settings.showRiskWarnings,
                      onChanged: (value) => ref.read(settingsProvider.notifier).setShowRiskWarnings(value),
                    ),
                    _buildSwitchSettingsItem(
                      icon: Icons.check_circle_rounded,
                      title: 'Require Confirmation',
                      value: settings.requireConfirmation,
                      onChanged: (value) => ref.read(settingsProvider.notifier).setRequireConfirmation(value),
                    ),
                    _buildSliderSettingsItem(
                      context: context,
                      icon: Icons.tune_rounded,
                      title: 'Default Slippage',
                      value: settings.defaultSlippage,
                      min: 0.1,
                      max: 5.0,
                      suffix: '%',
                      onChanged: (value) => ref.read(settingsProvider.notifier).setDefaultSlippage(value),
                    ),
                  ]),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _showResetDialog(BuildContext context, WidgetRef ref) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppTheme.darkCard,
        title: const Text('Reset Settings', style: TextStyle(color: AppTheme.cleanWhite)),
        content: const Text(
          'Are you sure you want to reset all settings to their defaults?',
          style: TextStyle(color: AppTheme.cleanWhite),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () {
              ref.read(settingsProvider.notifier).resetToDefaults();
              Navigator.pop(context);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Settings reset to defaults')),
              );
            },
            child: const Text('Reset', style: TextStyle(color: AppTheme.dangerRed)),
          ),
        ],
      ),
    );
  }

  Widget _buildSettingsSection(String title, List<Widget> items) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: TextStyle(
            color: AppTheme.cleanWhite.withOpacity(0.6),
            fontWeight: FontWeight.w600,
            fontSize: 12,
            letterSpacing: 1.2,
          ),
        ),
        const SizedBox(height: 12),
        Container(
          decoration: BoxDecoration(
            color: AppTheme.darkCard,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: AppTheme.cleanWhite.withOpacity(0.1)),
          ),
          child: Column(children: items),
        ),
      ],
    );
  }

  Widget _buildSelectSettingsItem({
    required BuildContext context,
    required IconData icon,
    required String title,
    required String value,
    required List<String> options,
    required Function(String) onSelected,
  }) {
    return InkWell(
      onTap: () {
        showModalBottomSheet(
          context: context,
          backgroundColor: AppTheme.darkCard,
          builder: (context) => SafeArea(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text(
                    'Select $title',
                    style: const TextStyle(
                      color: AppTheme.cleanWhite,
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                ...options.map((option) => ListTile(
                  title: Text(option, style: const TextStyle(color: AppTheme.cleanWhite)),
                  trailing: option == value
                      ? const Icon(Icons.check, color: AppTheme.primaryPurple)
                      : null,
                  onTap: () {
                    onSelected(option);
                    Navigator.pop(context);
                  },
                )),
                const SizedBox(height: 16),
              ],
            ),
          ),
        );
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        decoration: BoxDecoration(
          border: Border(
            bottom: BorderSide(color: AppTheme.cleanWhite.withOpacity(0.05)),
          ),
        ),
        child: Row(
          children: [
            Icon(icon, color: AppTheme.primaryPurple, size: 22),
            const SizedBox(width: 16),
            Expanded(
              child: Text(
                title,
                style: const TextStyle(
                  color: AppTheme.cleanWhite,
                  fontSize: 15,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
            Text(
              value,
              style: TextStyle(
                color: AppTheme.cleanWhite.withOpacity(0.6),
                fontSize: 14,
              ),
            ),
            const SizedBox(width: 8),
            Icon(
              Icons.chevron_right_rounded,
              color: AppTheme.cleanWhite.withOpacity(0.3),
              size: 20,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSwitchSettingsItem({
    required IconData icon,
    required String title,
    required bool value,
    required Function(bool) onChanged,
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(color: AppTheme.cleanWhite.withOpacity(0.05)),
        ),
      ),
      child: Row(
        children: [
          Icon(icon, color: AppTheme.primaryPurple, size: 22),
          const SizedBox(width: 16),
          Expanded(
            child: Text(
              title,
              style: const TextStyle(
                color: AppTheme.cleanWhite,
                fontSize: 15,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
          Switch(
            value: value,
            onChanged: onChanged,
            activeColor: AppTheme.primaryPurple,
          ),
        ],
      ),
    );
  }

  Widget _buildNumberSettingsItem({
    required BuildContext context,
    required WidgetRef ref,
    required IconData icon,
    required String title,
    required String value,
    required Function(double) onChanged,
  }) {
    return InkWell(
      onTap: () {
        final controller = TextEditingController(
          text: value.replaceAll(RegExp(r'[^\d.]'), ''),
        );
        showDialog(
          context: context,
          builder: (context) => AlertDialog(
            backgroundColor: AppTheme.darkCard,
            title: Text('Set $title', style: const TextStyle(color: AppTheme.cleanWhite)),
            content: TextField(
              controller: controller,
              keyboardType: TextInputType.number,
              style: const TextStyle(color: AppTheme.cleanWhite),
              decoration: InputDecoration(
                prefixText: '\$',
                prefixStyle: const TextStyle(color: AppTheme.cleanWhite),
                enabledBorder: OutlineInputBorder(
                  borderSide: BorderSide(color: AppTheme.cleanWhite.withOpacity(0.3)),
                ),
                focusedBorder: const OutlineInputBorder(
                  borderSide: BorderSide(color: AppTheme.primaryPurple),
                ),
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Cancel'),
              ),
              TextButton(
                onPressed: () {
                  final newValue = double.tryParse(controller.text) ?? 0;
                  if (newValue > 0) {
                    onChanged(newValue);
                  }
                  Navigator.pop(context);
                },
                child: const Text('Save'),
              ),
            ],
          ),
        );
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        decoration: BoxDecoration(
          border: Border(
            bottom: BorderSide(color: AppTheme.cleanWhite.withOpacity(0.05)),
          ),
        ),
        child: Row(
          children: [
            Icon(icon, color: AppTheme.primaryPurple, size: 22),
            const SizedBox(width: 16),
            Expanded(
              child: Text(
                title,
                style: const TextStyle(
                  color: AppTheme.cleanWhite,
                  fontSize: 15,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
            Text(
              value,
              style: TextStyle(
                color: AppTheme.cleanWhite.withOpacity(0.6),
                fontSize: 14,
              ),
            ),
            const SizedBox(width: 8),
            Icon(
              Icons.edit_rounded,
              color: AppTheme.cleanWhite.withOpacity(0.3),
              size: 20,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSliderSettingsItem({
    required BuildContext context,
    required IconData icon,
    required String title,
    required double value,
    required double min,
    required double max,
    required String suffix,
    required Function(double) onChanged,
  }) {
    return StatefulBuilder(
      builder: (context, setState) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          border: Border(
            bottom: BorderSide(color: AppTheme.cleanWhite.withOpacity(0.05)),
          ),
        ),
        child: Column(
          children: [
            Row(
              children: [
                Icon(icon, color: AppTheme.primaryPurple, size: 22),
                const SizedBox(width: 16),
                Expanded(
                  child: Text(
                    title,
                    style: const TextStyle(
                      color: AppTheme.cleanWhite,
                      fontSize: 15,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
                Text(
                  '${value.toStringAsFixed(1)}$suffix',
                  style: TextStyle(
                    color: AppTheme.cleanWhite.withOpacity(0.6),
                    fontSize: 14,
                  ),
                ),
              ],
            ),
            Slider(
              value: value,
              min: min,
              max: max,
              divisions: ((max - min) * 10).toInt(),
              activeColor: AppTheme.primaryPurple,
              inactiveColor: AppTheme.cleanWhite.withOpacity(0.2),
              onChanged: (newValue) {
                onChanged(newValue);
              },
            ),
          ],
        ),
      ),
    );
  }
}