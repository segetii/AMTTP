import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../../core/theme/app_theme.dart';
// Web-specific imports for file selection
import 'dart:html' as html if (dart.library.io) 'dart:io';
import 'dart:async';

/// Dispute Center Page - Covers AMTTPDisputeResolver.sol functionality
/// Functions covered:
/// - challengeTransaction()
/// - submitEvidence()
/// - requestAppeal()
/// - raiseDispute() (from AMTTPCore)
class DisputeCenterPage extends ConsumerStatefulWidget {
  const DisputeCenterPage({super.key});

  @override
  ConsumerState<DisputeCenterPage> createState() => _DisputeCenterPageState();
}

class _DisputeCenterPageState extends ConsumerState<DisputeCenterPage>
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
        title: const Text('Dispute Center'),
        backgroundColor: AppTheme.darkCard,
        foregroundColor: AppTheme.cleanWhite,
        elevation: 0,
        bottom: TabBar(
          controller: _tabController,
          isScrollable: true,
          indicatorColor: AppTheme.primaryBlue,
          tabs: const [
            Tab(text: 'Create Dispute', icon: Icon(Icons.add_circle)),
            Tab(text: 'Active Disputes', icon: Icon(Icons.pending)),
            Tab(text: 'Submit Evidence', icon: Icon(Icons.attach_file)),
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
            _CreateDisputeTab(),
            _ActiveDisputesTab(),
            _SubmitEvidenceTab(),
            _DisputeHistoryTab(),
          ],
        ),
      ),
    );
  }
}

/// Tab 0: Create Dispute
class _CreateDisputeTab extends ConsumerStatefulWidget {
  @override
  ConsumerState<_CreateDisputeTab> createState() => _CreateDisputeTabState();
}

class _CreateDisputeTabState extends ConsumerState<_CreateDisputeTab> {
  final _formKey = GlobalKey<FormState>();
  String? _selectedTxId;
  String _selectedReason = 'goods_not_received';
  final _evidenceController = TextEditingController();
  bool _isLoading = false;
  int _currentStep = 0;

  // Mock transaction data
  final _disputeableTransactions = [
    {'txId': '0xabc123...def456', 'amount': '1.5 ETH', 'to': '0x742d...', 'date': 'Jan 4, 2026'},
    {'txId': '0xdef456...ghi789', 'amount': '0.8 ETH', 'to': '0x8ba1...', 'date': 'Jan 3, 2026'},
    {'txId': '0xghi789...jkl012', 'amount': '2.0 ETH', 'to': '0xAb58...', 'date': 'Jan 2, 2026'},
  ];

  final _disputeReasons = {
    'goods_not_received': 'Goods/Services Not Received',
    'not_as_described': 'Goods/Services Not As Described',
    'unauthorized': 'Unauthorized Transaction',
    'other': 'Other',
  };

  @override
  void dispose() {
    _evidenceController.dispose();
    super.dispose();
  }

  Future<void> _challengeTransaction() async {
    if (_selectedTxId == null) return;
    
    setState(() => _isLoading = true);
    
    try {
      // Call challengeTransaction with arbitration fee
      await Future.delayed(const Duration(seconds: 2));
      
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Dispute created successfully!'),
            backgroundColor: AppTheme.accentGreen,
          ),
        );
        setState(() {
          _selectedTxId = null;
          _currentStep = 0;
        });
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
            // Stepper Progress
            _buildStepIndicator(),
            
            const SizedBox(height: 24),
            
            // Step 1: Select Transaction
            if (_currentStep == 0)
              _buildStep1SelectTransaction(),
            
            // Step 2: Dispute Details
            if (_currentStep == 1)
              _buildStep2DisputeDetails(),
            
