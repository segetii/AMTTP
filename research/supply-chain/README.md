# Domain VI: Supply Chain Disruption and Resilience

BSDT universality validation on supply chain networks.
Implements the four-channel decomposition, adaptive friction, and critical manifold
framework from the grand unification paper (Section 8).

## Historical Scenarios

1. **COVID-19 Semiconductor Shortage (2020–2022)** — TSMC concentration risk, cascading automotive/electronics disruption
2. **Suez Canal Blockage (March 2021)** — 6-day Ever Given blockage, $9.6B/day trade impact
3. **Texas Winter Storm / ERCOT (Feb 2021)** — Petrochemical cascade → automotive → consumer goods
4. **Fukushima (2011)** — Renesas Electronics single-source failure, Toyota $1.2B loss
5. **Thai Floods (2011)** — HDD supply chain collapse, Western Digital/Seagate disruption

## Running

```bash
py -3 research/supply-chain/run_supply_chain_sim.py
```

Results are saved to `research/supply-chain/results/` and figures to `research/supply-chain/figures/`.
