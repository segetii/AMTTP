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
  static const Color background = Color(0xFF030712);          // --background: #030712 (gray-950)
  static const Color foreground = Color(0xFFF9FAFB);          // --foreground: #f9fafb (gray-50)
  
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
  static const Color indigo300 = Color(0xFFA5B4FC);            // Added for selection states
  static const Color indigo400 = Color(0xFF818CF8);            // Added for nav active state
  static const Color indigo500 = Color(0xFF6366F1);
  static const Color indigo600 = Color(0xFF4F46E5);
  static const Color indigo700 = Color(0xFF4338CA);
  
  static const Color blue50 = Color(0xFFEFF6FF);
  static const Color blue100 = Color(0xFFDBEAFE);
  static const Color blue400 = Color(0xFF60A5FA);              // Added for KPI
  static const Color blue500 = Color(0xFF3B82F6);
  static const Color blue600 = Color(0xFF2563EB);
  
  static const Color purple300 = Color(0xFFC4B5FD);            // Added for visualization
  static const Color purple400 = Color(0xFFA78BFA);            // Added for KPI
  static const Color purple500 = Color(0xFF8B5CF6);            // Added for role color
  static const Color purple600 = Color(0xFF7C3AED);            // Added for drawer
  static const Color purple700 = Color(0xFF6D28D9);            // Added for visualization
  static const Color purple900 = Color(0xFF4C1D95);            // Added for visualization
  
  static const Color cyan500 = Color(0xFF06B6D4);
  static const Color cyan600 = Color(0xFF0891B2);
  
  // === Red Palette Extended ===
  static const Color red400 = Color(0xFFF87171);               // Added for KPI/warning
  
  // === Amber Palette Extended ===
  static const Color amber400 = Color(0xFFFBBF24);             // Added for KPI
  static const Color amber700 = Color(0xFFB45309);             // Added for compliance
  
  // === Green Palette Extended ===
  static const Color green400 = Color(0xFF4ADE80);             // Added for success states
  
  // === Legacy Aliases (for backward compatibility) ===
  static const Color backgroundDarkOps = slate900;            // War Room bg
  static const Color darkOpsBackground = Color(0xFF0B0E14);   // Per Ground Truth spec
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
  
  static const Color integrityLock = cyan500;
  
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
  static const Color premiumGold = Color(0xFFFBBF24);         // amber-400
  static const Color infoBlue = blue500;
  static const Color accentPink = Color(0xFFEC4899);          // pink-500
  
  // Glassmorphism Colors
  static const Color glassWhite = Color(0x40FFFFFF);
  static const Color glassDark = Color(0x30000000);

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

  // Modern Box Shadows
  static List<BoxShadow> softShadow = [
    BoxShadow(
      color: primaryPurple.withOpacity(0.15),
      blurRadius: 20,
      offset: const Offset(0, 10),
    ),
  ];
  
  static List<BoxShadow> cardShadow = [
    BoxShadow(
      color: Colors.black.withOpacity(0.05),
      blurRadius: 10,
      offset: const Offset(0, 4),
    ),
  ];
  
  static List<BoxShadow> glowShadow = [
    BoxShadow(
      color: primaryPurple.withOpacity(0.4),
      blurRadius: 30,
      spreadRadius: 2,
    ),
  ];

  static ThemeData lightTheme = ThemeData(
    useMaterial3: true,
    brightness: Brightness.light,
    colorScheme: const ColorScheme.light(
      primary: indigo600,          // Indigo-600 brand color
      secondary: indigo100,        // Indigo-100 support
      tertiary: premiumGold,       // Premium features
      error: red500,               // Red-500 errors
      surface: cleanWhite,         // White surfaces
      onPrimary: cleanWhite,       // White on indigo
      onSecondary: gray900,        // Dark text on light
      onSurface: gray900,          // Dark text on surfaces
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
        color: gray900,                  // text-gray-900
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
        color: gray700,                  // text-gray-700
        fontFamily: 'Inter',
      ),
      bodyMedium: TextStyle(
        fontSize: 14,
        fontWeight: FontWeight.normal,
        color: gray600,                  // text-gray-600
        fontFamily: 'Inter',
      ),
      bodySmall: TextStyle(
        fontSize: 12,
        fontWeight: FontWeight.normal,
        color: gray500,                  // text-gray-500
        fontFamily: 'Inter',
      ),
    ),
    
    fontFamily: 'Inter',
  );

  static ThemeData darkTheme = ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    colorScheme: const ColorScheme.dark(
      primary: indigo600,                // Primary brand
      secondary: cyan500,                // Accent cyan
      tertiary: premiumGold,             // Gold premium features
      error: red500,                     // Tailwind red-500
      surface: slate800,                 // slate-800 cards
      onPrimary: cleanWhite,
      onSecondary: slate900,
      onSurface: slate100,               // slate-100 text
    ),
    
    // === Scaffold Background (Next.js: bg-slate-900) ===
    scaffoldBackgroundColor: slate900,
    
    // === App Bar Theme (Dark Ops) ===
    appBarTheme: const AppBarTheme(
      backgroundColor: slate900,
      foregroundColor: slate100,
      elevation: 0,
      scrolledUnderElevation: 1,
      centerTitle: false,
    ),
    
    // === Card Theme (Next.js: bg-slate-800 border-slate-700) ===
    cardTheme: CardThemeData(
      color: slate800,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: const BorderSide(color: slate700),
      ),
    ),
    
    // === Elevated Button Theme ===
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: indigo600,
        foregroundColor: cleanWhite,
        elevation: 0,
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8),
        ),
      ),
    ),
    
    // === Text Theme (Tailwind Typography) ===
    textTheme: const TextTheme(
      headlineLarge: TextStyle(
        fontSize: 24,
        fontWeight: FontWeight.bold,
        color: slate100,                  // text-slate-100
        fontFamily: 'Inter',
      ),
      headlineMedium: TextStyle(
        fontSize: 20,
        fontWeight: FontWeight.bold,
        color: slate100,
        fontFamily: 'Inter',
      ),
      headlineSmall: TextStyle(
        fontSize: 16,
        fontWeight: FontWeight.w600,
        color: slate100,
        fontFamily: 'Inter',
      ),
      titleLarge: TextStyle(
        fontSize: 20,
        fontWeight: FontWeight.w600,
        color: slate100,
        fontFamily: 'Inter',
      ),
      titleMedium: TextStyle(
        fontSize: 16,
        fontWeight: FontWeight.w500,
        color: slate100,
        fontFamily: 'Inter',
      ),
      titleSmall: TextStyle(
        fontSize: 14,
        fontWeight: FontWeight.w500,
        color: slate300,                  // text-slate-300
        fontFamily: 'Inter',
      ),
      bodyLarge: TextStyle(
        fontSize: 16,
        fontWeight: FontWeight.normal,
        color: slate100,
        fontFamily: 'Inter',
      ),
      bodyMedium: TextStyle(
        fontSize: 14,
        fontWeight: FontWeight.normal,
        color: slate300,                  // text-slate-300
        fontFamily: 'Inter',
      ),
      bodySmall: TextStyle(
        fontSize: 12,
        fontWeight: FontWeight.normal,
        color: slate400,                  // text-slate-400
        fontFamily: 'Inter',
      ),
      labelLarge: TextStyle(
        fontSize: 14,
        fontWeight: FontWeight.w600,
        color: slate100,
        fontFamily: 'Inter',
      ),
      labelMedium: TextStyle(
        fontSize: 12,
        fontWeight: FontWeight.w500,
        color: slate400,
        fontFamily: 'Inter',
      ),
      labelSmall: TextStyle(
        fontSize: 12,
        fontWeight: FontWeight.w500,
        color: slate400,
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
    if (riskScore < 0.4) return green500;     // green-500
    if (riskScore < 0.7) return amber500;     // amber-500
    return red500;                             // red-500
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