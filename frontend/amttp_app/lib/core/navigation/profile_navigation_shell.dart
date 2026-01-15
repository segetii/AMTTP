import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../auth/user_profile_provider.dart';
import '../theme/app_theme.dart';

/// Profile-based Navigation Shell
/// Implements the sitemap navigation for each user profile type
class ProfileNavigationShell extends ConsumerStatefulWidget {
  final Widget child;
  
  const ProfileNavigationShell({super.key, required this.child});

  @override
  ConsumerState<ProfileNavigationShell> createState() => _ProfileNavigationShellState();
}

class _ProfileNavigationShellState extends ConsumerState<ProfileNavigationShell> {
  bool _isDrawerExpanded = true;
  
  @override
  Widget build(BuildContext context) {
    final profileState = ref.watch(userProfileProvider);
    final navItems = ref.watch(navigationItemsProvider);
    final currentRoute = GoRouterState.of(context).uri.toString();
    final isWideScreen = MediaQuery.of(context).size.width > 800;

    return Scaffold(
      backgroundColor: AppTheme.darkBg,
      appBar: _buildAppBar(profileState),
      drawer: isWideScreen ? null : _buildDrawer(navItems, currentRoute, profileState),
      body: Row(
        children: [
          // Permanent sidebar on wide screens
          if (isWideScreen)
            _buildSidebar(navItems, currentRoute, profileState),
          
          // Main content
          Expanded(
            child: Container(
              decoration: const BoxDecoration(
                gradient: AppTheme.darkGradient,
              ),
              child: widget.child,
            ),
          ),
        ],
      ),
    );
  }

