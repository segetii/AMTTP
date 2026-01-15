// UI Integrity Protection Tests
// Tests for Flutter integrity protection system
// Validates all 5 protection layers against attack scenarios

import 'package:flutter_test/flutter_test.dart';
import 'package:amttp_app/core/security/ui_integrity_service.dart';

void main() {
  group('UIIntegrityService', () {
    test('calculateHash produces consistent SHA-256', () {
      const input = 'test_string';
      final hash1 = UIIntegrityService.calculateHash(input);
      final hash2 = UIIntegrityService.calculateHash(input);
      
      expect(hash1, equals(hash2));
      expect(hash1.length, equals(64)); // SHA-256 produces 64 hex characters
    });

    test('calculateHash produces different hashes for different inputs', () {
      const input1 = 'test_string_1';
      const input2 = 'test_string_2';
      
      final hash1 = UIIntegrityService.calculateHash(input1);
      final hash2 = UIIntegrityService.calculateHash(input2);
      
      expect(hash1, isNot(equals(hash2)));
    });
  });

  group('ComponentIntegrity', () {
    test('captureComponentIntegrity creates valid snapshot', () {
      final integrity = UIIntegrityService.captureComponentIntegrity(
        componentId: 'TestComponent',
        state: {
          'amount': '1.5',
          'recipient': '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb',
        },
        handlers: ['onSubmit', 'onCancel'],
      );

      expect(integrity.componentId, equals('TestComponent'));
      expect(integrity.stateHash.length, equals(64));
      expect(integrity.handlerHash.length, equals(64));
      expect(integrity.timestamp, isNotNull);
    });

    test('same state produces same hash', () {
      final state = {
        'amount': '1.5',
        'recipient': '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb',
      };
      final handlers = ['onSubmit', 'onCancel'];

      final integrity1 = UIIntegrityService.captureComponentIntegrity(
        componentId: 'TestComponent',
        state: state,
        handlers: handlers,
      );

      final integrity2 = UIIntegrityService.captureComponentIntegrity(
        componentId: 'TestComponent',
        state: state,
        handlers: handlers,
      );

      expect(integrity1.stateHash, equals(integrity2.stateHash));
      expect(integrity1.handlerHash, equals(integrity2.handlerHash));
    });

    test('different state produces different hash', () {
      final integrity1 = UIIntegrityService.captureComponentIntegrity(
        componentId: 'TestComponent',
        state: {'amount': '1.5'},
        handlers: ['onSubmit'],
      );

      final integrity2 = UIIntegrityService.captureComponentIntegrity(
        componentId: 'TestComponent',
        state: {'amount': '2.5'}, // Changed amount
        handlers: ['onSubmit'],
      );

      expect(integrity1.stateHash, isNot(equals(integrity2.stateHash)));
    });

    test('handler order does not affect hash (sorted)', () {
      final state = {'amount': '1.5'};

      final integrity1 = UIIntegrityService.captureComponentIntegrity(
        componentId: 'TestComponent',
        state: state,
        handlers: ['onSubmit', 'onCancel', 'onBack'],
      );

      final integrity2 = UIIntegrityService.captureComponentIntegrity(
        componentId: 'TestComponent',
        state: state,
        handlers: ['onCancel', 'onBack', 'onSubmit'], // Different order
      );

      // Should be same because handlers are sorted before hashing
      expect(integrity1.handlerHash, equals(integrity2.handlerHash));
    });

    test('isStale returns true for old snapshots', () {
      final oldTimestamp = DateTime.now().subtract(const Duration(seconds: 61));
      final integrity = ComponentIntegrity(
        componentId: 'TestComponent',
        stateHash: 'abc123',
        handlerHash: 'def456',
        timestamp: oldTimestamp,
      );

      expect(integrity.isStale, isTrue);
    });

    test('isStale returns false for recent snapshots', () {
      final recentTimestamp = DateTime.now().subtract(const Duration(seconds: 30));
      final integrity = ComponentIntegrity(
        componentId: 'TestComponent',
        stateHash: 'abc123',
        handlerHash: 'def456',
        timestamp: recentTimestamp,
      );

      expect(integrity.isStale, isFalse);
    });
  });

  group('TransactionIntent', () {
    test('createTransactionIntent generates valid intent', () {
      final intent = UIIntegrityService.createTransactionIntent(
        from: '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb',
        to: '0x8ba1f109551bD432803012645Ac136ddd64DBA72',
        amount: '1.5',
        currency: 'ETH',
        memo: 'Test payment',
      );

      expect(intent.from, contains('0x'));
      expect(intent.to, contains('0x'));
      expect(intent.amount, equals('1.5'));
      expect(intent.currency, equals('ETH'));
      expect(intent.memo, equals('Test payment'));
    });

    test('getIntentHash produces consistent hash', () {
      final intent1 = TransactionIntent(
        from: '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb',
        to: '0x8ba1f109551bD432803012645Ac136ddd64DBA72',
        amount: '1.5',
        timestamp: DateTime(2026, 1, 1, 12, 0, 0),
      );

      final intent2 = TransactionIntent(
        from: '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb',
        to: '0x8ba1f109551bD432803012645Ac136ddd64DBA72',
        amount: '1.5',
        timestamp: DateTime(2026, 1, 1, 12, 0, 0),
      );

      final hash1 = intent1.getIntentHash();
      final hash2 = intent2.getIntentHash();

      expect(hash1, equals(hash2));
      expect(hash1, startsWith('0x'));
    });

    test('getIntentHash changes when amount changes (tamper detection)', () {
      final baseTimestamp = DateTime(2026, 1, 1, 12, 0, 0);

      final intent1 = TransactionIntent(
        from: '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb',
        to: '0x8ba1f109551bD432803012645Ac136ddd64DBA72',
        amount: '1.5',
        timestamp: baseTimestamp,
      );

      final intent2 = TransactionIntent(
        from: '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb',
        to: '0x8ba1f109551bD432803012645Ac136ddd64DBA72',
        amount: '100.0', // Attacker changed amount!
        timestamp: baseTimestamp,
      );

      final hash1 = intent1.getIntentHash();
      final hash2 = intent2.getIntentHash();

      expect(hash1, isNot(equals(hash2)));
    });

    test('addresses are normalized to lowercase', () {
      final intent = TransactionIntent(
        from: '0x742D35CC6634C0532925A3B844BC9E7595F0BEB', // Mixed case
        to: '0x8BA1F109551BD432803012645AC136DDD64DBA72', // Mixed case
        amount: '1.5',
      );

      final canonical = intent.toCanonicalJson();
      expect(canonical['from'], equals('0x742d35cc6634c0532925a3b844bc9e7595f0beb'));
      expect(canonical['to'], equals('0x8ba1f109551bd432803012645ac136ddd64dba72'));
    });

    test('verifyIntentHash detects tampering', () {
      final intent = TransactionIntent(
        from: '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb',
        to: '0x8ba1f109551bD432803012645Ac136ddd64DBA72',
        amount: '1.5',
        timestamp: DateTime(2026, 1, 1, 12, 0, 0),
      );

      final correctHash = intent.getIntentHash();
      final fakeHash = '0x1234567890abcdef';

      expect(
        UIIntegrityService.verifyIntentHash(
          intent: intent,
          expectedHash: correctHash,
        ),
        isTrue,
      );

      expect(
        UIIntegrityService.verifyIntentHash(
          intent: intent,
          expectedHash: fakeHash,
        ),
        isFalse,
      );
    });
  });

  group('Integrity Validation', () {
    test('validateIntegrity detects state hash mismatch', () {
      final trusted = UIIntegrityService.captureComponentIntegrity(
        componentId: 'TestComponent',
        state: {'amount': '1.5'},
        handlers: ['onSubmit'],
      );

      final current = UIIntegrityService.captureComponentIntegrity(
        componentId: 'TestComponent',
        state: {'amount': '100.0'}, // Tampered!
        handlers: ['onSubmit'],
      );

      final violations = UIIntegrityService.validateIntegrity(
        current: current,
        trusted: trusted,
      );

      expect(violations, isNotEmpty);
      expect(
        violations.any((v) => v.type == ViolationType.hashMismatch),
        isTrue,
      );
      expect(
        violations.any((v) => v.severity == ViolationSeverity.high),
        isTrue,
      );
    });

    test('validateIntegrity detects handler hash mismatch (code injection)', () {
      final trusted = UIIntegrityService.captureComponentIntegrity(
        componentId: 'TestComponent',
        state: {'amount': '1.5'},
        handlers: ['onSubmit', 'onCancel'],
      );

      final current = UIIntegrityService.captureComponentIntegrity(
        componentId: 'TestComponent',
        state: {'amount': '1.5'},
        handlers: ['onSubmit', 'onCancel', 'onMalicious'], // Injected!
      );

      final violations = UIIntegrityService.validateIntegrity(
        current: current,
        trusted: trusted,
      );

      expect(violations, isNotEmpty);
      expect(
        violations.any((v) => v.type == ViolationType.hashMismatch),
        isTrue,
      );
      expect(
        violations.any((v) => v.severity == ViolationSeverity.critical),
        isTrue,
      );
      expect(
        violations.any((v) => v.details.contains('code injection')),
        isTrue,
      );
    });

    test('validateIntegrity detects stale timestamp', () {
      final oldTimestamp = DateTime.now().subtract(const Duration(seconds: 61));
      final staleSnapshot = ComponentIntegrity(
        componentId: 'TestComponent',
        stateHash: 'abc123',
        handlerHash: 'def456',
        timestamp: oldTimestamp,
      );

      final violations = UIIntegrityService.validateIntegrity(
        current: staleSnapshot,
        trusted: null,
      );

      expect(violations, isNotEmpty);
      expect(
        violations.any((v) => v.type == ViolationType.staleTimestamp),
        isTrue,
      );
      expect(
        violations.any((v) => v.severity == ViolationSeverity.medium),
        isTrue,
      );
    });

    test('validateIntegrity passes for matching hashes', () {
      final trusted = UIIntegrityService.captureComponentIntegrity(
        componentId: 'TestComponent',
        state: {'amount': '1.5'},
        handlers: ['onSubmit'],
      );

      final current = UIIntegrityService.captureComponentIntegrity(
        componentId: 'TestComponent',
        state: {'amount': '1.5'},
        handlers: ['onSubmit'],
      );

      final violations = UIIntegrityService.validateIntegrity(
        current: current,
        trusted: trusted,
      );

      // Should only have stale timestamp if any
      expect(
        violations.every((v) => v.type != ViolationType.hashMismatch),
        isTrue,
      );
    });
  });

  group('IntegrityReport', () {
    test('generateReport creates complete report', () {
      final report = UIIntegrityService.generateReport(
        componentId: 'TestComponent',
        state: {'amount': '1.5'},
        handlers: ['onSubmit'],
      );

      expect(report.componentId, equals('TestComponent'));
      expect(report.stateHash, isNotEmpty);
      expect(report.handlerHash, isNotEmpty);
      expect(report.timestamp, isNotNull);
      expect(report.violations, isA<List<IntegrityViolation>>());
    });

    test('generateReport includes violations when hashes mismatch', () {
      final trusted = UIIntegrityService.captureComponentIntegrity(
        componentId: 'TestComponent',
        state: {'amount': '1.5'},
        handlers: ['onSubmit'],
      );

      final report = UIIntegrityService.generateReport(
        componentId: 'TestComponent',
        state: {'amount': '100.0'}, // Tampered
        handlers: ['onSubmit'],
        trustedSnapshot: trusted,
      );

      expect(report.violations, isNotEmpty);
    });

    test('toJson produces valid JSON', () {
      final report = UIIntegrityService.generateReport(
        componentId: 'TestComponent',
        state: {'amount': '1.5'},
        handlers: ['onSubmit'],
      );

      final json = report.toJson();

      expect(json['componentId'], equals('TestComponent'));
      expect(json['stateHash'], isA<String>());
      expect(json['handlerHash'], isA<String>());
      expect(json['timestamp'], isA<String>());
      expect(json['violations'], isA<List>());
    });
  });

  group('Attack Scenarios', () {
    test('Scenario 1: Amount manipulation attack (Bybit-style)', () {
      // Attacker tries to display 1.0 ETH but send 100 ETH
      
      // 1. User initiates 1.0 ETH transfer
      final legitimateIntent = TransactionIntent(
        from: '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb',
        to: '0x8ba1f109551bD432803012645Ac136ddd64DBA72',
        amount: '1.0',
      );
      final legitimateHash = legitimateIntent.getIntentHash();

      // 2. Attacker manipulates UI to send 100 ETH
      final maliciousIntent = TransactionIntent(
        from: '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb',
        to: '0x8ba1f109551bD432803012645Ac136ddd64DBA72',
        amount: '100.0', // Attacker changed amount
      );

      // 3. Server validates intent hash
      final verified = UIIntegrityService.verifyIntentHash(
        intent: maliciousIntent,
        expectedHash: legitimateHash,
      );

      // Attack should be BLOCKED
      expect(verified, isFalse);
    });

    test('Scenario 2: Handler injection attack', () {
      // Trusted state
      final trusted = UIIntegrityService.captureComponentIntegrity(
        componentId: 'SecureTransfer',
        state: {'amount': '1.5', 'recipient': '0xRecipient'},
        handlers: ['onSubmit', 'onCancel'],
      );

      // Attacker injects malicious handler
      final compromised = UIIntegrityService.captureComponentIntegrity(
        componentId: 'SecureTransfer',
        state: {'amount': '1.5', 'recipient': '0xRecipient'},
        handlers: ['onSubmit', 'onCancel', 'onStealFunds'], // Injected!
      );

      final violations = UIIntegrityService.validateIntegrity(
        current: compromised,
        trusted: trusted,
      );

      // Attack should be DETECTED
      expect(violations, isNotEmpty);
      expect(
        violations.any((v) => v.severity == ViolationSeverity.critical),
        isTrue,
      );
    });

    test('Scenario 3: Recipient address substitution', () {
      final timestamp = DateTime(2026, 1, 1, 12, 0, 0);

      // User's intended recipient
      final legitimateIntent = TransactionIntent(
        from: '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb',
        to: '0x8ba1f109551bD432803012645Ac136ddd64DBA72',
        amount: '1.0',
        timestamp: timestamp,
      );
      final legitimateHash = legitimateIntent.getIntentHash();

      // Attacker's wallet
      final attackerIntent = TransactionIntent(
        from: '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb',
        to: '0xAttackerWallet000000000000000000000000',
        amount: '1.0',
        timestamp: timestamp,
      );

      // Server validates
      final verified = UIIntegrityService.verifyIntentHash(
        intent: attackerIntent,
        expectedHash: legitimateHash,
      );

      // Attack should be BLOCKED
      expect(verified, isFalse);
    });

    test('Scenario 4: Stale UI attack (replay old page)', () {
      // Attacker serves old cached page from 2 minutes ago
      final oldTimestamp = DateTime.now().subtract(const Duration(minutes: 2));
      final staleSnapshot = ComponentIntegrity(
        componentId: 'SecureTransfer',
        stateHash: 'valid_hash',
        handlerHash: 'valid_hash',
        timestamp: oldTimestamp,
      );

      final violations = UIIntegrityService.validateIntegrity(
        current: staleSnapshot,
        trusted: null,
      );

      // Attack should be DETECTED
      expect(violations, isNotEmpty);
      expect(
        violations.any((v) => v.type == ViolationType.staleTimestamp),
        isTrue,
      );
    });
  });

  group('Utility Functions', () {
    test('formatIntentSummary produces readable output', () {
      final intent = TransactionIntent(
        from: '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb',
        to: '0x8ba1f109551bD432803012645Ac136ddd64DBA72',
        amount: '1.5',
        currency: 'ETH',
        memo: 'Test payment',
      );

      final summary = UIIntegrityService.formatIntentSummary(intent);

      expect(summary, contains('Transaction Details'));
      expect(summary, contains('From:'));
      expect(summary, contains('To:'));
      expect(summary, contains('Amount: 1.5 ETH'));
      expect(summary, contains('Memo: Test payment'));
    });
  });
}
