/**
 * Production Explainability Demo
 * 
 * Run: node --experimental-specifier-resolution=node --loader ts-node/esm demo-production.ts
 * Or: npx ts-node --esm demo-production.ts
 */

import { 
  ExplainabilityService,
  RiskExplainer,
  explainRiskDecision,
  RiskAction,
  ImpactLevel
} from './explainability/index.js';

// ═══════════════════════════════════════════════════════════════════════════════
// SAMPLE TRANSACTION DATA
// ═══════════════════════════════════════════════════════════════════════════════

const sampleRequest = {
  transactionId: 'tx-0x1234567890abcdef',
  riskScore: 0.73,
  features: {
    amountEth: 847.5,
    amountVsAverage: 12.3,
    avgAmount30d: 68.9,
    txCount1h: 3,
    txCount24h: 8,
    uniqueRecipients24h: 5,
    dormancyDays: 190,
    sanctionsMatch: false,
    countryCode: 'AE',
    fatfCountryRisk: 'greylist' as const,
    xgbProb: 0.73
  },
  graphContext: {
    pagerank: 0.00035,
    inDegree: 45,
    outDegree: 12,
    clusteringCoefficient: 0.65,
    hopsToSanctioned: 2,
    hopsToMixer: 4,
    mixerInteraction: false,
    degradedMode: false,
  },
  ruleResults: [
    {
      ruleType: 'LAYERING',
      triggered: true,
      severity: 'HIGH' as const,
      confidence: 0.85,
      description: 'Complex transaction chain with 4 hops preserving 95% value',
      evidence: { chainLength: 4, valuePreserved: 0.95, timeWindowHours: 2.5 }
    },
    {
      ruleType: 'VELOCITY_ANOMALY',
      triggered: true,
      severity: 'MEDIUM' as const,
      confidence: 0.7,
      description: '8 transactions in 24 hours after 190 days of inactivity',
      evidence: { txCount24h: 8, dormancyDays: 190 }
    }
  ]
};

// ═══════════════════════════════════════════════════════════════════════════════
// DEMO 1: Using ExplainabilityService (production recommended)
// ═══════════════════════════════════════════════════════════════════════════════

async function demoService() {
  console.log('\n' + '═'.repeat(80));
  console.log('  DEMO 1: ExplainabilityService (Production Mode)');
  console.log('═'.repeat(80) + '\n');
  
  const service = new ExplainabilityService();
  service.setEthPrice(2500);
  
  const response = await service.explain(sampleRequest);
  
  if (!response.success || !response.explanation) {
    console.error('Failed:', response.error);
    return;
  }
  
  const explanation = response.explanation;
  
  printExplanation(explanation);
  
  // Show health
  console.log('\n📊 Service Health:', service.getHealth());
}

// ═══════════════════════════════════════════════════════════════════════════════
// DEMO 2: Using RiskExplainer directly (simpler)
// ═══════════════════════════════════════════════════════════════════════════════

async function demoExplainer() {
  console.log('\n' + '═'.repeat(80));
  console.log('  DEMO 2: RiskExplainer (Direct Usage)');
  console.log('═'.repeat(80) + '\n');
  
  const explainer = new RiskExplainer({ ethPriceUsd: 2500 });
  
  const explanation = explainer.explain(
    sampleRequest.riskScore,
    sampleRequest.features,
    sampleRequest.graphContext,
    sampleRequest.ruleResults
  );
  
  printExplanation(explanation);
}

// ═══════════════════════════════════════════════════════════════════════════════
// DEMO 3: Using convenience function (quickest)
// ═══════════════════════════════════════════════════════════════════════════════

async function demoConvenience() {
  console.log('\n' + '═'.repeat(80));
  console.log('  DEMO 3: Convenience Function (Quick Usage)');
  console.log('═'.repeat(80) + '\n');
  
  const explanation = explainRiskDecision(
    0.73,
    { amountEth: 847.5, dormancyDays: 190 },
    { hopsToSanctioned: 2 },
    [{ ruleType: 'LAYERING', triggered: true, confidence: 0.85 }],
    2500
  );
  
  console.log('📊 Risk Score:', (explanation.riskScore * 100).toFixed(1) + '%');
  console.log('🎯 Action:', explanation.action);
  console.log('📝 Summary:', explanation.summary);
  console.log('🎲 Confidence:', (explanation.confidence * 100).toFixed(0) + '%');
  console.log('\n📋 Top Reasons:');
  explanation.topReasons.forEach((r, i) => console.log(`   ${i+1}. ${r}`));
}

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER: Print explanation
// ═══════════════════════════════════════════════════════════════════════════════

