"""
Quick-start example: load G-SIB panel, compute MFLS signal,
run full evaluation, and display results.
"""

from mfls import MFLSEngine


def main():
    engine = MFLSEngine(
        normal_start="2005-01-01",
        normal_end="2006-12-31",
        n_boot=500,
    )

    # 1. Load real G-SIB data (FDIC + World Bank + ECB)
    print("Loading G-SIB panel...")
    panel = engine.load_gsib_panel(start="2005-01-01", end="2023-12-31")
    print(f"  Panel: T={panel.X_std.shape[0]}, N={panel.X_std.shape[1]}, d={panel.X_std.shape[2]}")
    print(f"  Institutions: {panel.names}")

    # 2. Fit and score
    print("\nRunning MFLS pipeline...")
    result = engine.fit_and_score(panel)

    # 3. Blind-spot audit (latest quarter)
    print("\nBlind-spot audit (latest quarter):")
    audit = engine.bsdt_audit(t=-1)
    for i, name in enumerate(audit.institution_names):
        print(f"  {name:25s}  total={audit.total_score[i]:.3f}  dominant={audit.dominant_channel[i]}")

    # 4. CCyB recommendation
    ccyb = engine.ccyb()
    print(f"\nCurrent CCyB recommendation: {ccyb[-1]:.0f} bps")
    print(f"Peak CCyB (all time):        {ccyb.max():.0f} bps")

    # 5. Herding monitor
    herd = engine.herding_score()
    print(f"\nHerding monitor:")
    print(f"  Current herding score: {herd.herding_score[-1]:.4f}")
    print(f"  beta_delta_T:          {herd.beta_delta_T:.4f}")
    print(f"  Channel weights:       {herd.signed_lr_weights}")


if __name__ == "__main__":
    main()
