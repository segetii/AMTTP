# AMTTP Theme Compliance Summary

## Ground Truth Specification Alignment

This document summarizes the theme updates made to align the Flutter app with the **AMTTP UI/UX Ground Truth v2.3** specification.

---

## 🎨 Color Palette (Updated)

All colors have been centralized in `lib/core/theme/app_theme.dart`:

| Token | Spec Value | Implementation |
|-------|------------|----------------|
| Background Dark Ops | `#0B0E14` | `AppTheme.backgroundDarkOps` |
| Primary Text | `#E6E8EB` | `AppTheme.textPrimary` |
| Secondary Text | `#9AA1AC` | `AppTheme.textSecondary` |
| High Risk | `#E5484D` | `AppTheme.riskHigh` |
| Medium Risk | `#F5A524` | `AppTheme.riskMedium` |
| Low Risk | `#3FB950` | `AppTheme.riskLow` |
| Integrity Lock | `#4CC9F0` | `AppTheme.integrityLock` |

### Additional Design Tokens

| Token | Value | Purpose |
|-------|-------|---------|
| `primaryBlue` | `#6366F1` | Primary actions, brand color |
| `darkCard` | `#151A23` | Card backgrounds |
| `darkSurface` | `#1A1F2B` | Surface elements |
| `textLight` | `#94A3B8` | Inactive/muted text |

---

## 📝 Typography

Per Ground Truth specification:
- **Primary Font**: Inter (UI text)
- **Numerical/Hash Font**: JetBrains Mono (wallet addresses, transaction hashes)
- **Scale**: 12 / 14 / 16 / 20 / 24

---

## 📁 Files Updated

### Core Theme
- `lib/core/theme/app_theme.dart` - Complete rewrite with Ground Truth colors

### Shared Widgets
- `lib/shared/widgets/trust_check_interstitial.dart` - Risk colors, integrity lock
- `lib/shared/shells/focus_mode_shell.dart` - Navigation, status badges
- `lib/shared/shells/war_room_shell.dart` - Sidebar, analytics section

### Features
- `lib/features/analytics/analytics_hub_page.dart` - Tab bar, dialogs

### Services
- `lib/services/bridge/embedded_analytics.dart` - WebView backgrounds, overlays

---

## ✅ Color Migration Guide

When updating additional components, use these mappings:

### Risk/Status Colors
```dart
// OLD                          // NEW
Color(0xFFEF4444)    →   AppTheme.riskHigh      // Red/Danger
Color(0xFF10B981)    →   AppTheme.riskLow       // Green/Success
Color(0xFFF59E0B)    →   AppTheme.riskMedium    // Orange/Warning
```

### Background Colors
```dart
// OLD                          // NEW
Color(0xFF0B0E14)    →   AppTheme.backgroundDarkOps
Color(0xFF1A1F2E)    →   AppTheme.darkSurface
Color(0xFF0D1117)    →   const Color(0xFF0D1117) // Sidebar specific
```

### Text Colors
```dart
// OLD                          // NEW
Colors.white          →   AppTheme.textPrimary   // High emphasis
Color(0xFF64748B)    →   AppTheme.textSecondary  // Medium emphasis
Color(0xFF94A3B8)    →   AppTheme.textLight      // Low emphasis
```

### Primary/Brand Colors
```dart
// OLD                          // NEW
Color(0xFF6366F1)    →   AppTheme.primaryBlue
Color(0xFF4CC9F0)    →   AppTheme.integrityLock
```

---

## 🔧 Usage Pattern

```dart
import '../../core/theme/app_theme.dart';

// In widget build:
Container(
  color: AppTheme.backgroundDarkOps,
  child: Text(
    'Risk Score',
    style: TextStyle(
      color: AppTheme.textPrimary,
      fontFamily: 'Inter',
    ),
  ),
)

// For hash/address display:
Text(
  '0x1234...abcd',
  style: TextStyle(
    color: AppTheme.textSecondary,
    fontFamily: 'JetBrains Mono',
  ),
)

// For risk indicators:
Container(
  color: score > 0.7 
    ? AppTheme.riskHigh 
    : score > 0.4 
      ? AppTheme.riskMedium 
      : AppTheme.riskLow,
)
```

---

## 📊 Compliance Status

| Component | Status | Notes |
|-----------|--------|-------|
| AppTheme | ✅ Complete | All Ground Truth colors defined |
| Trust Check Interstitial | ✅ Complete | Risk colors updated |
| Focus Mode Shell | ✅ Complete | Nav and badges updated |
| War Room Shell | ✅ Complete | Sidebar colors updated |
| Analytics Hub | ✅ Complete | Tab bar and dialogs |
| Embedded Analytics | ✅ Complete | WebView overlays |

---

## 🚀 Next Steps

1. Run Flutter app to verify visual consistency
2. Consider adding `JetBrains Mono` font to `pubspec.yaml` if not present
3. Update any remaining hardcoded colors in feature pages
4. Test dark mode consistency across all screens

---

*Generated: Theme Compliance Update Session*
*Reference: AMTTP_UI_UX_Ground_Truth.md v2.3*
