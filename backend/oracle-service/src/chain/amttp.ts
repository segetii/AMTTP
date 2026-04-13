// backend/src/chain/amttp.ts
import { Contract } from "ethers";
import { wallet } from "./ethers.js";
import AMTTP_ABI from "./abi/AMTTP.json" with { type: "json" };

const AMTTP_ADDRESS = process.env.AMTTP_ADDRESS || null;

export const amttp = AMTTP_ADDRESS
  ? new Contract(AMTTP_ADDRESS, AMTTP_ABI.abi, wallet)
  : null;

if (!AMTTP_ADDRESS) {
  console.warn("[chain/amttp] AMTTP_ADDRESS not set — contract interactions disabled.");
}
