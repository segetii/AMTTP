"""
scenarios.py — Historical supply chain disruption scenarios
============================================================
Each scenario defines a network topology and disruption events
calibrated to historical data.  Numbers are drawn from:
  - World Bank trade data, BTS freight statistics
  - SIA semiconductor industry reports
  - Bloomberg supply chain analysis
  - Academic literature (Ivanov 2017, Simchi-Levi 2015)
"""

from __future__ import annotations
import numpy as np
from supply_chain_engine import (
    SupplyNode, SupplyEdge, SupplyChainNetwork, Disruption
)


# ═════════════════════════════════════════════════════════════
# Scenario 1: COVID-19 Semiconductor Shortage (2020–2022)
# ═════════════════════════════════════════════════════════════

def covid_semiconductor() -> tuple[SupplyChainNetwork, list[Disruption], dict]:
    """TSMC concentration risk → automotive → electronics cascade.

    Key features:
      - TSMC holds ~54% global foundry market share → extreme δ_G (concentration)
      - Automotive JIT = near-zero inventory buffer → camouflage risk δ_C
      - Demand whiplash (COVID WFH electronics surge) → δ_A
      - Unprecedented pandemic + trade war combo → δ_T
    """
    nodes = [
        # Tier 0: Raw materials
        SupplyNode("SUMCO (Si wafers)",     tier=0, sector="semiconductor",
                   baseline=np.array([1.0, 1.0, 0.85, 0.85])),
        SupplyNode("Shin-Etsu (chemicals)", tier=0, sector="semiconductor",
                   baseline=np.array([1.0, 1.0, 0.80, 0.90])),

        # Tier 1: Foundries
        SupplyNode("TSMC",                  tier=1, sector="semiconductor",
                   baseline=np.array([0.9, 1.0, 0.92, 0.95])),
        SupplyNode("Samsung Foundry",       tier=1, sector="semiconductor",
                   baseline=np.array([0.9, 1.0, 0.85, 0.90])),
        SupplyNode("GlobalFoundries",       tier=1, sector="semiconductor",
                   baseline=np.array([0.8, 1.0, 0.75, 0.80])),

        # Tier 2: Chip packaging / design
        SupplyNode("ASE Group (packaging)", tier=2, sector="semiconductor",
                   baseline=np.array([0.8, 1.0, 0.80, 0.85])),
        SupplyNode("Qualcomm (fabless)",    tier=2, sector="semiconductor",
                   baseline=np.array([0.7, 1.0, 0.85, 0.90])),
        SupplyNode("NXP Semicond.",         tier=2, sector="semiconductor",
                   baseline=np.array([0.7, 1.0, 0.80, 0.85])),

        # Tier 3: OEMs
        SupplyNode("Toyota",               tier=3, sector="automotive",
                   baseline=np.array([0.3, 1.0, 0.90, 0.92])),  # JIT = low inventory
        SupplyNode("VW Group",             tier=3, sector="automotive",
                   baseline=np.array([0.3, 1.0, 0.88, 0.90])),
        SupplyNode("Apple",                tier=3, sector="electronics",
                   baseline=np.array([0.5, 1.0, 0.95, 0.98])),
        SupplyNode("Sony (PS5)",           tier=3, sector="electronics",
                   baseline=np.array([0.4, 1.0, 0.90, 0.88])),

        # Tier 4: Retail/Distribution
        SupplyNode("Auto dealers",         tier=4, sector="automotive",
                   baseline=np.array([0.6, 1.0, 0.75, 0.80])),
        SupplyNode("Electronics retail",   tier=4, sector="electronics",
                   baseline=np.array([0.7, 1.0, 0.80, 0.85])),
    ]

    edges = [
        # Raw → Foundry
        SupplyEdge(0, 2, weight=0.9),   # SUMCO → TSMC (dominant)
        SupplyEdge(0, 3, weight=0.5),   # SUMCO → Samsung
        SupplyEdge(1, 2, weight=0.8),   # Shin-Etsu → TSMC
        SupplyEdge(1, 4, weight=0.6),   # Shin-Etsu → GlobalFoundries

        # Foundry → Packaging/Fabless
        SupplyEdge(2, 5, weight=0.9),   # TSMC → ASE
        SupplyEdge(2, 6, weight=0.95),  # TSMC → Qualcomm (near-total dependency)
        SupplyEdge(2, 7, weight=0.7),   # TSMC → NXP
        SupplyEdge(3, 7, weight=0.3),   # Samsung → NXP (partial)
        SupplyEdge(4, 7, weight=0.2),   # GF → NXP (minor)

        # Chip → OEM
        SupplyEdge(7, 8,  weight=0.85), # NXP → Toyota (automotive chips)
        SupplyEdge(7, 9,  weight=0.80), # NXP → VW
        SupplyEdge(6, 10, weight=0.90), # Qualcomm → Apple
        SupplyEdge(5, 11, weight=0.85), # ASE → Sony

        # OEM → Retail
        SupplyEdge(8,  12, weight=0.7),
        SupplyEdge(9,  12, weight=0.7),
        SupplyEdge(10, 13, weight=0.8),
        SupplyEdge(11, 13, weight=0.7),
    ]

    disruptions = [
        # Phase 1: COVID lockdowns reduce foundry capacity (Q1 2020)
        Disruption("COVID lockdown", onset_step=40, duration=30,
                   affected_nodes=[2, 3, 4, 5],    # foundries + packaging
                   severity=0.4, disruption_type='capacity'),
        # Phase 2: WFH demand surge for electronics (Q2-Q3 2020)
        Disruption("WFH demand surge", onset_step=50, duration=60,
                   affected_nodes=[10, 11, 13],     # electronics OEM + retail
                   severity=0.6, disruption_type='demand'),
        # Phase 3: Auto demand recovery + chip shortage (Q4 2020 – Q2 2021)
        Disruption("Auto recovery + shortage", onset_step=80, duration=80,
                   affected_nodes=[8, 9, 12],       # automotive OEM + dealers
                   severity=0.7, disruption_type='capacity'),
    ]

    meta = {
        "name": "COVID-19 Semiconductor Shortage",
        "period": "2020-2022",
        "key_metric": "automotive production loss",
        "historical_impact": "$210B automotive revenue loss (AlixPartners est.)",
    }

    return SupplyChainNetwork(nodes, edges), disruptions, meta


