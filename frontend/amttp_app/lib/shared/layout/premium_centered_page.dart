import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/app_theme.dart';

/// Shared centralized layout for premium end-user / PeP pages.
///
/// - Applies the dark gradient background used on the home screen
/// - Centers content with a max width of 624px (MetaMask/Revolut-style)
/// - Handles SafeArea and bottom padding space for the floating nav
class PremiumCenteredPage extends StatelessWidget {
  final Widget child;

  const PremiumCenteredPage({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    final screenWidth = MediaQuery.of(context).size.width;
    final maxContentWidth = screenWidth > 680 ? 624.0 : screenWidth - 40;

    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            Color(0xFF0F0F1A),
            Color(0xFF0A0A0F),
          ],
        ),
      ),
      child: SafeArea(
        bottom: false,
        child: SingleChildScrollView(
          padding: const EdgeInsets.only(bottom: 120),
          child: Center(
            child: ConstrainedBox(
              constraints: BoxConstraints(maxWidth: maxContentWidth),
              child: child,
            ),
          ),
        ),
      ),
    );
  }
}

/// Non-scrollable variant for tabbed pages that manage their own scrolling.
///
/// Provides the same gradient + centered max-width layout, but without
/// a [SingleChildScrollView] so [TabBarView] children can scroll independently.
class PremiumPageContainer extends StatelessWidget {
  final Widget child;

  const PremiumPageContainer({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    final screenWidth = MediaQuery.of(context).size.width;
    final maxContentWidth = screenWidth > 680 ? 624.0 : screenWidth - 40;

    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            Color(0xFF0F0F1A),
            Color(0xFF0A0A0F),
          ],
        ),
      ),
      child: SafeArea(
        bottom: false,
        child: Center(
          child: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: maxContentWidth),
            child: child,
          ),
        ),
      ),
    );
  }
}

/// In-page header row that replaces AppBar for pages inside the shell.
///
/// Shows a back button (if [canPop]), the page title, and optional actions.
class ShellPageHeader extends StatelessWidget {
  final String title;
  final List<Widget> actions;

  const ShellPageHeader({
    super.key,
    required this.title,
    this.actions = const [],
  });

  @override
  Widget build(BuildContext context) {
    final canPop = GoRouter.of(context).canPop();

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: [
          if (canPop)
            GestureDetector(
              onTap: () => context.pop(),
              child: Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: AppTheme.tokenCardElevated,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: AppTheme.tokenBorderStrong),
                ),
                child: const Icon(Icons.arrow_back_rounded,
                    color: AppTheme.tokenText, size: 18),
              ),
            ),
          if (canPop) const SizedBox(width: 12),
          Expanded(
            child: Text(
              title,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          ...actions,
        ],
      ),
    );
  }
}
