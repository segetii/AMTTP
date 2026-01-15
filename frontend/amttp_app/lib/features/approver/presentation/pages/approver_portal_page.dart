import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/theme/app_theme.dart';

/// Approver Portal Page - Covers AMTTPCore.sol approval workflow
/// Functions covered:
/// - approveSwap()
/// - rejectSwap()
/// - Pending swap queue management
class ApproverPortalPage extends ConsumerStatefulWidget {
  const ApproverPortalPage({super.key});

  @override
  ConsumerState<ApproverPortalPage> createState() => _ApproverPortalPageState();
}

class _ApproverPortalPageState extends ConsumerState<ApproverPortalPage>
    with TickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
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
        title: const Text('Approver Portal'),
        backgroundColor: AppTheme.darkCard,
        foregroundColor: AppTheme.cleanWhite,
        elevation: 0,
        actions: [
          IconButton(
            onPressed: () {},
            icon: const Icon(Icons.filter_list),
            tooltip: 'Filter',
          ),
          IconButton(
            onPressed: () {},
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh',
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          indicatorColor: AppTheme.primaryBlue,
          tabs: const [
            Tab(text: 'Pending', icon: Icon(Icons.pending_actions)),
            Tab(text: 'Approved', icon: Icon(Icons.check_circle)),
            Tab(text: 'Rejected', icon: Icon(Icons.cancel)),
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
            _PendingSwapsTab(),
            _ApprovedSwapsTab(),
            _RejectedSwapsTab(),
          ],
        ),
      ),
    );
  }
}

/// Tab 0: Pending Swaps awaiting approval
class _PendingSwapsTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final pendingSwaps = [
      {
        'swapId': 'SWP-001234',
        'from': '0x1234...5678',
        'to': '0xabcd...ef12',
        'amount': '2.5 ETH',
        'riskScore': 35,
        'created': '2 hours ago',
        'urgency': 'normal',
      },
      {
        'swapId': 'SWP-001235',
        'from': '0x8888...9999',
        'to': '0x1111...2222',
        'amount': '10.0 ETH',
        'riskScore': 72,
        'created': '15 min ago',
        'urgency': 'high',
      },
      {
        'swapId': 'SWP-001236',
        'from': '0xaaaa...bbbb',
        'to': '0xcccc...dddd',
        'amount': '0.5 ETH',
        'riskScore': 15,
        'created': '1 day ago',
        'urgency': 'low',
      },
    ];

    if (pendingSwaps.isEmpty) {
      return const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.inbox, size: 64, color: AppTheme.mutedText),
            SizedBox(height: 16),
            Text('No pending swaps', style: TextStyle(color: AppTheme.mutedText, fontSize: 18)),
          ],
        ),
      );
    }

    return Column(
      children: [
        _buildStatsHeader(pendingSwaps.length),
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: pendingSwaps.length,
            itemBuilder: (context, index) {
              return _PendingSwapCard(swap: pendingSwaps[index]);
            },
          ),
        ),
      ],
    );
  }

  Widget _buildStatsHeader(int count) {
    return Container(
      padding: const EdgeInsets.all(16),
      color: AppTheme.darkCard,
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppTheme.warningOrange.withOpacity(0.2),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Icon(Icons.pending_actions, color: AppTheme.warningOrange),
          ),
          const SizedBox(width: 12),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('$count Pending Approvals', style: const TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold, fontSize: 18)),
              const Text('Review and approve/reject swaps', style: TextStyle(color: AppTheme.mutedText)),
            ],
          ),
          const Spacer(),
          ElevatedButton.icon(
            onPressed: () {},
            icon: const Icon(Icons.done_all),
            label: const Text('Bulk Actions'),
            style: ElevatedButton.styleFrom(backgroundColor: AppTheme.primaryBlue),
          ),
        ],
      ),
    );
  }
}

class _PendingSwapCard extends StatelessWidget {
  final Map<String, dynamic> swap;

  const _PendingSwapCard({required this.swap});

