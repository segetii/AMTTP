"""Generate v52 plots from saved CSV."""
import pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

OUT  = Path("v52_window_sweep")
PLOT = OUT / "plots"
PLOT.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(OUT / "sweep_results.csv")
e = df[df["variant"] == "E_d0.50"].copy()
a = df[df["variant"] == "A_v34_base"].iloc[0]

CB_WINDOWS = sorted(e["window_d"].unique().tolist())
RHS_THRESH = 0.55

# ── 1. Pareto ──────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(14, 9))
cmap_none = plt.cm.Blues
cmap_rhs  = plt.cm.Oranges
for i, w in enumerate(CB_WINDOWS):
    shade = 0.35 + 0.55 * i / (len(CB_WINDOWS) - 1)
    r0 = e[(e["window_d"] == w) & (e["filter"] == "none")]
    if not r0.empty:
        r = r0.iloc[0]
        ax.scatter([r["maxdd"]*100], [r["final"]/1000],
                    c=[cmap_none(shade)], s=160, marker="o", zorder=5)
        ax.annotate(f"w={w}d", (r["maxdd"]*100, r["final"]/1000),
                     xytext=(4, 3), textcoords="offset points", fontsize=8)
    r1 = e[(e["window_d"] == w) & (e["filter"] != "none")]
    if not r1.empty:
        r = r1.iloc[0]
        ax.scatter([r["maxdd"]*100], [r["final"]/1000],
                    c=[cmap_rhs(shade)], s=160, marker="^", zorder=5)
        ax.annotate(f"w={w}d+rhs", (r["maxdd"]*100, r["final"]/1000),
                     xytext=(4, 3), textcoords="offset points", fontsize=8)
ax.scatter([a["maxdd"]*100], [a["final"]/1000],
            c="black", s=250, marker="*", zorder=8, label="A_v34_base w=90d (ref)")
ax.scatter([-34.85], [728.9], c="gray",    s=200, marker="D",  zorder=7, edgecolor="black",
            label="E w=90d baseline: $729K, MDD=-34.85%")
ax.scatter([-29.45], [948.1], c="gold",    s=250, marker="*",  zorder=8, edgecolor="darkorange",
            label="E w=90d+rhs v51-best: $948K, MDD=-29.45%")
ax.scatter([-13.98], [130.7], c="limegreen",s=200,marker="s",  zorder=7, edgecolor="green",
            label="v45_w180 d=0.25,w=180d: $131K, MDD=-14%")
ax.axvline(-29.45, color="orange", lw=0.8, ls="--", alpha=0.5, label="v51 best MDD")
ax.axvline(-20.0,  color="red",    lw=1.1, ls="--", alpha=0.6, label="-20% target")
ax.scatter([], [], c="steelblue",  s=120, marker="o", label="circles = no rhs filter")
ax.scatter([], [], c="darkorange", s=120, marker="^", label="triangles = rhs>=0.55+30d")
ax.set_xlabel("Max Drawdown (%)", fontsize=12)
ax.set_ylabel("Final Equity ($K)", fontsize=12)
ax.set_title("v52 \u2014 Pareto: E_d0.50 CB Window Sweep\n"
              "(blue->darker=longer window, orange->darker=longer window)",
              fontweight="bold", fontsize=12)
ax.legend(fontsize=8, loc="upper left")
ax.grid(True, alpha=0.25)
fig.tight_layout()
fig.savefig(PLOT / "pareto_final_vs_maxdd.png", dpi=160, bbox_inches="tight")
plt.close(fig)
print("pareto done")

# ── 2. Calmar vs window ────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(11, 6))
for filt_val, filt_name, color, marker in [
    ("none",            "no filter",       "steelblue",  "o"),
    ("rhs\u22650.55",   "rhs>=0.55+30d",   "darkorange",  "^"),
]:
    sub = e[e["filter"] == filt_val].sort_values("window_d")
    ax.plot(sub["window_d"], sub["calmar"], marker=marker,
             color=color, lw=2.0, label=f"E_d0.50 {filt_name}")
ax.axhline(17.45, color="gray",   lw=1.0, ls="--", alpha=0.6, label="E baseline Cal=17.45")
ax.axhline(22.60, color="orange", lw=1.0, ls="--", alpha=0.6, label="v51 best Cal=22.60")
ax.axhline(23.25, color="green",  lw=1.0, ls="--", alpha=0.6, label="v45_w180 Cal=23.25")
ax.set_xlabel("CB Window (days)", fontsize=12)
ax.set_ylabel("Calmar Ratio", fontsize=12)
ax.set_title("v52 \u2014 Calmar vs CB Window", fontweight="bold", fontsize=12)
ax.legend(fontsize=9); ax.grid(True, alpha=0.25)
fig.tight_layout()
fig.savefig(PLOT / "calmar_vs_window.png", dpi=160, bbox_inches="tight")
plt.close(fig)
print("calmar done")

# ── 3. MaxDD vs window ─────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(11, 6))
for filt_val, filt_name, color, marker in [
    ("none",            "no filter",       "steelblue",  "o"),
    ("rhs\u22650.55",   "rhs>=0.55+30d",   "darkorange",  "^"),
]:
    sub = e[e["filter"] == filt_val].sort_values("window_d")
    ax.plot(sub["window_d"], sub["maxdd"]*100, marker=marker,
             color=color, lw=2.0, label=f"E_d0.50 {filt_name}")
ax.axhline(-34.85, color="gray",   lw=1.0, ls="--", alpha=0.6, label="E baseline -34.85%")
ax.axhline(-29.45, color="orange", lw=1.0, ls="--", alpha=0.6, label="v51 best -29.45%")
ax.axhline(-20.0,  color="red",    lw=1.2, ls="--", alpha=0.7, label="-20% target")
ax.axhline(-13.98, color="green",  lw=1.0, ls="--", alpha=0.6, label="v45_w180 -13.98%")
ax.set_xlabel("CB Window (days)", fontsize=12)
ax.set_ylabel("Max Drawdown (%)", fontsize=12)
ax.set_title("v52 \u2014 MaxDD vs CB Window", fontweight="bold", fontsize=12)
ax.legend(fontsize=9); ax.grid(True, alpha=0.25)
fig.tight_layout()
fig.savefig(PLOT / "mdd_vs_window.png", dpi=160, bbox_inches="tight")
plt.close(fig)
print("mdd done")

# ── Summary ────────────────────────────────────────────────────────────────
print()
print("  window  filter        n_blk        final    maxdd  calmar")
print("  " + "-"*62)
for w in CB_WINDOWS:
    best = e[e["window_d"] == w].sort_values("calmar", ascending=False).iloc[0]
    star = "  **" if best["maxdd"] > -0.20 else ("  *" if best["maxdd"] > -0.25 else ("  o" if best["maxdd"] > -0.29 else ""))
    print("  %5dd  %-12s  %5d  $%9.1fK  %6.2f%%  %6.2f%s" % (
        w, best["filter"], int(best["n_blocked"]),
        best["final"]/1000, best["maxdd"]*100, best["calmar"], star))
print()
print("  References:")
print("  E w=90d  no-filter : $  728.9K  -34.85%   17.45")
print("  E w=90d  rhs>=0.55 : $  948.1K  -29.45%   22.60")
print("  A w=90d  no-filter : $  617.1K  -34.57%   16.60")
print("  d=0.25   w=180d    : $  130.7K  -13.98%   23.25")
print()
print("All plots saved to", PLOT)
