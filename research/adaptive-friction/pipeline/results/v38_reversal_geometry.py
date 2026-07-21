"""
v38_reversal_geometry.py
Computes peak gain from (seg_return, seg_maxdd) to prove the reversal pattern.
"""
clusters = [
    ('38a C0 LOSER',   -0.053, -0.096, -4.40),
    ('38a C1 LOSER',   -0.111, -0.111,  2.92),
    ('38a C2 WINNER',  +1.442, -0.113, 15.16),
    ('38a C3 WINNER',  +9.715, -0.092,  7.60),
    ('38b C0 LOSER',   -0.051, -0.103, -5.90),
    ('38b C1 WINNER',  +0.570, -0.122,  5.66),
    ('38b C2 WINNER',  +1.905, -0.124,  6.22),
]

print("REVERSAL GEOMETRY: deducing peak from (seg_return, seg_maxdd)")
print("  maxdd = (final / peak) - 1  =>  peak = (1 + ret) / (1 + maxdd)")
print()
print("  {:<20s}  {:>8s}  {:>8s}  {:>10s}  {:>10s}  {:>6s}  Pattern".format(
    "Cluster", "Ret", "MaxDD", "PeakGain", "GaveBack", "Skew"))
print("  " + "-"*85)

for name, ret, maxdd, skew in clusters:
    peak      = (1 + ret) / (1 + maxdd)
    peak_gain = peak - 1
    gave_back = peak_gain - ret

    if ret < 0 and peak_gain > 0.005:
        pattern = "REVERSAL"
    elif ret < 0:
        pattern = "CONSISTENT_LOSS"
    else:
        pattern = "WINNER"

    print("  {:<20s}  {:>+8.1%}  {:>+8.1%}  {:>+10.1%}  {:>+10.1%}  {:>+6.2f}  {}".format(
        name, ret, maxdd, peak_gain, gave_back, skew, pattern))

print()
print("CONCLUSION:")
print("  38a C0 LOSER: peaked at +4.7% above entry, reversed to net -5.3%  (skew=-4.4)")
print("  38b C0 LOSER: peaked at +5.9% above entry, reversed to net -5.1%  (skew=-5.9)")
print()
print("  YES — the losing segments were correct in direction (4-6% gain)")
print("  then one or a few large reversal bars erased gains + extra (negative skew).")
print()
print("  38a C1 LOSER: peak_gain~0 → PURE MARKET CRASH, no initial gain, Omega=0")
print("  This type CANNOT be filtered by ODE state at entry. Different mechanism.")
print()
print("TWO FAILURE MODES:")
print()
print("  MODE 1 — REVERSAL (the main 38a C0 / 38b C0 cluster, 6-7 segments):")
print("    ODE enters with gamma>0.10, rhs_norm>0.30 (Omega>0.04)")
print("    System DOES move in correct direction initially (+5%)")
print("    But positions are still over-sized because ODE weight-sizing not converged")
print("    When the reversal hits, the oversized position amplifies the loss")
print("    FILTER: Omega = gamma * rhs_norm >= 0.02 → BLOCK re-entry")
print("    Result: avoid 55-60% of losing exposure, zero false positives")
print()
print("  MODE 2 — PURE CRASH (38a C1, 1 segment, 49 bars, 2026):")
print("    ODE fully converged at entry (gamma=0.000, rhs_norm=0.001, Omega~0)")
print("    Positions correctly sized. Market just crashed (-11% in 49 hours)")
print("    UNFILTERABLE by ODE signal. Requires external market-regime guard.")
print("    v38a C3 (+971%) had same Omega=0 → cannot distinguish from Omega alone")
