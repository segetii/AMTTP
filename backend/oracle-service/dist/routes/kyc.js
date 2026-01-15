// backend/src/routes/kyc.ts
import { Router } from "express";
import { createKyc, getKycStatus } from "../kyc/kyc.service.js";
import { KycModel } from "../db/models.js";
import { kycHash as makeHash } from "../utils/hash.js";
export const kycRouter = Router();
// GET /kyc - Information endpoint
kycRouter.get("/", (req, res) => {
    res.json({
        message: "KYC Service API",
        endpoints: {
            "POST /kyc/init": "Initialize KYC process (requires: userId in body)",
            "GET /kyc/status/:applicantId": "Get KYC status by applicant ID",
            "POST /kyc/test-sandbox": "Create fake approved KYC for testing (requires: userId in body)"
        },
        example: {
            init: "POST /kyc/init with body: {\"userId\": \"user-123\"}",
            testSandbox: "POST /kyc/test-sandbox with body: {\"userId\": \"test-user-123\"}"
        }
    });
});
kycRouter.post("/init", async (req, res) => {
    const { userId } = req.body;
    const created = await createKyc(userId);
    const doc = await KycModel.create({
        userId,
        provider: created.provider,
        providerApplicantId: created.applicantId,
        level: created.level,
        status: "init"
    });
    res.json({ applicantId: created.applicantId, level: created.level });
});
kycRouter.get("/status/:applicantId", async (req, res) => {
    const { applicantId } = req.params;
    const status = await getKycStatus(applicantId);
    const kHash = makeHash("user-not-stored", status.provider, "KYC_BASIC", status.status);
    await KycModel.updateOne({ providerApplicantId: applicantId }, { status: status.status, kycHash: kHash, resultRaw: status.raw });
    res.json({ status: status.status, kycHash: kHash });
});
// Test route that bypasses Sumsub entirely for development
kycRouter.post("/test-sandbox", async (req, res) => {
    try {
        const { userId } = req.body;
        if (!userId) {
            return res.status(400).json({ error: "userId is required" });
        }
        // Create a fake approved KYC record
        const fakeApplicantId = `test-${userId}-${Date.now()}`;
        const kHash = makeHash(userId, "sumsub", "KYC_BASIC", "approved");
        const doc = await KycModel.create({
            userId,
            provider: "sumsub",
            providerApplicantId: fakeApplicantId,
            level: "KYC_BASIC",
            status: "approved",
            kycHash: kHash,
            resultRaw: { testMode: true, approvedAt: new Date().toISOString() }
        });
        res.json({
            applicantId: fakeApplicantId,
            level: "KYC_BASIC",
            status: "approved",
            kycHash: kHash,
            testMode: true
        });
    }
    catch (error) {
        console.error("Test sandbox error:", error);
        res.status(500).json({ error: "Internal server error" });
    }
});
