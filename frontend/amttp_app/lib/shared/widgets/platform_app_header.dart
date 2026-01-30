/// Platform App Header
/// 
/// Unified header component with app switcher for AMTTP Platform
/// Provides consistent branding and navigation across Flutter and Next.js apps

import 'dart:html' as html;
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import '../auth/shared_auth_service.dart';

/// Platform header with app switcher
class PlatformAppHeader extends StatelessWidget {
  final String currentApp; // 'wallet' or 'war-room'
  final VoidCallback? onMenuPressed;
  final Widget? trailing;

  const PlatformAppHeader({
    super.key,
    this.currentApp = 'wallet',
    this.onMenuPressed,
    this.trailing,
  });

  @override
  Widget build(BuildContext context) {
    final auth = SharedAuthService();
    
    return Container(
      height: 56,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(
        color: const Color(0xFF0F0F14),
        border: Border(
          bottom: BorderSide(
            color: Colors.white.withOpacity(0.08),
            width: 1,
          ),
        ),
      ),
      child: Row(
        children: [
          // Menu button (optional)
          if (onMenuPressed != null)
            IconButton(
              onPressed: onMenuPressed,
              icon: const Icon(Icons.menu, color: Colors.white70, size: 22),
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(minWidth: 40, minHeight: 40),
            ),
          
          // Logo & Brand
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 28,
                height: 28,
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [Color(0xFF3B82F6), Color(0xFF8B5CF6)],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const Icon(Icons.shield, color: Colors.white, size: 16),
              ),
              const SizedBox(width: 10),
              const Text(
                'AMTTP',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                  letterSpacing: 1,
                ),
              ),
            ],
          ),
          
          const SizedBox(width: 16),
          
          // App Switcher
          _AppSwitcher(currentApp: currentApp, auth: auth),
          
          const Spacer(),
          
          // Trailing widgets
          if (trailing != null) trailing!,
          
          // User menu (if authenticated)
          if (auth.isAuthenticated) ...[
            const SizedBox(width: 8),
            _UserMenu(auth: auth),
          ],
        ],
      ),
    );
  }
}

/// App switcher dropdown
class _AppSwitcher extends StatefulWidget {
  final String currentApp;
  final SharedAuthService auth;

  const _AppSwitcher({required this.currentApp, required this.auth});

  @override
  State<_AppSwitcher> createState() => _AppSwitcherState();
}

class _AppSwitcherState extends State<_AppSwitcher> {
  bool _isOpen = false;
  final _layerLink = LayerLink();
  OverlayEntry? _overlayEntry;

  void _toggleDropdown() {
    if (_isOpen) {
      _closeDropdown();
    } else {
      _openDropdown();
    }
  }

  void _openDropdown() {
    _overlayEntry = _createOverlay();
    Overlay.of(context).insert(_overlayEntry!);
    setState(() => _isOpen = true);
  }

  void _closeDropdown() {
    _overlayEntry?.remove();
    _overlayEntry = null;
    setState(() => _isOpen = false);
  }

