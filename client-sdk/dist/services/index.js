"use strict";
/**
 * Services index - re-exports all service classes
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.LabelService = exports.MonitoringService = exports.EDDService = exports.PEPService = exports.WebhookService = exports.BulkService = exports.ReputationService = exports.DisputeService = exports.PolicyService = exports.TransactionService = exports.KYCService = exports.RiskService = exports.BaseService = void 0;
var base_1 = require("./base");
Object.defineProperty(exports, "BaseService", { enumerable: true, get: function () { return base_1.BaseService; } });
var risk_1 = require("./risk");
Object.defineProperty(exports, "RiskService", { enumerable: true, get: function () { return risk_1.RiskService; } });
var kyc_1 = require("./kyc");
Object.defineProperty(exports, "KYCService", { enumerable: true, get: function () { return kyc_1.KYCService; } });
var transaction_1 = require("./transaction");
Object.defineProperty(exports, "TransactionService", { enumerable: true, get: function () { return transaction_1.TransactionService; } });
var policy_1 = require("./policy");
Object.defineProperty(exports, "PolicyService", { enumerable: true, get: function () { return policy_1.PolicyService; } });
var dispute_1 = require("./dispute");
Object.defineProperty(exports, "DisputeService", { enumerable: true, get: function () { return dispute_1.DisputeService; } });
var reputation_1 = require("./reputation");
Object.defineProperty(exports, "ReputationService", { enumerable: true, get: function () { return reputation_1.ReputationService; } });
var bulk_1 = require("./bulk");
Object.defineProperty(exports, "BulkService", { enumerable: true, get: function () { return bulk_1.BulkService; } });
var webhook_1 = require("./webhook");
Object.defineProperty(exports, "WebhookService", { enumerable: true, get: function () { return webhook_1.WebhookService; } });
var pep_1 = require("./pep");
Object.defineProperty(exports, "PEPService", { enumerable: true, get: function () { return pep_1.PEPService; } });
var edd_1 = require("./edd");
Object.defineProperty(exports, "EDDService", { enumerable: true, get: function () { return edd_1.EDDService; } });
var monitoring_1 = require("./monitoring");
Object.defineProperty(exports, "MonitoringService", { enumerable: true, get: function () { return monitoring_1.MonitoringService; } });
var label_1 = require("./label");
Object.defineProperty(exports, "LabelService", { enumerable: true, get: function () { return label_1.LabelService; } });
//# sourceMappingURL=index.js.map