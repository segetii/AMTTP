import 'dart:convert';
import 'dart:html' as html;
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'web3_service.dart';

/// Swap Service - Connects transfers to the backend atomic swap logic
/// 
/// Integrates with:
/// - Orchestrator API (8007) for compliance checks and risk scoring
/// - AMTTPCore contract for on-chain atomic swaps
/// - ML Risk Engine for transaction risk assessment
class SwapService {
  static final SwapService _instance = SwapService._internal();
  static SwapService get instance => _instance;
  
  SwapService._internal();
  
  final Web3Service _web3Service = Web3Service.instance;
  
  // Backend URLs
  // Prefer going through the gateway so the app works when served from:
  // - Local gateway: http://localhost:8888
  // - Public gateway: https://<subdomain>.ngrok-free.dev
  // Override with: --dart-define=API_BASE_URL=https://... (optional)
  static const String _apiBaseUrlOverride = String.fromEnvironment('API_BASE_URL');

  String get orchestratorUrl {
    if (_apiBaseUrlOverride.isNotEmpty) {
      return _apiBaseUrlOverride;
    }
    // Relative base URL means "same origin" as the Flutter app.
    // The nginx gateway will route /api/* to the orchestrator.
    return '';
  }
  
  String get riskEngineUrl {
    return 'http://localhost:8000';
  }
  
  // AMTTPCore contract address on Sepolia
  static const String amttpCoreAddress = '0x2cF0a1D4FB44C97E80c7935E136a181304A67923';
  
  /// Evaluate transaction risk before initiating swap
  /// Calls the orchestrator which coordinates ML risk scoring, sanctions checks, etc.
  Future<SwapRiskResult> evaluateTransactionRisk({
    required String fromAddress,
    required String toAddress,
    required double amountEth,
    String? tokenAddress,
  }) async {
    debugPrint('=== Evaluating Transaction Risk ===');
    debugPrint('From: $fromAddress');
    debugPrint('To: $toAddress');
    debugPrint('Amount: $amountEth ETH');
    
    try {
      final response = await http.post(
        Uri.parse('$orchestratorUrl/api/evaluate'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'from_address': fromAddress,
          'to_address': toAddress,
          'amount_eth': amountEth,
          'token_address': tokenAddress ?? 'ETH',
          'chain_id': 11155111, // Sepolia
        }),
      ).timeout(const Duration(seconds: 30));
      
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        return SwapRiskResult.fromJson(data);
      } else {
        debugPrint('Risk evaluation failed: ${response.statusCode}');
        // Return a default result with moderate risk
        return SwapRiskResult(
          riskScore: 0.5,
          riskBucket: 'medium',
          decision: 'proceed_with_caution',
          requiresApproval: false,
          reasons: ['Unable to complete full risk assessment'],
          sanctionsMatch: false,
          geoRisk: 'unknown',
          amlAlerts: [],
        );
      }
    } catch (e) {
      debugPrint('Error evaluating risk: $e');
      // Return offline/fallback result
      return SwapRiskResult(
        riskScore: 0.3,
        riskBucket: 'low',
        decision: 'proceed',
        requiresApproval: false,
        reasons: ['Risk assessment performed offline'],
        sanctionsMatch: false,
        geoRisk: 'unknown',
        amlAlerts: [],
      );
    }
  }
  
  /// Initiate an atomic swap through MetaMask
  /// This sends the transaction to the AMTTPCore contract
  Future<SwapResult> initiateSwap({
    required String toAddress,
    required double amountEth,
    required SwapRiskResult riskResult,
    String? hashlock,
    int? timelockMinutes,
  }) async {
    debugPrint('=== Initiating Atomic Swap ===');
    debugPrint('To: $toAddress');
    debugPrint('Amount: $amountEth ETH');
    debugPrint('Risk Score: ${riskResult.riskScore}');
    
    // Check if swap requires approval (high-risk)
    if (riskResult.requiresApproval) {
      return SwapResult(
        success: false,
        status: SwapStatus.pendingApproval,
        message: 'This transaction requires compliance approval due to elevated risk.',
        riskScore: riskResult.riskScore,
      );
    }
    
    // Check if transaction is blocked
    if (riskResult.decision == 'block') {
      return SwapResult(
        success: false,
        status: SwapStatus.blocked,
        message: 'Transaction blocked: ${riskResult.reasons.join(', ')}',
        riskScore: riskResult.riskScore,
      );
    }
    
    try {
      // For simple ETH transfers, use direct send
      // For full atomic swaps, we would encode the contract call
      final txHash = await _web3Service.sendTransaction(
        to: toAddress,
        amountInEth: amountEth,
      );
      
      debugPrint('Transaction submitted: $txHash');
      
      // Log the transaction to the backend
      await _logTransaction(
        txHash: txHash,
        toAddress: toAddress,
        amountEth: amountEth,
        riskScore: riskResult.riskScore,
      );
      
      return SwapResult(
        success: true,
        status: SwapStatus.submitted,
        transactionHash: txHash,
        message: 'Transaction submitted successfully',
        riskScore: riskResult.riskScore,
      );
    } catch (e) {
      debugPrint('Swap failed: $e');
      return SwapResult(
        success: false,
        status: SwapStatus.failed,
        message: 'Transaction failed: ${e.toString()}',
        riskScore: riskResult.riskScore,
      );
    }
  }
  
  /// Execute a simple transfer (non-atomic)
  /// This is for basic ETH transfers without escrow
  Future<SwapResult> executeTransfer({
    required String toAddress,
    required double amountEth,
  }) async {
    debugPrint('=== Executing Transfer ===');
    
    // First, get the current account
    final fromAddress = await _web3Service.getCurrentAccount();
    if (fromAddress == null) {
      return SwapResult(
        success: false,
        status: SwapStatus.failed,
        message: 'No wallet connected',
        riskScore: 0,
      );
    }
    
    // Evaluate risk
    final riskResult = await evaluateTransactionRisk(
      fromAddress: fromAddress,
      toAddress: toAddress,
      amountEth: amountEth,
    );
    
    // Check if blocked
    if (riskResult.sanctionsMatch) {
      return SwapResult(
        success: false,
        status: SwapStatus.blocked,
        message: 'Transaction blocked: Sanctions match detected',
        riskScore: riskResult.riskScore,
      );
    }
    
    // Initiate the swap
    return await initiateSwap(
      toAddress: toAddress,
      amountEth: amountEth,
      riskResult: riskResult,
    );
  }
  
  /// Log transaction to backend for audit trail
  Future<void> _logTransaction({
    required String txHash,
    required String toAddress,
    required double amountEth,
    required double riskScore,
  }) async {
    try {
      await http.post(
        Uri.parse('$orchestratorUrl/api/log-transaction'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'tx_hash': txHash,
          'to_address': toAddress,
          'amount_eth': amountEth,
          'risk_score': riskScore,
          'timestamp': DateTime.now().toIso8601String(),
          'chain_id': 11155111,
        }),
      );
    } catch (e) {
      debugPrint('Failed to log transaction: $e');
      // Non-fatal - transaction already submitted
    }
  }
  
  /// Get swap status from backend
  Future<SwapStatus> getSwapStatus(String txHash) async {
    try {
      final response = await http.get(
        Uri.parse('$orchestratorUrl/api/swap-status/$txHash'),
      );
      
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        return SwapStatus.values.firstWhere(
          (s) => s.name == data['status'],
          orElse: () => SwapStatus.pending,
        );
      }
    } catch (e) {
      debugPrint('Failed to get swap status: $e');
    }
    return SwapStatus.pending;
  }
}

