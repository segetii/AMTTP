import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../rbac/roles.dart';

/// User model for authentication - uses RBAC roles (R1-R6)
class AppUser {
  final String id;
  final String email;
  final String displayName;
  final String passwordHash;
  final Role role;  // Using RBAC Role instead of UserProfile
  final String? walletAddress;
  final DateTime createdAt;
  final bool isDemo;

  const AppUser({
    required this.id,
    required this.email,
    required this.displayName,
    required this.passwordHash,
    required this.role,
    this.walletAddress,
    required this.createdAt,
    this.isDemo = false,
  });

  Map<String, dynamic> toJson() => {
    'id': id,
    'email': email,
    'displayName': displayName,
    'passwordHash': passwordHash,
    'role': role.code,  // Store role code
    'walletAddress': walletAddress,
    'createdAt': createdAt.toIso8601String(),
    'isDemo': isDemo,
  };

  factory AppUser.fromJson(Map<String, dynamic> json) => AppUser(
    id: json['id'],
    email: json['email'],
    displayName: json['displayName'],
    passwordHash: json['passwordHash'],
    role: Role.fromCode(json['role'] ?? 'R1_END_USER'),
    walletAddress: json['walletAddress'],
    createdAt: DateTime.parse(json['createdAt']),
    isDemo: json['isDemo'] ?? false,
  );

  AppUser copyWith({
    String? displayName,
    Role? role,
    String? walletAddress,
  }) => AppUser(
    id: id,
    email: email,
    displayName: displayName ?? this.displayName,
    passwordHash: passwordHash,
    role: role ?? this.role,
    walletAddress: walletAddress ?? this.walletAddress,
    createdAt: createdAt,
    isDemo: isDemo,
  );
  
  /// Get the app mode for this user's role
  AppMode get appMode => getModeForRole(role);
  
  /// Check if user is in Focus Mode (R1/R2)
  bool get isFocusMode => appMode == AppMode.focusMode;
  
  /// Check if user is in War Room Mode (R3+)
  bool get isWarRoomMode => appMode == AppMode.warRoomMode;
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

