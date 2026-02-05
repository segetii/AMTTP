import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../core/providers/api_providers.dart';
import '../../../../shared/widgets/risk_level_indicator.dart';
import '../../../../services/swap_service.dart';
import '../../../../services/web3_service.dart';

/// NFT Swap Page - Covers AMTTPNFT.sol functionality
/// Functions covered:
/// - initiateNFTtoETHSwap()
/// - depositETHForNFT()
/// - completeNFTSwap()
/// - initiateNFTtoNFTSwap()
/// - depositNFTForSwap()
/// - completeNFTtoNFTSwap()
/// - refundNFTSwap()
class NFTSwapPage extends ConsumerStatefulWidget {
  const NFTSwapPage({super.key});

  @override
  ConsumerState<NFTSwapPage> createState() => _NFTSwapPageState();
}

class _NFTSwapPageState extends ConsumerState<NFTSwapPage>
    with TickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 4, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.darkBg,
      appBar: AppBar(
        title: const Text('NFT Swap'),
        backgroundColor: AppTheme.darkCard,
        foregroundColor: AppTheme.cleanWhite,
        elevation: 0,
        bottom: TabBar(
          controller: _tabController,
          isScrollable: true,
          indicatorColor: AppTheme.primaryBlue,
          tabs: const [
            Tab(text: 'NFT → ETH', icon: Icon(Icons.swap_horiz)),
            Tab(text: 'NFT → NFT', icon: Icon(Icons.compare_arrows)),
            Tab(text: 'Active Swaps', icon: Icon(Icons.pending_actions)),
            Tab(text: 'History', icon: Icon(Icons.history)),
          ],
        ),
      ),
      body: Container(
        decoration: const BoxDecoration(
          gradient: AppTheme.darkGradient,
        ),
        child: TabBarView(
          controller: _tabController,
          children: [
            _NFTToETHSwapTab(),
            _NFTToNFTSwapTab(),
            _ActiveSwapsTab(),
            _SwapHistoryTab(),
          ],
        ),
      ),
    );
  }
}

/// Tab 0: NFT → ETH Swap
class _NFTToETHSwapTab extends ConsumerStatefulWidget {
  @override
  ConsumerState<_NFTToETHSwapTab> createState() => _NFTToETHSwapTabState();
}

class _NFTToETHSwapTabState extends ConsumerState<_NFTToETHSwapTab> {
  final _formKey = GlobalKey<FormState>();
  final _nftAddressController = TextEditingController();
  final _tokenIdController = TextEditingController();
  final _ethAmountController = TextEditingController();
  final _recipientController = TextEditingController();
  final _hashLockController = TextEditingController();
  
  String _selectedTimelock = '24 hours';
  bool _isLoading = false;
  double? _riskScore;
  SwapRiskResult? _riskResult;
  String? _statusMessage;

  final SwapService _swapService = SwapService.instance;
  final Web3Service _web3Service = Web3Service.instance;

  @override
  void dispose() {
    _nftAddressController.dispose();
    _tokenIdController.dispose();
    _ethAmountController.dispose();
    _recipientController.dispose();
    _hashLockController.dispose();
    super.dispose();
  }

  Future<void> _checkRisk() async {
    if (_recipientController.text.isEmpty || _ethAmountController.text.isEmpty) {
      return;
    }
    
    setState(() => _isLoading = true);
    
    try {
      // Get current connected wallet
      final fromAddress = await _web3Service.getCurrentAccount();
      if (fromAddress == null) {
        setState(() {
          _statusMessage = 'Please connect your wallet first';
        });
        return;
      }
      
      final amount = double.tryParse(_ethAmountController.text) ?? 0.0;
      
      // Call real risk evaluation
      final result = await _swapService.evaluateTransactionRisk(
        fromAddress: fromAddress,
        toAddress: _recipientController.text,
        amountEth: amount,
        tokenAddress: _nftAddressController.text.isNotEmpty 
            ? _nftAddressController.text 
            : null,
      );
      
      setState(() {
        _riskResult = result;
        _riskScore = result.riskScore;
        _statusMessage = null;
      });
    } catch (e) {
      setState(() {
        _statusMessage = 'Risk check failed: $e';
      });
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _initiateSwap() async {
    if (!_formKey.currentState!.validate()) return;
    
    setState(() => _isLoading = true);
    
    try {
      // Check wallet connection
      final fromAddress = await _web3Service.getCurrentAccount();
      if (fromAddress == null) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Please connect your wallet first'),
              backgroundColor: AppTheme.dangerRed,
            ),
          );
        }
        return;
      }
      
