"use strict";
var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// src/index.ts
var index_exports = {};
__export(index_exports, {
  AMTTPClient: () => AMTTPClient,
  AMTTPError: () => AMTTPError,
  AMTTPErrorCode: () => AMTTPErrorCode,
  BulkService: () => BulkService,
  ComplianceService: () => ComplianceService,
  DashboardService: () => DashboardService,
  DisputeService: () => DisputeService,
  EDDService: () => EDDService,
  EventEmitter: () => EventEmitter,
  ExplainabilityService: () => ExplainabilityService,
  GeographicRiskService: () => GeographicRiskService,
  GovernanceService: () => GovernanceService,
  IntegrityService: () => IntegrityService,
  KYCService: () => KYCService,
  LabelService: () => LabelService,
  MEVProtection: () => MEVProtection,
  MonitoringService: () => MonitoringService,
  PEPService: () => PEPService,
  PolicyService: () => PolicyService,
  ReputationService: () => ReputationService,
  RiskService: () => RiskService,
  SanctionsService: () => SanctionsService,
  TransactionService: () => TransactionService,
  WebhookService: () => WebhookService
});
module.exports = __toCommonJS(index_exports);

// src/client.ts
var import_axios = __toESM(require("axios"));

// src/errors.ts
var AMTTPErrorCode = /* @__PURE__ */ ((AMTTPErrorCode2) => {
  AMTTPErrorCode2["NETWORK_ERROR"] = "NETWORK_ERROR";
  AMTTPErrorCode2["TIMEOUT"] = "TIMEOUT";
  AMTTPErrorCode2["UNAUTHORIZED"] = "UNAUTHORIZED";
  AMTTPErrorCode2["FORBIDDEN"] = "FORBIDDEN";
  AMTTPErrorCode2["INVALID_ADDRESS"] = "INVALID_ADDRESS";
  AMTTPErrorCode2["INVALID_AMOUNT"] = "INVALID_AMOUNT";
  AMTTPErrorCode2["INVALID_PARAMETERS"] = "INVALID_PARAMETERS";
  AMTTPErrorCode2["HIGH_RISK_BLOCKED"] = "HIGH_RISK_BLOCKED";
  AMTTPErrorCode2["SANCTIONED_ADDRESS"] = "SANCTIONED_ADDRESS";
  AMTTPErrorCode2["POLICY_VIOLATION"] = "POLICY_VIOLATION";
  AMTTPErrorCode2["KYC_REQUIRED"] = "KYC_REQUIRED";
  AMTTPErrorCode2["EDD_REQUIRED"] = "EDD_REQUIRED";
  AMTTPErrorCode2["INSUFFICIENT_BALANCE"] = "INSUFFICIENT_BALANCE";
  AMTTPErrorCode2["TRANSACTION_FAILED"] = "TRANSACTION_FAILED";
  AMTTPErrorCode2["ESCROW_REQUIRED"] = "ESCROW_REQUIRED";
  AMTTPErrorCode2["DISPUTE_NOT_FOUND"] = "DISPUTE_NOT_FOUND";
  AMTTPErrorCode2["EVIDENCE_REJECTED"] = "EVIDENCE_REJECTED";
  AMTTPErrorCode2["NOT_FOUND"] = "NOT_FOUND";
  AMTTPErrorCode2["RATE_LIMITED"] = "RATE_LIMITED";
  AMTTPErrorCode2["SERVER_ERROR"] = "SERVER_ERROR";
  AMTTPErrorCode2["UNKNOWN"] = "UNKNOWN";
  return AMTTPErrorCode2;
})(AMTTPErrorCode || {});
var AMTTPError = class _AMTTPError extends Error {
  constructor(message, code = "UNKNOWN" /* UNKNOWN */, statusCode, details) {
    super(message);
    this.name = "AMTTPError";
    this.code = code;
    this.statusCode = statusCode;
    this.details = details;
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, _AMTTPError);
    }
  }
  /**
   * Create an error from an API response
   */
  static fromResponse(response) {
    const message = response.data?.message || "An error occurred";
    let code = "UNKNOWN" /* UNKNOWN */;
    switch (response.status) {
      case 400:
        code = "INVALID_PARAMETERS" /* INVALID_PARAMETERS */;
        break;
      case 401:
        code = "UNAUTHORIZED" /* UNAUTHORIZED */;
        break;
      case 403:
        code = response.data?.code === "SANCTIONED" ? "SANCTIONED_ADDRESS" /* SANCTIONED_ADDRESS */ : "FORBIDDEN" /* FORBIDDEN */;
        break;
      case 404:
        code = "NOT_FOUND" /* NOT_FOUND */;
        break;
      case 429:
        code = "RATE_LIMITED" /* RATE_LIMITED */;
        break;
      case 451:
        code = "POLICY_VIOLATION" /* POLICY_VIOLATION */;
        break;
      case 500:
      case 502:
      case 503:
        code = "SERVER_ERROR" /* SERVER_ERROR */;
        break;
    }
    return new _AMTTPError(message, code, response.status, response.data?.details);
  }
  /**
   * Check if error is retryable
   */
  isRetryable() {
    return [
      "NETWORK_ERROR" /* NETWORK_ERROR */,
      "TIMEOUT" /* TIMEOUT */,
      "RATE_LIMITED" /* RATE_LIMITED */,
      "SERVER_ERROR" /* SERVER_ERROR */
    ].includes(this.code);
  }
  /**
   * Check if error requires user action
   */
  requiresUserAction() {
    return [
      "KYC_REQUIRED" /* KYC_REQUIRED */,
      "EDD_REQUIRED" /* EDD_REQUIRED */,
      "INSUFFICIENT_BALANCE" /* INSUFFICIENT_BALANCE */,
      "HIGH_RISK_BLOCKED" /* HIGH_RISK_BLOCKED */
    ].includes(this.code);
  }
  toJSON() {
    return {
      name: this.name,
      message: this.message,
      code: this.code,
      statusCode: this.statusCode,
      details: this.details
    };
  }
};

// src/events.ts
var import_eventemitter3 = __toESM(require("eventemitter3"));
var EventEmitter = class extends import_eventemitter3.default {
  /**
   * Wait for a specific event with timeout
   */
  waitFor(event, timeout = 3e4) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        reject(new Error(`Timeout waiting for event: ${String(event)}`));
      }, timeout);
      this.once(event, ((...args) => {
        clearTimeout(timer);
        resolve(args);
      }));
    });
  }
  /**
   * Emit with logging
   */
  emitWithLog(event, ...args) {
    if (process.env.AMTTP_DEBUG) {
      console.log(`[AMTTP Event] ${String(event)}:`, ...args);
    }
    return this.emit(event, ...args);
  }
};

// src/services/base.ts
var BaseService = class {
  constructor(http, events) {
    this.http = http;
    this.events = events;
  }
};

// src/services/risk.ts
var RiskService = class extends BaseService {
  constructor(http, events) {
    super(http, events);
  }
  /**
   * Assess risk for a single address
   */
  async assess(request) {
    const response = await this.http.post("/risk/assess", request);
    this.events.emit("risk:assessed", {
      address: request.address,
      riskLevel: response.data.riskLevel,
      riskScore: response.data.riskScore
    });
    return response.data;
  }
  /**
   * Get cached risk score for an address
   */
  async getScore(address) {
    try {
      const response = await this.http.get(`/risk/score/${address}`);
      return response.data;
    } catch (error) {
      if (error.response?.status === 404) {
        return null;
      }
      throw error;
    }
  }
  /**
   * Batch assess multiple addresses
   */
  async batchAssess(request) {
    const response = await this.http.post("/risk/batch", request);
    this.events.emit("risk:batchCompleted", {
      processedCount: response.data.processedCount,
      failedCount: response.data.failedCount
    });
    return response.data;
  }
  /**
   * Get risk thresholds configuration
   */
  async getThresholds() {
    const response = await this.http.get("/risk/thresholds");
    return response.data.thresholds;
  }
  /**
   * Check if address passes risk threshold
   */
  async checkThreshold(address, maxRiskLevel = "medium") {
    const response = await this.http.post("/risk/check-threshold", { address, maxRiskLevel });
    return response.data;
  }
  /**
   * Get risk history for an address
   */
  async getHistory(address, options) {
    const params = new URLSearchParams();
    if (options?.limit) params.append("limit", options.limit.toString());
    if (options?.offset) params.append("offset", options.offset.toString());
    if (options?.startDate) params.append("startDate", options.startDate.toISOString());
    if (options?.endDate) params.append("endDate", options.endDate.toISOString());
    const response = await this.http.get(`/risk/history/${address}?${params.toString()}`);
    return response.data;
  }
  /**
   * Invalidate cached risk score
   */
  async invalidateCache(address) {
    await this.http.delete(`/risk/cache/${address}`);
    this.events.emit("risk:cacheInvalidated", { address });
  }
  /**
   * Get risk factors configuration
   */
  async getFactors() {
    const response = await this.http.get("/risk/factors");
    return response.data;
  }
};

