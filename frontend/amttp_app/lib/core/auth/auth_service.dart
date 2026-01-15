import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'user_profile_provider.dart';

/// User model for authentication
class AppUser {
  final String id;
  final String email;
  final String displayName;
  final String passwordHash;
  final UserProfile profile;
  final String? walletAddress;
  final DateTime createdAt;
  final bool isDemo;

  const AppUser({
    required this.id,
    required this.email,
    required this.displayName,
    required this.passwordHash,
    required this.profile,
    this.walletAddress,
    required this.createdAt,
    this.isDemo = false,
  });

  Map<String, dynamic> toJson() => {
    'id': id,
    'email': email,
    'displayName': displayName,
    'passwordHash': passwordHash,
    'profile': profile.index,
    'walletAddress': walletAddress,
    'createdAt': createdAt.toIso8601String(),
    'isDemo': isDemo,
  };

  factory AppUser.fromJson(Map<String, dynamic> json) => AppUser(
    id: json['id'],
    email: json['email'],
    displayName: json['displayName'],
    passwordHash: json['passwordHash'],
    profile: UserProfile.values[json['profile']],
    walletAddress: json['walletAddress'],
    createdAt: DateTime.parse(json['createdAt']),
    isDemo: json['isDemo'] ?? false,
  );

  AppUser copyWith({
    String? displayName,
    UserProfile? profile,
    String? walletAddress,
  }) => AppUser(
    id: id,
    email: email,
    displayName: displayName ?? this.displayName,
    passwordHash: passwordHash,
    profile: profile ?? this.profile,
    walletAddress: walletAddress ?? this.walletAddress,
    createdAt: createdAt,
    isDemo: isDemo,
  );
}

/// Authentication result
class AuthResult {
  final bool success;
  final String? message;
  final AppUser? user;

  const AuthResult({
    required this.success,
    this.message,
    this.user,
  });

  factory AuthResult.success(AppUser user) => AuthResult(
    success: true,
    user: user,
  );

  factory AuthResult.failure(String message) => AuthResult(
    success: false,
    message: message,
  );
}

/// Authentication Service - handles user registration, login, and session management
class AuthService {
  static const String _usersKey = 'amttp_users';
  static const String _currentUserKey = 'amttp_current_user';
  static const String _sessionKey = 'amttp_session';

  SharedPreferences? _prefs;
  List<AppUser> _users = [];
  AppUser? _currentUser;

  /// Demo users with predefined credentials
  static final List<AppUser> demoUsers = [
    AppUser(
      id: 'demo-user-001',
      email: 'user@amttp.io',
      displayName: 'Alex Thompson',
      passwordHash: _hashPassword('user123'),
      profile: UserProfile.endUser,
      walletAddress: '0x742d35Cc6634C0532925a3b844Bc9e7595f44e3B',
      createdAt: DateTime(2025, 1, 1),
      isDemo: true,
    ),
    AppUser(
      id: 'demo-admin-001',
      email: 'admin@amttp.io',
      displayName: 'Sarah Chen',
      passwordHash: _hashPassword('admin123'),
      profile: UserProfile.admin,
      walletAddress: '0x8ba1f109551bD432803012645Ac136ddd64DBA72',
      createdAt: DateTime(2025, 1, 1),
      isDemo: true,
    ),
    AppUser(
      id: 'demo-compliance-001',
      email: 'compliance@amttp.io',
      displayName: 'Michael Rodriguez',
      passwordHash: _hashPassword('comply123'),
      profile: UserProfile.complianceOfficer,
      walletAddress: '0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B',
      createdAt: DateTime(2025, 1, 1),
      isDemo: true,
    ),
  ];

  /// Initialize the auth service
  Future<void> init() async {
    _prefs = await SharedPreferences.getInstance();
    await _loadUsers();
    await _loadCurrentUser();
  }

  /// Load users from storage
  Future<void> _loadUsers() async {
    final usersJson = _prefs?.getString(_usersKey);
    if (usersJson != null) {
      final List<dynamic> usersList = jsonDecode(usersJson);
      _users = usersList.map((u) => AppUser.fromJson(u)).toList();
    }
    
    // Ensure demo users exist
    for (final demoUser in demoUsers) {
      if (!_users.any((u) => u.email == demoUser.email)) {
        _users.add(demoUser);
      }
    }
    await _saveUsers();
  }

  /// Save users to storage
  Future<void> _saveUsers() async {
    final usersJson = jsonEncode(_users.map((u) => u.toJson()).toList());
    await _prefs?.setString(_usersKey, usersJson);
  }

