import 'package:flutter/foundation.dart';

/// Transaction status enumeration
enum TransactionStatus {
  pending,
  processing,
  confirmed,
  failed,
  cancelled,
}

extension TransactionStatusX on TransactionStatus {
  String get displayName {
    switch (this) {
      case TransactionStatus.pending:
        return 'Pending';
      case TransactionStatus.processing:
        return 'Processing';
      case TransactionStatus.confirmed:
        return 'Confirmed';
      case TransactionStatus.failed:
        return 'Failed';
      case TransactionStatus.cancelled:
        return 'Cancelled';
    }
  }

  bool get isFinalized =>
      this == TransactionStatus.confirmed ||
      this == TransactionStatus.failed ||
      this == TransactionStatus.cancelled;

  bool get isSuccess => this == TransactionStatus.confirmed;

  static TransactionStatus fromString(String value) {
    return TransactionStatus.values.firstWhere(
      (status) => status.name.toLowerCase() == value.toLowerCase(),
      orElse: () => TransactionStatus.pending,
    );
  }
}

/// Transaction type enumeration
enum TransactionType {
  send,
  receive,
  swap,
  approve,
  stake,
  unstake,
  mint,
  burn,
  contractInteraction,
  unknown,
}

extension TransactionTypeX on TransactionType {
  String get displayName {
    switch (this) {
      case TransactionType.send:
        return 'Send';
      case TransactionType.receive:
        return 'Receive';
      case TransactionType.swap:
        return 'Swap';
      case TransactionType.approve:
        return 'Approve';
      case TransactionType.stake:
        return 'Stake';
      case TransactionType.unstake:
        return 'Unstake';
      case TransactionType.mint:
        return 'Mint';
      case TransactionType.burn:
        return 'Burn';
      case TransactionType.contractInteraction:
        return 'Contract';
      case TransactionType.unknown:
        return 'Transaction';
    }
  }

  static TransactionType fromString(String value) {
    return TransactionType.values.firstWhere(
      (type) => type.name.toLowerCase() == value.toLowerCase(),
      orElse: () => TransactionType.unknown,
    );
  }
}

/// Transaction model
@immutable
class Transaction {
  final String id;
  final String? hash;
  final String from;
  final String to;
  final String amount;
  final String tokenSymbol;
  final int? tokenDecimals;
  final TransactionType type;
  final TransactionStatus status;
  final DateTime timestamp;
  final int? chainId;
  final String? gasUsed;
  final String? gasPrice;
  final String? gasFee;
  final int? blockNumber;
  final int? nonce;
  final double? riskScore;
  final List<String>? riskFactors;
  final String? errorMessage;
  final Map<String, dynamic>? metadata;

  const Transaction({
    required this.id,
    this.hash,
    required this.from,
    required this.to,
    required this.amount,
    this.tokenSymbol = 'ETH',
    this.tokenDecimals = 18,
    this.type = TransactionType.unknown,
    this.status = TransactionStatus.pending,
    required this.timestamp,
    this.chainId,
    this.gasUsed,
    this.gasPrice,
    this.gasFee,
    this.blockNumber,
    this.nonce,
    this.riskScore,
    this.riskFactors,
    this.errorMessage,
    this.metadata,
  });

  /// Creates a transaction from JSON
  factory Transaction.fromJson(Map<String, dynamic> json) {
    return Transaction(
      id: json['id'] as String,
      hash: json['hash'] as String?,
      from: json['from'] as String,
      to: json['to'] as String,
      amount: json['amount'] as String,
      tokenSymbol: json['tokenSymbol'] ?? json['token_symbol'] ?? 'ETH',
      tokenDecimals: json['tokenDecimals'] ?? json['token_decimals'] ?? 18,
      type: TransactionTypeX.fromString(json['type'] as String? ?? 'unknown'),
      status: TransactionStatusX.fromString(json['status'] as String? ?? 'pending'),
      timestamp: DateTime.parse(json['timestamp'] as String),
      chainId: json['chainId'] ?? json['chain_id'] as int?,
      gasUsed: json['gasUsed'] ?? json['gas_used'] as String?,
      gasPrice: json['gasPrice'] ?? json['gas_price'] as String?,
      gasFee: json['gasFee'] ?? json['gas_fee'] as String?,
      blockNumber: json['blockNumber'] ?? json['block_number'] as int?,
      nonce: json['nonce'] as int?,
      riskScore: (json['riskScore'] ?? json['risk_score'] as num?)?.toDouble(),
      riskFactors: (json['riskFactors'] ?? json['risk_factors'] as List<dynamic>?)
          ?.cast<String>(),
      errorMessage: json['errorMessage'] ?? json['error_message'] as String?,
      metadata: json['metadata'] as Map<String, dynamic>?,
    );
  }

