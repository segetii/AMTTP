/// Typography - Standardized Text Styles
/// 
/// Usage:
/// ```dart
/// Text('Hello', style: AppTypography.headlineLarge)
/// Text('Body text', style: AppTypography.bodyMedium)
/// ```

import 'package:flutter/material.dart';
import 'design_tokens.dart';

/// Standard typography for the app
abstract class AppTypography {
  // ═══════════════════════════════════════════════════════════════════════════
  // FONT FAMILIES
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const String fontFamily = 'Inter';
  static const String monoFontFamily = 'JetBrains Mono';
  
  // ═══════════════════════════════════════════════════════════════════════════
  // DISPLAY STYLES (Hero text, landing pages)
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const TextStyle displayLarge = TextStyle(
    fontSize: 48,
    fontWeight: FontWeight.w700,
    height: 1.1,
    letterSpacing: -0.5,
    color: ColorTokens.textPrimary,
  );
  
  static const TextStyle displayMedium = TextStyle(
    fontSize: 36,
    fontWeight: FontWeight.w700,
    height: 1.15,
    letterSpacing: -0.3,
    color: ColorTokens.textPrimary,
  );
  
  static const TextStyle displaySmall = TextStyle(
    fontSize: 28,
    fontWeight: FontWeight.w600,
    height: 1.2,
    color: ColorTokens.textPrimary,
  );
  
  // ═══════════════════════════════════════════════════════════════════════════
  // HEADLINE STYLES (Page titles, section headers)
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const TextStyle headlineLarge = TextStyle(
    fontSize: 24,
    fontWeight: FontWeight.w600,
    height: 1.25,
    color: ColorTokens.textPrimary,
  );
  
  static const TextStyle headlineMedium = TextStyle(
    fontSize: 20,
    fontWeight: FontWeight.w600,
    height: 1.3,
    color: ColorTokens.textPrimary,
  );
  
  static const TextStyle headlineSmall = TextStyle(
    fontSize: 18,
    fontWeight: FontWeight.w600,
    height: 1.35,
    color: ColorTokens.textPrimary,
  );
  
  // ═══════════════════════════════════════════════════════════════════════════
  // TITLE STYLES (Cards, dialogs)
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const TextStyle titleLarge = TextStyle(
    fontSize: 18,
    fontWeight: FontWeight.w600,
    height: 1.4,
    color: ColorTokens.textPrimary,
  );
  
  static const TextStyle titleMedium = TextStyle(
    fontSize: 16,
    fontWeight: FontWeight.w600,
    height: 1.4,
    color: ColorTokens.textPrimary,
  );
  
  static const TextStyle titleSmall = TextStyle(
    fontSize: 14,
    fontWeight: FontWeight.w600,
    height: 1.4,
    color: ColorTokens.textPrimary,
  );
  
  // ═══════════════════════════════════════════════════════════════════════════
  // BODY STYLES (Content, paragraphs)
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const TextStyle bodyLarge = TextStyle(
    fontSize: 16,
    fontWeight: FontWeight.w400,
    height: 1.5,
    color: ColorTokens.textPrimary,
  );
  
  static const TextStyle bodyMedium = TextStyle(
    fontSize: 14,
    fontWeight: FontWeight.w400,
    height: 1.5,
    color: ColorTokens.textPrimary,
  );
  
  static const TextStyle bodySmall = TextStyle(
    fontSize: 12,
    fontWeight: FontWeight.w400,
    height: 1.5,
    color: ColorTokens.textSecondary,
  );
  
  // ═══════════════════════════════════════════════════════════════════════════
  // LABEL STYLES (Buttons, inputs, chips)
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const TextStyle labelLarge = TextStyle(
    fontSize: 14,
    fontWeight: FontWeight.w600,
    height: 1.4,
    letterSpacing: 0.1,
    color: ColorTokens.textPrimary,
  );
  
  static const TextStyle labelMedium = TextStyle(
    fontSize: 12,
    fontWeight: FontWeight.w500,
    height: 1.4,
    letterSpacing: 0.1,
    color: ColorTokens.textPrimary,
  );
  
  static const TextStyle labelSmall = TextStyle(
    fontSize: 11,
    fontWeight: FontWeight.w500,
    height: 1.4,
    letterSpacing: 0.1,
    color: ColorTokens.textSecondary,
  );
  
  // ═══════════════════════════════════════════════════════════════════════════
  // CAPTION & OVERLINE
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const TextStyle caption = TextStyle(
    fontSize: 12,
    fontWeight: FontWeight.w400,
    height: 1.4,
    color: ColorTokens.textMuted,
  );
  
  static const TextStyle overline = TextStyle(
    fontSize: 10,
    fontWeight: FontWeight.w600,
    height: 1.4,
    letterSpacing: 1.0,
    color: ColorTokens.textMuted,
  );
  
  // ═══════════════════════════════════════════════════════════════════════════
  // MONOSPACE (Code, addresses, amounts)
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const TextStyle monoLarge = TextStyle(
    fontFamily: monoFontFamily,
    fontSize: 16,
    fontWeight: FontWeight.w500,
    height: 1.5,
    color: ColorTokens.textPrimary,
  );
  
  static const TextStyle monoMedium = TextStyle(
    fontFamily: monoFontFamily,
    fontSize: 14,
    fontWeight: FontWeight.w500,
    height: 1.5,
    color: ColorTokens.textPrimary,
  );
  
  static const TextStyle monoSmall = TextStyle(
    fontFamily: monoFontFamily,
    fontSize: 12,
    fontWeight: FontWeight.w500,
    height: 1.5,
    color: ColorTokens.textSecondary,
  );
  
  // ═══════════════════════════════════════════════════════════════════════════
  // SPECIALIZED STYLES
  // ═══════════════════════════════════════════════════════════════════════════
  
  /// Wallet address display
  static const TextStyle address = TextStyle(
    fontFamily: monoFontFamily,
    fontSize: 13,
    fontWeight: FontWeight.w500,
    letterSpacing: 0.5,
    color: ColorTokens.textSecondary,
  );
  
  /// Large amount display (balance, price)
  static const TextStyle amount = TextStyle(
    fontSize: 32,
    fontWeight: FontWeight.w700,
    height: 1.1,
    color: ColorTokens.textPrimary,
  );
  
  /// Risk score display
  static TextStyle riskScore(double score) {
    Color color;
    if (score < 0.4) {
      color = ColorTokens.riskLow;
    } else if (score < 0.7) {
      color = ColorTokens.riskMedium;
    } else {
      color = ColorTokens.riskHigh;
    }
    
    return TextStyle(
      fontSize: 24,
      fontWeight: FontWeight.w700,
      color: color,
    );
  }
}
