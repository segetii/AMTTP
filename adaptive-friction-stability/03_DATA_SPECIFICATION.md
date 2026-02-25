# 03 — Data Specification: Datasets for Simulation

All datasets required for the research programme, organised by purpose.

---

## Category 1: Historical Crypto Collapse Events (Validation)

These datasets validate the DPD model by reproducing observed collapse dynamics.

| # | Event | Date | Data Source | Records (est.) | What To Model |
|---|-------|------|-------------|-----------------|---------------|
| 1 | **Terra/Luna collapse** | May 2022 | Flipside Crypto, Terra public chain archives, CoinGecko API | ~500K txns over 5 days | UST depeg spiral: $1 → $0.02 in 72h. Mint/burn redemption cascade. Positive feedback death spiral. |
| 2 | **Iron Finance / TITAN** | Jun 2021 | Polygon chain data, DeFi Llama, The Graph | ~100K txns over 24h | Partial-collateral stablecoin collapse. $65 → $0 in 12 hours. Bank-run dynamics with lower TVL. |
| 3 | **FTX / Alameda contagion** | Nov 2022 | CoinGecko API, Kaiko market data, Nansen on-chain labels, FTT token flows | ~2M txns over 2 weeks | Contagion cascade across 100+ tokens. Withdrawal stampede. Credit contagion through DeFi. |
| 4 | **Chainlink oracle manipulation** | Sep 2020 | Chainlink price oracle logs, Ethereum mempool archives, Etherscan | ~50K txns/events | Flash loan → oracle manipulation → cascading Aave/Compound liquidations. $89M forced liquidations. |
| 5 | **3AC / Celsius contagion** | Jun-Jul 2022 | Nansen on-chain labels, Glassnode, Etherscan | ~1M txns over 4 weeks | Hidden leverage unwinding. Credit contagion chain: 3AC → Voyager → Celsius → BlockFi. |
| 6 | **Curve Finance exploit** | Jul 2023 | Curve pool data, Etherscan, DeFi Llama | ~200K txns over 1 week | Reentrancy → $70M drained → CRV death spiral → near-systemic event. Narrowly averted by OTC. |

### How to Obtain

- **Flipside Crypto**: https://flipsidecrypto.xyz — Free SQL queries on Terra, Ethereum, Polygon chain data
- **CoinGecko API**: https://www.coingecko.com/en/api — Historical price/volume data (free tier: 30 calls/min)
- **Kaiko**: https://www.kaiko.com — Institutional-grade market data (may need academic licence)
- **Nansen**: https://www.nansen.ai — Labelled wallet data (paid, academic discount available)
- **Glassnode**: https://glassnode.com — On-chain metrics (free tier available)
- **The Graph**: https://thegraph.com — Decentralised indexing protocol (free subgraph queries)
- **Etherscan API**: https://etherscan.io/apis — Transaction data (free tier: 5 calls/sec)
- **BigQuery Ethereum**: `bigquery-public-data.crypto_ethereum` — Full Ethereum history (free with Google Cloud credits)

---

## Category 2: Stablecoin Peg Dynamics (Stability Analysis)

Continuous price data showing peg maintenance and deviation — the core stability phenomenon.

| # | Dataset | Source | Records (est.) | Time Range | Purpose |
|---|---------|--------|-----------------|------------|---------|
| 7 | **USDT hourly peg data** | CoinGecko / Kaiko | ~50K data points | 2020–present | Show stable system: small perturbations self-correct. Quantify natural friction. |
| 8 | **USDC hourly peg data** | CoinGecko / Kaiko | ~50K data points | 2020–present | Full-reserve model: high friction γ → very stable. Compare with partial-reserve. |
| 9 | **DAI hourly peg data** | CoinGecko / Maker protocol | ~50K data points | 2020–present | Over-collateralised CDP model: algorithmic friction via liquidation thresholds. |
| 10 | **UST pre-collapse hourly** | Terra chain archives | ~10K data points | Jan 2022 – May 2022 | Show divergence approaching γ < γ* condition. Peg stress before collapse. |
| 11 | **FRAX hourly** | DeFi Llama / CoinGecko | ~20K data points | 2021–present | Partial collateralisation = partial friction. Intermediate stability case. |
| 12 | **LUSD hourly** | Liquity protocol / CoinGecko | ~20K data points | 2021–present | Redemption-fee friction model. Hard floor mechanism. |
| 13 | **sUSD depeg events** | Synthetix protocol data | ~5K data points | 2020–2022 | Recovery dynamics under governance-mediated friction. Manual intervention. |

### Key Variables to Extract

For each stablecoin:
- Price deviation from peg: Δp(t) = p(t) − 1.0
- Trading volume: proxy for kinetic energy
- TVL / collateral ratio: proxy for potential well depth
- Redemption/mint rate: proxy for friction γ(t)
- Whale transaction count: proxy for adversarial perturbation ξ(t)

---

## Category 3: Transaction Graph Data (AMTTP Integration)

Large-scale labelled transaction data for the anomaly detection / friction application.

