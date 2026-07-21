"""
CHB-MIT Per-Channel Collapse Signature
=======================================
Applies three engines to every EEG channel individually:
  1. MolecularEngine (Lennard-Jones physics)     — full 207-dim
  2. GravityModeEngine (N-body physics)          — full 207-dim
  3. BSDTChannels (trading BSDT)                 — per EEG channel (9-dim each)

Visualisations (1-D → 4-D):
  1-D  global score time-series (3 engines, seizure onset marked)
  2-D  per-channel score heat-map + BSDT δ_C / δ_G / δ_A / δ_T breakdown
  3-D  PCA of per-channel BSDT score matrix coloured by phase label
  4-D  same 3-D + time-as-colour + alarm size + collapse-star markers
  +    channel ranking bar-chart + delta-breakdown stacked bar

Author: Copilot – May 2026
"""

import sys, os, gc, time, warnings
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.metrics import roc_auc_score
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from mpl_toolkits.mplot3d import Axes3D   # noqa: F401

warnings.filterwarnings("ignore")

# ── paths ──────────────────────────────────────────────────────────────────
ROOT      = r"C:\amttp"
UDL_PATH  = os.path.join(ROOT, "research", "udl")
EEG_DIR   = os.path.join(ROOT, "data", "external_validation", "eeg")
PLOTDIR   = os.path.join(ROOT, "research", "neural-stability", "results", "channel_plots")
os.makedirs(PLOTDIR, exist_ok=True)

CHB_REF_EDF  = os.path.join(EEG_DIR, "chb01_01.edf")
CHB_TEST_EDF = os.path.join(EEG_DIR, "chb01_03.edf")
ONSET_S      = 2996.0
OFFSET_S     = 3036.0
REF_DUR_S    = 120.0
SFREQ_TGT    = 64
WIN_S        = 4
STRIDE_S     = 1

sys.path.insert(0, UDL_PATH)
from udl.system_mode import MolecularEngine, GravityModeEngine, BSDTChannels

# ── dark-theme constants ───────────────────────────────────────────────────
DARK_BG  = "#0d1117"
PANEL_BG = "#161b22"
GRID_CLR = "#30363d"
TEXT_CLR = "#e6edf3"
CMAP_HOT = "inferno"
CMAP_DIV = "RdYlBu_r"

PHASE_COLORS = {
    "interictal": "#60a5fa",
    "pre-ictal":  "#f59e0b",
    "ictal":      "#ef4444",
}


def _fig(w=16, h=9):
    fig = plt.figure(figsize=(w, h), facecolor=DARK_BG)
    return fig


def _ax(fig, *args, **kw):
    ax = fig.add_subplot(*args, **kw)
    ax.set_facecolor(PANEL_BG)
    ax.tick_params(colors=TEXT_CLR, labelsize=7)
    ax.xaxis.label.set_color(TEXT_CLR)
    ax.yaxis.label.set_color(TEXT_CLR)
    ax.title.set_color(TEXT_CLR)
    for sp in ax.spines.values():
        sp.set_edgecolor(GRID_CLR)
    ax.grid(color=GRID_CLR, lw=0.4, alpha=0.5)
    return ax


def _ax3d(fig, *args, **kw):
    ax = fig.add_subplot(*args, projection="3d", **kw)
    ax.set_facecolor(PANEL_BG)
    ax.xaxis.pane.fill = False; ax.yaxis.pane.fill = False; ax.zaxis.pane.fill = False
    ax.xaxis.pane.set_edgecolor(GRID_CLR)
    ax.yaxis.pane.set_edgecolor(GRID_CLR)
    ax.zaxis.pane.set_edgecolor(GRID_CLR)
    ax.tick_params(colors=TEXT_CLR, labelsize=7)
    ax.xaxis.label.set_color(TEXT_CLR); ax.yaxis.label.set_color(TEXT_CLR)
    ax.zaxis.label.set_color(TEXT_CLR); ax.title.set_color(TEXT_CLR)
    return ax


def _draw_ellipsoid(ax, lambdas, center=None, q=0.90, n_theta=20, n_phi=20, **kw):
    from scipy.stats import chi2 as scipy_chi2
    if center is None: center = np.zeros(3)
    r2    = float(scipy_chi2.ppf(q, df=3))
    radii = np.sqrt(r2 * np.maximum(lambdas[:3], 1e-10))
    th    = np.linspace(0, np.pi, n_theta)
    ph    = np.linspace(0, 2 * np.pi, n_phi)
    TH, PH = np.meshgrid(th, ph)
    Xw = radii[0] * np.sin(TH) * np.cos(PH) + center[0]
    Yw = radii[1] * np.sin(TH) * np.sin(PH) + center[1]
    Zw = radii[2] * np.cos(TH)              + center[2]
    return ax.plot_wireframe(Xw, Yw, Zw, **kw)


def _save(fig, name):
    path = os.path.join(PLOTDIR, name)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(path, dpi=120, bbox_inches="tight",
                facecolor=DARK_BG, edgecolor="none")
    plt.close(fig)
    print(f"  Saved -> {path}")


# ══════════════════════════════════════════════════════════════════════════
# EDF loading (pure-Python, from test_physics_engine_chbmit.py)
# ══════════════════════════════════════════════════════════════════════════
_EDF_WIDTHS = [16, 80, 8, 8, 8, 8, 8, 80, 8, 32]
_EDF_FNAMES = ['label', 'transducer', 'phys_dim', 'phys_min', 'phys_max',
               'dig_min', 'dig_max', 'prefilter', 'nsamples', 'reserved']
_EPS = 1e-10


