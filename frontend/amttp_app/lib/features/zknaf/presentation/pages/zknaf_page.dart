import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// zkNAF Proof Status Model
enum ZkProofType {
  sanctions,
  riskLow,
  riskMedium,
  kyc,
}

enum ZkProofStatus {
  notGenerated,
  generating,
  valid,
  expired,
  revoked,
  error,
}

class ZkProof {
  final String id;
  final ZkProofType type;
  final ZkProofStatus status;
  final String? proofHash;
  final DateTime? createdAt;
  final DateTime? expiresAt;
  final String? errorMessage;

  ZkProof({
    required this.id,
    required this.type,
    required this.status,
    this.proofHash,
    this.createdAt,
    this.expiresAt,
    this.errorMessage,
  });

  bool get isValid =>
      status == ZkProofStatus.valid &&
      expiresAt != null &&
      expiresAt!.isAfter(DateTime.now());

  String get typeDisplayName {
    switch (type) {
      case ZkProofType.sanctions:
        return 'Sanctions Non-Membership';
      case ZkProofType.riskLow:
        return 'Low Risk Score';
      case ZkProofType.riskMedium:
        return 'Medium Risk Score';
      case ZkProofType.kyc:
        return 'KYC Verified';
    }
  }

  IconData get typeIcon {
    switch (type) {
      case ZkProofType.sanctions:
        return Icons.shield_outlined;
      case ZkProofType.riskLow:
        return Icons.trending_down_rounded;
      case ZkProofType.riskMedium:
        return Icons.trending_flat_rounded;
      case ZkProofType.kyc:
        return Icons.verified_user_outlined;
    }
  }

  Color get statusColor {
    switch (status) {
      case ZkProofStatus.notGenerated:
        return Colors.grey;
      case ZkProofStatus.generating:
        return Colors.blue;
      case ZkProofStatus.valid:
        return Colors.green;
      case ZkProofStatus.expired:
        return Colors.orange;
      case ZkProofStatus.revoked:
        return Colors.red;
      case ZkProofStatus.error:
        return Colors.red;
    }
  }
}

/// zkNAF State
class ZkNAFState {
  final bool isLoading;
  final List<ZkProof> proofs;
  final bool isFullyCompliant;
  final String? walletAddress;
  final String? error;

  ZkNAFState({
    this.isLoading = false,
    this.proofs = const [],
    this.isFullyCompliant = false,
    this.walletAddress,
    this.error,
  });

  ZkNAFState copyWith({
    bool? isLoading,
    List<ZkProof>? proofs,
    bool? isFullyCompliant,
    String? walletAddress,
    String? error,
  }) {
    return ZkNAFState(
      isLoading: isLoading ?? this.isLoading,
      proofs: proofs ?? this.proofs,
      isFullyCompliant: isFullyCompliant ?? this.isFullyCompliant,
      walletAddress: walletAddress ?? this.walletAddress,
      error: error,
    );
  }

  ZkProof? getProof(ZkProofType type) {
    try {
      return proofs.firstWhere((p) => p.type == type);
    } catch (_) {
      return null;
    }
  }
}

/// zkNAF Notifier
class ZkNAFNotifier extends StateNotifier<ZkNAFState> {
  ZkNAFNotifier() : super(ZkNAFState());

  Future<void> loadProofs(String walletAddress) async {
    state = state.copyWith(isLoading: true, walletAddress: walletAddress);

    try {
      // Simulate API call to fetch existing proofs
      await Future.delayed(const Duration(milliseconds: 500));

      // Demo: Create initial state with no proofs
      final proofs = [
        ZkProof(
          id: 'demo-sanctions',
          type: ZkProofType.sanctions,
          status: ZkProofStatus.notGenerated,
        ),
        ZkProof(
          id: 'demo-risk',
          type: ZkProofType.riskLow,
          status: ZkProofStatus.notGenerated,
        ),
        ZkProof(
          id: 'demo-kyc',
          type: ZkProofType.kyc,
          status: ZkProofStatus.notGenerated,
        ),
      ];

      state = state.copyWith(
        isLoading: false,
        proofs: proofs,
        isFullyCompliant: false,
      );
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: e.toString(),
      );
    }
  }

  Future<void> generateProof(ZkProofType type) async {
    // Update status to generating
    final updatedProofs = state.proofs.map((p) {
      if (p.type == type) {
        return ZkProof(
          id: p.id,
          type: p.type,
          status: ZkProofStatus.generating,
        );
      }
      return p;
    }).toList();

    state = state.copyWith(proofs: updatedProofs);

    try {
      // Simulate proof generation
      await Future.delayed(const Duration(seconds: 2));

      // Update with generated proof
      final now = DateTime.now();
      final finalProofs = state.proofs.map((p) {
        if (p.type == type) {
          return ZkProof(
            id: 'proof-${type.name}-${now.millisecondsSinceEpoch}',
            type: p.type,
            status: ZkProofStatus.valid,
            proofHash: '0x${List.generate(64, (i) => 'abcdef0123456789'[(i * 7) % 16]).join()}',
            createdAt: now,
            expiresAt: now.add(const Duration(hours: 24)),
          );
        }
        return p;
      }).toList();

      // Check if fully compliant
      final isCompliant = finalProofs.every((p) => p.isValid);

      state = state.copyWith(
        proofs: finalProofs,
        isFullyCompliant: isCompliant,
      );
    } catch (e) {
      final errorProofs = state.proofs.map((p) {
        if (p.type == type) {
          return ZkProof(
            id: p.id,
            type: p.type,
            status: ZkProofStatus.error,
            errorMessage: e.toString(),
          );
        }
        return p;
      }).toList();

      state = state.copyWith(proofs: errorProofs);
    }
  }

  Future<void> generateAllProofs() async {
    for (final type in [ZkProofType.sanctions, ZkProofType.riskLow, ZkProofType.kyc]) {
      await generateProof(type);
    }
  }
}

