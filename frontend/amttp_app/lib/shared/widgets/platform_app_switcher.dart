/// Platform App Header (Cross-Platform)
/// 
/// Unified header component with app switcher for AMTTP Platform
/// Works on web, iOS, and Android

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

/// App switcher bar for switching between Wallet and War Room
class PlatformAppSwitcherBar extends StatefulWidget {
  final String currentApp; // 'wallet' or 'war-room'
  
  const PlatformAppSwitcherBar({
    super.key,
    this.currentApp = 'wallet',
  });

  @override
  State<PlatformAppSwitcherBar> createState() => _PlatformAppSwitcherBarState();
}

class _PlatformAppSwitcherBarState extends State<PlatformAppSwitcherBar> {
  bool _isOpen = false;
  final _layerLink = LayerLink();
  OverlayEntry? _overlayEntry;

  String get _walletUrl {
    if (kIsWeb) {
      final uri = Uri.base;
      if (uri.host == 'localhost' || uri.host == '127.0.0.1') {
        return 'http://localhost:3010';
      }
      return '${uri.scheme}://${uri.host}';
    }
    return 'https://app.amttp.io';
  }

  String get _warRoomUrl {
    if (kIsWeb) {
      final uri = Uri.base;
      if (uri.host == 'localhost' || uri.host == '127.0.0.1') {
        return 'http://localhost:3006';
      }
      return '${uri.scheme}://${uri.host}/war-room';
    }
    return 'https://app.amttp.io/war-room';
  }

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

  Future<void> _navigateToApp(String url) async {
    _closeDropdown();
    
    final uri = Uri.parse(url);
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
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
              offset: const Offset(0, 44),
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
                          if (widget.currentApp != 'wallet') {
                            _navigateToApp(_walletUrl);
                          } else {
                            _closeDropdown();
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
                          if (widget.currentApp != 'war-room') {
                            _navigateToApp(_warRoomUrl);
                          } else {
                            _closeDropdown();
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

/// Compact platform header for Flutter app
class CompactPlatformHeader extends StatelessWidget {
  final String currentApp;
  final Widget? trailing;
  final VoidCallback? onNotificationTap;

  const CompactPlatformHeader({
    super.key,
    this.currentApp = 'wallet',
    this.trailing,
    this.onNotificationTap,
  });

  @override
  Widget build(BuildContext context) {
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
          // Logo
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
          
          const SizedBox(width: 12),
          
          // App Switcher
          PlatformAppSwitcherBar(currentApp: currentApp),
          
          const Spacer(),
          
          // Notification bell
          if (onNotificationTap != null)
            IconButton(
              onPressed: onNotificationTap,
              icon: Stack(
                children: [
                  const Icon(Icons.notifications_outlined, color: Colors.white70, size: 22),
                  Positioned(
                    right: 0,
                    top: 0,
                    child: Container(
                      width: 8,
                      height: 8,
                      decoration: const BoxDecoration(
                        color: Color(0xFFEF4444),
                        shape: BoxShape.circle,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          
          // Trailing widget
          if (trailing != null) trailing!,
        ],
      ),
    );
  }
}
