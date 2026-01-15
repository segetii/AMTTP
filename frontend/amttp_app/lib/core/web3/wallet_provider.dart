import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../services/web3_service.dart';

enum WalletConnectionStatus {
  disconnected,
  connecting,
  connected,
  error,
}

class WalletState {
  final WalletConnectionStatus status;
  final String? address;
  final String? error;
  final double? balance;
  final double? ethBalance;
  final String? ensName;

  const WalletState({
    this.status = WalletConnectionStatus.disconnected,
    this.address,
    this.error,
    this.balance,
    this.ethBalance,
    this.ensName,
  });

  WalletState copyWith({
    WalletConnectionStatus? status,
    String? address,
    String? error,
    double? balance,
    double? ethBalance,
    String? ensName,
  }) {
    return WalletState(
      status: status ?? this.status,
      address: address ?? this.address,
      error: error ?? this.error,
      balance: balance ?? this.balance,
      ethBalance: ethBalance ?? this.ethBalance,
      ensName: ensName ?? this.ensName,
    );
  }

  bool get isConnected => status == WalletConnectionStatus.connected;
  bool get isConnecting => status == WalletConnectionStatus.connecting;
  bool get hasError => status == WalletConnectionStatus.error;

  String get addressString => address ?? '';
  String get formattedAddress => addressString.isNotEmpty
      ? '${addressString.substring(0, 6)}...${addressString.substring(addressString.length - 4)}'
      : '';
}

class WalletNotifier extends StateNotifier<WalletState> {
  final Web3Service _web3Service;

  WalletNotifier(this._web3Service) : super(const WalletState()) {
    _initialize();
  }

  Future<void> _initialize() async {
    await _web3Service.initialize();

    // Check if already connected
    final currentAccount = await _web3Service.getCurrentAccount();
    if (currentAccount != null) {
      await _updateWalletInfo(currentAccount);
    }

    // Set up listeners for account/chain changes
    _web3Service.onAccountsChanged((accounts) {
      if (accounts.isEmpty) {
        disconnect();
      } else {
        _updateWalletInfo(accounts.first);
      }
    });

    _web3Service.onChainChanged((chainId) {
      print('Chain changed to: $chainId');
    });
  }

  Future<void> connectWallet() async {
    print('=== WalletNotifier.connectWallet() called ===');
    print('MetaMask available: ${_web3Service.isMetaMaskAvailable}');
    
    if (!_web3Service.isMetaMaskAvailable) {
      print('MetaMask not available - setting error state');
      state = state.copyWith(
        status: WalletConnectionStatus.error,
        error:
            'MetaMask not detected. Please install MetaMask browser extension and refresh the page.',
      );
      return;
    }

    try {
      print('Setting connecting state...');
      state = state.copyWith(
        status: WalletConnectionStatus.connecting,
        error: null,
      );

      print('Calling _web3Service.connectWallet()...');
      final address = await _web3Service.connectWallet();
      print('Got address: $address');
      
      if (address != null) {
        await _updateWalletInfo(address);
      } else {
        throw Exception('Failed to get wallet address');
      }
    } catch (e) {
      print('Error in connectWallet: $e');
      state = state.copyWith(
        status: WalletConnectionStatus.error,
        error: e.toString(),
      );
    }
  }

  Future<void> _updateWalletInfo(String address) async {
    try {
      final ethBalance = await _web3Service.getEthBalance(address);

      state = state.copyWith(
        status: WalletConnectionStatus.connected,
        address: address,
        balance: ethBalance,  // Use ETH balance as primary
        ethBalance: ethBalance,
        error: null,
      );
    } catch (e) {
      state = state.copyWith(
        status: WalletConnectionStatus.error,
        error: 'Failed to load wallet information: $e',
      );
    }
  }

  Future<void> disconnect() async {
    state = const WalletState();
  }

  Future<void> refreshBalance() async {
    if (state.address != null) {
      await _updateWalletInfo(state.address!);
    }
  }

  Future<String> sendTransaction({
    required String to,
    required double amount,
    String? data,
  }) async {
    if (!state.isConnected) {
      throw Exception('Wallet not connected');
    }

    try {
      // Send actual transaction via MetaMask
      final txHash = await _web3Service.sendTransaction(
        to: to,
        amountInEth: amount,
        data: data,
      );
      
      // Refresh balance after transaction
      await refreshBalance();
      
      return txHash;
    } catch (e) {
      state = state.copyWith(
        status: WalletConnectionStatus.error,
        error: e.toString(),
      );
      rethrow;
    }
  }
}

final walletProvider =
    StateNotifierProvider<WalletNotifier, WalletState>((ref) {
  return WalletNotifier(Web3Service.instance);
});
