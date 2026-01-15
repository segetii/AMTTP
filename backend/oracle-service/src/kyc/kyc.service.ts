// backend/src/kyc/kyc.service.ts
import { sumsubCreateApplicant, sumsubGetApplicant } from "./sumsub.js";
import { yotiCreateSession, yotiGetSession } from "./yoti.js";

export async function createKyc(userId: string) {
  if (process.env.KYC_PROVIDER === "sumsub") {
    const a = await sumsubCreateApplicant({ externalUserId: userId });
    return { provider: "sumsub", applicantId: a.id, level: "KYC_BASIC" };
  } else if (process.env.KYC_PROVIDER === "yoti") {
    const session = await yotiCreateSession(userId);
    return { 
      provider: "yoti", 
      sessionId: session.sessionId, 
      sessionUrl: session.sessionUrl,
      clientToken: session.clientSessionToken 
    };
  } else {
    throw new Error(`Unknown KYC provider: ${process.env.KYC_PROVIDER}. Supported: sumsub, yoti`);
  }
}

export async function getKycStatus(id: string) {
  if (process.env.KYC_PROVIDER === "sumsub") {
    const s = await sumsubGetApplicant(id);
    // map provider status → "approved" | "pending" | "rejected"
    const status = s?.reviewStatus?.reviewAnswer === "GREEN" ? "approved"
                 : s?.reviewStatus?.reviewAnswer === "RED"   ? "rejected"
                 : "pending";
    return { provider: "sumsub", status, raw: s };
  } else if (process.env.KYC_PROVIDER === "yoti") {
    const result = await yotiGetSession(id);
    return { 
      provider: "yoti", 
      status: result.status, 
      checks: result.checks,
      attributes: result.attributes 
    };
  } else {
    throw new Error(`Unknown KYC provider: ${process.env.KYC_PROVIDER}. Supported: sumsub, yoti`);
  }
}
