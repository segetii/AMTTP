import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../../core/auth/user_profile_provider.dart';
import '../../../../core/theme/app_theme.dart';

/// Profile Selector Page - Demo page to switch between user profiles
/// Each profile maps to a different sitemap navigation structure
class ProfileSelectorPage extends ConsumerWidget {
  const ProfileSelectorPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final currentProfile = ref.watch(userProfileProvider);

    return Scaffold(
      backgroundColor: AppTheme.darkBg,
      body: Container(
        decoration: const BoxDecoration(
          gradient: AppTheme.darkGradient,
        ),
        child: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                const SizedBox(height: 40),
                
                // Logo
                Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: [AppTheme.primaryBlue, AppTheme.primaryPurple],
                    ),
                    borderRadius: BorderRadius.circular(20),
                    boxShadow: [
                      BoxShadow(
                        color: AppTheme.primaryBlue.withOpacity(0.4),
                        blurRadius: 30,
                        offset: const Offset(0, 10),
                      ),
                    ],
                  ),
                  child: const Icon(Icons.shield, color: Colors.white, size: 48),
                ),
                const SizedBox(height: 24),
                
                const Text(
                  'AMTTP',
                  style: TextStyle(
                    color: AppTheme.cleanWhite,
                    fontSize: 36,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 2,
                  ),
                ),
                const Text(
                  'Advanced Money Transfer Transaction Protocol',
                  style: TextStyle(color: AppTheme.mutedText, fontSize: 14),
                ),
                const SizedBox(height: 48),
                
                // Section Title
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  decoration: BoxDecoration(
                    color: AppTheme.darkCard,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: const Text(
                    'SELECT YOUR PROFILE',
                    style: TextStyle(
                      color: AppTheme.mutedText,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 1.5,
                    ),
                  ),
                ),
                const SizedBox(height: 32),
                
                // Profile Cards
                _ProfileCard(
                  profile: UserProfile.endUser,
                  title: 'End User',
                  subtitle: 'Standard user for secure transfers',
                  description: 'Access wallet, transfers, NFT swaps, history, and disputes',
                  icon: Icons.person_rounded,
                  color: AppTheme.primaryBlue,
                  isSelected: currentProfile.profile == UserProfile.endUser,
                  features: const [
                    'Secure Transfers',
                    'NFT Swaps',
                    'Cross-Chain',
                    'Dispute Filing',
                    'Session Keys',
                    'Safe Management',
                  ],
                  onTap: () {
                    ref.read(userProfileProvider.notifier).switchProfile(UserProfile.endUser);
                    context.go('/');
                  },
                ),
                const SizedBox(height: 16),
                
                _ProfileCard(
                  profile: UserProfile.admin,
                  title: 'Administrator',
                  subtitle: 'Full system oversight and management',
                  description: 'Access admin dashboard, DQN analytics, policies, and all user features',
                  icon: Icons.admin_panel_settings_rounded,
                  color: AppTheme.primaryPurple,
                  isSelected: currentProfile.profile == UserProfile.admin,
                  features: const [
                    'Admin Dashboard',
                    'DQN Analytics',
                    'Transaction Review',
                    'Policy Management',
                    'Webhook Config',
                    'All User Features',
                  ],
                  onTap: () {
                    ref.read(userProfileProvider.notifier).switchProfile(UserProfile.admin);
                    context.go('/admin');
                  },
                ),
                const SizedBox(height: 16),
                
                _ProfileCard(
                  profile: UserProfile.complianceOfficer,
                  title: 'Compliance Officer',
                  subtitle: 'KYC/AML and regulatory compliance tools',
                  description: 'Access freeze/unfreeze, PEP screening, EDD queue, and audit tools',
                  icon: Icons.verified_user_rounded,
                  color: AppTheme.warningOrange,
                  isSelected: currentProfile.profile == UserProfile.complianceOfficer,
                  features: const [
                    'Freeze/Unfreeze',
                    'PEP Screening',
                    'Sanctions Check',
                    'EDD Queue',
                    'Approver Portal',
                    'Transaction Audit',
                  ],
                  onTap: () {
                    ref.read(userProfileProvider.notifier).switchProfile(UserProfile.complianceOfficer);
                    context.go('/compliance');
                  },
                ),
                
                const SizedBox(height: 48),
                
                // Sitemap Reference
                Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    color: AppTheme.darkCard,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: AppTheme.mutedText.withOpacity(0.3)),
                  ),
                  child: Column(
                    children: [
                      const Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.map, color: AppTheme.primaryBlue, size: 20),
                          SizedBox(width: 8),
                          Text(
                            'Profile-Based Navigation',
                            style: TextStyle(
                              color: AppTheme.cleanWhite,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      const Text(
                        'Each profile has a tailored sitemap with role-specific navigation. '
                        'The sidebar and available features change based on your selected profile.',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: AppTheme.mutedText, fontSize: 13),
                      ),
                      const SizedBox(height: 16),
                      Wrap(
                        alignment: WrapAlignment.center,
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          _buildRouteChip('/', 'Home'),
                          _buildRouteChip('/wallet', 'Wallet'),
                          _buildRouteChip('/transfer', 'Transfer'),
                          _buildRouteChip('/nft-swap', 'NFT Swap'),
                          _buildRouteChip('/disputes', 'Disputes'),
                          _buildRouteChip('/admin', 'Admin'),
                          _buildRouteChip('/compliance', 'Compliance'),
                        ],
                      ),
                    ],
                  ),
                ),
                
                const SizedBox(height: 40),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildRouteChip(String route, String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: AppTheme.primaryBlue.withOpacity(0.15),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppTheme.primaryBlue.withOpacity(0.3)),
      ),
      child: Text(
        '$label ($route)',
        style: const TextStyle(color: AppTheme.primaryBlue, fontSize: 11),
      ),
    );
  }
}