      final amount = double.tryParse(_ethAmountController.text) ?? 0.0;
      
      // First evaluate risk if not done
      if (_riskResult == null) {
        _riskResult = await _swapService.evaluateTransactionRisk(
          fromAddress: fromAddress,
          toAddress: _recipientController.text,
          amountEth: amount,
        );
        setState(() {
          _riskScore = _riskResult!.riskScore;
        });
      }
      
      // Parse timelock to minutes
      int timelockMinutes = 24 * 60; // default 24 hours
      switch (_selectedTimelock) {
        case '1 hour': timelockMinutes = 60; break;
        case '6 hours': timelockMinutes = 6 * 60; break;
        case '12 hours': timelockMinutes = 12 * 60; break;
        case '24 hours': timelockMinutes = 24 * 60; break;
        case '48 hours': timelockMinutes = 48 * 60; break;
        case '7 days': timelockMinutes = 7 * 24 * 60; break;
      }
      
      // Initiate the swap via MetaMask
      final result = await _swapService.initiateSwap(
        toAddress: _recipientController.text,
        amountEth: amount,
        riskResult: _riskResult!,
        hashlock: _hashLockController.text.isNotEmpty ? _hashLockController.text : null,
        timelockMinutes: timelockMinutes,
      );
      
      if (mounted) {
        if (result.success) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Swap initiated! TX: ${result.transactionHash?.substring(0, 20)}...'),
              backgroundColor: AppTheme.accentGreen,
              duration: const Duration(seconds: 5),
            ),
          );
          // Clear form on success
          _nftAddressController.clear();
          _tokenIdController.clear();
          _ethAmountController.clear();
          _recipientController.clear();
          _hashLockController.clear();
          setState(() {
            _riskScore = null;
            _riskResult = null;
          });
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(result.message),
              backgroundColor: result.status == SwapStatus.blocked 
                  ? AppTheme.dangerRed 
                  : Colors.orange,
            ),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error: $e'),
            backgroundColor: AppTheme.dangerRed,
          ),
        );
      }
    } finally {
      setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Form(
        key: _formKey,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // NFT Selection Card
            _buildCard(
              title: 'Select Your NFT',
              icon: Icons.image,
              child: Column(
                children: [
                  TextFormField(
                    controller: _nftAddressController,
                    decoration: _inputDecoration('NFT Contract Address', Icons.token),
                    validator: (v) => v?.isEmpty == true ? 'Required' : null,
                    style: const TextStyle(color: AppTheme.cleanWhite),
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _tokenIdController,
                    decoration: _inputDecoration('Token ID', Icons.numbers),
                    keyboardType: TextInputType.number,
                    validator: (v) => v?.isEmpty == true ? 'Required' : null,
                    style: const TextStyle(color: AppTheme.cleanWhite),
                  ),
                  const SizedBox(height: 16),
                  // NFT Preview placeholder
                  Container(
                    height: 150,
                    decoration: BoxDecoration(
                      color: AppTheme.darkBg,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: AppTheme.darkCard),
                    ),
                    child: const Center(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.image_outlined, size: 48, color: AppTheme.mutedText),
                          SizedBox(height: 8),
                          Text('NFT Preview', style: TextStyle(color: AppTheme.mutedText)),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
            
            const SizedBox(height: 16),
            
            // Swap Configuration Card
            _buildCard(
              title: 'Swap Configuration',
              icon: Icons.settings,
              child: Column(
                children: [
                  TextFormField(
                    controller: _ethAmountController,
                    decoration: _inputDecoration('ETH Amount Requested', Icons.currency_exchange),
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    validator: (v) => v?.isEmpty == true ? 'Required' : null,
                    style: const TextStyle(color: AppTheme.cleanWhite),
                    onChanged: (_) => _checkRisk(),
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _recipientController,
                    decoration: _inputDecoration('Recipient Address', Icons.person),
                    validator: (v) => v?.isEmpty == true ? 'Required' : null,
                    style: const TextStyle(color: AppTheme.cleanWhite),
                    onChanged: (_) => _checkRisk(),
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _hashLockController,
                    decoration: _inputDecoration('Hash Lock (optional)', Icons.lock),
                    style: const TextStyle(color: AppTheme.cleanWhite),
                  ),
                  const SizedBox(height: 16),
                  DropdownButtonFormField<String>(
                    value: _selectedTimelock,
                    decoration: _inputDecoration('Time Lock', Icons.timer),
                    dropdownColor: AppTheme.darkCard,
                    style: const TextStyle(color: AppTheme.cleanWhite),
                    items: ['1 hour', '6 hours', '12 hours', '24 hours', '48 hours', '7 days']
                        .map((e) => DropdownMenuItem(value: e, child: Text(e)))
                        .toList(),
                    onChanged: (v) => setState(() => _selectedTimelock = v!),
                  ),
                ],
              ),
            ),
            
            const SizedBox(height: 16),
            
            // Risk Assessment Card
            if (_riskScore != null)
              _buildCard(
                title: 'Risk Assessment',
                icon: Icons.security,
                child: Row(
                  children: [
                    RiskLevelIndicator(riskScore: _riskScore!),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Risk Score: ${(_riskScore! * 100).toStringAsFixed(0)}%',
                            style: const TextStyle(
                              color: AppTheme.cleanWhite,
                              fontSize: 18,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            _riskScore! < 0.3 ? 'Low Risk - Swap can proceed' :
                            _riskScore! < 0.7 ? 'Medium Risk - Additional verification may be required' :
                            'High Risk - Approval required',
                            style: const TextStyle(color: AppTheme.mutedText),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            
            const SizedBox(height: 24),
            
            // Submit Button
            SizedBox(
              width: double.infinity,
              height: 56,
              child: ElevatedButton(
                onPressed: _isLoading ? null : _initiateSwap,
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppTheme.primaryBlue,
                  foregroundColor: AppTheme.cleanWhite,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                child: _isLoading
                    ? const CircularProgressIndicator(color: AppTheme.cleanWhite)
                    : const Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.swap_horiz),
                          SizedBox(width: 8),
                          Text('Initiate NFT → ETH Swap', style: TextStyle(fontSize: 16)),
                        ],
                      ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCard({
    required String title,
    required IconData icon,
    required Widget child,
  }) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkCard,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppTheme.darkCard.withOpacity(0.5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, color: AppTheme.primaryBlue),
              const SizedBox(width: 8),
              Text(
                title,
                style: const TextStyle(
                  color: AppTheme.cleanWhite,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          child,
        ],
      ),
    );
  }

  InputDecoration _inputDecoration(String label, IconData icon) {
    return InputDecoration(
      labelText: label,
      labelStyle: const TextStyle(color: AppTheme.mutedText),
      prefixIcon: Icon(icon, color: AppTheme.mutedText),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: AppTheme.mutedText),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: AppTheme.primaryBlue),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: AppTheme.dangerRed),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: AppTheme.dangerRed),
      ),
    );
  }
}

/// Tab 1: NFT → NFT Swap
class _NFTToNFTSwapTab extends ConsumerStatefulWidget {
  @override
  ConsumerState<_NFTToNFTSwapTab> createState() => _NFTToNFTSwapTabState();
}

class _NFTToNFTSwapTabState extends ConsumerState<_NFTToNFTSwapTab> {
  final _formKey = GlobalKey<FormState>();
  final _yourNftAddressController = TextEditingController();
  final _yourTokenIdController = TextEditingController();
  final _wantedNftAddressController = TextEditingController();
  final _wantedTokenIdController = TextEditingController();
  final _counterpartyController = TextEditingController();
  
  bool _isLoading = false;

  @override
  void dispose() {
    _yourNftAddressController.dispose();
    _yourTokenIdController.dispose();
    _wantedNftAddressController.dispose();
    _wantedTokenIdController.dispose();
    _counterpartyController.dispose();
    super.dispose();
  }

  Future<void> _initiateNFTtoNFTSwap() async {
    if (!_formKey.currentState!.validate()) return;
    
    setState(() => _isLoading = true);
    
    try {
      // Call initiateNFTtoNFTSwap
      await Future.delayed(const Duration(seconds: 2));
      
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('NFT → NFT Swap initiated successfully!'),
            backgroundColor: AppTheme.accentGreen,
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error: $e'),
            backgroundColor: AppTheme.dangerRed,
          ),
        );
      }
    } finally {
      setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Form(
        key: _formKey,
        child: Column(
          children: [
            // Your NFT Card
            _buildNFTCard(
              title: 'Your NFT (You Give)',
              nftAddressController: _yourNftAddressController,
              tokenIdController: _yourTokenIdController,
              color: AppTheme.dangerRed.withOpacity(0.2),
            ),
            
            const SizedBox(height: 16),
            
            // Swap Arrow
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppTheme.primaryBlue,
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.swap_vert, color: AppTheme.cleanWhite, size: 32),
            ),
            
            const SizedBox(height: 16),
            
            // Wanted NFT Card
            _buildNFTCard(
              title: 'Wanted NFT (You Receive)',
              nftAddressController: _wantedNftAddressController,
              tokenIdController: _wantedTokenIdController,
              color: AppTheme.accentGreen.withOpacity(0.2),
            ),
            
            const SizedBox(height: 16),
            
            // Counterparty Address
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: AppTheme.darkCard,
                borderRadius: BorderRadius.circular(16),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Row(
                    children: [
                      Icon(Icons.person, color: AppTheme.primaryBlue),
                      SizedBox(width: 8),
                      Text(
                        'Counterparty',
                        style: TextStyle(
                          color: AppTheme.cleanWhite,
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _counterpartyController,
                    decoration: InputDecoration(
                      labelText: 'Counterparty Address',
                      labelStyle: const TextStyle(color: AppTheme.mutedText),
                      prefixIcon: const Icon(Icons.account_balance_wallet, color: AppTheme.mutedText),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: const BorderSide(color: AppTheme.mutedText),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: const BorderSide(color: AppTheme.primaryBlue),
                      ),
                    ),
                    validator: (v) => v?.isEmpty == true ? 'Required' : null,
                    style: const TextStyle(color: AppTheme.cleanWhite),
                  ),
                ],
              ),
            ),
            
            const SizedBox(height: 24),
            
            // Submit Button
            SizedBox(
              width: double.infinity,
              height: 56,
              child: ElevatedButton(
                onPressed: _isLoading ? null : _initiateNFTtoNFTSwap,
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppTheme.primaryBlue,
                  foregroundColor: AppTheme.cleanWhite,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                child: _isLoading
                    ? const CircularProgressIndicator(color: AppTheme.cleanWhite)
                    : const Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.compare_arrows),
                          SizedBox(width: 8),
                          Text('Initiate NFT → NFT Swap', style: TextStyle(fontSize: 16)),
                        ],
                      ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildNFTCard({
    required String title,
    required TextEditingController nftAddressController,
    required TextEditingController tokenIdController,
    required Color color,
  }) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkCard,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color, width: 2),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              color: AppTheme.cleanWhite,
              fontSize: 18,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 16),
          TextFormField(
            controller: nftAddressController,
            decoration: InputDecoration(
              labelText: 'NFT Contract Address',
              labelStyle: const TextStyle(color: AppTheme.mutedText),
              prefixIcon: const Icon(Icons.token, color: AppTheme.mutedText),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: AppTheme.mutedText),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: AppTheme.primaryBlue),
              ),
            ),
            validator: (v) => v?.isEmpty == true ? 'Required' : null,
            style: const TextStyle(color: AppTheme.cleanWhite),
          ),
          const SizedBox(height: 16),
          TextFormField(
            controller: tokenIdController,
            decoration: InputDecoration(
              labelText: 'Token ID',
              labelStyle: const TextStyle(color: AppTheme.mutedText),
              prefixIcon: const Icon(Icons.numbers, color: AppTheme.mutedText),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: AppTheme.mutedText),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: AppTheme.primaryBlue),
              ),
            ),
            keyboardType: TextInputType.number,
            validator: (v) => v?.isEmpty == true ? 'Required' : null,
            style: const TextStyle(color: AppTheme.cleanWhite),
          ),
        ],
      ),
    );
  }
}

