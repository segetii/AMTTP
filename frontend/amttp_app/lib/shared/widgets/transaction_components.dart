import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../core/theme/design_tokens.dart';
import '../../core/theme/typography.dart';
import '../../core/theme/spacing.dart';
import 'app_components.dart';

/// Transaction status enumeration
enum TransactionStatus {
  pending,
  processing,
  confirmed,
  failed,
  cancelled,
}

/// Extension for transaction status helpers
extension TransactionStatusX on TransactionStatus {
  String get label {
    switch (this) {
      case TransactionStatus.pending:
        return 'Pending';
      case TransactionStatus.processing:
        return 'Processing';
      case TransactionStatus.confirmed:
        return 'Confirmed';
      case TransactionStatus.failed:
        return 'Failed';
      case TransactionStatus.cancelled:
        return 'Cancelled';
    }
  }

  Color get color {
    switch (this) {
      case TransactionStatus.pending:
        return SemanticColors.statusWarning;
      case TransactionStatus.processing:
        return SemanticColors.primary;
      case TransactionStatus.confirmed:
        return SemanticColors.statusSuccess;
      case TransactionStatus.failed:
        return SemanticColors.statusError;
      case TransactionStatus.cancelled:
        return SemanticColors.textTertiary;
    }
  }

  IconData get icon {
    switch (this) {
      case TransactionStatus.pending:
        return Icons.schedule;
      case TransactionStatus.processing:
        return Icons.sync;
      case TransactionStatus.failed:
        return Icons.error_outline;
      case TransactionStatus.confirmed:
        return Icons.check_circle_outline;
      case TransactionStatus.cancelled:
        return Icons.cancel_outlined;
    }
  }
}

/// Transaction card showing transfer details
class AppTransactionCard extends StatelessWidget {
  final String transactionId;
  final String fromAddress;
  final String toAddress;
  final String amount;
  final String? tokenSymbol;
  final TransactionStatus status;
  final DateTime timestamp;
  final double? riskScore;
  final VoidCallback? onTap;
  final VoidCallback? onCopyId;

  const AppTransactionCard({
    super.key,
    required this.transactionId,
    required this.fromAddress,
    required this.toAddress,
    required this.amount,
    this.tokenSymbol = 'ETH',
    required this.status,
    required this.timestamp,
    this.riskScore,
    this.onTap,
    this.onCopyId,
  });

  String _formatAddress(String address) {
    if (address.length > 12) {
      return '${address.substring(0, 6)}...${address.substring(address.length - 4)}';
    }
    return address;
  }

  String _formatTimestamp(DateTime dt) {
    final now = DateTime.now();
    final diff = now.difference(dt);

    if (diff.inMinutes < 1) return 'Just now';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    if (diff.inDays < 7) return '${diff.inDays}d ago';
    return '${dt.day}/${dt.month}/${dt.year}';
  }

  @override
  Widget build(BuildContext context) {
    return AppCard(
      onTap: onTap,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(SpacingTokens.sm),
                decoration: BoxDecoration(
                  color: status.color.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(RadiusTokens.sm),
                ),
                child: Icon(
                  status.icon,
                  color: status.color,
                  size: 20,
                ),
              ),
              Gaps.md,
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: GestureDetector(
                            onTap: () {
                              Clipboard.setData(
                                  ClipboardData(text: transactionId));
                              onCopyId?.call();
                            },
                            child: Row(
                              children: [
                                Text(
                                  _formatAddress(transactionId),
                                  style: AppTypography.bodyMedium.copyWith(
                                    color: SemanticColors.textPrimary,
                                    fontFamily: 'monospace',
                                  ),
                                ),
                                Gaps.xs,
                                Icon(
                                  Icons.copy,
                                  size: 14,
                                  color: SemanticColors.textTertiary,
                                ),
                              ],
                            ),
                          ),
                        ),
                        AppStatusBadge(
                          label: status.label,
                          status: _mapStatus(status),
                        ),
                      ],
                    ),
                    Gaps.xxs,
                    Text(
                      _formatTimestamp(timestamp),
                      style: AppTypography.labelSmall.copyWith(
                        color: SemanticColors.textTertiary,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          Gaps.lg,

          // Transfer details
          Container(
            padding: Insets.cardPadding,
            decoration: BoxDecoration(
              color: SemanticColors.surface,
              borderRadius: BorderRadius.circular(RadiusTokens.md),
            ),
            child: Column(
              children: [
                _AddressRow(
                  label: 'From',
                  address: fromAddress,
                  icon: Icons.arrow_upward,
                  iconColor: SemanticColors.statusError,
                ),
                Gaps.sm,
                Container(
                  height: 24,
                  alignment: Alignment.center,
                  child: Icon(
                    Icons.arrow_downward,
                    size: 16,
                    color: SemanticColors.textTertiary,
                  ),
                ),
                Gaps.sm,
                _AddressRow(
                  label: 'To',
                  address: toAddress,
                  icon: Icons.arrow_downward,
                  iconColor: SemanticColors.statusSuccess,
                ),
              ],
            ),
          ),
          Gaps.lg,

          // Amount and risk
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Amount',
                    style: AppTypography.labelSmall.copyWith(
                      color: SemanticColors.textTertiary,
                    ),
                  ),
                  Gaps.xxs,
                  Text(
                    '$amount $tokenSymbol',
                    style: AppTypography.titleMedium.copyWith(
                      color: SemanticColors.textPrimary,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
              if (riskScore != null)
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      'Risk Score',
                      style: AppTypography.labelSmall.copyWith(
                        color: SemanticColors.textTertiary,
                      ),
                    ),
                    Gaps.xxs,
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: SpacingTokens.sm,
                        vertical: SpacingTokens.xxs,
                      ),
                      decoration: BoxDecoration(
                        color:
                            RiskColors.fromScore(riskScore!).withOpacity(0.1),
                        borderRadius: BorderRadius.circular(RadiusTokens.sm),
                      ),
                      child: Text(
                        '${riskScore!.toInt()}%',
                        style: AppTypography.bodyMedium.copyWith(
                          color: RiskColors.fromScore(riskScore!),
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                  ],
                ),
            ],
          ),
        ],
      ),
    );
  }

  BadgeStatus _mapStatus(TransactionStatus status) {
    switch (status) {
      case TransactionStatus.confirmed:
        return BadgeStatus.success;
      case TransactionStatus.pending:
      case TransactionStatus.processing:
        return BadgeStatus.warning;
      case TransactionStatus.failed:
        return BadgeStatus.error;
      case TransactionStatus.cancelled:
        return BadgeStatus.neutral;
    }
  }
}

