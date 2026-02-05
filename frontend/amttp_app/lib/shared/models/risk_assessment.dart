import 'package:flutter/foundation.dart';

/// Risk level enumeration
enum RiskLevel {
  low,
  medium,
  high,
  critical,
}

extension RiskLevelX on RiskLevel {
  String get displayName {
    switch (this) {
      case RiskLevel.low:
        return 'Low Risk';
      case RiskLevel.medium:
        return 'Medium Risk';
      case RiskLevel.high:
        return 'High Risk';
      case RiskLevel.critical:
        return 'Critical Risk';
    }
  }

  String get shortName {
    switch (this) {
      case RiskLevel.low:
        return 'Low';
      case RiskLevel.medium:
        return 'Medium';
      case RiskLevel.high:
        return 'High';
      case RiskLevel.critical:
        return 'Critical';
    }
  }

  /// Threshold values for each risk level (0-100 scale)
  static RiskLevel fromScore(double score) {
    if (score < 30) return RiskLevel.low;
    if (score < 60) return RiskLevel.medium;
    if (score < 85) return RiskLevel.high;
    return RiskLevel.critical;
  }

  static RiskLevel fromString(String value) {
    return RiskLevel.values.firstWhere(
      (level) => level.name.toLowerCase() == value.toLowerCase(),
      orElse: () => RiskLevel.medium,
    );
  }
}

/// Individual risk factor
@immutable
class RiskFactor {
  final String id;
  final String name;
  final String? description;
  final double score;
  final double weight;
  final String? category;
  final Map<String, dynamic>? details;

  const RiskFactor({
    required this.id,
    required this.name,
    this.description,
    required this.score,
    required this.weight,
    this.category,
    this.details,
  });

  factory RiskFactor.fromJson(Map<String, dynamic> json) {
    return RiskFactor(
      id: json['id'] as String,
      name: json['name'] as String,
      description: json['description'] as String?,
      score: (json['score'] as num).toDouble(),
      weight: (json['weight'] as num).toDouble(),
      category: json['category'] as String?,
      details: json['details'] as Map<String, dynamic>?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      if (description != null) 'description': description,
      'score': score,
      'weight': weight,
      if (category != null) 'category': category,
      if (details != null) 'details': details,
    };
  }

  RiskLevel get riskLevel => RiskLevelX.fromScore(score);

  /// Weighted contribution to overall score
  double get contribution => score * weight;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RiskFactor &&
          runtimeType == other.runtimeType &&
          id == other.id;

  @override
  int get hashCode => id.hashCode;
}

/// Risk assessment result
@immutable
class RiskAssessment {
  final String id;
  final String? transactionId;
  final String? address;
  final double overallScore;
  final RiskLevel riskLevel;
  final List<RiskFactor> factors;
  final bool isBlocked;
  final String? blockReason;
  final DateTime assessedAt;
  final Duration? assessmentDuration;
  final String? modelVersion;
  final Map<String, dynamic>? explanations;
  final List<String>? recommendations;
  final Map<String, dynamic>? metadata;

  const RiskAssessment({
    required this.id,
    this.transactionId,
    this.address,
    required this.overallScore,
    required this.riskLevel,
    this.factors = const [],
    this.isBlocked = false,
    this.blockReason,
    required this.assessedAt,
    this.assessmentDuration,
    this.modelVersion,
    this.explanations,
    this.recommendations,
    this.metadata,
  });