class _ProfileCard extends StatelessWidget {
  final UserProfile profile;
  final String title;
  final String subtitle;
  final String description;
  final IconData icon;
  final Color color;
  final bool isSelected;
  final List<String> features;
  final VoidCallback onTap;

  const _ProfileCard({
    required this.profile,
    required this.title,
    required this.subtitle,
    required this.description,
    required this.icon,
    required this.color,
    required this.isSelected,
    required this.features,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: AppTheme.darkCard,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isSelected ? color : AppTheme.mutedText.withOpacity(0.3),
            width: isSelected ? 2 : 1,
          ),
          boxShadow: isSelected
              ? [BoxShadow(color: color.withOpacity(0.3), blurRadius: 20, offset: const Offset(0, 5))]
              : null,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: color.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Icon(icon, color: color, size: 28),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Text(
                            title,
                            style: const TextStyle(
                              color: AppTheme.cleanWhite,
                              fontSize: 20,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          if (isSelected) ...[
                            const SizedBox(width: 8),
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                              decoration: BoxDecoration(
                                color: color,
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: const Text(
                                'ACTIVE',
                                style: TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold),
                              ),
                            ),
                          ],
                        ],
                      ),
                      Text(subtitle, style: TextStyle(color: color, fontSize: 13)),
                    ],
                  ),
                ),
                Icon(
                  isSelected ? Icons.check_circle : Icons.arrow_forward_ios,
                  color: isSelected ? color : AppTheme.mutedText,
                  size: isSelected ? 28 : 16,
                ),
              ],
            ),
            const SizedBox(height: 16),
            Text(description, style: const TextStyle(color: AppTheme.mutedText, fontSize: 13)),
            const SizedBox(height: 16),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: features
                  .map((f) => Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: color.withOpacity(0.15),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Text(f, style: TextStyle(color: color, fontSize: 11)),
                      ))
                  .toList(),
            ),
          ],
        ),
      ),
    );
  }
}