// src/services/kyc.ts
var KYCService = class extends BaseService {
  constructor(http, events) {
    super(http, events);
  }
  /**
   * Submit KYC documents for verification
   */
  async submit(submission) {
    const response = await this.http.post("/kyc/submit", submission);
    this.events.emit("kyc:submitted", {
      address: submission.address,
      documentType: submission.documentType
    });
    return response.data;
  }
  /**
   * Get KYC status for an address
   */
  async getStatus(address) {
    const response = await this.http.get(`/kyc/status/${address}`);
    return response.data;
  }
  /**
   * Check if address is KYC verified
   */
  async isVerified(address) {
    const status = await this.getStatus(address);
    return status.status === "verified";
  }
  /**
   * Get KYC level for an address
   */
  async getLevel(address) {
    const status = await this.getStatus(address);
    return status.level;
  }
  /**
   * Upload document for KYC verification
   */
  async uploadDocument(address, document) {
    const response = await this.http.post(
      `/kyc/documents/${address}`,
      document
    );
    this.events.emit("kyc:documentUploaded", {
      address,
      documentType: document.type,
      documentId: response.data.documentId
    });
    return response.data;
  }
  /**
   * Get uploaded documents for an address
   */
  async getDocuments(address) {
    const response = await this.http.get(`/kyc/documents/${address}`);
    return response.data.documents;
  }
  /**
   * Get KYC requirements for a specific level
   */
  async getRequirements(level) {
    const url = level ? `/kyc/requirements?level=${level}` : "/kyc/requirements";
    const response = await this.http.get(url);
    return response.data.requirements;
  }
  /**
   * Request KYC level upgrade
   */
  async requestUpgrade(address, targetLevel) {
    const response = await this.http.post("/kyc/upgrade", { address, targetLevel });
    this.events.emit("kyc:upgradeRequested", {
      address,
      targetLevel,
      requestId: response.data.requestId
    });
    return response.data;
  }
  /**
   * Verify KYC attestation on-chain
   */
  async verifyOnChain(address, chainId) {
    const response = await this.http.get(`/kyc/verify-onchain/${address}?chainId=${chainId}`);
    return response.data;
  }
  /**
   * Renew expiring KYC
   */
  async renew(address) {
    const response = await this.http.post(`/kyc/renew/${address}`);
    this.events.emit("kyc:renewed", { address });
    return response.data;
  }
  /**
   * Check if KYC is expiring soon
   */
  async checkExpiry(address) {
    const response = await this.http.get(`/kyc/expiry/${address}`);
    return response.data;
  }
};

// src/services/transaction.ts
var TransactionService = class extends BaseService {
  constructor(http, events) {
    super(http, events);
  }
  /**
   * Validate a transaction before submission
   */
  async validate(request) {
    const response = await this.http.post("/tx/validate", request);
    this.events.emit("transaction:validated", {
      from: request.from,
      to: request.to,
      valid: response.data.valid,
      riskLevel: response.data.riskLevel
    });
    return response.data;
  }
  /**
   * Submit a transaction for processing
   */
  async submit(request) {
    const response = await this.http.post("/tx/submit", request);
    this.events.emit("transaction:submitted", {
      id: response.data.id,
      from: request.from,
      to: request.to,
      status: response.data.status
    });
    return response.data;
  }
  /**
   * Get transaction by ID
   */
  async get(id) {
    const response = await this.http.get(`/tx/${id}`);
    return response.data;
  }
  /**
   * Get transaction by hash
   */
  async getByHash(hash) {
    const response = await this.http.get(`/tx/hash/${hash}`);
    return response.data;
  }
  /**
   * Get transaction history
   */
  async getHistory(options) {
    const params = new URLSearchParams();
    if (options?.address) params.append("address", options.address);
    if (options?.status) params.append("status", options.status);
    if (options?.startDate) params.append("startDate", options.startDate.toISOString());
    if (options?.endDate) params.append("endDate", options.endDate.toISOString());
    if (options?.limit) params.append("limit", options.limit.toString());
    if (options?.offset) params.append("offset", options.offset.toString());
    if (options?.sortBy) params.append("sortBy", options.sortBy);
    if (options?.sortOrder) params.append("sortOrder", options.sortOrder);
    const response = await this.http.get(`/tx/history?${params.toString()}`);
    return response.data;
  }
  /**
   * Cancel a pending transaction
   */
  async cancel(id, reason) {
    const response = await this.http.post(`/tx/${id}/cancel`, { reason });
    this.events.emit("transaction:cancelled", { id, reason });
    return response.data;
  }
  /**
   * Retry a failed transaction
   */
  async retry(id) {
    const response = await this.http.post(`/tx/${id}/retry`);
    this.events.emit("transaction:retried", { id });
    return response.data;
  }
  /**
   * Get transaction status updates
   */
  async getStatusUpdates(id) {
    const response = await this.http.get(`/tx/${id}/status-updates`);
    return response.data;
  }
  /**
   * Request expedited processing
   */
  async expedite(id) {
    const response = await this.http.post(`/tx/${id}/expedite`);
    return response.data;
  }
  /**
   * Get transaction receipt
   */
  async getReceipt(id) {
    const response = await this.http.get(`/tx/${id}/receipt`);
    return response.data;
  }
  /**
   * Estimate transaction cost
   */
  async estimateCost(request) {
    const response = await this.http.post("/tx/estimate", request);
    return response.data;
  }
  /**
   * Get pending transactions for an address
   */
  async getPending(address) {
    const response = await this.http.get(
      `/tx/pending/${address}`
    );
    return response.data.transactions;
  }
};

// src/services/policy.ts
var PolicyService = class extends BaseService {
  constructor(http, events) {
    super(http, events);
  }
  /**
   * Evaluate policies for a transaction
   */
  async evaluate(request) {
    const response = await this.http.post("/policy/evaluate", request);
    this.events.emit("policy:evaluated", {
      from: request.from,
      to: request.to,
      decision: response.data.decision,
      appliedPolicies: response.data.appliedPolicies.length
    });
    return response.data;
  }
  /**
   * Get all policies
   */
  async list(options) {
    const params = new URLSearchParams();
    if (options?.type) params.append("type", options.type);
    if (options?.enabled !== void 0) params.append("enabled", options.enabled.toString());
    if (options?.limit) params.append("limit", options.limit.toString());
    if (options?.offset) params.append("offset", options.offset.toString());
    const response = await this.http.get(`/policy?${params.toString()}`);
    return response.data;
  }
  /**
   * Get policy by ID
   */
  async get(id) {
    const response = await this.http.get(`/policy/${id}`);
    return response.data;
  }
  /**
   * Create a new policy
   */
  async create(request) {
    const response = await this.http.post("/policy", request);
    this.events.emit("policy:created", {
      id: response.data.id,
      name: response.data.name,
      type: response.data.type
    });
    return response.data;
  }
  /**
   * Update an existing policy
   */
  async update(id, updates) {
    const response = await this.http.put(`/policy/${id}`, updates);
    this.events.emit("policy:updated", { id });
    return response.data;
  }
  /**
   * Delete a policy
   */
  async delete(id) {
    await this.http.delete(`/policy/${id}`);
    this.events.emit("policy:deleted", { id });
  }
  /**
   * Enable a policy
   */
  async enable(id) {
    const response = await this.http.post(`/policy/${id}/enable`);
    return response.data;
  }
  /**
   * Disable a policy
   */
  async disable(id) {
    const response = await this.http.post(`/policy/${id}/disable`);
    return response.data;
  }
  /**
   * Test policy against sample data
   */
  async test(id, testData) {
    const response = await this.http.post(`/policy/${id}/test`, testData);
    return response.data;
  }
  /**
   * Get policy templates
   */
  async getTemplates() {
    const response = await this.http.get("/policy/templates");
    return response.data;
  }
  /**
   * Create policy from template
   */
  async createFromTemplate(templateId, overrides) {
    const response = await this.http.post(`/policy/templates/${templateId}/create`, overrides);
    return response.data;
  }
  /**
   * Get policy audit log
   */
  async getAuditLog(id, options) {
    const params = new URLSearchParams();
    if (options?.limit) params.append("limit", options.limit.toString());
    if (options?.offset) params.append("offset", options.offset.toString());
    const response = await this.http.get(`/policy/${id}/audit?${params.toString()}`);
    return response.data;
  }
  /**
   * Validate policy configuration
   */
  async validate(policy) {
    const response = await this.http.post("/policy/validate", policy);
    return response.data;
  }
};

