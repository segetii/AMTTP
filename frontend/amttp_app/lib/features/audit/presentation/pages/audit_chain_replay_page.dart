import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/security/ui_integrity_service.dart';
import '../../../../core/theme/app_theme.dart';

/// Snapshot for audit replay
class AuditSnapshot {
  final String snapshotId;
  final DateTime timestamp;
  final String actorRole;
  final String actorId;
  final String actionContext;
  final String? transactionId;
  final Map<String, dynamic> displayedData;
  final String uiHash;
  final String? prevHash;
  final bool isVerified;

  const AuditSnapshot({
    required this.snapshotId,
    required this.timestamp,
    required this.actorRole,
    required this.actorId,
    required this.actionContext,
    this.transactionId,
    required this.displayedData,
    required this.uiHash,
    this.prevHash,
    this.isVerified = false,
  });

  factory AuditSnapshot.fromJson(Map<String, dynamic> json) => AuditSnapshot(
    snapshotId: json['snapshot_id'] ?? json['snapshotId'],
    timestamp: DateTime.parse(json['timestamp']),
    actorRole: json['actor_role'] ?? json['actorRole'],
    actorId: json['actor_id'] ?? json['actorId'],
    actionContext: json['action_context'] ?? json['actionContext'],
    transactionId: json['transaction_id'] ?? json['transactionId'],
    displayedData: json['displayed_data'] ?? json['displayedData'] ?? {},
    uiHash: json['ui_hash'] ?? json['uiHash'],
    prevHash: json['prev_hash'] ?? json['prevHash'],
  );
}

/// Chain verification result
class ChainVerificationResult {
  final bool isValid;
  final int totalSnapshots;
  final int verifiedSnapshots;
  final List<String> errors;
  final DateTime? verifiedAt;

  const ChainVerificationResult({
    required this.isValid,
    required this.totalSnapshots,
    required this.verifiedSnapshots,
    this.errors = const [],
    this.verifiedAt,
  });
}

/// Audit Chain Replay Tool
/// 
/// Allows auditors (R6) to:
/// - Browse historical snapshots
/// - Verify hash chain integrity
/// - Replay UI states
/// - Export for compliance

class AuditChainReplayTool extends ConsumerStatefulWidget {
  final List<AuditSnapshot>? preloadedSnapshots;
  final String? transactionId;

  const AuditChainReplayTool({
    super.key,
    this.preloadedSnapshots,
    this.transactionId,
  });

  @override
  ConsumerState<AuditChainReplayTool> createState() => _AuditChainReplayToolState();
}

