// backend/src/chain/ethers.ts
import { ethers } from "ethers";

const rpcUrl = process.env.RPC_URL || "http://localhost:8545";
export const provider = new ethers.JsonRpcProvider(rpcUrl);

// Graceful fallback: generate ephemeral wallet if PRIVATE_KEY not set
const pk = process.env.PRIVATE_KEY || ethers.Wallet.createRandom().privateKey;
if (!process.env.PRIVATE_KEY) {
  console.warn("[chain/ethers] PRIVATE_KEY not set — using ephemeral wallet. On-chain writes will not persist.");
}
export const wallet = new ethers.Wallet(pk, provider);
