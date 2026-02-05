import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../core/theme/design_tokens.dart';
import '../../core/theme/typography.dart';
import '../../core/theme/spacing.dart';
import 'app_components.dart';
import 'risk_components.dart';

/// Wallet connection status
enum WalletConnectionStatus {
  disconnected,
  connecting,
  connected,
  error,
}

/// Wallet type enumeration
enum WalletType {
  metamask,
  walletConnect,
  coinbase,
  rainbow,
  trust,
  ledger,
  unknown,
}

extension WalletTypeX on WalletType {
  String get displayName {
    switch (this) {
      case WalletType.metamask:
        return 'MetaMask';
      case WalletType.walletConnect:
        return 'WalletConnect';
      case WalletType.coinbase:
        return 'Coinbase Wallet';
      case WalletType.rainbow:
        return 'Rainbow';
      case WalletType.trust:
        return 'Trust Wallet';
      case WalletType.ledger:
        return 'Ledger';
      case WalletType.unknown:
        return 'Unknown Wallet';
    }
  }

  IconData get icon {
    switch (this) {
      case WalletType.metamask:
        return Icons.pets; // Fox-like
      case WalletType.walletConnect:
        return Icons.link;
      case WalletType.coinbase:
        return Icons.account_balance_wallet;
      case WalletType.rainbow:
        return Icons.wb_sunny;
      case WalletType.trust:
        return Icons.shield;
      case WalletType.ledger:
        return Icons.security;
      case WalletType.unknown:
        return Icons.wallet;
    }
  }
}

/// Main wallet card showing balance and actions
class AppWalletCard extends StatelessWidget {
  final String address;
  final String balance;
  final String tokenSymbol;
  final String? usdValue;
  final WalletType walletType;
  final WalletConnectionStatus status;
  final double? trustScore;
  final VoidCallback? onSend;
  final VoidCallback? onReceive;
  final VoidCallback? onDisconnect;
  final VoidCallback? onCopyAddress;

  const AppWalletCard({
    super.key,
    required this.address,
    required this.balance,
    this.tokenSymbol = 'ETH',
    this.usdValue,
    this.walletType = WalletType.unknown,
    this.status = WalletConnectionStatus.connected,
    this.trustScore,
    this.onSend,
    this.onReceive,
    this.onDisconnect,
    this.onCopyAddress,
  });

  String get _formattedAddress {
    if (address.length > 12) {
      return '${address.substring(0, 6)}...${address.substring(address.length - 4)}';
    }
    return address;
  }

  Color get _statusColor {
    switch (status) {
      case WalletConnectionStatus.connected:
        return SemanticColors.statusSuccess;
      case WalletConnectionStatus.connecting:
        return SemanticColors.statusWarning;
      case WalletConnectionStatus.disconnected:
        return SemanticColors.textTertiary;
      case WalletConnectionStatus.error:
        return SemanticColors.statusError;
    }
  }

