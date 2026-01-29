import 'package:flutter/material.dart';

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