  /// Converts to JSON
  Map<String, dynamic> toJson() {
    return {
      'id': id,
      if (hash != null) 'hash': hash,
      'from': from,
      'to': to,
      'amount': amount,
      'tokenSymbol': tokenSymbol,
      'tokenDecimals': tokenDecimals,
      'type': type.name,
      'status': status.name,
      'timestamp': timestamp.toIso8601String(),
      if (chainId != null) 'chainId': chainId,
      if (gasUsed != null) 'gasUsed': gasUsed,
      if (gasPrice != null) 'gasPrice': gasPrice,
      if (gasFee != null) 'gasFee': gasFee,
      if (blockNumber != null) 'blockNumber': blockNumber,
      if (nonce != null) 'nonce': nonce,
      if (riskScore != null) 'riskScore': riskScore,
      if (riskFactors != null) 'riskFactors': riskFactors,
      if (errorMessage != null) 'errorMessage': errorMessage,
      if (metadata != null) 'metadata': metadata,
    };
  }

  /// Whether this is a send transaction from the user's perspective
  bool isSentFrom(String address) =>
      from.toLowerCase() == address.toLowerCase();

  /// Whether this is a receive transaction from the user's perspective
  bool isReceivedBy(String address) =>
      to.toLowerCase() == address.toLowerCase();

  /// Short formatted hash
  String? get shortHash {
    if (hash == null || hash!.length < 12) return hash;
    return '${hash!.substring(0, 6)}...${hash!.substring(hash!.length - 4)}';
  }

  /// Short formatted from address
  String get shortFrom {
    if (from.length > 12) {
      return '${from.substring(0, 6)}...${from.substring(from.length - 4)}';
    }
    return from;
  }

  /// Short formatted to address
  String get shortTo {
    if (to.length > 12) {
      return '${to.substring(0, 6)}...${to.substring(to.length - 4)}';
    }
    return to;
  }

  /// Time ago string
  String get timeAgo {
    final now = DateTime.now();
    final diff = now.difference(timestamp);

    if (diff.inMinutes < 1) return 'Just now';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    if (diff.inDays < 7) return '${diff.inDays}d ago';
    return '${timestamp.day}/${timestamp.month}/${timestamp.year}';
  }

  /// Creates a copy with updated fields
  Transaction copyWith({
    String? id,
    String? hash,
    String? from,
    String? to,
    String? amount,
    String? tokenSymbol,
    int? tokenDecimals,
    TransactionType? type,
    TransactionStatus? status,
    DateTime? timestamp,
    int? chainId,
    String? gasUsed,
    String? gasPrice,
    String? gasFee,
    int? blockNumber,
    int? nonce,
    double? riskScore,
    List<String>? riskFactors,
    String? errorMessage,
    Map<String, dynamic>? metadata,
  }) {
    return Transaction(
      id: id ?? this.id,
      hash: hash ?? this.hash,
      from: from ?? this.from,
      to: to ?? this.to,
      amount: amount ?? this.amount,
      tokenSymbol: tokenSymbol ?? this.tokenSymbol,
      tokenDecimals: tokenDecimals ?? this.tokenDecimals,
      type: type ?? this.type,
      status: status ?? this.status,
      timestamp: timestamp ?? this.timestamp,
      chainId: chainId ?? this.chainId,
      gasUsed: gasUsed ?? this.gasUsed,
      gasPrice: gasPrice ?? this.gasPrice,
      gasFee: gasFee ?? this.gasFee,
      blockNumber: blockNumber ?? this.blockNumber,
      nonce: nonce ?? this.nonce,
      riskScore: riskScore ?? this.riskScore,
      riskFactors: riskFactors ?? this.riskFactors,
      errorMessage: errorMessage ?? this.errorMessage,
      metadata: metadata ?? this.metadata,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is Transaction &&
          runtimeType == other.runtimeType &&
          id == other.id;

  @override
  int get hashCode => id.hashCode;

  @override
  String toString() =>
      'Transaction(id: $id, hash: $shortHash, ${shortFrom} -> ${shortTo}, $amount $tokenSymbol, ${status.name})';
}

/// Transaction request for initiating a new transaction
@immutable
class TransactionRequest {
  final String to;
  final String amount;
  final String tokenSymbol;
  final String? contractAddress;
  final int? chainId;
  final String? data;
  final Map<String, dynamic>? metadata;

  const TransactionRequest({
    required this.to,
    required this.amount,
    this.tokenSymbol = 'ETH',
    this.contractAddress,
    this.chainId,
    this.data,
    this.metadata,
  });

  Map<String, dynamic> toJson() {
    return {
      'to': to,
      'amount': amount,
      'tokenSymbol': tokenSymbol,
      if (contractAddress != null) 'contractAddress': contractAddress,
      if (chainId != null) 'chainId': chainId,
      if (data != null) 'data': data,
      if (metadata != null) 'metadata': metadata,
    };
  }
}