  /// Demo users with predefined credentials for ALL roles (R1-R6)
  /// Per AMTTP Ground Truth v2.3 RBAC specification
  static final List<AppUser> demoUsers = [
    // R1: End User - Focus Mode, personal wallet
    AppUser(
      id: 'demo-r1-001',
      email: 'user@amttp.io',
      displayName: 'Alex Thompson',
      passwordHash: _hashPassword('user123'),
      role: Role.r1EndUser,
      walletAddress: '0x742d35Cc6634C0532925a3b844Bc9e7595f44e3B',
      createdAt: DateTime(2025, 1, 1),
      isDemo: true,
    ),
    // R2: End User PEP - Focus Mode, enhanced monitoring
    AppUser(
      id: 'demo-r2-001',
      email: 'pep@amttp.io',
      displayName: 'Jordan Mitchell',
      passwordHash: _hashPassword('pep123'),
      role: Role.r2EndUserPep,
      walletAddress: '0x9876543210AbCdEf0123456789AbCdEf01234567',
      createdAt: DateTime(2025, 1, 1),
      isDemo: true,
    ),
    // R3: Institution Ops - War Room (read-only)
    AppUser(
      id: 'demo-r3-001',
      email: 'ops@amttp.io',
      displayName: 'Emma Wilson',
      passwordHash: _hashPassword('ops123'),
      role: Role.r3InstitutionOps,
      walletAddress: '0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B',
      createdAt: DateTime(2025, 1, 1),
      isDemo: true,
    ),
    // R4: Institution Compliance - War Room (full access, multisig)
    AppUser(
      id: 'demo-r4-001',
      email: 'compliance@amttp.io',
      displayName: 'Michael Rodriguez',
      passwordHash: _hashPassword('comply123'),
      role: Role.r4InstitutionCompliance,
      walletAddress: '0x8ba1f109551bD432803012645Ac136ddd64DBA72',
      createdAt: DateTime(2025, 1, 1),
      isDemo: true,
    ),
    // R5: Platform Admin - system configuration
    AppUser(
      id: 'demo-r5-001',
      email: 'admin@amttp.io',
      displayName: 'Sarah Chen',
      passwordHash: _hashPassword('admin123'),
      role: Role.r5PlatformAdmin,
      walletAddress: '0xDef1C0ded9bec7F1a1670819833240f027b25EfF',
      createdAt: DateTime(2025, 1, 1),
      isDemo: true,
    ),
    // R6: Super Admin - emergency override only
    AppUser(
      id: 'demo-r6-001',
      email: 'super@amttp.io',
      displayName: 'James Park',
      passwordHash: _hashPassword('super123'),
      role: Role.r6SuperAdmin,
      walletAddress: '0x1111111111111111111111111111111111111111',
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
    
    // Always use fresh demo users (overwrite any stale stored versions)
    // This ensures password hashes and role data are always correct
    for (final demoUser in demoUsers) {
      _users.removeWhere((u) => u.email == demoUser.email);
      _users.add(demoUser);
    }
    await _saveUsers();
  }

  /// Save users to storage
  Future<void> _saveUsers() async {
    final usersJson = jsonEncode(_users.map((u) => u.toJson()).toList());
    await _prefs?.setString(_usersKey, usersJson);
  }

  /// Load current user session from persistent storage
  Future<void> _loadCurrentUser() async {
    final userId = _prefs?.getString(_currentUserKey);
    if (userId != null && _users.isNotEmpty) {
      final match = _users.where((u) => u.id == userId).toList();
      if (match.isNotEmpty) {
        _currentUser = match.first;
        return;
      }
    }
    _currentUser = null;
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
    required Role role,
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
      role: role,
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
    // Ensure service is initialized
    if (_prefs == null) {
      await init();
    }
    
    // Ensure demo users are available
    if (_users.isEmpty) {
      _users.addAll(demoUsers);
    }
    
    // Find user by email
    final userMatch = _users.where(
      (u) => u.email.toLowerCase() == email.toLowerCase(),
    ).toList();
    
    if (userMatch.isEmpty) {
      return AuthResult.failure('User not found');
    }
    
    final user = userMatch.first;

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
    Role? role,
    String? walletAddress,
  }) async {
    final userIndex = _users.indexWhere((u) => u.id == userId);
    if (userIndex == -1) {
      return AuthResult.failure('User not found');
    }

    _users[userIndex] = _users[userIndex].copyWith(
      displayName: displayName,
      role: role,
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

  /// Get demo credentials for display - ALL 6 RBAC ROLES
  static List<Map<String, String>> getDemoCredentials() {
    return [
      {
        'role': 'R1',
        'profile': 'End User',
        'email': 'user@amttp.io',
        'password': 'user123',
        'description': 'Personal wallet, Focus Mode',
        'mode': 'Focus Mode',
        'color': '0xFF10B981', // green
      },
      {
        'role': 'R2',
        'profile': 'End User (PEP)',
        'email': 'pep@amttp.io',
        'password': 'pep123',
        'description': 'Enhanced monitoring, Focus Mode',
        'mode': 'Focus Mode',
        'color': '0xFFF59E0B', // amber
      },
      {
        'role': 'R3',
        'profile': 'Institution Ops',
        'email': 'ops@amttp.io',
        'password': 'ops123',
        'description': 'Read-only analytics, War Room',
        'mode': 'War Room (View)',
        'color': '0xFF3B82F6', // blue
      },
      {
        'role': 'R4',
        'profile': 'Compliance Officer',
        'email': 'compliance@amttp.io',
        'password': 'comply123',
        'description': 'Policy & enforcement, War Room',
        'mode': 'War Room (Full)',
        'color': '0xFF8B5CF6', // purple
      },
      {
        'role': 'R5',
        'profile': 'Platform Admin',
        'email': 'admin@amttp.io',
        'password': 'admin123',
        'description': 'System config, user management',
        'mode': 'War Room (Admin)',
        'color': '0xFFF43F5E', // rose
      },
      {
        'role': 'R6',
        'profile': 'Super Admin',
        'email': 'super@amttp.io',
        'password': 'super123',
        'description': 'Emergency override only',
        'mode': 'War Room (Super)',
        'color': '0xFFDC2626', // red
      },
    ];
  }
}