  /// Load current user session
  Future<void> _loadCurrentUser() async {
    final userId = _prefs?.getString(_currentUserKey);
    if (userId != null) {
      _currentUser = _users.firstWhere(
        (u) => u.id == userId,
        orElse: () => demoUsers.first,
      );
    }
  }

  /// Get current logged-in user
  AppUser? get currentUser => _currentUser;

  /// Check if user is logged in
  bool get isLoggedIn => _currentUser != null;

  /// Hash password using SHA-256
  static String _hashPassword(String password) {
    final bytes = utf8.encode(password + 'amttp_salt_2026');
    final digest = sha256.convert(bytes);
    return digest.toString();
  }

  /// Register a new user
  Future<AuthResult> register({
    required String email,
    required String password,
    required String displayName,
    required UserProfile profile,
    String? walletAddress,
  }) async {
    // Validate email
    if (!_isValidEmail(email)) {
      return AuthResult.failure('Invalid email address');
    }

    // Check if email already exists
    if (_users.any((u) => u.email.toLowerCase() == email.toLowerCase())) {
      return AuthResult.failure('Email already registered');
    }

    // Validate password
    if (password.length < 6) {
      return AuthResult.failure('Password must be at least 6 characters');
    }

    // Create new user
    final user = AppUser(
      id: 'user-${DateTime.now().millisecondsSinceEpoch}',
      email: email.toLowerCase(),
      displayName: displayName,
      passwordHash: _hashPassword(password),
      profile: profile,
      walletAddress: walletAddress,
      createdAt: DateTime.now(),
    );

    _users.add(user);
    await _saveUsers();

    // Auto-login after registration
    _currentUser = user;
    await _prefs?.setString(_currentUserKey, user.id);

    return AuthResult.success(user);
  }

  /// Login with email and password
  Future<AuthResult> login({
    required String email,
    required String password,
  }) async {
    final user = _users.firstWhere(
      (u) => u.email.toLowerCase() == email.toLowerCase(),
      orElse: () => throw Exception('User not found'),
    );

    // Verify password
    final passwordHash = _hashPassword(password);
    if (user.passwordHash != passwordHash) {
      return AuthResult.failure('Invalid password');
    }

    // Set current user
    _currentUser = user;
    await _prefs?.setString(_currentUserKey, user.id);
    await _prefs?.setString(_sessionKey, DateTime.now().toIso8601String());

    return AuthResult.success(user);
  }

  /// Login with email and password (handles exceptions)
  Future<AuthResult> signIn({
    required String email,
    required String password,
  }) async {
    try {
      return await login(email: email, password: password);
    } catch (e) {
      return AuthResult.failure('Invalid email or password');
    }
  }

  /// Logout current user
  Future<void> logout() async {
    _currentUser = null;
    await _prefs?.remove(_currentUserKey);
    await _prefs?.remove(_sessionKey);
  }

  /// Update user profile
  Future<AuthResult> updateProfile({
    required String userId,
    String? displayName,
    UserProfile? profile,
    String? walletAddress,
  }) async {
    final userIndex = _users.indexWhere((u) => u.id == userId);
    if (userIndex == -1) {
      return AuthResult.failure('User not found');
    }

    _users[userIndex] = _users[userIndex].copyWith(
      displayName: displayName,
      profile: profile,
      walletAddress: walletAddress,
    );

    await _saveUsers();

    if (_currentUser?.id == userId) {
      _currentUser = _users[userIndex];
    }

    return AuthResult.success(_users[userIndex]);
  }

  /// Get all users (for admin)
  List<AppUser> getAllUsers() => List.unmodifiable(_users);

  /// Delete user account
  Future<bool> deleteUser(String userId) async {
    final user = _users.firstWhere((u) => u.id == userId, orElse: () => throw Exception());
    if (user.isDemo) return false; // Cannot delete demo users
    
    _users.removeWhere((u) => u.id == userId);
    await _saveUsers();
    
    if (_currentUser?.id == userId) {
      await logout();
    }
    
    return true;
  }

  /// Validate email format
  bool _isValidEmail(String email) {
    return RegExp(r'^[\w-\.]+@([\w-]+\.)+[\w-]{2,4}$').hasMatch(email);
  }

  /// Get demo credentials for display
  static List<Map<String, String>> getDemoCredentials() {
    return [
      {
        'profile': 'End User',
        'email': 'user@amttp.io',
        'password': 'user123',
        'description': 'Standard user for transfers & swaps',
      },
      {
        'profile': 'Administrator',
        'email': 'admin@amttp.io',
        'password': 'admin123',
        'description': 'Full system access & analytics',
      },
      {
        'profile': 'Compliance',
        'email': 'compliance@amttp.io',
        'password': 'comply123',
        'description': 'KYC/AML & regulatory tools',
      },
    ];
  }
}
