import 'package:flutter/material.dart';

/// AMTTP Theme - Aligned with Next.js Tailwind CSS Theme
///
/// Design Tokens (Unified with Next.js):
/// - Background: #030712 (gray-950)
/// - Foreground: #f9fafb (gray-50)
/// - Slate palette for War Room dark mode
/// - Risk colors: red-500, amber-500, green-500
/// - Primary: indigo-600 (#4f46e5)
///
/// Typography:
/// - Primary: Inter / Geist Sans
/// - Monospace: JetBrains Mono / Geist Mono

class AppTheme {
  // ═══════════════════════════════════════════════════════════════════════════
  // 🎨 NEXT.JS TAILWIND COLOR PALETTE (Unified)
  // ═══════════════════════════════════════════════════════════════════════════

  // === Base Colors (from globals.css) ===
  static const Color background =
      Color(0xFF030712); // --background: #030712 (gray-950)
  static const Color foreground =
      Color(0xFFF9FAFB); // --foreground: #f9fafb (gray-50)

  // === Slate Palette (War Room Dark Mode) ===
  static const Color slate50 = Color(0xFFF8FAFC);
  static const Color slate100 = Color(0xFFF1F5F9);
  static const Color slate200 = Color(0xFFE2E8F0);
  static const Color slate300 = Color(0xFFCBD5E1);
  static const Color slate400 = Color(0xFF94A3B8);
  static const Color slate500 = Color(0xFF64748B);
  static const Color slate600 = Color(0xFF475569);
  static const Color slate700 = Color(0xFF334155);
  static const Color slate800 = Color(0xFF1E293B);
  static const Color slate900 = Color(0xFF0F172A);
  static const Color slate950 = Color(0xFF020617);

  // === Gray Palette (Focus Mode Light) ===
  static const Color gray50 = Color(0xFFF9FAFB);
  static const Color gray100 = Color(0xFFF3F4F6);
  static const Color gray200 = Color(0xFFE5E7EB);
  static const Color gray300 = Color(0xFFD1D5DB);
  static const Color gray400 = Color(0xFF9CA3AF);
  static const Color gray500 = Color(0xFF6B7280);
  static const Color gray600 = Color(0xFF4B5563);
  static const Color gray700 = Color(0xFF374151);
  static const Color gray800 = Color(0xFF1F2937);
  static const Color gray900 = Color(0xFF111827);
  static const Color gray950 = Color(0xFF030712);

  // === Status Colors (Tailwind) ===
  static const Color red50 = Color(0xFFFEF2F2);
  static const Color red100 = Color(0xFFFEE2E2);
  static const Color red500 = Color(0xFFEF4444);
  static const Color red600 = Color(0xFFDC2626);
  static const Color red900 = Color(0xFF7F1D1D);

  static const Color amber50 = Color(0xFFFFFBEB);
  static const Color amber100 = Color(0xFFFEF3C7);
  static const Color amber500 = Color(0xFFF59E0B);
  static const Color amber600 = Color(0xFFD97706);
  static const Color amber900 = Color(0xFF78350F);

  static const Color green50 = Color(0xFFF0FDF4);
  static const Color green100 = Color(0xFFDCFCE7);
  static const Color green500 = Color(0xFF22C55E);
  static const Color green600 = Color(0xFF16A34A);
  static const Color green900 = Color(0xFF14532D);

  // === Primary Colors (Indigo/Blue) ===
  static const Color indigo50 = Color(0xFFEEF2FF);
  static const Color indigo100 = Color(0xFFE0E7FF);
  static const Color indigo300 =
      Color(0xFFA5B4FC); // Added for selection states
  static const Color indigo400 =
      Color(0xFF818CF8); // Added for nav active state
  static const Color indigo500 = Color(0xFF6366F1);
  static const Color indigo600 = Color(0xFF4F46E5);
  static const Color indigo700 = Color(0xFF4338CA);

  static const Color blue50 = Color(0xFFEFF6FF);
  static const Color blue100 = Color(0xFFDBEAFE);
  static const Color blue400 = Color(0xFF60A5FA); // Added for KPI
  static const Color blue500 = Color(0xFF3B82F6);
  static const Color blue600 = Color(0xFF2563EB);

