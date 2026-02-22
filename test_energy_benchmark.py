"""
Energy Framework Benchmark — Compare energy scoring across datasets.
Tests: standard QDA, energy-only, energy+QDA fusion, energy-flow+QDA.
"""
import numpy as np
import warnings
warnings.filterwarnings('ignore')
from sklearn.datasets import fetch_openml
from sklearn.metrics import roc_auc_score
from udl import UDLPipeline
from udl.spectra import (
    GeometricSpectrum, RankOrderSpectrum, StatisticalSpectrum,
    ChaosSpectrum, SpectralSpectrum, ExponentialSpectrum,
)

DATASETS = {
    'mammography': {'id': 'mammography', 'version': 1, 'pos': '1'},
    'satellite':   {'id': 'satellite', 'version': 1, 'pos': '1'},
    'pendigits':   {'id': 'pendigits', 'version': 1, 'pos': '4'},
}

OPERATORS = [
    ('stat', StatisticalSpectrum()),
    ('geom', GeometricSpectrum()),
    ('rank', RankOrderSpectrum()),
]

results = []

for ds_name, ds_info in DATASETS.items():
    print(f'\n{"="*60}')
    print(f'Dataset: {ds_name}')
    print(f'{"="*60}')

    try:
        data = fetch_openml(ds_info['id'], version=ds_info['version'],
                            as_frame=False, parser='auto')
    except Exception as e:
        print(f'  SKIP: {e}')
        continue

    X, y_raw = data.data, data.target
    y = (y_raw == ds_info['pos']).astype(int)
    n_anom = y.sum()
    print(f'  Shape: {X.shape}, anomalies: {n_anom}/{len(y)} ({100*n_anom/len(y):.1f}%)')

    if n_anom == 0 or n_anom == len(y):
        print('  SKIP: no class variation')
        continue

    # Fresh operator instances for each dataset
    ops_qda = [
        ('stat', StatisticalSpectrum()),
        ('geom', GeometricSpectrum()),
        ('rank', RankOrderSpectrum()),
    ]
    ops_energy = [
        ('stat', StatisticalSpectrum()),
        ('geom', GeometricSpectrum()),
        ('rank', RankOrderSpectrum()),
    ]
    ops_both = [
        ('stat', StatisticalSpectrum()),
        ('geom', GeometricSpectrum()),
        ('rank', RankOrderSpectrum()),
    ]
    ops_flow = [
        ('stat', StatisticalSpectrum()),
        ('geom', GeometricSpectrum()),
        ('rank', RankOrderSpectrum()),
    ]

    # 1. Standard QDA
    pipe_qda = UDLPipeline(operators=ops_qda, centroid_method='geometric_median')
    pipe_qda.fit(X, y)
    auc_qda = roc_auc_score(y, pipe_qda.score(X))
    print(f'  QDA AUC:          {auc_qda:.4f}')

    # 2. Energy-only
    pipe_e = UDLPipeline(operators=ops_energy, centroid_method='geometric_median',
                         energy_score=True, energy_alpha=1.0, energy_gamma=0.01)
    pipe_e.fit(X, y)
    auc_energy = roc_auc_score(y, pipe_e.energy_scores(X))
    print(f'  Energy AUC:       {auc_energy:.4f}')

    # 3. Energy+QDA fusion (average of normalised scores)
    pipe_both = UDLPipeline(operators=ops_both, centroid_method='geometric_median',
                            energy_score=True, energy_alpha=1.0, energy_gamma=0.01)
    pipe_both.fit(X, y)
    qda_s = pipe_both.score(X)
    e_s = pipe_both.energy_scores(X)
    # Normalise to [0,1]
    qda_n = (qda_s - qda_s.min()) / (qda_s.max() - qda_s.min() + 1e-10)
    e_n = (e_s - e_s.min()) / (e_s.max() - e_s.min() + 1e-10)
    fused = 0.5 * qda_n + 0.5 * e_n
    auc_fused = roc_auc_score(y, fused)
    print(f'  Fused AUC:        {auc_fused:.4f}')

    # 4. Energy flow + QDA
    pipe_flow = UDLPipeline(operators=ops_flow, centroid_method='geometric_median',
                            energy_flow=True, energy_flow_steps=5)
    pipe_flow.fit(X, y)
    auc_flow = roc_auc_score(y, pipe_flow.score(X))
    print(f'  Flow+QDA AUC:     {auc_flow:.4f}')

    # 5. Stability metrics
    stab = pipe_e.stability_analysis(X, y=y)
    print(f'  Separation ratio: {stab.get("energy_separation_ratio", 0):.2f}')
    print(f'  Cohen\'s d:        {stab.get("cohens_d", 0):.2f}')

    # 6. Operator diversity
    div = pipe_e.operator_diversity_report(X[:100])
    print(f'  Diversity sep:    {div["is_separating"]}')
    print(f'  Stacked rank:     {div["stacked_rank"]}/{div["input_dim"]}')

    results.append({
        'dataset': ds_name,
        'auc_qda': auc_qda,
        'auc_energy': auc_energy,
        'auc_fused': auc_fused,
        'auc_flow': auc_flow,
        'separation': stab.get('energy_separation_ratio', 0),
        'cohens_d': stab.get('cohens_d', 0),
    })

# Summary table
print(f'\n{"="*75}')
print(f'{"Dataset":15s} {"QDA":>8s} {"Energy":>8s} {"Fused":>8s} {"Flow":>8s} {"Sep":>6s} {"d":>6s}')
print(f'{"-"*75}')
for r in results:
    print(f'{r["dataset"]:15s} {r["auc_qda"]:8.4f} {r["auc_energy"]:8.4f} '
          f'{r["auc_fused"]:8.4f} {r["auc_flow"]:8.4f} '
          f'{r["separation"]:6.1f} {r["cohens_d"]:6.2f}')
print(f'{"="*75}')
