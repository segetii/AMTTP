/// AMTTP Consumer App - End User Entry Point
/// 
/// This is the CLEAN entry point for the consumer-facing Flutter app.
/// It provides a streamlined experience with ONLY the features end users need:
/// 
/// ✅ Included Features:
/// - Home dashboard (balance, quick actions)
/// - Wallet (tokens, NFTs, receive)
/// - Transfer (send with trust check)
/// - Trust Check (verify recipients)
/// - History (transaction log)
/// - Disputes (raise/view disputes)
/// - Wallet Connect (connect MetaMask, etc.)
/// - Profile/Settings
/// 
/// ❌ NOT Included (these are in Next.js War Room for institutions):
/// - War Room / Detection Studio
/// - Policy Engine / Compliance Tools
/// - ML Models / Graph Explorer
/// - User Management / Admin
/// - Audit Chain Replay
/// 
/// Usage:
/// ```bash
/// # Build consumer app
/// flutter build web --dart-define=APP_MODE=consumer -t lib/main_consumer.dart
/// 
/// # Run consumer app
/// flutter run -t lib/main_consumer.dart
/// ```

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'core/router/consumer_app_router.dart';
import 'core/theme/app_theme.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  
  // Set system UI overlay style
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.dark,
      systemNavigationBarColor: Colors.white,
      systemNavigationBarIconBrightness: Brightness.dark,
    ),
  );
  
  // Set preferred orientations
  await SystemChrome.setPreferredOrientations([
    DeviceOrientation.portraitUp,
    DeviceOrientation.portraitDown,
  ]);
  
  runApp(
    const ProviderScope(
      child: AMTTPConsumerApp(),
    ),
  );
}

class AMTTPConsumerApp extends ConsumerWidget {
  const AMTTPConsumerApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(consumerRouterProvider);
    
    return MaterialApp.router(
      title: 'AMTTP',
      debugShowCheckedModeBanner: false,
      
      // Theme
      theme: AppTheme.lightTheme,
      darkTheme: AppTheme.darkTheme,
      themeMode: ThemeMode.system,
      
      // Router
      routerConfig: router,
      
      // Builder for global UI adjustments
      builder: (context, child) {
        // Ensure text doesn't scale beyond reasonable limits
        return MediaQuery(
          data: MediaQuery.of(context).copyWith(
            textScaler: TextScaler.linear(
              MediaQuery.of(context).textScaler.scale(1.0).clamp(0.8, 1.3),
            ),
          ),
          child: child ?? const SizedBox.shrink(),
        );
      },
    );
  }
}