  static const Color purple300 = Color(0xFFC4B5FD); // Added for visualization
  static const Color purple400 = Color(0xFFA78BFA); // Added for KPI
  static const Color purple500 = Color(0xFF8B5CF6); // Added for role color
  static const Color purple600 = Color(0xFF7C3AED); // Added for drawer
  static const Color purple700 = Color(0xFF6D28D9); // Added for visualization
  static const Color purple900 = Color(0xFF4C1D95); // Added for visualization

  static const Color cyan500 = Color(0xFF06B6D4);
  static const Color cyan600 = Color(0xFF0891B2);

  // === Red Palette Extended ===
  static const Color red400 = Color(0xFFF87171); // Added for KPI/warning

  // === Amber Palette Extended ===
  static const Color amber400 = Color(0xFFFBBF24); // Added for KPI
  static const Color amber700 = Color(0xFFB45309); // Added for compliance

  // === Green Palette Extended ===
  static const Color green400 = Color(0xFF4ADE80); // Added for success states

  // === Legacy Aliases (for backward compatibility) ===
  static const Color backgroundDarkOps = slate900; // War Room bg
  static const Color darkOpsBackground =
      Color(0xFF0B0E14); // Per Ground Truth spec
  static const Color darkBg = slate900;
  static const Color darkCard = slate800;
  static const Color darkSurface = slate700;

  static const Color textPrimary = slate100;
  static const Color textSecondary = slate400;
  static const Color cleanWhite = Color(0xFFFFFFFF);

  // === Risk Status Colors (Tailwind mapped) ===
  static const Color riskHigh = red500;
  static const Color riskMedium = amber500;
  static const Color riskLow = green500;

  // === Cross-Stack Tokens (matches frontend/design-tokens.json) ===
  static const Color tokenPrimary = Color(0xFF6366F1);
  static const Color tokenPrimarySoft = Color(0xFF8B5CF6);
  static const Color tokenPrimaryLight = indigo400; // Nav active, links
  static const Color tokenBackground = Color(0xFF0A0A0F);
  static const Color tokenSurface = Color(0xFF12121A);
  static const Color tokenSurfaceDeep =
      Color(0xFF0F172A); // Deeper cards (slate-950)
  static const Color tokenCardElevated =
      Color(0xFF1A1A2E); // Elevated cards, popups
  static const Color tokenBorderSubtle = Color(0xFF1E1E2E);
  static const Color tokenBorderStrong = Color(0xFF2D2D44); // Prominent borders
  static const Color tokenText = Color(0xFFFFFFFF);
  static const Color tokenMutedText = Color(0xFF9CA3AF);
  static const Color tokenSuccess = Color(0xFF22C55E);
  static const Color tokenWarning = Color(0xFFF59E0B);
  static const Color tokenDanger = Color(0xFFEF4444);
  static const Color tokenDangerStrong = Color(0xFFDC2626); // red-600
  static const Color tokenPeP = Color(0xFFF97316); // orange-500 (PEP accent)
  static const Color tokenPePLight = Color(0xFFFB923C); // orange-400

  // === Gradient Stops ===
  static const Color tokenGradientCard = Color(0xFF1E1E3F); // Wallet card top
  static const Color tokenGradientDark =
      Color(0xFF0F0F2D); // Wallet card bottom
  static const Color tokenGradientBgTop = Color(0xFF0F0F1A); // Home page top

  // === Brand Colors (3rd-party) ===
  static const Color brandETH = Color(0xFF627EEA);
  static const Color brandMetaMask = Color(0xFFF6851B);
  static const Color brandWalletConnect = Color(0xFF3B99FC);
  static const Color brandCoinbase = Color(0xFF0052FF);
  static const Color brandUSDC = Color(0xFF2775CA);
  static const Color brandUSDT = Color(0xFF26A17B);

  // === Teal / Emerald (extended palette) ===
  static const Color teal500 = Color(0xFF14B8A6);
  static const Color emerald500 = Color(0xFF10B981);
  static const Color orange500 = Color(0xFFF97316);
  static const Color orange400 = Color(0xFFFB923C);
  static const Color pink500 = Color(0xFFEC4899);

  static const Color integrityLock = cyan500;

  // ═══════════════════════════════════════════════════════════════════════════
  // 📐 DESIGN SCALE CONSTANTS
  // ═══════════════════════════════════════════════════════════════════════════

