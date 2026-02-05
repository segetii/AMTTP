import 'package:flutter/foundation.dart';

/// Wallet type enumeration
enum WalletType {
  metamask,
  walletConnect,
  coinbase,
  rainbow,
  trust,
  ledger,
  unknown,
}

extension WalletTypeX on WalletType {
  String get displayName {
    switch (this) {
      case WalletType.metamask:
        return 'MetaMask';
      case WalletType.walletConnect:
        return 'WalletConnect';
      case WalletType.coinbase:
        return 'Coinbase Wallet';
      case WalletType.rainbow:
        return 'Rainbow';
      case WalletType.trust:
        return 'Trust Wallet';
      case WalletType.ledger:
        return 'Ledger';
      case WalletType.unknown:
        return 'Unknown Wallet';
    }
  }

  static WalletType fromString(String value) {
    return WalletType.values.firstWhere(
      (type) => type.name.toLowerCase() == value.toLowerCase(),
      orElse: () => WalletType.unknown,
    );
  }
}

/// Network/Chain enumeration
enum ChainId {
  mainnet(1, 'Ethereum Mainnet'),
  goerli(5, 'Goerli Testnet'),
  sepolia(11155111, 'Sepolia Testnet'),
  polygon(137, 'Polygon'),
  mumbai(80001, 'Mumbai Testnet'),
  arbitrum(42161, 'Arbitrum One'),
  optimism(10, 'Optimism'),
  base(8453, 'Base');

  final int id;
  final String displayName;

  const ChainId(this.id, this.displayName);

  static ChainId? fromId(int id) {
    return ChainId.values.where((chain) => chain.id == id).firstOrNull;
  }
}

/// Wallet connection status
enum WalletConnectionStatus {
  disconnected,
  connecting,
  connected,
  error,
}

/// Token balance model
@immutable
class TokenBalance {
  final String symbol;
  final String name;
  final String balance;
  final String? balanceFormatted;
  final double? usdValue;
  final double? change24h;
  final String? contractAddress;
  final int decimals;
  final String? iconUrl;

  const TokenBalance({
    required this.symbol,
    required this.name,
    required this.balance,
    this.balanceFormatted,
    this.usdValue,
    this.change24h,
    this.contractAddress,
    this.decimals = 18,
    this.iconUrl,
  });

  factory TokenBalance.fromJson(Map<String, dynamic> json) {
    return TokenBalance(
      symbol: json['symbol'] as String,
      name: json['name'] as String,
      balance: json['balance'] as String,
      balanceFormatted: json['balanceFormatted'] ?? json['balance_formatted'] as String?,
      usdValue: (json['usdValue'] ?? json['usd_value'] as num?)?.toDouble(),
      change24h: (json['change24h'] ?? json['change_24h'] as num?)?.toDouble(),
      contractAddress: json['contractAddress'] ?? json['contract_address'] as String?,
      decimals: json['decimals'] as int? ?? 18,
      iconUrl: json['iconUrl'] ?? json['icon_url'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'symbol': symbol,
      'name': name,
      'balance': balance,
      if (balanceFormatted != null) 'balanceFormatted': balanceFormatted,
      if (usdValue != null) 'usdValue': usdValue,
      if (change24h != null) 'change24h': change24h,
      if (contractAddress != null) 'contractAddress': contractAddress,
      'decimals': decimals,
      if (iconUrl != null) 'iconUrl': iconUrl,
    };
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is TokenBalance &&
          runtimeType == other.runtimeType &&
          symbol == other.symbol &&
          contractAddress == other.contractAddress;

  @override
  int get hashCode => symbol.hashCode ^ contractAddress.hashCode;
}

/// Wallet model
@immutable
class Wallet {
  final String address;
  final WalletType type;
  final WalletConnectionStatus status;
  final ChainId? chainId;
  final List<TokenBalance> balances;
  final double? trustScore;
  final DateTime? connectedAt;
  final Map<String, dynamic>? metadata;

  const Wallet({
    required this.address,
    this.type = WalletType.unknown,
    this.status = WalletConnectionStatus.disconnected,
    this.chainId,
    this.balances = const [],
    this.trustScore,
    this.connectedAt,
    this.metadata,
  });

  /// Creates an empty/disconnected wallet
  factory Wallet.empty() => const Wallet(
        address: '',
        status: WalletConnectionStatus.disconnected,
      );

  /// Creates a wallet from JSON
  factory Wallet.fromJson(Map<String, dynamic> json) {
    return Wallet(
      address: json['address'] as String,
      type: WalletTypeX.fromString(json['type'] as String? ?? 'unknown'),
      status: WalletConnectionStatus.values.firstWhere(
        (s) => s.name == (json['status'] as String? ?? 'disconnected'),
        orElse: () => WalletConnectionStatus.disconnected,
      ),
      chainId: json['chainId'] != null
          ? ChainId.fromId(json['chainId'] as int)
          : null,
      balances: (json['balances'] as List<dynamic>?)
              ?.map((e) => TokenBalance.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
      trustScore: (json['trustScore'] ?? json['trust_score'] as num?)?.toDouble(),
      connectedAt: json['connectedAt'] != null
          ? DateTime.parse(json['connectedAt'] as String)
          : null,
      metadata: json['metadata'] as Map<String, dynamic>?,
    );
  }

  /// Converts to JSON
  Map<String, dynamic> toJson() {
    return {
      'address': address,
      'type': type.name,
      'status': status.name,
      if (chainId != null) 'chainId': chainId!.id,
      'balances': balances.map((b) => b.toJson()).toList(),
      if (trustScore != null) 'trustScore': trustScore,
      if (connectedAt != null) 'connectedAt': connectedAt!.toIso8601String(),
      if (metadata != null) 'metadata': metadata,
    };
  }

  /// Total USD value of all tokens
  double get totalUsdValue {
    return balances.fold(0.0, (sum, token) => sum + (token.usdValue ?? 0));
  }

  /// Primary token balance (ETH or native token)
  TokenBalance? get primaryBalance {
    return balances.where((b) => b.contractAddress == null).firstOrNull;
  }

  /// Formatted address (shortened)
  String get shortAddress {
    if (address.length > 12) {
      return '${address.substring(0, 6)}...${address.substring(address.length - 4)}';
    }
    return address;
  }

  /// Check if wallet is connected
  bool get isConnected => status == WalletConnectionStatus.connected;

  /// Creates a copy with updated fields
  Wallet copyWith({
    String? address,
    WalletType? type,
    WalletConnectionStatus? status,
    ChainId? chainId,
    List<TokenBalance>? balances,
    double? trustScore,
    DateTime? connectedAt,
    Map<String, dynamic>? metadata,
  }) {
    return Wallet(
      address: address ?? this.address,
      type: type ?? this.type,
      status: status ?? this.status,
      chainId: chainId ?? this.chainId,
      balances: balances ?? this.balances,
      trustScore: trustScore ?? this.trustScore,
      connectedAt: connectedAt ?? this.connectedAt,
      metadata: metadata ?? this.metadata,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is Wallet &&
          runtimeType == other.runtimeType &&
          address.toLowerCase() == other.address.toLowerCase();

  @override
  int get hashCode => address.toLowerCase().hashCode;

  @override
  String toString() =>
      'Wallet(address: $shortAddress, type: ${type.displayName}, status: ${status.name})';
}
