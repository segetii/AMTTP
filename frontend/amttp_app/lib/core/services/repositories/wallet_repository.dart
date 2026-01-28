import 'package:dio/dio.dart';
import 'http_client.dart';
import 'api_config.dart' show ApiConfig;

/// Wallet balance and transaction history repository
/// 
/// Handles:
/// - Fetching wallet balances across chains
/// - Transaction history retrieval
/// - Token balance queries
class WalletRepository {
  final Dio _client = HttpClient.instance;

  /// Fetches the native token balance for an address
  /// 
  /// Returns balance in wei as a string (to preserve precision)
  /// Never returns mock data - throws on failure
  Future<WalletBalance> getBalance(String address, {String? chainId}) async {
    try {
      final response = await _client.get(
        '${ApiConfig.walletEndpoint}/balance',
        queryParameters: {
          'address': address,
          if (chainId != null) 'chainId': chainId,
        },
      );

      if (response.statusCode == 200 && response.data != null) {
        return WalletBalance.fromJson(response.data);
      }

      throw WalletException('Failed to fetch balance: ${response.statusCode}');
    } on DioException catch (e) {
      throw WalletException('Network error: ${e.message}');
    }
  }

  /// Fetches token balances for an address
  Future<List<TokenBalance>> getTokenBalances(String address, {String? chainId}) async {
    try {
      final response = await _client.get(
        '${ApiConfig.walletEndpoint}/tokens',
        queryParameters: {
          'address': address,
          if (chainId != null) 'chainId': chainId,
        },
      );

      if (response.statusCode == 200 && response.data != null) {
        final List<dynamic> data = response.data['tokens'] ?? [];
        return data.map((t) => TokenBalance.fromJson(t)).toList();
      }

      throw WalletException('Failed to fetch token balances: ${response.statusCode}');
    } on DioException catch (e) {
      throw WalletException('Network error: ${e.message}');
    }
  }

  /// Fetches transaction history for an address
  Future<TransactionHistory> getTransactionHistory(
    String address, {
    int page = 1,
    int limit = 20,
    String? chainId,
  }) async {
    try {
      final response = await _client.get(
        '${ApiConfig.walletEndpoint}/transactions',
        queryParameters: {
          'address': address,
          'page': page,
          'limit': limit,
          if (chainId != null) 'chainId': chainId,
        },
      );

      if (response.statusCode == 200 && response.data != null) {
        return TransactionHistory.fromJson(response.data);
      }

      throw WalletException('Failed to fetch transaction history: ${response.statusCode}');
    } on DioException catch (e) {
      throw WalletException('Network error: ${e.message}');
    }
  }

  /// Fetches details for a specific transaction
  Future<TransactionDetails> getTransactionDetails(String txHash, {String? chainId}) async {
    try {
      final response = await _client.get(
        '${ApiConfig.walletEndpoint}/transaction/$txHash',
        queryParameters: {
          if (chainId != null) 'chainId': chainId,
        },
      );

      if (response.statusCode == 200 && response.data != null) {
        return TransactionDetails.fromJson(response.data);
      }

      throw WalletException('Failed to fetch transaction details: ${response.statusCode}');
    } on DioException catch (e) {
      throw WalletException('Network error: ${e.message}');
    }
  }
}

/// Native token balance
class WalletBalance {
  final String address;
  final String balanceWei;
  final String balanceEther;
  final String chainId;
  final String? usdValue;

  WalletBalance({
    required this.address,
    required this.balanceWei,
    required this.balanceEther,
    required this.chainId,
    this.usdValue,
  });

  factory WalletBalance.fromJson(Map<String, dynamic> json) {
    return WalletBalance(
      address: json['address'] ?? '',
      balanceWei: json['balanceWei']?.toString() ?? '0',
      balanceEther: json['balanceEther']?.toString() ?? '0',
      chainId: json['chainId']?.toString() ?? '1',
      usdValue: json['usdValue']?.toString(),
    );
  }
}

/// ERC-20 token balance
class TokenBalance {
  final String tokenAddress;
  final String symbol;
  final String name;
  final int decimals;
  final String balance;
  final String? usdValue;

  TokenBalance({
    required this.tokenAddress,
    required this.symbol,
    required this.name,
    required this.decimals,
    required this.balance,
    this.usdValue,
  });