// src/services/dispute.ts
var DisputeService = class extends BaseService {
  constructor(http, events) {
    super(http, events);
  }
  /**
   * Create a new dispute
   */
  async create(request) {
    const response = await this.http.post("/dispute", request);
    this.events.emit("dispute:created", {
      id: response.data.id,
      transactionId: request.transactionId,
      category: request.category
    });
    return response.data;
  }
  /**
   * Get dispute by ID
   */
  async get(id) {
    const response = await this.http.get(`/dispute/${id}`);
    return response.data;
  }
  /**
   * Get dispute by Kleros dispute ID
   */
  async getByKlerosId(klerosDisputeId) {
    const response = await this.http.get(`/dispute/kleros/${klerosDisputeId}`);
    return response.data;
  }
  /**
   * List disputes
   */
  async list(options) {
    const params = new URLSearchParams();
    if (options?.status) params.append("status", options.status);
    if (options?.claimant) params.append("claimant", options.claimant);
    if (options?.respondent) params.append("respondent", options.respondent);
    if (options?.category) params.append("category", options.category);
    if (options?.limit) params.append("limit", options.limit.toString());
    if (options?.offset) params.append("offset", options.offset.toString());
    if (options?.sortBy) params.append("sortBy", options.sortBy);
    if (options?.sortOrder) params.append("sortOrder", options.sortOrder);
    const response = await this.http.get(`/dispute?${params.toString()}`);
    return response.data;
  }
  /**
   * Submit evidence for a dispute
   */
  async submitEvidence(disputeId, evidence) {
    const response = await this.http.post(`/dispute/${disputeId}/evidence`, evidence);
    this.events.emit("dispute:evidenceSubmitted", {
      disputeId,
      evidenceId: response.data.id,
      type: evidence.type
    });
    return response.data;
  }
  /**
   * Get evidence for a dispute
   */
  async getEvidence(disputeId) {
    const response = await this.http.get(`/dispute/${disputeId}/evidence`);
    return response.data.evidence;
  }
  /**
   * Escalate dispute to Kleros
   */
  async escalateToKleros(disputeId) {
    const response = await this.http.post(`/dispute/${disputeId}/escalate`);
    this.events.emit("dispute:escalated", {
      disputeId,
      klerosDisputeId: response.data.klerosDisputeId
    });
    return response.data;
  }
  /**
   * Get arbitration cost estimate
   */
  async getArbitrationCost(category) {
    const response = await this.http.get(`/dispute/arbitration-cost?category=${category}`);
    return response.data;
  }
  /**
   * Accept dispute resolution
   */
  async acceptResolution(disputeId) {
    const response = await this.http.post(`/dispute/${disputeId}/accept`);
    this.events.emit("dispute:resolutionAccepted", { disputeId });
    return response.data;
  }
  /**
   * Appeal dispute ruling
   */
  async appeal(disputeId, reason) {
    const response = await this.http.post(`/dispute/${disputeId}/appeal`, { reason });
    this.events.emit("dispute:appealed", {
      disputeId,
      appealId: response.data.appealId
    });
    return response.data;
  }
  /**
   * Withdraw dispute
   */
  async withdraw(disputeId, reason) {
    const response = await this.http.post(`/dispute/${disputeId}/withdraw`, { reason });
    this.events.emit("dispute:withdrawn", { disputeId });
    return response.data;
  }
  /**
   * Get dispute statistics
   */
  async getStatistics(address) {
    const url = address ? `/dispute/statistics?address=${address}` : "/dispute/statistics";
    const response = await this.http.get(url);
    return response.data;
  }
  /**
   * Get dispute timeline
   */
  async getTimeline(disputeId) {
    const response = await this.http.get(`/dispute/${disputeId}/timeline`);
    return response.data.timeline;
  }
  /**
   * Check if dispute is eligible for arbitration
   */
  async checkEligibility(disputeId) {
    const response = await this.http.get(`/dispute/${disputeId}/eligibility`);
    return response.data;
  }
};

// src/services/reputation.ts
var ReputationService = class extends BaseService {
  constructor(http, events) {
    super(http, events);
  }
  /**
   * Get reputation profile for an address
   */
  async getProfile(address) {
    const response = await this.http.get(`/reputation/${address}`);
    return response.data;
  }
  /**
   * Get reputation score
   */
  async getScore(address) {
    const response = await this.http.get(`/reputation/${address}/score`);
    return response.data;
  }
  /**
   * Get reputation tier
   */
  async getTier(address) {
    const profile = await this.getProfile(address);
    return profile.tier;
  }
  /**
   * Get tier requirements
   */
  async getTierRequirements(tier) {
    const url = tier ? `/reputation/tiers?tier=${tier}` : "/reputation/tiers";
    const response = await this.http.get(url);
    return response.data.tiers;
  }
  /**
   * Get progress to next tier
   */
  async getProgress(address) {
    const response = await this.http.get(`/reputation/${address}/progress`);
    return response.data;
  }
  /**
   * Get reputation history
   */
  async getHistory(address, options) {
    const params = new URLSearchParams();
    if (options?.type) params.append("type", options.type);
    if (options?.limit) params.append("limit", options.limit.toString());
    if (options?.offset) params.append("offset", options.offset.toString());
    if (options?.startDate) params.append("startDate", options.startDate.toISOString());
    if (options?.endDate) params.append("endDate", options.endDate.toISOString());
    const response = await this.http.get(`/reputation/${address}/history?${params.toString()}`);
    return response.data;
  }
  /**
   * Get badges for an address
   */
  async getBadges(address) {
    const response = await this.http.get(`/reputation/${address}/badges`);
    return response.data.badges;
  }
  /**
   * Get available badges
   */
  async getAvailableBadges() {
    const response = await this.http.get("/reputation/badges");
    return response.data;
  }
  /**
   * Get leaderboard
   */
  async getLeaderboard(options) {
    const params = new URLSearchParams();
    if (options?.tier) params.append("tier", options.tier);
    if (options?.limit) params.append("limit", options.limit.toString());
    if (options?.offset) params.append("offset", options.offset.toString());
    const response = await this.http.get(`/reputation/leaderboard?${params.toString()}`);
    return response.data;
  }
  /**
   * Get reputation statistics
   */
  async getStatistics() {
    const response = await this.http.get("/reputation/statistics");
    return response.data;
  }
  /**
   * Calculate reputation impact of a transaction
   */
  async calculateImpact(address, transaction) {
    const response = await this.http.post(`/reputation/${address}/calculate-impact`, transaction);
    this.events.emit("reputation:impactCalculated", {
      address,
      scoreChange: response.data.scoreChange
    });
    return response.data;
  }
  /**
   * Get transaction limits based on reputation
   */
  async getLimits(address) {
    const response = await this.http.get(`/reputation/${address}/limits`);
    return response.data;
  }
  /**
   * Compare reputation between two addresses
   */
  async compare(address1, address2) {
    const response = await this.http.get(`/reputation/compare?address1=${address1}&address2=${address2}`);
    return response.data;
  }
};

// src/services/bulk.ts
var BulkService = class extends BaseService {
  constructor(http, events) {
    super(http, events);
  }
  /**
   * Submit bulk scoring request
   */
  async submit(request) {
    const response = await this.http.post("/bulk/submit", request);
    return response.data;
  }
  /**
   * Submit and wait for results (synchronous for small batches)
   */
  async score(request) {
    const response = await this.http.post("/bulk/score", request);
    return response.data;
  }
  /**
   * Get job status
   */
  async getStatus(jobId) {
    const response = await this.http.get(`/bulk/status/${jobId}`);
    return response.data;
  }
  /**
   * Get job results
   */
  async getResults(jobId, options) {
    const params = new URLSearchParams();
    if (options?.limit) params.append("limit", options.limit.toString());
    if (options?.offset) params.append("offset", options.offset.toString());
    if (options?.status) params.append("status", options.status);
    const response = await this.http.get(`/bulk/results/${jobId}?${params.toString()}`);
    return response.data;
  }
  /**
   * Cancel a bulk job
   */
  async cancel(jobId) {
    const response = await this.http.post(`/bulk/cancel/${jobId}`);
    return response.data;
  }
  /**
   * Get job history
   */
  async getHistory(options) {
    const params = new URLSearchParams();
    if (options?.limit) params.append("limit", options.limit.toString());
    if (options?.offset) params.append("offset", options.offset.toString());
    if (options?.status) params.append("status", options.status);
    if (options?.startDate) params.append("startDate", options.startDate.toISOString());
    if (options?.endDate) params.append("endDate", options.endDate.toISOString());
    const response = await this.http.get(`/bulk/history?${params.toString()}`);
    return response.data;
  }
  /**
   * Get bulk scoring statistics
   */
  async getStatistics() {
    const response = await this.http.get("/bulk/statistics");
    return response.data;
  }
  /**
   * Download results as CSV
   */
  async downloadResults(jobId) {
    const response = await this.http.get(`/bulk/download/${jobId}`, {
      responseType: "blob"
    });
    return response.data;
  }
  /**
   * Retry failed transactions in a job
   */
  async retryFailed(jobId) {
    const response = await this.http.post(`/bulk/retry/${jobId}`);
    return response.data;
  }
};