/// Provider
final zkNAFProvider = StateNotifierProvider<ZkNAFNotifier, ZkNAFState>((ref) {
  return ZkNAFNotifier();
});

/// zkNAF Page
class ZkNAFPage extends ConsumerStatefulWidget {
  const ZkNAFPage({super.key});

  @override
  ConsumerState<ZkNAFPage> createState() => _ZkNAFPageState();
}

class _ZkNAFPageState extends ConsumerState<ZkNAFPage> {
  @override
  void initState() {
    super.initState();
    // Load proofs for demo wallet
    Future.microtask(() {
      ref.read(zkNAFProvider.notifier).loadProofs('0x1234...5678');
    });
  }

  @override
  Widget build(BuildContext context) {
    final zkNAFState = ref.watch(zkNAFProvider);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('zkNAF Privacy Proofs'),
        actions: [
          IconButton(
            icon: const Icon(Icons.info_outline),
            onPressed: () => _showInfoDialog(context),
          ),
        ],
      ),
      body: zkNAFState.isLoading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: () => ref.read(zkNAFProvider.notifier).loadProofs(
                    zkNAFState.walletAddress ?? '',
                  ),
              child: SingleChildScrollView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Compliance Status Card
                    _buildComplianceStatusCard(zkNAFState, theme),
                    const SizedBox(height: 24),

                    // FCA Compliance Notice
                    _buildFCANotice(theme),
                    const SizedBox(height: 24),

                    // Proof Cards
                    Text(
                      'Your Privacy Proofs',
                      style: theme.textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 16),

                    ...zkNAFState.proofs.map((proof) => Padding(
                          padding: const EdgeInsets.only(bottom: 12),
                          child: _buildProofCard(proof, theme),
                        )),

                    const SizedBox(height: 24),

                    // Generate All Button
                    if (!zkNAFState.isFullyCompliant)
                      SizedBox(
                        width: double.infinity,
                        child: ElevatedButton.icon(
                          onPressed: () => ref.read(zkNAFProvider.notifier).generateAllProofs(),
                          icon: const Icon(Icons.verified_outlined),
                          label: const Text('Generate All Proofs'),
                          style: ElevatedButton.styleFrom(
                            padding: const EdgeInsets.symmetric(vertical: 16),
                          ),
                        ),
                      ),

                    const SizedBox(height: 32),

