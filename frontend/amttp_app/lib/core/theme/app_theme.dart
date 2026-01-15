import 'package:flutter/material.dart';

class AppTheme {
  // 🎨 Modern AMTTP Color Palette - Sleek & Premium
  
  // Primary Gradient Colors
  static const Color primaryPurple = Color(0xFF7C3AED);      // Vibrant violet
  static const Color primaryPurpleDark = Color(0xFF5B21B6);  // Deep violet
  static const Color primaryPurpleLight = Color(0xFFA78BFA); // Light violet
  
  // Accent Colors
  static const Color accentCyan = Color(0xFF06B6D4);         // Cyan accent
  static const Color accentPink = Color(0xFFEC4899);         // Pink accent
  static const Color supportLilac = Color(0xFFDDD6FE);       // Soft lilac
  
  // Premium Gold
  static const Color premiumGold = Color(0xFFFBBF24);
  static const Color premiumGoldLight = Color(0xFFFDE68A);
  
  // Neutral Colors - Modern Gray Scale
  static const Color darkBg = Color(0xFF0F172A);             // Dark navy
  static const Color darkCard = Color(0xFF1E293B);           // Card dark
  static const Color lightAsh = Color(0xFFF8FAFC);           // Light bg
  static const Color mediumAsh = Color(0xFFE2E8F0);          // Borders
  static const Color darkAsh = Color(0xFF334155);            // Text dark
  
  // Clean White
  static const Color cleanWhite = Color(0xFFFFFFFF);
  
  // Status Colors - Vibrant
  static const Color successGreen = Color(0xFF10B981);
  static const Color warningOrange = Color(0xFFF59E0B);
  static const Color dangerRed = Color(0xFFEF4444);
  static const Color infoBlue = Color(0xFF3B82F6);
  static const Color errorRed = dangerRed;  // Alias for dangerRed
  
  // Glassmorphism Colors
  static const Color glassWhite = Color(0x40FFFFFF);
  static const Color glassDark = Color(0x30000000);
  
  // Legacy aliases
  static const Color primaryBlue = primaryPurple;
  static const Color secondaryBlue = supportLilac;
  static const Color accentGreen = successGreen;
  static const Color backgroundGrey = lightAsh;
  static const Color surfaceWhite = cleanWhite;
  static const Color textDark = darkAsh;
  static const Color textMedium = Color(0xFF64748B);
  static const Color textLight = Color(0xFF94A3B8);
  
  // Additional UI colors for secure widgets
  static const Color mutedText = Color(0xFF94A3B8);  // Same as textLight
  static const Color neonGreen = successGreen;
  static const Color neonBlue = accentCyan;
  static const Color warningYellow = warningOrange;
  static const Color cardBg = darkCard;

  // Modern Gradients
  static const LinearGradient primaryGradient = LinearGradient(
    colors: [primaryPurple, accentCyan],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );
  
  static const LinearGradient premiumGradient = LinearGradient(
    colors: [primaryPurple, accentPink],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );
  
  static const LinearGradient darkGradient = LinearGradient(
    colors: [darkBg, Color(0xFF1E1B4B)],
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
      primary: primaryPurple,      // Main brand actions - Metallic Purple
      secondary: supportLilac,     // Support elements - Lilac
      tertiary: premiumGold,       // Premium features - Gold
      error: dangerRed,       // App background - Light Ash
      surface: cleanWhite,        // Cards, sheets - White
      onPrimary: cleanWhite,      // Text on purple
      onSecondary: darkAsh,      // Text on light ash background
      onSurface: darkAsh,         // Text on white surfaces
    ),
    
    // App Bar Theme
    appBarTheme: const AppBarTheme(
      backgroundColor: primaryPurple,    // AMTTP Purple headers
      foregroundColor: cleanWhite,       // White text on purple
      elevation: 0,
      scrolledUnderElevation: 1,
      centerTitle: true,
    ),
    
    // Card Theme
    cardTheme: CardThemeData(
      color: cleanWhite,           // White cards
      elevation: 2,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: const BorderSide(color: mediumAsh, width: 0.5),  // Subtle ash border
      ),
    ),
    
    // Elevated Button Theme
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: primaryPurple,   // Purple primary buttons
        foregroundColor: cleanWhite,      // White text
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
        foregroundColor: primaryPurple,   // Purple text
        side: const BorderSide(color: primaryPurple, width: 1.5),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8),
        ),
      ),
    ),
    
    // Text Button Theme
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: primaryPurple,   // Purple text buttons
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      ),
    ),
    
    // Input Decoration Theme
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: lightAsh,             // Light ash input backgrounds
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: const BorderSide(color: mediumAsh),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: const BorderSide(color: mediumAsh),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: const BorderSide(color: primaryPurple, width: 2),  // Purple focus
      ),
    ),
    
    // Text Theme
    textTheme: const TextTheme(
      headlineLarge: TextStyle(
        fontSize: 32,
        fontWeight: FontWeight.bold,
        color: darkAsh,              // Dark ash for high contrast
        fontFamily: 'Inter',
      ),
      headlineMedium: TextStyle(
        fontSize: 28,
        fontWeight: FontWeight.bold,
        color: darkAsh,
        fontFamily: 'Inter',
      ),
      headlineSmall: TextStyle(
        fontSize: 24,
        fontWeight: FontWeight.w600,
        color: darkAsh,
        fontFamily: 'Inter',
      ),
      titleLarge: TextStyle(
        fontSize: 20,
        fontWeight: FontWeight.w600,
        color: darkAsh,
        fontFamily: 'Inter',
      ),
      titleMedium: TextStyle(
        fontSize: 16,
        fontWeight: FontWeight.w500,
        color: darkAsh,
        fontFamily: 'Inter',
      ),
      bodyLarge: TextStyle(
        fontSize: 16,
        fontWeight: FontWeight.normal,
        color: darkAsh,
        fontFamily: 'Inter',
      ),
      bodyMedium: TextStyle(
        fontSize: 14,
        fontWeight: FontWeight.normal,
        color: textMedium,              // Keep medium text for subtle elements
        fontFamily: 'Inter',
      ),
      bodySmall: TextStyle(
        fontSize: 12,
        fontWeight: FontWeight.normal,
        color: textLight,               // Keep light text for captions
        fontFamily: 'Inter',
      ),
    ),
    
    fontFamily: 'Inter',
  );

  static ThemeData darkTheme = ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    colorScheme: const ColorScheme.dark(
      primary: primaryPurple,          // AMTTP Purple for dark theme
      secondary: supportLilac,         // Lilac support
      tertiary: premiumGold,           // Gold premium features
      error: dangerRed,   // Dark background
      surface: Color(0xFF1E293B),      // Dark surface
      onPrimary: cleanWhite,           // White on purple
      onSecondary: cleanWhite,
      onSurface: Colors.white,
    ),
    
    fontFamily: 'Inter',
  );

  // Risk Level Colors
  static Color getRiskColor(double riskScore) {
    if (riskScore < 0.4) return accentGreen;
    if (riskScore < 0.7) return warningOrange;
    return dangerRed;
  }
  
  static String getRiskLabel(double riskScore) {
    if (riskScore < 0.4) return 'Low Risk';
    if (riskScore < 0.7) return 'Medium Risk';
    if (riskScore < 0.8) return 'High Risk';
    return 'Very High Risk';
  }
}