// src/services/webhook.ts
var WebhookService = class extends BaseService {
  constructor(http, events) {
    super(http, events);
  }
  /**
   * Create a new webhook
   */
  async create(request) {
    const response = await this.http.post("/webhook", request);
    return response.data;
  }
  /**
   * List all webhooks
   */
  async list(options) {
    const params = new URLSearchParams();
    if (options?.enabled !== void 0) params.append("enabled", options.enabled.toString());
    if (options?.limit) params.append("limit", options.limit.toString());
    if (options?.offset) params.append("offset", options.offset.toString());
    const response = await this.http.get(`/webhook?${params.toString()}`);
    return response.data;
  }
  /**
   * Get webhook by ID
   */
  async get(id) {
    const response = await this.http.get(`/webhook/${id}`);
    return response.data;
  }
  /**
   * Update a webhook
   */
  async update(id, updates) {
    const response = await this.http.put(`/webhook/${id}`, updates);
    return response.data;
  }
  /**
   * Delete a webhook
   */
  async delete(id) {
    await this.http.delete(`/webhook/${id}`);
  }
  /**
   * Enable a webhook
   */
  async enable(id) {
    const response = await this.http.post(`/webhook/${id}/enable`);
    return response.data;
  }
  /**
   * Disable a webhook
   */
  async disable(id) {
    const response = await this.http.post(`/webhook/${id}/disable`);
    return response.data;
  }
  /**
   * Rotate webhook secret
   */
  async rotateSecret(id) {
    const response = await this.http.post(`/webhook/${id}/rotate-secret`);
    return response.data;
  }
  /**
   * Test a webhook
   */
  async test(id, event) {
    const response = await this.http.post(`/webhook/${id}/test`, { event });
    return response.data;
  }
  /**
   * Get webhook deliveries
   */
  async getDeliveries(webhookId, options) {
    const params = new URLSearchParams();
    if (options?.status) params.append("status", options.status);
    if (options?.event) params.append("event", options.event);
    if (options?.limit) params.append("limit", options.limit.toString());
    if (options?.offset) params.append("offset", options.offset.toString());
    if (options?.startDate) params.append("startDate", options.startDate.toISOString());
    if (options?.endDate) params.append("endDate", options.endDate.toISOString());
    const response = await this.http.get(`/webhook/${webhookId}/deliveries?${params.toString()}`);
    return response.data;
  }
  /**
   * Retry a failed delivery
   */
  async retryDelivery(webhookId, deliveryId) {
    const response = await this.http.post(
      `/webhook/${webhookId}/deliveries/${deliveryId}/retry`
    );
    return response.data;
  }
  /**
   * Get available event types
   */
  async getEventTypes() {
    const response = await this.http.get("/webhook/events");
    return response.data;
  }
  /**
   * Get webhook statistics
   */
  async getStatistics(webhookId) {
    const url = webhookId ? `/webhook/${webhookId}/statistics` : "/webhook/statistics";
    const response = await this.http.get(url);
    return response.data;
  }
  /**
   * Verify webhook signature
   */
  verifySignature(payload, signature, secret) {
    const crypto2 = require("crypto");
    const expectedSignature = crypto2.createHmac("sha256", secret).update(payload).digest("hex");
    return `sha256=${expectedSignature}` === signature;
  }
};

// src/services/pep.ts
var PEPService = class extends BaseService {
  constructor(http, events) {
    super(http, events);
  }
  /**
   * Screen an address for PEP matches
   */
  async screen(request) {
    const response = await this.http.post("/pep/screen", request);
    return response.data;
  }
  /**
   * Get cached screening result
   */
  async getResult(address) {
    try {
      const response = await this.http.get(`/pep/result/${address}`);
      return response.data;
    } catch (error) {
      if (error.response?.status === 404) {
        return null;
      }
      throw error;
    }
  }
  /**
   * Check if address has PEP matches
   */
  async hasPEPMatches(address) {
    const response = await this.http.get(`/pep/check/${address}`);
    return response.data;
  }
  /**
   * Get screening history for an address
   */
  async getHistory(address, options) {
    const params = new URLSearchParams();
    if (options?.limit) params.append("limit", options.limit.toString());
    if (options?.offset) params.append("offset", options.offset.toString());
    if (options?.startDate) params.append("startDate", options.startDate.toISOString());
    if (options?.endDate) params.append("endDate", options.endDate.toISOString());
    const response = await this.http.get(`/pep/history/${address}?${params.toString()}`);
    return response.data;
  }
  /**
   * Batch screen multiple addresses
   */
  async batchScreen(addresses) {
    const response = await this.http.post("/pep/batch", { addresses });
    return response.data;
  }
  /**
   * Acknowledge a PEP match (mark as reviewed)
   */
  async acknowledgeMatch(address, matchId, decision) {
    const response = await this.http.post(`/pep/${address}/matches/${matchId}/acknowledge`, decision);
    return response.data;
  }
  /**
   * Get match details
   */
  async getMatchDetails(address, matchId) {
    const response = await this.http.get(`/pep/${address}/matches/${matchId}`);
    return response.data;
  }
  /**
   * Get available screening providers
   */
  async getProviders() {
    const response = await this.http.get("/pep/providers");
    return response.data;
  }
  /**
   * Invalidate cached screening result
   */
  async invalidateCache(address) {
    await this.http.delete(`/pep/cache/${address}`);
  }
  /**
   * Get PEP screening statistics
   */
  async getStatistics() {
    const response = await this.http.get("/pep/statistics");
    return response.data;
  }
  /**
   * Schedule periodic rescreening
   */
  async scheduleRescreening(address, intervalDays) {
    const response = await this.http.post(`/pep/${address}/schedule`, { intervalDays });
    return response.data;
  }
};

// src/services/edd.ts
var EDDService = class extends BaseService {
  constructor(http, events) {
    super(http, events);
  }
  /**
   * Create an EDD case
   */
  async create(request) {
    const response = await this.http.post("/edd", request);
    return response.data;
  }
  /**
   * Get EDD case by ID
   */
  async get(id) {
    const response = await this.http.get(`/edd/${id}`);
    return response.data;
  }
  /**
   * Get EDD case for an address
   */
  async getByAddress(address) {
    try {
      const response = await this.http.get(`/edd/address/${address}`);
      return response.data;
    } catch (error) {
      if (error.response?.status === 404) {
        return null;
      }
      throw error;
    }
  }
  /**
   * List EDD cases
   */
  async list(options) {
    const params = new URLSearchParams();
    if (options?.status) params.append("status", options.status);
    if (options?.trigger) params.append("trigger", options.trigger);
    if (options?.assignedTo) params.append("assignedTo", options.assignedTo);
    if (options?.priority) params.append("priority", options.priority);
    if (options?.limit) params.append("limit", options.limit.toString());
    if (options?.offset) params.append("offset", options.offset.toString());
    if (options?.sortBy) params.append("sortBy", options.sortBy);
    if (options?.sortOrder) params.append("sortOrder", options.sortOrder);
    const response = await this.http.get(`/edd?${params.toString()}`);
    return response.data;
  }
  /**
   * Assign EDD case to reviewer
   */
  async assign(id, assignee) {
    const response = await this.http.post(`/edd/${id}/assign`, { assignee });
    return response.data;
  }
  /**
   * Update EDD case status
   */
  async updateStatus(id, status, note) {
    const response = await this.http.put(`/edd/${id}/status`, { status, note });
    return response.data;
  }
  /**
   * Upload document for EDD case
   */
  async uploadDocument(id, document) {
    const response = await this.http.post(`/edd/${id}/documents`, document);
    return response.data;
  }
  /**
   * Get documents for EDD case
   */
  async getDocuments(id) {
    const response = await this.http.get(`/edd/${id}/documents`);
    return response.data.documents;
  }
  /**
   * Verify document
   */
  async verifyDocument(caseId, documentId, decision) {
    const response = await this.http.post(
      `/edd/${caseId}/documents/${documentId}/verify`,
      decision
    );
    return response.data;
  }
  /**
   * Add note to EDD case
   */
  async addNote(id, note) {
    const response = await this.http.post(`/edd/${id}/notes`, note);
    return response.data;
  }
  /**
   * Get notes for EDD case
   */
  async getNotes(id) {
    const response = await this.http.get(`/edd/${id}/notes`);
    return response.data.notes;
  }
  /**
   * Resolve EDD case
   */
  async resolve(id, resolution) {
    const response = await this.http.post(`/edd/${id}/resolve`, resolution);
    return response.data;
  }
  /**
   * Escalate EDD case
   */
  async escalate(id, reason, escalateTo) {
    const response = await this.http.post(`/edd/${id}/escalate`, { reason, escalateTo });
    return response.data;
  }
  /**
   * Get EDD case timeline
   */
  async getTimeline(id) {
    const response = await this.http.get(`/edd/${id}/timeline`);
    return response.data.timeline;
  }
  /**
   * Get EDD requirements for a trigger type
   */
  async getRequirements(trigger) {
    const response = await this.http.get(`/edd/requirements?trigger=${trigger}`);
    return response.data;
  }
  /**
   * Get EDD statistics
   */
  async getStatistics() {
    const response = await this.http.get("/edd/statistics");
    return response.data;
  }
  /**
   * Check if address requires EDD
   */
  async checkRequired(address) {
    const response = await this.http.get(`/edd/check/${address}`);
    return response.data;
  }
};