  String get _statusLabel {
    switch (status) {
      case WalletConnectionStatus.connected:
        return 'Connected';
      case WalletConnectionStatus.connecting:
        return 'Connecting...';
      case WalletConnectionStatus.disconnected:
        return 'Disconnected';
      case WalletConnectionStatus.error:
        return 'Error';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            SemanticColors.primary,
            SemanticColors.primaryHover,
          ],
        ),
        borderRadius: BorderRadius.circular(RadiusTokens.xl),
        boxShadow: [
          BoxShadow(
            color: SemanticColors.primary.withOpacity(0.3),
            blurRadius: 20,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Padding(
        padding: Insets.cardPadding,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    Icon(
                      walletType.icon,
                      color: Colors.white,
                      size: 24,
                    ),
                    Gaps.sm,
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          walletType.displayName,
                          style: AppTypography.labelMedium.copyWith(
                            color: Colors.white.withOpacity(0.8),
                          ),
                        ),
                        Row(
                          children: [
                            Container(
                              width: 8,
                              height: 8,
                              decoration: BoxDecoration(
                                color: _statusColor,
                                shape: BoxShape.circle,
                              ),
                            ),
                            Gaps.xs,
                            Text(
                              _statusLabel,
                              style: AppTypography.labelSmall.copyWith(
                                color: Colors.white.withOpacity(0.6),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ],
                ),
                if (onDisconnect != null)
                  IconButton(
                    onPressed: onDisconnect,
                    icon: const Icon(Icons.logout, color: Colors.white70),
                    tooltip: 'Disconnect',
                  ),
              ],
            ),
            Gaps.xl,

            // Address
            GestureDetector(
              onTap: () {
                Clipboard.setData(ClipboardData(text: address));
                onCopyAddress?.call();
              },
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: SpacingTokens.md,
                  vertical: SpacingTokens.sm,
                ),
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(RadiusTokens.md),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      _formattedAddress,
                      style: AppTypography.bodyMedium.copyWith(
                        color: Colors.white,
                        fontFamily: 'monospace',
                      ),
                    ),
                    Gaps.sm,
                    Icon(
                      Icons.copy,
                      size: 16,
                      color: Colors.white.withOpacity(0.7),
                    ),
                  ],
                ),
              ),
            ),
            Gaps.xl,

            // Balance
            Text(
              'Balance',
              style: AppTypography.labelMedium.copyWith(
                color: Colors.white.withOpacity(0.7),
              ),
            ),
            Gaps.xs,
            Row(
              crossAxisAlignment: CrossAxisAlignment.baseline,
              textBaseline: TextBaseline.alphabetic,
              children: [
                Text(
                  balance,
                  style: AppTypography.displaySmall.copyWith(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                Gaps.sm,
                Text(
                  tokenSymbol,
                  style: AppTypography.titleMedium.copyWith(
                    color: Colors.white.withOpacity(0.8),
                  ),
                ),
              ],
            ),
            if (usdValue != null) ...[
              Gaps.xs,
              Text(
                '≈ \$$usdValue USD',
                style: AppTypography.bodyMedium.copyWith(
                  color: Colors.white.withOpacity(0.6),
                ),
              ),
            ],

            // Trust score
            if (trustScore != null) ...[
              Gaps.lg,
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: SpacingTokens.md,
                  vertical: SpacingTokens.sm,
                ),
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(RadiusTokens.md),
                ),
                child: Row(
                  children: [
                    Icon(
                      Icons.verified_user,
                      size: 16,
                      color: Colors.white.withOpacity(0.8),
                    ),
                    Gaps.sm,
                    Text(
                      'Trust Score: ${trustScore!.toInt()}%',
                      style: AppTypography.labelMedium.copyWith(
                        color: Colors.white,
                      ),
                    ),
                  ],
                ),
              ),
            ],
            Gaps.xl,

            // Action buttons
            Row(
              children: [
                if (onSend != null)
                  Expanded(
                    child: _WalletActionButton(
                      icon: Icons.arrow_upward,
                      label: 'Send',
                      onPressed: onSend!,
                    ),
                  ),
                if (onSend != null && onReceive != null) Gaps.md,
                if (onReceive != null)
                  Expanded(
                    child: _WalletActionButton(
                      icon: Icons.arrow_downward,
                      label: 'Receive',
                      onPressed: onReceive!,
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _WalletActionButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onPressed;

  const _WalletActionButton({
    required this.icon,
    required this.label,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white.withOpacity(0.15),
      borderRadius: BorderRadius.circular(RadiusTokens.md),
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(RadiusTokens.md),
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: SpacingTokens.lg,
            vertical: SpacingTokens.md,
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, size: 18, color: Colors.white),
              Gaps.sm,
              Text(
                label,
                style: AppTypography.labelMedium.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Wallet selector for connection
class AppWalletSelector extends StatelessWidget {
  final List<WalletType> availableWallets;
  final ValueChanged<WalletType> onSelect;
  final WalletType? selectedWallet;
  final bool isConnecting;

  const AppWalletSelector({
    super.key,
    this.availableWallets = const [
      WalletType.metamask,
      WalletType.walletConnect,
      WalletType.coinbase,
      WalletType.rainbow,
      WalletType.trust,
      WalletType.ledger,
    ],
    required this.onSelect,
    this.selectedWallet,
    this.isConnecting = false,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          'Connect Wallet',
          style: AppTypography.headlineSmall.copyWith(
            color: SemanticColors.textPrimary,
          ),
        ),
        Gaps.xs,
        Text(
          'Select a wallet to connect to AMTTP',
          style: AppTypography.bodyMedium.copyWith(
            color: SemanticColors.textSecondary,
          ),
        ),
        Gaps.xl,
        ...availableWallets.map((wallet) {
          final isSelected = wallet == selectedWallet;
          return Padding(
            padding: const EdgeInsets.only(bottom: SpacingTokens.sm),
            child: _WalletOption(
              wallet: wallet,
              isSelected: isSelected,
              isConnecting: isSelected && isConnecting,
              onTap: () => onSelect(wallet),
            ),
          );
        }),
      ],
    );
  }
}

class _WalletOption extends StatelessWidget {
  final WalletType wallet;
  final bool isSelected;
  final bool isConnecting;
  final VoidCallback onTap;

  const _WalletOption({
    required this.wallet,
    required this.isSelected,
    required this.isConnecting,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: isSelected
          ? SemanticColors.primary.withOpacity(0.1)
          : SemanticColors.surfaceElevated,
      borderRadius: BorderRadius.circular(RadiusTokens.md),
      child: InkWell(
        onTap: isConnecting ? null : onTap,
        borderRadius: BorderRadius.circular(RadiusTokens.md),
        child: Container(
          padding: Insets.cardPadding,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(RadiusTokens.md),
            border: Border.all(
              color: isSelected
                  ? SemanticColors.primary
                  : SemanticColors.border,
              width: isSelected ? 2 : 1,
            ),
          ),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(SpacingTokens.sm),
                decoration: BoxDecoration(
                  color: SemanticColors.surface,
                  borderRadius: BorderRadius.circular(RadiusTokens.sm),
                ),
                child: Icon(
                  wallet.icon,
                  size: 24,
                  color: isSelected
                      ? SemanticColors.primary
                      : SemanticColors.textSecondary,
                ),
              ),
              Gaps.md,
              Expanded(
                child: Text(
                  wallet.displayName,
                  style: AppTypography.bodyMedium.copyWith(
                    color: SemanticColors.textPrimary,
                    fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
                  ),
                ),
              ),
              if (isConnecting)
                SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    valueColor: AlwaysStoppedAnimation(SemanticColors.primary),
                  ),
                )
              else if (isSelected)
                Icon(
                  Icons.check_circle,
                  color: SemanticColors.primary,
                  size: 24,
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Compact wallet address display
class AppWalletAddress extends StatelessWidget {
  final String address;
  final WalletType? walletType;
  final bool showCopyButton;
  final bool truncate;
  final VoidCallback? onCopy;

  const AppWalletAddress({
    super.key,
    required this.address,
    this.walletType,
    this.showCopyButton = true,
    this.truncate = true,
    this.onCopy,
  });

  String get _displayAddress {
    if (!truncate) return address;
    if (address.length > 12) {
      return '${address.substring(0, 6)}...${address.substring(address.length - 4)}';
    }
    return address;
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: showCopyButton
          ? () {
              Clipboard.setData(ClipboardData(text: address));
              onCopy?.call();
            }
          : null,
      child: Container(
        padding: const EdgeInsets.symmetric(
          horizontal: SpacingTokens.sm,
          vertical: SpacingTokens.xs,
        ),
        decoration: BoxDecoration(
          color: SemanticColors.surface,
          borderRadius: BorderRadius.circular(RadiusTokens.sm),
          border: Border.all(color: SemanticColors.border),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (walletType != null) ...[
              Icon(
                walletType!.icon,
                size: 16,
                color: SemanticColors.textSecondary,
              ),
              Gaps.xs,
            ],
            Text(
              _displayAddress,
              style: AppTypography.bodySmall.copyWith(
                color: SemanticColors.textPrimary,
                fontFamily: 'monospace',
              ),
            ),
            if (showCopyButton) ...[
              Gaps.xs,
              Icon(
                Icons.copy,
                size: 14,
                color: SemanticColors.textTertiary,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Token balance display
class AppTokenBalance extends StatelessWidget {
  final String balance;
  final String symbol;
  final String? usdValue;
  final String? iconUrl;
  final double? change24h;
  final VoidCallback? onTap;

  const AppTokenBalance({
    super.key,
    required this.balance,
    required this.symbol,
    this.usdValue,
    this.iconUrl,
    this.change24h,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final isPositiveChange = change24h != null && change24h! > 0;
    final changeColor = isPositiveChange
        ? SemanticColors.statusSuccess
        : SemanticColors.statusError;

    return AppListTile(
      leading: Container(
        width: 40,
        height: 40,
        decoration: BoxDecoration(
          color: SemanticColors.surface,
          shape: BoxShape.circle,
          border: Border.all(color: SemanticColors.border),
        ),
        child: Center(
          child: Text(
            symbol.length > 2 ? symbol.substring(0, 2) : symbol,
            style: AppTypography.labelMedium.copyWith(
              color: SemanticColors.textPrimary,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
      ),
      title: symbol,
      subtitle: usdValue != null ? '\$$usdValue' : null,
      trailing: Column(
        crossAxisAlignment: CrossAxisAlignment.end,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            balance,
            style: AppTypography.bodyMedium.copyWith(
              color: SemanticColors.textPrimary,
              fontWeight: FontWeight.w500,
            ),
          ),
          if (change24h != null) ...[
            Gaps.xxs,
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  isPositiveChange ? Icons.trending_up : Icons.trending_down,
                  size: 14,
                  color: changeColor,
                ),
                Gaps.xxs,
                Text(
                  '${isPositiveChange ? '+' : ''}${change24h!.toStringAsFixed(2)}%',
                  style: AppTypography.labelSmall.copyWith(
                    color: changeColor,
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
      onTap: onTap,
    );
  }
}
