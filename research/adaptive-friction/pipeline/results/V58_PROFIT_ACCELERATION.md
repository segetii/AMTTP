# Why Profit Starts Lower Then Accelerates

This note explains why the late intraday trading branch shows relatively modest profit in the first test year and then grows much faster in later years.

It is based on the current late-branch champion configuration:

- script: `run_crypto_pairs_v58_stability_patch.py`
- variant: `v58_tight`
- test window: 2023-01-01 to 2026-04-24
- train window: 2021-01-01 to 2022-12-31
- fee model: 5 bps trading-cost model applied per active hourly bar
- reference risk setting for the explanation below: dd20 view, `K=5`

## Short Answer

The later profit growth is driven by two things at once:

1. compounding
2. a stronger trading regime for this strategy in 2024-2025 than in 2023

It is not caused by the system being inactive in the first year. The strategy was effectively active throughout the test period.

## Year-By-Year Net Results

For `v58_tight` at dd20 (`K=5`), the previously computed yearly net returns were:

| Year | Net return | End value on $700 |
|---|---:|---:|
| 2023 | 30.05% | $910.36 |
| 2024 | 140.95% | $2,193.49 |
| 2025 | 245.16% | $7,571.05 |
| 2026 YTD | 27.80% | $9,675.48 |

2026 is year-to-date only, through late April 2026.

## What The Diagnostics Show

### 1. It was not a low-activity first year

The strategy was active on every evaluated test bar in each year of the dd20 diagnostic run.

| Year | Test bars | Active bars | Active % |
|---|---:|---:|---:|
| 2023 | 1,720 | 1,720 | 100.0% |
| 2024 | 3,739 | 3,739 | 100.0% |
| 2025 | 2,447 | 2,447 | 100.0% |
| 2026 YTD | 499 | 499 | 100.0% |

So the slower first-year growth was not because the model was sitting out waiting for signals.

### 2. The per-bar edge improved materially after 2023

The strategy made more on each active bar in later years.

| Year | Avg net bps per bar | Annualized net Sharpe |
|---|---:|---:|
| 2023 | 1.649 | 2.5829 |
| 2024 | 2.507 | 3.4808 |
| 2025 | 5.495 | 4.4714 |
| 2026 YTD | 5.213 | 5.2129 |

That means the system was not merely benefiting from a larger account. The expected return per unit of trading activity was also improving.

### 3. Later years were better regimes for this signal stack

This strategy is not a simple long-only crypto bet. It benefits from:

- volatility
- dislocations across assets
- spread movement
- reversals and regime instability that create exploitable two-sided movement

The underlying market diagnostics show why 2024-2025 became more favorable.

#### Realized volatility

| Year | BTC vol | ETH vol | SOL vol | ETH-BTC spread vol |
|---|---:|---:|---:|---:|
| 2023 | 76.45% | 80.13% | 190.07% | 47.37% |
| 2024 | 66.01% | 80.09% | 112.83% | 49.10% |
| 2025 | 69.70% | 115.77% | 136.34% | 71.60% |
| 2026 YTD | 96.94% | 127.98% | 141.62% | 54.46% |

#### Mean absolute hourly move

| Year | BTC | ETH | ETH-BTC spread |
|---|---:|---:|---:|
| 2023 | 51.40 bps | 59.68 bps | 31.89 bps |
| 2024 | 54.28 bps | 65.65 bps | 38.54 bps |
| 2025 | 52.19 bps | 88.06 bps | 55.51 bps |
| 2026 YTD | 81.54 bps | 106.42 bps | 45.63 bps |

This is the key structural reason profit accelerated. Later years had more movement and more cross-asset dispersion for the strategy to harvest.

### 4. 2025 is the clearest proof it is not just market beta

In 2025 the strategy was strongest even though the main underlying assets were weak:

| Year | BTC return | ETH return | SOL return |
|---|---:|---:|---:|
| 2023 | 136.09% | 73.19% | 524.65% |
| 2024 | 92.30% | 19.88% | 22.93% |
| 2025 | -14.85% | -31.96% | -54.53% |
| 2026 YTD | -15.20% | -27.55% | -36.70% |

If the system were simply riding bull markets, 2023 should have dominated 2025. It did not. That strongly suggests the strategy gains more from unstable, tradable structure than from one-way upside.

## Why Dollar Profit Looks Exponentially Bigger Later

Even if the percentage return were constant, dollar profit would still accelerate because the capital base is larger after each winning year.

Example:

- a 30% gain on $700 adds about $210
- a 30% gain on $2,193 adds about $658
- a 30% gain on $7,571 adds about $2,271

So once the strategy both compounds capital and trades in a stronger regime, the later dollar gains become much larger very quickly.

## Bottom Line

The first year is lower because:

- the capital base is still small
- 2023 was a weaker regime for this strategy than 2024-2025

The later acceleration happens because:

- the account has compounded
- volatility and cross-asset dispersion improved
- the strategy's per-bar edge increased sharply in 2024-2025

This is a regime-plus-compounding effect, not a warm-up effect.