# ═════════════════════════════════════════════════════════════
# Scenario 2: Suez Canal Blockage (March 2021)
# ═════════════════════════════════════════════════════════════

def suez_canal() -> tuple[SupplyChainNetwork, list[Disruption], dict]:
    """Ever Given grounding — logistics disruption cascading through trade.

    Key features:
      - Purely logistics disruption (lead time shock, not capacity)
      - 12% of global trade flows through Suez
      - Container rerouting via Cape of Good Hope (+10 days)
      - Rapid post-clearance congestion at destination ports
    """
    nodes = [
        # Tier 0: Asian manufacturers
        SupplyNode("China exports",        tier=0, sector="manufacturing",
                   baseline=np.array([1.0, 1.0, 0.90, 0.90])),
        SupplyNode("South Korea exports",  tier=0, sector="manufacturing",
                   baseline=np.array([1.0, 1.0, 0.88, 0.88])),

        # Tier 1: Shipping / logistics
        SupplyNode("Suez passage",         tier=1, sector="logistics",
                   baseline=np.array([1.0, 1.0, 0.95, 0.95])),
        SupplyNode("Cape route (alt)",     tier=1, sector="logistics",
                   baseline=np.array([0.8, 2.5, 0.50, 0.80])),  # higher lead time

        # Tier 2: European ports
        SupplyNode("Rotterdam",            tier=2, sector="logistics",
                   baseline=np.array([0.9, 1.0, 0.85, 0.90])),
        SupplyNode("Hamburg",              tier=2, sector="logistics",
                   baseline=np.array([0.9, 1.0, 0.82, 0.88])),
        SupplyNode("Felixstowe",           tier=2, sector="logistics",
                   baseline=np.array([0.8, 1.0, 0.78, 0.85])),

        # Tier 3: European manufacturers / retailers
        SupplyNode("EU auto assembly",     tier=3, sector="automotive",
                   baseline=np.array([0.5, 1.0, 0.90, 0.90])),
        SupplyNode("EU electronics dist",  tier=3, sector="electronics",
                   baseline=np.array([0.6, 1.0, 0.85, 0.88])),
        SupplyNode("EU FMCG retail",       tier=3, sector="retail",
                   baseline=np.array([0.7, 1.0, 0.80, 0.85])),
    ]

    edges = [
        # Asia → Suez
        SupplyEdge(0, 2, weight=0.85),
        SupplyEdge(1, 2, weight=0.80),
        # Asia → Cape (backup)
        SupplyEdge(0, 3, weight=0.15),
        SupplyEdge(1, 3, weight=0.20),
        # Suez → EU ports
        SupplyEdge(2, 4, weight=0.9),
        SupplyEdge(2, 5, weight=0.8),
        SupplyEdge(2, 6, weight=0.7),
        # Cape → EU ports (backup)
        SupplyEdge(3, 4, weight=0.3),
        SupplyEdge(3, 5, weight=0.2),
        SupplyEdge(3, 6, weight=0.3),
        # EU ports → end users
        SupplyEdge(4, 7, weight=0.8),
        SupplyEdge(5, 7, weight=0.6),
        SupplyEdge(4, 8, weight=0.7),
        SupplyEdge(6, 8, weight=0.5),
        SupplyEdge(4, 9, weight=0.6),
        SupplyEdge(5, 9, weight=0.5),
        SupplyEdge(6, 9, weight=0.4),
    ]

    disruptions = [
        # Suez blockage: 6 days, massive logistics disruption
        Disruption("Ever Given grounding", onset_step=60, duration=15,
                   affected_nodes=[2],      # Suez passage
                   severity=0.95, disruption_type='logistics'),
        # Port congestion aftermath (2-3 weeks)
        Disruption("Port congestion", onset_step=72, duration=40,
                   affected_nodes=[4, 5, 6],  # EU ports
                   severity=0.5, disruption_type='logistics'),
    ]

    meta = {
        "name": "Suez Canal Blockage (Ever Given)",
        "period": "March 2021",
        "key_metric": "$9.6B/day trade impact",
        "historical_impact": "6-day blockage, $54B total trade disruption",
    }

    return SupplyChainNetwork(nodes, edges), disruptions, meta


