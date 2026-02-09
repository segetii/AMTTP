"""
AMTTP zkNAF Demo Service
========================
Minimal Python-based zkNAF demo service for testing ZK proof flows.
This provides demo endpoints without actual ZK circuit execution.

Endpoints:
- GET  /zknaf/health - Health check
- GET  /zknaf/info - Service info
- POST /zknaf/demo/generate-all - Generate all demo proofs
- GET  /zknaf/demo/compliance/{address} - Check compliance status
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import Optional
import hashlib
import json
import uvicorn
import os

app = FastAPI(
    title="AMTTP zkNAF Demo Service",
    description="Zero-Knowledge Non-Disclosing Anti-Fraud - Demo Mode",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Demo data store
demo_proofs = {}
kyc_users = {}  # userId -> KYC record
user_wallets = {}  # userId -> list of wallet addresses
wallet_to_user = {}  # wallet address -> userId
transaction_log = []  # Transaction history

sanctions_list = {
    "0x8576acc5c05d6ce88f4e49bf65bdf0c62f91353c": {
        "list_type": "OFAC",
        "reason": "Tornado Cash",
        "added_at": "2022-08-08"
    }
}

# Models
class GenerateProofsRequest(BaseModel):
    address: str

class KYCRequest(BaseModel):
    userId: str
    firstName: Optional[str] = "Demo"
    lastName: Optional[str] = "User"
    email: Optional[str] = None

class LinkWalletRequest(BaseModel):
    userId: str
    walletAddress: str
    signature: Optional[str] = None  # Skip in demo mode

class TransactionRequest(BaseModel):
    fromAddress: str
    toAddress: str
    amount: str
    tokenSymbol: Optional[str] = "USDC"

class ProofResponse(BaseModel):
    id: str
    proofType: str
    proofHash: str
    publicSignals: list
    createdAt: str
    expiresAt: str
    isValid: bool

class ComplianceStatus(BaseModel):
    sanctionsCleared: bool
    riskLevel: str
    riskScore: int
    kycVerified: bool
    fullyCompliant: bool

# Helpers
def compute_hash(*args) -> str:
    """Compute keccak-like hash for demo"""
    data = "|".join(str(a) for a in args)
    return "0x" + hashlib.sha256(data.encode()).hexdigest()

def is_sanctioned(address: str) -> bool:
    return address.lower() in sanctions_list

# Routes
@app.get("/zknaf/health")
async def health():
    return {
        "status": "healthy",
        "service": "AMTTP zkNAF Demo",
        "version": "1.0.0",
        "demoMode": True,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

@app.get("/zknaf/info")
async def info():
    return {
        "service": "AMTTP zkNAF - Zero-Knowledge Non-Disclosing Anti-Fraud",
        "version": "1.0.0",
        "demoMode": True,
        "proofTypes": ["sanctions", "risk-low", "risk-medium", "kyc"],
        "fcaCompliant": True,
        "endpoints": {
            "KYC (Sumsub)": {
                "POST /zknaf/kyc/create": "Create KYC record (auto-approved in demo)",
                "GET /zknaf/kyc/status/{userId}": "Get KYC status and linked wallets"
            },
            "Wallet Linking": {
                "POST /zknaf/wallet/link": "Link wallet address to KYC-verified user",
                "GET /zknaf/wallet/info/{address}": "Get KYC info for wallet"
            },
            "ZK Proofs": {
                "POST /zknaf/demo/generate-all": "Generate all proofs for address",
                "GET /zknaf/demo/compliance/{address}": "Check compliance status",
                "GET /zknaf/proofs/{address}": "Get stored proofs for address"
            },
            "Transaction": {
                "POST /zknaf/transaction/verify": "Verify transaction compliance"
            },
            "Sanctions": {
                "GET /zknaf/sanctions/check/{address}": "Check if address is sanctioned"
            }
        }
    }

@app.post("/zknaf/demo/generate-all")
async def generate_all_proofs(request: GenerateProofsRequest):
    address = request.address
    
    if not address or not address.startswith("0x"):
        raise HTTPException(status_code=400, detail="Invalid address format")
    
    # Check sanctions
    if is_sanctioned(address):
        raise HTTPException(
            status_code=400, 
            detail=f"SANCTIONS_CHECK_FAILED: Address {address} is on sanctions list"
        )
    
    now = datetime.utcnow()
    expires = now + timedelta(hours=24)
    timestamp = int(now.timestamp())
    
    proofs = {
        "sanctions": {
            "id": f"demo-sanctions-{timestamp}",
            "proofType": "sanctions",
            "proofHash": compute_hash(address, "sanctions", timestamp),
            "publicSignals": [compute_hash("sanctions-list-root"), str(timestamp)],
            "createdAt": now.isoformat() + "Z",
            "expiresAt": expires.isoformat() + "Z",
            "isValid": True
        },
        "risk": {
            "id": f"demo-risk-{timestamp}",
            "proofType": "risk-low",
            "proofHash": compute_hash(address, "risk-low", timestamp),
            "publicSignals": ["0", "39", str(timestamp)],
            "createdAt": now.isoformat() + "Z",
            "expiresAt": expires.isoformat() + "Z",
            "isValid": True
        },
        "kyc": {
            "id": f"demo-kyc-{timestamp}",
            "proofType": "kyc",
            "proofHash": compute_hash(address, "kyc", timestamp),
            "publicSignals": [compute_hash(address), str(timestamp)],
            "createdAt": now.isoformat() + "Z",
            "expiresAt": expires.isoformat() + "Z",
            "isValid": True
        }
    }
    
    # Store for later lookup
    demo_proofs[address.lower()] = proofs
    
    return {
        "success": True,
        "demoMode": True,
        "address": address,
        "proofs": proofs,
        "compliance": {
            "sanctionsCleared": True,
            "riskLevel": "LOW",
            "kycVerified": True,
            "fullyCompliant": True
        }
    }

@app.get("/zknaf/demo/compliance/{address}")
async def check_compliance(address: str):
    sanctioned = is_sanctioned(address)
    
    # Check if proofs were generated
    has_proofs = address.lower() in demo_proofs
    
    return {
        "address": address,
        "demoMode": True,
        "compliance": {
            "sanctionsCleared": not sanctioned,
            "riskLevel": "LOW",
            "riskScore": 15,  # Demo: always low risk
            "kycVerified": True,  # Demo: always verified
            "fullyCompliant": not sanctioned
        },
        "proofStatus": {
            "hasSanctionsProof": has_proofs,
            "hasRiskProof": has_proofs,
            "hasKYCProof": has_proofs
        },
        "message": (
            "Address is on sanctions list - transfers blocked" if sanctioned
            else "Address is compliant - transfers allowed"
        )
    }

@app.get("/zknaf/sanctions/check/{address}")
async def check_sanctions(address: str):
    sanctioned = is_sanctioned(address)
    
    return {
        "address": address,
        "isSanctioned": sanctioned,
        "sanctionsListRoot": compute_hash("sanctions-list-root"),
        "checkedAt": datetime.utcnow().isoformat() + "Z",
        "details": sanctions_list.get(address.lower()) if sanctioned else None
    }

@app.get("/zknaf/proofs/{address}")
async def get_proofs(address: str):
    proofs = demo_proofs.get(address.lower(), {})
    
    return {
        "address": address,
        "proofs": list(proofs.values()) if proofs else [],
        "hasProofs": bool(proofs)
    }

# ============================================
# SUMSUB KYC INTEGRATION (Demo Mode)
# ============================================

@app.post("/zknaf/kyc/create")
async def create_kyc(request: KYCRequest):
    """Simulate Sumsub KYC creation - Demo Mode"""
    user_id = request.userId
    now = datetime.utcnow()
    
    kyc_record = {
        "userId": user_id,
        "applicantId": f"sumsub-demo-{user_id}-{int(now.timestamp())}",
        "provider": "sumsub",
        "level": "KYC_BASIC",
        "status": "approved",  # Auto-approve in demo
        "firstName": request.firstName,
        "lastName": request.lastName,
        "email": request.email or f"{user_id}@demo.amttp.io",
        "kycHash": compute_hash(user_id, "sumsub", "KYC_BASIC", "approved"),
        "createdAt": now.isoformat() + "Z",
        "approvedAt": now.isoformat() + "Z",
        "demoMode": True
    }
    
    kyc_users[user_id] = kyc_record
    user_wallets[user_id] = []  # Initialize empty wallet list
    
    return {
        "success": True,
        "demoMode": True,
        "message": "KYC auto-approved in demo mode",
        "kyc": kyc_record
    }

@app.get("/zknaf/kyc/status/{userId}")
async def get_kyc_status(userId: str):
    """Get KYC status for user"""
    if userId not in kyc_users:
        raise HTTPException(status_code=404, detail=f"User {userId} not found - create KYC first")
    
    return {
        "demoMode": True,
        "kyc": kyc_users[userId],
        "linkedWallets": user_wallets.get(userId, [])
    }

@app.post("/zknaf/wallet/link")
async def link_wallet(request: LinkWalletRequest):
    """Link wallet address to KYC-verified user"""
    user_id = request.userId
    wallet = request.walletAddress.lower()
    
    if user_id not in kyc_users:
        raise HTTPException(
            status_code=400, 
            detail=f"User {user_id} not found - complete KYC first"
        )
    
    if kyc_users[user_id]["status"] != "approved":
        raise HTTPException(
            status_code=400,
            detail="KYC not approved - cannot link wallet"
        )
    
    # Check sanctions
    if is_sanctioned(wallet):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot link sanctioned address: {wallet}"
        )
    
    # Link wallet
    if wallet not in user_wallets[user_id]:
        user_wallets[user_id].append(wallet)
    wallet_to_user[wallet] = user_id
    
    return {
        "success": True,
        "demoMode": True,
        "userId": user_id,
        "walletAddress": wallet,
        "linkedWallets": user_wallets[user_id],
        "message": "Wallet linked to KYC-verified user"
    }

@app.get("/zknaf/wallet/info/{address}")
async def get_wallet_info(address: str):
    """Get KYC info for wallet address"""
    wallet = address.lower()
    
    if wallet not in wallet_to_user:
        return {
            "address": address,
            "linked": False,
            "kycVerified": False,
            "message": "Wallet not linked to any KYC-verified user"
        }
    
    user_id = wallet_to_user[wallet]
    kyc = kyc_users.get(user_id, {})
    
    return {
        "address": address,
        "linked": True,
        "userId": user_id,
        "kycVerified": kyc.get("status") == "approved",
        "kycLevel": kyc.get("level"),
        "kycHash": kyc.get("kycHash"),
        "demoMode": True
    }

# ============================================
# TRANSACTION VERIFICATION
# ============================================

@app.post("/zknaf/transaction/verify")
async def verify_transaction(request: TransactionRequest):
    """Verify transaction compliance with zkNAF proofs"""
    from_addr = request.fromAddress.lower()
    to_addr = request.toAddress.lower()
    now = datetime.utcnow()
    
    errors = []
    warnings = []
    
    # Check 1: Sender sanctions
    if is_sanctioned(from_addr):
        errors.append({
            "code": "SENDER_SANCTIONED",
            "message": f"Sender {from_addr} is on OFAC sanctions list"
        })
    
    # Check 2: Receiver sanctions
    if is_sanctioned(to_addr):
        errors.append({
            "code": "RECEIVER_SANCTIONED", 
            "message": f"Receiver {to_addr} is on OFAC sanctions list"
        })
    
    # Check 3: Sender KYC
    sender_kyc = wallet_to_user.get(from_addr)
    if not sender_kyc:
        warnings.append({
            "code": "SENDER_NO_KYC",
            "message": "Sender wallet not linked to KYC-verified user"
        })
    
    # Check 4: Sender has valid proofs
    sender_proofs = demo_proofs.get(from_addr, {})
    if not sender_proofs:
        warnings.append({
            "code": "SENDER_NO_PROOFS",
            "message": "Sender has no zkNAF proofs - generate proofs first"
        })
    
    # Determine compliance
    is_compliant = len(errors) == 0
    risk_level = "LOW" if is_compliant and len(warnings) == 0 else "MEDIUM" if is_compliant else "BLOCKED"
    
    # Generate transaction proof (if compliant)
    tx_proof = None
    tx_id = f"tx-{int(now.timestamp())}"
    if is_compliant:
        tx_proof = {
            "transactionId": tx_id,
            "proofHash": compute_hash(from_addr, to_addr, request.amount, now.timestamp()),
            "senderProofRef": sender_proofs.get("sanctions", {}).get("proofHash") if sender_proofs else None,
            "verifiedAt": now.isoformat() + "Z",
            "expiresAt": (now + timedelta(minutes=5)).isoformat() + "Z"
        }
    
    # Log transaction to history
    tx_record = {
        "id": tx_id,
        "timestamp": now.isoformat() + "Z",
        "from": request.fromAddress,
        "to": request.toAddress,
        "amount": request.amount,
        "token": request.tokenSymbol,
        "status": "APPROVED" if is_compliant else "BLOCKED",
        "riskLevel": risk_level,
        "senderKycVerified": sender_kyc is not None,
        "senderKycUser": sender_kyc if sender_kyc else None,
        "errors": errors,
        "warnings": warnings,
        "proofHash": tx_proof["proofHash"] if tx_proof else None
    }
    transaction_log.append(tx_record)
    
    # Print to console for visibility
    status_emoji = "✅" if is_compliant else "🚫"
    print(f"{status_emoji} TX {tx_id}: {request.fromAddress[:10]}... -> {request.toAddress[:10]}... | {request.amount} {request.tokenSymbol} | {risk_level}")
    
    return {
        "success": is_compliant,
        "demoMode": True,
        "transaction": {
            "from": request.fromAddress,
            "to": request.toAddress,
            "amount": request.amount,
            "token": request.tokenSymbol
        },
        "compliance": {
            "isCompliant": is_compliant,
            "riskLevel": risk_level,
            "senderKycVerified": sender_kyc is not None,
            "senderHasProofs": bool(sender_proofs),
            "receiverSanctionsCleared": not is_sanctioned(to_addr)
        },
        "errors": errors,
        "warnings": warnings,
        "proof": tx_proof,
        "message": (
            "Transaction APPROVED - all compliance checks passed" if is_compliant and len(warnings) == 0
            else "Transaction APPROVED with warnings" if is_compliant
            else "Transaction BLOCKED - compliance check failed"
        )
    }

# ============================================
# TRANSACTION HISTORY / AUDIT LOG
# ============================================

@app.get("/zknaf/transactions")
async def get_all_transactions(limit: int = 50):
    """Get all transaction history (most recent first)"""
    return {
        "demoMode": True,
        "totalTransactions": len(transaction_log),
        "showing": min(limit, len(transaction_log)),
        "transactions": list(reversed(transaction_log[-limit:]))
    }

@app.get("/zknaf/transactions/approved")
async def get_approved_transactions(limit: int = 50):
    """Get approved transactions only"""
    approved = [tx for tx in transaction_log if tx["status"] == "APPROVED"]
    return {
        "demoMode": True,
        "totalApproved": len(approved),
        "showing": min(limit, len(approved)),
        "transactions": list(reversed(approved[-limit:]))
    }

@app.get("/zknaf/transactions/blocked")
async def get_blocked_transactions(limit: int = 50):
    """Get blocked transactions only"""
    blocked = [tx for tx in transaction_log if tx["status"] == "BLOCKED"]
    return {
        "demoMode": True,
        "totalBlocked": len(blocked),
        "showing": min(limit, len(blocked)),
        "transactions": list(reversed(blocked[-limit:]))
    }

@app.get("/zknaf/transactions/by-address/{address}")
async def get_transactions_by_address(address: str):
    """Get all transactions involving an address (as sender or receiver)"""
    addr = address.lower()
    matching = [tx for tx in transaction_log if tx["from"].lower() == addr or tx["to"].lower() == addr]
    return {
        "demoMode": True,
        "address": address,
        "asSender": len([tx for tx in matching if tx["from"].lower() == addr]),
        "asReceiver": len([tx for tx in matching if tx["to"].lower() == addr]),
        "totalTransactions": len(matching),
        "transactions": list(reversed(matching))
    }

@app.get("/zknaf/transactions/{tx_id}")
async def get_transaction_by_id(tx_id: str):
    """Get specific transaction by ID"""
    for tx in transaction_log:
        if tx["id"] == tx_id:
            return {"demoMode": True, "transaction": tx}
    raise HTTPException(status_code=404, detail=f"Transaction {tx_id} not found")

@app.get("/zknaf/audit/summary")
async def get_audit_summary():
    """Get transaction audit summary"""
    approved = [tx for tx in transaction_log if tx["status"] == "APPROVED"]
    blocked = [tx for tx in transaction_log if tx["status"] == "BLOCKED"]
    
    return {
        "demoMode": True,
        "summary": {
            "totalTransactions": len(transaction_log),
            "approved": len(approved),
            "blocked": len(blocked),
            "approvalRate": f"{(len(approved)/len(transaction_log)*100):.1f}%" if transaction_log else "N/A",
            "uniqueSenders": len(set(tx["from"].lower() for tx in transaction_log)),
            "uniqueReceivers": len(set(tx["to"].lower() for tx in transaction_log)),
            "kycVerifiedTransactions": len([tx for tx in transaction_log if tx["senderKycVerified"]]),
            "blockedReasons": {}
        },
        "recentTransactions": list(reversed(transaction_log[-5:])),
        "kycUsers": len(kyc_users),
        "linkedWallets": len(wallet_to_user)
    }

if __name__ == "__main__":
    port = int(os.environ.get("ZKNAF_PORT", 8008))
    print(f"\n🔐 AMTTP zkNAF Demo Service starting on port {port}")
    print(f"   Demo Mode: ON - No actual ZK circuits")
    print(f"   Health: http://localhost:{port}/zknaf/health")
    print(f"   Info: http://localhost:{port}/zknaf/info\n")
    
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
