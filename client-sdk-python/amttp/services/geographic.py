"""Geographic Risk Service — country & IP risk assessment."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from amttp.services.base import BaseService

# ── types ─────────────────────────────────────────────────────────────────────

GeoRiskLevel = Literal["PROHIBITED", "VERY_HIGH", "HIGH", "MEDIUM", "LOW", "MINIMAL"]
GeoTransactionPolicy = Literal["BLOCK", "REVIEW", "ESCROW", "ALLOW", "ENHANCED_MONITORING"]


class CountryRiskResponse(BaseModel):
    country_code: str = ""
    country_name: Optional[str] = None
    risk_score: float = 0
    risk_level: str = "LOW"
    risk_factors: List[str] = []
    is_fatf_black_list: bool = False
    is_fatf_grey_list: bool = False
    is_eu_high_risk: bool = False
    is_tax_haven: bool = False
    transaction_policy: str = "ALLOW"


class IPRiskResponse(BaseModel):
    ip_address: str = ""
    country_code: str = ""
    country_name: str = ""
    city: Optional[str] = None
    region: Optional[str] = None
    is_vpn: bool = False
    is_proxy: bool = False
    is_tor: bool = False
    is_datacenter: bool = False
    risk_score: float = 0
    risk_level: str = "LOW"
    risk_factors: List[str] = []


class TransactionGeoRiskRequest(BaseModel):
    originator_country: str
    beneficiary_country: str
    originator_ip: Optional[str] = None
    beneficiary_ip: Optional[str] = None
    value_usd: Optional[float] = None


class TransactionGeoRiskResponse(BaseModel):
    originator_country_risk: Optional[CountryRiskResponse] = None
    beneficiary_country_risk: Optional[CountryRiskResponse] = None
    originator_ip_risk: Optional[IPRiskResponse] = None
    beneficiary_ip_risk: Optional[IPRiskResponse] = None
    combined_risk_score: float = 0
    combined_risk_level: str = "LOW"
    transaction_policy: str = "ALLOW"
    requires_enhanced_due_diligence: bool = False
    requires_travel_rule: bool = False
    risk_factors: List[str] = []


class FATFListCountry(BaseModel):
    code: str = ""
    name: str = ""
    list_type: str = "grey"
    added_date: Optional[str] = None
    reason: Optional[str] = None


class CountryInfo(BaseModel):
    code: str = ""
    name: str = ""
    region: str = ""
    risk_score: float = 0
    risk_level: str = "LOW"
    fatf_status: Optional[str] = None
    eu_high_risk: bool = False
    tax_haven: bool = False
    currency_code: Optional[str] = None
    regulatory_framework: Optional[str] = None


# ── service ───────────────────────────────────────────────────────────────────


class GeographicRiskService(BaseService):
    """Geographic risk assessment."""

    async def get_country_risk(self, country_code: str) -> CountryRiskResponse:
        """Get risk assessment for a country."""
        resp = await self._http.post(
            "/geo/country-risk", json={"country_code": country_code.upper()}
        )
        resp.raise_for_status()
        data = CountryRiskResponse.model_validate(resp.json())
        self._events.emit("geo:risk_assessed", data.model_dump())
        return data

    async def get_ip_risk(self, ip_address: str) -> IPRiskResponse:
        """Get risk assessment for an IP address."""
        resp = await self._http.post("/geo/ip-risk", json={"ip_address": ip_address})
        resp.raise_for_status()
        return IPRiskResponse.model_validate(resp.json())

    async def get_transaction_risk(
        self, request: TransactionGeoRiskRequest
    ) -> TransactionGeoRiskResponse:
        """Get comprehensive geographic risk for a transaction."""
        resp = await self._http.post(
            "/geo/transaction-risk", json=request.model_dump(exclude_none=True)
        )
        resp.raise_for_status()
        return TransactionGeoRiskResponse.model_validate(resp.json())

    async def get_fatf_black_list(self) -> List[FATFListCountry]:
        """Get FATF Black List countries."""
        resp = await self._http.get("/geo/lists/fatf-black")
        resp.raise_for_status()
        return [FATFListCountry.model_validate(c) for c in resp.json().get("countries", [])]

    async def get_fatf_grey_list(self) -> List[FATFListCountry]:
        """Get FATF Grey List countries."""
        resp = await self._http.get("/geo/lists/fatf-grey")
        resp.raise_for_status()
        return [FATFListCountry.model_validate(c) for c in resp.json().get("countries", [])]

    async def get_eu_high_risk_list(self) -> List[FATFListCountry]:
        """Get EU High Risk Third Countries."""
        resp = await self._http.get("/geo/lists/eu-high-risk")
        resp.raise_for_status()
        return [FATFListCountry.model_validate(c) for c in resp.json().get("countries", [])]

    async def get_tax_havens(self) -> List[FATFListCountry]:
        """Get tax haven jurisdictions."""
        resp = await self._http.get("/geo/lists/tax-havens")
        resp.raise_for_status()
        return [FATFListCountry.model_validate(c) for c in resp.json().get("countries", [])]

    async def get_country_info(self, country_code: str) -> CountryInfo:
        """Get detailed country information."""
        resp = await self._http.get(f"/geo/country/{country_code.upper()}")
        resp.raise_for_status()
        return CountryInfo.model_validate(resp.json())

    async def is_high_risk_country(self, country_code: str) -> bool:
        """Check if a country is high risk."""
        risk = await self.get_country_risk(country_code)
        return risk.risk_level in ("PROHIBITED", "VERY_HIGH", "HIGH")

    async def is_prohibited_transaction(
        self, originator_country: str, beneficiary_country: str
    ) -> bool:
        """Check if transaction involves prohibited jurisdiction."""
        tx_risk = await self.get_transaction_risk(TransactionGeoRiskRequest(
            originator_country=originator_country,
            beneficiary_country=beneficiary_country,
        ))
        return tx_risk.transaction_policy == "BLOCK"

    async def health(self) -> Dict[str, Any]:
        """Check service health."""
        resp = await self._http.get("/health")
        resp.raise_for_status()
        return resp.json()