# ═════════════════════════════════════════════════════════════
# Scenario 3: Texas Winter Storm / ERCOT (February 2021)
# ═════════════════════════════════════════════════════════════

def texas_winter_storm() -> tuple[SupplyChainNetwork, list[Disruption], dict]:
    """Petrochemical cascade through industrial supply chains.

    Key features:
      - Power grid failure → petrochemical shutdown → plastics/rubber shortage
      - Cross-sector cascade: energy → chemicals → automotive → consumer goods
      - Financial stress on utilities → cascading credit issues
    """
    nodes = [
        # Tier 0: Energy / Power
        SupplyNode("ERCOT grid",          tier=0, sector="energy",
                   baseline=np.array([1.0, 1.0, 0.85, 0.90])),
        SupplyNode("Natural gas supply",  tier=0, sector="energy",
                   baseline=np.array([1.0, 1.0, 0.80, 0.88])),

        # Tier 1: Petrochemicals
        SupplyNode("Dow Chemical",        tier=1, sector="petrochemical",
                   baseline=np.array([0.9, 1.0, 0.88, 0.90])),
        SupplyNode("LyondellBasell",      tier=1, sector="petrochemical",
                   baseline=np.array([0.9, 1.0, 0.85, 0.88])),
        SupplyNode("ExxonMobil Chem.",    tier=1, sector="petrochemical",
                   baseline=np.array([0.9, 1.0, 0.87, 0.92])),

        # Tier 2: Plastics / Rubber / Specialty
        SupplyNode("Plastics producers",  tier=2, sector="plastics",
                   baseline=np.array([0.8, 1.0, 0.82, 0.85])),
        SupplyNode("Rubber producers",    tier=2, sector="rubber",
                   baseline=np.array([0.8, 1.0, 0.80, 0.83])),
        SupplyNode("Specialty chemicals", tier=2, sector="chemicals",
                   baseline=np.array([0.7, 1.0, 0.78, 0.85])),

        # Tier 3: End users
        SupplyNode("Auto manufacturers",  tier=3, sector="automotive",
                   baseline=np.array([0.4, 1.0, 0.90, 0.90])),
        SupplyNode("Consumer goods",      tier=3, sector="consumer",
                   baseline=np.array([0.6, 1.0, 0.85, 0.88])),
        SupplyNode("Construction",        tier=3, sector="construction",
                   baseline=np.array([0.5, 1.0, 0.80, 0.85])),
    ]

    edges = [
        # Energy → Petrochemicals
        SupplyEdge(0, 2, weight=0.9),
        SupplyEdge(0, 3, weight=0.85),
        SupplyEdge(0, 4, weight=0.8),
        SupplyEdge(1, 2, weight=0.85),
        SupplyEdge(1, 3, weight=0.9),
        SupplyEdge(1, 4, weight=0.75),

        # Petrochemicals → Derivatives
        SupplyEdge(2, 5, weight=0.8),
        SupplyEdge(3, 5, weight=0.7),
        SupplyEdge(3, 6, weight=0.8),
        SupplyEdge(4, 6, weight=0.6),
        SupplyEdge(2, 7, weight=0.7),
        SupplyEdge(4, 7, weight=0.8),

        # Derivatives → End users
        SupplyEdge(5, 8,  weight=0.75),
        SupplyEdge(6, 8,  weight=0.8),
        SupplyEdge(5, 9,  weight=0.6),
        SupplyEdge(7, 9,  weight=0.7),
        SupplyEdge(5, 10, weight=0.7),
        SupplyEdge(7, 10, weight=0.65),
    ]

    disruptions = [
        # Grid failure: near-total capacity loss
        Disruption("ERCOT grid failure", onset_step=50, duration=20,
                   affected_nodes=[0],
                   severity=0.9, disruption_type='capacity'),
        # Gas supply freeze
        Disruption("Gas supply freeze", onset_step=48, duration=25,
                   affected_nodes=[1],
                   severity=0.8, disruption_type='capacity'),
        # Financial stress on utilities
        Disruption("Utility financial stress", onset_step=55, duration=40,
                   affected_nodes=[0, 1],
                   severity=0.5, disruption_type='financial'),
    ]

    meta = {
        "name": "Texas Winter Storm (Uri) / ERCOT",
        "period": "February 2021",
        "key_metric": "petrochemical cascade depth",
        "historical_impact": "$195B total damage, weeks of chemical plant shutdowns",
    }

    return SupplyChainNetwork(nodes, edges), disruptions, meta