                    // How It Works Section
                    _buildHowItWorksSection(theme),
                  ],
                ),
              ),
            ),
    );
  }

  Widget _buildComplianceStatusCard(ZkNAFState state, ThemeData theme) {
    final validProofs = state.proofs.where((p) => p.isValid).length;
    final totalProofs = state.proofs.length;

    return Card(
      elevation: 4,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
          gradient: LinearGradient(
            colors: state.isFullyCompliant
                ? [Colors.green.shade700, Colors.green.shade500]
                : [Colors.orange.shade700, Colors.orange.shade500],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
        ),
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  state.isFullyCompliant ? Icons.verified : Icons.pending_outlined,
                  color: Colors.white,
                  size: 32,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        state.isFullyCompliant ? 'Fully Compliant' : 'Partial Compliance',
                        style: theme.textTheme.titleLarge?.copyWith(
                          color: Colors.white,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      Text(
                        '$validProofs of $totalProofs proofs valid',
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: Colors.white70,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            LinearProgressIndicator(
              value: totalProofs > 0 ? validProofs / totalProofs : 0,
              backgroundColor: Colors.white24,
              valueColor: const AlwaysStoppedAnimation<Color>(Colors.white),
            ),
            const SizedBox(height: 12),
            Text(
              state.isFullyCompliant
                  ? 'You can interact with privacy-preserving DeFi protocols'
                  : 'Generate remaining proofs to unlock full DeFi access',
              style: theme.textTheme.bodySmall?.copyWith(
                color: Colors.white70,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFCANotice(ThemeData theme) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.blue.shade50,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.blue.shade200),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.info_outline, color: Colors.blue.shade700),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'FCA Regulatory Compliance',
                  style: theme.textTheme.titleSmall?.copyWith(
                    color: Colors.blue.shade700,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  'ZK proofs let you prove compliance without revealing personal data. '
                  'AMTTP maintains full records for regulatory disclosure as required by MLR 2017.',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: Colors.blue.shade700,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildProofCard(ZkProof proof, ThemeData theme) {
    final isGenerating = proof.status == ZkProofStatus.generating;

    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: proof.statusColor.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(proof.typeIcon, color: proof.statusColor),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        proof.typeDisplayName,
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      Text(
                        _getStatusText(proof),
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: proof.statusColor,
                        ),
                      ),
                    ],
                  ),
                ),
                if (isGenerating)
                  const SizedBox(
                    width: 24,
                    height: 24,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                else if (proof.status == ZkProofStatus.valid)
                  const Icon(Icons.check_circle, color: Colors.green)
                else
                  TextButton(
                    onPressed: () => ref.read(zkNAFProvider.notifier).generateProof(proof.type),
                    child: const Text('Generate'),
                  ),
              ],
            ),
            if (proof.isValid && proof.proofHash != null) ...[
              const SizedBox(height: 12),
              const Divider(),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Proof Hash',
                          style: theme.textTheme.labelSmall?.copyWith(
                            color: Colors.grey,
                          ),
                        ),
                        Text(
                          '${proof.proofHash!.substring(0, 16)}...${proof.proofHash!.substring(proof.proofHash!.length - 8)}',
                          style: theme.textTheme.bodySmall?.copyWith(
                            fontFamily: 'monospace',
                          ),
                        ),
                      ],
                    ),
                  ),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text(
                        'Expires',
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: Colors.grey,
                        ),
                      ),
                      Text(
                        _formatExpiry(proof.expiresAt),
                        style: theme.textTheme.bodySmall,
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildHowItWorksSection(ThemeData theme) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'How zkNAF Works',
          style: theme.textTheme.titleLarge?.copyWith(
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 16),
        _buildStepCard(
          '1',
          'Generate ZK Proof',
          'Your compliance data is processed locally to create a cryptographic proof.',
          Icons.lock_outlined,
          theme,
        ),
        _buildStepCard(
          '2',
          'Prove Without Revealing',
          'The proof confirms compliance status without exposing personal details.',
          Icons.visibility_off_outlined,
          theme,
        ),
        _buildStepCard(
          '3',
          'On-Chain Verification',
          'DeFi protocols verify your proof on-chain, enabling access.',
          Icons.verified_outlined,
          theme,
        ),
        _buildStepCard(
          '4',
          'FCA Records Maintained',
          'AMTTP keeps full records for regulatory disclosure as required.',
          Icons.article_outlined,
          theme,
        ),
      ],
    );
  }

  Widget _buildStepCard(
    String step,
    String title,
    String description,
    IconData icon,
    ThemeData theme,
  ) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(
              color: theme.primaryColor,
              shape: BoxShape.circle,
            ),
            child: Center(
              child: Text(
                step,
                style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                Text(
                  description,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: Colors.grey.shade600,
                  ),
                ),
              ],
            ),
          ),
          Icon(icon, color: Colors.grey.shade400),
        ],
      ),
    );
  }

  String _getStatusText(ZkProof proof) {
    switch (proof.status) {
      case ZkProofStatus.notGenerated:
        return 'Not generated';
      case ZkProofStatus.generating:
        return 'Generating proof...';
      case ZkProofStatus.valid:
        return 'Valid until ${_formatExpiry(proof.expiresAt)}';
      case ZkProofStatus.expired:
        return 'Expired';
      case ZkProofStatus.revoked:
        return 'Revoked';
      case ZkProofStatus.error:
        return 'Error: ${proof.errorMessage ?? 'Unknown'}';
    }
  }

  String _formatExpiry(DateTime? expiry) {
    if (expiry == null) return 'Unknown';
    final diff = expiry.difference(DateTime.now());
    if (diff.inHours < 1) return '${diff.inMinutes}m';
    if (diff.inHours < 24) return '${diff.inHours}h';
    return '${diff.inDays}d';
  }

  void _showInfoDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('About zkNAF'),
        content: const SingleChildScrollView(
          child: Text(
            'zkNAF (Zero-Knowledge Non-Disclosing Anti-Fraud) allows you to prove '
            'compliance with regulations without revealing your personal information.\n\n'
            'Available Proofs:\n'
            '• Sanctions: Prove you\'re not on any sanctions list\n'
            '• Risk Score: Prove your risk level is acceptable\n'
            '• KYC: Prove you\'ve completed identity verification\n\n'
            'FCA Compliance:\n'
            'While ZK proofs protect your privacy for DeFi interactions, '
            'AMTTP maintains full records as required by MLR 2017 for '
            'regulatory disclosure, SAR filing, and law enforcement requests.',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Got it'),
          ),
        ],
      ),
    );
  }
}
