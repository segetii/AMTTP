import express from "express";
import cors from "cors";
import mongoose from "mongoose";
import { kycRouter } from "./routes/kyc.js";
import { riskRouter } from "./routes/risk.js";
import { txRouter } from "./routes/tx.js";
import { policyRouter } from "./routes/policy.js";
import { labelRouter } from "./routes/label.js";
import { explainabilityRouter } from "./routes/explainability.js";
// New gap-bridging modules
import { disputeRouter } from "./dispute/dispute-resolution.js";
import { reputationRouter } from "./reputation/reputation-service.js";
import { bulkRouter } from "./bulk/bulk-scoring.js";
import { webhookRouter } from "./webhooks/webhook-service.js";
import { pepRouter } from "./pep/pep-screening.js";
import { eddRouter } from "./edd/edd-workflow.js";
import { monitoringRouter } from "./monitoring/ongoing-monitoring.js";
const app = express();
app.use(cors());
app.use(express.json({ limit: '10mb' })); // Increased for bulk API
// Basic health endpoint for container health checks
app.get('/health', (_req, res) => {
    res.status(200).json({ status: 'ok' });
});
// API info endpoint
app.get('/', (_req, res) => {
    res.json({
        service: 'AMTTP Oracle Service',
        version: '3.0.0',
        endpoints: {
            // Core services
            '/kyc': 'KYC verification endpoints',
            '/risk': 'Risk scoring with DQN/XGBoost hybrid model',
            '/tx': 'Transaction submission endpoints',
            '/policy': 'Policy engine (FCA/AMLD6 compliant)',
            '/label': 'Label submission with RBAC & dual-control',
            '/explainability': 'Human-readable risk explanations API (NEW)',
            // P2P Use Case
            '/dispute': 'P2P dispute resolution (Kleros integration)',
            '/reputation': 'On-chain reputation system for P2P actors',
            // Exchange Use Case
            '/bulk': 'Bulk transaction scoring (1000+ tx/batch)',
            '/webhook': 'Webhooks & SSE streaming for real-time alerts',
            // PEP/High-Risk Use Case
            '/pep': 'PEP database screening (Dow Jones/Refinitiv)',
            '/edd': 'Enhanced Due Diligence document workflow',
            '/monitoring': 'Ongoing PEP/sanctions re-screening',
        },
        useCaseCoverage: {
            'Individual P2P': '95%+ (dispute resolution, reputation, escrow)',
            'Exchanges': '95%+ (bulk API, webhooks, streaming)',
            'PEP Handling': '95%+ (PEP screening, EDD, ongoing monitoring)',
        },
        architecture: {
            policyEngine: 'Cedar-style policy-as-code layer',
            oracleTrust: 'Signed responses with ECDSA/RSA',
            labelSafeguards: 'RBAC + dual-control + provenance',
            fcaCompliance: 'Air-gapped service on port 8002',
            explainability: 'Human-readable ML decision explanations',
        },
    });
});
// Core routes
app.use("/kyc", kycRouter);
app.use("/risk", riskRouter);
app.use("/tx", txRouter);
app.use("/policy", policyRouter);
app.use("/label", labelRouter);
app.use("/explainability", explainabilityRouter);
// P2P Use Case routes
app.use("/dispute", disputeRouter);
app.use("/reputation", reputationRouter);
// Exchange Use Case routes
app.use("/bulk", bulkRouter);
app.use("/webhook", webhookRouter);
// PEP/High-Risk Use Case routes
app.use("/pep", pepRouter);
app.use("/edd", eddRouter);
app.use("/monitoring", monitoringRouter);
async function start() {
    await mongoose.connect(process.env.MONGO_URI);
    const port = process.env.PORT || 3000;
    app.listen(port, () => console.log(`oracle-service listening on ${port}`));
}
// Only start the server if this file is executed directly
if (process.env.NODE_ENV !== 'test') {
    start();
}
export { app };