  factory TokenBalance.fromJson(Map<String, dynamic> json) {
    return TokenBalance(
      tokenAddress: json['tokenAddress'] ?? '',
      symbol: json['symbol'] ?? '',
      name: json['name'] ?? '',
      decimals: json['decimals'] ?? 18,
      balance: json['balance']?.toString() ?? '0',
      usdValue: json['usdValue']?.toString(),
    );
  }
}

/// Paginated transaction history
class TransactionHistory {
  final List<TransactionSummary> transactions;
  final int total;
  final int page;
  final int limit;
  final bool hasMore;

  TransactionHistory({
    required this.transactions,
    required this.total,
    required this.page,
    required this.limit,
    required this.hasMore,
  });

  factory TransactionHistory.fromJson(Map<String, dynamic> json) {
    final List<dynamic> txList = json['transactions'] ?? [];
    return TransactionHistory(
      transactions: txList.map((t) => TransactionSummary.fromJson(t)).toList(),
      total: json['total'] ?? 0,
      page: json['page'] ?? 1,
      limit: json['limit'] ?? 20,
      hasMore: json['hasMore'] ?? false,
    );
  }
}

/// Summary of a transaction (for list views)
class TransactionSummary {
  final String hash;
  final String from;
  final String to;
  final String value;
  final DateTime timestamp;
  final String status;
  final String? methodName;

  TransactionSummary({
    required this.hash,
    required this.from,
    required this.to,
    required this.value,
    required this.timestamp,
    required this.status,
    this.methodName,
  });

  factory TransactionSummary.fromJson(Map<String, dynamic> json) {
    return TransactionSummary(
      hash: json['hash'] ?? '',
      from: json['from'] ?? '',
      to: json['to'] ?? '',
      value: json['value']?.toString() ?? '0',
      timestamp: DateTime.tryParse(json['timestamp'] ?? '') ?? DateTime.now(),
      status: json['status'] ?? 'unknown',
      methodName: json['methodName'],
    );
  }
}

/// Full transaction details
class TransactionDetails {
  final String hash;
  final String from;
  final String to;
  final String value;
  final String gasUsed;
  final String gasPrice;
  final String nonce;
  final String blockNumber;
  final DateTime timestamp;
  final String status;
  final String? methodName;
  final String? input;
  final List<TransactionLog>? logs;

  TransactionDetails({
    required this.hash,
    required this.from,
    required this.to,
    required this.value,
    required this.gasUsed,
    required this.gasPrice,
    required this.nonce,
    required this.blockNumber,
    required this.timestamp,
    required this.status,
    this.methodName,
    this.input,
    this.logs,
  });

  factory TransactionDetails.fromJson(Map<String, dynamic> json) {
    final List<dynamic>? logList = json['logs'];
    return TransactionDetails(
      hash: json['hash'] ?? '',
      from: json['from'] ?? '',
      to: json['to'] ?? '',
      value: json['value']?.toString() ?? '0',
      gasUsed: json['gasUsed']?.toString() ?? '0',
      gasPrice: json['gasPrice']?.toString() ?? '0',
      nonce: json['nonce']?.toString() ?? '0',
      blockNumber: json['blockNumber']?.toString() ?? '0',
      timestamp: DateTime.tryParse(json['timestamp'] ?? '') ?? DateTime.now(),
      status: json['status'] ?? 'unknown',
      methodName: json['methodName'],
      input: json['input'],
      logs: logList?.map((l) => TransactionLog.fromJson(l)).toList(),
    );
  }
}

/// Transaction log/event
class TransactionLog {
  final String address;
  final List<String> topics;
  final String data;
  final String? eventName;

  TransactionLog({
    required this.address,
    required this.topics,
    required this.data,
    this.eventName,
  });

  factory TransactionLog.fromJson(Map<String, dynamic> json) {
    final List<dynamic> topicList = json['topics'] ?? [];
    return TransactionLog(
      address: json['address'] ?? '',
      topics: topicList.map((t) => t.toString()).toList(),
      data: json['data'] ?? '',
      eventName: json['eventName'],
    );
  }
}

/// Exception for wallet operations
class WalletException implements Exception {
  final String message;
  WalletException(this.message);

  @override
  String toString() => 'WalletException: $message';
}