| # | Dataset | Source | Records | Features | Labels | Purpose |
|---|---------|--------|---------|----------|--------|---------|
| 14 | **Ethereum 30-day transactions** | BigQuery `crypto_ethereum` | 1.67M txns | ~50 raw features | Unlabelled | Live AML friction application. Production AMTTP data. |
| 15 | **BitcoinHeist** | UCI ML Repository | 2,640,911 rows | 177 features | Binary (fraud: 0.87%) | Supervised anomaly baseline. Teacher model training data. |
| 16 | **Elliptic Bitcoin** | Kaggle | 203,769 txns | 49 features | Binary + temporal | Graph-labelled illicit flows with temporal ordering. |
| 17 | **Ethereum fraud detection** | Kaggle | ~9,800 addresses | 8 features | Binary | Labelled fraudulent Ethereum addresses. |
| 18 | **DeFi protocol interactions** | The Graph subgraphs | Variable | Protocol-specific | Unlabelled | AMM/lending pool dynamics: Uniswap, Aave, Compound. |

### Already Available in Workspace

- BitcoinHeist + Ethereum Kaggle: already used in AMTTP training pipeline
- BigQuery 30-day Ethereum: already queried for AMTTP production data
- Anomaly benchmarks (mammography, shuttle, pendigits, synthetic, mimic): used in UDL/GravityEngine evaluation

---

## Category 4: Synthetic Controlled Experiments

Purpose-built simulations to validate theoretical predictions.

| # | Experiment | N Agents | Duration | What It Tests |
|---|-----------|----------|----------|---------------|
| 19 | **Zero-friction economy** | 100–1000 | 500 steps | Prove instability: inject adversarial ξ, show ||X|| → ∞ without damping |
| 20 | **Adaptive friction economy** | 100–1000 | 500 steps | Prove stability: same adversary, apply γ(t) ≥ γ*, show bounded trajectories |
| 21 | **Critical threshold sweep** | 500 | 200 steps × 50 γ values | Map the stability boundary: find γ* as function of adversary budget B |
| 22 | **Adversarial agent injection** | 500 + 10–50 adversaries | 300 steps | Measure minimum γ* needed to absorb coordinated attack |
| 23 | **Mass-dependent stability** | 500 (varying mass) | 300 steps | Effect of capital concentration (whale agents) on γ* |
| 24 | **Multi-agent RL adversary vs RL controller** | 500 | 10K episodes | Nash equilibrium of the friction game. Does RL converge? |
| 25 | **Phase transition experiment** | 1000 | 500 steps, varying σ | Identify market "melting point" — where cluster structure dissolves |
| 26 | **Terra/Luna synthetic replay** | 200 agents | Calibrate to real data | Reproduce observed collapse dynamics. Validate γ* prediction. |

### Synthetic Data Generation Parameters

```python
# Base economy
N_agents = 500
d_features = 10          # economic state dimensions
mass_dist = "lognormal"  # capital follows power law
sigma_interact = 1.0     # interaction range
lambda_rep = 0.1         # competition strength
alpha_anchor = 0.1       # mean-reversion strength

# Adversary
B_budget = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0]  # adversarial budgets to sweep
xi_strategy = "optimal"  # worst-case perturbation direction

# Friction sweep
gamma_values = np.linspace(0, 2.0, 50)  # friction from zero to heavy
```

---

## Category 5: Macroeconomic Extension Data (Future — Tier 1)

For generalising beyond crypto to traditional economic systems.

| # | Dataset | Source | Purpose |
|---|---------|--------|---------|
| 27 | **Bank run historical data** | FDIC, Bank of England archives | Validate friction-stability theory in TradFi |
| 28 | **Currency attack episodes** | IMF IFS database | Soros/ERM 1992, Asian crisis 1997 — zero-friction foreign exchange |
| 29 | **Flash crash 2010** | SEC MIDAS data | Ultra-low-friction equity market instability |
| 30 | **CBDC pilot data** | BIS Innovation Hub, Digital Yuan logs | Central bank digital currency stability |

---

## Data Pipeline Architecture

```
Raw Sources → Extraction → Standardisation → DPD State Mapping → Simulation
     ↓              ↓              ↓                 ↓               ↓
 APIs/Chain    Python/SQL    Normalise to       Map to (X, Ẋ,     Run GravityEngine
  archives     scripts     common schema       M, γ, ξ)          / DPE dynamics
```

### State Mapping (Economic → Particle)

| Economic Variable | Particle Variable | Symbol |
|-------------------|-------------------|--------|
| Wallet balance / TVL | Mass | m_i |
| (price, volume, volatility, ...) feature vector | Position | x_i |
| Transaction rate, capital flow velocity | Velocity | ẋ_i |
| Compliance level, circuit breaker status | Damping | γ(t) |
| Adversarial trades, flash loans, exploits | External perturbation | ξ(t) |
| Market cap concentration (HHI) | Mass distribution | M |
| Liquidation threshold | Potential well depth | Φ_depth |
