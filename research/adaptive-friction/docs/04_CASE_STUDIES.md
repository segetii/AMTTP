# 04 — Case Studies: Where Systems Exploded

Six historical crypto collapses analysed through the DPD (Dissipative Particle Dynamics) lens. Each case maps to a specific failure mode in the particle system.

---

## Case 1: Terra/Luna — The Canonical Death Spiral (May 2022)

### What Happened

UST was an algorithmic stablecoin pegged to $1 via a mint/burn mechanism with LUNA:
- To mint 1 UST → burn $1 worth of LUNA
- To redeem 1 UST → mint $1 worth of LUNA

On 7 May 2022, a large UST holder sold ~$285M on Curve. The peg slipped to $0.985. Arbitrageurs sold UST → minted LUNA → sold LUNA → LUNA price dropped → collateral value dropped → more UST selling → **positive feedback death spiral**. By 13 May, UST was $0.02 and LUNA was $0.00. $60 billion destroyed.

### DPD Model Mapping

| Economic Element | Particle Variable | Value/Behaviour |
|-----------------|-------------------|-----------------|
| UST holders | Particles (N ≈ 500K active) | Positions in (price, holding) space |
| LUNA market cap | System mass M | ~$40B → 0 |
| Anchor Protocol yield | Attraction force (γ = high) | 20% APY pulled capital into UST |
| Mint/burn mechanism | **Zero friction** (γ = 0) | Unlimited redemption, no rate limit, no circuit breaker |
| $285M sell | Adversarial impulse ξ(t₀) | Kicked system beyond potential well rim |
| Death spiral | Unbounded trajectory ||X(t)|| → ∞ | Lyapunov V(t) → ∞ monotonically |

### Why It Exploded (DPD Analysis)

The mint/burn mechanism had **γ = 0** — zero friction on redemptions. The system's interaction potential had a finite well depth (determined by LUNA market cap). The adversarial impulse exceeded the escape energy:

```
||ξ(t₀)|| > √(2 · V_well_depth / M_system)
```

Once outside the well, the positive feedback (minting LUNA dilutes price → more selling → deeper depeg) acts as a **negative damping** — anti-friction that accelerates divergence.

### What Friction Would Have Saved It

- **Redemption rate limits**: Cap UST→LUNA minting at $X/day (friction γ > 0)
- **Dynamic collateral requirement**: Increase collateral ratio when peg deviation ΔP > threshold
- **Circuit breaker**: Halt redemptions when depeg exceeds 2% (emergency friction γ → ∞)
- **Gradual fee scaling**: Redemption fee increasing with depeg severity (adaptive γ(t))

### Predicted Critical Threshold

```
γ*(Terra) ≈ ξ_max / ||Ẋ_max|| ≈ $285M / (30-day avg redemption rate)
```

If redemptions were capped at ~$50M/day, the system would have absorbed the shock.

---

## Case 2: Iron Finance / TITAN — The Faster Collapse (June 2021)

### What Happened

Iron Finance ran a partially-collateralised stablecoin (IRON) on Polygon:
- 75% USDC + 25% TITAN token backing
- TITAN price provided the variable collateral

A large whale sold TITAN on 16 June 2021. TITAN dropped from $65 → panic → the 25% TITAN backing lost value → IRON depegged → redemptions minted more TITAN → TITAN went to $0 in **12 hours**. Mark Cuban lost millions.

### DPD Model Mapping

- **Lower mass system** than Terra (smaller TVL, ~$2B vs $40B)
- **Shallower potential well** (only 25% variable backing)
- **Same zero friction** on redemptions
- **Faster collapse** because lower inertia (less capital to absorb shocks)

### Key Insight

The critical friction threshold γ* is **inversely proportional to potential well depth**:

```
γ* ∝ B / V_depth
```

Iron Finance had a shallower well (25% collateral) and needed *more* friction than Terra, not less. It had the same zero friction. Collapse was inevitable given sufficient perturbation.

---

## Case 3: Chainlink Oracle Manipulation (September 2020)

### What Happened

An attacker used flash loans to manipulate Chainlink price feeds on Aave and Compound. The manipulated oracle reported incorrect asset prices → $89M in cascading liquidations → users lost collateral to unfair liquidation prices.

### DPD Model Mapping

This is fundamentally different from Terra/Luna. It's an **external force injection**:

| Economic Element | Particle Variable |
|-----------------|-------------------|
| Oracle price feed | External field operator Φ_k |
| Flash loan manipulation | Impulse ξ(t₀) applied through operator channel |
| Liquidation cascade | Chain reaction: particle i's displacement forces particle j |
| No circuit breaker on liquidations | γ = 0 on the liquidation path |

### Key Insight

This maps to the **operator deviation pull** in GravityEngine:

```
F_op = −Σ_k β_k · DΦ_k(x)ᵀ D_k(x)
```

The oracle is an operator Φ_k. When the operator is corrupted, the force field itself is adversarially modified — not just a perturbation ξ, but a perturbation to the *potential*:

```
Φ(X) → Φ(X) + δΦ_adversarial(X)
```

The Lyapunov analysis must account for **Input-to-State Stability (ISS)** — bounded disturbances to both the state AND the potential. This requires a stronger theorem:

```
V̇ ≤ −αV + β₁||ξ|| + β₂||δΦ||
```

### What Friction Would Have Saved It

- **Oracle delay buffer**: Time-weighted average prices (TWAP) instead of spot (friction on information propagation)
- **Liquidation cooldown**: Minimum wait period between liquidations of same collateral
- **Liquidation rate cap**: Maximum liquidation volume per block

---

## Case 4: FTX / Alameda Contagion (November 2022)

### What Happened

