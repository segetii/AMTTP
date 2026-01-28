/// Disputes repository
/// 
/// Handles dispute creation, evidence submission, and resolution.
library;

import 'package:dio/dio.dart';
import 'http_client.dart';
import '../api_config.dart';

/// Dispute status enum
enum DisputeStatus {
  pending,
  evidenceSubmission,
  arbitration,
  resolved,
  appealed,
  closed,
}

/// Dispute ruling
enum DisputeRuling {
  pending,
  inFavorOfInitiator,
  inFavorOfCounterparty,
  split,
  dismissed,
}

/// Evidence item
class Evidence {
  final String id;
  final String disputeId;
  final String submittedBy;
  final String type;
  final String uri;
  final DateTime submittedAt;
  final Map<String, dynamic>? metadata;

  Evidence({
    required this.id,
    required this.disputeId,
    required this.submittedBy,
    required this.type,
    required this.uri,
    required this.submittedAt,
    this.metadata,
  });

  factory Evidence.fromJson(Map<String, dynamic> json) {
    return Evidence(
      id: json['id'] as String,
      disputeId: json['dispute_id'] as String,
      submittedBy: json['submitted_by'] as String,
      type: json['type'] as String,
      uri: json['uri'] as String,
      submittedAt: DateTime.parse(json['submitted_at'] as String),
      metadata: json['metadata'] as Map<String, dynamic>?,
    );
  }
}

/// Dispute model
class Dispute {
  final String id;
  final String transactionHash;
  final String initiator;
  final String counterparty;
  final DisputeStatus status;
  final DisputeRuling ruling;
  final String amountWei;
  final DateTime createdAt;
  final DateTime? resolvedAt;
  final List<Evidence> evidence;
  final String? arbitratorAddress;
  final int? appealDeadline;

  Dispute({
    required this.id,
    required this.transactionHash,
    required this.initiator,
    required this.counterparty,
    required this.status,
    required this.ruling,
    required this.amountWei,
    required this.createdAt,
    this.resolvedAt,
    this.evidence = const [],
    this.arbitratorAddress,
    this.appealDeadline,
  });

  factory Dispute.fromJson(Map<String, dynamic> json) {
    return Dispute(
      id: json['id'] as String,
      transactionHash: json['transaction_hash'] as String,
      initiator: json['initiator'] as String,
      counterparty: json['counterparty'] as String,
      status: _parseStatus(json['status'] as String?),
      ruling: _parseRuling(json['ruling'] as String?),
      amountWei: json['amount_wei'] as String,
      createdAt: DateTime.parse(json['created_at'] as String),
      resolvedAt: json['resolved_at'] != null
          ? DateTime.tryParse(json['resolved_at'])
          : null,
      evidence: (json['evidence'] as List<dynamic>?)
              ?.map((e) => Evidence.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
      arbitratorAddress: json['arbitrator_address'] as String?,
      appealDeadline: json['appeal_deadline'] as int?,
    );
  }

  static DisputeStatus _parseStatus(String? status) {
    switch (status?.toLowerCase()) {
      case 'pending':
        return DisputeStatus.pending;
      case 'evidence_submission':
        return DisputeStatus.evidenceSubmission;
      case 'arbitration':
        return DisputeStatus.arbitration;
      case 'resolved':
        return DisputeStatus.resolved;
      case 'appealed':
        return DisputeStatus.appealed;
      case 'closed':
        return DisputeStatus.closed;
      default:
        return DisputeStatus.pending;
    }
  }

  static DisputeRuling _parseRuling(String? ruling) {
    switch (ruling?.toLowerCase()) {
      case 'in_favor_of_initiator':
        return DisputeRuling.inFavorOfInitiator;
      case 'in_favor_of_counterparty':
        return DisputeRuling.inFavorOfCounterparty;
      case 'split':
        return DisputeRuling.split;
      case 'dismissed':
        return DisputeRuling.dismissed;
      default:
        return DisputeRuling.pending;
    }
  }

  bool get canSubmitEvidence => status == DisputeStatus.evidenceSubmission;
  bool get canAppeal =>
      status == DisputeStatus.resolved &&
      appealDeadline != null &&
      DateTime.now().millisecondsSinceEpoch < appealDeadline!;
}

/// Repository for dispute operations
class DisputeRepository {
  final HttpClient _client;

  DisputeRepository({HttpClient? client}) : _client = client ?? HttpClient();

  /// Get all disputes for an address
  Future<List<Dispute>> getDisputes({
    String? address,
    DisputeStatus? status,
    int? limit,
    int? offset,
  }) async {
    final queryParams = <String, dynamic>{};
    if (address != null) queryParams['address'] = address;
    if (status != null) queryParams['status'] = status.name;
    if (limit != null) queryParams['limit'] = limit;
    if (offset != null) queryParams['offset'] = offset;

    final response = await _client.get<List<dynamic>>(
      ApiConfig.disputes,
      queryParameters: queryParams,
    );

    return response
        .map((e) => Dispute.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Get a single dispute by ID
  Future<Dispute> getDispute(String disputeId) async {
    final response = await _client.get<Map<String, dynamic>>(
      '${ApiConfig.disputes}/$disputeId',
    );
    
    return Dispute.fromJson(response);
  }

  /// Create a new dispute
  Future<Dispute> createDispute({
    required String transactionHash,
    required String reason,
    required String amountWei,
    Map<String, dynamic>? metadata,
  }) async {
    final response = await _client.post<Map<String, dynamic>>(
      ApiConfig.disputes,
      data: {
        'transaction_hash': transactionHash,
        'reason': reason,
        'amount_wei': amountWei,
        'metadata': metadata ?? {},
      },
    );
    
    return Dispute.fromJson(response);
  }

  /// Submit evidence for a dispute
  Future<Evidence> submitEvidence({
    required String disputeId,
    required String type,
    required String filePath,
    String? description,
    void Function(int, int)? onProgress,
  }) async {
    final formData = FormData.fromMap({
      'dispute_id': disputeId,
      'type': type,
      'file': await MultipartFile.fromFile(filePath),
      if (description != null) 'description': description,
    });

    final response = await _client.uploadFile<Map<String, dynamic>>(
      ApiConfig.disputeEvidence,
      formData: formData,
      onSendProgress: onProgress,
    );
    
    return Evidence.fromJson(response);
  }

  /// Submit text/link evidence
  Future<Evidence> submitTextEvidence({
    required String disputeId,
    required String type,
    required String content,
    String? description,
  }) async {
    final response = await _client.post<Map<String, dynamic>>(
      ApiConfig.disputeEvidence,
      data: {
        'dispute_id': disputeId,
        'type': type,
        'content': content,
        if (description != null) 'description': description,
      },
    );
    
    return Evidence.fromJson(response);
  }

  /// Appeal a dispute ruling
  Future<Dispute> appealDispute({
    required String disputeId,
    required String reason,
  }) async {
    final response = await _client.post<Map<String, dynamic>>(
      '${ApiConfig.disputes}/$disputeId/appeal',
      data: {'reason': reason},
    );
    
    return Dispute.fromJson(response);
  }

  /// Withdraw from a dispute
  Future<void> withdrawDispute(String disputeId) async {
    await _client.post<void>(
      '${ApiConfig.disputes}/$disputeId/withdraw',
    );
  }
}
