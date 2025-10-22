// backend/src/kyc/yoti.ts
// Outline only – Yoti uses SDK ID and private key to create session links.
// Implement when you decide to run both providers in parallel.
export async function yotiCreateSession(userId: string) {
  // create share session, return sessionId and URL
}
export async function yotiGetSession(sessionId: string) {
  // poll session outcome, return "approved"/"rejected" + attributes
}
