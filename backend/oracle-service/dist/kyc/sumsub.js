// backend/src/kyc/sumsub.ts
import axios from "axios";
import crypto from "crypto";
export async function sumsubCreateApplicant(p) {
    const base = process.env.SUMSUB_BASE_URL;
    const appToken = process.env.SUMSUB_APP_TOKEN;
    const secret = process.env.SUMSUB_SECRET_KEY;
    const level = p.level ?? "KYC_BASIC";
    const url = `${base}/resources/applicants?levelName=${level}`;
    const ts = Math.floor(Date.now() / 1000);
    const body = { externalUserId: p.externalUserId };
    const signature = sign("POST", `/resources/applicants?levelName=${level}`, ts, JSON.stringify(body), secret);
    const headers = {
        "X-App-Token": appToken,
        "X-App-Access-Sig": signature,
        "X-App-Access-Ts": ts.toString(),
        "Content-Type": "application/json"
    };
    if (process.env.SUMSUB_SANDBOX)
        headers["X-REQUEST-ID"] = `sandbox-${p.externalUserId}-${Date.now()}`;
    const { data } = await axios.post(url, body, { headers });
    return data; // contains applicantId, etc.
}
export async function sumsubGetApplicant(applicantId) {
    const base = process.env.SUMSUB_BASE_URL;
    const appToken = process.env.SUMSUB_APP_TOKEN;
    const secret = process.env.SUMSUB_SECRET_KEY;
    const path = `/resources/applicants/${applicantId}/requiredIdDocsStatus`;
    const url = `${base}${path}`;
    const ts = Math.floor(Date.now() / 1000);
    const signature = sign("GET", path, ts, "", secret);
    const headers = {
        "X-App-Token": appToken,
        "X-App-Access-Sig": signature,
        "X-App-Access-Ts": ts.toString()
    };
    const { data } = await axios.get(url, { headers });
    return data; // status info
}
function sign(method, path, ts, body, secret) {
    const h = crypto.createHmac("sha256", secret);
    h.update(`${ts}${method}${path}${body}`);
    return h.digest("hex");
}
