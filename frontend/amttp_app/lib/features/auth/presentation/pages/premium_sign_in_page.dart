import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';
import 'dart:ui';
import '../../../../core/auth/auth_provider.dart';
import '../../../../core/auth/auth_service.dart';
import '../../../../core/rbac/roles.dart';

/// Premium Fintech Sign In Page - Metamask/Revolut Style
/// 
/// Simplified routing:
/// - End Users (R1, R2) → Flutter Wallet App (/)
/// - Institutional (R3+) → Next.js War Room (external)
class PremiumSignInPage extends ConsumerStatefulWidget {
  const PremiumSignInPage({super.key});

  @override
  ConsumerState<PremiumSignInPage> createState() => _PremiumSignInPageState();
}

class _PremiumSignInPageState extends ConsumerState<PremiumSignInPage>
    with SingleTickerProviderStateMixin {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _obscurePassword = true;
  late AnimationController _animController;
  late Animation<double> _fadeAnim;
  late Animation<Offset> _slideAnim;

  // Next.js War Room URL
  static const String _warRoomUrl = 'http://localhost:3006/war-room';

  @override
  void initState() {
    super.initState();
    SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.light,
    ));
    _animController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    );
    _fadeAnim = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(parent: _animController, curve: Curves.easeOut),
    );
    _slideAnim = Tween<Offset>(
      begin: const Offset(0, 0.15),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _animController, curve: Curves.easeOutCubic));
    _animController.forward();
  }

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    _animController.dispose();
    super.dispose();
  }

  Future<void> _signIn() async {
    if (!_formKey.currentState!.validate()) return;

    final success = await ref.read(authProvider.notifier).signIn(
      email: _emailController.text.trim(),
      password: _passwordController.text,
    );

    if (success && mounted) {
      final user = ref.read(authProvider).user;
      if (user != null) {
        _routeToAppropriateDestination(user.role);
      } else {
        context.go('/');
      }
    }
  }

  /// Route user based on role:
  /// - End Users (R1, R2) → Flutter Wallet (/)
  /// - Institutional (R3+) → Next.js War Room (external link)
  void _routeToAppropriateDestination(Role role) {
    if (role.level <= 2) {
      // End Users stay in Flutter
      context.go('/');
    } else {
      // Institutional users go to Next.js War Room
      _launchWarRoom();
    }
  }

  Future<void> _launchWarRoom() async {
    final uri = Uri.parse(_warRoomUrl);
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
    // Also navigate to home in case they come back
    if (mounted) {
      context.go('/');
    }
  }

  void _quickLogin(String email, String password) {
    _emailController.text = email;
    _passwordController.text = password;
    _signIn();
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authProvider);
    final demoCredentials = AuthService.getDemoCredentials();

    return Scaffold(
      backgroundColor: const Color(0xFF0A0A0F),
      body: Stack(
        children: [
          // Animated gradient background
          _buildAnimatedBackground(),
          
          // Main content
          SafeArea(
            child: Center(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: FadeTransition(
                  opacity: _fadeAnim,
                  child: SlideTransition(
                    position: _slideAnim,
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 420),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          // Logo and branding
                          _buildLogo(),
                          const SizedBox(height: 48),
                          
                          // Login card
                          _buildLoginCard(authState),
                          const SizedBox(height: 32),
                          
                          // Demo accounts
                          _buildDemoAccounts(demoCredentials),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAnimatedBackground() {
    return Stack(
      children: [
        // Top gradient orb
        Positioned(
          top: -100,
          right: -100,
          child: Container(
            width: 400,
            height: 400,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: RadialGradient(
                colors: [
                  const Color(0xFF6366F1).withOpacity(0.3),
                  const Color(0xFF6366F1).withOpacity(0.0),
                ],
              ),
            ),
          ),
        ),
        // Bottom gradient orb
        Positioned(
          bottom: -150,
          left: -100,
          child: Container(
            width: 500,
            height: 500,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: RadialGradient(
                colors: [
                  const Color(0xFF8B5CF6).withOpacity(0.2),
                  const Color(0xFF8B5CF6).withOpacity(0.0),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildLogo() {
    return Column(
      children: [
        // Logo icon with gradient
        Container(
          width: 80,
          height: 80,
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [Color(0xFF6366F1), Color(0xFF8B5CF6)],
            ),
            borderRadius: BorderRadius.circular(24),
            boxShadow: [
              BoxShadow(
                color: const Color(0xFF6366F1).withOpacity(0.4),
                blurRadius: 30,
                offset: const Offset(0, 10),
              ),
            ],
          ),
          child: const Center(
            child: Text(
              'A',
              style: TextStyle(
                color: Colors.white,
                fontSize: 40,
                fontWeight: FontWeight.bold,
                letterSpacing: -2,
              ),
            ),
          ),
        ),
        const SizedBox(height: 24),
        
        // App name
        const Text(
          'AMTTP',
          style: TextStyle(
            color: Colors.white,
            fontSize: 32,
            fontWeight: FontWeight.bold,
            letterSpacing: 4,
          ),
        ),
        const SizedBox(height: 8),
        
        // Tagline
        Text(
          'Secure • Compliant • Decentralized',
          style: TextStyle(
            color: Colors.white.withOpacity(0.5),
            fontSize: 14,
            fontWeight: FontWeight.w500,
            letterSpacing: 1,
          ),
        ),
      ],
    );
  }

  Widget _buildLoginCard(AuthState authState) {
    return Container(
      padding: const EdgeInsets.all(32),
      decoration: BoxDecoration(
        color: const Color(0xFF12121A),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(
          color: const Color(0xFF1E1E2E),
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.3),
            blurRadius: 30,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Form(
        key: _formKey,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Header
            const Text(
              'Welcome back',
              style: TextStyle(
                color: Colors.white,
                fontSize: 24,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Sign in to access your account',
              style: TextStyle(
                color: Colors.white.withOpacity(0.5),
                fontSize: 14,
              ),
            ),
            const SizedBox(height: 32),
            
            // Email field
            _buildTextField(
              controller: _emailController,
              label: 'Email',
              hint: 'Enter your email',
              icon: Icons.email_outlined,
              keyboardType: TextInputType.emailAddress,
              validator: (v) => v == null || v.isEmpty ? 'Enter email' : null,
            ),
            const SizedBox(height: 20),
            
            // Password field
            _buildTextField(
              controller: _passwordController,
              label: 'Password',
              hint: 'Enter your password',
              icon: Icons.lock_outline_rounded,
              obscureText: _obscurePassword,
              suffixIcon: IconButton(
                icon: Icon(
                  _obscurePassword ? Icons.visibility_off_outlined : Icons.visibility_outlined,
                  color: const Color(0xFF64748B),
                  size: 20,
                ),
                onPressed: () => setState(() => _obscurePassword = !_obscurePassword),
              ),
              validator: (v) => v == null || v.isEmpty ? 'Enter password' : null,
            ),
            const SizedBox(height: 32),
            
            // Sign in button
            _buildSignInButton(authState),
            const SizedBox(height: 20),
            
            // Divider
            Row(
              children: [
                Expanded(child: Container(height: 1, color: const Color(0xFF1E1E2E))),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Text(
                    'or continue with',
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.4),
                      fontSize: 12,
                    ),
                  ),
                ),
                Expanded(child: Container(height: 1, color: const Color(0xFF1E1E2E))),
              ],
            ),
            const SizedBox(height: 20),
            
            // Social buttons
            Row(
              children: [
                Expanded(child: _buildSocialButton('Connect Wallet', Icons.account_balance_wallet_outlined)),
                const SizedBox(width: 12),
                Expanded(child: _buildSocialButton('Web3Auth', Icons.security_outlined)),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTextField({
    required TextEditingController controller,
    required String label,
    required String hint,
    required IconData icon,
    TextInputType? keyboardType,
    bool obscureText = false,
    Widget? suffixIcon,
    String? Function(String?)? validator,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(
            color: Colors.white.withOpacity(0.7),
            fontSize: 13,
            fontWeight: FontWeight.w500,
          ),
        ),
        const SizedBox(height: 8),
        TextFormField(
          controller: controller,
          keyboardType: keyboardType,
          obscureText: obscureText,
          validator: validator,
          style: const TextStyle(color: Colors.white, fontSize: 15),
          decoration: InputDecoration(
            hintText: hint,
            hintStyle: TextStyle(color: Colors.white.withOpacity(0.3)),
            prefixIcon: Icon(icon, color: const Color(0xFF64748B), size: 20),
            suffixIcon: suffixIcon,
            filled: true,
            fillColor: const Color(0xFF0A0A0F),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: const BorderSide(color: Color(0xFF1E1E2E)),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: const BorderSide(color: Color(0xFF1E1E2E)),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: const BorderSide(color: Color(0xFF6366F1), width: 1.5),
            ),
            errorBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: const BorderSide(color: Color(0xFFEF4444)),
            ),
            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
          ),
        ),
      ],
    );
  }

  Widget _buildSignInButton(AuthState authState) {
    return GestureDetector(
      onTap: authState.isLoading ? null : _signIn,
      child: Container(
        height: 56,
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [Color(0xFF6366F1), Color(0xFF8B5CF6)],
          ),
          borderRadius: BorderRadius.circular(16),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF6366F1).withOpacity(0.4),
              blurRadius: 20,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        child: Center(
          child: authState.isLoading
              ? const SizedBox(
                  width: 24,
                  height: 24,
                  child: CircularProgressIndicator(
                    color: Colors.white,
                    strokeWidth: 2.5,
                  ),
                )
              : const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      'Sign In',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    SizedBox(width: 8),
                    Icon(Icons.arrow_forward_rounded, color: Colors.white, size: 20),
                  ],
                ),
        ),
      ),
    );
  }

  Widget _buildSocialButton(String text, IconData icon) {
    return Container(
      height: 48,
      decoration: BoxDecoration(
        color: const Color(0xFF0A0A0F),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF1E1E2E)),
      ),
      child: Center(
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: const Color(0xFF64748B), size: 18),
            const SizedBox(width: 8),
            Text(
              text,
              style: const TextStyle(
                color: Color(0xFF94A3B8),
                fontSize: 13,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildDemoAccounts(List<Map<String, String>> demoCredentials) {
    // Build a lookup map from the list
    Map<String, Map<String, String>> credsMap = {};
    for (var cred in demoCredentials) {
      final role = cred['role'] ?? '';
      if (role == 'R1') credsMap['end_user'] = cred;
      if (role == 'R2') credsMap['pep_user'] = cred;
      if (role == 'R3') credsMap['analyst'] = cred;
      if (role == 'R4') credsMap['compliance'] = cred;
      if (role == 'R5') credsMap['admin'] = cred;
      if (role == 'R6') credsMap['super_admin'] = cred;
    }
    
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(left: 4, bottom: 16),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                  color: const Color(0xFF22C55E).withOpacity(0.15),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.science_outlined, color: Color(0xFF22C55E), size: 14),
                    SizedBox(width: 6),
                    Text(
                      'DEMO MODE',
                      style: TextStyle(
                        color: Color(0xFF22C55E),
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 1,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Text(
                'Quick access accounts',
                style: TextStyle(
                  color: Colors.white.withOpacity(0.4),
                  fontSize: 13,
                ),
              ),
            ],
          ),
        ),
        
        // Account cards
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            _buildDemoCard(
              title: 'End User',
              subtitle: 'R1 • Focus Mode',
              icon: Icons.person_outline_rounded,
              color: const Color(0xFF3B82F6),
              onTap: () {
                final creds = credsMap['end_user'];
                if (creds != null) _quickLogin(creds['email']!, creds['password']!);
              },
            ),
            _buildDemoCard(
              title: 'PeP User',
              subtitle: 'R2 • Focus Mode',
              icon: Icons.verified_user_outlined,
              color: const Color(0xFF8B5CF6),
              onTap: () {
                final creds = credsMap['pep_user'];
                if (creds != null) _quickLogin(creds['email']!, creds['password']!);
              },
            ),
            _buildDemoCard(
              title: 'Analyst',
              subtitle: 'R3 • War Room',
              icon: Icons.analytics_outlined,
              color: const Color(0xFFF59E0B),
              onTap: () {
                final creds = credsMap['analyst'];
                if (creds != null) _quickLogin(creds['email']!, creds['password']!);
              },
            ),
            _buildDemoCard(
              title: 'Compliance',
              subtitle: 'R4 • War Room',
              icon: Icons.gavel_outlined,
              color: const Color(0xFFEF4444),
              onTap: () {
                final creds = credsMap['compliance'];
                if (creds != null) _quickLogin(creds['email']!, creds['password']!);
              },
            ),
            _buildDemoCard(
              title: 'Admin',
              subtitle: 'R5 • War Room',
              icon: Icons.admin_panel_settings_outlined,
              color: const Color(0xFF10B981),
              onTap: () {
                final creds = credsMap['admin'];
                if (creds != null) _quickLogin(creds['email']!, creds['password']!);
              },
            ),
            _buildDemoCard(
              title: 'Super Admin',
              subtitle: 'R6 • War Room',
              icon: Icons.security_outlined,
              color: const Color(0xFFEC4899),
              onTap: () {
                final creds = credsMap['super_admin'];
                if (creds != null) _quickLogin(creds['email']!, creds['password']!);
              },
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildDemoCard({
    required String title,
    required String subtitle,
    required IconData icon,
    required Color color,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 120,
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: const Color(0xFF12121A),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: const Color(0xFF1E1E2E)),
        ),
        child: Column(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: color.withOpacity(0.15),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(icon, color: color, size: 22),
            ),
            const SizedBox(height: 12),
            Text(
              title,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 13,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              subtitle,
              style: TextStyle(
                color: Colors.white.withOpacity(0.4),
                fontSize: 11,
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}
