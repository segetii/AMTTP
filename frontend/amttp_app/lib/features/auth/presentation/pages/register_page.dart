import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../../core/auth/auth_provider.dart';
import '../../../../core/rbac/roles.dart';
import '../../../../core/theme/app_theme.dart';

/// Register Page - Create new user account with role selection
/// Only End User roles (R1, R2) can self-register - institutional roles require admin invite
class RegisterPage extends ConsumerStatefulWidget {
  const RegisterPage({super.key});

  @override
  ConsumerState<RegisterPage> createState() => _RegisterPageState();
}

class _RegisterPageState extends ConsumerState<RegisterPage> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();
  final _displayNameController = TextEditingController();
  final _walletAddressController = TextEditingController();
  
  bool _obscurePassword = true;
  bool _obscureConfirmPassword = true;
  Role _selectedRole = Role.r1EndUser;  // Default to R1 End User
  bool _acceptTerms = false;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    _displayNameController.dispose();
    _walletAddressController.dispose();
    super.dispose();
  }

  Future<void> _register() async {
    if (!_formKey.currentState!.validate()) return;

    if (!_acceptTerms) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Please accept the Terms of Service'),
          backgroundColor: AppTheme.dangerRed,
        ),
      );
      return;
    }

    final success = await ref.read(authProvider.notifier).register(
      email: _emailController.text.trim(),
      password: _passwordController.text,
      displayName: _displayNameController.text.trim(),
      role: _selectedRole,
      walletAddress: _walletAddressController.text.trim().isNotEmpty 
          ? _walletAddressController.text.trim() 
          : null,
    );

    if (success && mounted) {
      // Navigate to home - router will handle role-based redirects
      context.go('/');
    }
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authProvider);

    return Scaffold(
      backgroundColor: AppTheme.darkBg,
      body: Container(
        decoration: const BoxDecoration(
          gradient: AppTheme.darkGradient,
        ),
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 500),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    // Logo
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          colors: [AppTheme.primaryBlue, AppTheme.primaryPurple],
                        ),
                        borderRadius: BorderRadius.circular(16),
                        boxShadow: [
                          BoxShadow(
                            color: AppTheme.primaryBlue.withOpacity(0.4),
                            blurRadius: 20,
                            offset: const Offset(0, 8),
                          ),
                        ],
                      ),
                      child: const Icon(Icons.shield, color: Colors.white, size: 36),
                    ),
                    const SizedBox(height: 20),
                    
                    const Text(
                      'Create Account',
                      style: TextStyle(
                        color: AppTheme.cleanWhite,
                        fontSize: 26,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'Join AMTTP for secure transfers',
                      style: TextStyle(color: AppTheme.mutedText),
                    ),
                    const SizedBox(height: 32),

                    // Registration Form
                    Container(
                      padding: const EdgeInsets.all(24),
                      decoration: BoxDecoration(
                        color: AppTheme.darkCard,
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(color: AppTheme.mutedText.withOpacity(0.2)),
                      ),
                      child: Form(
                        key: _formKey,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            // Role Selection - Only End User roles for self-registration
                            const Text(
                              'Select Account Type',
                              style: TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.w600),
                            ),
                            const SizedBox(height: 12),
                            Row(
                              children: [
                                Expanded(child: _buildRoleOption(Role.r1EndUser)),
                                const SizedBox(width: 8),
                                Expanded(child: _buildRoleOption(Role.r2EndUserPep)),
                              ],
                            ),
                            const SizedBox(height: 8),
                            Text(
                              'Institutional roles (R3-R6) require admin invitation',
                              style: TextStyle(color: AppTheme.mutedText, fontSize: 11),
                            ),
                            const SizedBox(height: 24),

                            // Display Name
                            const Text('Display Name', style: TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.w500)),
                            const SizedBox(height: 8),
                            TextFormField(
                              controller: _displayNameController,
                              style: const TextStyle(color: AppTheme.cleanWhite),
                              decoration: _inputDecoration('Enter your name', Icons.person_outline),
                              validator: (value) {
                                if (value == null || value.isEmpty) {
                                  return 'Please enter your name';
                                }
                                return null;
                              },
                            ),
                            const SizedBox(height: 16),

                            // Email
                            const Text('Email', style: TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.w500)),
                            const SizedBox(height: 8),
                            TextFormField(
                              controller: _emailController,
                              keyboardType: TextInputType.emailAddress,
                              style: const TextStyle(color: AppTheme.cleanWhite),
                              decoration: _inputDecoration('Enter your email', Icons.email_outlined),
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
                            const SizedBox(height: 16),

                            // Password
                            const Text('Password', style: TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.w500)),
                            const SizedBox(height: 8),
                            TextFormField(
                              controller: _passwordController,
                              obscureText: _obscurePassword,
                              style: const TextStyle(color: AppTheme.cleanWhite),
                              decoration: InputDecoration(
                                hintText: 'Create a password',
                                hintStyle: const TextStyle(color: AppTheme.mutedText),
                                prefixIcon: const Icon(Icons.lock_outlined, color: AppTheme.mutedText),
                                suffixIcon: IconButton(
                                  icon: Icon(
                                    _obscurePassword ? Icons.visibility_off : Icons.visibility,
                                    color: AppTheme.mutedText,
                                  ),
                                  onPressed: () => setState(() => _obscurePassword = !_obscurePassword),
                                ),
                                filled: true,
                                fillColor: AppTheme.darkBg,
                                border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(12),
                                  borderSide: BorderSide.none,
                                ),
                                focusedBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(12),
                                  borderSide: const BorderSide(color: AppTheme.primaryBlue),
                                ),
                              ),
                              validator: (value) {
                                if (value == null || value.isEmpty) {
                                  return 'Please enter a password';
                                }
                                if (value.length < 6) {
                                  return 'Password must be at least 6 characters';
                                }
                                return null;
                              },
                            ),
                            const SizedBox(height: 16),

                            // Confirm Password
                            const Text('Confirm Password', style: TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.w500)),
                            const SizedBox(height: 8),
                            TextFormField(
                              controller: _confirmPasswordController,
                              obscureText: _obscureConfirmPassword,
                              style: const TextStyle(color: AppTheme.cleanWhite),
                              decoration: InputDecoration(
                                hintText: 'Confirm your password',
                                hintStyle: const TextStyle(color: AppTheme.mutedText),
                                prefixIcon: const Icon(Icons.lock_outlined, color: AppTheme.mutedText),
                                suffixIcon: IconButton(
                                  icon: Icon(
                                    _obscureConfirmPassword ? Icons.visibility_off : Icons.visibility,
                                    color: AppTheme.mutedText,
                                  ),
                                  onPressed: () => setState(() => _obscureConfirmPassword = !_obscureConfirmPassword),
                                ),
                                filled: true,
                                fillColor: AppTheme.darkBg,
                                border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(12),
                                  borderSide: BorderSide.none,
                                ),
                                focusedBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(12),
                                  borderSide: const BorderSide(color: AppTheme.primaryBlue),
                                ),
                              ),
                              validator: (value) {
                                if (value != _passwordController.text) {
                                  return 'Passwords do not match';
                                }
                                return null;
                              },
                            ),
                            const SizedBox(height: 16),

                            // Wallet Address (Optional)
                            const Text(
                              'Wallet Address (Optional)',
                              style: TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.w500),
                            ),
                            const SizedBox(height: 8),
                            TextFormField(
                              controller: _walletAddressController,
                              style: const TextStyle(color: AppTheme.cleanWhite, fontFamily: 'monospace'),
                              decoration: _inputDecoration('0x...', Icons.account_balance_wallet_outlined),
                            ),
                            const SizedBox(height: 20),

                            // Terms of Service
                            Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Checkbox(
                                  value: _acceptTerms,
                                  onChanged: (v) => setState(() => _acceptTerms = v ?? false),
                                  activeColor: AppTheme.primaryBlue,
                                ),
                                Expanded(
                                  child: Padding(
                                    padding: const EdgeInsets.only(top: 12),
                                    child: RichText(
                                      text: TextSpan(
                                        style: const TextStyle(color: AppTheme.mutedText, fontSize: 13),
                                        children: [
                                          const TextSpan(text: 'I agree to the '),
                                          TextSpan(
                                            text: 'Terms of Service',
                                            style: TextStyle(color: AppTheme.primaryBlue),
                                          ),
                                          const TextSpan(text: ' and '),
                                          TextSpan(
                                            text: 'Privacy Policy',
                                            style: TextStyle(color: AppTheme.primaryBlue),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 20),

                            // Error Message
                            if (authState.errorMessage != null)
                              Container(
                                padding: const EdgeInsets.all(12),
                                margin: const EdgeInsets.only(bottom: 16),
                                decoration: BoxDecoration(
                                  color: AppTheme.dangerRed.withOpacity(0.1),
                                  borderRadius: BorderRadius.circular(8),
                                  border: Border.all(color: AppTheme.dangerRed.withOpacity(0.5)),
                                ),
                                child: Row(
                                  children: [
                                    const Icon(Icons.error_outline, color: AppTheme.dangerRed, size: 20),
                                    const SizedBox(width: 8),
                                    Expanded(
                                      child: Text(
                                        authState.errorMessage!,
                                        style: const TextStyle(color: AppTheme.dangerRed, fontSize: 13),
                                      ),
                                    ),
                                  ],
                                ),
                              ),

                            // Register Button
                            SizedBox(
                              width: double.infinity,
                              height: 52,
                              child: ElevatedButton(
                                onPressed: authState.isLoading ? null : _register,
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: AppTheme.primaryBlue,
                                  foregroundColor: Colors.white,
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                ),
                                child: authState.isLoading
                                    ? const SizedBox(
                                        width: 24,
                                        height: 24,
                                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                      )
                                    : const Text(
                                        'Create Account',
                                        style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                                      ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 24),

                    // Sign In Link
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Text('Already have an account?', style: TextStyle(color: AppTheme.mutedText)),
                        TextButton(
                          onPressed: () => context.go('/sign-in'),
                          child: const Text('Sign In'),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildRoleOption(Role role) {
    final isSelected = _selectedRole == role;
    final color = _getRoleColor(role);
    final icon = _getRoleIcon(role);
    final label = _getRoleLabel(role);

    return GestureDetector(
      onTap: () => setState(() => _selectedRole = role),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 8),
        decoration: BoxDecoration(
          color: isSelected ? color.withOpacity(0.2) : AppTheme.darkBg,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isSelected ? color : AppTheme.mutedText.withOpacity(0.3),
            width: isSelected ? 2 : 1,
          ),
        ),
        child: Column(
          children: [
            Icon(icon, color: isSelected ? color : AppTheme.mutedText, size: 24),
            const SizedBox(height: 4),
            Text(
              label,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: isSelected ? color : AppTheme.mutedText,
                fontSize: 11,
                fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
              ),
            ),
            const SizedBox(height: 2),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: color.withOpacity(0.2),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                role.code.substring(0, 2),  // "R1" or "R2"
                style: TextStyle(color: color, fontSize: 9, fontWeight: FontWeight.bold),
              ),
            ),
          ],
        ),
      ),
    );
  }

  InputDecoration _inputDecoration(String hint, IconData icon) {
    return InputDecoration(
      hintText: hint,
      hintStyle: const TextStyle(color: AppTheme.mutedText),
      prefixIcon: Icon(icon, color: AppTheme.mutedText),
      filled: true,
      fillColor: AppTheme.darkBg,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide.none,
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: AppTheme.primaryBlue),
      ),
    );
  }

  Color _getRoleColor(Role role) {
    switch (role) {
      case Role.r1EndUser:
        return AppTheme.primaryBlue;
      case Role.r2EndUserPep:
        return AppTheme.warningOrange;
      default:
        return AppTheme.primaryPurple;
    }
  }

  IconData _getRoleIcon(Role role) {
    switch (role) {
      case Role.r1EndUser:
        return Icons.person_rounded;
      case Role.r2EndUserPep:
        return Icons.verified_user_rounded;
      default:
        return Icons.business_rounded;
    }
  }

  String _getRoleLabel(Role role) {
    switch (role) {
      case Role.r1EndUser:
        return 'Personal';
      case Role.r2EndUserPep:
        return 'PEP/HNW';
      default:
        return role.displayName;
    }
  }
}
