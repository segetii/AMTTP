// backend/src/kyc/yoti.ts
/**
 * Yoti Identity Verification Integration
 *
 * Yoti IDV uses SDK ID and private key (RSA) to create verification sessions.
 * Users complete verification via Yoti app or web SDK.
 *
 * Environment variables required:
 * - YOTI_SDK_ID: Your Yoti SDK/Client ID
 * - YOTI_PRIVATE_KEY_BASE64: Base64-encoded RSA private key (PEM)
 * - YOTI_BASE_URL: API base URL (default: https://api.yoti.com/idverify/v1)
 */
import axios from "axios";
import crypto from "crypto";
import { v4 as uuidv4 } from "uuid";
const YOTI_BASE_URL = process.env.YOTI_BASE_URL || "https://api.yoti.com/idverify/v1";
/**
 * Create a Yoti Identity Verification session
 */
export async function yotiCreateSession(userId, config) {
    validateYotiConfig();
    const sdkId = process.env.YOTI_SDK_ID;
    const sessionSpec = buildSessionSpec(userId, config);
    const endpoint = `/sessions`;
    const { signature, nonce, timestamp } = signRequest("POST", endpoint, JSON.stringify(sessionSpec));
    const headers = {
        "X-Yoti-Auth-Id": sdkId,
        "X-Yoti-Auth-Digest": signature,
        "X-Yoti-Auth-Nonce": nonce,
        "X-Yoti-Auth-Timestamp": timestamp,
        "Content-Type": "application/json",
    };
    try {
        const { data } = await axios.post(`${YOTI_BASE_URL}${endpoint}`, sessionSpec, { headers });
        return {
            sessionId: data.session_id,
            clientSessionToken: data.client_session_token,
            sessionUrl: `https://api.yoti.com/idverify/v1/sessions/${data.session_id}/client`,
            status: "created",
        };
    }
    catch (error) {
        console.error("Yoti session creation failed:", error.response?.data || error.message);
        throw new Error(`Yoti session creation failed: ${error.response?.data?.message || error.message}`);
    }
}
/**
 * Get Yoti session status and results
 */
export async function yotiGetSession(sessionId) {
    validateYotiConfig();
    const sdkId = process.env.YOTI_SDK_ID;
    const endpoint = `/sessions/${sessionId}`;
    const { signature, nonce, timestamp } = signRequest("GET", endpoint);
    const headers = {
        "X-Yoti-Auth-Id": sdkId,
        "X-Yoti-Auth-Digest": signature,
        "X-Yoti-Auth-Nonce": nonce,
        "X-Yoti-Auth-Timestamp": timestamp,
    };
    try {
        const { data } = await axios.get(`${YOTI_BASE_URL}${endpoint}`, { headers });
        // Map Yoti state to our standard status
        const status = mapYotiStatus(data.state, data.checks || []);
        return {
            sessionId: data.session_id,
            status,
            checks: (data.checks || []).map((c) => ({
                type: c.type,
                state: c.state,
                recommendation: c.report?.recommendation,
            })),
            attributes: extractAttributes(data),
        };
    }
    catch (error) {
        console.error("Yoti session fetch failed:", error.response?.data || error.message);
        throw new Error(`Yoti session fetch failed: ${error.response?.data?.message || error.message}`);
    }
}
/**
 * Delete/invalidate a Yoti session
 */
