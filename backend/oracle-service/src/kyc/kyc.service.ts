// backend/src/kyc/kyc.service.ts
import { sumsubCreateApplicant, sumsubGetApplicant } from "./sumsub.js";
// import { yotiCreateSession, yotiGetSession } from "./yoti";

export async function createKyc(userId: string) {
  if (process.env.KYC_PROVIDER === "sumsub") {
    const a = await sumsubCreateApplicant({ externalUserId: userId });
    return { provider: "sumsub", applicantId: a.id, level: "KYC_BASIC" };
  } else {
    // const s = await yotiCreateSession(userId);
    // return { provider: "yoti", sessionId: s.id };
    throw new Error("Yoti adapter not implemented yet");
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
  } else {
    throw new Error("Yoti adapter not implemented yet");
  }
}