# ═════════════════════════════════════════════════════════════
# Scenario 4: Fukushima (2011)
# ═════════════════════════════════════════════════════════════

def fukushima() -> tuple[SupplyChainNetwork, list[Disruption], dict]:
    """Earthquake + tsunami → Renesas semiconductor failure → auto cascade.

    Key features:
      - Single-source dependency: Renesas held ~40% global automotive MCU market
      - Toyota lost production of 800K vehicles
      - Exposed extreme tier-2/3 concentration previously invisible to OEMs
    """
    nodes = [
        # Tier 0: Raw materials / Utilities
        SupplyNode("TEPCO (power)",        tier=0, sector="energy",
                   baseline=np.array([1.0, 1.0, 0.90, 0.88])),
        SupplyNode("Japanese suppliers",   tier=0, sector="components",
                   baseline=np.array([1.0, 1.0, 0.85, 0.85])),

        # Tier 1: Semiconductor
        SupplyNode("Renesas Naka fab",     tier=1, sector="semiconductor",
                   baseline=np.array([0.8, 1.0, 0.90, 0.85])),
        SupplyNode("Other MCU fabs",       tier=1, sector="semiconductor",
                   baseline=np.array([0.7, 1.0, 0.80, 0.82])),

        # Tier 2: Automotive electronics
        SupplyNode("Denso",                tier=2, sector="automotive",
                   baseline=np.array([0.6, 1.0, 0.88, 0.90])),
        SupplyNode("Continental AG",       tier=2, sector="automotive",
                   baseline=np.array([0.6, 1.0, 0.85, 0.88])),
        SupplyNode("Bosch",                tier=2, sector="automotive",
                   baseline=np.array([0.6, 1.0, 0.87, 0.90])),

        # Tier 3: OEMs
        SupplyNode("Toyota",              tier=3, sector="automotive",
                   baseline=np.array([0.3, 1.0, 0.92, 0.95])),
        SupplyNode("Honda",               tier=3, sector="automotive",
                   baseline=np.array([0.3, 1.0, 0.90, 0.92])),
        SupplyNode("Nissan",              tier=3, sector="automotive",
                   baseline=np.array([0.3, 1.0, 0.88, 0.90])),
        SupplyNode("GM (US impact)",      tier=3, sector="automotive",
                   baseline=np.array([0.4, 1.0, 0.85, 0.88])),
    ]

    edges = [
        # Power + suppliers → Renesas
        SupplyEdge(0, 2, weight=0.95),    # TEPCO → Renesas (critical)
        SupplyEdge(1, 2, weight=0.80),
        SupplyEdge(1, 3, weight=0.60),

        # Renesas → Tier-1 suppliers (near-monopoly for auto MCUs)
        SupplyEdge(2, 4, weight=0.90),    # Renesas → Denso
        SupplyEdge(2, 5, weight=0.70),    # Renesas → Continental
        SupplyEdge(2, 6, weight=0.65),    # Renesas → Bosch
        SupplyEdge(3, 5, weight=0.30),    # Other MCU → Continental
        SupplyEdge(3, 6, weight=0.35),    # Other MCU → Bosch

        # Tier-1 → OEMs
        SupplyEdge(4, 7,  weight=0.90),   # Denso → Toyota
        SupplyEdge(4, 8,  weight=0.70),   # Denso → Honda
        SupplyEdge(5, 9,  weight=0.75),   # Continental → Nissan
        SupplyEdge(5, 10, weight=0.60),   # Continental → GM
        SupplyEdge(6, 7,  weight=0.50),   # Bosch → Toyota
        SupplyEdge(6, 10, weight=0.65),   # Bosch → GM
    ]

    disruptions = [
        # Earthquake + tsunami: Renesas Naka fab destroyed
        Disruption("Earthquake: Renesas Naka", onset_step=40, duration=60,
                   affected_nodes=[2],      # Renesas fab
                   severity=0.95, disruption_type='capacity'),
        # Power disruption (TEPCO Fukushima)
        Disruption("TEPCO power failure", onset_step=38, duration=30,
                   affected_nodes=[0],
                   severity=0.7, disruption_type='capacity'),
        # Broader Japanese supply disruption
        Disruption("Japan supply disruption", onset_step=42, duration=40,
                   affected_nodes=[1, 3],
                   severity=0.5, disruption_type='capacity'),
    ]

    meta = {
        "name": "Fukushima / Renesas Semiconductor",
        "period": "March 2011",
        "key_metric": "automotive production loss",
        "historical_impact": "Toyota $1.2B loss, 800K vehicles not produced",
    }

    return SupplyChainNetwork(nodes, edges), disruptions, meta


