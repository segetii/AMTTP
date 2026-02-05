/// Standard App Components - Consistent UI Building Blocks
/// 
/// These components follow the design system and should be used
/// throughout the app for consistency.

import 'package:flutter/material.dart';
import '../../core/theme/design_tokens.dart';
import '../../core/theme/typography.dart';
import '../../core/theme/spacing.dart';

// ═══════════════════════════════════════════════════════════════════════════════
// APP CARD
// ═══════════════════════════════════════════════════════════════════════════════

/// Standard card component with consistent styling
class AppCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry? padding;
  final VoidCallback? onTap;
  final Color? backgroundColor;
  final List<BoxShadow>? shadow;
  final double? borderRadius;
  final Border? border;
  
  const AppCard({
    super.key,
    required this.child,
    this.padding,
    this.onTap,
    this.backgroundColor,
    this.shadow,
    this.borderRadius,
    this.border,
  });
  
  @override
  Widget build(BuildContext context) {
    final card = Container(
      padding: padding ?? Insets.card,
      decoration: BoxDecoration(
        color: backgroundColor ?? ColorTokens.surface,
        borderRadius: BorderRadius.circular(borderRadius ?? RadiusTokens.card),
        border: border ?? Border.all(color: ColorTokens.border, width: 1),
        boxShadow: shadow ?? ShadowTokens.sm,
      ),
      child: child,
    );
    
    if (onTap != null) {
      return GestureDetector(
        onTap: onTap,
        child: card,
      );
    }
    
    return card;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// APP BUTTON
// ═══════════════════════════════════════════════════════════════════════════════

enum AppButtonVariant { primary, secondary, outline, ghost, danger }
enum AppButtonSize { small, medium, large }

/// Standard button component
class AppButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final AppButtonVariant variant;
  final AppButtonSize size;
  final IconData? icon;
  final bool isLoading;
  final bool isFullWidth;
  
  const AppButton({
    super.key,
    required this.label,
    this.onPressed,
    this.variant = AppButtonVariant.primary,
    this.size = AppButtonSize.medium,
    this.icon,
    this.isLoading = false,
    this.isFullWidth = false,
  });
  
  @override
  Widget build(BuildContext context) {
    // Size configurations
    final (double height, double fontSize, EdgeInsets padding) = switch (size) {
      AppButtonSize.small => (32.0, 12.0, const EdgeInsets.symmetric(horizontal: 12, vertical: 6)),
      AppButtonSize.medium => (44.0, 14.0, const EdgeInsets.symmetric(horizontal: 16, vertical: 10)),
      AppButtonSize.large => (52.0, 16.0, const EdgeInsets.symmetric(horizontal: 20, vertical: 14)),
    };
    
    // Variant configurations
    final (Color bgColor, Color textColor, Color borderColor) = switch (variant) {
      AppButtonVariant.primary => (ColorTokens.primary, Colors.white, Colors.transparent),
      AppButtonVariant.secondary => (ColorTokens.surfaceElevated, ColorTokens.textPrimary, Colors.transparent),
      AppButtonVariant.outline => (Colors.transparent, ColorTokens.textPrimary, ColorTokens.border),
      AppButtonVariant.ghost => (Colors.transparent, ColorTokens.textSecondary, Colors.transparent),
      AppButtonVariant.danger => (ColorTokens.error, Colors.white, Colors.transparent),
    };
    
    final Widget content = Row(
      mainAxisSize: isFullWidth ? MainAxisSize.max : MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        if (isLoading) ...[
          SizedBox(
            width: fontSize,
            height: fontSize,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              valueColor: AlwaysStoppedAnimation(textColor),
            ),
          ),
          Gaps.h8,
        ] else if (icon != null) ...[
          Icon(icon, size: fontSize + 2, color: textColor),
          Gaps.h8,
        ],
        Text(
          label,
          style: TextStyle(
            fontSize: fontSize,
            fontWeight: FontWeight.w600,
            color: textColor,
          ),
        ),
      ],
    );
    
    return SizedBox(
      width: isFullWidth ? double.infinity : null,
      height: height,
      child: Material(
        color: bgColor,
        borderRadius: BorderRadius.circular(RadiusTokens.button),
        child: InkWell(
          onTap: isLoading ? null : onPressed,
          borderRadius: BorderRadius.circular(RadiusTokens.button),
          child: Container(
            padding: padding,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(RadiusTokens.button),
              border: Border.all(color: borderColor),
            ),
            child: content,
          ),
        ),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// APP TEXT FIELD
// ═══════════════════════════════════════════════════════════════════════════════

/// Standard text input component
class AppTextField extends StatelessWidget {
  final String? label;
  final String? hint;
  final String? error;
  final TextEditingController? controller;
  final ValueChanged<String>? onChanged;
  final TextInputType keyboardType;
  final bool obscureText;
  final Widget? prefix;
  final Widget? suffix;
  final int maxLines;
  final bool enabled;
  final FocusNode? focusNode;
  
  const AppTextField({
    super.key,
    this.label,
    this.hint,
    this.error,
    this.controller,
    this.onChanged,
    this.keyboardType = TextInputType.text,
    this.obscureText = false,
    this.prefix,
    this.suffix,
    this.maxLines = 1,
    this.enabled = true,
    this.focusNode,
  });
  
  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (label != null) ...[
          Text(label!, style: AppTypography.labelMedium),
          Gaps.v8,
        ],
        Container(
          decoration: BoxDecoration(
            color: ColorTokens.surfaceElevated,
            borderRadius: BorderRadius.circular(RadiusTokens.input),
            border: Border.all(
              color: error != null ? ColorTokens.error : ColorTokens.border,
            ),
          ),
          child: TextField(
            controller: controller,
            onChanged: onChanged,
            keyboardType: keyboardType,
            obscureText: obscureText,
            maxLines: maxLines,
            enabled: enabled,
            focusNode: focusNode,
            style: AppTypography.bodyMedium,
            decoration: InputDecoration(
              hintText: hint,
              hintStyle: AppTypography.bodyMedium.copyWith(
                color: ColorTokens.textMuted,
              ),
              prefixIcon: prefix,
              suffixIcon: suffix,
              contentPadding: Insets.input,
              border: InputBorder.none,
            ),
          ),
        ),
        if (error != null) ...[
          Gaps.v4,
          Text(
            error!,
            style: AppTypography.caption.copyWith(color: ColorTokens.error),
          ),
        ],
      ],
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// STATUS BADGE
// ═══════════════════════════════════════════════════════════════════════════════

enum StatusBadgeType { success, warning, error, info, neutral }

/// Status indicator badge
class StatusBadge extends StatelessWidget {
  final String label;
  final StatusBadgeType type;
  final IconData? icon;
  
  const StatusBadge({
    super.key,
    required this.label,
    this.type = StatusBadgeType.neutral,
    this.icon,
  });
  
  @override
  Widget build(BuildContext context) {
    final (Color bgColor, Color textColor) = switch (type) {
      StatusBadgeType.success => (ColorTokens.successLight, ColorTokens.successDark),
      StatusBadgeType.warning => (ColorTokens.warningLight, ColorTokens.warningDark),
      StatusBadgeType.error => (ColorTokens.errorLight, ColorTokens.errorDark),
      StatusBadgeType.info => (ColorTokens.infoLight, ColorTokens.infoDark),
      StatusBadgeType.neutral => (ColorTokens.surfaceElevated, ColorTokens.textSecondary),
    };
    
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(RadiusTokens.chip),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 12, color: textColor),
            Gaps.h4,
          ],
          Text(
            label,
            style: AppTypography.labelSmall.copyWith(color: textColor),
          ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// RISK SCORE INDICATOR
// ═══════════════════════════════════════════════════════════════════════════════

/// Visual risk score indicator
class RiskScoreIndicator extends StatelessWidget {
  final double score; // 0.0 - 1.0
  final bool showLabel;
  final double size;
  
  const RiskScoreIndicator({
    super.key,
    required this.score,
    this.showLabel = true,
    this.size = 48,
  });
  
  Color get color {
    if (score < 0.4) return ColorTokens.riskLow;
    if (score < 0.7) return ColorTokens.riskMedium;
    return ColorTokens.riskHigh;
  }
  
  String get label {
    if (score < 0.4) return 'Low';
    if (score < 0.7) return 'Medium';
    return 'High';
  }
  
  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          width: size,
          height: size,
          child: Stack(
            alignment: Alignment.center,
            children: [
              CircularProgressIndicator(
                value: score,
                strokeWidth: 4,
                backgroundColor: ColorTokens.border,
                valueColor: AlwaysStoppedAnimation(color),
              ),
              Text(
                '${(score * 100).toInt()}',
                style: TextStyle(
                  fontSize: size * 0.3,
                  fontWeight: FontWeight.bold,
                  color: color,
                ),
              ),
            ],
          ),
        ),
        if (showLabel) ...[
          Gaps.v8,
          StatusBadge(
            label: label,
            type: score < 0.4
                ? StatusBadgeType.success
                : score < 0.7
                    ? StatusBadgeType.warning
                    : StatusBadgeType.error,
          ),
        ],
      ],
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// ADDRESS DISPLAY
// ═══════════════════════════════════════════════════════════════════════════════

/// Ethereum address display with copy button
class AddressDisplay extends StatelessWidget {
  final String address;
  final bool truncate;
  final VoidCallback? onCopy;
  
  const AddressDisplay({
    super.key,
    required this.address,
    this.truncate = true,
    this.onCopy,
  });
  
  String get displayAddress {
    if (!truncate || address.length <= 16) return address;
    return '${address.substring(0, 6)}...${address.substring(address.length - 4)}';
  }
  
  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(displayAddress, style: AppTypography.address),
        if (onCopy != null) ...[
          Gaps.h8,
          GestureDetector(
            onTap: onCopy,
            child: Icon(
              Icons.copy_rounded,
              size: 16,
              color: ColorTokens.textMuted,
            ),
          ),
        ],
      ],
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// LOADING INDICATOR
// ═══════════════════════════════════════════════════════════════════════════════

/// Consistent loading indicator
class AppLoadingIndicator extends StatelessWidget {
  final double size;
  final Color? color;
  final String? message;
  
  const AppLoadingIndicator({
    super.key,
    this.size = 32,
    this.color,
    this.message,
  });
  
  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            width: size,
            height: size,
            child: CircularProgressIndicator(
              strokeWidth: 3,
              valueColor: AlwaysStoppedAnimation(
                color ?? ColorTokens.primary,
              ),
            ),
          ),
          if (message != null) ...[
            Gaps.v16,
            Text(
              message!,
              style: AppTypography.bodySmall,
              textAlign: TextAlign.center,
            ),
          ],
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// EMPTY STATE
// ═══════════════════════════════════════════════════════════════════════════════

/// Empty state placeholder
class EmptyState extends StatelessWidget {
  final IconData icon;
  final String title;
  final String? description;
  final String? actionLabel;
  final VoidCallback? onAction;
  
  const EmptyState({
    super.key,
    required this.icon,
    required this.title,
    this.description,
    this.actionLabel,
    this.onAction,
  });
  
  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: Insets.lg,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 80,
              height: 80,
              decoration: BoxDecoration(
                color: ColorTokens.surfaceElevated,
                borderRadius: BorderRadius.circular(40),
              ),
              child: Icon(
                icon,
                size: 40,
                color: ColorTokens.textMuted,
              ),
            ),
            Gaps.v24,
            Text(
              title,
              style: AppTypography.headlineMedium,
              textAlign: TextAlign.center,
            ),
            if (description != null) ...[
              Gaps.v8,
              Text(
                description!,
                style: AppTypography.bodyMedium.copyWith(
                  color: ColorTokens.textSecondary,
                ),
                textAlign: TextAlign.center,
              ),
            ],
            if (actionLabel != null && onAction != null) ...[
              Gaps.v24,
              AppButton(
                label: actionLabel!,
                onPressed: onAction,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// SECTION HEADER
// ═══════════════════════════════════════════════════════════════════════════════

/// Section header with optional action
class SectionHeader extends StatelessWidget {
  final String title;
  final String? subtitle;
  final String? actionLabel;
  final VoidCallback? onAction;
  
  const SectionHeader({
    super.key,
    required this.title,
    this.subtitle,
    this.actionLabel,
    this.onAction,
  });
  
  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: AppTypography.headlineSmall),
              if (subtitle != null) ...[
                Gaps.v4,
                Text(
                  subtitle!,
                  style: AppTypography.bodySmall,
                ),
              ],
            ],
          ),
        ),
        if (actionLabel != null && onAction != null)
          TextButton(
            onPressed: onAction,
            child: Text(actionLabel!),
          ),
      ],
    );
  }
}