function printExplanation(explanation: any) {
  console.log('📊 RISK SCORE:', (explanation.riskScore * 100).toFixed(1) + '%');
  console.log('🎯 ACTION:', explanation.action);
  console.log('📝 SUMMARY:', explanation.summary);
  console.log('🎲 CONFIDENCE:', (explanation.confidence * 100).toFixed(0) + '%');
  
  console.log('\n' + '─'.repeat(80));
  console.log('TOP REASONS:');
  console.log('─'.repeat(80));
  explanation.topReasons.forEach((reason: string, i: number) => {
    console.log(`  ${i + 1}. ${reason}`);
  });
  
  if (explanation.typologyMatches?.length > 0) {
    console.log('\n' + '─'.repeat(80));
    console.log('DETECTED PATTERNS:');
    console.log('─'.repeat(80));
    explanation.typologyMatches.forEach((match: any) => {
      console.log(`\n  🔍 ${match.typology.toUpperCase()} (${(match.confidence * 100).toFixed(0)}% confidence)`);
      console.log(`     ${match.description}`);
      if (match.regulatoryGuidance) {
        console.log(`     📚 Ref: ${match.regulatoryGuidance}`);
      }
    });
  }
  
  if (explanation.graphExplanation) {
    console.log('\n' + '─'.repeat(80));
    console.log('NETWORK ANALYSIS:');
    console.log('─'.repeat(80));
    console.log(`  ${explanation.graphExplanation}`);
  }
  
  console.log('\n' + '─'.repeat(80));
  console.log('RECOMMENDATIONS:');
  console.log('─'.repeat(80));
  explanation.recommendations.forEach((rec: string) => {
    console.log(`  ▸ ${rec}`);
  });
  
  console.log('\n' + '─'.repeat(80));
  console.log('CONTRIBUTING FACTORS:');
  console.log('─'.repeat(80));
  const impactEmoji: Record<string, string> = {
    CRITICAL: '🔴',
    HIGH: '🟠', 
    MEDIUM: '🟡',
    LOW: '🟢',
    NEUTRAL: '⚪'
  };
  explanation.factors.slice(0, 8).forEach((factor: any) => {
    console.log(`  ${impactEmoji[factor.impact]} [${factor.impact}] ${factor.humanReadable}`);
    console.log(`     Category: ${factor.category} | ${factor.technicalDetail}`);
    if (factor.regulatoryRef) {
      console.log(`     📚 ${factor.regulatoryRef}`);
    }
  });
  
  console.log('\n' + '─'.repeat(80));
  console.log('METADATA:');
  console.log('─'.repeat(80));
  console.log(`  Version: ${explanation.metadata.explainerVersion}`);
  console.log(`  Generated: ${explanation.metadata.generatedAt}`);
  console.log(`  Processing: ${explanation.metadata.processingTimeMs}ms`);
  console.log(`  Config Hash: ${explanation.metadata.configHash}`);
  if (explanation.degradedMode) {
    console.log(`  ⚠️  DEGRADED MODE: ${explanation.degradedComponents?.join(', ')}`);
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// RUN DEMOS
// ═══════════════════════════════════════════════════════════════════════════════

async function main() {
  console.log('\n' + '╔'.padEnd(79, '═') + '╗');
  console.log('║' + '  AMTTP PRODUCTION EXPLAINABILITY SYSTEM - DEMO'.padEnd(78) + '║');
  console.log('╚'.padEnd(79, '═') + '╝');
  
  await demoService();
  await demoExplainer();
  await demoConvenience();
  
  console.log('\n' + '═'.repeat(80));
  console.log('  DEMO COMPLETE');
  console.log('═'.repeat(80) + '\n');
}

main().catch(console.error);