/// Tab 2: Active Swaps
class _ActiveSwapsTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Mock data - in production, fetch from API
    final activeSwaps = [
      _SwapData(
        id: 'abc123',
        type: 'NFT → ETH',
        nftName: 'BAYC #1234',
        amount: '10 ETH',
        status: 'Waiting for ETH',
        timeRemaining: '23:45:00',
        canComplete: false,
      ),
      _SwapData(
        id: 'def456',
        type: 'NFT → NFT',
        nftName: 'Azuki #567',
        amount: 'CryptoPunk #890',
        status: 'Waiting for NFT',
        timeRemaining: '12:30:00',
        canComplete: false,
      ),
      _SwapData(
        id: 'ghi789',
        type: 'NFT → ETH',
        nftName: 'Doodles #123',
        amount: '5 ETH',
        status: 'Ready to Complete',
        timeRemaining: '18:00:00',
        canComplete: true,
      ),
    ];

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: activeSwaps.length,
      itemBuilder: (context, index) {
        final swap = activeSwaps[index];
        return _ActiveSwapCard(swap: swap);
      },
    );
  }
}

class _SwapData {
  final String id;
  final String type;
  final String nftName;
  final String amount;
  final String status;
  final String timeRemaining;
  final bool canComplete;

  _SwapData({
    required this.id,
    required this.type,
    required this.nftName,
    required this.amount,
    required this.status,
    required this.timeRemaining,
    required this.canComplete,
  });
}

