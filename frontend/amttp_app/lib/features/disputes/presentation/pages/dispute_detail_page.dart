import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/theme/app_theme.dart';

/// Dispute Detail Page - Detailed view for a single dispute
/// Functions covered:
/// - submitEvidence()
/// - requestAppeal()
/// - Dispute timeline
/// - Evidence gallery
class DisputeDetailPage extends ConsumerStatefulWidget {
  final String disputeId;

  const DisputeDetailPage({super.key, required this.disputeId});

  @override
  ConsumerState<DisputeDetailPage> createState() => _DisputeDetailPageState();
}

class _DisputeDetailPageState extends ConsumerState<DisputeDetailPage> {
  final _evidenceController = TextEditingController();
  bool _isSubmitting = false;

  // Mock dispute data
  late Map<String, dynamic> _dispute;

  @override
  void initState() {
    super.initState();
    _dispute = {
      'id': widget.disputeId,
      'status': 'evidence_period',
      'created': 'Jan 2, 2026 14:30',
      'deadline': 'Jan 9, 2026 14:30',
      'daysLeft': 5,
      'swapId': 'SWP-001234',
      'amount': '2.5 ETH',
      'challenger': '0x1234...5678',
      'respondent': '0xabcd...ef12',
      'reason': 'Item not as described - NFT metadata does not match listing',
      'staked': '0.5 ETH',
      'evidence': [
        {'from': 'challenger', 'text': 'NFT was advertised as having rare trait but actual metadata shows common trait', 'timestamp': 'Jan 2, 2026 14:35', 'attachments': 1},
        {'from': 'respondent', 'text': 'Metadata was correctly displayed on marketplace. Buyer should have verified before purchase.', 'timestamp': 'Jan 3, 2026 09:00', 'attachments': 2},
      ],
      'timeline': [
        {'event': 'Dispute Created', 'time': 'Jan 2, 2026 14:30', 'actor': 'Challenger'},
        {'event': 'Evidence Submitted', 'time': 'Jan 2, 2026 14:35', 'actor': 'Challenger'},
        {'event': 'Evidence Submitted', 'time': 'Jan 3, 2026 09:00', 'actor': 'Respondent'},
      ],
    };
  }

  @override
  void dispose() {
    _evidenceController.dispose();
    super.dispose();
  }

