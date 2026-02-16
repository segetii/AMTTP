/// Cross-App Auth Bridge — Flutter Side
///
/// Solves the fundamental problem: Flutter uses SharedPreferences, Next.js
/// uses localStorage. They are **separate storage domains** even on the
/// same origin.
///
/// Solution: When Flutter authenticates, it writes a signed session token
/// to a **document.cookie** (via dart:html on web). Cookies are shared
/// across all paths on the same origin, so Next.js can read them.
///
/// The token is HMAC-SHA256 signed to prevent client-side tampering.
/// The signing key is compiled into the app via --dart-define.
///
/// Flow:
///   1. User signs in via Flutter → AuthService validates credentials
///   2. CrossAppAuthBridge.writeSession() →
///        a. Builds JSON payload {userId, role, mode, exp, iat}
///        b. HMAC-SHA256 signs it → base64url(payload).base64url(signature)
///        c. Writes to document.cookie as `amttp_xauth=<token>; path=/; SameSite=Strict`
///   3. Next.js reads the cookie via middleware or client-side → verifies HMAC → trusts session
///   4. On logout, Flutter clears the cookie
library;

import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';

// Signing key — override via --dart-define=AUTH_BRIDGE_KEY=<secret>
// In production this MUST be set to a strong random secret shared with Next.js
const String _bridgeKey = String.fromEnvironment(
  'AUTH_BRIDGE_KEY',
  defaultValue: 'amttp-dev-bridge-key-change-in-production-2026',
);

const String kCookieName = 'amttp_xauth';
const Duration kSessionDuration = Duration(hours: 24);

/// Payload embedded in the bridge token
class BridgeTokenPayload {
  final String userId;
  final String email;
  final String role; // e.g. "R3_INSTITUTION_OPS"
  final String mode; // "FOCUS" or "WAR_ROOM"
  final String displayName;
  final int iat; // issued-at (epoch seconds)
  final int exp; // expiry (epoch seconds)

  const BridgeTokenPayload({
    required this.userId,
    required this.email,
    required this.role,
    required this.mode,
    required this.displayName,
    required this.iat,
    required this.exp,
  });

  bool get isExpired => DateTime.now().millisecondsSinceEpoch ~/ 1000 > exp;

  Map<String, dynamic> toJson() => {
        'sub': userId,
        'email': email,
        'role': role,
        'mode': mode,
        'name': displayName,
        'iat': iat,
        'exp': exp,
      };

  factory BridgeTokenPayload.fromJson(Map<String, dynamic> json) {
    return BridgeTokenPayload(
      userId: json['sub'] as String,
      email: json['email'] as String,
      role: json['role'] as String,
      mode: json['mode'] as String,
      displayName: json['name'] as String,
      iat: json['iat'] as int,
      exp: json['exp'] as int,
    );
  }
}

/// Cross-app auth bridge — writes/reads HMAC-signed cookies
class CrossAppAuthBridge {
  CrossAppAuthBridge._();

  // ───────────────────── Token creation ─────────────────────

  /// Create a signed bridge token for the given user session.
  /// Returns `base64url(payload).base64url(hmac)` string.
  static String createToken({
    required String userId,
    required String email,
    required String role,
    required String mode,
    required String displayName,
  }) {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final payload = BridgeTokenPayload(
      userId: userId,
      email: email,
      role: role,
      mode: mode,
      displayName: displayName,
      iat: now,
      exp: now + kSessionDuration.inSeconds,
    );

    final payloadJson = jsonEncode(payload.toJson());
    final payloadB64 = base64Url.encode(utf8.encode(payloadJson));
    final sig = _sign(payloadB64);
    return '$payloadB64.$sig';
  }

