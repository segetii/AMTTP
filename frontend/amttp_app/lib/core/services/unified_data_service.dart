/// Unified Data Service for Flutter
/// 
/// Provides consistent data access across all Flutter components.
/// Fetches from Next.js API endpoints to ensure data uniformity.
library;

import 'dart:convert';
import 'package:http/http.dart' as http;
import '../constants/app_constants.dart';

/// Dashboard statistics from Memgraph
class DashboardStats {
  final int totalTransactions;
  final double totalVolume;
  final int flaggedCount;
  final double averageRiskScore;
  final int highRiskWallets;
  final double complianceRate;

  DashboardStats({
    required this.totalTransactions,
    required this.totalVolume,
    required this.flaggedCount,
    required this.averageRiskScore,
    required this.highRiskWallets,
    required this.complianceRate,
  });

  factory DashboardStats.fromJson(Map<String, dynamic> json) {
    final totalTx = json['totalTransactions'] as int? ?? 0;
    final flagged = json['flaggedWallets'] as int? ?? json['flaggedCount'] as int? ?? 0;
    
    return DashboardStats(
      totalTransactions: totalTx,
      totalVolume: (json['totalVolume'] as num?)?.toDouble() ?? 0.0,
      flaggedCount: flagged,
      averageRiskScore: (json['avgRiskScore'] as num?)?.toDouble() ?? 
                        (json['averageRiskScore'] as num?)?.toDouble() ?? 0.0,
      highRiskWallets: json['highRiskWallets'] as int? ?? 0,
      complianceRate: totalTx > 0 ? ((totalTx - flagged) / totalTx) * 100 : 100.0,
    );
  }

  factory DashboardStats.empty() => DashboardStats(
    totalTransactions: 0,
    totalVolume: 0.0,
    flaggedCount: 0,
    averageRiskScore: 0.0,
    highRiskWallets: 0,
    complianceRate: 100.0,
  );
}

/// Flagged transaction item
class FlaggedTransaction {
  final String id;
  final String hash;
  final String from;
  final String to;
  final double value;
  final double riskScore;
  final List<String> flags;
  final String timestamp;
  final String status;

  FlaggedTransaction({
    required this.id,
    required this.hash,
    required this.from,
    required this.to,
    required this.value,
    required this.riskScore,
    required this.flags,
    required this.timestamp,
    required this.status,
  });

  factory FlaggedTransaction.fromJson(Map<String, dynamic> json, int index) {
    return FlaggedTransaction(
      id: json['id'] as String? ?? 'flagged-$index',
      hash: json['hash'] as String? ?? json['tx_hash'] as String? ?? '',
      from: json['from'] as String? ?? json['sender'] as String? ?? '',
      to: json['to'] as String? ?? json['receiver'] as String? ?? '',
      value: (json['value'] as num?)?.toDouble() ?? (json['amount'] as num?)?.toDouble() ?? 0.0,
      riskScore: (json['riskScore'] as num?)?.toDouble() ?? (json['risk_score'] as num?)?.toDouble() ?? 0.0,
      flags: (json['flags'] as List<dynamic>?)?.cast<String>() ?? [json['reason'] as String? ?? 'Flagged'],
      timestamp: json['timestamp'] as String? ?? DateTime.now().toIso8601String(),
      status: json['status'] as String? ?? 'pending',
    );
  }
}

/// Sankey flow node
class SankeyNode {
  final String id;
  final String label;
  final String type;
  final String riskLevel;

  SankeyNode({
    required this.id,
    required this.label,
    required this.type,
    required this.riskLevel,
  });

  factory SankeyNode.fromJson(Map<String, dynamic> json) {
    return SankeyNode(
      id: json['id'] as String? ?? '',
      label: json['label'] as String? ?? '',
      type: json['type'] as String? ?? 'intermediate',
      riskLevel: json['riskLevel'] as String? ?? 'medium',
    );
  }
}

/// Sankey flow link
class SankeyLink {
  final String source;
  final String target;
  final double value;
  final int count;
  final bool isAnomaly;

  SankeyLink({
    required this.source,
    required this.target,
    required this.value,
    required this.count,
    required this.isAnomaly,
  });

  factory SankeyLink.fromJson(Map<String, dynamic> json) {
    return SankeyLink(
      source: json['source'] as String? ?? '',
      target: json['target'] as String? ?? '',
      value: (json['value'] as num?)?.toDouble() ?? 0.0,
      count: json['count'] as int? ?? 0,
      isAnomaly: json['isAnomaly'] as bool? ?? false,
    );
  }
}

/// Sankey data container
class SankeyData {
  final List<SankeyNode> nodes;
  final List<SankeyLink> links;

  SankeyData({required this.nodes, required this.links});

