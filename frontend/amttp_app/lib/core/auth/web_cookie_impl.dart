/// Web-specific cookie implementation for CrossAppAuthBridge
///
/// This file uses dart:html directly and is ONLY imported on web builds.
/// For non-web platforms, cross_app_auth_bridge.dart falls back gracefully.
library;

// ignore: avoid_web_libraries_in_flutter
import 'dart:html' as html;

/// Write a cookie via document.cookie
void webSetCookie(String value) {
  html.document.cookie = value;
}

/// Read a named cookie from document.cookie
String? webGetCookie(String name) {
  final cookies = html.document.cookie ?? '';
  for (final cookie in cookies.split(';')) {
    final parts = cookie.trim().split('=');
    if (parts.length >= 2 && parts[0] == name) {
      return parts.sublist(1).join('=');
    }
  }
  return null;
}

/// Write the bridge session to both cookie and localStorage
/// This ensures both Flutter (SharedPreferences) and Next.js (cookie + localStorage)
/// can see the session.
void webWriteSession(String cookieName, String token, int maxAgeSeconds) {
  // Write cookie (readable by Next.js middleware / server components)
  html.document.cookie =
      '$cookieName=$token; path=/; SameSite=Strict; max-age=$maxAgeSeconds';

  // Also write to localStorage under a shared key (readable by Next.js client components)
  html.window.localStorage['amttp_bridge_token'] = token;
}

/// Clear bridge session from both cookie and localStorage
void webClearSession(String cookieName) {
  html.document.cookie = '$cookieName=; path=/; SameSite=Strict; max-age=0';
  html.window.localStorage.remove('amttp_bridge_token');
}

/// Read the bridge token — try cookie first, fall back to localStorage
String? webReadSession(String cookieName) {
  // Try cookie
  final fromCookie = webGetCookie(cookieName);
  if (fromCookie != null && fromCookie.isNotEmpty) return fromCookie;

  // Fall back to localStorage
  final fromStorage = html.window.localStorage['amttp_bridge_token'];
  if (fromStorage != null && fromStorage.isNotEmpty) return fromStorage;

  return null;
}