def _read_edf_raw(path, start_s=0.0, end_s=1e9, max_channels=23):
    with open(path, "rb") as fh:
        hdr          = fh.read(256)
        nr_records   = int(hdr[236:244].strip())
        rec_duration = float(hdr[244:252].strip())
        ns_total     = int(hdr[252:256].strip())
        sig_hdr      = fh.read(ns_total * 256)
        ns           = min(ns_total, max_channels)

        def _get(fn, si):
            fi   = _EDF_FNAMES.index(fn)
            base = sum(_EDF_WIDTHS[:fi]) * ns_total + si * _EDF_WIDTHS[fi]
            return sig_hdr[base: base + _EDF_WIDTHS[fi]].decode(errors="replace").strip()

        def _sf(fn, si, d=0.0):
            try: return float(_get(fn, si))
            except: return d

        def _si(fn, si, d=256):
            try: return int(_get(fn, si))
            except: return d

        labels   = [_get('label', i) for i in range(ns)]
        physmin  = np.array([_sf('phys_min', i, -32768.) for i in range(ns)])
        physmax  = np.array([_sf('phys_max', i,  32767.) for i in range(ns)])
        digmin   = np.array([_sf('dig_min',  i, -32768.) for i in range(ns)])
        digmax   = np.array([_sf('dig_max',  i,  32767.) for i in range(ns)])
        nsamples = np.array([_si('nsamples', i, 256) for i in range(ns_total)])
        sfreq    = float(nsamples[0]) / rec_duration
        gain     = (physmax - physmin) / (digmax - digmin + _EPS)
        off_cal  = physmin - digmin * gain

        hdr_bytes        = 256 + ns_total * 256
        bytes_per_record = int(np.sum(nsamples)) * 2
        start_rec = max(0, int(start_s / rec_duration))
        end_rec   = min(nr_records, int(np.ceil(end_s / rec_duration)))
        n_recs    = end_rec - start_rec
        fh.seek(hdr_bytes + start_rec * bytes_per_record)
        chunks = []
        for _ in range(n_recs):
            rec_ch = []
            for i in range(ns_total):
                n_samp = max(0, int(nsamples[i]))
                raw = np.frombuffer(fh.read(n_samp * 2), dtype=np.int16)
                if i < ns:
                    rec_ch.append(raw.astype(np.float64) * gain[i] + off_cal[i])
            chunks.append(rec_ch)

    X = np.concatenate([np.stack(chunks[r], axis=-1) for r in range(n_recs)], axis=0)
    s0 = int((start_s - start_rec * rec_duration) * sfreq)
    s1 = s0 + int((end_s - start_s) * sfreq)
    X  = X[s0: min(s1, X.shape[0])]
    return X, labels, float(sfreq)


def _decimate(data, factor):
    if factor == 1: return data
    k   = np.ones(factor) / factor
    out = np.apply_along_axis(lambda x: np.convolve(x, k, mode='same'), 0, data)
    return out[::factor]


def load_edf(path, target_sf=64, max_dur=None):
    end_s = max_dur if max_dur else 1e9
    data, labels, sf = _read_edf_raw(path, 0, end_s)
    native = int(round(sf))
    if native > target_sf:
        factor = native // target_sf
        if factor > 1:
            data = _decimate(data, factor)
    return data, target_sf, labels


# ══════════════════════════════════════════════════════════════════════════
# Feature extraction
# ══════════════════════════════════════════════════════════════════════════
def _band_power(x, sf, lo, hi):
    n = len(x)
    if n < 8: return 0.0
    f = np.fft.rfftfreq(n, 1.0 / sf)
    p = np.abs(np.fft.rfft(x)) ** 2
    m = (f >= lo) & (f < hi)
    return float(p[m].mean()) if m.any() else 0.0


def extract_features(data, sf, win_samp, stride_samp):
    """Returns (n_windows, n_ch * 9)."""
    n_samp, n_ch = data.shape
    starts  = np.arange(0, n_samp - win_samp + 1, stride_samp)
    n_win   = len(starts)
    X       = np.zeros((n_win, n_ch * 9), dtype=np.float32)
    for wi, st in enumerate(starts):
        seg = data[st: st + win_samp]
        for ci in range(n_ch):
            x   = seg[:, ci].astype(np.float64)
            off = ci * 9
            X[wi, off + 0] = float(x.mean())
            X[wi, off + 1] = float(x.std() + 1e-10)
            X[wi, off + 2] = float(np.log(x.var() + 1e-10))
            X[wi, off + 3] = float(np.mean(np.abs(np.diff(x))))
            X[wi, off + 4] = _band_power(x, sf, 0.5,  4.0)
            X[wi, off + 5] = _band_power(x, sf, 4.0,  8.0)
            X[wi, off + 6] = _band_power(x, sf, 8.0, 13.0)
            X[wi, off + 7] = _band_power(x, sf, 13., 30.0)
            X[wi, off + 8] = _band_power(x, sf, 30., 49.0)
    return X  # (n_win, n_ch * 9)


def window_times_labels(n_win, stride_samp, sf):
    centres = (np.arange(n_win) * stride_samp + WIN_S * sf / 2) / sf
    y = ((centres >= ONSET_S) & (centres <= OFFSET_S)).astype(int)
    # Phase: interictal / pre-ictal (last 300 s before onset) / ictal
    phase = np.array(["interictal"] * n_win, dtype=object)
    phase[(centres >= ONSET_S - 300) & (y == 0)] = "pre-ictal"
    phase[y == 1] = "ictal"
    return centres, y, phase


