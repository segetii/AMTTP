import 'dart:async';
import 'dart:html' as html;
import 'dart:js_util' as jsu;
import 'package:flutter/foundation.dart';

class Web3Service {
  static final Web3Service _instance = Web3Service._internal();
  static Web3Service get instance => _instance;

  Web3Service._internal();

  // CHANGED: Always return true so the UI button is enabled.
  // We check for 'ethereum' inside connectWallet() instead.
  bool get isMetaMaskAvailable => true;

  Future<void> initialize() async {
    // No-op for now as we use window.ethereum directly
  }

  void onAccountsChanged(Function(List<String>) callback) {
    if (!jsu.hasProperty(html.window, 'ethereum')) return;
    final ethereum = jsu.getProperty(html.window, 'ethereum');
    
    jsu.callMethod(ethereum, 'on', ['accountsChanged', jsu.allowInterop((accounts) {
      final List<String> dartAccounts = [];
      if (accounts is List) {
        dartAccounts.addAll(accounts.map((e) => e.toString()));
      }
      callback(dartAccounts);
    })]);
  }

  void onChainChanged(Function(String) callback) {
    if (!jsu.hasProperty(html.window, 'ethereum')) return;
    final ethereum = jsu.getProperty(html.window, 'ethereum');
    
    jsu.callMethod(ethereum, 'on', ['chainChanged', jsu.allowInterop((chainId) {
      callback(chainId.toString());
    })]);
  }

  Future<void> checkAndSwitchNetwork() async {
    if (!jsu.hasProperty(html.window, 'ethereum')) return;
    final ethereum = jsu.getProperty(html.window, 'ethereum');

    try {
      final chainId = await jsu.promiseToFuture(
        jsu.callMethod(ethereum, 'request', [
          jsu.jsify({'method': 'eth_chainId'})
        ]),
      );

      // 0xaa36a7 is Sepolia
      if (chainId != '0xaa36a7') {
        debugPrint('Wrong network detected ($chainId). Switching to Sepolia...');
        try {
          await jsu.promiseToFuture(
            jsu.callMethod(ethereum, 'request', [
              jsu.jsify({
                'method': 'wallet_switchEthereumChain',
                'params': [{'chainId': '0xaa36a7'}]
              })
            ]),
          );
        } catch (e) {
          // If switch fails, try to add the chain
          debugPrint('Switch failed, trying to add Sepolia chain...');
          await jsu.promiseToFuture(
            jsu.callMethod(ethereum, 'request', [
              jsu.jsify({
                'method': 'wallet_addEthereumChain',
                'params': [
                  {
                    'chainId': '0xaa36a7',
                    'chainName': 'Sepolia Test Network',
                    'nativeCurrency': {
                      'name': 'Sepolia ETH',
                      'symbol': 'ETH',
                      'decimals': 18,
                    },
                    'rpcUrls': ['https://sepolia.infura.io/v3/'],
                    'blockExplorerUrls': ['https://sepolia.etherscan.io'],
                  },
                ],
              })
            ]),
          );
        }
      }
    } catch (e) {
      debugPrint('Error switching network: $e');
    }
  }

  Future<String?> connectWallet() async {
    // 1. Direct check when action is triggered
    final hasEth = jsu.hasProperty(html.window, 'ethereum');
    
    if (!hasEth) {
      throw Exception('MetaMask not found! Please install the extension.');
    }

    final ethereum = jsu.getProperty(html.window, 'ethereum');

    try {
      // Ensure we are on Sepolia before connecting
      await checkAndSwitchNetwork();

      // 2. Request accounts directly
      final accounts = await jsu.promiseToFuture(
        jsu.callMethod(ethereum, 'request', [
          jsu.jsify({'method': 'eth_requestAccounts'})
        ]),
      );

      // 3. Handle response safely
      if (accounts == null) return null;
      
      // Convert JS array to Dart list safely
      final List<dynamic> accList = [];
      // Handle different JS array types that might be returned
      if (accounts is List) {
        accList.addAll(accounts);
      } else {
        // Fallback for JS iterables
        try {
          accList.addAll(List.from(accounts as Iterable));
        } catch (_) {
          // Last resort: try toString if it's a single item or weird object
          return accounts.toString(); 
        }
      }
      
      if (accList.isEmpty) return null;
      
      return accList.first.toString();
    } catch (e) {
      throw Exception('Connection failed: $e');
    }
  }

