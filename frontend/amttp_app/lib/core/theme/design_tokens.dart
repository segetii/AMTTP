/// Design Tokens - Cross-Platform Consistency
/// 
/// These tokens are synchronized with:
/// - Next.js: frontend/design-tokens.json
/// - Tailwind: tailwind.config.js
/// 
/// Naming Convention: category_variant_state
/// Example: color_primary_default, spacing_md, radius_lg
library;

import 'package:flutter/material.dart';

/// Color tokens synchronized with Next.js/Tailwind
abstract class ColorTokens {
  // ═══════════════════════════════════════════════════════════════════════════
  // BRAND COLORS
  // ═══════════════════════════════════════════════════════════════════════════
  
  /// Primary brand color (indigo-600)
  static const Color primary = Color(0xFF4F46E5);
  static const Color primaryHover = Color(0xFF4338CA);
  static const Color primaryLight = Color(0xFFE0E7FF);
  static const Color primaryDark = Color(0xFF3730A3);
  
  /// Secondary accent (cyan-500)
  static const Color accent = Color(0xFF06B6D4);
  static const Color accentLight = Color(0xFFCFFAFE);
  
  // ═══════════════════════════════════════════════════════════════════════════
  // SEMANTIC COLORS
  // ═══════════════════════════════════════════════════════════════════════════
  
  /// Success states (green)
  static const Color success = Color(0xFF22C55E);
  static const Color successLight = Color(0xFFDCFCE7);
  static const Color successDark = Color(0xFF16A34A);
  
  /// Warning states (amber)
  static const Color warning = Color(0xFFF59E0B);
  static const Color warningLight = Color(0xFFFEF3C7);
  static const Color warningDark = Color(0xFFD97706);
  
  /// Error/Danger states (red)
  static const Color error = Color(0xFFEF4444);
  static const Color errorLight = Color(0xFFFEE2E2);
  static const Color errorDark = Color(0xFFDC2626);
  
  /// Info states (blue)
  static const Color info = Color(0xFF3B82F6);
  static const Color infoLight = Color(0xFFDBEAFE);
  static const Color infoDark = Color(0xFF2563EB);
  
  // ═══════════════════════════════════════════════════════════════════════════
  // RISK COLORS (Protocol-specific)
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const Color riskLow = Color(0xFF22C55E);       // green-500
  static const Color riskMedium = Color(0xFFF59E0B);    // amber-500
  static const Color riskHigh = Color(0xFFEF4444);      // red-500
  static const Color riskCritical = Color(0xFF7F1D1D); // red-900
  
  // ═══════════════════════════════════════════════════════════════════════════
  // SURFACE COLORS (Dark Theme - Default)
  // ═══════════════════════════════════════════════════════════════════════════
  
  /// App background
  static const Color background = Color(0xFF030712);     // gray-950
  
  /// Card/Surface background
  static const Color surface = Color(0xFF0F172A);        // slate-900
  static const Color surfaceElevated = Color(0xFF1E293B); // slate-800
  
  /// Borders
  static const Color border = Color(0xFF334155);         // slate-700
  static const Color borderSubtle = Color(0xFF1E293B);   // slate-800
  
  // ═══════════════════════════════════════════════════════════════════════════
  // TEXT COLORS
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const Color textPrimary = Color(0xFFF9FAFB);    // gray-50
  static const Color textSecondary = Color(0xFF94A3B8);  // slate-400
  static const Color textMuted = Color(0xFF64748B);      // slate-500
  static const Color textDisabled = Color(0xFF475569);   // slate-600
  
  // ═══════════════════════════════════════════════════════════════════════════
  // LIGHT THEME OVERRIDES
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const Color lightBackground = Color(0xFFF9FAFB);  // gray-50
  static const Color lightSurface = Color(0xFFFFFFFF);     // white
  static const Color lightBorder = Color(0xFFE5E7EB);      // gray-200
  static const Color lightTextPrimary = Color(0xFF111827); // gray-900
  static const Color lightTextSecondary = Color(0xFF6B7280); // gray-500
}

/// Spacing tokens (8px base unit)
abstract class SpacingTokens {
  static const double xs = 4.0;    // 0.5 unit
  static const double sm = 8.0;    // 1 unit
  static const double md = 16.0;   // 2 units
  static const double lg = 24.0;   // 3 units
  static const double xl = 32.0;   // 4 units
  static const double xxl = 48.0;  // 6 units
  static const double xxxl = 64.0; // 8 units
  
  /// Page padding
  static const double pagePadding = 16.0;
  
  /// Card padding
  static const double cardPadding = 16.0;
  
  /// Section gap
  static const double sectionGap = 24.0;
}

/// Border radius tokens
abstract class RadiusTokens {
  static const double none = 0.0;
  static const double sm = 4.0;
  static const double md = 8.0;
  static const double lg = 12.0;
  static const double xl = 16.0;
  static const double xxl = 24.0;
  static const double full = 9999.0;
  
  /// Standard card radius
  static const double card = 12.0;
  
  /// Button radius
  static const double button = 8.0;
  
  /// Input field radius
  static const double input = 8.0;
  
  /// Chip/Tag radius
  static const double chip = 9999.0;
}

/// Shadow tokens
abstract class ShadowTokens {
  static const List<BoxShadow> none = [];
  
  static const List<BoxShadow> sm = [
    BoxShadow(
      color: Color(0x0A000000),
      blurRadius: 4,
      offset: Offset(0, 1),
    ),
  ];
  
  static const List<BoxShadow> md = [
    BoxShadow(
      color: Color(0x14000000),
      blurRadius: 8,
      offset: Offset(0, 4),
    ),
  ];
  
  static const List<BoxShadow> lg = [
    BoxShadow(
      color: Color(0x1A000000),
      blurRadius: 16,
      offset: Offset(0, 8),
    ),
  ];
  
  /// Glow effect for primary elements
  static List<BoxShadow> primaryGlow = [
    BoxShadow(
      color: ColorTokens.primary.withOpacity(0.3),
      blurRadius: 12,
      offset: const Offset(0, 4),
    ),
  ];
}

/// Animation duration tokens
abstract class DurationTokens {
  static const Duration instant = Duration.zero;
  static const Duration fast = Duration(milliseconds: 150);
  static const Duration normal = Duration(milliseconds: 250);
  static const Duration slow = Duration(milliseconds: 400);
  static const Duration slower = Duration(milliseconds: 600);
}

/// Animation curve tokens
abstract class CurveTokens {
  static const Curve ease = Curves.easeInOut;
  static const Curve easeIn = Curves.easeIn;
  static const Curve easeOut = Curves.easeOut;
  static const Curve spring = Curves.elasticOut;
}