class _AddressRow extends StatelessWidget {
  final String label;
  final String address;
  final IconData icon;
  final Color iconColor;

  const _AddressRow({
    required this.label,
    required this.address,
    required this.icon,
    required this.iconColor,
  });

  String _formatAddress(String addr) {
    if (addr.length > 20) {
      return '${addr.substring(0, 10)}...${addr.substring(addr.length - 8)}';
    }
    return addr;
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          padding: const EdgeInsets.all(SpacingTokens.xs),
          decoration: BoxDecoration(
            color: iconColor.withOpacity(0.1),
            shape: BoxShape.circle,
          ),
          child: Icon(icon, size: 12, color: iconColor),
        ),
        Gaps.sm,
        Text(
          label,
          style: AppTypography.labelSmall.copyWith(
            color: SemanticColors.textTertiary,
          ),
        ),
        Gaps.sm,
        Expanded(
          child: Text(
            _formatAddress(address),
            style: AppTypography.bodySmall.copyWith(
              color: SemanticColors.textPrimary,
              fontFamily: 'monospace',
            ),
          ),
        ),
        GestureDetector(
          onTap: () => Clipboard.setData(ClipboardData(text: address)),
          child: Icon(
            Icons.copy,
            size: 14,
            color: SemanticColors.textTertiary,
          ),
        ),
      ],
    );
  }
}

/// Compact transaction list item
class AppTransactionListItem extends StatelessWidget {
  final String transactionId;
  final String amount;
  final String tokenSymbol;
  final TransactionStatus status;
  final DateTime timestamp;
  final bool isSent;
  final VoidCallback? onTap;

  const AppTransactionListItem({
    super.key,
    required this.transactionId,
    required this.amount,
    this.tokenSymbol = 'ETH',
    required this.status,
    required this.timestamp,
    required this.isSent,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return AppListTile(
      leading: Container(
        padding: const EdgeInsets.all(SpacingTokens.sm),
        decoration: BoxDecoration(
          color: (isSent ? SemanticColors.statusError : SemanticColors.statusSuccess)
              .withOpacity(0.1),
          shape: BoxShape.circle,
        ),
        child: Icon(
          isSent ? Icons.arrow_upward : Icons.arrow_downward,
          color: isSent ? SemanticColors.statusError : SemanticColors.statusSuccess,
          size: 20,
        ),
      ),
      title: isSent ? 'Sent' : 'Received',
      subtitle: _formatTimestamp(timestamp),
      trailing: Column(
        crossAxisAlignment: CrossAxisAlignment.end,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            '${isSent ? '-' : '+'}$amount $tokenSymbol',
            style: AppTypography.bodyMedium.copyWith(
              color: isSent
                  ? SemanticColors.statusError
                  : SemanticColors.statusSuccess,
              fontWeight: FontWeight.w600,
            ),
          ),
          Gaps.xxs,
          AppStatusBadge(
            label: status.label,
            status: _mapStatus(status),
          ),
        ],
      ),
      onTap: onTap,
    );
  }

  String _formatTimestamp(DateTime dt) {
    final now = DateTime.now();
    final diff = now.difference(dt);

    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    return '${dt.day}/${dt.month}';
  }

  BadgeStatus _mapStatus(TransactionStatus status) {
    switch (status) {
      case TransactionStatus.confirmed:
        return BadgeStatus.success;
      case TransactionStatus.pending:
      case TransactionStatus.processing:
        return BadgeStatus.warning;
      case TransactionStatus.failed:
        return BadgeStatus.error;
      case TransactionStatus.cancelled:
        return BadgeStatus.neutral;
    }
  }
}