  // === Border Radius Scale (4 levels) ===
  static const double radiusSm = 8.0;
  static const double radiusMd = 12.0;
  static const double radiusLg = 16.0;
  static const double radiusXl = 24.0;

  // === Spacing Scale (8px grid) ===
  static const double space4 = 4.0;
  static const double space8 = 8.0;
  static const double space12 = 12.0;
  static const double space16 = 16.0;
  static const double space20 = 20.0;
  static const double space24 = 24.0;
  static const double space32 = 32.0;
  static const double space48 = 48.0;

  // === Spacing Widgets (convenience) ===
  static const SizedBox gap4 = SizedBox(height: 4);
  static const SizedBox gap8 = SizedBox(height: 8);
  static const SizedBox gap12 = SizedBox(height: 12);
  static const SizedBox gap16 = SizedBox(height: 16);
  static const SizedBox gap24 = SizedBox(height: 24);
  static const SizedBox gap32 = SizedBox(height: 32);
  static const SizedBox hGap4 = SizedBox(width: 4);
  static const SizedBox hGap8 = SizedBox(width: 8);
  static const SizedBox hGap12 = SizedBox(width: 12);
  static const SizedBox hGap16 = SizedBox(width: 16);

  // === ETH Price (single source of truth) ===
  static const double ethUsdPrice = 2580.0;

  // === Semantic Aliases ===
  static const Color dangerRed = red500;
  static const Color warningOrange = amber500;
  static const Color successGreen = green500;
  static const Color errorRed = red500;
  static const Color neonGreen = green500;
  static const Color neonBlue = cyan500;
  static const Color warningYellow = amber500;

  // === Primary Brand Color ===
  static const Color primaryBlue = indigo600;
  static const Color primaryPurple = indigo600;
  static const Color primaryPurpleLight = indigo100;
  static const Color accentCyan = cyan500;

  // === Light Theme Colors (Focus Mode) ===
  static const Color lightAsh = gray50;
  static const Color mediumAsh = gray200;
  static const Color darkAsh = gray700;

  // === Legacy Aliases ===
  static const Color secondaryBlue = indigo100;
  static const Color accentGreen = green500;
  static const Color backgroundGrey = gray50;
  static const Color surfaceWhite = cleanWhite;
  static const Color textDark = gray900;
  static const Color textMedium = gray500;
  static const Color textLight = gray400;
  static const Color mutedText = slate400;
  static const Color cardBg = slate800;
  static const Color supportLilac = indigo100;
  static const Color premiumGold = Color(0xFFFBBF24); // amber-400
  static const Color infoBlue = blue500;
  static const Color accentPink = Color(0xFFEC4899); // pink-500

  // Glassmorphism Colors
  static const Color glassWhite = Color(0x40FFFFFF);
  static const Color glassDark = Color(0x30000000);

  // === Standardized Shadows (3 levels) ===
  static const List<BoxShadow> shadowSm = [
    BoxShadow(color: Color(0x14000000), blurRadius: 8, offset: Offset(0, 2)),
  ];
  static const List<BoxShadow> shadowMd = [
    BoxShadow(color: Color(0x26000000), blurRadius: 16, offset: Offset(0, 8)),
  ];
  static const List<BoxShadow> shadowLg = [
    BoxShadow(color: Color(0x33000000), blurRadius: 28, offset: Offset(0, 14)),
  ];
  static List<BoxShadow> shadowGlow(Color color) => [
        BoxShadow(
            color: Color.fromRGBO(
                color.r.toInt(), color.g.toInt(), color.b.toInt(), 0.35),
            blurRadius: 20,
            offset: const Offset(0, 8)),
      ];

  // ═══════════════════════════════════════════════════════════════════════════
  // 🎨 GRADIENTS
  // ═══════════════════════════════════════════════════════════════════════════