// src/services/monitoring.ts
var MonitoringService = class extends BaseService {
  constructor(http, events) {
    super(http, events);
  }
  /**
   * Add address to monitoring
   */
  async addAddress(address, options) {
    const response = await this.http.post("/monitoring/addresses", {
      address,
      ...options
    });
    return response.data;
  }
  /**
   * Remove address from monitoring
   */
  async removeAddress(address) {
    await this.http.delete(`/monitoring/addresses/${address}`);
  }
  /**
   * Get monitored addresses
   */
  async getAddresses(options) {
    const params = new URLSearchParams();
    if (options?.enabled !== void 0) params.append("enabled", options.enabled.toString());
    if (options?.hasAlerts !== void 0) params.append("hasAlerts", options.hasAlerts.toString());
    if (options?.tags) options.tags.forEach((t) => params.append("tags", t));
    if (options?.limit) params.append("limit", options.limit.toString());
    if (options?.offset) params.append("offset", options.offset.toString());
    const response = await this.http.get(`/monitoring/addresses?${params.toString()}`);
    return response.data;
  }
  /**
   * Get address monitoring status
   */
  async getAddressStatus(address) {
    const response = await this.http.get(`/monitoring/addresses/${address}`);
    return response.data;
  }
  /**
   * Get alerts
   */
  async getAlerts(options) {
    const params = new URLSearchParams();
    if (options?.address) params.append("address", options.address);
    if (options?.type) params.append("type", options.type);
    if (options?.severity) params.append("severity", options.severity);
    if (options?.status) params.append("status", options.status);
    if (options?.limit) params.append("limit", options.limit.toString());
    if (options?.offset) params.append("offset", options.offset.toString());
    if (options?.startDate) params.append("startDate", options.startDate.toISOString());
    if (options?.endDate) params.append("endDate", options.endDate.toISOString());
    const response = await this.http.get(`/monitoring/alerts?${params.toString()}`);
    return response.data;
  }
  /**
   * Get alert by ID
   */
  async getAlert(id) {
    const response = await this.http.get(`/monitoring/alerts/${id}`);
    return response.data;
  }
  /**
   * Acknowledge an alert
   */
  async acknowledgeAlert(id, acknowledgedBy) {
    const response = await this.http.post(`/monitoring/alerts/${id}/acknowledge`, {
      acknowledgedBy
    });
    return response.data;
  }
  /**
   * Resolve an alert
   */
  async resolveAlert(id, resolution) {
    const response = await this.http.post(`/monitoring/alerts/${id}/resolve`, resolution);
    return response.data;
  }
  /**
   * Dismiss an alert
   */
  async dismissAlert(id, reason, dismissedBy) {
    const response = await this.http.post(`/monitoring/alerts/${id}/dismiss`, {
      reason,
      dismissedBy
    });
    return response.data;
  }
  /**
   * Get monitoring rules
   */
  async getRules() {
    const response = await this.http.get("/monitoring/rules");
    return response.data.rules;
  }
  /**
   * Create a monitoring rule
   */
  async createRule(rule) {
    const response = await this.http.post("/monitoring/rules", rule);
    return response.data;
  }
  /**
   * Update a monitoring rule
   */
  async updateRule(id, updates) {
    const response = await this.http.put(`/monitoring/rules/${id}`, updates);
    return response.data;
  }
  /**
   * Delete a monitoring rule
   */
  async deleteRule(id) {
    await this.http.delete(`/monitoring/rules/${id}`);
  }
  /**
   * Enable/disable a rule
   */
  async toggleRule(id, enabled) {
    const response = await this.http.post(`/monitoring/rules/${id}/toggle`, { enabled });
    return response.data;
  }
  /**
   * Get monitoring configuration
   */
  async getConfig() {
    const response = await this.http.get("/monitoring/config");
    return response.data;
  }
  /**
   * Update monitoring configuration
   */
  async updateConfig(config) {
    const response = await this.http.put("/monitoring/config", config);
    return response.data;
  }
  /**
   * Trigger manual check for an address
   */
  async triggerCheck(address) {
    const response = await this.http.post(`/monitoring/check/${address}`);
    return response.data;
  }
  /**
   * Get monitoring statistics
   */
  async getStatistics() {
    const response = await this.http.get("/monitoring/statistics");
    return response.data;
  }
  /**
   * Get risk trend for an address
   */
  async getRiskTrend(address, options) {
    const params = new URLSearchParams();
    if (options?.days) params.append("days", options.days.toString());
    const response = await this.http.get(`/monitoring/trend/${address}?${params.toString()}`);
    return response.data;
  }
};

// src/services/label.ts
var LabelService = class extends BaseService {
  constructor(http, events) {
    super(http, events);
  }
  /**
   * Get labels for an address
   */
  async getLabels(address) {
    const response = await this.http.get(`/label/${address}`);
    return response.data;
  }
  /**
   * Check if address has specific label categories
   */
  async hasLabels(address, categories) {
    const params = new URLSearchParams();
    if (categories) categories.forEach((c) => params.append("categories", c));
    const response = await this.http.get(`/label/${address}/check?${params.toString()}`);
    return response.data;
  }
  /**
   * Batch check multiple addresses
   */
  async batchCheck(addresses, options) {
    const response = await this.http.post("/label/batch", {
      addresses,
      ...options
    });
    return response.data;
  }
  /**
   * Add a label to an address
   */
  async addLabel(label) {
    const response = await this.http.post("/label", label);
    return response.data;
  }
  /**
   * Update a label
   */
  async updateLabel(id, updates) {
    const response = await this.http.put(`/label/${id}`, updates);
    return response.data;
  }
  /**
   * Remove a label
   */
  async removeLabel(id) {
    await this.http.delete(`/label/${id}`);
  }
  /**
   * Verify a label
   */
  async verifyLabel(id, verified, verifiedBy) {
    const response = await this.http.post(`/label/${id}/verify`, {
      verified,
      verifiedBy
    });
    return response.data;
  }
  /**
   * Search labels
   */
  async search(options) {
    const params = new URLSearchParams();
    if (options?.query) params.append("query", options.query);
    if (options?.category) params.append("category", options.category);
    if (options?.severity) params.append("severity", options.severity);
    if (options?.source) params.append("source", options.source);
    if (options?.verified !== void 0) params.append("verified", options.verified.toString());
    if (options?.limit) params.append("limit", options.limit.toString());
    if (options?.offset) params.append("offset", options.offset.toString());
    const response = await this.http.get(`/label/search?${params.toString()}`);
    return response.data;
  }
  /**
   * Get label categories with descriptions
   */
  async getCategories() {
    const response = await this.http.get("/label/categories");
    return response.data;
  }
  /**
   * Get label sources
   */
  async getSources() {
    const response = await this.http.get("/label/sources");
    return response.data;
  }
  /**
   * Get label statistics
   */
  async getStatistics() {
    const response = await this.http.get("/label/statistics");
    return response.data;
  }
  /**
   * Get label history for an address
   */
  async getHistory(address, options) {
    const params = new URLSearchParams();
    if (options?.limit) params.append("limit", options.limit.toString());
    if (options?.offset) params.append("offset", options.offset.toString());
    const response = await this.http.get(`/label/${address}/history?${params.toString()}`);
    return response.data;
  }
  /**
   * Report a label (for moderation)
   */
  async reportLabel(id, report) {
    const response = await this.http.post(`/label/${id}/report`, report);
    return response.data;
  }
  /**
   * Get risky label categories that should trigger blocking
   */
  async getBlockingCategories() {
    const response = await this.http.get("/label/blocking-categories");
    return response.data.categories;
  }
};

