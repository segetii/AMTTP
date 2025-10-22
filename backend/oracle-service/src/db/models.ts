// backend/src/db/models.ts
import mongoose from "mongoose";

const KycSchema = new mongoose.Schema({
  userId: { type: String, index: true },
  provider: { type: String, enum: ["sumsub","yoti"], required: true },
  providerApplicantId: String,
  level: { type: String, default: "KYC_BASIC" },
  status: { type: String, enum: ["init","pending","approved","rejected"], index: true },
  kycHash: { type: String, index: true },
  resultRaw: mongoose.Schema.Types.Mixed,
}, { timestamps: true });

const RiskSchema = new mongoose.Schema({
  userId: { type: String, index: true },
  input: mongoose.Schema.Types.Mixed,
  engineScore: Number,       // 0..1 from your Python model
  walletRisk: Number,        // 0..100 (if you add Chainalysis later)
  riskLevel: Number,         // 1=low,2=medium,3=high (derived)
  explanation: String
}, { timestamps: true });

// Enhanced DQN Risk Scoring Model for audit trail and analytics
const RiskScoreSchema = new mongoose.Schema({
  transactionHash: { type: String, index: true },
  fromAddress: { type: String, required: true, index: true },
  toAddress: { type: String, required: true, index: true },
  amount: { type: Number, required: true },
  riskScore: { type: Number, required: true, min: 0, max: 1 }, // 0-1 from DQN model
  riskCategory: { type: String, enum: ["MINIMAL", "LOW", "MEDIUM", "HIGH"], required: true },
  confidence: { type: Number, min: 0, max: 1 }, // Model confidence
  modelVersion: { type: String, required: true }, // Track model versions
  features: [Number], // Feature vector used for scoring
  recommendations: [String], // Action recommendations
  timestamp: { type: Date, default: Date.now, index: true },
  // Performance tracking
  f1Score: Number, // Model F1 score at time of prediction
  trainingDate: String, // When the model was trained
  // Additional metadata
  processingTime: Number, // Time taken to score (ms)
  source: { type: String, default: "api" }, // Source of the request
  validated: Boolean, // If prediction was later validated
  actualOutcome: String // Actual fraud outcome (for model improvement)
}, { timestamps: true });

// Add compound indexes for common queries
RiskScoreSchema.index({ fromAddress: 1, timestamp: -1 });
RiskScoreSchema.index({ toAddress: 1, timestamp: -1 });
RiskScoreSchema.index({ riskCategory: 1, timestamp: -1 });
RiskScoreSchema.index({ modelVersion: 1, timestamp: -1 });

const SwapSchema = new mongoose.Schema({
  buyer: String,
  seller: String,
  assetType: { type: String, enum: ["ETH","ERC20","ERC721"] },
  token: String,
  tokenId: String,
  amount: String,            // wei as string
  timelock: Number,
  kycHash: String,
  riskLevel: Number,
  swapId: { type: String, index: true },
  txHash: String,
  status: { type: String, enum: ["initiated","completed","refunded","frozen"], default: "initiated" },
  // Enhanced with DQN risk scoring
  dqnRiskScore: Number,      // DQN model risk score (0-1)
  dqnRiskCategory: String,   // Risk category from DQN
  riskModelVersion: String   // Version of risk model used
}, { timestamps: true });

export const KycModel = mongoose.model("Kyc", KycSchema);
export const RiskModel = mongoose.model("Risk", RiskSchema);
export const RiskScoreModel = mongoose.model("RiskScore", RiskScoreSchema);
export const SwapModel = mongoose.model("Swap", SwapSchema);
