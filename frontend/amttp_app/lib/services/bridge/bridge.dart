/// Flutter ↔ Next.js Bridge Services
/// 
/// This package provides bidirectional communication between
/// the Flutter app and the Next.js analytics dashboard.
/// 
/// Usage:
/// ```dart
/// import 'package:amttp_app/services/bridge/bridge.dart';
/// 
/// // Initialize bridge after login
/// final bridge = FlutterNextJSBridge();
/// bridge.setSession(
///   sessionToken: token,
///   userId: user.id,
///   userRole: user.role,
///   walletAddress: user.wallet,
/// );
/// 
/// // Embed analytics in a Flutter screen
/// EmbeddedAnalytics(
///   route: '/detection-studio',
///   showFullScreenButton: true,
///   onTransactionSelected: (txHash) => print('Selected: $txHash'),
/// )
/// 
/// // Open full-screen analytics
/// bridge.openFullScreen('/war-room');
/// ```

library bridge;

export 'flutter_nextjs_bridge.dart';
export 'embedded_analytics.dart';
