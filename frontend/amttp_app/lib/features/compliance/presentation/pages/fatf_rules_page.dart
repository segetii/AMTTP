// ignore_for_file: avoid_web_libraries_in_flutter
import 'dart:html' as html;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../../core/theme/app_theme.dart';

/// FATF Rules Page - Links to Next.js compliance tools and Detection Studio
/// Provides quick access to:
/// - FATF Black/Grey Lists (via Next.js)
/// - Country Risk Checker
/// - Detection Studio integration
/// - Compliance Dashboard
class FATFRulesPage extends ConsumerStatefulWidget {
  const FATFRulesPage({super.key});

  @override
  ConsumerState<FATFRulesPage> createState() => _FATFRulesPageState();
}

class _FATFRulesPageState extends ConsumerState<FATFRulesPage> {
  // Use relative URL root for Next.js pages (nginx proxies to Next.js)
  // We'll pass full paths like /compliance or /compliance/fatf-rules directly.
  static const _nextJsBaseUrl = '';
  
  // Quick links to Next.js compliance pages
  final List<_ComplianceLink> _complianceLinks = [
    _ComplianceLink(
      title: 'FATF Rules Dashboard',
      description: 'View FATF Black/Grey lists, check country risk scores',
      icon: Icons.public,
      color: Colors.blue,
      path: '/compliance/fatf-rules',
    ),
    _ComplianceLink(
      title: 'Compliance Overview',
      description: 'Full compliance dashboard with sanctions & monitoring',
      icon: Icons.shield,
      color: Colors.green,
      path: '/compliance',
    ),
    _ComplianceLink(
      title: 'Sanctions Screening',
      description: 'Check addresses against OFAC, EU, UN sanctions lists',
      icon: Icons.gavel,
      color: Colors.orange,
      path: '/compliance', // Sanctions tab in compliance
    ),
    _ComplianceLink(
      title: 'Transaction Reports',
      description: 'View compliance reports and audit trails',
      icon: Icons.assessment,
      color: Colors.purple,
      path: '/reports',
    ),
  ];

  void _openNextJsPage(String path) {
    if (kIsWeb) {
      html.window.open('$_nextJsBaseUrl$path', '_blank');
    }
  }

  void _openDetectionStudio() {
    context.go('/detection-studio');
  }