/// Transaction confirmation dialog
class AppTransactionConfirmation extends StatelessWidget {
  final String toAddress;
  final String amount;
  final String tokenSymbol;
  final double? estimatedFee;
  final double? riskScore;
  final List<String>? warnings;
  final VoidCallback onConfirm;
  final VoidCallback onCancel;

  const AppTransactionConfirmation({
    super.key,
    required this.toAddress,
    required this.amount,
    this.tokenSymbol = 'ETH',
    this.estimatedFee,
    this.riskScore,
    this.warnings,
    required this.onConfirm,
    required this.onCancel,
  });

  @override
  Widget build(BuildContext context) {
    final hasHighRisk = riskScore != null && riskScore! >= 70;

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Header icon
        Center(
          child: Container(
            padding: const EdgeInsets.all(SpacingTokens.lg),
            decoration: BoxDecoration(
              color: hasHighRisk
                  ? SemanticColors.statusError.withOpacity(0.1)
                  : SemanticColors.primary.withOpacity(0.1),
              shape: BoxShape.circle,
            ),
            child: Icon(
              hasHighRisk ? Icons.warning_amber : Icons.send,
              size: 48,
              color: hasHighRisk ? SemanticColors.statusError : SemanticColors.primary,
            ),
          ),
        ),
        Gaps.lg,

        // Title
        Text(
          'Confirm Transaction',
          style: AppTypography.headlineSmall.copyWith(
            color: SemanticColors.textPrimary,
          ),
          textAlign: TextAlign.center,
        ),
        Gaps.lg,

        // Details
        Container(
          padding: Insets.cardPadding,
          decoration: BoxDecoration(
            color: SemanticColors.surface,
            borderRadius: BorderRadius.circular(RadiusTokens.md),
          ),
          child: Column(
            children: [
              _DetailRow(label: 'To', value: _formatAddress(toAddress)),
              const Divider(),
              _DetailRow(label: 'Amount', value: '$amount $tokenSymbol'),
              if (estimatedFee != null) ...[
                const Divider(),
                _DetailRow(
                  label: 'Est. Fee',
                  value: '$estimatedFee $tokenSymbol',
                ),
              ],
              if (riskScore != null) ...[
                const Divider(),
                _DetailRow(
                  label: 'Risk Score',
                  value: '${riskScore!.toInt()}%',
                  valueColor: RiskColors.fromScore(riskScore!),
                ),
              ],
            ],
          ),
        ),

        // Warnings
        if (warnings != null && warnings!.isNotEmpty) ...[
          Gaps.md,
          Container(
            padding: Insets.cardPadding,
            decoration: BoxDecoration(
              color: SemanticColors.statusWarning.withOpacity(0.1),
              borderRadius: BorderRadius.circular(RadiusTokens.md),
              border: Border.all(
                color: SemanticColors.statusWarning.withOpacity(0.3),
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(
                      Icons.warning_amber,
                      size: 16,
                      color: SemanticColors.statusWarning,
                    ),
                    Gaps.xs,
                    Text(
                      'Warnings',
                      style: AppTypography.labelMedium.copyWith(
                        color: SemanticColors.statusWarning,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
                Gaps.sm,
                ...warnings!.map((warning) => Padding(
                      padding: const EdgeInsets.only(bottom: SpacingTokens.xs),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '• ',
                            style: AppTypography.bodySmall.copyWith(
                              color: SemanticColors.statusWarning,
                            ),
                          ),
                          Expanded(
                            child: Text(
                              warning,
                              style: AppTypography.bodySmall.copyWith(
                                color: SemanticColors.textSecondary,
                              ),
                            ),
                          ),
                        ],
                      ),
                    )),
              ],
            ),
          ),
        ],
        Gaps.xl,

        // Actions
        Row(
          children: [
            Expanded(
              child: AppButton(
                label: 'Cancel',
                variant: ButtonVariant.secondary,
                onPressed: onCancel,
              ),
            ),
            Gaps.md,
            Expanded(
              child: AppButton(
                label: hasHighRisk ? 'Proceed Anyway' : 'Confirm',
                variant: hasHighRisk ? ButtonVariant.danger : ButtonVariant.primary,
                onPressed: onConfirm,
              ),
            ),
          ],
        ),
      ],
    );
  }

  String _formatAddress(String addr) {
    if (addr.length > 20) {
      return '${addr.substring(0, 10)}...${addr.substring(addr.length - 8)}';
    }
    return addr;
  }
}

class _DetailRow extends StatelessWidget {
  final String label;
  final String value;
  final Color? valueColor;

  const _DetailRow({
    required this.label,
    required this.value,
    this.valueColor,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: SpacingTokens.xs),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: AppTypography.bodyMedium.copyWith(
              color: SemanticColors.textSecondary,
            ),
          ),
          Text(
            value,
            style: AppTypography.bodyMedium.copyWith(
              color: valueColor ?? SemanticColors.textPrimary,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }
}
