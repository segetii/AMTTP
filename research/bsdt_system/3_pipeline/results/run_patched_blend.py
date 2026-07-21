from __future__ import annotations
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(r"c:\amttp\research\adaptive-friction\pipeline\results")))

import run_crypto_godmode_v27_all_microstructure as v27
from run_crypto_pairs_v34_full_combined import build_1h_df, TEST_START, TRAIN_START
from run_crypto_godmode_v1 import W_TARGET_A1, build_w_star, build_b_aligned
from run_crypto_canonical_v4 import build_factor_returns
from run_crypto_godmode_v8_multiasset_shell import ASSETS, fetch_futures_ohlcv_symbol
from v58_dd_gated_brake import build_sigma, regularise_sigma_g7, theta_from, compute_psi_star, fisher_weight_noise_sqrt, build_unit_for_sigma, STACKS, D_CHAMP, Q_CHAMP, RT_BPS
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from simulate_master_strategy import equity_metrics, INIT

def generate_curve(stack_def):
    df, _ = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    w_star = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned = build_b_aligned(w_star)
    factor_R = build_factor_returns(df)
    v27.RT_COST = RT_BPS / 10_000.0
    ohlc_map = {s: fetch_futures_ohlcv_symbol(s) for _, s, _, _ in ASSETS}
    ch = get_channel_series()
    
    Sigma_base, _, sdiag, bdiag = build_sigma(factor_R, train_mask, df, D_CHAMP)
    
    name, max_k, w_trend, w_ews, w_stoch, slip, tc, stop_sl, k_min_kcap = stack_def
    
    if max_k is None:
        Sigma_g7 = Sigma_base
    else:
        Sigma_g7, lam_g7 = regularise_sigma_g7(Sigma_base, float(max_k))
        
    theta_g7 = theta_from(b_aligned, train_mask, Sigma_g7, bdiag["budget"], Q_CHAMP)
    log_ann, unit = build_unit_for_sigma(df, train_mask, w_star, b_aligned, Sigma_g7, theta_g7, ch, ohlc_map)
    
    K_normal = 1.0 # Base engine scaling
    from v58_dd_gated_brake import simulate_dd_gated
    
    res = simulate_dd_gated(
        unit, log_ann, K_normal,
        cb_halt=0.00, cb_resume=0.00, cb_window_d=0, release_thr=0.0, release_ext=0,
        omega_a=0.0, curv_b=0.0, admiss_c=0.0, psi_star=0.0,
        g24_eta=0.0, g24_lock_min=0, g24_rank_Ix=3,
        dd_thr=None, dd_stop_brake=0.30, beta=0.0, k_min_frac=1.0
    )
    return res['eq']

def main():
    import warnings
    warnings.filterwarnings('ignore')
    print("Generating V55_Final curve...")
    eq_final = generate_curve(STACKS[0])
    print("Generating V55_Calmar curve...")
    eq_calmar = generate_curve(STACKS[1])
    
    print("Blending at 0.8 V55_Final + 0.2 V55_Calmar...")
    
    ret_final = eq_final.pct_change().fillna(0)
    ret_calmar = eq_calmar.pct_change().fillna(0)
    
    ret_blend = 0.8 * ret_final + 0.2 * ret_calmar
    eq_blend = (1 + ret_blend).cumprod() * INIT
    
    eq_blend_series = pd.Series(eq_blend)
    metrics = equity_metrics(eq_blend_series)
    
    print(f"\n==========================================")
    print(f"Patched 0.8 Dual Blend Results:")
    print(f"Final Equity : ${metrics['final']:,.0f}")
    print(f"Max Drawdown : {metrics['maxdd']*100:.2f}%")
    print(f"Calmar Ratio : {metrics['calmar']:.2f}")
    print(f"Sharpe Ratio : {metrics['sharpe']:.3f}")
    print(f"==========================================")

if __name__ == "__main__":
    main()