class _AuditChainReplayToolState extends ConsumerState<AuditChainReplayTool>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;
  
  List<AuditSnapshot> _snapshots = [];
  AuditSnapshot? _selectedSnapshot;
  ChainVerificationResult? _verificationResult;
  bool _isLoading = false;
  bool _isVerifying = false;
  String? _error;

  // Filters
  String? _filterRole;
  String? _filterAction;
  DateTimeRange? _filterDateRange;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
    _loadSnapshots();
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  Future<void> _loadSnapshots() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      if (widget.preloadedSnapshots != null) {
        _snapshots = widget.preloadedSnapshots!;
      } else {
        // In production, fetch from API
        // For now, generate mock data
        _snapshots = _generateMockSnapshots();
      }
      
      setState(() {
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _error = 'Failed to load snapshots: $e';
        _isLoading = false;
      });
    }
  }

  Future<void> _verifyChain() async {
    setState(() {
      _isVerifying = true;
    });

    try {
      final errors = <String>[];
      var verifiedCount = 0;
      String? expectedPrevHash;

      for (var i = 0; i < _snapshots.length; i++) {
        final snapshot = _snapshots[i];
        
        // Verify prev_hash linkage
        if (snapshot.prevHash != expectedPrevHash) {
          errors.add('Chain broken at snapshot ${snapshot.snapshotId} (index $i)');
        } else {
          verifiedCount++;
        }

        // Compute expected hash for next iteration
        expectedPrevHash = UIIntegrityService.calculateHash(
          '${snapshot.snapshotId}:${snapshot.uiHash}:${snapshot.timestamp.toIso8601String()}'
        );

        // Add small delay to show progress
        await Future.delayed(const Duration(milliseconds: 50));
        setState(() {}); // Trigger rebuild to show progress
      }

      setState(() {
        _verificationResult = ChainVerificationResult(
          isValid: errors.isEmpty,
          totalSnapshots: _snapshots.length,
          verifiedSnapshots: verifiedCount,
          errors: errors,
          verifiedAt: DateTime.now(),
        );
        _isVerifying = false;
      });
    } catch (e) {
      setState(() {
        _error = 'Verification failed: $e';
        _isVerifying = false;
      });
    }
  }

  List<AuditSnapshot> get _filteredSnapshots {
    var result = _snapshots;
    
    if (_filterRole != null) {
      result = result.where((s) => s.actorRole == _filterRole).toList();
    }
    
    if (_filterAction != null) {
      result = result.where((s) => s.actionContext == _filterAction).toList();
    }
    
    if (_filterDateRange != null) {
      result = result.where((s) => 
        s.timestamp.isAfter(_filterDateRange!.start) &&
        s.timestamp.isBefore(_filterDateRange!.end)
      ).toList();
    }
    
    return result;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.darkBg,
      appBar: AppBar(
        title: const Text('Audit Chain Replay'),
        backgroundColor: AppTheme.darkCard,
        foregroundColor: AppTheme.cleanWhite,
        elevation: 0,
        actions: [
          if (_verificationResult != null)
            Container(
              margin: const EdgeInsets.symmetric(vertical: 8, horizontal: 8),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              decoration: BoxDecoration(
                color: _verificationResult!.isValid
                    ? AppTheme.neonGreen.withOpacity(0.2)
                    : Colors.red.withOpacity(0.2),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    _verificationResult!.isValid ? Icons.verified : Icons.error,
                    size: 16,
                    color: _verificationResult!.isValid ? AppTheme.neonGreen : Colors.red,
                  ),
                  const SizedBox(width: 6),
                  Text(
                    _verificationResult!.isValid ? 'Verified' : 'Invalid',
                    style: TextStyle(
                      color: _verificationResult!.isValid ? AppTheme.neonGreen : Colors.red,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
          IconButton(
            icon: const Icon(Icons.download),
            onPressed: () => _exportChain(),
            tooltip: 'Export Chain (JSON)',
          ),
          IconButton(
            icon: _isVerifying
                ? SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: AppTheme.cleanWhite,
                    ),
                  )
                : const Icon(Icons.verified_user),
            onPressed: _isVerifying ? null : _verifyChain,
            tooltip: 'Verify Chain Integrity',
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          indicatorColor: AppTheme.primaryBlue,
          tabs: const [
            Tab(text: 'Timeline', icon: Icon(Icons.timeline, size: 18)),
            Tab(text: 'Snapshot', icon: Icon(Icons.camera, size: 18)),
            Tab(text: 'Verification', icon: Icon(Icons.check_circle, size: 18)),
          ],
        ),
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? _buildErrorState()
              : TabBarView(
                  controller: _tabController,
                  children: [
                    _buildTimelineTab(),
                    _buildSnapshotTab(),
                    _buildVerificationTab(),
                  ],
                ),
    );
  }

  Widget _buildErrorState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.error_outline, size: 64, color: Colors.red.withOpacity(0.5)),
          const SizedBox(height: 16),
          Text(
            _error!,
            style: TextStyle(color: AppTheme.cleanWhite.withOpacity(0.7)),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 24),
          ElevatedButton.icon(
            onPressed: _loadSnapshots,
            icon: const Icon(Icons.refresh),
            label: const Text('Retry'),
          ),
        ],
      ),
    );
  }

  Widget _buildTimelineTab() {
    return Column(
      children: [
        // Filters
        Container(
          padding: const EdgeInsets.all(16),
          color: AppTheme.darkCard,
          child: Row(
            children: [
              Expanded(
                child: _buildFilterDropdown(
                  label: 'Role',
                  value: _filterRole,
                  items: ['R3_INSTITUTION_OPS', 'R4_INSTITUTION_COMPLIANCE', 'R5_PLATFORM_ADMIN', 'R6_SUPER_ADMIN'],
                  onChanged: (v) => setState(() => _filterRole = v),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _buildFilterDropdown(
                  label: 'Action',
                  value: _filterAction,
                  items: ['WALLET_PAUSE', 'ASSET_FREEZE', 'POLICY_CHANGE', 'INVESTIGATION'],
                  onChanged: (v) => setState(() => _filterAction = v),
                ),
              ),
              const SizedBox(width: 12),
              TextButton.icon(
                onPressed: () {
                  setState(() {
                    _filterRole = null;
                    _filterAction = null;
                    _filterDateRange = null;
                  });
                },
                icon: const Icon(Icons.clear, size: 16),
                label: const Text('Clear'),
              ),
            ],
          ),
        ),
        
        // Stats bar
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          color: AppTheme.darkCard.withOpacity(0.5),
          child: Row(
            children: [
              Text(
                '${_filteredSnapshots.length} snapshots',
                style: TextStyle(
                  color: AppTheme.cleanWhite.withOpacity(0.6),
                  fontSize: 12,
                ),
              ),
              const Spacer(),
              if (_snapshots.isNotEmpty)
                Text(
                  'From ${_formatDate(_snapshots.last.timestamp)} to ${_formatDate(_snapshots.first.timestamp)}',
                  style: TextStyle(
                    color: AppTheme.cleanWhite.withOpacity(0.4),
                    fontSize: 12,
                  ),
                ),
            ],
          ),
        ),
        
        // Timeline list
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: _filteredSnapshots.length,
            itemBuilder: (context, index) {
              final snapshot = _filteredSnapshots[index];
              final isSelected = _selectedSnapshot?.snapshotId == snapshot.snapshotId;
              
              return InkWell(
                onTap: () {
                  setState(() => _selectedSnapshot = snapshot);
                  _tabController.animateTo(1);
                },
                child: Container(
                  margin: const EdgeInsets.only(bottom: 12),
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: isSelected
                        ? AppTheme.primaryBlue.withOpacity(0.15)
                        : AppTheme.darkCard,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: isSelected
                          ? AppTheme.primaryBlue
                          : AppTheme.cleanWhite.withOpacity(0.1),
                      width: isSelected ? 2 : 1,
                    ),
                  ),
                  child: Row(
                    children: [
                      // Timeline indicator
                      Column(
                        children: [
                          Container(
                            width: 12,
                            height: 12,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: _getActionColor(snapshot.actionContext),
                            ),
                          ),
                          if (index < _filteredSnapshots.length - 1)
                            Container(
                              width: 2,
                              height: 40,
                              color: AppTheme.cleanWhite.withOpacity(0.2),
                            ),
                        ],
                      ),
                      const SizedBox(width: 16),
                      
                      // Content
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Text(
                                  snapshot.actionContext,
                                  style: const TextStyle(
                                    color: AppTheme.cleanWhite,
                                    fontWeight: FontWeight.w600,
                                    fontSize: 14,
                                  ),
                                ),
                                const Spacer(),
                                Text(
                                  _formatDateTime(snapshot.timestamp),
                                  style: TextStyle(
                                    color: AppTheme.cleanWhite.withOpacity(0.5),
                                    fontSize: 12,
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 4),
                            Text(
                              '${snapshot.actorRole} • ${snapshot.actorId}',
                              style: TextStyle(
                                color: AppTheme.cleanWhite.withOpacity(0.6),
                                fontSize: 12,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              'Hash: ${snapshot.uiHash.substring(0, 16)}…',
                              style: TextStyle(
                                color: AppTheme.cleanWhite.withOpacity(0.4),
                                fontSize: 11,
                                fontFamily: 'JetBrains Mono',
                              ),
                            ),
                          ],
                        ),
                      ),
                      
                      // Arrow
                      Icon(
                        Icons.chevron_right,
                        color: AppTheme.cleanWhite.withOpacity(0.3),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _buildSnapshotTab() {
    if (_selectedSnapshot == null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.touch_app,
              size: 64,
              color: AppTheme.cleanWhite.withOpacity(0.2),
            ),
            const SizedBox(height: 16),
            Text(
              'Select a snapshot from Timeline to view details',
              style: TextStyle(color: AppTheme.cleanWhite.withOpacity(0.5)),
            ),
          ],
        ),
      );
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Snapshot header
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppTheme.darkCard,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(
                      Icons.camera,
                      color: AppTheme.primaryBlue,
                    ),
                    const SizedBox(width: 8),
                    const Text(
                      'SNAPSHOT METADATA',
                      style: TextStyle(
                        color: AppTheme.primaryBlue,
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 1,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                _buildMetadataRow('Snapshot ID', _selectedSnapshot!.snapshotId),
                _buildMetadataRow('Timestamp', _formatDateTime(_selectedSnapshot!.timestamp)),
                _buildMetadataRow('Actor Role', _selectedSnapshot!.actorRole),
                _buildMetadataRow('Actor ID', _selectedSnapshot!.actorId),
                _buildMetadataRow('Action', _selectedSnapshot!.actionContext),
                if (_selectedSnapshot!.transactionId != null)
                  _buildMetadataRow('Transaction ID', _selectedSnapshot!.transactionId!),
              ],
            ),
          ),
          
          const SizedBox(height: 16),
          
          // Hash chain info
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppTheme.darkCard,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(
                      Icons.link,
                      color: AppTheme.neonGreen,
                    ),
                    const SizedBox(width: 8),
                    const Text(
                      'HASH CHAIN',
                      style: TextStyle(
                        color: AppTheme.neonGreen,
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 1,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                _buildHashRow('UI Hash', _selectedSnapshot!.uiHash),
                if (_selectedSnapshot!.prevHash != null)
                  _buildHashRow('Previous Hash', _selectedSnapshot!.prevHash!),
              ],
            ),
          ),
          
          const SizedBox(height: 16),
          
          // Displayed data
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppTheme.darkCard,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(
                      Icons.data_object,
                      color: Colors.orange,
                    ),
                    const SizedBox(width: 8),
                    const Text(
                      'DISPLAYED DATA (What User Saw)',
                      style: TextStyle(
                        color: Colors.orange,
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 1,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: AppTheme.darkBg,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: SelectableText(
                    _formatJson(_selectedSnapshot!.displayedData),
                    style: const TextStyle(
                      color: AppTheme.cleanWhite,
                      fontSize: 12,
                      fontFamily: 'JetBrains Mono',
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildVerificationTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Verification action card
          Card(
            color: AppTheme.darkCard,
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                children: [
                  Icon(
                    _verificationResult?.isValid == true
                        ? Icons.verified_user
                        : Icons.security,
                    size: 64,
                    color: _verificationResult?.isValid == true
                        ? AppTheme.neonGreen
                        : AppTheme.primaryBlue,
                  ),
                  const SizedBox(height: 16),
                  Text(
                    _verificationResult == null
                        ? 'Chain Integrity Verification'
                        : (_verificationResult!.isValid
                            ? 'Chain Verified Successfully'
                            : 'Chain Verification Failed'),
                    style: TextStyle(
                      color: AppTheme.cleanWhite,
                      fontSize: 20,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    _verificationResult == null
                        ? 'Verify the cryptographic integrity of the audit chain'
                        : '${_verificationResult!.verifiedSnapshots} of ${_verificationResult!.totalSnapshots} snapshots verified',
                    style: TextStyle(
                      color: AppTheme.cleanWhite.withOpacity(0.6),
                    ),
                  ),
                  const SizedBox(height: 24),
                  
                  if (_verificationResult == null)
                    ElevatedButton.icon(
                      onPressed: _isVerifying ? null : _verifyChain,
                      icon: _isVerifying
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.play_arrow),
                      label: Text(_isVerifying ? 'Verifying...' : 'Start Verification'),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppTheme.primaryBlue,
                        padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
                      ),
                    ),
                ],
              ),
            ),
          ),
          
          if (_verificationResult != null) ...[
            const SizedBox(height: 24),
            
            // Verification results
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: _verificationResult!.isValid
                    ? AppTheme.neonGreen.withOpacity(0.1)
                    : Colors.red.withOpacity(0.1),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: _verificationResult!.isValid
                      ? AppTheme.neonGreen.withOpacity(0.3)
                      : Colors.red.withOpacity(0.3),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(
                        _verificationResult!.isValid
                            ? Icons.check_circle
                            : Icons.error,
                        color: _verificationResult!.isValid
                            ? AppTheme.neonGreen
                            : Colors.red,
                      ),
                      const SizedBox(width: 8),
                      Text(
                        'VERIFICATION RESULT',
                        style: TextStyle(
                          color: _verificationResult!.isValid
                              ? AppTheme.neonGreen
                              : Colors.red,
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          letterSpacing: 1,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  _buildResultRow('Status', _verificationResult!.isValid ? 'VALID' : 'INVALID'),
                  _buildResultRow('Total Snapshots', _verificationResult!.totalSnapshots.toString()),
                  _buildResultRow('Verified', _verificationResult!.verifiedSnapshots.toString()),
                  _buildResultRow('Verified At', _formatDateTime(_verificationResult!.verifiedAt!)),
                  
                  if (_verificationResult!.errors.isNotEmpty) ...[
                    const SizedBox(height: 16),
                    const Text(
                      'Errors:',
                      style: TextStyle(
                        color: Colors.red,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 8),
                    ..._verificationResult!.errors.map((e) => Padding(
                      padding: const EdgeInsets.symmetric(vertical: 2),
                      child: Row(
                        children: [
                          const Icon(Icons.error_outline, size: 16, color: Colors.red),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              e,
                              style: TextStyle(
                                color: AppTheme.cleanWhite.withOpacity(0.8),
                                fontSize: 13,
                              ),
                            ),
                          ),
                        ],
                      ),
                    )),
                  ],
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildFilterDropdown({
    required String label,
    required String? value,
    required List<String> items,
    required void Function(String?) onChanged,
  }) {
    return DropdownButtonFormField<String>(
      initialValue: value,
      decoration: InputDecoration(
        labelText: label,
        labelStyle: TextStyle(color: AppTheme.cleanWhite.withOpacity(0.5)),
        filled: true,
        fillColor: AppTheme.darkBg,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide.none,
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      ),
      dropdownColor: AppTheme.darkCard,
      style: const TextStyle(color: AppTheme.cleanWhite, fontSize: 13),
      items: [
        DropdownMenuItem<String>(
          value: null,
          child: Text('All', style: TextStyle(color: AppTheme.cleanWhite.withOpacity(0.5))),
        ),
        ...items.map((item) => DropdownMenuItem(
          value: item,
          child: Text(item),
        )),
      ],
      onChanged: onChanged,
    );
  }

  Widget _buildMetadataRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 120,
            child: Text(
              label,
              style: TextStyle(
                color: AppTheme.cleanWhite.withOpacity(0.5),
                fontSize: 13,
              ),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(
                color: AppTheme.cleanWhite,
                fontSize: 13,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildHashRow(String label, String hash) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: TextStyle(
              color: AppTheme.cleanWhite.withOpacity(0.5),
              fontSize: 12,
            ),
          ),
          const SizedBox(height: 4),
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: AppTheme.darkBg,
              borderRadius: BorderRadius.circular(4),
            ),
            child: Row(
              children: [
                Expanded(
                  child: SelectableText(
                    hash,
                    style: const TextStyle(
                      color: AppTheme.cleanWhite,
                      fontSize: 11,
                      fontFamily: 'JetBrains Mono',
                    ),
                  ),
                ),
                IconButton(
                  icon: Icon(Icons.copy, size: 16, color: AppTheme.cleanWhite.withOpacity(0.5)),
                  onPressed: () {},
                  tooltip: 'Copy',
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildResultRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          SizedBox(
            width: 120,
            child: Text(
              label,
              style: TextStyle(
                color: AppTheme.cleanWhite.withOpacity(0.6),
                fontSize: 13,
              ),
            ),
          ),
          Text(
            value,
            style: TextStyle(
              color: AppTheme.cleanWhite,
              fontSize: 13,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }

  Color _getActionColor(String action) {
    switch (action) {
      case 'WALLET_PAUSE':
        return Colors.orange;
      case 'ASSET_FREEZE':
        return Colors.blue;
      case 'POLICY_CHANGE':
        return Colors.purple;
      case 'INVESTIGATION':
        return AppTheme.primaryBlue;
      default:
        return AppTheme.cleanWhite.withOpacity(0.5);
    }
  }

  String _formatDate(DateTime dt) {
    return '${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')}';
  }

  String _formatDateTime(DateTime dt) {
    return '${_formatDate(dt)} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}:${dt.second.toString().padLeft(2, '0')}';
  }

  String _formatJson(Map<String, dynamic> data) {
    const encoder = JsonEncoder.withIndent('  ');
    return encoder.convert(data);
  }

  void _exportChain() {
    // In production, this would generate and download a JSON file
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Exporting chain as JSON...')),
    );
  }

  List<AuditSnapshot> _generateMockSnapshots() {
    final now = DateTime.now();
    return [
      AuditSnapshot(
        snapshotId: 'snap_001',
        timestamp: now.subtract(const Duration(hours: 1)),
        actorRole: 'R4_INSTITUTION_COMPLIANCE',
        actorId: 'user_8831',
        actionContext: 'WALLET_PAUSE',
        transactionId: '0xA1B2C3',
        displayedData: {
          'risk_pillars': {'identity': 'Verified', 'behavior': 'Anomalous'},
          'fan_out': 7,
          'velocity_spike': '6σ',
        },
        uiHash: 'a7f3c9e2d1b0f8a7c6e5d4b3a2f1e0d9c8b7a6f5',
        prevHash: null,
      ),
      AuditSnapshot(
        snapshotId: 'snap_002',
        timestamp: now.subtract(const Duration(minutes: 45)),
        actorRole: 'R3_INSTITUTION_OPS',
        actorId: 'user_4421',
        actionContext: 'INVESTIGATION',
        transactionId: '0xA1B2C3',
        displayedData: {
          'graph_summary': {'hops': 3, 'fan_out': 7, 'layering': true},
        },
        uiHash: 'b8e4d0f3c2a1e9d8c7b6a5f4e3d2c1b0a9f8e7d6',
        prevHash: 'a7f3c9e2d1b0f8a7c6e5d4b3a2f1e0d9c8b7a6f5',
      ),
      AuditSnapshot(
        snapshotId: 'snap_003',
        timestamp: now.subtract(const Duration(minutes: 30)),
        actorRole: 'R4_INSTITUTION_COMPLIANCE',
        actorId: 'user_8831',
        actionContext: 'POLICY_CHANGE',
        displayedData: {
          'policy_id': 'POLICY_v3.2',
          'changes': ['velocity_threshold: 5000 -> 3000'],
        },
        uiHash: 'c9f5e1a4d3b2c0e9d8c7b6a5f4e3d2c1b0a9f8e7',
        prevHash: 'b8e4d0f3c2a1e9d8c7b6a5f4e3d2c1b0a9f8e7d6',
      ),
    ];
  }
}

// JSON encoder for formatting
class JsonEncoder {
  final String? indent;
  
  const JsonEncoder.withIndent(this.indent);
  
  String convert(Map<String, dynamic> data) {
    return _encode(data, 0);
  }
  
  String _encode(dynamic value, int depth) {
    final prefix = indent != null ? indent! * depth : '';
    final newline = indent != null ? '\n' : '';
    
    if (value is Map) {
      if (value.isEmpty) return '{}';
      final entries = value.entries.map((e) {
        return '$prefix${indent ?? ""}"${e.key}": ${_encode(e.value, depth + 1)}';
      }).join(',$newline');
      return '{$newline$entries$newline${indent != null ? indent! * (depth > 0 ? depth - 1 : 0) : ''}}';
    } else if (value is List) {
      if (value.isEmpty) return '[]';
      final items = value.map((e) => '$prefix${indent ?? ""}${_encode(e, depth + 1)}').join(',$newline');
      return '[$newline$items$newline${indent != null ? indent! * (depth > 0 ? depth - 1 : 0) : ''}]';
    } else if (value is String) {
      return '"$value"';
    } else if (value is bool || value is num) {
      return '$value';
    } else if (value == null) {
      return 'null';
    }
    return '"$value"';
  }
}
