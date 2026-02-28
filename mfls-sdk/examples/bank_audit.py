"""
Bank-level BSDT audit: audit individual US banks via FDIC data
to identify which institutions are contributing most to systemic
risk, and through which blind-spot channels.
"""

from mfls import MFLSEngine


# Top-30 US banks by total assets (FDIC certificate IDs)
TOP_30_CERTS = [
    628,     # JPMorgan Chase
    476,     # Bank of America
    852,     # Wells Fargo
    27389,   # Citibank
    32992,   # US Bancorp
    6384,    # Truist
    3511,    # PNC
    27314,   # Capital One
    34968,   # TD Bank
    59017,   # Charles Schwab
    3303,    # BMO
    3510,    # Citizens
    9846,    # Fifth Third
    33947,   # Ally
    17534,   # KeyBank
    4297,    # Huntington
    57957,   # Goldman Sachs
    33124,   # Morgan Stanley
    18409,   # HSBC Bank USA
    58979,   # Discover
]

# Human-readable labels for the certificates
NAMES = [
    "JPMorgan Chase", "Bank of America", "Wells Fargo", "Citibank",
    "US Bancorp", "Truist", "PNC", "Capital One", "TD Bank",
    "Charles Schwab", "BMO", "Citizens", "Fifth Third", "Ally",
    "KeyBank", "Huntington", "Goldman Sachs", "Morgan Stanley",
    "HSBC Bank USA", "Discover",
]


def main():
    engine = MFLSEngine(
        normal_start="2005-01-01",
        normal_end="2006-12-31",
        n_boot=200,
    )

    # 1. Load FDIC panel for the first 20 certs
    print("Fetching FDIC data for 20 major US banks...")
    panel = engine.load_fdic_panel(
        certs=TOP_30_CERTS[:20],
        names=NAMES[:20],
        start="2005-01-01",
        end="2023-12-31",
    )
    print(f"  Panel: T={panel.X_std.shape[0]}, N={panel.X_std.shape[1]}")

    # 2. Run the MFLS signal pipeline
    print("\nComputing MFLS signal...")
    result = engine.fit_and_score(panel)
    print(f"  AUROC = {result.auroc:.4f}  CI = [{result.auroc_ci[0]:.4f}, {result.auroc_ci[1]:.4f}]")
    print(f"  Hit Rate  = {result.hit_rate:.4f}")
    print(f"  False Alarm = {result.false_alarm_rate:.4f}")
    print(f"  GFC lead  = {result.gfc_lead} quarters")

    # 3. Audit every quarter in the GFC period
    print("\nBSDT audit for Q4-2007 through Q4-2008:")
    gfc_range = [t for t, d in enumerate(panel.dates) if "2007-10" <= d <= "2008-12"]
    for t in gfc_range:
        audit = engine.bsdt_audit(t=t)
        top_3_idx = audit.total_score.argsort()[::-1][:3]
        top_3 = [(audit.institution_names[i], audit.total_score[i], audit.dominant_channel[i])
                 for i in top_3_idx]
        print(f"  {panel.dates[t]}: top-3 = {top_3}")

    # 4. Compare CCyB through the cycle
    ccyb = engine.ccyb()
    print("\nCCyB time series (selected quarters):")
    for t in range(0, len(ccyb), max(1, len(ccyb) // 10)):
        print(f"  {panel.dates[t]}: {ccyb[t]:.0f} bps")

    # 5. Herding monitor
    herd = engine.herding_score()
    print(f"\nHerding analysis:")
    print(f"  Peak herding score = {herd.herding_score.max():.4f}")
    peak_idx = herd.herding_score.argmax()
    print(f"  Occurred at: {panel.dates[peak_idx]}")
    print(f"  Channel weights from Signed-LR: {herd.signed_lr_weights}")


if __name__ == "__main__":
    main()
