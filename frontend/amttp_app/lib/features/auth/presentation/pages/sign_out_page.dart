import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../../core/auth/auth_provider.dart';

/// Trampoline page that signs out the current user and redirects to sign-in.
/// Used when navigating from the external landing page to ensure
/// a fresh authentication flow.
class SignOutPage extends ConsumerStatefulWidget {
  const SignOutPage({super.key});

  @override
  ConsumerState<SignOutPage> createState() => _SignOutPageState();
}

class _SignOutPageState extends ConsumerState<SignOutPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await ref.read(authProvider.notifier).signOut();
      if (mounted) {
        context.go('/sign-in');
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: Color(0xFF0A0A0F),
      body: Center(
        child: CircularProgressIndicator(color: Color(0xFF6366F1)),
      ),
    );
  }
}
