// backend/src/utils/hash.ts
import crypto from "crypto";
export function kycHash(userId, provider, level, status) {
    return "0x" + crypto.createHash("sha256").update(`${provider}:${level}:${status}:${userId}`).digest("hex");
}