  @override
  Widget build(BuildContext context) {
    final riskScore = swap['riskScore'] as int;
    final urgency = swap['urgency'] as String;
    final riskColor = riskScore > 70 ? AppTheme.dangerRed : 
                      riskScore > 40 ? AppTheme.warningOrange : AppTheme.accentGreen;
    final urgencyColor = urgency == 'high' ? AppTheme.dangerRed :
                         urgency == 'low' ? AppTheme.mutedText : AppTheme.warningOrange;

    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkCard,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: urgencyColor.withOpacity(0.5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: urgencyColor.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  urgency.toUpperCase(),
                  style: TextStyle(color: urgencyColor, fontSize: 10, fontWeight: FontWeight.bold),
                ),
              ),
              const SizedBox(width: 8),
              Text(swap['swapId'] as String, style: const TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold)),
              const Spacer(),
              Text(swap['created'] as String, style: const TextStyle(color: AppTheme.mutedText, fontSize: 12)),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('From', style: TextStyle(color: AppTheme.mutedText, fontSize: 12)),
                    const SizedBox(height: 4),
                    Text(swap['from'] as String, style: const TextStyle(color: AppTheme.cleanWhite, fontFamily: 'monospace')),
                  ],
                ),
              ),
              const Icon(Icons.arrow_forward, color: AppTheme.mutedText),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    const Text('To', style: TextStyle(color: AppTheme.mutedText, fontSize: 12)),
                    const SizedBox(height: 4),
                    Text(swap['to'] as String, style: const TextStyle(color: AppTheme.cleanWhite, fontFamily: 'monospace')),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              _buildInfoChip(Icons.monetization_on, swap['amount'] as String, AppTheme.primaryBlue),
              const SizedBox(width: 12),
              _buildInfoChip(Icons.security, 'Risk: $riskScore', riskColor),
            ],
          ),
          const SizedBox(height: 16),
          
          // Risk Analysis Summary
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppTheme.darkBg,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(
              children: [
                Icon(Icons.analytics, color: riskColor, size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    riskScore > 70 
                        ? 'High risk: Consider additional verification' 
                        : riskScore > 40 
                            ? 'Medium risk: Review counterparty history' 
                            : 'Low risk: Standard swap request',
                    style: const TextStyle(color: AppTheme.mutedText, fontSize: 12),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () {
                    _showRejectDialog(context);
                  },
                  icon: const Icon(Icons.cancel),
                  label: const Text('Reject'),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppTheme.dangerRed,
                    side: const BorderSide(color: AppTheme.dangerRed),
                    padding: const EdgeInsets.symmetric(vertical: 12),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: () {
                    _showApproveDialog(context);
                  },
                  icon: const Icon(Icons.check_circle),
                  label: const Text('Approve'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppTheme.accentGreen,
                    foregroundColor: AppTheme.cleanWhite,
                    padding: const EdgeInsets.symmetric(vertical: 12),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildInfoChip(IconData icon, String text, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: color.withOpacity(0.2),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: color, size: 16),
          const SizedBox(width: 4),
          Text(text, style: TextStyle(color: color, fontWeight: FontWeight.bold)),
        ],
      ),
    );
  }

  void _showApproveDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppTheme.darkCard,
        title: const Row(
          children: [
            Icon(Icons.check_circle, color: AppTheme.accentGreen),
            SizedBox(width: 8),
            Text('Approve Swap', style: TextStyle(color: AppTheme.cleanWhite)),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Swap ID: ${swap['swapId']}', style: const TextStyle(color: AppTheme.cleanWhite)),
            const SizedBox(height: 8),
            Text('Amount: ${swap['amount']}', style: const TextStyle(color: AppTheme.mutedText)),
            const SizedBox(height: 16),
            const Text('This action will execute approveSwap() on-chain.', style: TextStyle(color: AppTheme.mutedText)),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Swap approved successfully!'), backgroundColor: AppTheme.accentGreen),
              );
            },
            style: ElevatedButton.styleFrom(backgroundColor: AppTheme.accentGreen),
            child: const Text('Confirm Approval'),
          ),
        ],
      ),
    );
  }

  void _showRejectDialog(BuildContext context) {
    final reasonController = TextEditingController();
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppTheme.darkCard,
        title: const Row(
          children: [
            Icon(Icons.cancel, color: AppTheme.dangerRed),
            SizedBox(width: 8),
            Text('Reject Swap', style: TextStyle(color: AppTheme.cleanWhite)),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Swap ID: ${swap['swapId']}', style: const TextStyle(color: AppTheme.cleanWhite)),
            const SizedBox(height: 16),
            TextField(
              controller: reasonController,
              maxLines: 3,
              decoration: InputDecoration(
                labelText: 'Rejection Reason',
                labelStyle: const TextStyle(color: AppTheme.mutedText),
                hintText: 'Enter reason for rejection...',
                hintStyle: const TextStyle(color: AppTheme.mutedText),
                filled: true,
                fillColor: AppTheme.darkBg,
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide.none),
              ),
              style: const TextStyle(color: AppTheme.cleanWhite),
            ),
            const SizedBox(height: 16),
            const Text('This action will execute rejectSwap() on-chain.', style: TextStyle(color: AppTheme.mutedText)),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Swap rejected'), backgroundColor: AppTheme.dangerRed),
              );
            },
            style: ElevatedButton.styleFrom(backgroundColor: AppTheme.dangerRed),
            child: const Text('Confirm Rejection'),
          ),
        ],
      ),
    );
  }
}

