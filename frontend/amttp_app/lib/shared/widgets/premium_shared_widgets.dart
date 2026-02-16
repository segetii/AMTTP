/// AMTTP Premium Shared Widgets
///
/// Extracted from duplicate implementations across premium pages.
/// All widgets use AppTheme tokens for consistent styling.
library;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/app_theme.dart';

// ═══════════════════════════════════════════════════════════════════════════════
// PREMIUM HEADER BAR — Consistent back-button header across all premium pages
// ═══════════════════════════════════════════════════════════════════════════════

class PremiumHeaderBar extends StatelessWidget {
  final String title;
  final String? subtitle;
  final List<Widget>? actions;
  final VoidCallback? onBack;
  final Color? titleColor;

  const PremiumHeaderBar({
    super.key,
    required this.title,
    this.subtitle,
    this.actions,
    this.onBack,
    this.titleColor,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(
        horizontal: AppTheme.space16,
        vertical: AppTheme.space12,
      ),
      child: Row(
        children: [
          // Back button
          GestureDetector(
            onTap: onBack ?? () => context.pop(),
            child: Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                color: AppTheme.tokenCardElevated,
                borderRadius: BorderRadius.circular(AppTheme.radiusMd),
                border: Border.all(color: AppTheme.tokenBorderStrong),
              ),
              child: const Icon(
                Icons.arrow_back_rounded,
                color: AppTheme.tokenText,
                size: 20,
              ),
            ),
          ),
          const SizedBox(width: AppTheme.space12),
          // Title + subtitle
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  title,
                  style: TextStyle(
                    color: titleColor ?? AppTheme.tokenText,
                    fontSize: 20,
                    fontWeight: FontWeight.w700,
                    fontFamily: 'Inter',
                  ),
                ),
                if (subtitle != null)
                  Text(
                    subtitle!,
                    style: const TextStyle(
                      color: AppTheme.slate400,
                      fontSize: 14,
                      fontFamily: 'Inter',
                    ),
                  ),
              ],
            ),
          ),
          // Action buttons
          if (actions != null) ...actions!,
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// SHEET HANDLE — Consistent drag indicator for bottom sheets
// ═══════════════════════════════════════════════════════════════════════════════

class SheetHandle extends StatelessWidget {
  const SheetHandle({super.key});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        width: 40,
        height: 4,
        margin: const EdgeInsets.only(
            top: AppTheme.space12, bottom: AppTheme.space8),
        decoration: BoxDecoration(
          color: AppTheme.gray700,
          borderRadius: BorderRadius.circular(2),
        ),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// SCANNER MODAL — Unified QR scanner placeholder modal
// ═══════════════════════════════════════════════════════════════════════════════

class ScannerModal extends StatelessWidget {
  final String title;
  final VoidCallback? onClose;

  const ScannerModal({
    super.key,
    this.title = 'Scan QR Code',
    this.onClose,
  });

  /// Show the scanner as a bottom sheet
  static Future<void> show(BuildContext context,
      {String title = 'Scan QR Code'}) {
    return showModalBottomSheet(
      context: context,
      backgroundColor: AppTheme.tokenSurface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(AppTheme.radiusXl),
        ),
      ),
      builder: (_) => ScannerModal(title: title),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(AppTheme.space24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SheetHandle(),
          const SizedBox(height: AppTheme.space16),
          Text(
            title,
            style: const TextStyle(
              color: AppTheme.tokenText,
              fontSize: 20,
              fontWeight: FontWeight.w700,
              fontFamily: 'Inter',
            ),
          ),
          const SizedBox(height: AppTheme.space24),
          // Scanner placeholder
          Container(
            width: double.infinity,
            height: 200,
            decoration: BoxDecoration(
              color: AppTheme.tokenCardElevated,
              borderRadius: BorderRadius.circular(AppTheme.radiusLg),
              border: Border.all(color: AppTheme.tokenBorderStrong),
            ),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  Icons.qr_code_scanner_rounded,
                  size: 64,
                  color: AppTheme.tokenPrimary.withAlpha(128),
                ),
                const SizedBox(height: AppTheme.space12),
                const Text(
                  'Camera access required',
                  style: TextStyle(
                    color: AppTheme.slate400,
                    fontSize: 14,
                    fontFamily: 'Inter',
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: AppTheme.space16),
          // Enable Camera CTA
          SizedBox(
            width: double.infinity,
            height: 48,
            child: ElevatedButton.icon(
              onPressed: () => Navigator.of(context).pop(),
              icon: const Icon(Icons.camera_alt_rounded, size: 20),
              label: const Text('Enable Camera'),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.tokenPrimary,
                foregroundColor: AppTheme.tokenText,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppTheme.radiusMd),
                ),
                textStyle: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                  fontFamily: 'Inter',
                ),
              ),
            ),
          ),
          const SizedBox(height: AppTheme.space16),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// PREMIUM ERROR STATE — Consistent error display (inline & full-page)
// ═══════════════════════════════════════════════════════════════════════════════

class PremiumErrorState extends StatelessWidget {
  final String message;
  final String? detail;
  final VoidCallback? onRetry;
  final bool fullPage;

