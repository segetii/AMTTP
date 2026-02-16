import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../security/tee_attestation_service.dart';

/// A confirmation dialog for critical actions that require TEE attestation.
///
/// Shows action details, performs attestation, and returns the result.
/// If the action requires multisig, shows an additional notice.
///
/// Usage:
///   final result = await CriticalActionDialog.show(
///     context: context,
///     ref: ref,
///     actionId: 'freeze_address',
///     roleLevel: 4,
///     details: {'address': '0x1234...'},
///   );
///   if (result?.success == true) { /* proceed */ }
class CriticalActionDialog extends ConsumerStatefulWidget {
  final String actionId;
  final int roleLevel;
  final Map<String, String> details;

  const CriticalActionDialog({
    super.key,
    required this.actionId,
    required this.roleLevel,
    this.details = const {},
  });

  /// Show the dialog and return the attestation result (null if cancelled)
  static Future<AttestationResult?> show({
    required BuildContext context,
    required WidgetRef ref,
    required String actionId,
    required int roleLevel,
    Map<String, String> details = const {},
  }) {
    return showDialog<AttestationResult>(
      context: context,
      barrierDismissible: false,
      builder: (_) => CriticalActionDialog(
        actionId: actionId,
        roleLevel: roleLevel,
        details: details,
      ),
    );
  }

  @override
  ConsumerState<CriticalActionDialog> createState() =>
      _CriticalActionDialogState();
}

class _CriticalActionDialogState extends ConsumerState<CriticalActionDialog> {
  bool _isProcessing = false;
  bool _showPinEntry = false;
  String? _error;
  final _pinController = TextEditingController();

  CriticalAction? get _action =>
      TeeAttestationService.findAction(widget.actionId);

  @override
  void dispose() {
    _pinController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final action = _action;
    if (action == null) {
      return AlertDialog(
        backgroundColor: const Color(0xFF1A1A2E),
        title: const Text('Error', style: TextStyle(color: Colors.red)),
        content: Text(
          'Unknown action: ${widget.actionId}',
          style: const TextStyle(color: Colors.white70),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Close'),
          ),
        ],
      );
    }

    return AlertDialog(
      backgroundColor: const Color(0xFF1A1A2E),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(
          color: _error != null
              ? Colors.red.withOpacity(0.5)
              : const Color(0xFFF59E0B).withOpacity(0.3),
        ),
      ),
      title: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: const Color(0xFFF59E0B).withOpacity(0.2),
              borderRadius: BorderRadius.circular(8),
            ),
            child: const Icon(
              Icons.shield_outlined,
              color: Color(0xFFF59E0B),
              size: 24,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'CRITICAL ACTION',
                  style: TextStyle(
                    color: Color(0xFFF59E0B),
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.5,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  action.label,
                  style: const TextStyle(color: Colors.white, fontSize: 18),
                ),
              ],
            ),
          ),
        ],
      ),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Description
          Text(
            action.description,
            style: const TextStyle(color: Colors.white54, fontSize: 14),
          ),
          const SizedBox(height: 16),

          // Action details
          if (widget.details.isNotEmpty) ...[
            ...widget.details.entries.map((e) => Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Row(
                    children: [
                      Text(
                        '${e.key}: ',
                        style: const TextStyle(
                            color: Colors.white38, fontSize: 12),
                      ),
                      Expanded(
                        child: Text(
                          e.value,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 12,
                            fontFamily: 'monospace',
                          ),
                        ),
                      ),
                    ],
                  ),
                )),
            const SizedBox(height: 16),
          ],

          // Security requirements
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.05),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Security Requirements',
                  style: TextStyle(
                    color: Colors.white70,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 8),
                _buildRequirement(
                  'Role R${action.minRole}+',
                  widget.roleLevel >= action.minRole,
                ),
                if (action.requiresTEE)
                  _buildRequirement('Hardware attestation', false,
                      pending: true),
                if (action.requiresMultisig)
                  _buildRequirement('Multisig approval required', false,
                      pending: true),
              ],
            ),
          ),

          // PIN entry fallback
          if (_showPinEntry) ...[
            const SizedBox(height: 16),
            const Text(
              'Hardware attestation unavailable. Enter your PIN to confirm:',
              style: TextStyle(color: Colors.white54, fontSize: 12),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _pinController,
              obscureText: true,
              keyboardType: TextInputType.number,
              maxLength: 6,
              style: const TextStyle(color: Colors.white, letterSpacing: 8),
              textAlign: TextAlign.center,
              decoration: InputDecoration(
                counterText: '',
                filled: true,
                fillColor: Colors.white.withOpacity(0.05),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                  borderSide: BorderSide(color: Colors.white.withOpacity(0.1)),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                  borderSide: const BorderSide(color: Color(0xFF60A5FA)),
                ),
              ),
            ),
          ],

          // Error
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(
              _error!,
              style: const TextStyle(color: Colors.red, fontSize: 12),
            ),
          ],
        ],
      ),
      actions: [
        TextButton(
          onPressed: _isProcessing ? null : () => Navigator.pop(context, null),
          child: Text(
            'Cancel',
            style: TextStyle(color: Colors.white.withOpacity(0.5)),
          ),
        ),
        ElevatedButton(
          onPressed: _isProcessing ? null : _onConfirm,
          style: ElevatedButton.styleFrom(
            backgroundColor: const Color(0xFFF59E0B),
            foregroundColor: Colors.black,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(8),
            ),
          ),
          child: _isProcessing
              ? const SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(
                      strokeWidth: 2, color: Colors.black),
                )
              : Text(_showPinEntry ? 'Confirm with PIN' : 'Authenticate'),
        ),
      ],
    );
  }

  Widget _buildRequirement(String label, bool satisfied,
      {bool pending = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Icon(
            satisfied
                ? Icons.check_circle_rounded
                : pending
                    ? Icons.radio_button_unchecked
                    : Icons.cancel_rounded,
            color: satisfied
                ? const Color(0xFF10B981)
                : pending
                    ? Colors.white38
                    : Colors.red,
            size: 16,
          ),
          const SizedBox(width: 8),
          Text(
            label,
            style: TextStyle(
              color: satisfied ? const Color(0xFF10B981) : Colors.white54,
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _onConfirm() async {
    setState(() {
      _isProcessing = true;
      _error = null;
    });

    final tee = ref.read(teeServiceProvider);
    final result =
        await tee.gateCriticalAction(widget.actionId, widget.roleLevel);

    if (result.success) {
      if (mounted) Navigator.pop(context, result);
      return;
    }

    // If needs PIN fallback, show PIN entry
    if (result.error == 'NEEDS_PIN_CONFIRMATION') {
      if (_showPinEntry && _pinController.text.length >= 4) {
        // PIN entered — in production, verify against stored hash
        // For now, accept any 4+ digit PIN as fallback
        if (mounted) {
          Navigator.pop(
              context,
              AttestationResult(
                success: true,
                method: 'fallback-pin',
                timestamp: DateTime.now().millisecondsSinceEpoch,
              ));
        }
        return;
      }
      setState(() {
        _showPinEntry = true;
        _isProcessing = false;
      });
      return;
    }

    setState(() {
      _error = result.error ?? 'Attestation failed';
      _isProcessing = false;
    });
  }
}
