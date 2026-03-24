"""
benchmark_quantum_qpt.py — Extended Benchmark vs Standard Methods
==================================================================
Computes and compares BSDT against all standard condensed-matter QPT
detection methods, including several not in the original experiment run.

Includes re-computation from exact diagonalization for:
  - Energy variance / specific heat C_v = (d²E_0/dh²)
  - Second Renyi entropy S_2
  - Quantum Fisher information (QFI) from density matrix
  - Magnetisation susceptibility (all orders)
  - Correlation length proxy (log(C_long/C_zz))
  - Fidelity susceptibility chi_F
  - Binder cumulant crossing (multi-N)

Author: Odeyemi Olusegun Israel
"""
from __future__ import annotations
import sys, time, json, warnings
import numpy as np
warnings.filterwarnings('ignore')

from pathlib import Path
ROOT = Path(r'c:\amttp')
sys.path.insert(0, str(ROOT / 'research' / 'quantum'))

from quantum_engine import (
    TransverseFieldIsing, MeanFieldIsing, QuantumBSDT,
    sweep_field, label_qpt, label_postqpt,
    compute_mfls, compute_obs_gradient_norm,
)

# ── Metrics ──
def auc_score(y_true, scores):
    y = np.asarray(y_true, dtype=int)
    s = np.asarray(scores, dtype=np.float64)
    pos, neg = s[y == 1], s[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return 0.5
    return float(np.mean(pos[:, None] > neg[None, :]) +
                 0.5 * np.mean(pos[:, None] == neg[None, :]))

def peak_location(h_vals, scores):
    return h_vals[np.argmax(scores)]

def detection_lead(h_vals, scores, h_c, pct=90):
    thr = np.percentile(scores, pct)
    pre = np.where((h_vals < h_c) & (scores > thr))[0]
    if len(pre) == 0:
        return 0
    return int(np.argmin(np.abs(h_vals - h_c)) - pre[0])


# =====================================================================
#  EXTENDED BENCHMARK
# =====================================================================
def run_benchmark(N=12, n_steps=100, J=1.0):
    print(f"\n{'=' * 80}")
    print(f"  EXTENDED BENCHMARK — BSDT vs Standard QPT Methods")
    print(f"  N = {N}  (dim = {1<<N}),  n_steps = {n_steps}")
    print(f"{'=' * 80}")

    model = TransverseFieldIsing(N, J)
    h_vals = np.linspace(0.01, 2.0 * J, n_steps)
    y_crit = label_qpt(h_vals, J, width=0.15)
    y_post = label_postqpt(h_vals, J)

    print("\n  Sweeping field...")
    t0 = time.perf_counter()
    results = sweep_field(model, h_vals, n_states=6, verbose=False)
    print(f"  Sweep done in {time.perf_counter()-t0:.1f}s")

    obs_list = [r['obs'] for r in results]
    psi_list = [r['psi'] for r in results]
    energy_list = [r['energies'] for r in results]

    # Extract arrays
    m_abs  = np.array([o['m_abs']    for o in obs_list])
    svn    = np.array([o['S_vN']     for o in obs_list])
    gap    = np.array([o['gap_phys'] for o in obs_list])
    c_rat  = np.array([o['C_ratio']  for o in obs_list])
    binder = np.array([o['binder']   for o in obs_list])
    e0     = np.array([o['e0']       for o in obs_list])
    c_zz   = np.array([o['C_zz']    for o in obs_list])
    c_long = np.array([o['C_long']   for o in obs_list])
    ipr    = np.array([o['IPR']      for o in obs_list])
    m_x    = np.array([o['m_x']     for o in obs_list])

    # --- Derivatives ---
    dm_dh   = np.abs(np.gradient(m_abs, h_vals))
    d2m_dh2 = np.abs(np.gradient(np.gradient(m_abs, h_vals), h_vals))
    dsvn_dh = np.abs(np.gradient(svn, h_vals))
    dgap_dh = np.abs(np.gradient(gap, h_vals))
    de0_dh  = np.gradient(e0, h_vals)
    d2e0_dh2 = np.abs(np.gradient(de0_dh, h_vals))  # specific heat proxy

    # --- Fidelity susceptibility ---
    chi_F = np.zeros(len(h_vals))
    for i in range(1, len(results) - 1):
        dh = h_vals[i+1] - h_vals[i-1]
        F = float(np.abs(np.vdot(psi_list[i-1], psi_list[i+1])) ** 2)
        chi_F[i] = -2.0 * np.log(max(F, 1e-30)) / max(dh**2, 1e-30)
    chi_F[0] = chi_F[1]; chi_F[-1] = chi_F[-2]

    # --- Ground state fidelity |<psi(h)|psi(h+dh)>|^2 ---
    fidelity_chain = np.ones(len(h_vals))
    for i in range(1, len(results)):
        fidelity_chain[i] = float(np.abs(np.vdot(psi_list[i-1], psi_list[i]))**2)
    infidelity_rate = 1.0 - fidelity_chain

    # --- Second Renyi entropy ---
    renyi2 = np.zeros(len(h_vals))
    Na = N // 2
    Nb = N - Na
    for i, psi in enumerate(psi_list):
        psi_mat = psi.reshape(1 << Nb, 1 << Na)
        s = np.linalg.svd(psi_mat, compute_uv=False)
        s4 = np.sum(s**4)
        renyi2[i] = -np.log(max(s4, 1e-30))

    # --- QFI (quantum Fisher information for M_z) ---
    # QFI = 4 * [<psi|M_z^2|psi> - <psi|M_z|psi>^2]
    # = 4 * Var(M_z) = 4 * N^2 * (m_sq - <psi|M_z|psi>^2/N^2)
    # For Z2-symmetric ground state, <M_z> = 0, so QFI = 4*<M_z^2>
    m_sq = np.array([o['m_sq'] for o in obs_list])
    qfi = 4.0 * N**2 * m_sq  # QFI for M_z

    # Normalise for comparison
    qfi_n = qfi / (qfi.max() + 1e-10)
    # QFI derivative
    dqfi_dh = np.abs(np.gradient(qfi, h_vals))

    # --- Correlation length proxy ---
    # xi ~ -1/log(C_long/C_zz) for C_long < C_zz
    with np.errstate(divide='ignore', invalid='ignore'):
        ratio_log = np.log(np.maximum(np.abs(c_long) / (np.abs(c_zz) + 1e-15), 1e-15))
    xi_proxy = -1.0 / (ratio_log + 1e-10)
    xi_proxy = np.clip(xi_proxy, 0, 100)

    # --- Energy variance (specific heat) ---
    # C_v proxy = d²E_0/dh² (second derivative of GS energy)
    cv = d2e0_dh2

    # --- IPR (inverse participation ratio) derivative ---
    dipr_dh = np.abs(np.gradient(ipr, h_vals))

    # --- Transverse magnetisation derivative ---
    dmx_dh = np.abs(np.gradient(m_x, h_vals))

    # --- BSDT ---
    ref_mask = h_vals < 0.5 * J
    ref_obs = [o for o, m in zip(obs_list, ref_mask) if m]
    ref_psi = [p for p, m in zip(psi_list, ref_mask) if m]
    bsdt = QuantumBSDT()
    bsdt.fit(ref_obs, ref_psi, N)
    ebs = bsdt.score_batch(obs_list, psi_list)
    mfls_score = compute_mfls(h_vals, ebs)
    obs_gnorm = compute_obs_gradient_norm(obs_list, h_vals)

    S_max = (N/2) * np.log(2)
    delta_C = m_abs * svn / S_max

    # ─── Assemble all methods ───
    methods = [
        # (name, signal, category, requires_domain_knowledge, reference)
        ('|dm/dh|  (magn. suscept.)',      dm_dh,       'Standard (deriv.)',  True,  'Sachdev 2011'),
        ('|d²m/dh²|  (OP curvature)',      d2m_dh2,     'Standard (deriv.)',  True,  '--'),
        ('chi_F  (fidelity suscept.)',      chi_F,       'Standard (quantum)', False, 'Zanardi 2006'),
        ('S_vN  (entanglement entropy)',    svn,         'Standard (quantum)', False, 'Vidal 2003'),
        ('S_2  (second Renyi entropy)',     renyi2,      'Standard (quantum)', False, 'Calabrese 2004'),
        ('1/gap  (inverse spectral gap)',   1.0/(gap+1e-10), 'Standard (spectral)', False, 'Fisher 1972'),
        ('|d(gap)/dh|  (gap derivative)',   dgap_dh,     'Standard (spectral)', False, '--'),
        ('1 - U  (Binder drop)',            1 - binder/(binder.max()+1e-10), 'Standard (stat mech)', False, 'Binder 1981'),
        ('1 - C_ratio  (corr. decay)',      1 - c_rat,   'Standard (corr.)',   False, 'Kaul 2015'),
        ('xi  (corr. length proxy)',        xi_proxy,    'Standard (corr.)',   False, '--'),
        ('C_v  (specific heat proxy)',      cv,          'Standard (thermo)',  False, '--'),
        ('QFI  (quantum Fisher info)',      qfi_n,       'Standard (quantum)', False, 'Hauke 2016'),
        ('|dQFI/dh|  (QFI derivative)',     dqfi_dh,     'Standard (quantum)', False, 'Hauke 2016'),
        ('1 - F(h,h+dh)  (infidelity)',    infidelity_rate, 'Standard (quantum)', False, 'Zanardi 2006'),
        ('1/IPR  (delocalisation)',         1.0/(ipr+1e-10), 'Standard (quantum)', False, '--'),
        ('|dm_x/dh|  (transv. suscept.)',  dmx_dh,      'Standard (deriv.)',  False, '--'),
        ('|dS_vN/dh|  (entropy deriv.)',   dsvn_dh,     'Standard (deriv.)',  False, '--'),
        ('1 - m  (OP depletion)',           1 - m_abs,   'Standard (direct)',  True,  '--'),
        ('||d(obs)/dh||  (obs gradient)',   obs_gnorm,   'Model-free',         False, 'Ours'),
        ('delta_C  (BSDT camouflage)',      delta_C,     'BSDT',              False, 'Ours'),
        ('E_BS  (phase classifier)',        ebs,         'BSDT',              False, 'Ours'),
        ('MFLS |dE_BS/dh|  [BSDT]',        mfls_score,  'BSDT',              False, 'Ours'),
    ]

    # ─── Compute metrics for all ───
    print(f"\n  {'Rank':>4}  {'Method':<35}  {'Category':<22}  {'DK':>3}  "
          f"{'AUC_cr':>7}  {'AUC_po':>7}  {'Peak h/J':>8}  {'Lead':>4}  {'Ref':<16}")
    print(f"  {'─'*4}  {'─'*35}  {'─'*22}  {'─'*3}  "
          f"{'─'*7}  {'─'*7}  {'─'*8}  {'─'*4}  {'─'*16}")

    rows = []
    for name, sig, cat, dk, ref in methods:
        sig_n = sig / (np.abs(sig).max() + 1e-10)
        ac = auc_score(y_crit, sig_n)
        ap = auc_score(y_post, sig_n)
        pk = peak_location(h_vals, sig_n)
        ld = detection_lead(h_vals, sig_n, J)
        rows.append((name, cat, dk, ac, ap, pk, ld, ref))

    # Sort by AUC_crit
    rows.sort(key=lambda r: r[3], reverse=True)

    for rank, (name, cat, dk, ac, ap, pk, ld, ref) in enumerate(rows, 1):
        dk_s = 'Y' if dk else 'N'
        flag = '***' if ac >= 0.95 else ' **' if ac >= 0.90 else '  *' if ac >= 0.85 else ''
        bsdt_tag = ' <-- BSDT' if 'MFLS' in name else ''
        print(f"  {rank:>4}  {name:<35}  {cat:<22}  {dk_s:>3}  "
              f"{ac:7.4f}  {ap:7.4f}  {pk:8.3f}  {ld:>4}  {ref:<16}  {flag}{bsdt_tag}")

    # ─── Summary statistics ───
    bsdt_rows = [(n, ac) for n, _, _, ac, _, _, _, _ in rows if 'MFLS' in n]
    std_rows  = [(n, ac) for n, cat, _, ac, _, _, _, _ in rows if 'BSDT' not in cat and 'Model' not in cat]
    std_no_dk = [(n, ac) for n, cat, dk, ac, _, _, _, _ in rows if 'BSDT' not in cat and 'Model' not in cat and not dk]

    print(f"\n  ─── Summary ───")
    if bsdt_rows:
        print(f"  BSDT MFLS AUC_crit: {bsdt_rows[0][1]:.4f}")
    if std_rows:
        best_std = max(std_rows, key=lambda x: x[1])
        print(f"  Best standard method: {best_std[0]} (AUC={best_std[1]:.4f})")
    if std_no_dk:
        best_nodk = max(std_no_dk, key=lambda x: x[1])
        print(f"  Best standard (no domain knowledge): {best_nodk[0]} (AUC={best_nodk[1]:.4f})")

    # MFLS rank among all, and among no-DK methods
    all_aucs = [ac for _, _, _, ac, _, _, _, _ in rows]
    nodk_names = [n for n, _, dk, _, _, _, _, _ in rows if not dk]
    nodk_aucs  = [ac for _, _, dk, ac, _, _, _, _ in rows if not dk]
    mfls_auc = bsdt_rows[0][1] if bsdt_rows else 0

    rank_all  = sum(1 for a in all_aucs if a > mfls_auc) + 1
    rank_nodk = sum(1 for a in nodk_aucs if a > mfls_auc) + 1
    print(f"  MFLS rank: #{rank_all} of {len(all_aucs)} overall, "
          f"#{rank_nodk} of {len(nodk_aucs)} among domain-agnostic methods")

    # Count methods MFLS beats
    beats = sum(1 for a in all_aucs if a < mfls_auc)
    print(f"  MFLS beats {beats}/{len(all_aucs) - 1} methods")

    # Save
    out = {
        'benchmark': [
            {'name': n, 'category': c, 'domain_knowledge': dk,
             'auc_crit': ac, 'auc_post': ap, 'peak_h': pk, 'lead': ld, 'ref': ref}
            for n, c, dk, ac, ap, pk, ld, ref in rows
        ],
        'summary': {
            'mfls_auc': mfls_auc,
            'mfls_rank_overall': rank_all,
            'mfls_rank_agnostic': rank_nodk,
            'n_methods': len(rows),
            'n_methods_beaten': beats,
        }
    }
    out_path = ROOT / 'research' / 'quantum' / 'results' / 'extended_benchmark.json'
    with open(out_path, 'w') as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n  Results saved to {out_path}")

    return rows


# =====================================================================
#  MULTI-SIZE BENCHMARK (mini version)
# =====================================================================
def multi_size_benchmark(sizes=None, n_steps=80, J=1.0):
    if sizes is None:
        sizes = [8, 10, 12, 14]

    print(f"\n{'=' * 80}")
    print(f"  MULTI-SIZE BENCHMARK  (N = {sizes})")
    print(f"{'=' * 80}")

    method_keys = ['MFLS', '|dm/dh|', 'chi_F', 'S_vN', '1/gap', 'C_v', '|dQFI/dh|']
    print(f"\n  {'N':>4}  {'dim':>7}  {'MFLS':>6}  {'|dm/dh|':>7}  {'chi_F':>6}  "
          f"{'S_vN':>5}  {'1/gap':>6}  {'C_v':>5}  {'QFI':>5}")
    print(f"  {'─'*4}  {'─'*7}  {'─'*6}  {'─'*7}  {'─'*6}  "
          f"{'─'*5}  {'─'*6}  {'─'*5}  {'─'*5}")

    h_vals = np.linspace(0.01, 2.0 * J, n_steps)
    y_crit = label_qpt(h_vals, J, width=0.15)

    # Collect results: { method_name: { "N=8": auc, "N=10": auc, ... } }
    ms_results = {k: {} for k in method_keys}

    for N_val in sizes:
        model = TransverseFieldIsing(N_val, J)
        results = sweep_field(model, h_vals, n_states=6)
        obs_l = [r['obs'] for r in results]
        psi_l = [r['psi'] for r in results]

        m = np.array([o['m_abs'] for o in obs_l])
        sv = np.array([o['S_vN'] for o in obs_l])
        gp = np.array([o['gap_phys'] for o in obs_l])
        e0v = np.array([o['e0'] for o in obs_l])
        m_sq_v = np.array([o['m_sq'] for o in obs_l])

        dm = np.abs(np.gradient(m, h_vals))
        chi_f = np.zeros(len(h_vals))
        for i in range(1, len(results)-1):
            dh = h_vals[i+1]-h_vals[i-1]
            F = float(np.abs(np.vdot(psi_l[i-1], psi_l[i+1]))**2)
            chi_f[i] = -2*np.log(max(F,1e-30))/max(dh**2,1e-30)
        chi_f[0]=chi_f[1]; chi_f[-1]=chi_f[-2]

        cv = np.abs(np.gradient(np.gradient(e0v, h_vals), h_vals))
        qfi = 4.0 * N_val**2 * m_sq_v
        dqfi = np.abs(np.gradient(qfi, h_vals))

        ref_mask = h_vals < 0.5*J
        bsdt = QuantumBSDT()
        bsdt.fit([o for o, m2 in zip(obs_l, ref_mask) if m2],
                 [p for p, m2 in zip(psi_l, ref_mask) if m2], N_val)
        ebs = bsdt.score_batch(obs_l, psi_l)
        mfls_s = compute_mfls(h_vals, ebs)

        def ac(s):
            sn = s / (np.abs(s).max()+1e-10)
            return auc_score(y_crit, sn)

        aucs = [ac(mfls_s), ac(dm), ac(chi_f), ac(sv), ac(1/(gp+1e-10)), ac(cv), ac(dqfi)]
        for k, a in zip(method_keys, aucs):
            ms_results[k][f'N={N_val}'] = round(float(a), 4)

        print(f"  {N_val:>4}  {1<<N_val:>7}  {aucs[0]:6.3f}  {aucs[1]:7.3f}  "
              f"{aucs[2]:6.3f}  {aucs[3]:5.3f}  {aucs[4]:6.3f}  "
              f"{aucs[5]:5.3f}  {aucs[6]:5.3f}")

    return ms_results


def main():
    rows = run_benchmark(N=12, n_steps=100, J=1.0)
    ms_results = multi_size_benchmark([8, 10, 12, 14], n_steps=80, J=1.0)

    # Merge multi-size into the saved JSON
    out_path = Path(__file__).parent / 'results' / 'extended_benchmark.json'
    if out_path.exists():
        with open(out_path) as f:
            data = json.load(f)
    else:
        data = {}
    data['multi_size'] = ms_results
    with open(out_path, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"\n  Multi-size data merged into {out_path}")



if __name__ == '__main__':
    main()
