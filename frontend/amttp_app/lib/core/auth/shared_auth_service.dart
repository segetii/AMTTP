/// Shared Auth Service
/// 
/// Provides unified authentication across Flutter and Next.js apps
/// Uses shared JWT token stored in localStorage/secure storage
library;

import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Auth token key - same key used by Next.js app
const String kAuthTokenKey = 'amttp_auth_token';
const String kSessionKey = 'amttp_session';

/// User session data shared between apps
class SharedSession {
  final String address;
  final String role;
  final String mode;
  final DateTime expiresAt;
  final String? displayName;

  SharedSession({
    required this.address,
    required this.role,
    required this.mode,
    required this.expiresAt,
    this.displayName,
  });

  factory SharedSession.fromJson(Map<String, dynamic> json) {
    return SharedSession(
      address: json['address'] as String,
      role: json['role'] as String,
      mode: json['mode'] as String,
      expiresAt: DateTime.parse(json['expiresAt'] as String),
      displayName: json['displayName'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
    'address': address,
    'role': role,
    'mode': mode,
    'expiresAt': expiresAt.toIso8601String(),
    'displayName': displayName,
  };

  bool get isExpired => DateTime.now().isAfter(expiresAt);
  
  bool get isEndUser => ['R1', 'R2'].contains(role);
  bool get isInstitutional => ['R3', 'R4', 'R5', 'R6'].contains(role);
}

/// Shared auth service singleton
class SharedAuthService extends ChangeNotifier {
  static final SharedAuthService _instance = SharedAuthService._internal();
  factory SharedAuthService() => _instance;
  SharedAuthService._internal();

  SharedSession? _session;
  bool _isLoading = true;

  SharedSession? get session => _session;
  bool get isAuthenticated => _session != null && !_session!.isExpired;
  bool get isLoading => _isLoading;

  /// Initialize - load session from storage
  Future<void> init() async {
    _isLoading = true;
    notifyListeners();

    try {
      final prefs = await SharedPreferences.getInstance();
      final sessionJson = prefs.getString(kSessionKey);
      
      if (sessionJson != null) {
        final data = jsonDecode(sessionJson) as Map<String, dynamic>;
        _session = SharedSession.fromJson(data);
        
        // Check expiration
        if (_session!.isExpired) {
          await logout();
        }
      }
    } catch (e) {
      debugPrint('SharedAuthService: Failed to load session: $e');
      _session = null;
    }

    _isLoading = false;
    notifyListeners();
  }

  /// Login with wallet address (demo mode)
  Future<void> loginDemo({
    required String address,
    required String role,
    String? displayName,
  }) async {
    final mode = ['R1', 'R2'].contains(role) ? 'focus' : 'war-room';
    
    _session = SharedSession(
      address: address,
      role: role,
      mode: mode,
      expiresAt: DateTime.now().add(const Duration(hours: 24)),
      displayName: displayName,
    );

    await _saveSession();
    notifyListeners();
  }

  /// Logout - clear session
  Future<void> logout() async {
    _session = null;
    
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(kSessionKey);
      await prefs.remove(kAuthTokenKey);
    } catch (e) {
      debugPrint('SharedAuthService: Failed to clear session: $e');
    }

    notifyListeners();
  }

  /// Save session to storage
  Future<void> _saveSession() async {
    if (_session == null) return;

    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(kSessionKey, jsonEncode(_session!.toJson()));
    } catch (e) {
      debugPrint('SharedAuthService: Failed to save session: $e');
    }
  }

  /// Get War Room URL based on environment
  String getWarRoomUrl() {
    if (kIsWeb) {
      // In production, War Room is at /war-room
      // In dev, it's at localhost:3006
      final uri = Uri.base;
      if (uri.host == 'localhost' || uri.host == '127.0.0.1') {
        return 'http://localhost:3006';
      }
      return '${uri.scheme}://${uri.host}/war-room';
    }
    // Mobile - always use production URL or configured URL
    return 'https://app.amttp.io/war-room';
  }

  /// Get Wallet App URL based on environment
  String getWalletAppUrl() {
    if (kIsWeb) {
      final uri = Uri.base;
      if (uri.host == 'localhost' || uri.host == '127.0.0.1') {
        return 'http://localhost:3010';
      }
      return '${uri.scheme}://${uri.host}';
    }
    return 'https://app.amttp.io';
  }
}