  Future<String?> getCurrentAccount() async {
    if (!jsu.hasProperty(html.window, 'ethereum')) return null;
    
    try {
       final ethereum = jsu.getProperty(html.window, 'ethereum');
       final accounts = await jsu.promiseToFuture(
        jsu.callMethod(ethereum, 'request', [
          jsu.jsify({'method': 'eth_accounts'})
        ]),
      );
      
      if (accounts == null) return null;
      
      final List<dynamic> accList = [];
      if (accounts is List) {
        accList.addAll(accounts);
      } else {
        try {
          accList.addAll(List.from(accounts as Iterable));
        } catch (_) {
          return null;
        }
      }

      if (accList.isEmpty) return null;
      return accList.first.toString();
    } catch (_) {
      return null;
    }
  }

  Future<String> sendTransaction({
    required String to,
    required double amountInEth,
    String? data,
  }) async {
    if (!jsu.hasProperty(html.window, 'ethereum')) {
      throw Exception('MetaMask not found');
    }
    
    final ethereum = jsu.getProperty(html.window, 'ethereum');
    
    // Get current account first
    final from = await getCurrentAccount();
    if (from == null) throw Exception('No account connected');

    // Convert ETH to Wei (hex)
    // 1 ETH = 10^18 Wei
    final wei = (amountInEth * 1000000000000000000).toInt();
    final valueHex = '0x${wei.toRadixString(16)}';

    final transactionParameters = <String, dynamic>{
      'to': to,
      'from': from,
      'value': valueHex,
    };

    if (data != null) {
      transactionParameters['data'] = data;
    }

    try {
      final txHash = await jsu.promiseToFuture(
        jsu.callMethod(ethereum, 'request', [
          jsu.jsify({
            'method': 'eth_sendTransaction',
            'params': [transactionParameters],
          })
        ]),
      );
      return txHash.toString();
    } catch (e) {
      throw Exception('Transaction failed: $e');
    }
  }

  Future<double> getEthBalance(String address) async {
    if (!jsu.hasProperty(html.window, 'ethereum')) {
      debugPrint('getEthBalance: No ethereum provider');
      return 0.0;
    }
    final ethereum = jsu.getProperty(html.window, 'ethereum');
    try {
      // Ensure address is lowercase for consistency
      final normalizedAddress = address.toLowerCase();
      debugPrint('getEthBalance: Querying balance for $normalizedAddress');
      
      final balanceHex = await jsu.promiseToFuture(
        jsu.callMethod(ethereum, 'request', [
          jsu.jsify({
            'method': 'eth_getBalance',
            'params': [normalizedAddress, 'latest']
          })
        ]),
      );
      
      debugPrint('getEthBalance: Raw result = $balanceHex');
      
      if (balanceHex == null) {
        debugPrint('getEthBalance: Balance is null');
        return 0.0;
      }
      
      // Convert hex to double (ETH)
      final hexStr = balanceHex.toString();
      if (hexStr.isEmpty || hexStr == '0x0' || hexStr == '0x') {
        debugPrint('getEthBalance: Balance is zero or empty');
        return 0.0;
      }
      
      final hex = hexStr.replaceAll('0x', '');
      if (hex.isEmpty) return 0.0;
      
      final wei = BigInt.parse(hex, radix: 16);
      final ethBalance = wei.toDouble() / 1e18;
      debugPrint('getEthBalance: Parsed balance = $ethBalance ETH');
      return ethBalance;
    } catch (e) {
      debugPrint('Error getting ETH balance: $e');
      return 0.0;
    }
  }
}