  const PremiumErrorState({
    super.key,
    this.message = 'Something went wrong',
    this.detail,
    this.onRetry,
    this.fullPage = false,
  });

  @override
  Widget build(BuildContext context) {
    final content = Column(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Container(
          width: fullPage ? 64 : 40,
          height: fullPage ? 64 : 40,
          decoration: BoxDecoration(
            color: AppTheme.tokenDanger.withAlpha(26),
            borderRadius: BorderRadius.circular(fullPage ? 32 : 20),
          ),
          child: Icon(
            Icons.error_outline_rounded,
            color: AppTheme.tokenDanger,
            size: fullPage ? 32 : 20,
          ),
        ),
        SizedBox(height: fullPage ? AppTheme.space16 : AppTheme.space8),
        Text(
          message,
          textAlign: TextAlign.center,
          style: TextStyle(
            color: AppTheme.tokenText,
            fontSize: fullPage ? 18 : 14,
            fontWeight: FontWeight.w600,
            fontFamily: 'Inter',
          ),
        ),
        if (detail != null) ...[
          const SizedBox(height: AppTheme.space4),
          Text(
            detail!,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: AppTheme.slate400,
              fontSize: 13,
              fontFamily: 'Inter',
            ),
          ),
        ],
        if (onRetry != null) ...[
          SizedBox(height: fullPage ? AppTheme.space16 : AppTheme.space8),
          SizedBox(
            height: 48,
            child: TextButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh_rounded, size: 18),
              label: const Text('Retry'),
              style: TextButton.styleFrom(
                foregroundColor: AppTheme.tokenPrimary,
                textStyle: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  fontFamily: 'Inter',
                ),
              ),
            ),
          ),
        ],
      ],
    );

    if (fullPage) {
      return Center(
          child: Padding(
        padding: const EdgeInsets.all(AppTheme.space32),
        child: content,
      ));
    }

    return Container(
      padding: const EdgeInsets.all(AppTheme.space16),
      decoration: BoxDecoration(
        color: AppTheme.tokenDanger.withAlpha(13),
        borderRadius: BorderRadius.circular(AppTheme.radiusMd),
        border: Border.all(color: AppTheme.tokenDanger.withAlpha(51)),
      ),
      child: content,
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// PREMIUM LOADING SPINNER — Consistent loading indicator
// ═══════════════════════════════════════════════════════════════════════════════

enum SpinnerSize { inline, button, page }

class PremiumSpinner extends StatelessWidget {
  final SpinnerSize size;
  final Color? color;

  const PremiumSpinner({
    super.key,
    this.size = SpinnerSize.button,
    this.color,
  });

  @override
  Widget build(BuildContext context) {
    final double dim;
    final double stroke;
    switch (size) {
      case SpinnerSize.inline:
        dim = 16;
        stroke = 2;
      case SpinnerSize.button:
        dim = 20;
        stroke = 2;
      case SpinnerSize.page:
        dim = 48;
        stroke = 3;
    }

    final widget = SizedBox(
      width: dim,
      height: dim,
      child: CircularProgressIndicator(
        strokeWidth: stroke,
        valueColor: AlwaysStoppedAnimation(color ?? AppTheme.tokenPrimary),
      ),
    );

    if (size == SpinnerSize.page) {
      return Center(child: widget);
    }
    return widget;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// PREMIUM CTA BUTTON — Semantic button replacing GestureDetector pattern
// ═══════════════════════════════════════════════════════════════════════════════

class PremiumCTA extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final bool isLoading;
  final bool isSecondary;
  final IconData? icon;
  final Color? color;
  final double? width;

  const PremiumCTA({
    super.key,
    required this.label,
    this.onPressed,
    this.isLoading = false,
    this.isSecondary = false,
    this.icon,
    this.color,
    this.width,
  });

  @override
  Widget build(BuildContext context) {
    final bg = color ?? AppTheme.tokenPrimary;
    final isDisabled = onPressed == null || isLoading;

    return SizedBox(
      width: width ?? double.infinity,
      height: 52,
      child: ElevatedButton(
        onPressed: isDisabled ? null : onPressed,
        style: ElevatedButton.styleFrom(
          backgroundColor: isSecondary ? AppTheme.tokenCardElevated : bg,
          foregroundColor: AppTheme.tokenText,
          disabledBackgroundColor: bg.withAlpha(77),
          disabledForegroundColor: AppTheme.tokenText.withAlpha(128),
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppTheme.radiusMd),
            side: isSecondary
                ? const BorderSide(color: AppTheme.tokenBorderStrong)
                : BorderSide.none,
          ),
          textStyle: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            fontFamily: 'Inter',
          ),
        ),
        child: isLoading
            ? const PremiumSpinner(
                size: SpinnerSize.button, color: AppTheme.tokenText)
            : Row(
                mainAxisAlignment: MainAxisAlignment.center,
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (icon != null) ...[
                    Icon(icon, size: 20),
                    const SizedBox(width: AppTheme.space8),
                  ],
                  Text(label),
                ],
              ),
      ),
    );
  }
}