  PreferredSizeWidget _buildAppBar(UserProfileState profileState) {
    return AppBar(
      backgroundColor: AppTheme.darkCard,
      foregroundColor: AppTheme.cleanWhite,
      elevation: 0,
      title: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [AppTheme.primaryBlue, AppTheme.primaryPurple],
              ),
              borderRadius: BorderRadius.circular(8),
            ),
            child: const Icon(Icons.shield, color: Colors.white, size: 20),
          ),
          const SizedBox(width: 12),
          const Text('AMTTP', style: TextStyle(fontWeight: FontWeight.bold)),
        ],
      ),
      actions: [
        // Profile Switcher (for demo)
        PopupMenuButton<UserProfile>(
          icon: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: _getProfileColor(profileState.profile).withOpacity(0.2),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: _getProfileColor(profileState.profile)),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(_getProfileIcon(profileState.profile), 
                     color: _getProfileColor(profileState.profile), size: 16),
                const SizedBox(width: 8),
                Text(
                  _getProfileLabel(profileState.profile),
                  style: TextStyle(color: _getProfileColor(profileState.profile), fontSize: 12),
                ),
                const SizedBox(width: 4),
                Icon(Icons.arrow_drop_down, 
                     color: _getProfileColor(profileState.profile), size: 16),
              ],
            ),
          ),
          onSelected: (profile) {
            ref.read(userProfileProvider.notifier).switchProfile(profile);
          },
          itemBuilder: (context) => [
            _buildProfileMenuItem(UserProfile.endUser, profileState.profile),
            _buildProfileMenuItem(UserProfile.admin, profileState.profile),
            _buildProfileMenuItem(UserProfile.complianceOfficer, profileState.profile),
          ],
        ),
        const SizedBox(width: 8),
        // Notifications
        IconButton(
          icon: Badge(
            label: const Text('3'),
            child: const Icon(Icons.notifications_outlined),
          ),
          onPressed: () {},
        ),
        const SizedBox(width: 8),
        // User Avatar
        Padding(
          padding: const EdgeInsets.only(right: 16),
          child: CircleAvatar(
            radius: 16,
            backgroundColor: AppTheme.primaryBlue,
            child: Text(
              profileState.displayName.isNotEmpty ? profileState.displayName[0] : 'U',
              style: const TextStyle(color: Colors.white, fontSize: 12),
            ),
          ),
        ),
      ],
    );
  }

  PopupMenuItem<UserProfile> _buildProfileMenuItem(UserProfile profile, UserProfile current) {
    final isSelected = profile == current;
    return PopupMenuItem(
      value: profile,
      child: Row(
        children: [
          Icon(_getProfileIcon(profile), 
               color: isSelected ? _getProfileColor(profile) : AppTheme.mutedText,
               size: 20),
          const SizedBox(width: 12),
          Text(
            _getProfileLabel(profile),
            style: TextStyle(
              color: isSelected ? _getProfileColor(profile) : AppTheme.cleanWhite,
              fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
            ),
          ),
          if (isSelected) ...[
            const Spacer(),
            Icon(Icons.check, color: _getProfileColor(profile), size: 16),
          ],
        ],
      ),
    );
  }

  Widget _buildSidebar(List<NavigationItem> items, String currentRoute, UserProfileState profileState) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      width: _isDrawerExpanded ? 260 : 72,
      decoration: BoxDecoration(
        color: AppTheme.darkCard,
        border: Border(
          right: BorderSide(color: AppTheme.mutedText.withOpacity(0.2)),
        ),
      ),
      child: Column(
        children: [
          // Collapse button
          Container(
            padding: const EdgeInsets.all(8),
            child: IconButton(
              icon: Icon(_isDrawerExpanded ? Icons.chevron_left : Icons.chevron_right),
              onPressed: () => setState(() => _isDrawerExpanded = !_isDrawerExpanded),
              color: AppTheme.mutedText,
            ),
          ),
          
          // Profile indicator
          if (_isDrawerExpanded)
            _buildProfileIndicator(profileState),
          
          const Divider(color: AppTheme.mutedText, height: 1),
          
          // Navigation items
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(vertical: 8),
              children: _buildNavItems(items, currentRoute),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDrawer(List<NavigationItem> items, String currentRoute, UserProfileState profileState) {
    return Drawer(
      backgroundColor: AppTheme.darkCard,
      child: Column(
        children: [
          // Header
          Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [AppTheme.primaryBlue, AppTheme.primaryPurple],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
            ),
            child: SafeArea(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: Colors.white.withOpacity(0.2),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: const Icon(Icons.shield, color: Colors.white, size: 28),
                      ),
                      const SizedBox(width: 12),
                      const Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('AMTTP', style: TextStyle(color: Colors.white, fontSize: 24, fontWeight: FontWeight.bold)),
                          Text('Secure Transfers', style: TextStyle(color: Colors.white70, fontSize: 12)),
                        ],
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  _buildProfileIndicator(profileState, light: true),
                ],
              ),
            ),
          ),
          
          // Navigation items
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(vertical: 8),
              children: _buildNavItems(items, currentRoute),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildProfileIndicator(UserProfileState profileState, {bool light = false}) {
    final color = _getProfileColor(profileState.profile);
    return Container(
      margin: const EdgeInsets.all(12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withOpacity(0.5)),
      ),
      child: Row(
        children: [
          Icon(_getProfileIcon(profileState.profile), color: color, size: 20),
          if (_isDrawerExpanded || light) ...[
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    profileState.displayName,
                    style: TextStyle(
                      color: light ? Colors.white : AppTheme.cleanWhite,
                      fontWeight: FontWeight.bold,
                      fontSize: 14,
                    ),
                  ),
                  Text(
                    _getProfileLabel(profileState.profile),
                    style: TextStyle(color: color, fontSize: 11),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  List<Widget> _buildNavItems(List<NavigationItem> items, String currentRoute) {
    final widgets = <Widget>[];
    
    for (final item in items) {
      if (item.isSection && item.children.isNotEmpty) {
        // Section with children
        widgets.add(_buildSectionHeader(item));
        for (final child in item.children) {
          widgets.add(_buildNavTile(child, currentRoute));
        }
        widgets.add(const SizedBox(height: 8));
      } else if (item.isSection) {
        // Section header only
        widgets.add(_buildSectionHeader(item));
        widgets.add(_buildNavTile(item, currentRoute, isSection: true));
      } else {
        // Regular item
        widgets.add(_buildNavTile(item, currentRoute));
      }
    }
    
    return widgets;
  }

  Widget _buildSectionHeader(NavigationItem item) {
    if (!_isDrawerExpanded) return const SizedBox.shrink();
    
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
      child: Text(
        item.title.toUpperCase(),
        style: TextStyle(
          color: AppTheme.mutedText,
          fontSize: 11,
          fontWeight: FontWeight.w600,
          letterSpacing: 1.2,
        ),
      ),
    );
  }

  Widget _buildNavTile(NavigationItem item, String currentRoute, {bool isSection = false}) {
    if (item.route.isEmpty && !isSection) return const SizedBox.shrink();
    
    final isSelected = currentRoute == item.route;
    final iconData = _getIconData(item.icon);
    
    return Container(
      margin: EdgeInsets.symmetric(
        horizontal: _isDrawerExpanded ? 8 : 4,
        vertical: 2,
      ),
      decoration: BoxDecoration(
        color: isSelected ? AppTheme.primaryBlue.withOpacity(0.2) : Colors.transparent,
        borderRadius: BorderRadius.circular(8),
        border: isSelected 
            ? Border.all(color: AppTheme.primaryBlue.withOpacity(0.5))
            : null,
      ),
      child: ListTile(
        dense: true,
        contentPadding: EdgeInsets.symmetric(
          horizontal: _isDrawerExpanded ? 12 : 0,
        ),
        leading: Container(
          width: 36,
          alignment: Alignment.center,
          child: Badge(
            isLabelVisible: item.badge != null,
            label: Text(item.badge ?? ''),
            child: Icon(
              iconData,
              color: isSelected ? AppTheme.primaryBlue : AppTheme.mutedText,
              size: 20,
            ),
          ),
        ),
        title: _isDrawerExpanded
            ? Text(
                item.title,
                style: TextStyle(
                  color: isSelected ? AppTheme.cleanWhite : AppTheme.mutedText,
                  fontSize: 14,
                  fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
                ),
              )
            : null,
        onTap: item.route.isNotEmpty 
            ? () {
                context.go(item.route);
                // Close drawer on mobile
                if (MediaQuery.of(context).size.width <= 800) {
                  Navigator.of(context).pop();
                }
              }
            : null,
      ),
    );
  }

  IconData _getIconData(String iconName) {
    final iconMap = {
      'home': Icons.home_rounded,
      'dashboard': Icons.dashboard_rounded,
      'account_balance_wallet': Icons.account_balance_wallet_rounded,
      'send': Icons.send_rounded,
      'swap_horiz': Icons.swap_horiz_rounded,
      'collections': Icons.collections_rounded,
      'link': Icons.link_rounded,
      'history': Icons.history_rounded,
      'gavel': Icons.gavel_rounded,
      'key': Icons.key_rounded,
      'security': Icons.security_rounded,
      'shield': Icons.shield_rounded,
      'settings': Icons.settings_rounded,
      'person': Icons.person_rounded,
      'receipt_long': Icons.receipt_long_rounded,
      'approval': Icons.approval_rounded,
      'policy': Icons.policy_rounded,
      'verified_user': Icons.verified_user_rounded,
      'manage_accounts': Icons.manage_accounts_rounded,
      'ac_unit': Icons.ac_unit_rounded,
      'visibility': Icons.visibility_rounded,
      'search': Icons.search_rounded,
      'fact_check': Icons.fact_check_rounded,
      'admin_panel_settings': Icons.admin_panel_settings_rounded,
      'privacy_tip': Icons.privacy_tip_rounded,
      'lock': Icons.lock_rounded,
      'public': Icons.public_rounded,
    };
    return iconMap[iconName] ?? Icons.circle;
  }

  Color _getProfileColor(UserProfile profile) {
    switch (profile) {
      case UserProfile.endUser:
        return AppTheme.primaryBlue;
      case UserProfile.admin:
        return AppTheme.primaryPurple;
      case UserProfile.complianceOfficer:
        return AppTheme.warningOrange;
    }
  }

  IconData _getProfileIcon(UserProfile profile) {
    switch (profile) {
      case UserProfile.endUser:
        return Icons.person_rounded;
      case UserProfile.admin:
        return Icons.admin_panel_settings_rounded;
      case UserProfile.complianceOfficer:
        return Icons.verified_user_rounded;
    }
  }

  String _getProfileLabel(UserProfile profile) {
    switch (profile) {
      case UserProfile.endUser:
        return 'End User';
      case UserProfile.admin:
        return 'Admin';
      case UserProfile.complianceOfficer:
        return 'Compliance';
    }
  }
}
