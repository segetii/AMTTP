import 'package:flutter/foundation.dart';

/// User role enumeration matching RBAC config
enum UserRole {
  guest,
  retail,
  premium,
  institutional,
  operator,
  admin,
}

extension UserRoleX on UserRole {
  String get displayName {
    switch (this) {
      case UserRole.guest:
        return 'Guest';
      case UserRole.retail:
        return 'Retail User';
      case UserRole.premium:
        return 'Premium User';
      case UserRole.institutional:
        return 'Institutional';
      case UserRole.operator:
        return 'Operator';
      case UserRole.admin:
        return 'Administrator';
    }
  }

  int get level {
    switch (this) {
      case UserRole.guest:
        return 0;
      case UserRole.retail:
        return 1;
      case UserRole.premium:
        return 2;
      case UserRole.institutional:
        return 3;
      case UserRole.operator:
        return 4;
      case UserRole.admin:
        return 5;
    }
  }

  bool get isConsumer =>
      this == UserRole.guest ||
      this == UserRole.retail ||
      this == UserRole.premium;

  bool get isInstitutional =>
      this == UserRole.institutional ||
      this == UserRole.operator ||
      this == UserRole.admin;

  static UserRole fromString(String value) {
    return UserRole.values.firstWhere(
      (role) => role.name == value.toLowerCase(),
      orElse: () => UserRole.guest,
    );
  }
}

/// User model
@immutable
class User {
  final String id;
  final String? email;
  final String? displayName;
  final String? avatarUrl;
  final UserRole role;
  final String? walletAddress;
  final double? trustScore;
  final DateTime createdAt;
  final DateTime? lastLoginAt;
  final bool isVerified;
  final Map<String, dynamic>? metadata;

  const User({
    required this.id,
    this.email,
    this.displayName,
    this.avatarUrl,
    this.role = UserRole.guest,
    this.walletAddress,
    this.trustScore,
    required this.createdAt,
    this.lastLoginAt,
    this.isVerified = false,
    this.metadata,
  });

  /// Creates a guest user
  factory User.guest() => User(
        id: 'guest',
        role: UserRole.guest,
        createdAt: DateTime.now(),
      );

  /// Creates a user from JSON
  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id: json['id'] as String,
      email: json['email'] as String?,
      displayName: json['displayName'] ?? json['display_name'] as String?,
      avatarUrl: json['avatarUrl'] ?? json['avatar_url'] as String?,
      role: UserRoleX.fromString(json['role'] as String? ?? 'guest'),
      walletAddress: json['walletAddress'] ?? json['wallet_address'] as String?,
      trustScore: (json['trustScore'] ?? json['trust_score'] as num?)?.toDouble(),
      createdAt: DateTime.parse(json['createdAt'] ?? json['created_at'] as String),
      lastLoginAt: json['lastLoginAt'] != null || json['last_login_at'] != null
          ? DateTime.parse((json['lastLoginAt'] ?? json['last_login_at']) as String)
          : null,
      isVerified: json['isVerified'] ?? json['is_verified'] ?? false,
      metadata: json['metadata'] as Map<String, dynamic>?,
    );
  }

  /// Converts to JSON
  Map<String, dynamic> toJson() {
    return {
      'id': id,
      if (email != null) 'email': email,
      if (displayName != null) 'displayName': displayName,
      if (avatarUrl != null) 'avatarUrl': avatarUrl,
      'role': role.name,
      if (walletAddress != null) 'walletAddress': walletAddress,
      if (trustScore != null) 'trustScore': trustScore,
      'createdAt': createdAt.toIso8601String(),
      if (lastLoginAt != null) 'lastLoginAt': lastLoginAt!.toIso8601String(),
      'isVerified': isVerified,
      if (metadata != null) 'metadata': metadata,
    };
  }

  /// Creates a copy with updated fields
  User copyWith({
    String? id,
    String? email,
    String? displayName,
    String? avatarUrl,
    UserRole? role,
    String? walletAddress,
    double? trustScore,
    DateTime? createdAt,
    DateTime? lastLoginAt,
    bool? isVerified,
    Map<String, dynamic>? metadata,
  }) {
    return User(
      id: id ?? this.id,
      email: email ?? this.email,
      displayName: displayName ?? this.displayName,
      avatarUrl: avatarUrl ?? this.avatarUrl,
      role: role ?? this.role,
      walletAddress: walletAddress ?? this.walletAddress,
      trustScore: trustScore ?? this.trustScore,
      createdAt: createdAt ?? this.createdAt,
      lastLoginAt: lastLoginAt ?? this.lastLoginAt,
      isVerified: isVerified ?? this.isVerified,
      metadata: metadata ?? this.metadata,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is User &&
          runtimeType == other.runtimeType &&
          id == other.id &&
          email == other.email &&
          role == other.role;

  @override
  int get hashCode => id.hashCode ^ email.hashCode ^ role.hashCode;

  @override
  String toString() =>
      'User(id: $id, email: $email, role: ${role.name}, wallet: $walletAddress)';
}
