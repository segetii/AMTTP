import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import json, numpy as np, pandas as pd
from eval_protocol import eval_all_variants, latex_eval_table, CRISIS_WINDOWS_EVAL

# load saved pipeline outputs
with open('results/pipeline_stats_v2.json') as f:
    stats = json.load(f)

# re-run the variant comparison to get signals
# (signals are stored in variant_comparison.json in variants pipeline)
import importlib, importlib.util
from run_pipeline import main as pipe_main
print('[eval] Re-running pipeline to get signal arrays …')
# The pipeline already saves results; load the OOS signal from the stats
# Minimal approach: call run_pipeline which recomputes and re-saves.
pipe_main()
print('[eval] Done – see results/eval_protocol*.json')
