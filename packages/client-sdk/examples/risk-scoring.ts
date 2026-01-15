// examples/risk-scoring.ts
// AMTTP SDK Examples - Risk Scoring

import { AMTTPClient, MLService, PolicyAction, RiskLevel, utils } from '@amttp/client-sdk';

// ============================================================
// Example 1: Basic Risk Scoring
// ============================================================

async function basicScoring() {
  console.log('\n[Example 1: Basic Risk Scoring]');
  
  // Create ML service
  const mlService = new MLService('http://localhost:8000');
  
  // Score a transaction
  const risk = await mlService.scoreTransaction('tx_001', {
    amount: 1.5,          // ETH
    velocity_24h: 3,
    account_age_days: 90,
    country_risk: 0.2,
  });
  
  console.log(`Risk Score: ${utils.formatRiskScore(risk.riskScore)}`);
  console.log(`Risk Level: ${RiskLevel[risk.riskLevel]}`);
  console.log(`Action: ${PolicyAction[risk.action]}`);
  console.log(`Model: ${risk.modelVersion}`);
  console.log('Recommendations:');
  risk.recommendations.forEach(rec => console.log(`  - ${rec}`));
}

// ============================================================
// Example 2: Full Client Integration
// ============================================================

async function fullClientIntegration() {
  console.log('\n[Example 2: Full Client Integration]');
  
  const client = new AMTTPClient({
    rpcUrl: 'https://mainnet.infura.io/v3/YOUR_KEY',
    contractAddress: '0x...',
    oracleUrl: 'http://localhost:3000',
    mlApiUrl: 'http://localhost:8000',
    // privateKey: '0x...', // Optional for signing
  });
  
  // Score transaction risk
  const risk = await client.scoreTransactionRisk({
    from: '0x1234...',
    to: '0x5678...',
    amount: 10,  // ETH
    metadata: {
      velocity_24h: 5,
      account_age_days: 30,
    }
  });
  
  console.log(`Risk Category: ${risk.riskCategory}`);
  console.log(`Confidence: ${(risk.confidence * 100).toFixed(1)}%`);
  
  // Decide action based on risk
  if (risk.riskScore >= 0.7) {
    console.log('⚠️ High risk - Use escrow protection');
  } else if (risk.riskScore >= 0.4) {
    console.log('👀 Medium risk - Requires review');
  } else {
    console.log('✅ Low risk - Proceed normally');
  }
}

// ============================================================
// Example 3: Batch Scoring
// ============================================================

async function batchScoring() {
  console.log('\n[Example 3: Batch Scoring]');
  
  const mlService = new MLService('http://localhost:8000');
  
  const transactions = [
    { id: 'tx_001', features: { amount: 1.0, velocity_24h: 1 } },
    { id: 'tx_002', features: { amount: 5.0, velocity_24h: 10 } },
    { id: 'tx_003', features: { amount: 50.0, velocity_24h: 50 } },
  ];
  
  const risks = await mlService.scoreBatch(transactions);
  
  console.log('Batch Results:');
  risks.forEach((risk, i) => {
    const color = utils.getRiskColor(risk.riskCategory);
    console.log(
      `  ${transactions[i].id}: ` +
      `${utils.formatRiskScore(risk.riskScore)} -> ` +
      `${PolicyAction[risk.action]}`
    );
  });
}

// ============================================================
// Example 4: React Hook Pattern
// ============================================================

/*
// hooks/useRiskScore.ts
import { useState, useCallback } from 'react';
import { MLService, RiskScore } from '@amttp/client-sdk';

const mlService = new MLService(process.env.NEXT_PUBLIC_ML_API_URL);

export function useRiskScore() {
  const [loading, setLoading] = useState(false);
  const [risk, setRisk] = useState<RiskScore | null>(null);
  const [error, setError] = useState<Error | null>(null);

  const scoreTransaction = useCallback(async (
    to: string,
    amount: number,
    features?: Record<string, number>
  ) => {
    setLoading(true);
    setError(null);
    
    try {
      const result = await mlService.scoreTransaction(
        `tx_${Date.now()}`,
        { amount, ...features }
      );
      setRisk(result);
      return result;
    } catch (err) {
      setError(err as Error);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  return { scoreTransaction, risk, loading, error };
}

// Usage in component:
function TransferForm() {
  const { scoreTransaction, risk, loading } = useRiskScore();
  
  const handleSubmit = async (to: string, amount: number) => {
    const riskResult = await scoreTransaction(to, amount);
    
    if (riskResult.action === PolicyAction.BLOCK) {
      alert('Transaction blocked due to high risk');
      return;
    }
    
    if (riskResult.action === PolicyAction.ESCROW) {
      // Use escrow flow
    }
    
    // Proceed with transaction
  };
}
*/

// ============================================================
// Example 5: Express.js Middleware
// ============================================================

/*
// middleware/riskCheck.ts
import { Request, Response, NextFunction } from 'express';
import { MLService, PolicyAction } from '@amttp/client-sdk';

const mlService = new MLService(process.env.ML_API_URL);

export async function riskCheckMiddleware(
  req: Request,
  res: Response,
  next: NextFunction
) {
  const { to, amount, from } = req.body;
  
  if (!to || !amount) {
    return next();
  }
  
  try {
    const risk = await mlService.scoreTransaction(`api_${Date.now()}`, {
      amount: Number(amount),
      from_address: from,
      to_address: to,
    });
    
    // Attach risk to request
    req.riskScore = risk;
    
    // Block high-risk transactions
    if (risk.action === PolicyAction.BLOCK) {
      return res.status(403).json({
        error: 'Transaction blocked due to high risk',
        riskScore: risk.riskScore,
        recommendations: risk.recommendations,
      });
    }
    
    next();
  } catch (error) {
    // Allow transaction but log warning
    console.warn('Risk check failed:', error);
    next();
  }
}

// Usage:
// app.post('/api/transfer', riskCheckMiddleware, transferHandler);
*/

// ============================================================
// Run Examples
// ============================================================

async function main() {
  console.log('='.repeat(60));
  console.log('AMTTP TypeScript SDK Examples');
  console.log('='.repeat(60));
  
  try {
    await basicScoring();
    // await fullClientIntegration();
    // await batchScoring();
  } catch (error) {
    console.error('Example failed:', error);
  }
}

main();
