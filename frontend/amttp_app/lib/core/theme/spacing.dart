/// Spacing Utilities - Consistent Gaps and Padding
/// 
/// Usage:
/// ```dart
/// Padding(padding: Insets.pagePadding, child: ...)
/// SizedBox(height: Gaps.md)
/// ```
library;

import 'package:flutter/material.dart';
import 'design_tokens.dart';

/// Insets (EdgeInsets) for padding
abstract class Insets {
  /// Zero padding
  static const EdgeInsets zero = EdgeInsets.zero;
  
  /// Extra small: 4px all around
  static const EdgeInsets xs = EdgeInsets.all(SpacingTokens.xs);
  
  /// Small: 8px all around
  static const EdgeInsets sm = EdgeInsets.all(SpacingTokens.sm);
  
  /// Medium: 16px all around
  static const EdgeInsets md = EdgeInsets.all(SpacingTokens.md);
  
  /// Large: 24px all around
  static const EdgeInsets lg = EdgeInsets.all(SpacingTokens.lg);
  
  /// Extra large: 32px all around
  static const EdgeInsets xl = EdgeInsets.all(SpacingTokens.xl);
  
  /// Standard page padding
  static const EdgeInsets page = EdgeInsets.symmetric(
    horizontal: SpacingTokens.pagePadding,
    vertical: SpacingTokens.md,
  );
  
  /// Card internal padding
  static const EdgeInsets card = EdgeInsets.all(SpacingTokens.cardPadding);
  
  /// Horizontal only - small
  static const EdgeInsets horizontalSm = EdgeInsets.symmetric(
    horizontal: SpacingTokens.sm,
  );
  
  /// Horizontal only - medium
  static const EdgeInsets horizontalMd = EdgeInsets.symmetric(
    horizontal: SpacingTokens.md,
  );
  
  /// Vertical only - small
  static const EdgeInsets verticalSm = EdgeInsets.symmetric(
    vertical: SpacingTokens.sm,
  );
  
  /// Vertical only - medium
  static const EdgeInsets verticalMd = EdgeInsets.symmetric(
    vertical: SpacingTokens.md,
  );
  
  /// Button padding
  static const EdgeInsets button = EdgeInsets.symmetric(
    horizontal: SpacingTokens.md,
    vertical: SpacingTokens.sm,
  );
  
  /// Input field padding
  static const EdgeInsets input = EdgeInsets.symmetric(
    horizontal: SpacingTokens.md,
    vertical: SpacingTokens.sm + 2,
  );
}

/// Gaps (SizedBox) for spacing between elements
abstract class Gaps {
  // ═══════════════════════════════════════════════════════════════════════════
  // VERTICAL GAPS
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const SizedBox v4 = SizedBox(height: 4);
  static const SizedBox v8 = SizedBox(height: 8);
  static const SizedBox v12 = SizedBox(height: 12);
  static const SizedBox v16 = SizedBox(height: 16);
  static const SizedBox v20 = SizedBox(height: 20);
  static const SizedBox v24 = SizedBox(height: 24);
  static const SizedBox v32 = SizedBox(height: 32);
  static const SizedBox v48 = SizedBox(height: 48);
  static const SizedBox v64 = SizedBox(height: 64);
  
  // Semantic aliases
  static const SizedBox vXs = v4;
  static const SizedBox vSm = v8;
  static const SizedBox vMd = v16;
  static const SizedBox vLg = v24;
  static const SizedBox vXl = v32;
  
  // ═══════════════════════════════════════════════════════════════════════════
  // HORIZONTAL GAPS
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const SizedBox h4 = SizedBox(width: 4);
  static const SizedBox h8 = SizedBox(width: 8);
  static const SizedBox h12 = SizedBox(width: 12);
  static const SizedBox h16 = SizedBox(width: 16);
  static const SizedBox h20 = SizedBox(width: 20);
  static const SizedBox h24 = SizedBox(width: 24);
  static const SizedBox h32 = SizedBox(width: 32);
  static const SizedBox h48 = SizedBox(width: 48);
  
  // Semantic aliases
  static const SizedBox hXs = h4;
  static const SizedBox hSm = h8;
  static const SizedBox hMd = h16;
  static const SizedBox hLg = h24;
  static const SizedBox hXl = h32;
  
  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION GAPS
  // ═══════════════════════════════════════════════════════════════════════════
  
  /// Gap between sections
  static const SizedBox section = SizedBox(height: SpacingTokens.sectionGap);
  
  /// Gap between cards
  static const SizedBox card = SizedBox(height: 16);
  
  /// Gap between list items
  static const SizedBox listItem = SizedBox(height: 12);
}

/// Dividers with consistent styling
abstract class AppDividers {
  static const Divider thin = Divider(
    height: 1,
    thickness: 1,
    color: ColorTokens.border,
  );
  
  static const Divider subtle = Divider(
    height: 1,
    thickness: 1,
    color: ColorTokens.borderSubtle,
  );
  
  static const VerticalDivider vertical = VerticalDivider(
    width: 1,
    thickness: 1,
    color: ColorTokens.border,
  );
}
