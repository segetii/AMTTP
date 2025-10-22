import 'package:web3dart/web3dart.dart';
import 'package:http/http.dart';
import 'dart:js' as js;
import 'dart:js_util' as js_util;

class Web3Service {
  static Web3Service? _instance;
  Web3Client? _client;

  // AMTTP Contract addresses (use real deployed contracts)
  static const String _rpcUrl = 'http://localhost:8545'; // Local development
  // static const String _amttpTokenAddress =
  //     '0x1234567890123456789012345678901234567890'; // Replace with real contract
  // static const String _policyEngineAddress =
  //     '0x0987654321098765432109876543210987654321'; // Replace with real contract

  Web3Service._internal();

  static Web3Service get instance {
    _instance ??= Web3Service._internal();
    return _instance!;
  }

  Future<void> initialize() async {
    try {
      _client = Web3Client(_rpcUrl, Client());
      print('Web3Service initialized with RPC: $_rpcUrl');
    } catch (e) {
      print('Error initializing Web3Service: $e');
    }
  }

  // Check if MetaMask is available
  bool get isMetaMaskAvailable {
    try {
      return js.context.hasProperty('ethereum');
    } catch (e) {
      return false;
    }
  }

  // Connect to MetaMask wallet
  Future<String?> connectWallet() async {
    if (!isMetaMaskAvailable) {
      throw Exception(
          'MetaMask not detected. Please install MetaMask browser extension.');
    }

    try {
      // Request account access
      final ethereum = js.context['ethereum'];
      final accounts = await js_util
          .promiseToFuture(js_util.callMethod(ethereum, 'request', [
        js_util.jsify({'method': 'eth_requestAccounts'})
      ]));

      if (accounts != null && accounts.length > 0) {
        final address = accounts[0] as String;
        print('Connected to wallet: $address');
        return address;
      }

      throw Exception('No accounts found');
    } catch (e) {
      print('Error connecting to wallet: $e');
      throw Exception('Failed to connect wallet: $e');
    }
  }

  // Get current wallet address
  Future<String?> getCurrentAccount() async {
    if (!isMetaMaskAvailable) return null;

    try {
      final ethereum = js.context['ethereum'];
      final accounts = await js_util
          .promiseToFuture(js_util.callMethod(ethereum, 'request', [
        js_util.jsify({'method': 'eth_accounts'})
      ]));

      if (accounts != null && accounts.length > 0) {
        return accounts[0] as String;
      }
      return null;
    } catch (e) {
      print('Error getting current account: $e');
      return null;
    }
  }

  // Get AMTTP token balance
  Future<double> getAmttpBalance(String address) async {
    try {
      if (_client == null) await initialize();

      // For demo purposes, return a calculated balance
      // In production, this would call the actual AMTTP token contract

      // Mock balance calculation based on address
      final balance = address.hashCode.abs() % 10000;
      return balance.toDouble();
    } catch (e) {
      print('Error getting AMTTP balance: $e');
      return 0.0;
    }
  }

  // Get ETH balance
  Future<double> getEthBalance(String address) async {
    try {
      if (_client == null) await initialize();

      final ethAddress = EthereumAddress.fromHex(address);
      final balance = await _client!.getBalance(ethAddress);
      return balance.getInWei.toDouble() / 1e18; // Convert wei to ETH
    } catch (e) {
      print('Error getting ETH balance: $e');
      return 0.0;
    }
  }

  // Perform risk analysis (call smart contract)
  Future<Map<String, dynamic>> performRiskAnalysis(
      Map<String, dynamic> transactionData) async {
    try {
      // This would call the actual policy engine contract
      // For now, return a calculated risk score

      final amount = transactionData['amount'] as double? ?? 0.0;
      final riskScore = _calculateRiskScore(amount);

      return {
        'riskScore': riskScore,
        'riskLevel': _getRiskLevel(riskScore),
        'recommendation': _getRiskRecommendation(riskScore),
        'timestamp': DateTime.now().millisecondsSinceEpoch,
      };
    } catch (e) {
      print('Error performing risk analysis: $e');
      return {
        'riskScore': 50.0,
        'riskLevel': 'medium',
        'recommendation': 'Review transaction carefully',
        'timestamp': DateTime.now().millisecondsSinceEpoch,
      };
    }
  }

  double _calculateRiskScore(double amount) {
    // Simple risk calculation based on transaction amount
    if (amount < 100) return 10.0 + (amount * 0.1);
    if (amount < 1000) return 20.0 + ((amount - 100) * 0.05);
    if (amount < 10000) return 25.0 + ((amount - 1000) * 0.01);
    return 75.0 + ((amount - 10000) * 0.001);
  }

  String _getRiskLevel(double score) {
    if (score < 25) return 'low';
    if (score < 50) return 'medium';
    if (score < 75) return 'high';
    return 'critical';
  }

  String _getRiskRecommendation(double score) {
    if (score < 25) return 'Transaction appears safe to proceed';
    if (score < 50) return 'Review transaction details carefully';
    if (score < 75) return 'High risk detected - proceed with caution';
    return 'Critical risk - recommend declining transaction';
  }

  // Listen for account changes
  void onAccountsChanged(Function(List<String>) callback) {
    if (!isMetaMaskAvailable) return;

    try {
      final ethereum = js.context['ethereum'];
      js_util.callMethod(ethereum, 'on', [
        'accountsChanged',
        js.allowInterop((accounts) {
          if (accounts != null) {
            callback(List<String>.from(accounts));
          }
        })
      ]);
    } catch (e) {
      print('Error setting up account change listener: $e');
    }
  }

  // Listen for chain changes
  void onChainChanged(Function(String) callback) {
    if (!isMetaMaskAvailable) return;

    try {
      final ethereum = js.context['ethereum'];
      js_util.callMethod(ethereum, 'on', [
        'chainChanged',
        js.allowInterop((chainId) {
          if (chainId != null) {
            callback(chainId.toString());
          }
        })
      ]);
    } catch (e) {
      print('Error setting up chain change listener: $e');
    }
  }

  void dispose() {
    _client?.dispose();
  }
}
