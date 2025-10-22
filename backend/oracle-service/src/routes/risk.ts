// backend/src/routes/risk.ts
import { Router } from "express";
import { scoreRisk, scoreDQNTransaction, getRiskModelStatus } from "../risk/risk.service.js";
import { RiskScoreModel } from "../db/models.js";

export const riskRouter = Router();

// GET /risk - Information endpoint
riskRouter.get("/", (req, res) => {
  res.json({
    message: "AMTTP Risk Scoring API",
    endpoints: {
      "POST /risk/score": "Score transaction risk using DQN model (enhanced)",
      "POST /risk/dqn-score": "Direct DQN model scoring with your trained model",
      "GET /risk/models/status": "Get current model status and performance",
      "GET /risk/history/:address": "Get risk scoring history for address"
    },
    modelInfo: {
      version: "DQN-v1.0-real-fraud",
      performance: "F1=0.669+ (Production Ready)",
      trainingData: "28,457 real fraud transactions"
    }
  });
});

// Enhanced risk scoring with DQN integration
riskRouter.post("/score", async (req, res) => {
  try {
    const transactionData = req.body;
    
    // Use your original scoring for backward compatibility
    const basicScore = await scoreRisk(req.body);
    
    // Enhance with DQN model scoring
    const dqnScore = await scoreDQNTransaction(transactionData);
    
    // Combine scores for hybrid approach
    const hybridResult = {
      ...basicScore,
      dqnScore: dqnScore.riskScore,
      dqnConfidence: dqnScore.confidence,
      hybridScore: (basicScore.score * 0.3) + (dqnScore.riskScore * 0.7), // Weight DQN higher
      riskCategory: dqnScore.riskCategory,
      modelVersion: "hybrid-dqn-v1.0"
    };

    // Store in database
    if (transactionData.from && transactionData.to) {
      await RiskScoreModel.create({
        transactionHash: transactionData.transactionHash || null,
        fromAddress: transactionData.from,
        toAddress: transactionData.to,
        amount: transactionData.amount || 0,
        riskScore: hybridResult.hybridScore,
        riskCategory: hybridResult.riskCategory,
        confidence: dqnScore.confidence,
        modelVersion: "hybrid-dqn-v1.0",
        features: dqnScore.features,
        timestamp: new Date()
      });
    }

    res.json(hybridResult);
    
  } catch (error) {
    console.error('Enhanced risk scoring error:', error);
    const msg = error instanceof Error ? error.message : String(error);
    res.status(500).json({ 
      error: 'Risk scoring failed',
      message: msg 
    });
  }
});

// Direct DQN model scoring endpoint
riskRouter.post("/dqn-score", async (req, res) => {
  try {
    const transactionData = req.body;
    
    // Validate required fields
    const requiredFields = ['amount', 'to', 'from'];
    for (const field of requiredFields) {
      if (!transactionData[field]) {
        return res.status(400).json({ 
          error: `Missing required field: ${field}`,
          required: requiredFields 
        });
      }
    }

    // Score using your trained DQN model
    const dqnResult = await scoreDQNTransaction(transactionData);
    
    res.json({
      ...dqnResult,
      modelInfo: {
        version: "DQN-v1.0-real-fraud",
        f1Score: 0.669,
        trainingData: "28,457 real fraud transactions",
        performance: "Production Ready"
      }
    });

  } catch (error) {
    console.error('DQN scoring error:', error);
    const msg = error instanceof Error ? error.message : String(error);
    res.status(500).json({ 
      error: 'DQN scoring failed',
      message: msg 
    });
  }
});
// Get model status and performance
riskRouter.get("/models/status", async (req, res) => {
  try {
    const modelStatus = await getRiskModelStatus();
    res.json(modelStatus);
  } catch (error) {
    console.error('Model status error:', error);
    const msg = error instanceof Error ? error.message : String(error);
    res.status(500).json({ 
      error: 'Failed to get model status',
      message: msg 
    });
  }
});
