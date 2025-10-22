import 'package:flutter/material.dart';
import '../../core/theme/app_theme.dart';

class FeaturesCarousel extends StatefulWidget {
  const FeaturesCarousel({super.key});

  @override
  State<FeaturesCarousel> createState() => _FeaturesCarouselState();
}

class _FeaturesCarouselState extends State<FeaturesCarousel>
    with TickerProviderStateMixin {
  late PageController _pageController;
  late AnimationController _animationController;
  late Animation<double> _fadeAnimation;

  int _currentIndex = 0;

  final List<FeatureItem> _features = [
    const FeatureItem(
      icon: Icons.psychology_outlined,
      title: 'AI-Powered Fraud Detection',
      description: 'Advanced DQN machine learning protects every transaction',
      gradient: [AppTheme.primaryPurple, AppTheme.supportLilac],
      accentColor: AppTheme.premiumGold,
    ),
    const FeatureItem(
      icon: Icons.verified_user_outlined,
      title: 'Compliance-First Design',
      description: 'Built-in regulatory compliance and audit trails',
      gradient: [AppTheme.supportLilac, AppTheme.premiumGold],
      accentColor: AppTheme.primaryPurple,
    ),
    const FeatureItem(
      icon: Icons.security_outlined,
      title: 'Enterprise Security',
      description: 'Multi-signature approvals and institutional controls',
      gradient: [AppTheme.premiumGold, AppTheme.primaryPurple],
      accentColor: AppTheme.supportLilac,
    ),
  ];

  @override
  void initState() {
    super.initState();
    _pageController = PageController();
    _animationController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );
    _fadeAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _animationController, curve: Curves.easeInOut),
    );
    _animationController.forward();

    // Auto-advance carousel
    _startAutoAdvance();
  }

  void _startAutoAdvance() {
    Future.delayed(const Duration(seconds: 4), () {
      if (mounted) {
        _nextPage();
        _startAutoAdvance();
      }
    });
  }

  void _nextPage() {
    final nextIndex = (_currentIndex + 1) % _features.length;
    _pageController.animateToPage(
      nextIndex,
      duration: const Duration(milliseconds: 500),
      curve: Curves.easeInOut,
    );
  }

  @override
  void dispose() {
    _pageController.dispose();
    _animationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 320,
      margin: const EdgeInsets.symmetric(horizontal: 24),
      child: Column(
        children: [
          // Carousel Title
          FadeTransition(
            opacity: _fadeAnimation,
            child: const Padding(
              padding: EdgeInsets.only(bottom: 24),
              child: Text(
                'AMTTP Core Features',
                style: TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                  color: AppTheme.primaryPurple,
                  letterSpacing: 0.5,
                ),
                textAlign: TextAlign.center,
              ),
            ),
          ),

          // Carousel Content
          Expanded(
            child: PageView.builder(
              controller: _pageController,
              onPageChanged: (index) {
                setState(() {
                  _currentIndex = index;
                });
              },
              itemCount: _features.length,
              itemBuilder: (context, index) {
                final feature = _features[index];
                return AnimatedBuilder(
                  animation: _pageController,
                  builder: (context, child) {
                    double value = 1.0;
                    if (_pageController.position.haveDimensions) {
                      value = _pageController.page! - index;
                      value = (1 - (value.abs() * 0.3)).clamp(0.0, 1.0);
                    }

                    return Transform.scale(
                      scale: value,
                      child: Opacity(
                        opacity: value,
                        child: _buildFeatureCard(feature),
                      ),
                    );
                  },
                );
              },
            ),
          ),

          const SizedBox(height: 20),

          // Page Indicators
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: List.generate(
              _features.length,
              (index) => GestureDetector(
                onTap: () {
                  _pageController.animateToPage(
                    index,
                    duration: const Duration(milliseconds: 300),
                    curve: Curves.easeInOut,
                  );
                },
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 300),
                  margin: const EdgeInsets.symmetric(horizontal: 4),
                  width: _currentIndex == index ? 24 : 8,
                  height: 8,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(4),
                    gradient: _currentIndex == index
                        ? LinearGradient(
                            colors: _features[index].gradient,
                            begin: Alignment.centerLeft,
                            end: Alignment.centerRight,
                          )
                        : null,
                    color: _currentIndex == index ? null : AppTheme.mediumAsh,
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFeatureCard(FeatureItem feature) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        gradient: LinearGradient(
          colors: [
            feature.gradient[0].withOpacity(0.1),
            feature.gradient[1].withOpacity(0.05),
          ],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        border: Border.all(
          color: feature.gradient[0].withOpacity(0.2),
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: feature.gradient[0].withOpacity(0.15),
            blurRadius: 20,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Stack(
        children: [
          // Background Pattern
          Positioned(
            top: -20,
            right: -20,
            child: Container(
              width: 100,
              height: 100,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(
                  colors: [
                    feature.accentColor.withOpacity(0.1),
                    feature.accentColor.withOpacity(0.05),
                  ],
                ),
              ),
            ),
          ),

          // Main Content
          Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Icon
                Container(
                  width: 60,
                  height: 60,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(16),
                    gradient: LinearGradient(
                      colors: feature.gradient,
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: feature.gradient[0].withOpacity(0.3),
                        blurRadius: 12,
                        offset: const Offset(0, 4),
                      ),
                    ],
                  ),
                  child: Icon(
                    feature.icon,
                    color: AppTheme.cleanWhite,
                    size: 30,
                  ),
                ),

                const SizedBox(height: 20),

                // Title
                Text(
                  feature.title,
                  style: const TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                    color: AppTheme.textDark,
                    height: 1.2,
                  ),
                ),

                const SizedBox(height: 12),

                // Description
                Text(
                  feature.description,
                  style: const TextStyle(
                    fontSize: 14,
                    color: AppTheme.textLight,
                    height: 1.4,
                  ),
                ),

                const Spacer(),

                // Action Button
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 8,
                  ),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(20),
                    gradient: LinearGradient(
                      colors: [
                        feature.accentColor.withOpacity(0.1),
                        feature.accentColor.withOpacity(0.05),
                      ],
                    ),
                    border: Border.all(
                      color: feature.accentColor.withOpacity(0.3),
                    ),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        'Learn More',
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: feature.accentColor,
                        ),
                      ),
                      const SizedBox(width: 4),
                      Icon(
                        Icons.arrow_forward,
                        size: 16,
                        color: feature.accentColor,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class FeatureItem {
  final IconData icon;
  final String title;
  final String description;
  final List<Color> gradient;
  final Color accentColor;

  const FeatureItem({
    required this.icon,
    required this.title,
    required this.description,
    required this.gradient,
    required this.accentColor,
  });
}
