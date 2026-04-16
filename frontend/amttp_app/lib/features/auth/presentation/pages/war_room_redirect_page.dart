import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/platform/web_stub.dart'
    if (dart.library.html) 'dart:html' as html;
import '../../../../core/auth/auth_provider.dart';

/// A trampoline page that performs a full browser redirect to the
/// standalone Next.js War Room. GoRouter navigates here for R3+ users,
/// and initState immediately triggers a full page navigation that
/// replaces the Flutter SPA with the Next.js app.
///
/// The user's role and display name are passed as query parameters so
/// the Next.js War Room can create the correct session for the
/// authenticated role (R3, R4, R5, or R6) instead of defaulting to R3.
class WarRoomRedirectPage extends ConsumerStatefulWidget {
  const WarRoomRedirectPage({super.key});

  @override
  ConsumerState<WarRoomRedirectPage> createState() =>
      _WarRoomRedirectPageState();
}

class _WarRoomRedirectPageState extends ConsumerState<WarRoomRedirectPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final authState = ref.read(authProvider);
      final user = authState.user;

      // Only allow R3+ users to redirect to War Room
      if (user == null || user.role.level < 3) {
        // Not authenticated or wrong role — go back to sign-in
        Navigator.of(context).pop();
        return;
      }

      // Build query params to pass role info to Next.js
      final role = user.role.code;
      final name = user.displayName;
      final email = user.email;

      // Generate a one-time nonce to prevent unauthenticated URL crafting.
      // This nonce is stored in a cookie (readable by Next.js on same domain)
      // and must match the URL param for the War Room to accept the redirect.
      final nonce = '${DateTime.now().millisecondsSinceEpoch}_${Random().nextInt(999999)}';
      html.document.cookie =
          'amttp_redirect_nonce=$nonce; Path=/; SameSite=Lax; max-age=60';

      final params = Uri(queryParameters: {
        'role': role,
        'name': name,
        'email': email,
        'nonce': nonce,
      }).query;

      // Determine the correct Next.js War Room URL based on environment:
      // - Dev mode (Flutter on port 3010): redirect to localhost:3006/war-room
      // - Production/Docker (nginx): use relative /war-room path
      final currentPort = html.window.location.port;
      final String warRoomUrl;
      if (currentPort == '3010') {
        warRoomUrl = 'http://localhost:3006/war-room?$params';
      } else {
        warRoomUrl = '/war-room?$params';
      }
      html.window.location.replace(warRoomUrl);
    });
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: Color(0xFF0A0A0F),
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(
              color: Color(0xFF00D4AA),
              strokeWidth: 3,
            ),
            SizedBox(height: 24),
            Text(
              'Loading War Room...',
              style: TextStyle(
                color: Colors.white70,
                fontSize: 16,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