# ══════════════════════════════════════════════════════════════════════════
# Collapse-signature metrics
# ══════════════════════════════════════════════════════════════════════════
def collapse_metrics(scores, y, centres):
    im  = y == 1;  nm = y == 0
    mi  = float(scores[im].mean()) if im.any()  else 0.0
    mn  = float(scores[nm].mean()) if nm.any()  else 1e-9
    disc = mi / (mn + 1e-10)
    try:
        auroc = float(roc_auc_score(y, scores)) if im.any() and nm.any() else float("nan")
    except Exception:
        auroc = float("nan")
    # Lead time: first time rolling-60s score > 2× background
    roll_w  = max(1, 60 // STRIDE_S)
    rolling = np.convolve(scores, np.ones(roll_w) / roll_w, mode="full")[:len(scores)]
    bkg_thr = 2.0 * float(rolling[nm].mean()) if nm.any() else 0.0
    lead    = float("nan")
    for i in range(len(rolling)):
        if rolling[i] >= bkg_thr and centres[i] < ONSET_S:
            lead = ONSET_S - centres[i]
    return dict(disc=disc, auroc=auroc, lead_s=lead)


# ══════════════════════════════════════════════════════════════════════════
# LOAD DATA
# ══════════════════════════════════════════════════════════════════════════
print("=" * 70)
print("  CHB-MIT PER-CHANNEL COLLAPSE SIGNATURE")
print("  Engines: MolecularEngine | GravityModeEngine | BSDTChannels")
print("=" * 70)

print("\n  Loading EDF files …")
data_ref,  sf_ref,  lbl_ref  = load_edf(CHB_REF_EDF,  SFREQ_TGT, max_dur=REF_DUR_S)
data_test, sf_test, lbl_test = load_edf(CHB_TEST_EDF, SFREQ_TGT)

n_ch       = data_test.shape[1]
ch_labels  = [l.strip() for l in lbl_test[:n_ch]]
win_samp   = WIN_S  * SFREQ_TGT
str_samp   = STRIDE_S * SFREQ_TGT

print(f"  Reference: {data_ref.shape[0]} samples ({REF_DUR_S:.0f}s)  "
      f"channels: {n_ch}")
print(f"  Test:      {data_test.shape[0]} samples "
      f"({data_test.shape[0]/SFREQ_TGT:.0f}s)  seizure: {ONSET_S:.0f}s–{OFFSET_S:.0f}s")

# Full feature matrices
print("  Extracting features …")
F_ref  = extract_features(data_ref[:, :n_ch],  SFREQ_TGT, win_samp, str_samp).astype(np.float64)
F_test = extract_features(data_test[:, :n_ch], SFREQ_TGT, win_samp, str_samp).astype(np.float64)

n_ref  = len(F_ref)
n_test = len(F_test)
centres, y_all, phase_all = window_times_labels(n_test, str_samp, SFREQ_TGT)

print(f"  Reference windows: {n_ref}  |  Test windows: {n_test}")
print(f"  Ictal windows: {int((y_all==1).sum())}  "
      f"Pre-ictal (300s): {int((phase_all=='pre-ictal').sum())}  "
      f"Interictal: {int((phase_all=='interictal').sum())}")


# ══════════════════════════════════════════════════════════════════════════
# ENGINE 1 & 2: MolecularEngine + GravityModeEngine (full 207-dim)
# ══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("  ENGINE 1/2: MolecularEngine + GravityModeEngine (207-dim)")
print("=" * 70)

F_all  = np.vstack([F_ref, F_test])
y_full = np.concatenate([np.zeros(n_ref, dtype=int), y_all])

global_scores = {}
for eng_name, EngClass in [("Molecular", MolecularEngine),
                            ("Gravity",   GravityModeEngine)]:
    gc.collect()
    print(f"\n  [{eng_name}] fitting + scoring …")
    t0  = time.time()
    eng = EngClass(iterations=50, k_neighbors=15, max_samples=1500, use_fused=True)
    sc_all = eng.fit_score(F_all, y_full)
    sc_test = sc_all[n_ref:]
    # Normalise to [0,1]
    sc_test = (sc_test - sc_test.min()) / (np.ptp(sc_test) + 1e-10)
    m = collapse_metrics(sc_test, y_all, centres)
    elapsed = time.time() - t0
    print(f"    disc={m['disc']:.2f}x  AUROC={m['auroc']:.4f}  "
          f"lead={m['lead_s']:.1f}s  elapsed={elapsed:.1f}s")
    global_scores[eng_name] = dict(scores=sc_test, **m)


# ══════════════════════════════════════════════════════════════════════════
# ENGINE 3: BSDTChannels — per EEG channel (9-dim each)
# ══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("  ENGINE 3: BSDTChannels — per EEG channel (9 features each)")
print("=" * 70)

# Per-channel score matrix: (n_test, n_ch)
bsdt_scores_ch  = np.zeros((n_test,  n_ch))   # BSDT score per channel
bsdt_delta_C    = np.zeros((n_test,  n_ch))
bsdt_delta_G    = np.zeros((n_test,  n_ch))
bsdt_delta_A    = np.zeros((n_test,  n_ch))
bsdt_delta_T    = np.zeros((n_test,  n_ch))
ch_metrics      = []

t0_bsdt = time.time()
for ci in range(n_ch):
    off = ci * 9
    Xr  = F_ref[:, off: off + 9].astype(np.float64)
    Xt  = F_test[:, off: off + 9].astype(np.float64)

    # Standardise using reference stats
    sc  = StandardScaler().fit(Xr)
    Xr_s = sc.transform(Xr)
    Xt_s  = sc.transform(Xt)

    bsdt = BSDTChannels(k=min(10, n_ref - 1))
    bsdt.fit(Xr_s)

    sc_ch = bsdt.score(Xt_s)                    # (n_test,) in [0,1]
    ch_d  = bsdt.channels(Xt_s)

    bsdt_scores_ch[:, ci] = sc_ch
    bsdt_delta_C[:, ci]   = ch_d["delta_C"]
    bsdt_delta_G[:, ci]   = ch_d["delta_G"]
    bsdt_delta_A[:, ci]   = ch_d["delta_A"]
    bsdt_delta_T[:, ci]   = ch_d["delta_T"]

    m = collapse_metrics(sc_ch, y_all, centres)
    ch_metrics.append(dict(ch=ci, label=ch_labels[ci], **m))

    if ci % 5 == 0 or ci == n_ch - 1:
        print(f"  ch {ci+1:2d}/{n_ch} {ch_labels[ci]:12s}  "
              f"disc={m['disc']:.2f}x  AUROC={m['auroc']:.4f}")

elapsed_bsdt = time.time() - t0_bsdt
print(f"\n  BSDTChannels elapsed: {elapsed_bsdt:.1f}s")

# Global BSDT score = mean across channels
bsdt_global = bsdt_scores_ch.mean(axis=1)
bsdt_global = (bsdt_global - bsdt_global.min()) / (np.ptp(bsdt_global) + 1e-10)
m_bsdt = collapse_metrics(bsdt_global, y_all, centres)
global_scores["BSDT"] = dict(scores=bsdt_global, **m_bsdt)
print(f"\n  BSDT (mean-channel) disc={m_bsdt['disc']:.2f}x  "
      f"AUROC={m_bsdt['auroc']:.4f}  lead={m_bsdt['lead_s']:.1f}s")

# Sort channels by disc ratio
ch_sorted = sorted(ch_metrics, key=lambda x: x['disc'], reverse=True)
top5   = ch_sorted[:5]
bot5   = ch_sorted[-5:]
top5_idx = [x['ch'] for x in top5]

print("\n  Top-5 collapse channels (disc ratio):")
for x in top5:
    print(f"    [{x['ch']:2d}] {x['label']:12s}  disc={x['disc']:.2f}x  "
          f"AUROC={x['auroc']:.4f}  lead={x['lead_s']:.1f}s")
print("  Bottom-5:")
for x in bot5:
    print(f"    [{x['ch']:2d}] {x['label']:12s}  disc={x['disc']:.2f}x  "
          f"AUROC={x['auroc']:.4f}  lead={x['lead_s']:.1f}s")


# ══════════════════════════════════════════════════════════════════════════
# PCA on per-channel score matrix (n_test × n_ch) for 3D/4D
# ══════════════════════════════════════════════════════════════════════════
print("\n  Computing PCA on per-channel BSDT score matrix …")
sc_norm = StandardScaler().fit_transform(bsdt_scores_ch)
pca4    = PCA(n_components=min(4, n_ch)).fit(sc_norm)
Z4      = pca4.transform(sc_norm)   # (n_test, ≤4)
lam3    = pca4.explained_variance_[:3]

# Reference cloud in this PCA space (normal interictal windows)
ref_idx = phase_all == "interictal"
ctr3    = Z4[ref_idx, :3].mean(axis=0)


# ══════════════════════════════════════════════════════════════════════════
# PLOTTING
# ══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("  PLOTTING 1-D / 2-D / 3-D / 4-D")
print("=" * 70)

phase_cmap = {
    "interictal": "#60a5fa",
    "pre-ictal":  "#f59e0b",
    "ictal":      "#ef4444",
}

# ─────────────────────────────────────────────────────────────────────────
# PLOT 1  ·  1-D global score time series (3 engines)
# ─────────────────────────────────────────────────────────────────────────
print("\n  [1/7] channel_1d_global_scores.png …")
fig = _fig(18, 11)
fig.suptitle("CHB-MIT chb01_03 — 1-D Score Time Series  "
             "[ MolecularEngine | GravityModeEngine | BSDTChannels ]",
             color=TEXT_CLR, fontsize=13, fontweight="bold")

for pi, (eng, meta) in enumerate(global_scores.items(), 1):
    ax = _ax(fig, 3, 1, pi)
    sc = meta["scores"]
    ax.set_title(f"{eng}  |  disc={meta['disc']:.2f}×  AUROC={meta['auroc']:.4f}  "
                 f"lead={meta['lead_s']:.1f}s",
                 color=TEXT_CLR, fontsize=10)
    ax.plot(centres, sc, lw=0.7, color="#60a5fa", alpha=0.85)
    ax.axvline(ONSET_S, color="#ef4444", lw=1.5, ls="--", label="seizure onset")
    ax.axvline(OFFSET_S, color="#f59e0b", lw=1.0, ls="--", alpha=0.8, label="seizure offset")
    # Pre-ictal band
    ax.axvspan(ONSET_S - 300, ONSET_S, alpha=0.10, color="#f59e0b")
    # Ictal band
    ax.axvspan(ONSET_S, OFFSET_S, alpha=0.20, color="#ef4444")
    ax.set_xlabel("Time (s)", fontsize=8)
    ax.set_ylabel("Score (norm)", fontsize=8)
    if pi == 1:
        ax.legend(fontsize=8, framealpha=0.3, labelcolor=TEXT_CLR,
                  facecolor=PANEL_BG, edgecolor=GRID_CLR)

_save(fig, "channel_1d_global_scores.png")


# ─────────────────────────────────────────────────────────────────────────
# PLOT 2  ·  1-D per-channel BSDT score trajectories (top-5 + bottom-5)
# ─────────────────────────────────────────────────────────────────────────
print("  [2/7] channel_1d_perchannel.png …")
fig = _fig(18, 12)
fig.suptitle("CHB-MIT — 1-D Per-Channel BSDT Score Trajectories  "
             "(top-5 collapse vs bottom-5)",
             color=TEXT_CLR, fontsize=13, fontweight="bold")

gs = gridspec.GridSpec(5, 2, figure=fig, hspace=0.55, wspace=0.3)
cmap_ch = plt.get_cmap("tab10")
for row in range(5):
    for col, (x_list, title_pfx) in enumerate([
        (top5,  "TOP"),
        (bot5,  "BOT"),
    ]):
        entry = x_list[row]
        ci    = entry['ch']
        ax    = fig.add_subplot(gs[row, col])
        ax.set_facecolor(PANEL_BG)
        ax.tick_params(colors=TEXT_CLR, labelsize=7)
        for sp in ax.spines.values(): sp.set_edgecolor(GRID_CLR)
        ax.grid(color=GRID_CLR, lw=0.3, alpha=0.4)
        sc_ci = bsdt_scores_ch[:, ci]
        ax.plot(centres, sc_ci, lw=0.7, color=cmap_ch(row / 5), alpha=0.9)
        ax.axvline(ONSET_S, color="#ef4444", lw=1.2, ls="--")
        ax.axvspan(ONSET_S, OFFSET_S, alpha=0.25, color="#ef4444")
        ax.axvspan(ONSET_S - 300, ONSET_S, alpha=0.10, color="#f59e0b")
        ax.set_title(
            f"{title_pfx} [{ci}] {entry['label']}  disc={entry['disc']:.2f}x  "
            f"AUROC={entry['auroc']:.3f}",
            color=TEXT_CLR, fontsize=8)
        ax.set_xlabel("Time (s)", fontsize=7)
        ax.set_ylabel("Score", fontsize=7)

_save(fig, "channel_1d_perchannel.png")


# ─────────────────────────────────────────────────────────────────────────
# PLOT 3  ·  2-D heat-map: time × channel (BSDT score)
# ─────────────────────────────────────────────────────────────────────────
print("  [3/7] channel_2d_heatmap.png …")
fig = _fig(18, 12)
fig.suptitle("CHB-MIT — 2-D Score Heat-Maps  (time × channel)",
             color=TEXT_CLR, fontsize=13, fontweight="bold")

# Sort channels by disc for display
sort_idx = [x['ch'] for x in ch_sorted]
hm_data  = bsdt_scores_ch[:, sort_idx].T   # (n_ch, n_test)
sorted_lbl = [ch_sorted[i]['label'] for i in range(n_ch)]

# Down-sample time axis for display if too many windows
max_cols = 600
step = max(1, n_test // max_cols)
hm_disp = hm_data[:, ::step]
t_disp  = centres[::step]

# Panel 1: BSDT per-channel heatmap
ax1 = _ax(fig, 2, 2, 1)
im1 = ax1.imshow(hm_disp, aspect="auto", cmap=CMAP_HOT,
                 extent=[t_disp[0], t_disp[-1], n_ch - 0.5, -0.5],
                 vmin=0, vmax=1)
ax1.set_yticks(range(n_ch))
ax1.set_yticklabels(sorted_lbl, fontsize=5)
ax1.axvline(ONSET_S, color="#00ffff", lw=1.5, ls="--", label="onset")
ax1.set_xlabel("Time (s)", fontsize=8); ax1.set_ylabel("Channel (sorted by disc)", fontsize=8)
ax1.set_title("BSDT Score  (channels ranked by disc ratio)", color=TEXT_CLR, fontsize=10)
fig.colorbar(im1, ax=ax1, pad=0.01).set_label("Score", color=TEXT_CLR, fontsize=8)
ax1.tick_params(colors=TEXT_CLR, labelsize=6)

# Panel 2: delta_A heatmap (activity anomaly = most sensitive to ictal)
hm_dA    = bsdt_delta_A[:, sort_idx].T[:, ::step]
ax2 = _ax(fig, 2, 2, 2)
im2 = ax2.imshow(hm_dA, aspect="auto", cmap="plasma",
                 extent=[t_disp[0], t_disp[-1], n_ch - 0.5, -0.5],
                 vmin=0, vmax=1)
ax2.set_yticks(range(n_ch))
ax2.set_yticklabels(sorted_lbl, fontsize=5)
ax2.axvline(ONSET_S, color="#00ffff", lw=1.5, ls="--")
ax2.set_xlabel("Time (s)", fontsize=8); ax2.set_ylabel("Channel", fontsize=8)
ax2.set_title("BSDT delta_A  (Activity Anomaly = Mahalanobis departure)", color=TEXT_CLR, fontsize=10)
fig.colorbar(im2, ax=ax2, pad=0.01).set_label("delta_A", color=TEXT_CLR, fontsize=8)
ax2.tick_params(colors=TEXT_CLR, labelsize=6)

# Panel 3: Molecular engine score heatmap vs BSDT global
ax3 = _ax(fig, 2, 2, 3)
ax3.set_title("Global Score Time Series: all 3 engines", color=TEXT_CLR, fontsize=10)
ax3.set_xlabel("Time (s)", fontsize=8); ax3.set_ylabel("Score (norm)", fontsize=8)
colors_eng = {"Molecular": "#60a5fa", "Gravity": "#34d399", "BSDT": "#f59e0b"}
for eng_n, meta in global_scores.items():
    ax3.plot(centres, meta["scores"], lw=0.9, alpha=0.85,
             color=colors_eng[eng_n], label=eng_n)
ax3.axvline(ONSET_S, color="#ef4444", lw=1.5, ls="--", label="onset")
ax3.axvspan(ONSET_S, OFFSET_S, alpha=0.25, color="#ef4444")
ax3.axvspan(ONSET_S - 300, ONSET_S, alpha=0.10, color="#f59e0b")
ax3.legend(fontsize=8, framealpha=0.3, labelcolor=TEXT_CLR,
           facecolor=PANEL_BG, edgecolor=GRID_CLR)

# Panel 4: Channel disc ratio bar chart
disc_vals = np.array([x['disc'] for x in ch_sorted])
auroc_vals = np.array([x['auroc'] for x in ch_sorted])
x_pos      = np.arange(n_ch)
ax4 = _ax(fig, 2, 2, 4)
bar_colors = plt.cm.plasma(disc_vals / (disc_vals.max() + 1e-10))
ax4.bar(x_pos, disc_vals, color=bar_colors, alpha=0.85)
ax4.set_xticks(x_pos[::2])
ax4.set_xticklabels([ch_sorted[i]['label'] for i in range(0, n_ch, 2)],
                    rotation=45, ha="right", fontsize=5)
ax4.set_xlabel("Channel (sorted by disc)", fontsize=8)
ax4.set_ylabel("Discrimination ratio (disc)", fontsize=8)
ax4.set_title("Per-Channel Collapse Discrimination (BSDT)", color=TEXT_CLR, fontsize=10)
ax4.axhline(1.0, color="#ffffff", ls="--", lw=0.8, alpha=0.5, label="baseline=1")
ax4.legend(fontsize=7, framealpha=0.3, labelcolor=TEXT_CLR,
           facecolor=PANEL_BG, edgecolor=GRID_CLR)

_save(fig, "channel_2d_heatmap.png")


# ─────────────────────────────────────────────────────────────────────────
# PLOT 4  ·  2-D BSDT 4-channel breakdown (delta_C / G / A / T stacked)
# ─────────────────────────────────────────────────────────────────────────
print("  [4/7] channel_2d_delta_breakdown.png …")
fig = _fig(18, 10)
fig.suptitle("CHB-MIT — 2-D BSDT Channel Breakdown  "
             "[ delta_C | delta_G | delta_A | delta_T ]  per EEG channel",
             color=TEXT_CLR, fontsize=13, fontweight="bold")

delta_maps = [
    ("delta_C", bsdt_delta_C, "Camouflage (centroid proximity)"),
    ("delta_G", bsdt_delta_G, "Feature Gap (near-zero features)"),
    ("delta_A", bsdt_delta_A, "Activity Anomaly (Mahalanobis)"),
    ("delta_T", bsdt_delta_T, "Temporal Novelty (kNN distance)"),
]
delta_cmaps = ["Blues_r", "Greens_r", "Reds", "Oranges"]

for pi, (dname, dmat, dtitle) in enumerate(delta_maps, 1):
    ax = _ax(fig, 2, 2, pi)
    hm = dmat[:, sort_idx].T[:, ::step]
    im = ax.imshow(hm, aspect="auto", cmap=delta_cmaps[pi - 1],
                   extent=[t_disp[0], t_disp[-1], n_ch - 0.5, -0.5],
                   vmin=0, vmax=1)
    ax.set_yticks(range(n_ch))
    ax.set_yticklabels(sorted_lbl, fontsize=5)
    ax.axvline(ONSET_S, color="#00ffff", lw=1.5, ls="--", label="onset")
    ax.set_xlabel("Time (s)", fontsize=8)
    ax.set_ylabel("Channel (ranked by disc)", fontsize=8)
    ax.set_title(f"{dname}  —  {dtitle}", color=TEXT_CLR, fontsize=9)
    cb = fig.colorbar(im, ax=ax, pad=0.01)
    cb.set_label(dname, color=TEXT_CLR, fontsize=8)
    cb.ax.yaxis.set_tick_params(labelcolor=TEXT_CLR)
    ax.tick_params(colors=TEXT_CLR, labelsize=6)

_save(fig, "channel_2d_delta_breakdown.png")


# ─────────────────────────────────────────────────────────────────────────
# PLOT 5  ·  3-D PCA of per-channel score matrix
#            Each point = one time window, coords = PC1/2/3 of (23,) score vec
#            Colour = phase label  |  Reference ellipsoid = interictal cloud
# ─────────────────────────────────────────────────────────────────────────
print("  [5/7] channel_3d_pca.png …")
fig = _fig(14, 10)
fig.suptitle("CHB-MIT — 3-D PCA of Channel-Score Space  (23-channel BSDT)\n"
             "Each point = one 1-second window  ·  cyan ellipsoid = interictal C*",
             color=TEXT_CLR, fontsize=12, fontweight="bold")

ax3d = _ax3d(fig, 1, 1, 1)

# Reference (interictal) cloud
ref_cloud = Z4[ref_idx, :3]
ax3d.scatter(ref_cloud[:, 0], ref_cloud[:, 1], ref_cloud[:, 2],
             c="#40e0d0", s=4, alpha=0.3, depthshade=True, label="interictal ref")
_draw_ellipsoid(ax3d, lam3, center=ctr3, q=0.90,
                color="#40e0d0", alpha=0.15, linewidth=0.5,
                rstride=3, cstride=3, zorder=1)

# Pre-ictal and ictal
for phase_lbl, col, siz in [("pre-ictal", "#f59e0b", 12), ("ictal", "#ef4444", 25)]:
    pm = phase_all == phase_lbl
    if pm.any():
        ax3d.scatter(Z4[pm, 0], Z4[pm, 1], Z4[pm, 2],
                     c=col, s=siz, alpha=0.9, depthshade=True,
                     label=phase_lbl, zorder=5)

ax3d.set_xlabel("PC1", fontsize=8); ax3d.set_ylabel("PC2", fontsize=8)
ax3d.set_zlabel("PC3", fontsize=8)
ev_ratio = pca4.explained_variance_ratio_[:3]
ax3d.set_title(f"PC1={ev_ratio[0]:.1%}  PC2={ev_ratio[1]:.1%}  "
               f"PC3={ev_ratio[2]:.1%}  of variance",
               color=TEXT_CLR, fontsize=9)
ax3d.legend(fontsize=9, framealpha=0.3, labelcolor=TEXT_CLR,
            facecolor=PANEL_BG, edgecolor=GRID_CLR, loc="upper left")

_save(fig, "channel_3d_pca.png")


# ─────────────────────────────────────────────────────────────────────────
# PLOT 6  ·  4-D  PC1/PC2/PC3 + time-as-colour + alarm-size + phase markers
# ─────────────────────────────────────────────────────────────────────────
print("  [6/7] channel_4d_collapse.png …")
fig = _fig(14, 10)
fig.suptitle("CHB-MIT — 4-D Collapse Visualisation\n"
             "PC1/PC2/PC3  ·  colour = time  ·  size = BSDT score  ·  stars = phase",
             color=TEXT_CLR, fontsize=12, fontweight="bold")

ax4d = _ax3d(fig, 1, 1, 1)

# Reference ellipsoid
_draw_ellipsoid(ax4d, lam3, center=ctr3, q=0.90,
                color="#40e0d0", alpha=0.12, linewidth=0.4,
                rstride=3, cstride=3, zorder=1)
ax4d.scatter(ref_cloud[:, 0], ref_cloud[:, 1], ref_cloud[:, 2],
             c="#40e0d0", s=3, alpha=0.25, depthshade=True)

# All windows: colour = time (4th dim), size = BSDT global score
t_n    = (centres - centres.min()) / (np.ptp(centres) + 1e-10)
sizes4 = 8 + bsdt_global * 80
sc4d   = ax4d.scatter(Z4[:, 0], Z4[:, 1], Z4[:, 2],
                      c=t_n, cmap="viridis",
                      s=sizes4, alpha=0.55, depthshade=True, zorder=2)

# Phase markers
for phase_lbl, col, mkr, siz in [
    ("pre-ictal", "#f59e0b", "^", 60),
    ("ictal",     "#ef4444", "*", 120),
]:
    pm = phase_all == phase_lbl
    if pm.any():
        ax4d.scatter(Z4[pm, 0], Z4[pm, 1], Z4[pm, 2],
                     c=col, s=siz, marker=mkr, alpha=0.95,
                     label=phase_lbl, depthshade=False, zorder=6)

# Trajectory line through channel-score space
line_step = max(1, n_test // 400)
for i in range(0, n_test - line_step, line_step):
    ax4d.plot(Z4[i:i+line_step+1, 0], Z4[i:i+line_step+1, 1], Z4[i:i+line_step+1, 2],
              color="#444d56", lw=0.4, alpha=0.3, zorder=1)

ax4d.set_xlabel("PC1", fontsize=8); ax4d.set_ylabel("PC2", fontsize=8)
ax4d.set_zlabel("PC3", fontsize=8)
ax4d.legend(fontsize=9, framealpha=0.3, labelcolor=TEXT_CLR,
            facecolor=PANEL_BG, edgecolor=GRID_CLR, loc="upper left")

cbar4 = fig.colorbar(sc4d, ax=ax4d, pad=0.04, shrink=0.7)
cbar4.set_label("Time (s)  [4th dimension]", color=TEXT_CLR, fontsize=8)
cbar4.ax.yaxis.set_tick_params(labelcolor=TEXT_CLR)

_save(fig, "channel_4d_collapse.png")


# ─────────────────────────────────────────────────────────────────────────
# PLOT 7  ·  Channel ranking & collapse signature summary
#            Panel A: disc-ratio + AUROC radar-style bar chart for all 23 ch
#            Panel B: pre-ictal vs ictal score separation per channel
#            Panel C: Molecular / Gravity / BSDT comparison (3 global scores overlay)
#            Panel D: Delta channel mean values (ictal vs interictal)
# ─────────────────────────────────────────────────────────────────────────
print("  [7/7] channel_summary.png …")
fig = _fig(18, 12)
fig.suptitle("CHB-MIT — Collapse Signature Summary  "
             "[ Channel Ranking | Physics vs BSDT | Delta Breakdown ]",
             color=TEXT_CLR, fontsize=13, fontweight="bold")

# Panel A: disc ratio + AUROC dual-axis
ax_a = _ax(fig, 2, 2, 1)
x_pos = np.arange(n_ch)
disc_sorted = [x['disc']   for x in ch_sorted]
auc_sorted  = [x['auroc']  for x in ch_sorted]
lbl_sorted  = [x['label']  for x in ch_sorted]
ax_a.bar(x_pos - 0.2, disc_sorted, width=0.4,
         color="#60a5fa", alpha=0.8, label="disc ratio")
ax_b2 = ax_a.twinx()
ax_b2.bar(x_pos + 0.2, auc_sorted, width=0.4,
          color="#34d399", alpha=0.7, label="AUROC")
ax_b2.set_ylim(0, 1.1)
ax_b2.tick_params(colors=TEXT_CLR, labelsize=7)
ax_b2.set_ylabel("AUROC", color=TEXT_CLR, fontsize=8)
ax_a.set_xticks(x_pos[::2])
ax_a.set_xticklabels([lbl_sorted[i] for i in range(0, n_ch, 2)],
                     rotation=45, ha="right", fontsize=5)
ax_a.set_xlabel("Channel (sorted by disc)", fontsize=8)
ax_a.set_ylabel("Discrimination ratio", fontsize=8)
ax_a.set_title("Per-Channel BSDT Collapse Ranking", color=TEXT_CLR, fontsize=10)
ax_a.axhline(1.0, color="#ffffff", ls="--", lw=0.7, alpha=0.5)
lines1, labs1 = ax_a.get_legend_handles_labels()
lines2, labs2 = ax_b2.get_legend_handles_labels()
ax_a.legend(lines1 + lines2, labs1 + labs2, fontsize=7, framealpha=0.3,
            labelcolor=TEXT_CLR, facecolor=PANEL_BG, edgecolor=GRID_CLR)

# Panel B: boxplot of scores per phase for top-5 channels
ax_c = _ax(fig, 2, 2, 2)
ax_c.set_title("Top-5 Channel Score Distribution  (interictal / pre-ictal / ictal)",
               color=TEXT_CLR, fontsize=10)
box_data = []
box_cols  = []
box_xlabels = []
for rank, x in enumerate(top5):
    ci = x['ch']
    sc_ci = bsdt_scores_ch[:, ci]
    for ph, col in [("interictal", "#60a5fa"), ("pre-ictal", "#f59e0b"), ("ictal", "#ef4444")]:
        pm = phase_all == ph
        if pm.any():
            box_data.append(sc_ci[pm])
            box_cols.append(col)
            box_xlabels.append(f"{x['label']}\n{ph[:3]}")
bp = ax_c.boxplot(box_data, patch_artist=True, notch=True,
                  medianprops=dict(color="#ffffff", lw=1.5),
                  whiskerprops=dict(color=TEXT_CLR),
                  capprops=dict(color=TEXT_CLR),
                  flierprops=dict(color=TEXT_CLR, marker=".", markersize=2))
for patch, col in zip(bp['boxes'], box_cols):
    patch.set_facecolor(col); patch.set_alpha(0.75)
ax_c.set_xticklabels(box_xlabels, fontsize=5, rotation=45, ha="right")
ax_c.set_ylabel("BSDT Score", fontsize=8)

# Panel C: 3 engine global score overlay (zoomed to last 600s)
ax_d = _ax(fig, 2, 2, 3)
t_mask = centres >= (ONSET_S - 600)
ax_d.set_title("Global Engine Scores — last 600 s before + ictal window",
               color=TEXT_CLR, fontsize=10)
for eng_n, col in colors_eng.items():
    sc = global_scores[eng_n]["scores"]
    ax_d.plot(centres[t_mask], sc[t_mask], lw=1.0, color=col, alpha=0.9, label=eng_n)
ax_d.axvline(ONSET_S, color="#ef4444", lw=1.5, ls="--", label="onset")
ax_d.axvspan(ONSET_S, OFFSET_S, alpha=0.25, color="#ef4444")
ax_d.axvspan(ONSET_S - 300, ONSET_S, alpha=0.10, color="#f59e0b")
ax_d.set_xlabel("Time (s)", fontsize=8); ax_d.set_ylabel("Score (norm)", fontsize=8)
ax_d.legend(fontsize=8, framealpha=0.3, labelcolor=TEXT_CLR,
            facecolor=PANEL_BG, edgecolor=GRID_CLR)

# Panel D: mean delta values per phase (ictal vs interictal, averaged over channels)
ax_e = _ax(fig, 2, 2, 4)
ax_e.set_title("BSDT Delta Breakdown — mean across channels",
               color=TEXT_CLR, fontsize=10)
delta_names = ["delta_C", "delta_G", "delta_A", "delta_T"]
delta_mats  = [bsdt_delta_C, bsdt_delta_G, bsdt_delta_A, bsdt_delta_T]
d_col_map   = {"interictal": "#60a5fa", "pre-ictal": "#f59e0b", "ictal": "#ef4444"}
x_d = np.arange(len(delta_names))
width = 0.25
for ph_i, (ph, col) in enumerate([("interictal", "#60a5fa"),
                                   ("pre-ictal", "#f59e0b"),
                                   ("ictal", "#ef4444")]):
    pm = phase_all == ph
    vals = [float(dm[pm].mean()) if pm.any() else 0.0 for dm in delta_mats]
    ax_e.bar(x_d + (ph_i - 1) * width, vals, width=width,
             color=col, alpha=0.8, label=ph)
ax_e.set_xticks(x_d)
ax_e.set_xticklabels(delta_names, fontsize=9)
ax_e.set_ylabel("Mean delta value", fontsize=8)
ax_e.legend(fontsize=8, framealpha=0.3, labelcolor=TEXT_CLR,
            facecolor=PANEL_BG, edgecolor=GRID_CLR)

_save(fig, "channel_summary.png")


# ══════════════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("  COLLAPSE SIGNATURE RESULTS — CHB-MIT chb01_03")
print("=" * 70)

print("\n  Global engine scores:")
for eng_n, meta in global_scores.items():
    print(f"  {eng_n:12s}  disc={meta['disc']:.2f}x  AUROC={meta['auroc']:.4f}  "
          f"lead={meta['lead_s']:.1f}s")

print(f"\n  Per-channel BSDT — TOP-5 collapse channels:")
for x in top5:
    lead_str = f"{x['lead_s']:.0f}s" if not (isinstance(x['lead_s'], float) and np.isnan(x['lead_s'])) else "n/a"
    print(f"  [{x['ch']:2d}] {x['label']:12s}  disc={x['disc']:.2f}x  "
          f"AUROC={x['auroc']:.4f}  lead={lead_str}")

print(f"\n  Plots saved to: {PLOTDIR}")
print("    channel_1d_global_scores.png")
print("    channel_1d_perchannel.png")
print("    channel_2d_heatmap.png")
print("    channel_2d_delta_breakdown.png")
print("    channel_3d_pca.png")
print("    channel_4d_collapse.png")
print("    channel_summary.png")
print("=" * 70)