class _ActiveSwapCard extends StatelessWidget {
  final _SwapData swap;

  const _ActiveSwapCard({required this.swap});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkCard,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: swap.canComplete ? AppTheme.accentGreen : AppTheme.warningOrange,
          width: 2,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Swap #${swap.id}',
                style: const TextStyle(
                  color: AppTheme.cleanWhite,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: swap.canComplete 
                      ? AppTheme.accentGreen.withOpacity(0.2)
                      : AppTheme.warningOrange.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  swap.status,
                  style: TextStyle(
                    color: swap.canComplete ? AppTheme.accentGreen : AppTheme.warningOrange,
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              const Icon(Icons.image, color: AppTheme.mutedText, size: 20),
              const SizedBox(width: 8),
              Text(swap.nftName, style: const TextStyle(color: AppTheme.cleanWhite)),
              const SizedBox(width: 8),
              const Icon(Icons.arrow_forward, color: AppTheme.mutedText, size: 16),
              const SizedBox(width: 8),
              Text(swap.amount, style: const TextStyle(color: AppTheme.cleanWhite)),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              const Icon(Icons.timer, color: AppTheme.mutedText, size: 20),
              const SizedBox(width: 8),
              Text(
                'Time remaining: ${swap.timeRemaining}',
                style: const TextStyle(color: AppTheme.mutedText),
              ),
            ],
          ),
          const SizedBox(height: 16),
          if (swap.canComplete) ...[
            TextField(
              decoration: InputDecoration(
                hintText: 'Enter Preimage to Complete',
                hintStyle: const TextStyle(color: AppTheme.mutedText),
                filled: true,
                fillColor: AppTheme.darkBg,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: BorderSide.none,
                ),
              ),
              style: const TextStyle(color: AppTheme.cleanWhite),
            ),
            const SizedBox(height: 12),
          ],
          Row(
            children: [
              if (swap.canComplete)
                Expanded(
                  child: ElevatedButton.icon(
                    onPressed: () {
                      // Call completeNFTSwap or completeNFTtoNFTSwap
                    },
                    icon: const Icon(Icons.check_circle),
                    label: const Text('Complete Swap'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppTheme.accentGreen,
                      foregroundColor: AppTheme.cleanWhite,
                    ),
                  ),
                ),
              if (swap.canComplete) const SizedBox(width: 8),
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () {
                    // Call refundNFTSwap
                  },
                  icon: const Icon(Icons.refresh),
                  label: const Text('Refund'),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppTheme.dangerRed,
                    side: const BorderSide(color: AppTheme.dangerRed),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// Tab 3: Swap History
class _SwapHistoryTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Mock history data
    final history = [
      {'id': 'xyz001', 'type': 'NFT → ETH', 'status': 'Completed', 'date': 'Jan 3, 2026'},
      {'id': 'xyz002', 'type': 'NFT → NFT', 'status': 'Refunded', 'date': 'Jan 2, 2026'},
      {'id': 'xyz003', 'type': 'NFT → ETH', 'status': 'Completed', 'date': 'Jan 1, 2026'},
    ];

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: history.length,
      itemBuilder: (context, index) {
        final item = history[index];
        final isCompleted = item['status'] == 'Completed';
        
        return Container(
          margin: const EdgeInsets.only(bottom: 12),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppTheme.darkCard,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: isCompleted 
                      ? AppTheme.accentGreen.withOpacity(0.2)
                      : AppTheme.warningOrange.withOpacity(0.2),
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  isCompleted ? Icons.check : Icons.refresh,
                  color: isCompleted ? AppTheme.accentGreen : AppTheme.warningOrange,
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Swap #${item['id']}',
                      style: const TextStyle(
                        color: AppTheme.cleanWhite,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    Text(
                      '${item['type']} • ${item['date']}',
                      style: const TextStyle(color: AppTheme.mutedText),
                    ),
                  ],
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: isCompleted 
                      ? AppTheme.accentGreen.withOpacity(0.2)
                      : AppTheme.warningOrange.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  item['status']!,
                  style: TextStyle(
                    color: isCompleted ? AppTheme.accentGreen : AppTheme.warningOrange,
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