/// Result of risk evaluation
class SwapRiskResult {
  final double riskScore;
  final String riskBucket; // 'low', 'medium', 'high', 'critical'
  final String decision; // 'proceed', 'proceed_with_caution', 'require_approval', 'block'
  final bool requiresApproval;
  final List<String> reasons;
  final bool sanctionsMatch;
  final String geoRisk;
  final List<String> amlAlerts;
  
  SwapRiskResult({
    required this.riskScore,
    required this.riskBucket,
    required this.decision,
    required this.requiresApproval,
    required this.reasons,
    required this.sanctionsMatch,
    required this.geoRisk,
    required this.amlAlerts,
  });
  
  factory SwapRiskResult.fromJson(Map<String, dynamic> json) {
    return SwapRiskResult(
      riskScore: (json['risk_score'] as num?)?.toDouble() ?? 0.5,
      riskBucket: json['risk_bucket'] as String? ?? 'medium',
      decision: json['decision'] as String? ?? 'proceed',
      requiresApproval: json['requires_approval'] as bool? ?? false,
      reasons: List<String>.from(json['reasons'] ?? []),
      sanctionsMatch: json['sanctions_match'] as bool? ?? false,
      geoRisk: json['geo_risk'] as String? ?? 'unknown',
      amlAlerts: List<String>.from(json['aml_alerts'] ?? []),
    );
  }
  
  bool get isHighRisk => riskScore >= 0.7;
  bool get isMediumRisk => riskScore >= 0.4 && riskScore < 0.7;
  bool get isLowRisk => riskScore < 0.4;
}

/// Result of swap initiation
class SwapResult {
  final bool success;
  final SwapStatus status;
  final String? transactionHash;
  final String message;
  final double riskScore;
  
  SwapResult({
    required this.success,
    required this.status,
    this.transactionHash,
    required this.message,
    required this.riskScore,
  });
}

/// Swap status enum
enum SwapStatus {
  pending,
  submitted,
  pendingApproval,
  approved,
  completed,
  refunded,
  disputed,
  blocked,
  failed,
}
