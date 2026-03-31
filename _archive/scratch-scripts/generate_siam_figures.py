"""Generate figures for SIAM paper: adaptive calibration results."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

# Load results
with open('insample_calibrated_results.json', 'r') as f:
    data = json.load(f)

dates_str = data['dates']
dates = [datetime.strptime(d, '%Y-%m-%d') for d in dates_str]
crisis_set = set(data['crisis_quarters'])
n_calib = data['n_calib']

# Crisis periods for shading (start, end)
crisis_periods = [
    (datetime(2007, 10, 1), datetime(2009, 7, 1), 'GFC'),
    (datetime(2011, 7, 1), datetime(2012, 7, 1), 'Euro'),
    (datetime(2020, 1, 1), datetime(2020, 7, 1), 'COVID'),
]

lehman_date = datetime(2008, 9, 15)

# --- Figure 1: Score timelines for top 3 algorithms with adaptive P99 threshold ---
fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)

algorithms = [
    ('mol_expogate', 'Mol+ExpoGate', '#1f77b4'),
    ('rtd_fisher', 'RTD+Fisher', '#2ca02c'),
    ('rtd_mol', 'RTD+Mol', '#d62728'),
]

for ax_idx, (key, label, color) in enumerate(algorithms):
    ax = axes[ax_idx]
    scores = data['scores'][key]
    
    # Compute adaptive P99 threshold (rolling 8-quarter window)
    window = 8
    adaptive_thresh = []
    for t in range(len(scores)):
        if t < n_calib:
            # Use calibration period stats
            calib_scores = scores[:n_calib]
            thr = np.percentile(calib_scores, 99)
        else:
            start = max(0, t - window)
            thr = np.percentile(scores[start:t], 99)
        adaptive_thresh.append(thr)
    
    # Also compute fixed mu+3sig threshold from calibration
    calib_scores = scores[:n_calib]
    fixed_thresh = np.mean(calib_scores) + 3 * np.std(calib_scores)
    
    # Plot score timeline
    ax.plot(dates, scores, color=color, linewidth=1.5, label=f'{label} score', zorder=3)
    ax.plot(dates, adaptive_thresh, color='black', linewidth=1.0, linestyle='--',
            label='Adaptive P99 threshold', zorder=3)
    ax.axhline(fixed_thresh, color='gray', linewidth=0.8, linestyle=':',
               label=f'Fixed $\\mu+3\\sigma$ ({fixed_thresh:.3f})', zorder=2)
    
    # Crisis shading
    for start, end, crisis_label in crisis_periods:
        ax.axvspan(start, end, alpha=0.15, color='red', zorder=1)
    
    # Lehman date
    ax.axvline(lehman_date, color='purple', linewidth=1.0, linestyle='--', alpha=0.7, zorder=2)
    
    # Mark TP/FP with adaptive P99
    for t_idx in range(n_calib, len(scores)):
        is_crisis = dates_str[t_idx] in crisis_set
        is_alarm = scores[t_idx] > adaptive_thresh[t_idx]
        if is_alarm and is_crisis:
            ax.plot(dates[t_idx], scores[t_idx], 'g^', markersize=8, zorder=5)
        elif is_alarm and not is_crisis:
            ax.plot(dates[t_idx], scores[t_idx], 'rx', markersize=7, zorder=5)
        elif not is_alarm and is_crisis:
            ax.plot(dates[t_idx], scores[t_idx], 'yv', markersize=6, zorder=4)
    
    ax.set_ylabel('Anomaly Score', fontsize=10)
    ax.set_title(f'{label} (AUROC = {data["results"][key]["auroc"]:.3f})', fontsize=11, fontweight='bold')
    ax.legend(loc='upper right', fontsize=7, framealpha=0.9)
    ax.grid(True, alpha=0.3)

axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
axes[-1].xaxis.set_major_locator(mdates.YearLocator(2))
axes[-1].set_xlabel('Date', fontsize=10)
fig.suptitle('In-Sample Monitoring with Adaptive Calibration', fontsize=13, fontweight='bold', y=0.98)
plt.tight_layout(rect=[0, 0, 1, 0.96])
plt.savefig('research/siam-paper/adaptive_calibration_timeline.pdf', bbox_inches='tight', dpi=300)
plt.savefig('research/siam-paper/adaptive_calibration_timeline.png', bbox_inches='tight', dpi=150)
print("Saved: adaptive_calibration_timeline.pdf")

# --- Figure 2: Fixed vs Adaptive comparison bar chart ---
fig2, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5))

algo_labels = ['Mol+Expo', 'RTD+Fish', 'Mol+Quad', 'RTD+Mol', 'Mol+Fish', 'Molecular', 'Hybrid', 'Gravity']
algo_keys = ['mol_expogate', 'rtd_fisher', 'mol_quadsurf', 'rtd_mol', 'mol_fisher', 'mol_fused', 'hybrid', 'gravity']

# Fixed P99 FAR and Recall
fixed_far = [data['results'][k]['Fixed P99']['far'] for k in algo_keys]
fixed_recall = [data['results'][k]['Fixed P99']['recall'] for k in algo_keys]

# Adaptive P99 FAR and Recall
adapt_far = [data['results'][k]['Adaptive P99']['far'] for k in algo_keys]
adapt_recall = [data['results'][k]['Adaptive P99']['recall'] for k in algo_keys]

x = np.arange(len(algo_labels))
width = 0.35

# FAR comparison
bars1 = ax1.bar(x - width/2, fixed_far, width, label='Fixed P99', color='#ff7f0e', alpha=0.8)
bars2 = ax1.bar(x + width/2, adapt_far, width, label='Adaptive P99', color='#1f77b4', alpha=0.8)
ax1.set_ylabel('False Alarm Rate (%)', fontsize=10)
ax1.set_title('FAR: Fixed vs Adaptive', fontsize=11, fontweight='bold')
ax1.set_xticks(x)
ax1.set_xticklabels(algo_labels, rotation=45, ha='right', fontsize=8)
ax1.legend(fontsize=8)
ax1.grid(True, alpha=0.3, axis='y')
# Annotate the 100% bar
for i, v in enumerate(fixed_far):
    if v > 50:
        ax1.text(i - width/2, v + 1, f'{v:.0f}%', ha='center', fontsize=7, fontweight='bold', color='red')

# Recall comparison
bars3 = ax2.bar(x - width/2, fixed_recall, width, label='Fixed P99', color='#ff7f0e', alpha=0.8)
bars4 = ax2.bar(x + width/2, adapt_recall, width, label='Adaptive P99', color='#1f77b4', alpha=0.8)
ax2.set_ylabel('Crisis Recall (%)', fontsize=10)
ax2.set_title('Recall: Fixed vs Adaptive', fontsize=11, fontweight='bold')
ax2.set_xticks(x)
ax2.set_xticklabels(algo_labels, rotation=45, ha='right', fontsize=8)
ax2.legend(fontsize=8)
ax2.grid(True, alpha=0.3, axis='y')

plt.tight_layout()
plt.savefig('research/siam-paper/fixed_vs_adaptive_comparison.pdf', bbox_inches='tight', dpi=300)
plt.savefig('research/siam-paper/fixed_vs_adaptive_comparison.png', bbox_inches='tight', dpi=150)
print("Saved: fixed_vs_adaptive_comparison.pdf")

# --- Figure 3: AUROC ranking with GFC-AUROC ---
fig3, ax = plt.subplots(figsize=(8, 4.5))

aurocs = [data['results'][k]['auroc'] for k in algo_keys]
gfc_aurocs = [data['results'][k]['gfc_auroc'] for k in algo_keys]

x = np.arange(len(algo_labels))
width = 0.35

bars_a = ax.bar(x - width/2, aurocs, width, label='Full AUROC', color='#2ca02c', alpha=0.85)
bars_g = ax.bar(x + width/2, gfc_aurocs, width, label='GFC AUROC', color='#9467bd', alpha=0.85)

ax.set_ylabel('AUROC', fontsize=10)
ax.set_title('Algorithm Ranking: Full AUROC vs GFC-Window AUROC', fontsize=11, fontweight='bold')
ax.set_xticks(x)
ax.set_xticklabels(algo_labels, rotation=45, ha='right', fontsize=8)
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3, axis='y')
ax.set_ylim(0, 1.1)
ax.axhline(0.5, color='gray', linewidth=0.8, linestyle=':', alpha=0.5)

# Annotate top values
for i, (a, g) in enumerate(zip(aurocs, gfc_aurocs)):
    ax.text(i - width/2, a + 0.02, f'{a:.3f}', ha='center', fontsize=7)
    ax.text(i + width/2, g + 0.02, f'{g:.3f}', ha='center', fontsize=7)

plt.tight_layout()
plt.savefig('research/siam-paper/auroc_ranking.pdf', bbox_inches='tight', dpi=300)
plt.savefig('research/siam-paper/auroc_ranking.png', bbox_inches='tight', dpi=150)
print("Saved: auroc_ranking.pdf")

print("\nAll figures generated successfully!")
