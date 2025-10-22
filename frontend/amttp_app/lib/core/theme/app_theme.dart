import 'package:flutter/material.dart';

class AppTheme {
  // 🎨 Finalized AMTTP Color Palette (Trust, Security, Compliance, Exclusivity)
  
  // Metallic Purple (Brand Signature) - Primary brand color for headers, key flows, important modules
  static const Color primaryPurple = Color(0xFF6C3BB4);
  
  // Lilac (Support) - Secondary shade for highlights, background accents
  static const Color supportLilac = Color(0xFFC8A2C8);
  
  // Ash (Neutral Foundation)
  static const Color lightAsh = Color(0xFFF5F6FA);    // backgrounds, containers
  static const Color mediumAsh = Color(0xFFE5E5E5);   // cards, dividers
  static const Color darkAsh = Color(0xFF5C5C5C);     // text, icons, high-contrast areas
  
  // Gold (Premium/Enterprise) - For enterprise-only features, VIP modules, compliance/security emphasis
  static const Color premiumGold = Color(0xFFD4AF37);
  
  // White (Clean UI) - Core base for clarity and readability
  static const Color cleanWhite = Color(0xFFFFFFFF);
  
  // Status Colors (kept for functional use)
  static const Color successGreen = Color(0xFF10B981);
  static const Color warningOrange = Color(0xFFF59E0B);
  static const Color dangerRed = Color(0xFFEF4444);
  
  // Legacy aliases for backward compatibility
  static const Color primaryBlue = primaryPurple;
  static const Color secondaryBlue = supportLilac;
  static const Color accentGreen = successGreen;
  static const Color backgroundGrey = lightAsh;
  static const Color surfaceWhite = cleanWhite;
  static const Color textDark = darkAsh;
  static const Color textMedium = Color(0xFF6B7280);
  static const Color textLight = Color(0xFF9CA3AF);

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