  // Modern Gradients
  static const LinearGradient primaryGradient = LinearGradient(
    colors: [primaryBlue, integrityLock],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const LinearGradient premiumGradient = LinearGradient(
    colors: [primaryBlue, accentPink],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  /// Dark Ops gradient - per Ground Truth spec
  static const LinearGradient darkGradient = LinearGradient(
    colors: [backgroundDarkOps, Color(0xFF0D1117)],
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
  );

  static const LinearGradient goldGradient = LinearGradient(
    colors: [premiumGold, Color(0xFFF97316)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  // Background gradient for secure widgets
  static const LinearGradient backgroundGradient = darkGradient;

  // Modern Box Shadows (legacy — prefer shadowSm/shadowMd/shadowLg)
  static List<BoxShadow> softShadow = shadowMd;
  static List<BoxShadow> cardShadow = shadowSm;
  static List<BoxShadow> glowShadow = [
    BoxShadow(
      color: primaryPurple.withAlpha(102),
      blurRadius: 30,
      spreadRadius: 2,
    ),
  ];

  static ThemeData lightTheme = ThemeData(
    useMaterial3: true,
    brightness: Brightness.light,
    colorScheme: const ColorScheme.light(
      primary: indigo600, // Indigo-600 brand color
      secondary: indigo100, // Indigo-100 support
      tertiary: premiumGold, // Premium features
      error: red500, // Red-500 errors
      surface: cleanWhite, // White surfaces
      onPrimary: cleanWhite, // White on indigo
      onSecondary: gray900, // Dark text on light
      onSurface: gray900, // Dark text on surfaces
    ),

    // === Scaffold Background (Next.js: bg-white) ===
    scaffoldBackgroundColor: cleanWhite,

    // App Bar Theme (Next.js Focus Mode: clean white)
    appBarTheme: const AppBarTheme(
      backgroundColor: cleanWhite,
      foregroundColor: gray900,
      elevation: 0,
      scrolledUnderElevation: 1,
      centerTitle: true,
    ),

    // Card Theme (Next.js: bg-white shadow)
    cardTheme: CardThemeData(
      color: cleanWhite,
      elevation: 2,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: const BorderSide(color: gray200, width: 0.5),
      ),
    ),

    // Elevated Button Theme
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: indigo600,
        foregroundColor: cleanWhite,
        elevation: 2,
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8),
        ),
      ),
    ),