  Future<void> _submitEvidence() async {
    if (_evidenceController.text.isEmpty) return;
    
    setState(() => _isSubmitting = true);
    try {
      await Future.delayed(const Duration(seconds: 2));
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Evidence submitted successfully!'), backgroundColor: AppTheme.accentGreen),
        );
        _evidenceController.clear();
      }
    } finally {
      setState(() => _isSubmitting = false);
    }
  }

  Future<void> _requestAppeal() async {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppTheme.darkCard,
        title: const Row(
          children: [
            Icon(Icons.gavel, color: AppTheme.warningOrange),
            SizedBox(width: 8),
            Text('Request Appeal', style: TextStyle(color: AppTheme.cleanWhite)),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Request an appeal to the Kleros arbitration court.', style: TextStyle(color: AppTheme.mutedText)),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppTheme.darkBg,
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    Icon(Icons.attach_money, color: AppTheme.warningOrange, size: 16),
                    SizedBox(width: 8),
                    Text('Appeal Fee: 0.3 ETH', style: TextStyle(color: AppTheme.cleanWhite)),
                  ]),
                  SizedBox(height: 8),
                  Row(children: [
                    Icon(Icons.timer, color: AppTheme.warningOrange, size: 16),
                    SizedBox(width: 8),
                    Text('Review Time: ~7 days', style: TextStyle(color: AppTheme.cleanWhite)),
                  ]),
                ],
              ),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Appeal request submitted to Kleros'), backgroundColor: AppTheme.accentGreen),
              );
            },
            style: ElevatedButton.styleFrom(backgroundColor: AppTheme.warningOrange),
            child: const Text('Submit Appeal'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final status = _dispute['status'] as String;
    final statusLabel = _getStatusLabel(status);
    final statusColor = _getStatusColor(status);

    return Scaffold(
      backgroundColor: AppTheme.darkBg,
      appBar: AppBar(
        title: Text('Dispute ${widget.disputeId}'),
        backgroundColor: AppTheme.darkCard,
        foregroundColor: AppTheme.cleanWhite,
        elevation: 0,
        actions: [
          IconButton(onPressed: () {}, icon: const Icon(Icons.share), tooltip: 'Share'),
          IconButton(onPressed: () {}, icon: const Icon(Icons.more_vert), tooltip: 'More'),
        ],
      ),
      body: Container(
        decoration: const BoxDecoration(gradient: AppTheme.darkGradient),
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Status Header
              Container(
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  color: AppTheme.darkCard,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: statusColor.withOpacity(0.5)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: statusColor.withOpacity(0.2),
                            shape: BoxShape.circle,
                          ),
                          child: Icon(Icons.gavel, color: statusColor),
                        ),
                        const SizedBox(width: 16),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(statusLabel, style: TextStyle(color: statusColor, fontSize: 18, fontWeight: FontWeight.bold)),
                              Text('Swap: ${_dispute['swapId']} • ${_dispute['amount']}', style: const TextStyle(color: AppTheme.mutedText)),
                            ],
                          ),
                        ),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                          decoration: BoxDecoration(
                            color: AppTheme.warningOrange.withOpacity(0.2),
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: Text('${_dispute['daysLeft']} days left', style: const TextStyle(color: AppTheme.warningOrange, fontWeight: FontWeight.bold)),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    const Divider(color: AppTheme.mutedText),
                    const SizedBox(height: 16),
                    Row(
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text('Challenger', style: TextStyle(color: AppTheme.mutedText, fontSize: 12)),
                              const SizedBox(height: 4),
                              Text(_dispute['challenger'] as String, style: const TextStyle(color: AppTheme.cleanWhite, fontFamily: 'monospace')),
                            ],
                          ),
                        ),
                        const Icon(Icons.compare_arrows, color: AppTheme.mutedText),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              const Text('Respondent', style: TextStyle(color: AppTheme.mutedText, fontSize: 12)),
                              const SizedBox(height: 4),
                              Text(_dispute['respondent'] as String, style: const TextStyle(color: AppTheme.cleanWhite, fontFamily: 'monospace')),
                            ],
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
                      child: Row(
                        children: [
                          const Icon(Icons.report, color: AppTheme.warningOrange, size: 20),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(_dispute['reason'] as String, style: const TextStyle(color: AppTheme.cleanWhite)),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        const Icon(Icons.lock, color: AppTheme.mutedText, size: 16),
                        const SizedBox(width: 8),
                        Text('Staked: ${_dispute['staked']}', style: const TextStyle(color: AppTheme.mutedText)),
                        const Spacer(),
                        const Icon(Icons.timer, color: AppTheme.mutedText, size: 16),
                        const SizedBox(width: 8),
                        Text('Deadline: ${_dispute['deadline']}', style: const TextStyle(color: AppTheme.mutedText)),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),

              // Evidence Section
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(color: AppTheme.darkCard, borderRadius: BorderRadius.circular(16)),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Row(children: [
                      Icon(Icons.folder, color: AppTheme.primaryBlue),
                      SizedBox(width: 8),
                      Text('Evidence', style: TextStyle(color: AppTheme.cleanWhite, fontSize: 18, fontWeight: FontWeight.bold)),
                    ]),
                    const SizedBox(height: 16),
                    
                    ...(_dispute['evidence'] as List).map((ev) {
                      final isChallenger = ev['from'] == 'challenger';
                      return Container(
                        margin: const EdgeInsets.only(bottom: 12),
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: AppTheme.darkBg,
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: isChallenger ? AppTheme.dangerRed.withOpacity(0.3) : AppTheme.accentGreen.withOpacity(0.3)),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                  decoration: BoxDecoration(
                                    color: (isChallenger ? AppTheme.dangerRed : AppTheme.accentGreen).withOpacity(0.2),
                                    borderRadius: BorderRadius.circular(4),
                                  ),
                                  child: Text(
                                    isChallenger ? 'CHALLENGER' : 'RESPONDENT',
                                    style: TextStyle(color: isChallenger ? AppTheme.dangerRed : AppTheme.accentGreen, fontSize: 10, fontWeight: FontWeight.bold),
                                  ),
                                ),
                                const Spacer(),
                                Text(ev['timestamp'] as String, style: const TextStyle(color: AppTheme.mutedText, fontSize: 12)),
                              ],
                            ),
                            const SizedBox(height: 12),
                            Text(ev['text'] as String, style: const TextStyle(color: AppTheme.cleanWhite)),
                            if (ev['attachments'] != null && ev['attachments'] > 0) ...[
                              const SizedBox(height: 8),
                              Row(
                                children: [
                                  const Icon(Icons.attach_file, color: AppTheme.mutedText, size: 16),
                                  const SizedBox(width: 4),
                                  Text('${ev['attachments']} attachment(s)', style: const TextStyle(color: AppTheme.primaryBlue, fontSize: 12)),
                                ],
                              ),
                            ],
                          ],
                        ),
                      );
                    }),
                    
                    const Divider(color: AppTheme.mutedText),
                    const SizedBox(height: 12),
                    
                    // Submit Evidence Form
                    const Text('Submit Evidence', style: TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold)),
                    const SizedBox(height: 8),
                    TextField(
                      controller: _evidenceController,
                      maxLines: 3,
                      decoration: InputDecoration(
                        hintText: 'Describe your evidence...',
                        hintStyle: const TextStyle(color: AppTheme.mutedText),
                        filled: true,
                        fillColor: AppTheme.darkBg,
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide.none),
                      ),
                      style: const TextStyle(color: AppTheme.cleanWhite),
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        OutlinedButton.icon(
                          onPressed: () {},
                          icon: const Icon(Icons.attach_file),
                          label: const Text('Attach File'),
                          style: OutlinedButton.styleFrom(foregroundColor: AppTheme.primaryBlue),
                        ),
                        const Spacer(),
                        ElevatedButton.icon(
                          onPressed: _isSubmitting ? null : _submitEvidence,
                          icon: _isSubmitting
                              ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                              : const Icon(Icons.send),
                          label: const Text('Submit'),
                          style: ElevatedButton.styleFrom(backgroundColor: AppTheme.primaryBlue),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),

              // Timeline Section
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(color: AppTheme.darkCard, borderRadius: BorderRadius.circular(16)),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Row(children: [
                      Icon(Icons.timeline, color: AppTheme.primaryBlue),
                      SizedBox(width: 8),
                      Text('Timeline', style: TextStyle(color: AppTheme.cleanWhite, fontSize: 18, fontWeight: FontWeight.bold)),
                    ]),
                    const SizedBox(height: 16),
                    ...(_dispute['timeline'] as List).asMap().entries.map((entry) {
                      final item = entry.value;
                      final isLast = entry.key == (_dispute['timeline'] as List).length - 1;
                      return Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Column(
                            children: [
                              Container(
                                width: 12,
                                height: 12,
                                decoration: BoxDecoration(
                                  color: AppTheme.primaryBlue,
                                  shape: BoxShape.circle,
                                ),
                              ),
                              if (!isLast)
                                Container(
                                  width: 2,
                                  height: 40,
                                  color: AppTheme.primaryBlue.withOpacity(0.3),
                                ),
                            ],
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Padding(
                              padding: const EdgeInsets.only(bottom: 16),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(item['event'] as String, style: const TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold)),
                                  Text('${item['actor']} • ${item['time']}', style: const TextStyle(color: AppTheme.mutedText, fontSize: 12)),
                                ],
                              ),
                            ),
                          ),
                        ],
                      );
                    }),
                  ],
                ),
              ),
              const SizedBox(height: 16),

              // Action Buttons
              Row(
                children: [
                  Expanded(
                    child: ElevatedButton.icon(
                      onPressed: _requestAppeal,
                      icon: const Icon(Icons.gavel),
                      label: const Text('Request Appeal'),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppTheme.warningOrange,
                        foregroundColor: AppTheme.cleanWhite,
                        padding: const EdgeInsets.symmetric(vertical: 16),
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 32),
            ],
          ),
        ),
      ),
    );
  }

  String _getStatusLabel(String status) {
    switch (status) {
      case 'evidence_period': return 'Evidence Period';
      case 'voting': return 'Jury Voting';
      case 'appeal': return 'Appeal Period';
      case 'resolved': return 'Resolved';
      default: return 'Unknown';
    }
  }

  Color _getStatusColor(String status) {
    switch (status) {
      case 'evidence_period': return AppTheme.warningOrange;
      case 'voting': return AppTheme.primaryBlue;
      case 'appeal': return AppTheme.dangerRed;
      case 'resolved': return AppTheme.accentGreen;
      default: return AppTheme.mutedText;
    }
  }
}
