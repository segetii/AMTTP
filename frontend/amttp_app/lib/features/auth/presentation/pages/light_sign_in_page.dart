import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../../core/auth/auth_provider.dart';
import '../../../../core/auth/auth_service.dart';
import '../../../../core/rbac/roles.dart';
import '../../../../core/theme/app_theme.dart';

/// Light Sign In Page - Clean white-themed login with RBAC demo accounts
class LightSignInPage extends ConsumerStatefulWidget {
  const LightSignInPage({super.key});

  @override
  ConsumerState<LightSignInPage> createState() => _LightSignInPageState();
}

class _LightSignInPageState extends ConsumerState<LightSignInPage>
    with SingleTickerProviderStateMixin {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _obscurePassword = true;
  bool _rememberMe = true;
  late AnimationController _animController;
  late Animation<double> _fadeAnim;
  late Animation<Offset> _slideAnim;

  @override
  void initState() {
    super.initState();
    _animController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );
    _fadeAnim = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(parent: _animController, curve: Curves.easeOut),
    );
    _slideAnim = Tween<Offset>(
      begin: const Offset(0, 0.1),
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
        final mode = getModeForRole(user.role);
        if (mode == AppMode.focusMode) {
          context.go('/');
        } else {
          context.go('/war-room');
        }
      } else {
        context.go('/');
      }
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
      backgroundColor: AppTheme.slate50,
      body: SafeArea(
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
                      // Logo with blue gradient
                      Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            colors: [AppTheme.blue500, AppTheme.blue600],
                          ),
                          borderRadius: BorderRadius.circular(16),
                          boxShadow: [
                            BoxShadow(
                              color: AppTheme.blue500.withOpacity(0.3),
                              blurRadius: 20,
                              offset: const Offset(0, 8),
                            ),
                          ],
                        ),
                        child: const Icon(Icons.shield, color: Colors.white, size: 40),
                      ),
                      const SizedBox(height: 24),
                      
                      // Title
                      Text(
                        'Welcome to AMTTP',
                        style: TextStyle(
                          color: AppTheme.slate800,
                          fontSize: 28,
                          fontWeight: FontWeight.bold,
                          letterSpacing: -0.5,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Secure blockchain transfers with AI protection',
                        style: TextStyle(
                          color: AppTheme.slate500,
                          fontSize: 15,
                        ),
                      ),
                      const SizedBox(height: 40),

                      // Login Card
                      Container(
                        padding: const EdgeInsets.all(24),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(16),
                          boxShadow: [
                            BoxShadow(
                              color: Colors.black.withOpacity(0.05),
                              blurRadius: 20,
                              offset: const Offset(0, 4),
                            ),
                          ],
                        ),
                        child: Form(
                          key: _formKey,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              // Email
                              Text(
                                'Email',
                                style: TextStyle(
                                  color: AppTheme.slate700,
                                  fontWeight: FontWeight.w500,
                                  fontSize: 14,
                                ),
                              ),
                              const SizedBox(height: 8),
                              TextFormField(
                                controller: _emailController,
                                keyboardType: TextInputType.emailAddress,
                                decoration: InputDecoration(
                                  hintText: 'Enter your email',
                                  hintStyle: TextStyle(color: AppTheme.slate400),
                                  prefixIcon: Icon(Icons.email_outlined, color: AppTheme.slate400),
                                  filled: true,
                                  fillColor: AppTheme.slate50,
                                  border: OutlineInputBorder(
                                    borderRadius: BorderRadius.circular(12),
                                    borderSide: BorderSide(color: AppTheme.slate200),
                                  ),
                                  enabledBorder: OutlineInputBorder(
                                    borderRadius: BorderRadius.circular(12),
                                    borderSide: BorderSide(color: AppTheme.slate200),
                                  ),
                                  focusedBorder: OutlineInputBorder(
                                    borderRadius: BorderRadius.circular(12),
                                    borderSide: BorderSide(color: AppTheme.blue500),
                                  ),
                                ),
                                validator: (value) {
                                  if (value == null || value.isEmpty) {
                                    return 'Please enter your email';
                                  }
                                  if (!value.contains('@')) {
                                    return 'Please enter a valid email';
                                  }
                                  return null;
                                },
                              ),
                              const SizedBox(height: 20),

                              // Password
                              Text(
                                'Password',
                                style: TextStyle(
                                  color: AppTheme.slate700,
                                  fontWeight: FontWeight.w500,
                                  fontSize: 14,
                                ),
                              ),
                              const SizedBox(height: 8),
                              TextFormField(
                                controller: _passwordController,
                                obscureText: _obscurePassword,
                                decoration: InputDecoration(
                                  hintText: 'Enter your password',
                                  hintStyle: TextStyle(color: AppTheme.slate400),
                                  prefixIcon: Icon(Icons.lock_outlined, color: AppTheme.slate400),
                                  suffixIcon: IconButton(
                                    icon: Icon(
                                      _obscurePassword ? Icons.visibility_off : Icons.visibility,
                                      color: AppTheme.slate400,
                                    ),
                                    onPressed: () => setState(() => _obscurePassword = !_obscurePassword),
                                  ),
                                  filled: true,
                                  fillColor: AppTheme.slate50,
                                  border: OutlineInputBorder(
                                    borderRadius: BorderRadius.circular(12),
                                    borderSide: BorderSide(color: AppTheme.slate200),
                                  ),
                                  enabledBorder: OutlineInputBorder(
                                    borderRadius: BorderRadius.circular(12),
                                    borderSide: BorderSide(color: AppTheme.slate200),
                                  ),
                                  focusedBorder: OutlineInputBorder(
                                    borderRadius: BorderRadius.circular(12),
                                    borderSide: BorderSide(color: AppTheme.blue500),
                                  ),
                                ),
                                validator: (value) {
                                  if (value == null || value.isEmpty) {
                                    return 'Please enter your password';
                                  }
                                  return null;
                                },
                              ),
                              const SizedBox(height: 16),

                              // Remember & Forgot
                              Row(
                                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                children: [
                                  Row(
                                    children: [
                                      SizedBox(
                                        width: 20,
                                        height: 20,
                                        child: Checkbox(
                                          value: _rememberMe,
                                          onChanged: (v) => setState(() => _rememberMe = v ?? true),
                                          activeColor: AppTheme.blue500,
                                          shape: RoundedRectangleBorder(
                                            borderRadius: BorderRadius.circular(4),
                                          ),
                                        ),
                                      ),
                                      const SizedBox(width: 8),
                                      Text('Remember me', style: TextStyle(color: AppTheme.slate600, fontSize: 14)),
                                    ],
                                  ),
                                  TextButton(
                                    onPressed: () {},
                                    child: Text(
                                      'Forgot password?',
                                      style: TextStyle(color: AppTheme.blue500),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 16),

                              // Error
                              if (authState.errorMessage != null)
                                Container(
                                  padding: const EdgeInsets.all(12),
                                  margin: const EdgeInsets.only(bottom: 16),
                                  decoration: BoxDecoration(
                                    color: AppTheme.red50,
                                    borderRadius: BorderRadius.circular(8),
                                    border: Border.all(color: AppTheme.red100),
                                  ),
                                  child: Row(
                                    children: [
                                      Icon(Icons.error_outline, color: AppTheme.red500, size: 20),
                                      const SizedBox(width: 8),
                                      Expanded(
                                        child: Text(
                                          authState.errorMessage!,
                                          style: TextStyle(color: AppTheme.red600, fontSize: 13),
                                        ),
                                      ),
                                    ],
                                  ),
                                ),

                              // Sign In Button - Blue
                              SizedBox(
                                width: double.infinity,
                                height: 50,
                                child: ElevatedButton(
                                  onPressed: authState.isLoading ? null : _signIn,
                                  style: ElevatedButton.styleFrom(
                                    backgroundColor: AppTheme.blue500,
                                    foregroundColor: Colors.white,
                                    elevation: 0,
                                    shape: RoundedRectangleBorder(
                                      borderRadius: BorderRadius.circular(12),
                                    ),
                                  ),
                                  child: authState.isLoading
                                      ? const SizedBox(
                                          width: 24,
                                          height: 24,
                                          child: CircularProgressIndicator(
                                            strokeWidth: 2,
                                            color: Colors.white,
                                          ),
                                        )
                                      : const Text(
                                          'Sign In',
                                          style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                                        ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: 20),

                      // Register Link
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Text("Don't have an account?", style: TextStyle(color: AppTheme.slate500)),
                          TextButton(
                            onPressed: () => context.go('/register'),
                            child: Text(
                              'Create Account',
                              style: TextStyle(color: AppTheme.blue500, fontWeight: FontWeight.w600),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 24),

                      // Demo Accounts Section
                      Container(
                        padding: const EdgeInsets.all(20),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(color: AppTheme.slate200),
                        ),
                        child: Column(
                          children: [
                            Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Container(
                                  padding: const EdgeInsets.all(6),
                                  decoration: BoxDecoration(
                                    color: AppTheme.blue50,
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  child: Icon(Icons.play_circle_outline, color: AppTheme.blue500, size: 18),
                                ),
                                const SizedBox(width: 8),
                                Text(
                                  'Quick Demo Access',
                                  style: TextStyle(
                                    color: AppTheme.slate800,
                                    fontWeight: FontWeight.bold,
                                    fontSize: 15,
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 4),
                            Text(
                              'Click to login with any role',
                              style: TextStyle(color: AppTheme.slate500, fontSize: 13),
                            ),
                            const SizedBox(height: 16),
                            ...demoCredentials.map((cred) => _buildDemoTile(cred)),
                          ],
                        ),
                      ),
                      const SizedBox(height: 32),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildDemoTile(Map<String, String> cred) {
    // Use the exact RBAC profile colors
    final colorValue = int.tryParse(cred['color'] ?? '0xFF3B82F6');
    final color = Color(colorValue ?? 0xFF3B82F6);
    
    IconData getIcon() {
      switch (cred['role']) {
        case 'R1': return Icons.person_outline;
        case 'R2': return Icons.verified_user_outlined;
        case 'R3': return Icons.analytics_outlined;
        case 'R4': return Icons.policy_outlined;
        case 'R5': return Icons.admin_panel_settings_outlined;
        case 'R6': return Icons.security;
        default: return Icons.person_outline;
      }
    }
    
    final isFocusMode = cred['role'] == 'R1' || cred['role'] == 'R2';

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: () => _quickLogin(cred['email']!, cred['password']!),
          borderRadius: BorderRadius.circular(12),
          child: Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: color.withOpacity(0.05),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: color.withOpacity(0.2)),
            ),
            child: Row(
              children: [
                // Role Icon with color
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: color.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(getIcon(), color: color, size: 20),
                ),
                const SizedBox(width: 12),
                // Role Info
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          // Role badge
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: color,
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              cred['role'] ?? '',
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 10,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            cred['profile'] ?? '',
                            style: TextStyle(
                              color: AppTheme.slate800,
                              fontWeight: FontWeight.w600,
                              fontSize: 14,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text(
                        cred['description'] ?? '',
                        style: TextStyle(color: AppTheme.slate500, fontSize: 12),
                      ),
                    ],
                  ),
                ),
                // Mode badge
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: isFocusMode 
                      ? AppTheme.green500.withOpacity(0.1)
                      : AppTheme.purple500.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    isFocusMode ? 'Focus' : 'War Room',
                    style: TextStyle(
                      color: isFocusMode ? AppTheme.green600 : AppTheme.purple600,
                      fontSize: 10,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
