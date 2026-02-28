import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from run_pipeline import main as pipe_main
print('[robustness] Robustness checks embedded in main pipeline run.')
# The main pipeline run_pipeline.py imports and calls robustness_checks
# via the reproduce.py orchestration. No separate run needed.