            // Step 3: Arbitration Fee
            if (_currentStep == 2)
              _buildStep3ArbitrationFee(),
          ],
        ),
      ),
    );
  }

  Widget _buildStepIndicator() {
    return Row(
      children: [
        _buildStepCircle(0, 'Select TX'),
        Expanded(child: Container(height: 2, color: _currentStep > 0 ? AppTheme.primaryBlue : AppTheme.mutedText)),
        _buildStepCircle(1, 'Details'),
        Expanded(child: Container(height: 2, color: _currentStep > 1 ? AppTheme.primaryBlue : AppTheme.mutedText)),
        _buildStepCircle(2, 'Confirm'),
      ],
    );
  }

  Widget _buildStepCircle(int step, String label) {
    final isActive = _currentStep >= step;
    return Column(
      children: [
        Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: isActive ? AppTheme.primaryBlue : AppTheme.darkCard,
            shape: BoxShape.circle,
            border: Border.all(color: isActive ? AppTheme.primaryBlue : AppTheme.mutedText),
          ),
          child: Center(
            child: isActive && _currentStep > step
                ? const Icon(Icons.check, color: AppTheme.cleanWhite, size: 20)
                : Text(
                    '${step + 1}',
                    style: TextStyle(
                      color: isActive ? AppTheme.cleanWhite : AppTheme.mutedText,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
          ),
        ),
        const SizedBox(height: 4),
        Text(
          label,
          style: TextStyle(
            color: isActive ? AppTheme.cleanWhite : AppTheme.mutedText,
            fontSize: 12,
          ),
        ),
      ],
    );
  }

  Widget _buildStep1SelectTransaction() {
    return _buildCard(
      title: 'Step 1: Select Transaction',
      icon: Icons.receipt_long,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Select a transaction to dispute:',
            style: TextStyle(color: AppTheme.mutedText),
          ),
          const SizedBox(height: 16),
          ..._disputeableTransactions.map((tx) => _buildTransactionTile(tx)),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: _selectedTxId != null
                  ? () => setState(() => _currentStep = 1)
                  : null,
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.primaryBlue,
                foregroundColor: AppTheme.cleanWhite,
                padding: const EdgeInsets.symmetric(vertical: 16),
              ),
              child: const Text('Continue'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTransactionTile(Map<String, String> tx) {
    final isSelected = _selectedTxId == tx['txId'];
    return GestureDetector(
      onTap: () => setState(() => _selectedTxId = tx['txId']),
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: isSelected ? AppTheme.primaryBlue.withOpacity(0.2) : AppTheme.darkBg,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isSelected ? AppTheme.primaryBlue : Colors.transparent,
            width: 2,
          ),
        ),
        child: Row(
          children: [
            Radio<String>(
              value: tx['txId']!,
              groupValue: _selectedTxId,
              onChanged: (v) => setState(() => _selectedTxId = v),
              activeColor: AppTheme.primaryBlue,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    tx['txId']!,
                    style: const TextStyle(
                      color: AppTheme.cleanWhite,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  Text(
                    '${tx['amount']} to ${tx['to']} • ${tx['date']}',
                    style: const TextStyle(color: AppTheme.mutedText, fontSize: 12),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStep2DisputeDetails() {
    return _buildCard(
      title: 'Step 2: Dispute Details',
      icon: Icons.description,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Reason for Dispute:',
            style: TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 12),
          ..._disputeReasons.entries.map((entry) => RadioListTile<String>(
            title: Text(entry.value, style: const TextStyle(color: AppTheme.cleanWhite)),
            value: entry.key,
            groupValue: _selectedReason,
            onChanged: (v) => setState(() => _selectedReason = v!),
            activeColor: AppTheme.primaryBlue,
            contentPadding: EdgeInsets.zero,
          )),
          const SizedBox(height: 16),
          const Text(
            'Evidence Description:',
            style: TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          TextFormField(
            controller: _evidenceController,
            maxLines: 4,
            decoration: InputDecoration(
              hintText: 'Describe the issue and provide initial evidence...',
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
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: () => setState(() => _currentStep = 0),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppTheme.mutedText,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                  ),
                  child: const Text('Back'),
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: ElevatedButton(
                  onPressed: () => setState(() => _currentStep = 2),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppTheme.primaryBlue,
                    foregroundColor: AppTheme.cleanWhite,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                  ),
                  child: const Text('Continue'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildStep3ArbitrationFee() {
    return _buildCard(
      title: 'Step 3: Arbitration Fee',
      icon: Icons.gavel,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppTheme.warningOrange.withOpacity(0.2),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppTheme.warningOrange),
            ),
            child: Row(
              children: [
                const Icon(Icons.warning, color: AppTheme.warningOrange),
                const SizedBox(width: 12),
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Arbitration Fee Required: 0.1 ETH',
                        style: TextStyle(
                          color: AppTheme.cleanWhite,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      SizedBox(height: 4),
                      Text(
                        'This fee will be refunded if you win the dispute.',
                        style: TextStyle(color: AppTheme.mutedText, fontSize: 12),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          _buildInfoRow('Kleros Arbitration Court', 'General Court'),
          _buildInfoRow('Expected Resolution Time', '3-7 days'),
          _buildInfoRow('Number of Jurors', '3'),
          const SizedBox(height: 24),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: () => setState(() => _currentStep = 1),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppTheme.mutedText,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                  ),
                  child: const Text('Back'),
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                flex: 2,
                child: ElevatedButton.icon(
                  onPressed: _isLoading ? null : _challengeTransaction,
                  icon: _isLoading
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: AppTheme.cleanWhite,
                          ),
                        )
                      : const Icon(Icons.gavel),
                  label: const Text('Challenge Transaction'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppTheme.dangerRed,
                    foregroundColor: AppTheme.cleanWhite,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildInfoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(color: AppTheme.mutedText)),
          Text(value, style: const TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold)),
        ],
      ),
    );
  }

  Widget _buildCard({required String title, required IconData icon, required Widget child}) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkCard,
        borderRadius: BorderRadius.circular(16),
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
}

/// Tab 1: Active Disputes
class _ActiveDisputesTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Mock active disputes (toggle to empty list to see empty state)
    final disputes = <_DisputeData>[
      _DisputeData(
        id: '001',
        txId: '0xabc123...def456',
        status: 'evidence_phase',
        statusLabel: 'Evidence Phase',
        deadline: '2 days 14 hours',
        canAppeal: false,
      ),
      _DisputeData(
        id: '002',
        txId: '0xdef456...ghi789',
        status: 'ruling_issued',
        statusLabel: 'Ruling Issued',
        deadline: '5 days (appeal window)',
        canAppeal: true,
        ruling: 'In Your Favor',
      ),
    ];

    if (disputes.isEmpty) {
      return _buildEmptyState();
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: disputes.length,
      itemBuilder: (context, index) => _DisputeCard(dispute: disputes[index]),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.gavel_rounded,
            size: 72,
            color: AppTheme.mutedText.withOpacity(0.5),
          ),
          const SizedBox(height: 20),
          const Text(
            'No Active Disputes',
            style: TextStyle(
              color: AppTheme.cleanWhite,
              fontSize: 20,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'All clear! You have no disputes in progress.',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppTheme.mutedText.withOpacity(0.7),
              fontSize: 14,
            ),
          ),
        ],
      ),
    );
  }
}

class _DisputeData {
  final String id;
  final String txId;
  final String status;
  final String statusLabel;
  final String deadline;
  final bool canAppeal;
  final String? ruling;

  _DisputeData({
    required this.id,
    required this.txId,
    required this.status,
    required this.statusLabel,
    required this.deadline,
    required this.canAppeal,
    this.ruling,
  });
}

class _DisputeCard extends StatelessWidget {
  final _DisputeData dispute;

  const _DisputeCard({required this.dispute});

  Color get _statusColor {
    switch (dispute.status) {
      case 'evidence_phase':
        return AppTheme.warningOrange;
      case 'voting':
        return AppTheme.primaryBlue;
      case 'ruling_issued':
        return AppTheme.accentGreen;
      default:
        return AppTheme.mutedText;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkCard,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: _statusColor.withOpacity(0.5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Dispute #${dispute.id}',
                style: const TextStyle(
                  color: AppTheme.cleanWhite,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: _statusColor.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  dispute.statusLabel,
                  style: TextStyle(
                    color: _statusColor,
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            'TX: ${dispute.txId}',
            style: const TextStyle(color: AppTheme.mutedText),
          ),
          const SizedBox(height: 8),
          
          // Progress Bar
          _buildProgressBar(),
          
          const SizedBox(height: 12),
          Row(
            children: [
              const Icon(Icons.timer, color: AppTheme.mutedText, size: 16),
              const SizedBox(width: 8),
              Text(
                'Deadline: ${dispute.deadline}',
                style: const TextStyle(color: AppTheme.mutedText),
              ),
            ],
          ),
          if (dispute.ruling != null) ...[
            const SizedBox(height: 8),
            Row(
              children: [
                const Icon(Icons.gavel, color: AppTheme.accentGreen, size: 16),
                const SizedBox(width: 8),
                Text(
                  'Ruling: ${dispute.ruling}',
                  style: const TextStyle(color: AppTheme.accentGreen, fontWeight: FontWeight.bold),
                ),
              ],
            ),
          ],
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () {
                    context.go('/dispute/${dispute.id}');
                  },
                  icon: const Icon(Icons.visibility),
                  label: const Text('View Details'),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppTheme.primaryBlue,
                    side: const BorderSide(color: AppTheme.primaryBlue),
                  ),
                ),
              ),
              if (dispute.status == 'evidence_phase') ...[
                const SizedBox(width: 8),
                Expanded(
                  child: ElevatedButton.icon(
                    onPressed: () {
                      // Navigate to submit evidence
                    },
                    icon: const Icon(Icons.attach_file),
                    label: const Text('Add Evidence'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppTheme.primaryBlue,
                      foregroundColor: AppTheme.cleanWhite,
                    ),
                  ),
                ),
              ],
              if (dispute.canAppeal) ...[
                const SizedBox(width: 8),
                Expanded(
                  child: ElevatedButton.icon(
                    onPressed: () {
                      // Call requestAppeal
                    },
                    icon: const Icon(Icons.gavel),
                    label: const Text('Appeal'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppTheme.warningOrange,
                      foregroundColor: AppTheme.cleanWhite,
                    ),
                  ),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildProgressBar() {
    final progress = dispute.status == 'evidence_phase' ? 0.3 :
                     dispute.status == 'voting' ? 0.6 :
                     dispute.status == 'ruling_issued' ? 0.9 : 0.0;
    
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(
            value: progress,
            backgroundColor: AppTheme.darkBg,
            valueColor: AlwaysStoppedAnimation<Color>(_statusColor),
            minHeight: 8,
          ),
        ),
        const SizedBox(height: 8),
        const Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('Created', style: TextStyle(color: AppTheme.mutedText, fontSize: 10)),
            Text('Evidence', style: TextStyle(color: AppTheme.mutedText, fontSize: 10)),
            Text('Voting', style: TextStyle(color: AppTheme.mutedText, fontSize: 10)),
            Text('Ruling', style: TextStyle(color: AppTheme.mutedText, fontSize: 10)),
            Text('Final', style: TextStyle(color: AppTheme.mutedText, fontSize: 10)),
          ],
        ),
      ],
    );
  }
}