    // Outlined Button Theme
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: indigo600,
        side: const BorderSide(color: indigo600, width: 1.5),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8),
        ),
      ),
    ),

    // Text Button Theme
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: indigo600,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      ),
    ),

    // Input Decoration Theme (Next.js: bg-gray-50 border-gray-200)
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: gray50,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: const BorderSide(color: gray200),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: const BorderSide(color: gray200),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: const BorderSide(color: indigo600, width: 2),
      ),
    ),

    // Text Theme (Next.js: text-gray-900, text-gray-600, text-gray-500)
    textTheme: const TextTheme(
      headlineLarge: TextStyle(
        fontSize: 32,
        fontWeight: FontWeight.bold,
        color: gray900, // text-gray-900
        fontFamily: 'Inter',
      ),
      headlineMedium: TextStyle(
        fontSize: 28,
        fontWeight: FontWeight.bold,
        color: gray900,
        fontFamily: 'Inter',
      ),
      headlineSmall: TextStyle(
        fontSize: 24,
        fontWeight: FontWeight.w600,
        color: gray900,
        fontFamily: 'Inter',
      ),
      titleLarge: TextStyle(
        fontSize: 20,
        fontWeight: FontWeight.w600,
        color: gray900,
        fontFamily: 'Inter',
      ),
      titleMedium: TextStyle(
        fontSize: 16,
        fontWeight: FontWeight.w500,
        color: gray900,
        fontFamily: 'Inter',
      ),
      bodyLarge: TextStyle(
        fontSize: 16,
        fontWeight: FontWeight.normal,
        color: gray700, // text-gray-700
        fontFamily: 'Inter',
      ),
      bodyMedium: TextStyle(
        fontSize: 14,
        fontWeight: FontWeight.normal,
        color: gray600, // text-gray-600
        fontFamily: 'Inter',
      ),
      bodySmall: TextStyle(
        fontSize: 12,
        fontWeight: FontWeight.normal,
        color: gray500, // text-gray-500
        fontFamily: 'Inter',
      ),
    ),

    fontFamily: 'Inter',
  );

  static ThemeData darkTheme = ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    colorScheme: const ColorScheme.dark(
      primary: tokenPrimary, // Token primary
      secondary: tokenPrimarySoft, // Softer primary
      tertiary: premiumGold, // Gold premium features
      error: tokenDanger, // Danger token
      surface: tokenSurface, // Token surface
      onPrimary: tokenText,
      onSecondary: tokenText,
      onSurface: tokenText, // Text on surfaces
    ),

    // === Scaffold Background (Next.js: bg-slate-900) ===
    scaffoldBackgroundColor: tokenBackground,

    // === App Bar Theme (Dark Ops) ===
    appBarTheme: const AppBarTheme(
      backgroundColor: tokenBackground,
      foregroundColor: tokenText,
      elevation: 0,
      scrolledUnderElevation: 1,
      centerTitle: false,
    ),

    // === Card Theme (Next.js: bg-slate-800 border-slate-700) ===
    cardTheme: CardThemeData(
      color: tokenSurface,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: const BorderSide(color: tokenBorderSubtle),
      ),
    ),

    // === Elevated Button Theme ===
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: tokenPrimary,
        foregroundColor: tokenText,
        elevation: 0,
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8),
        ),
      ),
    ),

    // === Text Theme (Tailwind Typography — sizes match light theme) ===
    textTheme: const TextTheme(
      headlineLarge: TextStyle(
        fontSize: 32,
        fontWeight: FontWeight.bold,
        color: slate100,
        fontFamily: 'Inter',
      ),
      headlineMedium: TextStyle(
        fontSize: 28,
        fontWeight: FontWeight.bold,
        color: slate100,
        fontFamily: 'Inter',
      ),
      headlineSmall: TextStyle(
        fontSize: 24,
        fontWeight: FontWeight.w600,
        color: slate100,
        fontFamily: 'Inter',
      ),
      titleLarge: TextStyle(
        fontSize: 20,
        color: slate100, // text-slate-100
        fontFamily: 'Inter',
      ),
      titleMedium: TextStyle(
        fontSize: 16,
        color: slate100, // text-slate-100
        fontFamily: 'Inter',
      ),
      titleSmall: TextStyle(
        fontSize: 14,
        color: slate300, // text-slate-300 (muted)
        fontFamily: 'Inter',
      ),
      bodyLarge: TextStyle(
        fontSize: 16,
        color: slate100, // text-slate-100
        fontFamily: 'Inter',
      ),
      bodyMedium: TextStyle(
        fontSize: 14,
        color: slate300, // text-slate-300 (muted)
        fontFamily: 'Inter',
      ),
      bodySmall: TextStyle(
        fontSize: 12,
        color: slate400, // text-slate-400 (muted)
        fontFamily: 'Inter',
      ),
      labelLarge: TextStyle(
        fontSize: 14,
        color: slate100, // text-slate-100
        fontFamily: 'Inter',
      ),
      labelMedium: TextStyle(
        fontSize: 12,
        color: slate400, // text-slate-400 (muted)
        fontFamily: 'Inter',
      ),
      labelSmall: TextStyle(
        fontSize: 12,
        color: slate400, // text-slate-400 (muted)
        letterSpacing: 0.5,
        fontFamily: 'Inter',
      ),
    ),

    fontFamily: 'Inter',
  );

  // ═══════════════════════════════════════════════════════════════════════════
  // 🎯 RISK LEVEL HELPERS (Tailwind Colors)
  // ═══════════════════════════════════════════════════════════════════════════

  /// Get risk color per Tailwind palette
  static Color getRiskColor(double riskScore) {
    if (riskScore < 0.4) return green500; // green-500
    if (riskScore < 0.7) return amber500; // amber-500
    return red500; // red-500
  }

  static String getRiskLabel(double riskScore) {
    if (riskScore < 0.4) return 'Low Risk';
    if (riskScore < 0.7) return 'Medium Risk';
    if (riskScore < 0.8) return 'High Risk';
    return 'Very High Risk';
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 🔤 TYPOGRAPHY HELPERS (Ground Truth: JetBrains Mono for hashes)
  // ═══════════════════════════════════════════════════════════════════════════

  /// Monospace style for hashes, addresses, numerical data
  static const TextStyle monoStyle = TextStyle(
    fontFamily: 'JetBrains Mono',
    fontSize: 12,
    color: textPrimary,
  );

  /// Hash display style (truncated)
  static const TextStyle hashStyle = TextStyle(
    fontFamily: 'JetBrains Mono',
    fontSize: 12,
    color: textSecondary,
    letterSpacing: 0.5,
  );

  /// Address display style
  static const TextStyle addressStyle = TextStyle(
    fontFamily: 'JetBrains Mono',
    fontSize: 13,
    color: textPrimary,
    fontWeight: FontWeight.w500,
  );
}