// src/mev/protection.ts
var MEVProtection = class extends BaseService {
  constructor(http, events) {
    super(http, events);
    this.config = {
      enabled: true,
      protectionLevel: "enhanced",
      flashbotsEnabled: true,
      privateMempoolEnabled: true,
      maxSlippage: 0.5,
      deadlineMinutes: 20
    };
  }
  /**
   * Get current MEV protection configuration
   */
  getConfig() {
    return { ...this.config };
  }
  /**
   * Update MEV protection configuration
   */
  setConfig(config) {
    this.config = { ...this.config, ...config };
  }
  /**
   * Analyze transaction for MEV vulnerabilities
   */
  async analyze(transaction) {
    const response = await this.http.post("/mev/analyze", transaction);
    return response.data;
  }
  /**
   * Submit transaction with MEV protection
   */
  async submitProtected(transaction) {
    const response = await this.http.post("/mev/submit", {
      transaction,
      config: this.config
    });
    return response.data;
  }
  /**
   * Submit Flashbots bundle
   */
  async submitBundle(bundle) {
    const response = await this.http.post("/mev/bundle", bundle);
    return response.data;
  }
  /**
   * Get bundle status
   */
  async getBundleStatus(bundleHash) {
    const response = await this.http.get(`/mev/bundle/${bundleHash}`);
    return response.data;
  }
  /**
   * Simulate transaction
   */
  async simulate(transaction) {
    const response = await this.http.post("/mev/simulate", transaction);
    return response.data;
  }
  /**
   * Get protected transaction status
   */
  async getTransactionStatus(id) {
    const response = await this.http.get(`/mev/transaction/${id}`);
    return response.data;
  }
  /**
   * Get transaction history with MEV protection
   */
  async getHistory(options) {
    const params = new URLSearchParams();
    if (options?.address) params.append("address", options.address);
    if (options?.status) params.append("status", options.status);
    if (options?.limit) params.append("limit", options.limit.toString());
    if (options?.offset) params.append("offset", options.offset.toString());
    const response = await this.http.get(`/mev/history?${params.toString()}`);
    return response.data;
  }
  /**
   * Cancel pending protected transaction
   */
  async cancel(id) {
    const response = await this.http.post(`/mev/transaction/${id}/cancel`);
    return response.data;
  }
  /**
   * Get MEV statistics
   */
  async getStatistics() {
    const response = await this.http.get("/mev/statistics");
    return response.data;
  }
  /**
   * Check if Flashbots relay is available
   */
  async checkFlashbotsStatus() {
    const response = await this.http.get("/mev/flashbots/status");
    return response.data;
  }
  /**
   * Get recommended gas settings for protected transaction
   */
  async getGasRecommendation() {
    const response = await this.http.get("/mev/gas-recommendation");
    return response.data;
  }
};

// src/services/compliance.ts
var ComplianceService = class extends BaseService {
  constructor(http, events) {
    super(http, events);
  }
  /**
   * Evaluate a transaction for compliance
   * This is the main entry point for transaction evaluation
   */
  async evaluate(request) {
    const response = await this.http.post("/evaluate", request);
    this.events.emit("compliance:evaluated", response.data);
    return response.data;
  }
  /**
   * Evaluate with UI integrity verification
   * Binds the evaluation to a UI snapshot hash for audit trail
   */
  async evaluateWithIntegrity(request, snapshotHash) {
    const response = await this.http.post("/evaluate-with-integrity", {
      ...request,
      ui_snapshot_hash: snapshotHash
    });
    return response.data;
  }
  /**
   * Get dashboard statistics
   */
  async getDashboardStats() {
    const response = await this.http.get("/dashboard/stats");
    return response.data;
  }
  /**
   * Get dashboard alerts
   */
  async getDashboardAlerts(options) {
    const response = await this.http.get("/dashboard/alerts", {
      params: options
    });
    return response.data.alerts;
  }
  /**
   * Get timeline data for charts
   */
  async getTimelineData(options) {
    const response = await this.http.get("/dashboard/timeline", {
      params: options
    });
    return response.data.data;
  }
  /**
   * Get Sankey flow data for value visualization
   */
  async getSankeyFlow(options) {
    const response = await this.http.get("/sankey-flow", { params: options });
    return response.data;
  }
  /**
   * Get entity profile by address
   */
  async getProfile(address) {
    const response = await this.http.get(`/profiles/${address}`);
    return response.data;
  }
  /**
   * Update entity profile
   */
  async updateProfile(address, updates) {
    const response = await this.http.put(`/profiles/${address}`, updates);
    this.events.emit("profile:updated", response.data);
    return response.data;
  }
  /**
   * Set entity type for an address
   */
  async setEntityType(address, entityType) {
    const response = await this.http.post(
      `/profiles/${address}/set-type/${entityType}`
    );
    return response.data;
  }
  /**
   * List all profiles
   */
  async listProfiles(options) {
    const response = await this.http.get("/profiles", {
      params: options
    });
    return response.data.profiles;
  }
  /**
   * Get decision history
   */
  async listDecisions(options) {
    const response = await this.http.get("/decisions", {
      params: options
    });
    return response.data.decisions;
  }
  /**
   * Get available entity types
   */
  async getEntityTypes() {
    const response = await this.http.get("/entity-types");
    return response.data.entity_types;
  }
  /**
   * Check service health
   */
  async health() {
    const response = await this.http.get("/health");
    return response.data;
  }
};

// src/services/explainability.ts
var ExplainabilityService = class extends BaseService {
  constructor(http, events, baseUrl = "http://localhost:8009") {
    super(http, events);
    this.baseUrl = baseUrl;
  }
  /**
   * Get explanation for a risk score
   */
  async explain(request) {
    const response = await this.http.post(
      `${this.baseUrl}/explain`,
      request
    );
    this.events.emit("explainability:explained", response.data);
    return response.data;
  }
  /**
   * Get explanation for a specific transaction
   */
  async explainTransaction(request) {
    const response = await this.http.post(
      `${this.baseUrl}/explain/transaction`,
      request
    );
    return response.data;
  }
  /**
   * Get all known fraud typologies
   */
  async getTypologies() {
    const response = await this.http.get(
      `${this.baseUrl}/typologies`
    );
    return response.data.typologies;
  }
  /**
   * Get explanation for an address based on its features
   */
  async explainAddress(address, features) {
    return this.explain({
      risk_score: features.risk_score || 50,
      features: {
        ...features,
        address
      }
    });
  }
  /**
   * Get a human-readable summary for a risk level
   */
  static getRiskSummary(riskScore) {
    if (riskScore >= 90) {
      return "Critical risk - Immediate action required";
    } else if (riskScore >= 75) {
      return "High risk - Enhanced review recommended";
    } else if (riskScore >= 50) {
      return "Medium risk - Standard monitoring applies";
    } else if (riskScore >= 25) {
      return "Low risk - Continue normal processing";
    } else {
      return "Minimal risk - Routine transaction";
    }
  }
  /**
   * Get recommended action based on risk score
   */
  static getRecommendedAction(riskScore) {
    if (riskScore >= 90) return "BLOCK";
    if (riskScore >= 75) return "ESCROW";
    if (riskScore >= 50) return "REVIEW";
    return "ALLOW";
  }
  /**
   * Check service health
   */
  async health() {
    const response = await this.http.get(`${this.baseUrl}/health`);
    return response.data;
  }
};

