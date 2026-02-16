"""
AMTTP Auth Gateway Service
===========================
Centralized authentication and RBAC enforcement for the unified platform.

- Issues JWT tokens on login (email/password or wallet connect)
- Validates sessions via /auth/validate (used by Nginx auth_request)
- Enforces role-based access to /app (Next.js) and /consumer (Flutter)
- Shares the same user database and password hashing as Flutter auth_service.dart

Ports: 8020 (internal only, not exposed publicly)
"""

import os
import json
import time
import hmac
import hashlib
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, Response, HTTPException, Cookie
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import jwt

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

JWT_SECRET = os.environ.get("JWT_SECRET", "amttp_jwt_secret_change_in_production_2026")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.environ.get("JWT_EXPIRY_HOURS", "24"))
COOKIE_NAME = "amttp_session"
HMAC_COOKIE_NAME = "amttp_xauth"  # Cross-app auth bridge cookie
# Must match the BRIDGE_KEY in frontend/frontend/src/lib/cross-app-auth-bridge.ts
BRIDGE_KEY = os.environ.get("BRIDGE_KEY", "amttp-dev-bridge-key-change-in-production-2026")
PORT = int(os.environ.get("AUTH_GATEWAY_PORT", "8020"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auth-gateway")

# ═══════════════════════════════════════════════════════════════════════════════
# RBAC ROLE DEFINITIONS (matches both Flutter and Next.js)
# ═══════════════════════════════════════════════════════════════════════════════

ROLES = {
    "R1_END_USER":              {"level": 1, "apps": ["consumer"],           "label": "End User"},
    "R2_END_USER_PEP":          {"level": 2, "apps": ["consumer"],           "label": "End User (PEP)"},
    "R3_INSTITUTION_OPS":       {"level": 3, "apps": ["consumer", "app"],    "label": "Institution Ops"},
    "R4_INSTITUTION_COMPLIANCE":{"level": 4, "apps": ["consumer", "app"],    "label": "Compliance Officer"},
    "R5_PLATFORM_ADMIN":        {"level": 5, "apps": ["consumer", "app"],    "label": "Platform Admin"},
    "R6_SUPER_ADMIN":           {"level": 6, "apps": ["consumer", "app"],    "label": "Super Admin"},
}

# ═══════════════════════════════════════════════════════════════════════════════
# USER DATABASE (demo users — same credentials as Flutter auth_service.dart)
# In production, replace with PostgreSQL/MongoDB
# ═══════════════════════════════════════════════════════════════════════════════

def _hash_password(password: str) -> str:
    """SHA-256 hash matching Flutter auth_service.dart"""
    salted = f"{password}amttp_salt_2026"
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()


USERS_DB: Dict[str, Dict[str, Any]] = {
    "user@amttp.io": {
        "id": "demo-r1-001",
        "email": "user@amttp.io",
        "display_name": "Alex Thompson",
        "password_hash": _hash_password("user123"),
        "role": "R1_END_USER",
        "wallet_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f44e3B",
    },
    "pep@amttp.io": {
        "id": "demo-r2-001",
        "email": "pep@amttp.io",
        "display_name": "Jordan Mitchell",
        "password_hash": _hash_password("pep123"),
        "role": "R2_END_USER_PEP",
        "wallet_address": "0x9876543210AbCdEf0123456789AbCdEf01234567",
    },
    "ops@amttp.io": {
        "id": "demo-r3-001",
        "email": "ops@amttp.io",
        "display_name": "Emma Wilson",
        "password_hash": _hash_password("ops123"),
        "role": "R3_INSTITUTION_OPS",
        "wallet_address": "0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B",
    },
    "compliance@amttp.io": {
        "id": "demo-r4-001",
        "email": "compliance@amttp.io",
        "display_name": "Michael Rodriguez",
        "password_hash": _hash_password("comply123"),
        "role": "R4_INSTITUTION_COMPLIANCE",
        "wallet_address": "0x8ba1f109551bD432803012645Ac136ddd64DBA72",
    },
    "admin@amttp.io": {
        "id": "demo-r5-001",
        "email": "admin@amttp.io",
        "display_name": "Sarah Chen",
        "password_hash": _hash_password("admin123"),
        "role": "R5_PLATFORM_ADMIN",
        "wallet_address": "0xDef1C0ded9bec7F1a1670819833240f027b25EfF",
    },
    "super@amttp.io": {
        "id": "demo-r6-001",
        "email": "super@amttp.io",
        "display_name": "James Park",
        "password_hash": _hash_password("super123"),
        "role": "R6_SUPER_ADMIN",
        "wallet_address": "0x1111111111111111111111111111111111111111",
    },
}

# Wallet address → email lookup
WALLET_LOOKUP = {u["wallet_address"].lower(): u["email"] for u in USERS_DB.values()}

# ═══════════════════════════════════════════════════════════════════════════════
# JWT HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def create_token(user: Dict[str, Any]) -> str:
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "role": user["role"],
        "display_name": user["display_name"],
        "wallet": user["wallet_address"],
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def create_hmac_cookie(user: Dict[str, Any]) -> str:
    """
    Create cross-app auth bridge cookie in the exact format expected by
    frontend/frontend/src/lib/cross-app-auth-bridge.ts:
      base64url(JSON payload) . base64url(HMAC-SHA256 signature)

    Payload: {sub, email, role, mode, name, iat, exp}
    """
    import base64 as b64

    now = int(time.time())
    role = user["role"]
    role_info = ROLES.get(role, ROLES["R1_END_USER"])
    # R1/R2 = FOCUS mode (consumer), R3+ = WAR_ROOM mode
    mode = "WAR_ROOM" if "app" in role_info["apps"] else "FOCUS"

    payload = {
        "sub": user["id"],
        "email": user["email"],
        "role": role,
        "mode": mode,
        "name": user["display_name"],
        "iat": now,
        "exp": now + (JWT_EXPIRY_HOURS * 3600),
    }

    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = b64.urlsafe_b64encode(payload_json.encode()).rstrip(b"=").decode()

    # HMAC-SHA256 of the base64url-encoded payload, using the bridge key
    sig_raw = hmac.new(BRIDGE_KEY.encode(), payload_b64.encode(), hashlib.sha256).digest()
    sig_b64 = b64.urlsafe_b64encode(sig_raw).rstrip(b"=").decode()

    return f"{payload_b64}.{sig_b64}"


# ═══════════════════════════════════════════════════════════════════════════════
# FASTAPI APP
# ═══════════════════════════════════════════════════════════════════════════════

app = FastAPI(title="AMTTP Auth Gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response Models ────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    wallet_address: Optional[str] = None

class LoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    user: Optional[Dict[str, Any]] = None
    redirect: Optional[str] = None
    error: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/auth/health")
async def health():
    return {"status": "healthy", "service": "auth-gateway", "users": len(USERS_DB)}


@app.post("/auth/login")
async def login(req: LoginRequest, response: Response):
    """
    Authenticate user by email/password OR wallet address.
    Sets session cookie + HMAC cross-app cookie.
    Returns JWT token + user info + redirect URL based on role.
    """
    user = None

    # Email/password login
    if req.email and req.password:
        email_lower = req.email.lower().strip()
        db_user = USERS_DB.get(email_lower)
        if db_user and db_user["password_hash"] == _hash_password(req.password):
            user = db_user
        else:
            raise HTTPException(status_code=401, detail="Invalid email or password")

    # Wallet-based login
    elif req.wallet_address:
        wallet_lower = req.wallet_address.lower()
        email = WALLET_LOOKUP.get(wallet_lower)
        if email:
            user = USERS_DB[email]
        else:
            raise HTTPException(status_code=401, detail="Wallet not registered")

    else:
        raise HTTPException(status_code=400, detail="Provide email/password or wallet_address")

    # Create tokens
    token = create_token(user)
    hmac_cookie = create_hmac_cookie(user)

    # Determine redirect based on role
    role_info = ROLES.get(user["role"], ROLES["R1_END_USER"])
    redirect = "/app/" if "app" in role_info["apps"] else "/consumer/"

    # Set cookies (httponly for security)
    response.set_cookie(
        COOKIE_NAME, token,
        httponly=True, samesite="lax", path="/",
        max_age=JWT_EXPIRY_HOURS * 3600,
    )
    response.set_cookie(
        HMAC_COOKIE_NAME, hmac_cookie,
        httponly=False, samesite="lax", path="/",  # Readable by JS for cross-app bridge
        max_age=JWT_EXPIRY_HOURS * 3600,
    )

    logger.info(f"Login successful: {user['email']} ({user['role']}) -> {redirect}")

    return LoginResponse(
        success=True,
        token=token,
        user={
            "id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"],
            "role": user["role"],
            "role_label": role_info["label"],
            "wallet_address": user["wallet_address"],
            "allowed_apps": role_info["apps"],
        },
        redirect=redirect,
    )


@app.get("/auth/validate")
async def validate(request: Request):
    """
    Validate session — called by Nginx auth_request.
    Returns 200 if valid, 401 if not.
    Sets X-Auth-User, X-Auth-Role, X-Auth-Email headers for downstream services.
    """
    # Check cookie first
    token = request.cookies.get(COOKIE_NAME)

    # Fall back to Authorization header
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise HTTPException(status_code=401, detail="No session")

    claims = decode_token(token)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    # Check RBAC: which app is the user trying to access?
    # Nginx passes the original URI via X-Original-URI
    original_uri = request.headers.get("X-Original-URI", "/")
    role = claims.get("role", "R1_END_USER")
    role_info = ROLES.get(role, ROLES["R1_END_USER"])

    # Determine target app from URI
    target_app = "consumer"  # default
    if original_uri.startswith("/app") or original_uri.startswith("/_next") or original_uri.startswith("/war-room"):
        target_app = "app"

    # Enforce RBAC
    if target_app not in role_info["apps"]:
        raise HTTPException(
            status_code=403,
            detail=f"Role {role} cannot access {target_app}. Allowed: {role_info['apps']}"
        )

    # Return 200 with user info in headers (Nginx forwards these to upstream)
    resp = Response(status_code=200)
    resp.headers["X-Auth-User"] = claims["sub"]
    resp.headers["X-Auth-Role"] = role
    resp.headers["X-Auth-Email"] = claims.get("email", "")
    resp.headers["X-Auth-Display-Name"] = claims.get("display_name", "")
    return resp


@app.get("/auth/me")
async def me(request: Request):
    """Return current user info from session cookie."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    claims = decode_token(token)
    if not claims:
        raise HTTPException(status_code=401, detail="Session expired")

    role = claims.get("role", "R1_END_USER")
    role_info = ROLES.get(role, ROLES["R1_END_USER"])

    return {
        "id": claims["sub"],
        "email": claims.get("email"),
        "display_name": claims.get("display_name"),
        "role": role,
        "role_label": role_info["label"],
        "role_level": role_info["level"],
        "wallet_address": claims.get("wallet"),
        "allowed_apps": role_info["apps"],
        "token_expires": claims.get("exp"),
    }


@app.post("/auth/logout")
async def logout(response: Response):
    """Clear all auth cookies."""
    response.delete_cookie(COOKIE_NAME, path="/")
    response.delete_cookie(HMAC_COOKIE_NAME, path="/")
    return {"success": True, "message": "Logged out"}


@app.get("/auth/users")
async def list_users():
    """List available demo users (for login page display, no passwords)."""
    return [
        {
            "email": u["email"],
            "display_name": u["display_name"],
            "role": u["role"],
            "role_label": ROLES.get(u["role"], {}).get("label", u["role"]),
            "allowed_apps": ROLES.get(u["role"], {}).get("apps", []),
        }
        for u in USERS_DB.values()
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# STARTUP
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting Auth Gateway on port {PORT}")
    logger.info(f"Demo users: {list(USERS_DB.keys())}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