  void _openComplianceTools() {
    context.go('/compliance');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.darkBg,
      appBar: AppBar(
        title: Row(
          children: [
            Icon(Icons.public, color: AppTheme.primaryBlue),
            const SizedBox(width: 8),
            const Text('FATF Rules & Compliance'),
          ],
        ),
        backgroundColor: AppTheme.darkCard,
        foregroundColor: AppTheme.cleanWhite,
        actions: [
          TextButton.icon(
            onPressed: _openDetectionStudio,
            icon: Icon(Icons.visibility, color: AppTheme.primaryBlue),
            label: Text('Detection Studio', style: TextStyle(color: AppTheme.cleanWhite)),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: Container(
        decoration: const BoxDecoration(gradient: AppTheme.darkGradient),
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header Card
              _buildHeaderCard(),
              const SizedBox(height: 24),
              
              // Quick Actions
              Text(
                'Quick Actions',
                style: TextStyle(
                  color: AppTheme.cleanWhite,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 12),
              _buildQuickActions(),
              const SizedBox(height: 24),
              
              // Compliance Links Grid
              Text(
                'Compliance Tools (Next.js Dashboard)',
                style: TextStyle(
                  color: AppTheme.cleanWhite,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 12),
              _buildComplianceLinksGrid(),
              const SizedBox(height: 24),
              
              // FATF Guidelines Summary
              Text(
                'FATF Compliance Guidelines',
                style: TextStyle(
                  color: AppTheme.cleanWhite,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 12),
              _buildGuidelinesCards(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeaderCard() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [AppTheme.primaryBlue.withOpacity(0.3), AppTheme.darkCard],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppTheme.primaryBlue.withOpacity(0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.security, color: AppTheme.primaryBlue, size: 32),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'FATF Compliance Center',
                      style: TextStyle(
                        color: AppTheme.cleanWhite,
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    Text(
                      'Financial Action Task Force compliance tools',
                      style: TextStyle(color: AppTheme.mutedText),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Text(
            'Access FATF Black/Grey lists, country risk assessments, sanctions screening, '
            'and compliance reporting through our integrated Next.js dashboard.',
            style: TextStyle(color: AppTheme.cleanWhite.withOpacity(0.8)),
          ),
        ],
      ),
    );
  }

  Widget _buildQuickActions() {
    return Row(
      children: [
        Expanded(
          child: _QuickActionButton(
            icon: Icons.visibility,
            label: 'Detection Studio',
            color: AppTheme.primaryBlue,
            onTap: _openDetectionStudio,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _QuickActionButton(
            icon: Icons.shield,
            label: 'Compliance Tools',
            color: Colors.green,
            onTap: _openComplianceTools,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _QuickActionButton(
            icon: Icons.open_in_new,
            label: 'Full Dashboard',
            color: Colors.purple,
            onTap: () => _openNextJsPage('/compliance/fatf-rules'),
          ),
        ),
      ],
    );
  }

  Widget _buildComplianceLinksGrid() {
    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        childAspectRatio: 1.5,
        crossAxisSpacing: 12,
        mainAxisSpacing: 12,
      ),
      itemCount: _complianceLinks.length,
      itemBuilder: (context, index) {
        final link = _complianceLinks[index];
        return _ComplianceLinkCard(
          link: link,
          onTap: () => _openNextJsPage(link.path),
        );
      },
    );
  }

  Widget _buildGuidelinesCards() {
    return Column(
      children: [
        _GuidelineCard(
          title: 'FATF Black List',
          subtitle: 'High-Risk Jurisdictions',
          icon: Icons.block,
          color: Colors.red,
          items: [
            'All transactions BLOCKED',
            'Automatic SAR filing required',
            'Risk score: 100/100',
            'No exceptions allowed',
          ],
        ),
        const SizedBox(height: 12),
        _GuidelineCard(
          title: 'FATF Grey List',
          subtitle: 'Increased Monitoring',
          icon: Icons.warning,
          color: Colors.orange,
          items: [
            'Enhanced due diligence required',
            'Escrow for large transactions',
            '24-48 hour review period',
            'Risk score: +40 points',
          ],
        ),
        const SizedBox(height: 12),
        _GuidelineCard(
          title: 'Travel Rule (Rec. 16)',
          subtitle: 'Cross-border Requirements',
          icon: Icons.flight,
          color: Colors.blue,
          items: [
            'Threshold: £840 / €1,000',
            'Originator info required',
            'Beneficiary info required',
            'VASP-to-VASP verification',
          ],
        ),
      ],
    );
  }
}

class _ComplianceLink {
  final String title;
  final String description;
  final IconData icon;
  final Color color;
  final String path;

  _ComplianceLink({
    required this.title,
    required this.description,
    required this.icon,
    required this.color,
    required this.path,
  });
}

class _QuickActionButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  const _QuickActionButton({
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: color.withOpacity(0.2),
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 12),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: color.withOpacity(0.3)),
          ),
          child: Column(
            children: [
              Icon(icon, color: color, size: 28),
              const SizedBox(height: 8),
              Text(
                label,
                style: TextStyle(color: AppTheme.cleanWhite, fontSize: 12),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ComplianceLinkCard extends StatelessWidget {
  final _ComplianceLink link;
  final VoidCallback onTap;

  const _ComplianceLinkCard({
    required this.link,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppTheme.darkCard,
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: link.color.withOpacity(0.3)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(link.icon, color: link.color, size: 24),
                  const Spacer(),
                  Icon(Icons.open_in_new, color: AppTheme.mutedText, size: 16),
                ],
              ),
              const Spacer(),
              Text(
                link.title,
                style: TextStyle(
                  color: AppTheme.cleanWhite,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                link.description,
                style: TextStyle(color: AppTheme.mutedText, fontSize: 11),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _GuidelineCard extends StatelessWidget {
  final String title;
  final String subtitle;
  final IconData icon;
  final Color color;
  final List<String> items;

  const _GuidelineCard({
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.color,
    required this.items,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkCard,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: color.withOpacity(0.2),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(icon, color: color, size: 24),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: TextStyle(
                    color: color,
                    fontWeight: FontWeight.bold,
                    fontSize: 16,
                  ),
                ),
                Text(subtitle, style: TextStyle(color: AppTheme.mutedText, fontSize: 12)),
                const SizedBox(height: 8),
                ...items.map((item) => Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Row(
                    children: [
                      Icon(Icons.check_circle, color: color, size: 14),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          item,
                          style: TextStyle(color: AppTheme.cleanWhite, fontSize: 12),
                        ),
                      ),
                    ],
                  ),
                )),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
