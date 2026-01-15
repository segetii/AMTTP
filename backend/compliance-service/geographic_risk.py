"""
AMTTP Geographic Risk Scoring Service
FATF grey/black list integration, high-risk jurisdictions, IP geolocation

Features:
- FATF Grey List (increased monitoring jurisdictions)
- FATF Black List (high-risk third countries)
- EU High Risk Third Countries
- Country risk scoring
- IP geolocation cross-check
- Jurisdiction-based transaction rules
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import ipaddress

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

# ═══════════════════════════════════════════════════════════════════════════════
# FATF LISTS (Updated January 2026)
# ═══════════════════════════════════════════════════════════════════════════════

# FATF Black List - High-Risk Jurisdictions Subject to a Call for Action
# Countries with significant strategic deficiencies
FATF_BLACK_LIST = {
    "KP": {"name": "North Korea (DPRK)", "since": "2011-02", "reason": "Proliferation financing, AML failures"},
    "IR": {"name": "Iran", "since": "2020-02", "reason": "Terrorism financing, AML deficiencies"},
    "MM": {"name": "Myanmar", "since": "2022-10", "reason": "Insufficient AML/CFT framework"},
}

# FATF Grey List - Jurisdictions Under Increased Monitoring
# Countries actively working with FATF to address deficiencies
FATF_GREY_LIST = {
    "BG": {"name": "Bulgaria", "since": "2023-10", "reason": "AML framework deficiencies"},
    "BF": {"name": "Burkina Faso", "since": "2021-02", "reason": "Terrorism financing risks"},
    "CM": {"name": "Cameroon", "since": "2023-06", "reason": "AML/CFT deficiencies"},
    "CD": {"name": "DR Congo", "since": "2022-10", "reason": "AML/CFT weaknesses"},
    "HR": {"name": "Croatia", "since": "2024-06", "reason": "Beneficial ownership transparency"},
    "HT": {"name": "Haiti", "since": "2020-10", "reason": "AML/CFT deficiencies"},
    "KE": {"name": "Kenya", "since": "2024-02", "reason": "Terrorism financing risks"},
    "ML": {"name": "Mali", "since": "2021-10", "reason": "Terrorism financing risks"},
    "MZ": {"name": "Mozambique", "since": "2022-10", "reason": "Terrorism financing risks"},
    "NG": {"name": "Nigeria", "since": "2023-02", "reason": "Terrorism financing, AML deficiencies"},
    "PH": {"name": "Philippines", "since": "2021-06", "reason": "AML/CFT effectiveness"},
    "SN": {"name": "Senegal", "since": "2021-02", "reason": "Terrorism financing risks"},
    "ZA": {"name": "South Africa", "since": "2023-02", "reason": "Terrorism financing, beneficial ownership"},
    "SS": {"name": "South Sudan", "since": "2021-06", "reason": "AML/CFT framework gaps"},
    "SY": {"name": "Syria", "since": "2010-02", "reason": "Terrorism financing, sanctions"},
    "TZ": {"name": "Tanzania", "since": "2022-10", "reason": "AML/CFT deficiencies"},
    "VE": {"name": "Venezuela", "since": "2024-02", "reason": "Corruption, AML failures"},
    "VN": {"name": "Vietnam", "since": "2023-06", "reason": "AML/CFT effectiveness"},
    "YE": {"name": "Yemen", "since": "2020-02", "reason": "Terrorism financing risks"},
}

# EU High Risk Third Countries (Commission Delegated Regulation)
EU_HIGH_RISK_THIRD_COUNTRIES = {
    "AF": {"name": "Afghanistan", "since": "2016", "reason": "Terrorism financing"},
    "BS": {"name": "Bahamas", "since": "2018", "reason": "AML deficiencies"},
    "BB": {"name": "Barbados", "since": "2020", "reason": "AML deficiencies"},
    "BW": {"name": "Botswana", "since": "2018", "reason": "AML deficiencies"},
    "KH": {"name": "Cambodia", "since": "2019", "reason": "AML deficiencies"},
    "GH": {"name": "Ghana", "since": "2020", "reason": "AML deficiencies"},
    "JM": {"name": "Jamaica", "since": "2020", "reason": "AML deficiencies"},
    "MU": {"name": "Mauritius", "since": "2020", "reason": "AML deficiencies"},
    "NI": {"name": "Nicaragua", "since": "2020", "reason": "AML deficiencies"},
    "PK": {"name": "Pakistan", "since": "2018", "reason": "Terrorism financing"},
    "PA": {"name": "Panama", "since": "2020", "reason": "AML deficiencies"},
    "TT": {"name": "Trinidad and Tobago", "since": "2018", "reason": "AML deficiencies"},
    "UG": {"name": "Uganda", "since": "2023", "reason": "AML deficiencies"},
    "ZW": {"name": "Zimbabwe", "since": "2020", "reason": "AML deficiencies"},
}

# UK High Risk Countries (MLR 2017 Schedule 3ZA)
UK_HIGH_RISK_COUNTRIES = {
    **FATF_BLACK_LIST,
    **{k: v for k, v in EU_HIGH_RISK_THIRD_COUNTRIES.items()},
}

# Tax Haven / Secrecy Jurisdictions (for enhanced monitoring)
TAX_HAVENS = {
    "VG": {"name": "British Virgin Islands", "risk": "secrecy"},
    "KY": {"name": "Cayman Islands", "risk": "secrecy"},
    "BM": {"name": "Bermuda", "risk": "secrecy"},
    "JE": {"name": "Jersey", "risk": "secrecy"},
    "GG": {"name": "Guernsey", "risk": "secrecy"},
    "IM": {"name": "Isle of Man", "risk": "secrecy"},
    "LI": {"name": "Liechtenstein", "risk": "secrecy"},
    "MC": {"name": "Monaco", "risk": "secrecy"},
    "SC": {"name": "Seychelles", "risk": "secrecy"},
    "MV": {"name": "Maldives", "risk": "secrecy"},
    "WS": {"name": "Samoa", "risk": "secrecy"},
    "VU": {"name": "Vanuatu", "risk": "secrecy"},
}

# ═══════════════════════════════════════════════════════════════════════════════
# COUNTRY RISK SCORING
# ═══════════════════════════════════════════════════════════════════════════════

class RiskLevel(str, Enum):
    PROHIBITED = "PROHIBITED"       # Transactions blocked
    VERY_HIGH = "VERY_HIGH"        # 80-100 score, requires SAR
    HIGH = "HIGH"                  # 60-79 score, enhanced monitoring
    MEDIUM = "MEDIUM"              # 40-59 score, standard monitoring
    LOW = "LOW"                    # 20-39 score, minimal monitoring
    MINIMAL = "MINIMAL"            # 0-19 score, no additional monitoring

def calculate_country_risk_score(country_code: str) -> Tuple[int, RiskLevel, List[str]]:
    """
    Calculate risk score for a country (0-100)
    Returns: (score, risk_level, risk_factors)
    """
    country_code = country_code.upper()
    score = 0
    factors = []
    
    # FATF Black List: Prohibited
    if country_code in FATF_BLACK_LIST:
        return 100, RiskLevel.PROHIBITED, [f"FATF Black List: {FATF_BLACK_LIST[country_code]['reason']}"]
    
    # FATF Grey List: +40 points
    if country_code in FATF_GREY_LIST:
        score += 40
        factors.append(f"FATF Grey List: {FATF_GREY_LIST[country_code]['reason']}")
    
    # EU High Risk: +30 points
    if country_code in EU_HIGH_RISK_THIRD_COUNTRIES:
        score += 30
        factors.append(f"EU High Risk Third Country: {EU_HIGH_RISK_THIRD_COUNTRIES[country_code]['reason']}")
    
    # UK High Risk (additional): +20 points
    if country_code in UK_HIGH_RISK_COUNTRIES and country_code not in EU_HIGH_RISK_THIRD_COUNTRIES:
        score += 20
        factors.append(f"UK MLR High Risk Country")
    
    # Tax Haven: +15 points
    if country_code in TAX_HAVENS:
        score += 15
        factors.append(f"Secrecy Jurisdiction: {TAX_HAVENS[country_code]['name']}")
    
    # Determine risk level
    if score >= 80:
        level = RiskLevel.VERY_HIGH
    elif score >= 60:
        level = RiskLevel.HIGH
    elif score >= 40:
        level = RiskLevel.MEDIUM
    elif score >= 20:
        level = RiskLevel.LOW
    else:
        level = RiskLevel.MINIMAL
    
    return score, level, factors

# ═══════════════════════════════════════════════════════════════════════════════
# IP GEOLOCATION (Using ip-api.com - free tier)
# ═══════════════════════════════════════════════════════════════════════════════

import aiohttp

async def geolocate_ip(ip_address: str) -> Optional[Dict[str, Any]]:
    """
    Geolocate an IP address
    Returns country info or None if failed
    """
    try:
        # Validate IP
        ipaddress.ip_address(ip_address)
    except ValueError:
        return None
    
    # Skip private IPs
    if ipaddress.ip_address(ip_address).is_private:
        return {"country_code": "PRIVATE", "country": "Private Network", "is_private": True}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"http://ip-api.com/json/{ip_address}?fields=status,country,countryCode,region,city,isp,org,as,proxy,hosting",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "success":
                        return {
                            "country_code": data.get("countryCode"),
                            "country": data.get("country"),
                            "region": data.get("region"),
                            "city": data.get("city"),
                            "isp": data.get("isp"),
                            "org": data.get("org"),
                            "as": data.get("as"),
                            "is_proxy": data.get("proxy", False),
                            "is_hosting": data.get("hosting", False),
                            "is_private": False
                        }
    except Exception as e:
        print(f"IP geolocation error: {e}")
    
    return None

# ═══════════════════════════════════════════════════════════════════════════════
# API MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class CountryRiskRequest(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2, description="ISO 3166-1 alpha-2 country code")

class CountryRiskResponse(BaseModel):
    country_code: str
    risk_score: int
    risk_level: str
    risk_factors: List[str]
    is_fatf_black_list: bool
    is_fatf_grey_list: bool
    is_eu_high_risk: bool
    is_tax_haven: bool
    transaction_policy: str

class IPRiskRequest(BaseModel):
    ip_address: str

class TransactionGeoRiskRequest(BaseModel):
    originator_country: str
    beneficiary_country: str
    originator_ip: Optional[str] = None
    value_eth: Optional[float] = None

class TransactionGeoRiskResponse(BaseModel):
    combined_risk_score: int
    risk_level: str
    originator_risk: Dict[str, Any]
    beneficiary_risk: Dict[str, Any]
    ip_risk: Optional[Dict[str, Any]] = None
    cross_border: bool
    recommendations: List[str]

# ═══════════════════════════════════════════════════════════════════════════════
# FASTAPI APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("═" * 60)
    print("       AMTTP Geographic Risk Scoring Service")
    print("═" * 60)
    print(f"📋 FATF Black List countries: {len(FATF_BLACK_LIST)}")
    print(f"📋 FATF Grey List countries: {len(FATF_GREY_LIST)}")
    print(f"📋 EU High Risk countries: {len(EU_HIGH_RISK_THIRD_COUNTRIES)}")
    print(f"📋 Tax Haven jurisdictions: {len(TAX_HAVENS)}")
    print("═" * 60)
    
    yield
    
    print("👋 Geographic risk service shutting down")

app = FastAPI(
    title="AMTTP Geographic Risk Scoring Service",
    description="FATF grey/black list, high-risk jurisdictions, IP geolocation",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── ENDPOINTS ──────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "geographic-risk",
        "lists": {
            "fatf_black": len(FATF_BLACK_LIST),
            "fatf_grey": len(FATF_GREY_LIST),
            "eu_high_risk": len(EU_HIGH_RISK_THIRD_COUNTRIES),
            "tax_havens": len(TAX_HAVENS)
        }
    }

@app.post("/geo/country-risk", response_model=CountryRiskResponse)
async def get_country_risk(request: CountryRiskRequest):
    """
    Get risk score for a country
    """
    country_code = request.country_code.upper()
    score, level, factors = calculate_country_risk_score(country_code)
    
    # Determine transaction policy
    if level == RiskLevel.PROHIBITED:
        policy = "BLOCK - Transactions prohibited with this jurisdiction"
    elif level == RiskLevel.VERY_HIGH:
        policy = "ESCROW + SAR - Mandatory escrow and suspicious activity review"
    elif level == RiskLevel.HIGH:
        policy = "ENHANCED_MONITORING - Enhanced due diligence required"
    elif level == RiskLevel.MEDIUM:
        policy = "STANDARD_MONITORING - Standard compliance checks"
    else:
        policy = "NORMAL - Standard transaction processing"
    
    return CountryRiskResponse(
        country_code=country_code,
        risk_score=score,
        risk_level=level.value,
        risk_factors=factors,
        is_fatf_black_list=country_code in FATF_BLACK_LIST,
        is_fatf_grey_list=country_code in FATF_GREY_LIST,
        is_eu_high_risk=country_code in EU_HIGH_RISK_THIRD_COUNTRIES,
        is_tax_haven=country_code in TAX_HAVENS,
        transaction_policy=policy
    )

@app.post("/geo/ip-risk")
async def get_ip_risk(request: IPRiskRequest):
    """
    Get risk assessment for an IP address
    """
    geo_info = await geolocate_ip(request.ip_address)
    
    if not geo_info:
        return {
            "ip_address": request.ip_address,
            "geolocation": None,
            "risk_assessment": {
                "error": "Could not geolocate IP address"
            }
        }
    
    if geo_info.get("is_private"):
        return {
            "ip_address": request.ip_address,
            "geolocation": geo_info,
            "risk_assessment": {
                "risk_score": 0,
                "risk_level": "MINIMAL",
                "note": "Private network IP"
            }
        }
    
    # Get country risk
    country_code = geo_info.get("country_code", "")
    score, level, factors = calculate_country_risk_score(country_code)
    
    # Add IP-specific risk factors
    if geo_info.get("is_proxy"):
        score += 20
        factors.append("IP detected as proxy/VPN")
    
    if geo_info.get("is_hosting"):
        score += 10
        factors.append("IP belongs to hosting/datacenter")
    
    return {
        "ip_address": request.ip_address,
        "geolocation": geo_info,
        "risk_assessment": {
            "risk_score": min(100, score),
            "risk_level": level.value,
            "risk_factors": factors
        }
    }

@app.post("/geo/transaction-risk", response_model=TransactionGeoRiskResponse)
async def assess_transaction_geo_risk(request: TransactionGeoRiskRequest):
    """
    Assess geographic risk for a transaction
    """
    # Get country risks
    orig_score, orig_level, orig_factors = calculate_country_risk_score(request.originator_country)
    benef_score, benef_level, benef_factors = calculate_country_risk_score(request.beneficiary_country)
    
    # IP risk if provided
    ip_risk = None
    ip_score_add = 0
    if request.originator_ip:
        geo_info = await geolocate_ip(request.originator_ip)
        if geo_info and not geo_info.get("is_private"):
            ip_country = geo_info.get("country_code", "")
            
            # Check for country mismatch
            if ip_country and ip_country != request.originator_country:
                ip_score_add = 25
                ip_risk = {
                    "ip_country": ip_country,
                    "stated_country": request.originator_country,
                    "mismatch": True,
                    "additional_score": ip_score_add,
                    "factor": "IP geolocation does not match stated originator country"
                }
            else:
                ip_risk = {
                    "ip_country": ip_country,
                    "stated_country": request.originator_country,
                    "mismatch": False,
                    "additional_score": 0
                }
            
            # Check for proxy/VPN
            if geo_info.get("is_proxy"):
                ip_score_add += 15
                if ip_risk:
                    ip_risk["is_proxy"] = True
                    ip_risk["additional_score"] = ip_score_add
    
    # Calculate combined risk
    combined_score = max(orig_score, benef_score) + ip_score_add
    
    # Cross-border check
    cross_border = request.originator_country.upper() != request.beneficiary_country.upper()
    if cross_border:
        combined_score += 5  # Small addition for cross-border
    
    combined_score = min(100, combined_score)
    
    # Determine combined level
    if combined_score >= 100 or orig_level == RiskLevel.PROHIBITED or benef_level == RiskLevel.PROHIBITED:
        combined_level = RiskLevel.PROHIBITED
    elif combined_score >= 80:
        combined_level = RiskLevel.VERY_HIGH
    elif combined_score >= 60:
        combined_level = RiskLevel.HIGH
    elif combined_score >= 40:
        combined_level = RiskLevel.MEDIUM
    elif combined_score >= 20:
        combined_level = RiskLevel.LOW
    else:
        combined_level = RiskLevel.MINIMAL
    
    # Generate recommendations
    recommendations = []
    
    if combined_level == RiskLevel.PROHIBITED:
        recommendations.append("BLOCK: Transaction involves prohibited jurisdiction")
    elif combined_level == RiskLevel.VERY_HIGH:
        recommendations.append("ESCROW: Place funds in escrow pending compliance review")
        recommendations.append("SAR: File Suspicious Activity Report")
        recommendations.append("EDD: Conduct Enhanced Due Diligence on all parties")
    elif combined_level == RiskLevel.HIGH:
        recommendations.append("REVIEW: Manual compliance review required")
        recommendations.append("EDD: Enhanced Due Diligence recommended")
    elif combined_level == RiskLevel.MEDIUM:
        recommendations.append("MONITOR: Standard monitoring with elevated attention")
    
    if ip_risk and ip_risk.get("mismatch"):
        recommendations.append("VERIFY: Confirm originator location - IP/stated country mismatch")
    
    if cross_border and request.value_eth and request.value_eth >= 10:
        recommendations.append("TRAVEL_RULE: Ensure Travel Rule compliance for cross-border transaction")
    
    return TransactionGeoRiskResponse(
        combined_risk_score=combined_score,
        risk_level=combined_level.value,
        originator_risk={
            "country_code": request.originator_country.upper(),
            "risk_score": orig_score,
            "risk_level": orig_level.value,
            "factors": orig_factors
        },
        beneficiary_risk={
            "country_code": request.beneficiary_country.upper(),
            "risk_score": benef_score,
            "risk_level": benef_level.value,
            "factors": benef_factors
        },
        ip_risk=ip_risk,
        cross_border=cross_border,
        recommendations=recommendations
    )

@app.get("/geo/lists/fatf-black")
async def get_fatf_black_list():
    """Get FATF Black List countries"""
    return {
        "list_name": "FATF Black List - High-Risk Jurisdictions Subject to a Call for Action",
        "last_updated": "2024-10",
        "countries": [
            {"code": k, **v}
            for k, v in FATF_BLACK_LIST.items()
        ]
    }

@app.get("/geo/lists/fatf-grey")
async def get_fatf_grey_list():
    """Get FATF Grey List countries"""
    return {
        "list_name": "FATF Grey List - Jurisdictions Under Increased Monitoring",
        "last_updated": "2024-10",
        "countries": [
            {"code": k, **v}
            for k, v in FATF_GREY_LIST.items()
        ]
    }

@app.get("/geo/lists/eu-high-risk")
async def get_eu_high_risk_list():
    """Get EU High Risk Third Countries"""
    return {
        "list_name": "EU High Risk Third Countries",
        "countries": [
            {"code": k, **v}
            for k, v in EU_HIGH_RISK_THIRD_COUNTRIES.items()
        ]
    }

@app.get("/geo/lists/tax-havens")
async def get_tax_havens_list():
    """Get tax haven/secrecy jurisdictions"""
    return {
        "list_name": "Tax Haven / Secrecy Jurisdictions",
        "countries": [
            {"code": k, **v}
            for k, v in TAX_HAVENS.items()
        ]
    }

@app.get("/geo/country/{country_code}")
async def get_country_info(country_code: str):
    """Get all risk info for a specific country"""
    country_code = country_code.upper()
    score, level, factors = calculate_country_risk_score(country_code)
    
    return {
        "country_code": country_code,
        "risk_score": score,
        "risk_level": level.value,
        "risk_factors": factors,
        "lists": {
            "fatf_black": FATF_BLACK_LIST.get(country_code),
            "fatf_grey": FATF_GREY_LIST.get(country_code),
            "eu_high_risk": EU_HIGH_RISK_THIRD_COUNTRIES.get(country_code),
            "uk_high_risk": UK_HIGH_RISK_COUNTRIES.get(country_code),
            "tax_haven": TAX_HAVENS.get(country_code)
        }
    }

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.getenv("GEO_RISK_SERVICE_PORT", "8006"))
    print(f"🚀 Starting Geographic Risk Scoring Service on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