// src/services/sanctions.ts
var SanctionsService = class extends BaseService {
  constructor(http, events, baseUrl = "http://localhost:8004") {
    super(http, events);
    this.baseUrl = baseUrl;
  }
  /**
   * Check an address or name against sanctions lists
   */
  async check(request) {
    const response = await this.http.post(
      `${this.baseUrl}/sanctions/check`,
      request
    );
    this.events.emit("sanctions:checked", response.data);
    if (response.data.is_sanctioned && response.data.matches.length > 0) {
      const entity = response.data.matches[0].entity;
      if (entity) {
        this.events.emit("sanctions:match", request.address || "", entity.source_list);
      }
    }
    return response.data;
  }
  /**
   * Check multiple addresses in batch
   */
  async batchCheck(request) {
    const response = await this.http.post(
      `${this.baseUrl}/sanctions/batch-check`,
      request
    );
    return response.data;
  }
  /**
   * Check if an address is on any crypto-specific sanctions list
   * (e.g., Tornado Cash, Lazarus Group addresses)
   */
  async checkCryptoAddress(address) {
    return this.check({
      address: address.toLowerCase(),
      include_fuzzy: false
    });
  }
  /**
   * Check a name with fuzzy matching for PEP/sanctions
   */
  async checkName(name, threshold = 0.85) {
    return this.check({
      name,
      include_fuzzy: true,
      threshold
    });
  }
  /**
   * Refresh sanctions lists from sources
   */
  async refresh() {
    const response = await this.http.post(`${this.baseUrl}/sanctions/refresh`);
    return response.data;
  }
  /**
   * Get sanctions database statistics
   */
  async getStats() {
    const response = await this.http.get(`${this.baseUrl}/sanctions/stats`);
    return response.data;
  }
  /**
   * Get list of available sanctions lists
   */
  async getLists() {
    const response = await this.http.get(
      `${this.baseUrl}/sanctions/lists`
    );
    return response.data.lists;
  }
  /**
   * Check service health
   */
  async health() {
    const response = await this.http.get(`${this.baseUrl}/health`);
    return response.data;
  }
};

// src/services/geographic.ts
var GeographicRiskService = class extends BaseService {
  constructor(http, events, baseUrl = "http://localhost:8006") {
    super(http, events);
    this.baseUrl = baseUrl;
  }
  /**
   * Get risk assessment for a country
   */
  async getCountryRisk(countryCode) {
    const response = await this.http.post(
      `${this.baseUrl}/geo/country-risk`,
      { country_code: countryCode.toUpperCase() }
    );
    this.events.emit("geo:risk_assessed", response.data);
    return response.data;
  }
  /**
   * Get risk assessment for an IP address
   */
  async getIPRisk(ipAddress) {
    const response = await this.http.post(
      `${this.baseUrl}/geo/ip-risk`,
      { ip_address: ipAddress }
    );
    return response.data;
  }
  /**
   * Get comprehensive geographic risk for a transaction
   */
  async getTransactionRisk(request) {
    const response = await this.http.post(
      `${this.baseUrl}/geo/transaction-risk`,
      request
    );
    return response.data;
  }
  /**
   * Get FATF Black List countries
   */
  async getFATFBlackList() {
    const response = await this.http.get(
      `${this.baseUrl}/geo/lists/fatf-black`
    );
    return response.data.countries;
  }
  /**
   * Get FATF Grey List countries
   */
  async getFATFGreyList() {
    const response = await this.http.get(
      `${this.baseUrl}/geo/lists/fatf-grey`
    );
    return response.data.countries;
  }
  /**
   * Get EU High Risk Third Countries
   */
  async getEUHighRiskList() {
    const response = await this.http.get(
      `${this.baseUrl}/geo/lists/eu-high-risk`
    );
    return response.data.countries;
  }
  /**
   * Get Tax Haven jurisdictions
   */
  async getTaxHavens() {
    const response = await this.http.get(
      `${this.baseUrl}/geo/lists/tax-havens`
    );
    return response.data.countries;
  }
  /**
   * Get detailed country information
   */
  async getCountryInfo(countryCode) {
    const response = await this.http.get(
      `${this.baseUrl}/geo/country/${countryCode.toUpperCase()}`
    );
    return response.data;
  }
  /**
   * Check if a country is high risk (FATF Black/Grey or EU High Risk)
   */
  async isHighRiskCountry(countryCode) {
    const risk = await this.getCountryRisk(countryCode);
    return risk.risk_level === "PROHIBITED" || risk.risk_level === "VERY_HIGH" || risk.risk_level === "HIGH";
  }
  /**
   * Check if transaction involves prohibited jurisdiction
   */
  async isProhibitedTransaction(originatorCountry, beneficiaryCountry) {
    const transactionRisk = await this.getTransactionRisk({
      originator_country: originatorCountry,
      beneficiary_country: beneficiaryCountry
    });
    return transactionRisk.transaction_policy === "BLOCK";
  }
  /**
   * Check service health
   */
  async health() {
    const response = await this.http.get(`${this.baseUrl}/health`);
    return response.data;
  }
};