/// Tab 1: Approved Swaps
class _ApprovedSwapsTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final approvedSwaps = [
      {'swapId': 'SWP-001200', 'amount': '1.5 ETH', 'approvedAt': 'Jan 3, 2026', 'by': 'You'},
      {'swapId': 'SWP-001199', 'amount': '3.0 ETH', 'approvedAt': 'Jan 2, 2026', 'by': 'You'},
    ];

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: approvedSwaps.length,
      itemBuilder: (context, index) {
        final swap = approvedSwaps[index];
        return Container(
          margin: const EdgeInsets.only(bottom: 12),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppTheme.darkCard,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: AppTheme.accentGreen.withOpacity(0.3)),
          ),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: AppTheme.accentGreen.withOpacity(0.2),
                  shape: BoxShape.circle,
                ),
                child: const Icon(Icons.check_circle, color: AppTheme.accentGreen),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(swap['swapId'] as String, style: const TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold)),
                    Text('${swap['amount']} • Approved by ${swap['by']}', style: const TextStyle(color: AppTheme.mutedText, fontSize: 12)),
                  ],
                ),
              ),
              Text(swap['approvedAt'] as String, style: const TextStyle(color: AppTheme.mutedText)),
            ],
          ),
        );
      },
    );
  }
}

/// Tab 2: Rejected Swaps
class _RejectedSwapsTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final rejectedSwaps = [
      {'swapId': 'SWP-001150', 'amount': '25.0 ETH', 'rejectedAt': 'Jan 1, 2026', 'reason': 'High risk score'},
      {'swapId': 'SWP-001148', 'amount': '5.0 ETH', 'rejectedAt': 'Dec 30, 2025', 'reason': 'Suspicious counterparty'},
    ];

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: rejectedSwaps.length,
      itemBuilder: (context, index) {
        final swap = rejectedSwaps[index];
        return Container(
          margin: const EdgeInsets.only(bottom: 12),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppTheme.darkCard,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: AppTheme.dangerRed.withOpacity(0.3)),
          ),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: AppTheme.dangerRed.withOpacity(0.2),
                  shape: BoxShape.circle,
                ),
                child: const Icon(Icons.cancel, color: AppTheme.dangerRed),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(swap['swapId'] as String, style: const TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold)),
                    Text('${swap['amount']} • ${swap['reason']}', style: const TextStyle(color: AppTheme.mutedText, fontSize: 12)),
                  ],
                ),
              ),
              Text(swap['rejectedAt'] as String, style: const TextStyle(color: AppTheme.mutedText)),
            ],
          ),
        );
      },
    );
  }
}