export async function yotiDeleteSession(sessionId) {
    validateYotiConfig();
    const sdkId = process.env.YOTI_SDK_ID;
    const endpoint = `/sessions/${sessionId}`;
    const { signature, nonce, timestamp } = signRequest("DELETE", endpoint);
    const headers = {
        "X-Yoti-Auth-Id": sdkId,
        "X-Yoti-Auth-Digest": signature,
        "X-Yoti-Auth-Nonce": nonce,
        "X-Yoti-Auth-Timestamp": timestamp,
    };
    await axios.delete(`${YOTI_BASE_URL}${endpoint}`, { headers });
}
// --- Helper Functions ---
function validateYotiConfig() {
    if (!process.env.YOTI_SDK_ID) {
        throw new Error("YOTI_SDK_ID environment variable is required");
    }
    if (!process.env.YOTI_PRIVATE_KEY_BASE64) {
        throw new Error("YOTI_PRIVATE_KEY_BASE64 environment variable is required");
    }
}
function getPrivateKey() {
    const keyBase64 = process.env.YOTI_PRIVATE_KEY_BASE64;
    return Buffer.from(keyBase64, "base64").toString("utf-8");
}
function signRequest(method, endpoint, body) {
    const privateKey = getPrivateKey();
    const nonce = uuidv4();
    const timestamp = new Date().toISOString();
    // Build message to sign: METHOD&ENDPOINT&NONCE&TIMESTAMP&BODY_HASH
    const bodyHash = body ? crypto.createHash("sha256").update(body).digest("base64") : "";
    const message = `${method}&${endpoint}&${nonce}&${timestamp}&${bodyHash}`;
    // Sign with RSA-SHA256
    const sign = crypto.createSign("RSA-SHA256");
    sign.update(message);
    const signature = sign.sign(privateKey, "base64");
    return { signature, nonce, timestamp };
}
function buildSessionSpec(userId, config) {
    return {
        session_deadline: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(), // 7 days
        resources_ttl: 604800, // 7 days in seconds
        user_tracking_id: userId,
        notifications: {
            endpoint: process.env.YOTI_WEBHOOK_URL || undefined,
            topics: ["SESSION_COMPLETION", "CHECK_COMPLETION"],
        },
        requested_checks: [
            { type: "ID_DOCUMENT_AUTHENTICITY" },
            { type: "ID_DOCUMENT_TEXT_DATA_CHECK" },
            { type: "ID_DOCUMENT_FACE_MATCH" },
            { type: "LIVENESS" },
        ],
        requested_tasks: [
            {
                type: "ID_DOCUMENT_TEXT_DATA_EXTRACTION",
                config: {
                    manual_check: "FALLBACK",
                },
            },
        ],
        required_documents: [
            {
                type: "ID_DOCUMENT",
                filter: {
                    type: "DOCUMENT_RESTRICTIONS",
                    inclusion: "INCLUDE",
                    documents: [
                        { country_codes: ["GBR"], document_types: ["PASSPORT", "DRIVING_LICENCE"] },
                        { country_codes: ["*"], document_types: ["PASSPORT"] },
                    ],
                },
            },
        ],
        sdk_config: {
            allowed_capture_methods: "CAMERA_AND_UPLOAD",
            primary_colour: "#2D9CDB",
            secondary_colour: "#FFFFFF",
            font_colour: "#FFFFFF",
            locale: "en-GB",
            preset_issuing_country: "GBR",
            success_url: config?.redirectUrl || process.env.YOTI_SUCCESS_URL,
            error_url: process.env.YOTI_ERROR_URL,
        },
    };
}
function mapYotiStatus(state, checks) {
    if (state === "COMPLETED") {
        // Check if all checks passed
        const allPassed = checks.every((c) => c.state === "DONE" && c.report?.recommendation?.value === "APPROVE");
        const anyRejected = checks.some((c) => c.report?.recommendation?.value === "REJECT");
        if (allPassed)
            return "approved";
        if (anyRejected)
            return "rejected";
        return "pending"; // Manual review needed
    }
    if (state === "EXPIRED")
        return "expired";
    return "pending";
}
function extractAttributes(data) {
    const attrs = {};
    // Extract identity attributes from completed checks
    if (data.resources?.id_documents) {
        for (const doc of data.resources.id_documents) {
            if (doc.document_fields) {
                attrs.fullName = doc.document_fields.full_name;
                attrs.dateOfBirth = doc.document_fields.date_of_birth;
                attrs.nationality = doc.document_fields.nationality;
                attrs.documentNumber = doc.document_fields.document_number;
                attrs.expiryDate = doc.document_fields.expiry_date;
                attrs.documentType = doc.document_type;
                attrs.issuingCountry = doc.issuing_country;
            }
        }
    }
    return attrs;
}
