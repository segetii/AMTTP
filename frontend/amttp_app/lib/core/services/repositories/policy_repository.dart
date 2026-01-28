import 'package:dio/dio.dart';
import 'http_client.dart';
import 'api_config.dart' show ApiConfig;

/// Policy management repository
/// 
/// Handles CRUD operations for AMTTP policies including:
/// - Creating new policies
/// - Updating existing policies
/// - Retrieving policies by ID or for an address
/// - Activating/deactivating policies
class PolicyRepository {
  final Dio _client = HttpClient.instance;

  /// Creates a new policy
  /// 
  /// Returns the created policy with its assigned ID
  /// Throws [PolicyException] on failure
  Future<Policy> createPolicy(CreatePolicyRequest request) async {
    try {
      final response = await _client.post(
        ApiConfig.policyEndpoint,
        data: request.toJson(),
      );

      if (response.statusCode == 201 && response.data != null) {
        return Policy.fromJson(response.data);
      }

      throw PolicyException('Failed to create policy: ${response.statusCode}');
    } on DioException catch (e) {
      throw PolicyException('Network error: ${e.message}');
    }
  }

  /// Retrieves a policy by ID
  Future<Policy> getPolicy(String policyId) async {
    try {
      final response = await _client.get('${ApiConfig.policyEndpoint}/$policyId');

      if (response.statusCode == 200 && response.data != null) {
        return Policy.fromJson(response.data);
      }

      throw PolicyException('Policy not found: $policyId');
    } on DioException catch (e) {
      if (e.response?.statusCode == 404) {
        throw PolicyException('Policy not found: $policyId');
      }
      throw PolicyException('Network error: ${e.message}');
    }
  }

  /// Retrieves all policies for an address
  Future<List<Policy>> getPoliciesForAddress(String address) async {
    try {
      final response = await _client.get(
        ApiConfig.policyEndpoint,
        queryParameters: {'address': address},
      );

      if (response.statusCode == 200 && response.data != null) {
        final List<dynamic> data = response.data['policies'] ?? response.data;
        return data.map((p) => Policy.fromJson(p)).toList();
      }

      throw PolicyException('Failed to fetch policies');
    } on DioException catch (e) {
      throw PolicyException('Network error: ${e.message}');
    }
  }

  /// Updates an existing policy
  Future<Policy> updatePolicy(String policyId, UpdatePolicyRequest request) async {
    try {
      final response = await _client.put(
        '${ApiConfig.policyEndpoint}/$policyId',
        data: request.toJson(),
      );

      if (response.statusCode == 200 && response.data != null) {
        return Policy.fromJson(response.data);
      }

      throw PolicyException('Failed to update policy: ${response.statusCode}');
    } on DioException catch (e) {
      throw PolicyException('Network error: ${e.message}');
    }
  }

  /// Activates a policy
  Future<Policy> activatePolicy(String policyId) async {
    try {
      final response = await _client.post(
        '${ApiConfig.policyEndpoint}/$policyId/activate',
      );

      if (response.statusCode == 200 && response.data != null) {
        return Policy.fromJson(response.data);
      }

      throw PolicyException('Failed to activate policy: ${response.statusCode}');
    } on DioException catch (e) {
      throw PolicyException('Network error: ${e.message}');
    }
  }

  /// Deactivates a policy
  Future<Policy> deactivatePolicy(String policyId) async {
    try {
      final response = await _client.post(
        '${ApiConfig.policyEndpoint}/$policyId/deactivate',
      );

      if (response.statusCode == 200 && response.data != null) {
        return Policy.fromJson(response.data);
      }

      throw PolicyException('Failed to deactivate policy: ${response.statusCode}');
    } on DioException catch (e) {
      throw PolicyException('Network error: ${e.message}');
    }
  }

  /// Deletes a policy
  Future<void> deletePolicy(String policyId) async {
    try {
      final response = await _client.delete('${ApiConfig.policyEndpoint}/$policyId');

      if (response.statusCode != 200 && response.statusCode != 204) {
        throw PolicyException('Failed to delete policy: ${response.statusCode}');
      }
    } on DioException catch (e) {
      throw PolicyException('Network error: ${e.message}');
    }
  }

  /// Evaluates a transaction against a specific policy
  Future<PolicyEvaluationResult> evaluateTransaction(
    String policyId,
    PolicyEvaluationRequest request,
  ) async {
    try {
      final response = await _client.post(
        '${ApiConfig.policyEndpoint}/$policyId/evaluate',
        data: request.toJson(),
      );

      if (response.statusCode == 200 && response.data != null) {
        return PolicyEvaluationResult.fromJson(response.data);
      }

      // On failure, DENY by default - never silently approve
      return PolicyEvaluationResult(
        allowed: false,
        reason: 'Policy evaluation failed: ${response.statusCode}',
        policyId: policyId,
      );
    } on DioException catch (e) {
      // On network error, DENY by default
      return PolicyEvaluationResult(
        allowed: false,
        reason: 'Network error during policy evaluation: ${e.message}',
        policyId: policyId,
      );
    }
  }
}