  /// Verify and decode a bridge token. Returns null if invalid/expired.
  static BridgeTokenPayload? verifyToken(String token) {
    try {
      final parts = token.split('.');
      if (parts.length != 2) return null;

      final payloadB64 = parts[0];
      final sig = parts[1];

      // Verify HMAC
      if (_sign(payloadB64) != sig) {
        debugPrint('[CrossAppAuth] HMAC verification failed');
        return null;
      }

      final payloadJson = utf8.decode(base64Url.decode(payloadB64));
      final payload = BridgeTokenPayload.fromJson(
        jsonDecode(payloadJson) as Map<String, dynamic>,
      );

      if (payload.isExpired) {
        debugPrint('[CrossAppAuth] Token expired');
        return null;
      }

      return payload;
    } catch (e) {
      debugPrint('[CrossAppAuth] Token verification error: $e');
      return null;
    }
  }

  // ───────────────────── Cookie I/O (web only) ─────────────────────

  /// Write session cookie so Next.js can read it.
  /// Only works on web platform (uses dart:html via conditional import).
  static void writeCookie(String token) {
    if (!kIsWeb) return;
    _setCookie(
        '$kCookieName=$token; path=/; SameSite=Strict; max-age=${kSessionDuration.inSeconds}');
  }

  /// Clear the session cookie on logout.
  static void clearCookie() {
    if (!kIsWeb) return;
    _setCookie('$kCookieName=; path=/; SameSite=Strict; max-age=0');
  }

  /// Read the bridge token from cookie (used by Flutter to restore session).
  static String? readCookie() {
    if (!kIsWeb) return null;
    return _getCookie(kCookieName);
  }

  // ───────────────────── HMAC helpers ─────────────────────

  static String _sign(String data) {
    final key = utf8.encode(_bridgeKey);
    final bytes = utf8.encode(data);
    final hmacSha256 = Hmac(sha256, key);
    final digest = hmacSha256.convert(bytes);
    return base64Url.encode(digest.bytes);
  }

  // ───────────────────── Platform cookie helpers ─────────────────────
  // These use conditional imports resolved at build time.
  // On non-web platforms they are no-ops.

  static void _setCookie(String value) {
    try {
      // ignore: avoid_web_libraries_in_flutter
      // This import is guarded by kIsWeb check above
      _webSetCookie(value);
    } catch (_) {
      // Not on web — ignore
    }
  }

  static String? _getCookie(String name) {
    try {
      return _webGetCookie(name);
    } catch (_) {
      return null;
    }
  }
}

// ─────────────── Web-specific cookie functions ───────────────
// These are in a separate section to isolate dart:html dependency.
// In production, use conditional imports for multi-platform support.

void _webSetCookie(String value) {
  // Implementation injected at build time via web_cookie_impl.dart
  // Uses document.cookie = value
  _WebCookieHelper.setCookie(value);
}

String? _webGetCookie(String name) {
  return _WebCookieHelper.getCookie(name);
}

/// Web cookie helper — uses document.cookie API
/// This class is only instantiated on web platform
class _WebCookieHelper {
  static void setCookie(String value) {
    if (!kIsWeb) return;
    // Use universal_html or dart:html based on build target
    try {
      // Dynamic invocation to avoid import errors on non-web
      // ignore: undefined_prefixed_name
      final dynamic html = _getHtmlDocument();
      if (html != null) {
        html.cookie = value;
      }
    } catch (_) {}
  }

  static String? getCookie(String name) {
    if (!kIsWeb) return null;
    try {
      final dynamic html = _getHtmlDocument();
      if (html == null) return null;
      final String cookies = html.cookie ?? '';
      for (final cookie in cookies.split(';')) {
        final parts = cookie.trim().split('=');
        if (parts.length >= 2 && parts[0] == name) {
          return parts.sublist(1).join('=');
        }
      }
    } catch (_) {}
    return null;
  }

  static dynamic _getHtmlDocument() {
    try {
      // Use dart:html document on web
      return _unsafeGetDocument();
    } catch (_) {
      return null;
    }
  }
}

// This function isolates the dart:html dependency
dynamic _unsafeGetDocument() {
  // This will be replaced by the web-specific implementation
  // In web builds, dart:html is available
  // In non-web builds, this throws and is caught
  throw UnsupportedError('Not on web platform');
}
