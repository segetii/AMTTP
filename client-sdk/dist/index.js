"use strict";
/**
 * AMTTP Client SDK
 *
 * A comprehensive SDK for interacting with the AMTTP (Advanced Money Transfer Transaction Protocol)
 * backend services. Provides regulatory-compliant transaction processing with DQN-based risk scoring.
 *
 * @packageDocumentation
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.EventEmitter = exports.AMTTPErrorCode = exports.AMTTPError = exports.MEVProtection = exports.LabelService = exports.MonitoringService = exports.EDDService = exports.PEPService = exports.WebhookService = exports.BulkService = exports.ReputationService = exports.DisputeService = exports.PolicyService = exports.TransactionService = exports.KYCService = exports.RiskService = exports.AMTTPClient = void 0;
// Main client export
var client_1 = require("./client");
Object.defineProperty(exports, "AMTTPClient", { enumerable: true, get: function () { return client_1.AMTTPClient; } });
// Service exports with specific types
var risk_1 = require("./services/risk");
Object.defineProperty(exports, "RiskService", { enumerable: true, get: function () { return risk_1.RiskService; } });
var kyc_1 = require("./services/kyc");
Object.defineProperty(exports, "KYCService", { enumerable: true, get: function () { return kyc_1.KYCService; } });
var transaction_1 = require("./services/transaction");
Object.defineProperty(exports, "TransactionService", { enumerable: true, get: function () { return transaction_1.TransactionService; } });
var policy_1 = require("./services/policy");
Object.defineProperty(exports, "PolicyService", { enumerable: true, get: function () { return policy_1.PolicyService; } });
var dispute_1 = require("./services/dispute");
Object.defineProperty(exports, "DisputeService", { enumerable: true, get: function () { return dispute_1.DisputeService; } });
var reputation_1 = require("./services/reputation");
Object.defineProperty(exports, "ReputationService", { enumerable: true, get: function () { return reputation_1.ReputationService; } });
var bulk_1 = require("./services/bulk");
Object.defineProperty(exports, "BulkService", { enumerable: true, get: function () { return bulk_1.BulkService; } });
var webhook_1 = require("./services/webhook");
Object.defineProperty(exports, "WebhookService", { enumerable: true, get: function () { return webhook_1.WebhookService; } });
var pep_1 = require("./services/pep");
Object.defineProperty(exports, "PEPService", { enumerable: true, get: function () { return pep_1.PEPService; } });
var edd_1 = require("./services/edd");
Object.defineProperty(exports, "EDDService", { enumerable: true, get: function () { return edd_1.EDDService; } });
var monitoring_1 = require("./services/monitoring");
Object.defineProperty(exports, "MonitoringService", { enumerable: true, get: function () { return monitoring_1.MonitoringService; } });
var label_1 = require("./services/label");
Object.defineProperty(exports, "LabelService", { enumerable: true, get: function () { return label_1.LabelService; } });
var protection_1 = require("./mev/protection");
Object.defineProperty(exports, "MEVProtection", { enumerable: true, get: function () { return protection_1.MEVProtection; } });
var errors_1 = require("./errors");
Object.defineProperty(exports, "AMTTPError", { enumerable: true, get: function () { return errors_1.AMTTPError; } });
Object.defineProperty(exports, "AMTTPErrorCode", { enumerable: true, get: function () { return errors_1.AMTTPErrorCode; } });
var events_1 = require("./events");
Object.defineProperty(exports, "EventEmitter", { enumerable: true, get: function () { return events_1.EventEmitter; } });
//# sourceMappingURL=index.js.map