/// Tab 2: Submit Evidence
class _SubmitEvidenceTab extends ConsumerStatefulWidget {
  @override
  ConsumerState<_SubmitEvidenceTab> createState() => _SubmitEvidenceTabState();
}

class _SubmitEvidenceTabState extends ConsumerState<_SubmitEvidenceTab> {
  final _formKey = GlobalKey<FormState>();
  String? _selectedDisputeId;
  String _evidenceType = 'text';
  final _contentController = TextEditingController();
  final _descriptionController = TextEditingController();
  bool _isLoading = false;
  String? _selectedFileName;
  List<int>? _selectedFileBytes;

  final _activeDisputes = ['001', '002'];

  @override
  void dispose() {
    _contentController.dispose();
    _descriptionController.dispose();
    super.dispose();
  }
  
  Future<void> _pickFile() async {
    if (kIsWeb) {
      // Web file picker using HTML input element
      final uploadInput = html.FileUploadInputElement()..accept = '*/*';
      uploadInput.click();
      
      await uploadInput.onChange.first;
      
      if (uploadInput.files!.isNotEmpty) {
        final file = uploadInput.files!.first;
        final reader = html.FileReader();
        
        reader.readAsArrayBuffer(file);
        await reader.onLoad.first;
        
        setState(() {
          _selectedFileName = file.name;
          _selectedFileBytes = (reader.result as List<int>);
          _contentController.text = file.name;
        });
        
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('File selected: ${file.name}'),
              backgroundColor: AppTheme.primaryBlue,
            ),
          );
        }
      }
    } else {
      // For non-web platforms, show info dialog
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('File picker available on web platform'),
            backgroundColor: AppTheme.warningOrange,
          ),
        );
      }
    }
  }

  Future<void> _submitEvidence() async {
    if (!_formKey.currentState!.validate()) return;
    
    setState(() => _isLoading = true);
    
    try {
      // In production, this would upload to IPFS or backend storage
      await Future.delayed(const Duration(seconds: 2));
      
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Evidence submitted successfully!'),
            backgroundColor: AppTheme.accentGreen,
          ),
        );
        _contentController.clear();
        _descriptionController.clear();
        setState(() {
          _selectedFileName = null;
          _selectedFileBytes = null;
        });
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
                      Icon(Icons.attach_file, color: AppTheme.primaryBlue),
                      SizedBox(width: 8),
                      Text(
                        'Submit New Evidence',
                        style: TextStyle(
                          color: AppTheme.cleanWhite,
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  
                  // Select Dispute
                  DropdownButtonFormField<String>(
                    value: _selectedDisputeId,
                    decoration: InputDecoration(
                      labelText: 'Select Dispute',
                      labelStyle: const TextStyle(color: AppTheme.mutedText),
                      filled: true,
                      fillColor: AppTheme.darkBg,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: BorderSide.none,
                      ),
                    ),
                    dropdownColor: AppTheme.darkCard,
                    style: const TextStyle(color: AppTheme.cleanWhite),
                    items: _activeDisputes
                        .map((id) => DropdownMenuItem(
                              value: id,
                              child: Text('Dispute #$id'),
                            ))
                        .toList(),
                    onChanged: (v) => setState(() => _selectedDisputeId = v),
                    validator: (v) => v == null ? 'Required' : null,
                  ),
                  const SizedBox(height: 16),
                  
                  // Evidence Type
                  const Text(
                    'Evidence Type:',
                    style: TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      _buildTypeChip('text', 'Text', Icons.text_fields),
                      const SizedBox(width: 8),
                      _buildTypeChip('file', 'File', Icons.insert_drive_file),
                      const SizedBox(width: 8),
                      _buildTypeChip('ipfs', 'IPFS Link', Icons.link),
                    ],
                  ),
                  const SizedBox(height: 16),
                  
                  // Content - Show file picker button for file type
                  if (_evidenceType == 'file') ...[
                    InkWell(
                      onTap: _pickFile,
                      child: Container(
                        padding: const EdgeInsets.all(20),
                        decoration: BoxDecoration(
                          color: AppTheme.darkBg,
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                            color: _selectedFileName != null 
                                ? AppTheme.accentGreen 
                                : AppTheme.mutedText.withValues(alpha: 0.3),
                            style: BorderStyle.solid,
                          ),
                        ),
                        child: Column(
                          children: [
                            Icon(
                              _selectedFileName != null 
                                  ? Icons.check_circle 
                                  : Icons.cloud_upload,
                              size: 48,
                              color: _selectedFileName != null 
                                  ? AppTheme.accentGreen 
                                  : AppTheme.mutedText,
                            ),
                            const SizedBox(height: 12),
                            Text(
                              _selectedFileName ?? 'Click to select a file',
                              style: TextStyle(
                                color: _selectedFileName != null 
                                    ? AppTheme.cleanWhite 
                                    : AppTheme.mutedText,
                                fontWeight: _selectedFileName != null 
                                    ? FontWeight.bold 
                                    : FontWeight.normal,
                              ),
                              textAlign: TextAlign.center,
                            ),
                            if (_selectedFileName != null) ...[
                              const SizedBox(height: 8),
                              Text(
                                'Click to change file',
                                style: TextStyle(
                                  color: AppTheme.mutedText,
                                  fontSize: 12,
                                ),
                              ),
                            ],
                          ],
                        ),
                      ),
                    ),
                  ] else ...[
                    TextFormField(
                      controller: _contentController,
                      maxLines: _evidenceType == 'text' ? 4 : 1,
                      decoration: InputDecoration(
                        labelText: _evidenceType == 'text'
                            ? 'Evidence Content'
                            : 'IPFS URI',
                        labelStyle: const TextStyle(color: AppTheme.mutedText),
                        filled: true,
                        fillColor: AppTheme.darkBg,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: BorderSide.none,
                        ),
                      ),
                      style: const TextStyle(color: AppTheme.cleanWhite),
                      validator: (v) => v?.isEmpty == true ? 'Required' : null,
                    ),
                  ],
                  const SizedBox(height: 16),
                  
                  // Description
                  TextFormField(
                    controller: _descriptionController,
                    decoration: InputDecoration(
                      labelText: 'Description',
                      labelStyle: const TextStyle(color: AppTheme.mutedText),
                      filled: true,
                      fillColor: AppTheme.darkBg,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: BorderSide.none,
                      ),
                    ),
                    style: const TextStyle(color: AppTheme.cleanWhite),
                  ),
                  const SizedBox(height: 24),
                  
                  // Submit Button
                  SizedBox(
                    width: double.infinity,
                    height: 56,
                    child: ElevatedButton.icon(
                      onPressed: _isLoading ? null : _submitEvidence,
                      icon: _isLoading
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: AppTheme.cleanWhite,
                              ),
                            )
                          : const Icon(Icons.upload),
                      label: const Text('Submit Evidence'),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppTheme.primaryBlue,
                        foregroundColor: AppTheme.cleanWhite,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTypeChip(String type, String label, IconData icon) {
    final isSelected = _evidenceType == type;
    return GestureDetector(
      onTap: () => setState(() => _evidenceType = type),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: isSelected ? AppTheme.primaryBlue : AppTheme.darkBg,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isSelected ? AppTheme.primaryBlue : AppTheme.mutedText,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 16, color: isSelected ? AppTheme.cleanWhite : AppTheme.mutedText),
            const SizedBox(width: 4),
            Text(
              label,
              style: TextStyle(
                color: isSelected ? AppTheme.cleanWhite : AppTheme.mutedText,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Tab 3: Dispute History
class _DisputeHistoryTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final history = [
      {'id': '000', 'status': 'Resolved - Won', 'date': 'Dec 15, 2025', 'amount': '2.5 ETH'},
      {'id': '099', 'status': 'Resolved - Lost', 'date': 'Dec 1, 2025', 'amount': '1.0 ETH'},
    ];

    if (history.isEmpty) {
      return _buildEmptyState();
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: history.length,
      itemBuilder: (context, index) {
        final item = history[index];
        final won = item['status']!.contains('Won');
        
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
                  color: won
                      ? AppTheme.accentGreen.withOpacity(0.2)
                      : AppTheme.dangerRed.withOpacity(0.2),
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  won ? Icons.check : Icons.close,
                  color: won ? AppTheme.accentGreen : AppTheme.dangerRed,
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Dispute #${item['id']}',
                      style: const TextStyle(
                        color: AppTheme.cleanWhite,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    Text(
                      '${item['amount']} • ${item['date']}',
                      style: const TextStyle(color: AppTheme.mutedText),
                    ),
                  ],
                ),
              ),
              Text(
                item['status']!,
                style: TextStyle(
                  color: won ? AppTheme.accentGreen : AppTheme.dangerRed,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.history_rounded,
            size: 72,
            color: AppTheme.mutedText.withOpacity(0.5),
          ),
          const SizedBox(height: 20),
          const Text(
            'No Dispute History',
            style: TextStyle(
              color: AppTheme.cleanWhite,
              fontSize: 20,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Your resolved disputes will appear here.',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppTheme.mutedText.withOpacity(0.7),
              fontSize: 14,
            ),
          ),
        ],
      ),
    );
  }
}
