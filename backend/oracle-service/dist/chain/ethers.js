// backend/src/chain/ethers.ts
import { ethers } from "ethers";
export const provider = new ethers.JsonRpcProvider(process.env.RPC_URL);
export const wallet = new ethers.Wallet(process.env.PRIVATE_KEY, provider);
