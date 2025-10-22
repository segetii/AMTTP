// backend/src/routes/tx.ts
import { Router } from "express";
import { amttp } from "../chain/amttp.js";
import { RiskModel, SwapModel } from "../db/models.js";
import { ethers } from "ethers";

export const txRouter = Router();

// Send ETH swap using AMTTPUpgradeable.initiateSwapETH
txRouter.post("/sendTransaction", async (req, res) => {
  const { buyer, seller, amountEth, timelockSec, secret, kycHash, riskLevel } = req.body;

  // compute hash(secret)
  const secretHash = ethers.keccak256(ethers.toUtf8Bytes(secret));
  const amountWei = ethers.parseEther(amountEth);

  // call contract
  try {
    const tx = await amttp.initiateSwapETH(
      seller,
      secretHash,
      Math.floor(Date.now() / 1000) + (timelockSec ?? 3600),
      riskLevel ?? 1,
      kycHash ?? ethers.ZeroHash,
      "0x",                               // oracleSig optional
      { value: amountWei }
    );
    const rc = await tx.wait();
    // compute swapId locally (same logic as contract)
    const swapId = ethers.keccak256(ethers.AbiCoder.defaultAbiCoder().encode(
      ["address","address","bytes32","uint256","uint8","address","uint256","uint256"],
      [buyer, seller, secretHash, Math.floor(Date.now()/1000) + (timelockSec ?? 3600), 0, ethers.ZeroAddress, 0, amountWei] // matches computeSwapId args
    ));

    await SwapModel.create({
      buyer, seller, assetType: "ETH", token: null, tokenId: null,
      amount: amountWei.toString(), timelock: Math.floor(Date.now()/1000) + (timelockSec ?? 3600),
      kycHash, riskLevel, swapId, txHash: rc?.hash, status: "initiated"
    });
    res.json({ ok: true, txHash: rc?.hash, swapId });
  } catch (e: any) {
    res.status(500).json({ ok: false, error: e?.message || "tx failed" });
  }
});