  factory SankeyData.fromJson(Map<String, dynamic> json) {
    return SankeyData(
      nodes: (json['nodes'] as List<dynamic>?)
          ?.map((n) => SankeyNode.fromJson(n as Map<String, dynamic>))
          .toList() ?? [],
      links: (json['links'] as List<dynamic>?)
          ?.map((l) => SankeyLink.fromJson(l as Map<String, dynamic>))
          .toList() ?? [],
    );
  }

  factory SankeyData.empty() => SankeyData(nodes: [], links: []);
}

/// Graph node for network visualization
class GraphNodeData {
  final String id;
  final double riskScore;
  final int transactionCount;
  final double totalValue;

  GraphNodeData({
    required this.id,
    required this.riskScore,
    required this.transactionCount,
    required this.totalValue,
  });

  factory GraphNodeData.fromJson(Map<String, dynamic> json) {
    return GraphNodeData(
      id: json['id'] as String? ?? '',
      riskScore: (json['riskScore'] as num?)?.toDouble() ?? 
                 (json['risk_score'] as num?)?.toDouble() ?? 0.0,
      transactionCount: json['transactionCount'] as int? ?? 
                        json['tx_count'] as int? ?? 0,
      totalValue: (json['totalValue'] as num?)?.toDouble() ?? 
                  (json['value'] as num?)?.toDouble() ?? 0.0,
    );
  }
}

/// Graph edge for network visualization
class GraphEdgeData {
  final String id;
  final String source;
  final String target;
  final double value;

  GraphEdgeData({
    required this.id,
    required this.source,
    required this.target,
    required this.value,
  });

  factory GraphEdgeData.fromJson(Map<String, dynamic> json) {
    return GraphEdgeData(
      id: json['id'] as String? ?? '${json['source']}-${json['target']}',
      source: json['source'] as String? ?? '',
      target: json['target'] as String? ?? '',
      value: (json['value'] as num?)?.toDouble() ?? 0.0,
    );
  }
}

/// Graph data container
class GraphData {
  final List<GraphNodeData> nodes;
  final List<GraphEdgeData> edges;

  GraphData({required this.nodes, required this.edges});

  factory GraphData.fromJson(Map<String, dynamic> json) {
    return GraphData(
      nodes: (json['nodes'] as List<dynamic>?)
          ?.map((n) => GraphNodeData.fromJson(n as Map<String, dynamic>))
          .toList() ?? [],
      edges: (json['edges'] as List<dynamic>?)
          ?.map((e) => GraphEdgeData.fromJson(e as Map<String, dynamic>))
          .toList() ?? [],
    );
  }

  factory GraphData.empty() => GraphData(nodes: [], edges: []);
}

/// Unified Data Service
/// 
/// Fetches all visualization data from the Next.js API endpoints
/// to ensure consistency with the web dashboard.
class UnifiedDataService {
  static final UnifiedDataService _instance = UnifiedDataService._internal();
  factory UnifiedDataService() => _instance;
  UnifiedDataService._internal();

  final String _baseUrl = AppConstants.nextJsUrl;
  final http.Client _client = http.Client();

  /// Fetch dashboard statistics
  Future<DashboardStats> getDashboardStats() async {
    try {
      final response = await _client.get(
        Uri.parse('$_baseUrl/api/data/stats'),
        headers: {'Accept': 'application/json'},
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final json = jsonDecode(response.body) as Map<String, dynamic>;
        return DashboardStats.fromJson(json);
      }
    } catch (e) {
      // Fallback to empty stats on error
    }
    return DashboardStats.empty();
  }

  /// Fetch flagged transaction queue
  Future<List<FlaggedTransaction>> getFlaggedQueue() async {
    try {
      final response = await _client.get(
        Uri.parse('$_baseUrl/api/data/flagged'),
        headers: {'Accept': 'application/json'},
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final json = jsonDecode(response.body) as List<dynamic>;
        return json.asMap().entries.map((e) => 
          FlaggedTransaction.fromJson(e.value as Map<String, dynamic>, e.key)
        ).toList();
      }
    } catch (e) {
      // Fallback to empty list on error
    }
    return [];
  }

  /// Fetch sankey flow data
  Future<SankeyData> getSankeyData() async {
    try {
      final response = await _client.get(
        Uri.parse('$_baseUrl/api/data/sankey'),
        headers: {'Accept': 'application/json'},
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final json = jsonDecode(response.body) as Map<String, dynamic>;
        return SankeyData.fromJson(json);
      }
    } catch (e) {
      // Fallback to empty data on error
    }
    return SankeyData.empty();
  }

  /// Fetch graph network data
  Future<GraphData> getGraphData() async {
    try {
      final response = await _client.get(
        Uri.parse('$_baseUrl/api/data/graph'),
        headers: {'Accept': 'application/json'},
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final json = jsonDecode(response.body) as Map<String, dynamic>;
        return GraphData.fromJson(json);
      }
    } catch (e) {
      // Fallback to empty data on error
    }
    return GraphData.empty();
  }

  void dispose() {
    _client.close();
  }
}