# ═════════════════════════════════════════════════════════════
# Scenario 5: Thai Floods (2011)
# ═════════════════════════════════════════════════════════════

def thai_floods() -> tuple[SupplyChainNetwork, list[Disruption], dict]:
    """Hard disk drive supply chain collapse.

    Key features:
      - Thailand produced ~45% of world HDD components
      - Western Digital, Seagate, and Toshiba factories flooded
      - HDD prices doubled; recovery took >6 months
      - Accelerated SSD adoption (structural market shift)
    """
    nodes = [
        # Tier 0: HDD components (Thai industrial estates)
        SupplyNode("Navanakorn (heads)",   tier=0, sector="HDD",
                   baseline=np.array([0.9, 1.0, 0.90, 0.85])),
        SupplyNode("Rojana (motors)",      tier=0, sector="HDD",
                   baseline=np.array([0.9, 1.0, 0.88, 0.82])),
        SupplyNode("Hi-Tech (platters)",   tier=0, sector="HDD",
                   baseline=np.array([0.9, 1.0, 0.85, 0.80])),

        # Tier 1: HDD assembly
        SupplyNode("Western Digital",      tier=1, sector="HDD",
                   baseline=np.array([0.8, 1.0, 0.92, 0.90])),
        SupplyNode("Seagate",              tier=1, sector="HDD",
                   baseline=np.array([0.8, 1.0, 0.90, 0.88])),
        SupplyNode("Toshiba Storage",      tier=1, sector="HDD",
                   baseline=np.array([0.7, 1.0, 0.85, 0.85])),

        # Tier 2: OEMs / Data centers
        SupplyNode("Dell",                 tier=2, sector="electronics",
                   baseline=np.array([0.6, 1.0, 0.88, 0.90])),
        SupplyNode("HP",                   tier=2, sector="electronics",
                   baseline=np.array([0.6, 1.0, 0.86, 0.88])),
        SupplyNode("Cloud providers",      tier=2, sector="cloud",
                   baseline=np.array([0.5, 1.0, 0.92, 0.95])),

        # Tier 3: Consumer retail
        SupplyNode("Retail electronics",   tier=3, sector="retail",
                   baseline=np.array([0.7, 1.0, 0.80, 0.85])),
    ]

    edges = [
        # Thai components → HDD assemblers
        SupplyEdge(0, 3, weight=0.90),    # heads → WD
        SupplyEdge(0, 4, weight=0.80),    # heads → Seagate
        SupplyEdge(1, 3, weight=0.85),    # motors → WD
        SupplyEdge(1, 5, weight=0.75),    # motors → Toshiba
        SupplyEdge(2, 3, weight=0.80),    # platters → WD
        SupplyEdge(2, 4, weight=0.85),    # platters → Seagate
        SupplyEdge(2, 5, weight=0.70),    # platters → Toshiba

        # Assemblers → OEMs
        SupplyEdge(3, 6, weight=0.80),
        SupplyEdge(3, 7, weight=0.75),
        SupplyEdge(4, 6, weight=0.60),
        SupplyEdge(4, 8, weight=0.85),
        SupplyEdge(5, 7, weight=0.50),
        SupplyEdge(5, 8, weight=0.60),

        # OEMs → Retail
        SupplyEdge(6, 9, weight=0.7),
        SupplyEdge(7, 9, weight=0.65),
    ]

    disruptions = [
        # Massive flooding: all Thai industrial estates
        Disruption("Thai floods: component plants", onset_step=45, duration=50,
                   affected_nodes=[0, 1, 2],
                   severity=0.90, disruption_type='capacity'),
        # WD factory directly flooded
        Disruption("WD Bangpa-In flooding", onset_step=48, duration=45,
                   affected_nodes=[3],
                   severity=0.85, disruption_type='capacity'),
        # Financial stress from lost production
        Disruption("Industry financial stress", onset_step=55, duration=60,
                   affected_nodes=[3, 4, 5],
                   severity=0.4, disruption_type='financial'),
    ]

    meta = {
        "name": "Thailand Floods — HDD Supply Chain",
        "period": "Oct–Dec 2011",
        "key_metric": "HDD price and production impact",
        "historical_impact": "HDD prices doubled, 6+ month recovery",
    }

    return SupplyChainNetwork(nodes, edges), disruptions, meta


# ─────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────

ALL_SCENARIOS = {
    "covid_semiconductor": covid_semiconductor,
    "suez_canal":          suez_canal,
    "texas_winter_storm":  texas_winter_storm,
    "fukushima":           fukushima,
    "thai_floods":         thai_floods,
}