FTX (centralised exchange) was secretly insolvent. Alameda Research (sister trading firm) held massive FTT (FTX token) positions used as collateral. When CoinDesk exposed the balance sheet on 2 November:

1. Binance announced selling $500M FTT → FTT price collapsed
2. FTX withdrawal stampede (bank run): $6B withdrawn in 72h
3. FTX halted withdrawals → confirmed insolvency
4. Contagion: Genesis halted withdrawals → BlockFi bankruptcy → Voyager bankruptcy → Silvergate bank failure

### DPD Model Mapping

This is **N-body contagion** — the most complex case:

| Economic Element | Particle Variable |
|-----------------|-------------------|
| FTX | Massive particle (m_FTX ≫ others), suddenly removed |
| FTT token holders | Cluster of particles gravitationally bound to FTX |
| Other exchanges/lenders | Particles at various distances from FTX |
| Credit linkages | Pairwise interaction potential (hidden until revealed) |
| Bank run | All velocity vectors pointing outward (withdrawal) |
| Contagion cascade | Sequential escape: nearest particles first, then second-nearest |

### Key Insight

Removing a massive particle (FTX) from the system **shifts the centre of mass μ** and **reduces the total potential well depth**. All particles previously in quasi-stable orbits around FTX are suddenly unbound.

The contagion propagates at the "speed of information" — particles nearest to FTX in economic space (Genesis, BlockFi) escape first. This is analogous to a **gravitational wave** propagating outward from a mass removal event.

### Critical Observation

The system had **hidden interaction terms** — undisclosed credit linkages between FTX/Alameda and other entities. The true interaction potential Φ was unknown to most participants. This is an **information asymmetry** problem:

```
Φ_observed(X) ≠ Φ_true(X)
```

The Lyapunov function constructed from Φ_observed was invalid. Stability was illusory.

**Implication**: The friction controller must be robust to **unknown interaction potentials** — a requirement for ISS under model uncertainty.

---

## Case 5: 3AC / Celsius Contagion Chain (June–July 2022)

### What Happened

Three Arrows Capital (3AC), a crypto hedge fund, borrowed billions using GBTC and stETH as collateral. When both depegged:

1. 3AC couldn't meet margin calls → $3.5B default
2. Voyager Digital (3AC's lender) → bankruptcy
3. Celsius Network (exposed to 3AC via stETH) → froze withdrawals → bankruptcy
4. BlockFi (lent to 3AC) → distressed → eventually bankrupt after FTX rescue collapsed

### DPD Model Mapping

This is **hidden leverage unwinding** — similar to FTX but slower (weeks instead of days):

- **Leverage** = particles with inflated apparent mass (m_apparent ≫ m_real)
- **Margin call** = sudden mass correction: m_i snaps from m_apparent to m_real
- **Cascade** = mass corrections propagate through credit linkages
- **Friction** = redemption gates, withdrawal limits (Celsius froze withdrawals — emergency γ → ∞, but too late)

### Key Insight

The system was operating with **incorrect mass parameters**. The Lyapunov function:

```
V(X, Ẋ) = Φ(X) + ½ ẊᵀMẊ
```

was computed with M = M_apparent ≠ M_real. When the true masses were revealed, V jumped discontinuously — the system was already outside the true stability region while appearing stable.

---

## Case 6: Curve Finance Exploit (July 2023)

### What Happened

A Vyper compiler reentrancy bug was exploited across multiple Curve pools:
- $70M drained from alETH/msETH/pETH pools
- CRV token price crashed (founder had $168M in Aave CRV-collateralised loans)
- If CRV hit $0.37 → Aave forced liquidation → cascading DeFi failure
- Averted by OTC deals: founder sold CRV at $0.40 to Tron, DWF Labs, others

### DPD Model Mapping

| Economic Element | Particle Variable |
|-----------------|-------------------|
| Exploit (reentrancy) | Sudden energy injection: E_inject = $70M |
| CRV price crash | Particle displacement toward escape threshold |
| Aave liquidation boundary | Potential well rim at r = r_critical ($0.37 CRV price) |
| OTC deals | **Manual friction injection**: human intervention applied γ_emergency |
| Near-miss | System touched the rim but didn't escape |

### Key Insight

This case shows **manually applied emergency friction** — the OTC deals were economically equivalent to increasing γ(t) by orders of magnitude at the critical moment. The system narrowly avoided phase transition (collapse) because:

```
γ_OTC(t_critical) > γ*(t_critical)
```

An automated friction controller (RL) could have done this faster and without requiring personal phone calls between billionaires.

---

## Summary: Failure Mode Taxonomy

| Case | Failure Mode | DPD Description | γ at Failure |
|------|-------------|-----------------|-------------|
| Terra/Luna | Death spiral (positive feedback) | Negative damping outside well | γ = 0, needed γ ≈ redemption cap |
| Iron Finance | Same, but faster (lower inertia) | Shallower well, same zero γ | γ = 0, needed γ ∝ 1/V_depth |
| Chainlink | Oracle corruption (potential modification) | External operator ξ corrupted Φ | γ = 0 on liquidation path |
| FTX | Mass removal + contagion | Massive particle removed, cascade | γ = 0 on withdrawals |
| 3AC/Celsius | Hidden leverage (incorrect masses) | M_apparent ≠ M_real, V discontinuous | γ irrelevant (wrong model) |
| Curve | Energy injection + near-miss | Kicked to rim, manual γ rescue | γ_manual saved it just in time |

### Common Thread

**Every single case had γ = 0 (no friction) on the critical path.** The system was designed to be "frictionless" — which is exactly what made it unstable. The core theorem predicts all six cases:

> Zero-friction equilibria are generically unstable under bounded adversarial perturbation.