// src/services/integrity.ts
var IntegrityService = class extends BaseService {
  constructor(http, events, baseUrl = "http://localhost:8008") {
    super(http, events);
    this.baseUrl = baseUrl;
  }
  /**
   * Register a UI snapshot hash for later verification
   */
  async registerHash(request) {
    const response = await this.http.post(
      `${this.baseUrl}/register-hash`,
      request
    );
    return response.data;
  }
  /**
   * Verify the integrity of a UI snapshot
   */
  async verifyIntegrity(request) {
    const response = await this.http.post(
      `${this.baseUrl}/verify-integrity`,
      request
    );
    this.events.emit("integrity:verified", response.data);
    if (!response.data.is_valid) {
      this.events.emit("integrity:violation", response.data);
    }
    return response.data;
  }
  /**
   * Submit a payment with integrity verification
   */
  async submitPayment(submission) {
    const response = await this.http.post(
      `${this.baseUrl}/submit-payment`,
      submission
    );
    return response.data;
  }
  /**
   * Get list of integrity violations
   */
  async getViolations(options) {
    const response = await this.http.get(
      `${this.baseUrl}/violations`,
      { params: options }
    );
    return response.data.violations;
  }
  /**
   * Generate a snapshot hash from UI state
   */
  static async generateSnapshotHash(state) {
    const encoder = new TextEncoder();
    const data = encoder.encode(JSON.stringify(state, Object.keys(state).sort()));
    const hashBuffer = await crypto.subtle.digest("SHA-256", data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
  }
  /**
   * Create a snapshot data object
   */
  static createSnapshotData(componentId, componentType, state, userId, sessionId) {
    return {
      component_id: componentId,
      component_type: componentType,
      state,
      timestamp: (/* @__PURE__ */ new Date()).toISOString(),
      user_id: userId,
      session_id: sessionId
    };
  }
  /**
   * Check service health
   */
  async health() {
    const response = await this.http.get(`${this.baseUrl}/health`);
    return response.data;
  }
};

// src/services/governance.ts
var GovernanceService = class extends BaseService {
  constructor(http, events) {
    super(http, events);
  }
  /**
   * Create a new governance action
   */
  async createAction(request) {
    const response = await this.http.post("/governance/actions", request);
    this.events.emit("governance:action_created", response.data);
    return response.data;
  }
  /**
   * Get a governance action by ID
   */
  async getAction(actionId) {
    try {
      const response = await this.http.get(`/governance/actions/${actionId}`);
      return response.data;
    } catch {
      return null;
    }
  }
  /**
   * List governance actions
   */
  async listActions(options) {
    const response = await this.http.get(
      "/governance/actions",
      { params: options }
    );
    return response.data.actions;
  }
  /**
   * Get pending actions for a user
   */
  async getPendingActions(userId) {
    const response = await this.http.get(
      `/governance/actions/pending`,
      { params: { userId } }
    );
    return response.data;
  }
  /**
   * Sign a governance action
   */
  async signAction(request) {
    const response = await this.http.post(
      `/governance/actions/${request.actionId}/sign`,
      request
    );
    this.events.emit("governance:signature_added", response.data);
    if (response.data.quorumReached) {
      this.events.emit("governance:quorum_reached", response.data);
    }
    return response.data;
  }
  /**
   * Execute a governance action (after quorum reached)
   */
  async executeAction(actionId) {
    const response = await this.http.post(
      `/governance/actions/${actionId}/execute`
    );
    return response.data;
  }
  /**
   * Cancel a governance action
   */
  async cancelAction(actionId, reason) {
    const response = await this.http.post(`/governance/actions/${actionId}/cancel`, { reason });
    return response.data;
  }
  /**
   * Get What-You-Approve summary for an action
   */
  async getWYASummary(actionId) {
    const response = await this.http.get(`/governance/actions/${actionId}/wya`);
    return response.data;
  }
  /**
   * Get audit trail for an action
   */
  async getAuditTrail(actionId) {
    const response = await this.http.get(`/governance/actions/${actionId}/audit`);
    return response.data.events;
  }
  /**
   * Check if user can sign an action
   */
  async canUserSign(actionId, userId) {
    const response = await this.http.get(`/governance/actions/${actionId}/can-sign`, {
      params: { userId }
    });
    return response.data;
  }
  /**
   * Calculate quorum progress
   */
  static calculateQuorumProgress(action) {
    const current = action.signatures.length;
    const required = action.requiredSignatures;
    return {
      current,
      required,
      percentage: Math.min(100, current / required * 100)
    };
  }
  /**
   * Get action type label
   */
  static getActionTypeLabel(type) {
    const labels = {
      WALLET_PAUSE: "Pause Wallet",
      WALLET_UNPAUSE: "Unpause Wallet",
      MANDATORY_ESCROW: "Mandatory Escrow",
      RELEASE_ESCROW: "Release Escrow",
      POLICY_UPDATE: "Update Policy",
      WHITELIST_ADD: "Add to Whitelist",
      WHITELIST_REMOVE: "Remove from Whitelist",
      BLACKLIST_ADD: "Add to Blacklist",
      BLACKLIST_REMOVE: "Remove from Blacklist",
      EMERGENCY_STOP: "Emergency Stop"
    };
    return labels[type] || type;
  }
};

// src/services/dashboard.ts
var DashboardService = class extends BaseService {
  constructor(http, events) {
    super(http, events);
  }
  /**
   * Get dashboard overview statistics
   */
  async getStats(filters) {
    const response = await this.http.get(
      "/monitoring/dashboard/stats",
      { params: filters }
    );
    return response.data;
  }
  /**
   * Get active alerts
   */
  async getAlerts(options) {
    const response = await this.http.get(
      "/monitoring/alerts",
      { params: options }
    );
    return response.data.alerts;
  }
  /**
   * Mark an alert as read
   */
  async markAlertRead(alertId) {
    await this.http.patch(`/monitoring/alerts/${alertId}`, { isRead: true });
    this.events.emit("dashboard:alert_read", { alertId });
  }
  /**
   * Dismiss an alert
   */
  async dismissAlert(alertId) {
    await this.http.delete(`/monitoring/alerts/${alertId}`);
    this.events.emit("dashboard:alert_dismissed", { alertId });
  }
  /**
   * Get risk distribution
   */
  async getRiskDistribution(filters) {
    const response = await this.http.get(
      "/monitoring/dashboard/risk-distribution",
      { params: filters }
    );
    return response.data;
  }
  /**
   * Get activity metrics over time
   */
  async getActivityMetrics(timeRange = "24h") {
    const response = await this.http.get(
      "/monitoring/dashboard/activity",
      { params: { timeRange } }
    );
    return response.data.metrics;
  }
  /**
   * Get Sankey flow visualization data
   */
  async getSankeyFlow(options) {
    const response = await this.http.get(
      "/monitoring/dashboard/sankey",
      { params: options }
    );
    return response.data;
  }
  /**
   * Get top risk entities
   */
  async getTopRiskEntities(limit = 10) {
    const response = await this.http.get(
      "/monitoring/dashboard/top-risk",
      { params: { limit } }
    );
    return response.data.entities;
  }
  /**
   * Get geographic risk map data
   */
  async getGeographicRiskMap() {
    const response = await this.http.get(
      "/monitoring/dashboard/geographic"
    );
    return response.data;
  }
  /**
   * Get real-time metrics
   */
  async getRealTimeMetrics() {
    const response = await this.http.get("/monitoring/dashboard/realtime");
    return response.data;
  }
  /**
   * Export dashboard data
   */
  async exportData(format, filters) {
    const response = await this.http.get("/monitoring/dashboard/export", {
      params: { format, ...filters },
      responseType: "blob"
    });
    return response.data;
  }
  /**
   * Subscribe to real-time updates (returns cleanup function)
   */
  subscribeToUpdates(callback) {
    const interval = setInterval(async () => {
      try {
        const metrics = await this.getRealTimeMetrics();
        callback({ type: "metrics", data: metrics });
      } catch {
      }
    }, 5e3);
    return () => clearInterval(interval);
  }
  /**
   * Format alert for display
   */
  static formatAlert(alert) {
    const colors = {
      low: "blue",
      medium: "yellow",
      high: "orange",
      critical: "red"
    };
    const icons = {
      transaction: "\u{1F4B8}",
      policy: "\u{1F4DC}",
      sanctions: "\u{1F6AB}",
      ml: "\u{1F916}",
      system: "\u2699\uFE0F"
    };
    return {
      title: alert.title,
      description: alert.message,
      time: new Date(alert.timestamp).toLocaleString(),
      color: colors[alert.severity] || "gray",
      icon: icons[alert.type] || "\u{1F4CC}"
    };
  }
};

// src/client.ts
var AMTTPClient = class {
  constructor(config) {
    this.config = {
      baseUrl: config.baseUrl,
      apiKey: config.apiKey,
      timeout: config.timeout ?? 3e4,
      retryAttempts: config.retryAttempts ?? 3,
      mevConfig: config.mevConfig,
      debug: config.debug ?? false
    };
    this.http = import_axios.default.create({
      baseURL: this.config.baseUrl,
      timeout: this.config.timeout,
      headers: {
        "Content-Type": "application/json",
        ...this.config.apiKey && { "X-API-Key": this.config.apiKey }
      }
    });
    this.setupInterceptors();
    this.events = new EventEmitter();
    this.risk = new RiskService(this.http, this.events);
    this.kyc = new KYCService(this.http, this.events);
    this.transactions = new TransactionService(this.http, this.events);
    this.policy = new PolicyService(this.http, this.events);
    this.disputes = new DisputeService(this.http, this.events);
    this.reputation = new ReputationService(this.http, this.events);
    this.bulk = new BulkService(this.http, this.events);
    this.webhooks = new WebhookService(this.http, this.events);
    this.pep = new PEPService(this.http, this.events);
    this.edd = new EDDService(this.http, this.events);
    this.monitoring = new MonitoringService(this.http, this.events);
    this.labels = new LabelService(this.http, this.events);
    this.mev = new MEVProtection(this.http, this.events);
    this.compliance = new ComplianceService(this.http, this.events);
    this.explainability = new ExplainabilityService(this.http, this.events);
    this.sanctions = new SanctionsService(this.http, this.events);
    this.geographic = new GeographicRiskService(this.http, this.events);
    this.integrity = new IntegrityService(this.http, this.events);
    this.governance = new GovernanceService(this.http, this.events);
    this.dashboard = new DashboardService(this.http, this.events);
    if (this.config.mevConfig) {
      this.mev.setConfig(this.config.mevConfig);
    }
    if (this.config.debug) {
      console.log("[AMTTP] Client initialized", { baseUrl: this.config.baseUrl });
    }
  }
  setupInterceptors() {
    this.http.interceptors.request.use(
      (config) => {
        if (this.config.debug) {
          console.log(`[AMTTP] ${config.method?.toUpperCase()} ${config.url}`, config.data);
        }
        return config;
      },
      (error) => Promise.reject(error)
    );
    this.http.interceptors.response.use(
      (response) => {
        if (this.config.debug) {
          console.log(`[AMTTP] Response:`, response.data);
        }
        return response;
      },
      async (error) => {
        const amttpError = this.handleError(error);
        const config = error.config;
        if (amttpError.isRetryable() && config && !config._retryCount) {
          config._retryCount = config._retryCount ?? 0;
          if (config._retryCount < this.config.retryAttempts) {
            config._retryCount++;
            const delay = Math.pow(2, config._retryCount) * 1e3;
            if (this.config.debug) {
              console.log(`[AMTTP] Retrying request (attempt ${config._retryCount})...`);
            }
            await new Promise((resolve) => setTimeout(resolve, delay));
            return this.http(config);
          }
        }
        this.events.emit("error", amttpError);
        throw amttpError;
      }
    );
  }
  handleError(error) {
    if (error.response) {
      return AMTTPError.fromResponse({
        status: error.response.status,
        data: error.response.data
      });
    }
    if (error.code === "ECONNABORTED") {
      return new AMTTPError("Request timeout", "TIMEOUT" /* TIMEOUT */);
    }
    return new AMTTPError(
      error.message || "Network error",
      "NETWORK_ERROR" /* NETWORK_ERROR */
    );
  }
  /**
   * Health check for the API
   */
  async healthCheck() {
    const response = await this.http.get("/health");
    return response.data;
  }
  /**
   * Get current API configuration
   */
  getConfig() {
    return { ...this.config };
  }
  /**
   * Update API key
   */
  setApiKey(apiKey) {
    this.http.defaults.headers["X-API-Key"] = apiKey;
  }
};
// Annotate the CommonJS export names for ESM import in node:
0 && (module.exports = {
  AMTTPClient,
  AMTTPError,
  AMTTPErrorCode,
  BulkService,
  ComplianceService,
  DashboardService,
  DisputeService,
  EDDService,
  EventEmitter,
  ExplainabilityService,
  GeographicRiskService,
  GovernanceService,
  IntegrityService,
  KYCService,
  LabelService,
  MEVProtection,
  MonitoringService,
  PEPService,
  PolicyService,
  ReputationService,
  RiskService,
  SanctionsService,
  TransactionService,
  WebhookService
});