  OverlayEntry _createOverlay() {
    return OverlayEntry(
      builder: (context) => Stack(
        children: [
          // Backdrop
          Positioned.fill(
            child: GestureDetector(
              onTap: _closeDropdown,
              child: Container(color: Colors.transparent),
            ),
          ),
          // Dropdown
          Positioned(
            width: 220,
            child: CompositedTransformFollower(
              link: _layerLink,
              offset: const Offset(0, 40),
              child: Material(
                color: Colors.transparent,
                child: Container(
                  decoration: BoxDecoration(
                    color: const Color(0xFF1A1A24),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: Colors.white.withOpacity(0.1)),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withOpacity(0.4),
                        blurRadius: 20,
                        offset: const Offset(0, 8),
                      ),
                    ],
                  ),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      _AppOption(
                        icon: Icons.account_balance_wallet,
                        label: 'Wallet App',
                        description: 'Transfers & Trust Check',
                        isSelected: widget.currentApp == 'wallet',
                        onTap: () {
                          _closeDropdown();
                          if (widget.currentApp != 'wallet') {
                            _navigateToApp(widget.auth.getWalletAppUrl());
                          }
                        },
                      ),
                      Divider(height: 1, color: Colors.white.withOpacity(0.08)),
                      _AppOption(
                        icon: Icons.security,
                        label: 'War Room',
                        description: 'Compliance & Monitoring',
                        isSelected: widget.currentApp == 'war-room',
                        onTap: () {
                          _closeDropdown();
                          if (widget.currentApp != 'war-room') {
                            _navigateToApp(widget.auth.getWarRoomUrl());
                          }
                        },
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _navigateToApp(String url) {
    if (kIsWeb) {
      html.window.location.href = url;
    }
  }

  @override
  Widget build(BuildContext context) {
    final appLabel = widget.currentApp == 'wallet' ? 'Wallet' : 'War Room';
    final appIcon = widget.currentApp == 'wallet' 
        ? Icons.account_balance_wallet 
        : Icons.security;

    return CompositedTransformTarget(
      link: _layerLink,
      child: InkWell(
        onTap: _toggleDropdown,
        borderRadius: BorderRadius.circular(8),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            color: _isOpen ? Colors.white.withOpacity(0.1) : Colors.transparent,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
              color: Colors.white.withOpacity(_isOpen ? 0.2 : 0.1),
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(appIcon, color: const Color(0xFF3B82F6), size: 18),
              const SizedBox(width: 8),
              Text(
                appLabel,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                ),
              ),
              const SizedBox(width: 4),
              Icon(
                _isOpen ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down,
                color: Colors.white54,
                size: 18,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// App option in dropdown
class _AppOption extends StatelessWidget {
  final IconData icon;
  final String label;
  final String description;
  final bool isSelected;
  final VoidCallback onTap;

  const _AppOption({
    required this.icon,
    required this.label,
    required this.description,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: isSelected ? const Color(0xFF3B82F6).withOpacity(0.1) : null,
        ),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                color: isSelected 
                    ? const Color(0xFF3B82F6).withOpacity(0.2)
                    : Colors.white.withOpacity(0.05),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Icon(
                icon,
                color: isSelected ? const Color(0xFF3B82F6) : Colors.white54,
                size: 18,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        label,
                        style: TextStyle(
                          color: isSelected ? Colors.white : Colors.white70,
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      if (isSelected) ...[
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: const Color(0xFF3B82F6),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: const Text(
                            'Active',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 10,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                  const SizedBox(height: 2),
                  Text(
                    description,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.5),
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// User menu
class _UserMenu extends StatelessWidget {
  final SharedAuthService auth;

  const _UserMenu({required this.auth});

  @override
  Widget build(BuildContext context) {
    final session = auth.session;
    if (session == null) return const SizedBox.shrink();

    final shortAddress = '${session.address.substring(0, 6)}...${session.address.substring(session.address.length - 4)}';

    return PopupMenuButton<String>(
      offset: const Offset(0, 40),
      color: const Color(0xFF1A1A24),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: Colors.white.withOpacity(0.1)),
      ),
      onSelected: (value) {
        if (value == 'logout') {
          auth.logout();
        }
      },
      itemBuilder: (context) => [
        PopupMenuItem(
          enabled: false,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                session.displayName ?? shortAddress,
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500),
              ),
              Text(
                'Role: ${session.role}',
                style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 12),
              ),
            ],
          ),
        ),
        const PopupMenuDivider(),
        const PopupMenuItem(
          value: 'logout',
          child: Row(
            children: [
              Icon(Icons.logout, color: Colors.redAccent, size: 18),
              SizedBox(width: 8),
              Text('Logout', style: TextStyle(color: Colors.redAccent)),
            ],
          ),
        ),
      ],
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.05),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: Colors.white.withOpacity(0.1)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircleAvatar(
              radius: 12,
              backgroundColor: const Color(0xFF3B82F6),
              child: Text(
                session.address.substring(2, 4).toUpperCase(),
                style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold),
              ),
            ),
            const SizedBox(width: 8),
            Text(
              shortAddress,
              style: const TextStyle(color: Colors.white70, fontSize: 13),
            ),
            const SizedBox(width: 4),
            const Icon(Icons.keyboard_arrow_down, color: Colors.white38, size: 16),
          ],
        ),
      ),
    );
  }
}
