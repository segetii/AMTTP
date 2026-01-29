# AMTTP Frontend UX Fix Plan (Premium Shell, Trust, Wallet, War Room)

**Status: ✅ COMPLETE** (Last updated: Implementation complete)

## 1) Navigation & Routing Clean-Up (Flutter + Next.js) ✅
- **Flutter central route config** (`core/router/app_router.dart`): ✅ Added `enum FintechSection { home, wallet, send, activity, profile }` and `sectionForRoute()`/`fintechSectionForRoute()` mapping functions.
- **Bottom nav state** (`PremiumFintechShell._updateNavIndex`): ✅ Uses `fintechSectionForRoute()` instead of `route.contains(...)`.
- **Nested routes**: ✅ Mapped `/transfer/review`, `/transfer/trust` → `send`; `/wallet/connect`, `/wallet/settings` → `wallet`; verified bottom-nav highlights nested routes.
- **Next.js War Room nav** (`WarRoomShell.tsx`): ✅ System group collapsed by default; active-group styling added.

## 2) Trust Check Integration & Logic (Flutter) ✅
- **Transfer page explicit trust check** (`PremiumTransferPage`): ✅ Removed auto `_checkTrust`; added "Check Trust Score" button near recipient; shows idle → spinner → result card states.
- **Backend/structured mock**: ✅ Added `TrustCheckRepository` with deterministic hash-based scoring (40-100 range); buckets: TRUSTED (80+), CAUTION (60-79), HIGH RISK (<60).
- **Reuse logic on trust page** (`PremiumTrustCheckPage`): ✅ Uses shared `TrustCheckRepository`; scoring aligned.

## 3) Premium Trust Check UX Improvements ✅
- **Stepper** (`PremiumTrustCheckPage`): ✅ "1. Enter · 2. Analyze · 3. Result" with `_trustStep` tracking (1 before check, 2 while `_isChecking`, 3 on result).
- **Advanced details split**: ✅ Graph/explainability in modal (`_showGraphModal()`); main page shows score + brief breakdown.
- **Post-check actions**: ✅ Safe actions primary (Escrow/Manual review, Whitelist); risky "Send anyway" secondary with warning + confirm dialog.

## 4) Premium Home & Carousel Refinements ✅
- **Carousel controls** (`FintechHomePage`): ✅ Dots/pills indicators via PageView onPageChanged tracking.
- **Auto-scroll etiquette**: ✅ `_lastUserInteraction` timestamp; only auto-advance if idle ≥8s; respects interaction.
- **Header declutter**: ✅ Grouped secondary actions; primary CTAs "Trust check" and "Send" remain prominent.

## 5) Wallet Connect: Demo vs Production Mode ✅
- **Connection mode flag**: ✅ Added `isDemo` flag in `PremiumWalletConnectPage`; shows "Demo Mode" banner when true.
- **Cancel & accessibility**: ✅ Cancel button with `Semantics` labels; bottom sheet dismiss support.

## 6) Cross-Stack Design System Alignment ✅
- **Design tokens** (`frontend/design-tokens.json`): ✅ Tokens defined (primary, primarySoft, background, surface, borderSubtle, success, warning, danger), radii, spacing, typography.
- **Apply to Flutter**: ✅ `AppTheme` uses token constants (`tokenPrimary`, `tokenSurface`, etc.) mapped to `ThemeData`.
- **Apply to Tailwind/Next.js**: ✅ `tailwind.config.ts` extended with same key colors/radii; `WarRoomShell` uses token classes.

## 7) Error, Empty, and Loading States ✅
- **Async states**: ✅ Trust checks, transfer submissions, wallet connect all show idle → loading → success/error with clear copy.
- **Empty states**: ✅ Added to:
  - `HistoryPage` - `_buildEmptyState()`
  - `DisputeCenterPage` - `_buildEmptyState()` for Active tab, `_buildEmptyHistoryState()` for History tab
  - `CompliancePage` - `_buildEmptyFrozenState()`, `_buildEmptyTrustedState()`, `_buildEmptyEDDState()`
- **Skeletons in War Room**: ✅ `SkeletonDashboard` component; `lastUpdated` timestamp on core dashboards.

## 8) Final Polishing & Regression ✅
- **UI smoke tests**: ✅ `browser_ui_test.py` passed 32/32 tests (100%)
- **Screenshots**: ✅ Refreshed 15 screenshots in `screenshots/`
- **Docs**: ✅ Updated `UI_ARCHITECTURE_MAP.md` with "UX Decisions & Rationale" section