/// Policy entity
class Policy {
  final String id;
  final String name;
  final String description;
  final String ownerAddress;
  final PolicyType type;
  final PolicyStatus status;
  final List<PolicyRule> rules;
  final DateTime createdAt;
  final DateTime updatedAt;

  Policy({
    required this.id,
    required this.name,
    required this.description,
    required this.ownerAddress,
    required this.type,
    required this.status,
    required this.rules,
    required this.createdAt,
    required this.updatedAt,
  });

  factory Policy.fromJson(Map<String, dynamic> json) {
    final List<dynamic> rulesList = json['rules'] ?? [];
    return Policy(
      id: json['id'] ?? '',
      name: json['name'] ?? '',
      description: json['description'] ?? '',
      ownerAddress: json['ownerAddress'] ?? json['owner'] ?? '',
      type: PolicyType.fromString(json['type']),
      status: PolicyStatus.fromString(json['status']),
      rules: rulesList.map((r) => PolicyRule.fromJson(r)).toList(),
      createdAt: DateTime.tryParse(json['createdAt'] ?? '') ?? DateTime.now(),
      updatedAt: DateTime.tryParse(json['updatedAt'] ?? '') ?? DateTime.now(),
    );
  }

  bool get isActive => status == PolicyStatus.active;
}

/// Policy types
enum PolicyType {
  spending,
  allowlist,
  blocklist,
  timelock,
  multisig,
  custom;

  static PolicyType fromString(String? value) {
    return PolicyType.values.firstWhere(
      (e) => e.name.toLowerCase() == value?.toLowerCase(),
      orElse: () => PolicyType.custom,
    );
  }
}

/// Policy status
enum PolicyStatus {
  active,
  inactive,
  pending,
  expired;

  static PolicyStatus fromString(String? value) {
    return PolicyStatus.values.firstWhere(
      (e) => e.name.toLowerCase() == value?.toLowerCase(),
      orElse: () => PolicyStatus.inactive,
    );
  }
}

/// Policy rule
class PolicyRule {
  final String id;
  final String type;
  final Map<String, dynamic> parameters;

  PolicyRule({
    required this.id,
    required this.type,
    required this.parameters,
  });

  factory PolicyRule.fromJson(Map<String, dynamic> json) {
    return PolicyRule(
      id: json['id'] ?? '',
      type: json['type'] ?? '',
      parameters: Map<String, dynamic>.from(json['parameters'] ?? {}),
    );
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'type': type,
    'parameters': parameters,
  };
}

/// Request to create a new policy
class CreatePolicyRequest {
  final String name;
  final String description;
  final String ownerAddress;
  final String type;
  final List<Map<String, dynamic>> rules;

  CreatePolicyRequest({
    required this.name,
    required this.description,
    required this.ownerAddress,
    required this.type,
    required this.rules,
  });

  Map<String, dynamic> toJson() => {
    'name': name,
    'description': description,
    'ownerAddress': ownerAddress,
    'type': type,
    'rules': rules,
  };
}

/// Request to update a policy
class UpdatePolicyRequest {
  final String? name;
  final String? description;
  final List<Map<String, dynamic>>? rules;

  UpdatePolicyRequest({
    this.name,
    this.description,
    this.rules,
  });

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    if (name != null) json['name'] = name;
    if (description != null) json['description'] = description;
    if (rules != null) json['rules'] = rules;
    return json;
  }
}

/// Request for policy evaluation
class PolicyEvaluationRequest {
  final String from;
  final String to;
  final String value;
  final String? data;

  PolicyEvaluationRequest({
    required this.from,
    required this.to,
    required this.value,
    this.data,
  });

  Map<String, dynamic> toJson() => {
    'from': from,
    'to': to,
    'value': value,
    if (data != null) 'data': data,
  };
}

/// Result of policy evaluation
class PolicyEvaluationResult {
  final bool allowed;
  final String reason;
  final String policyId;
  final List<String>? violations;

  PolicyEvaluationResult({
    required this.allowed,
    required this.reason,
    required this.policyId,
    this.violations,
  });

  factory PolicyEvaluationResult.fromJson(Map<String, dynamic> json) {
    final List<dynamic>? violationList = json['violations'];
    return PolicyEvaluationResult(
      allowed: json['allowed'] ?? false,
      reason: json['reason'] ?? '',
      policyId: json['policyId'] ?? '',
      violations: violationList?.map((v) => v.toString()).toList(),
    );
  }
}

/// Exception for policy operations
class PolicyException implements Exception {
  final String message;
  PolicyException(this.message);

  @override
  String toString() => 'PolicyException: $message';
}