  factory RiskAssessment.fromJson(Map<String, dynamic> json) {
    final score = (json['overallScore'] ?? json['overall_score'] ?? json['score'] as num).toDouble();
    
    return RiskAssessment(
      id: json['id'] as String,
      transactionId: json['transactionId'] ?? json['transaction_id'] as String?,
      address: json['address'] as String?,
      overallScore: score,
      riskLevel: json['riskLevel'] != null
          ? RiskLevelX.fromString(json['riskLevel'] as String)
          : RiskLevelX.fromScore(score),
      factors: (json['factors'] as List<dynamic>?)
              ?.map((e) => RiskFactor.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
      isBlocked: json['isBlocked'] ?? json['is_blocked'] ?? false,
      blockReason: json['blockReason'] ?? json['block_reason'] as String?,
      assessedAt: DateTime.parse(json['assessedAt'] ?? json['assessed_at'] as String),
      assessmentDuration: json['assessmentDuration'] != null
          ? Duration(milliseconds: json['assessmentDuration'] as int)
          : null,
      modelVersion: json['modelVersion'] ?? json['model_version'] as String?,
      explanations: json['explanations'] as Map<String, dynamic>?,
      recommendations: (json['recommendations'] as List<dynamic>?)?.cast<String>(),
      metadata: json['metadata'] as Map<String, dynamic>?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      if (transactionId != null) 'transactionId': transactionId,
      if (address != null) 'address': address,
      'overallScore': overallScore,
      'riskLevel': riskLevel.name,
      'factors': factors.map((f) => f.toJson()).toList(),
      'isBlocked': isBlocked,
      if (blockReason != null) 'blockReason': blockReason,
      'assessedAt': assessedAt.toIso8601String(),
      if (assessmentDuration != null) 'assessmentDuration': assessmentDuration!.inMilliseconds,
      if (modelVersion != null) 'modelVersion': modelVersion,
      if (explanations != null) 'explanations': explanations,
      if (recommendations != null) 'recommendations': recommendations,
      if (metadata != null) 'metadata': metadata,
    };
  }

  /// Top risk factors by contribution
  List<RiskFactor> get topFactors {
    final sorted = List<RiskFactor>.from(factors)
      ..sort((a, b) => b.contribution.compareTo(a.contribution));
    return sorted.take(5).toList();
  }

  /// Factors grouped by category
  Map<String, List<RiskFactor>> get factorsByCategory {
    final grouped = <String, List<RiskFactor>>{};
    for (final factor in factors) {
      final category = factor.category ?? 'Other';
      grouped.putIfAbsent(category, () => []).add(factor);
    }
    return grouped;
  }

  /// Whether the transaction should proceed
  bool get canProceed => !isBlocked;

  /// Whether the transaction needs additional review
  bool get needsReview =>
      riskLevel == RiskLevel.high || riskLevel == RiskLevel.critical;

  /// Creates a copy with updated fields
  RiskAssessment copyWith({
    String? id,
    String? transactionId,
    String? address,
    double? overallScore,
    RiskLevel? riskLevel,
    List<RiskFactor>? factors,
    bool? isBlocked,
    String? blockReason,
    DateTime? assessedAt,
    Duration? assessmentDuration,
    String? modelVersion,
    Map<String, dynamic>? explanations,
    List<String>? recommendations,
    Map<String, dynamic>? metadata,
  }) {
    return RiskAssessment(
      id: id ?? this.id,
      transactionId: transactionId ?? this.transactionId,
      address: address ?? this.address,
      overallScore: overallScore ?? this.overallScore,
      riskLevel: riskLevel ?? this.riskLevel,
      factors: factors ?? this.factors,
      isBlocked: isBlocked ?? this.isBlocked,
      blockReason: blockReason ?? this.blockReason,
      assessedAt: assessedAt ?? this.assessedAt,
      assessmentDuration: assessmentDuration ?? this.assessmentDuration,
      modelVersion: modelVersion ?? this.modelVersion,
      explanations: explanations ?? this.explanations,
      recommendations: recommendations ?? this.recommendations,
      metadata: metadata ?? this.metadata,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RiskAssessment &&
          runtimeType == other.runtimeType &&
          id == other.id;

  @override
  int get hashCode => id.hashCode;

  @override
  String toString() =>
      'RiskAssessment(id: $id, score: ${overallScore.toStringAsFixed(1)}, level: ${riskLevel.name}, blocked: $isBlocked)';
}

/// Risk assessment request
@immutable
class RiskAssessmentRequest {
  final String? transactionId;
  final String? fromAddress;
  final String? toAddress;
  final String? amount;
  final String? tokenSymbol;
  final Map<String, dynamic>? context;

  const RiskAssessmentRequest({
    this.transactionId,
    this.fromAddress,
    this.toAddress,
    this.amount,
    this.tokenSymbol,
    this.context,
  });

  Map<String, dynamic> toJson() {
    return {
      if (transactionId != null) 'transactionId': transactionId,
      if (fromAddress != null) 'fromAddress': fromAddress,
      if (toAddress != null) 'toAddress': toAddress,
      if (amount != null) 'amount': amount,
      if (tokenSymbol != null) 'tokenSymbol': tokenSymbol,
      if (context != null) 'context': context,
    };
  }
}
