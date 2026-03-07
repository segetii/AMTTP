"""
Re-run only the 4 methods that had the projector-bypass bug:
  QDA-lean, QDA-Mag-lean, BSDT-Fisher, CombA-QDA-Mag

Reads existing full_benchmark_checkpoint.json, overwrites just those
4 methods per dataset, writes back. All other methods are preserved.
"""
import subprocess, sys, json, os
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKER_SCRIPT = os.path.join(SCRIPT_DIR, "worker_eval.py")

CHECKPOINT_FILE = os.path.join(
    os.path.dirname(SCRIPT_DIR), "results", "full_benchmark_checkpoint.json"
)

# Only these methods were broken (projector bypass bug)
FIXED_METHODS = ["QDA-lean", "QDA-Mag-lean", "BSDT-Fisher", "CombA-QDA-Mag"]

ALL_DATASETS = [
    "mammography", "shuttle", "pendigits", "annthyroid",
    "arrhythmia", "satellite", "glass", "cardio",
]

PROGRESS_FILE = CHECKPOINT_FILE.replace(".json", "_fixprogress.json")


def load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def run_dataset_worker(ds_name):
    """Run worker_eval.py for ds_name; returns full results dict."""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.dirname(SCRIPT_DIR)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        result = subprocess.run(
            [sys.executable, "-u", WORKER_SCRIPT, ds_name],
            capture_output=True, text=True, timeout=3600,
            cwd=os.path.dirname(SCRIPT_DIR), env=env,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT for {ds_name}")
        return {}

    for line in result.stdout.split("\n"):
        if line.startswith("RESULTS_JSON:"):
            return json.loads(line[len("RESULTS_JSON:"):])

    if result.returncode != 0:
        print(f"  CRASHED (exit {result.returncode}): {result.stderr[-200:]}")
    return {}


def main():
    checkpoint = load_json(CHECKPOINT_FILE)
    progress = load_json(PROGRESS_FILE)

    datasets_to_process = [d for d in ALL_DATASETS if d in checkpoint and d != "shuttle"]

    print(f"Patching {FIXED_METHODS} on {len(datasets_to_process)} datasets")
    print(f"(Shuttle skipped — handled separately)\n")

    for ds_name in datasets_to_process:
        if progress.get(ds_name, {}).get("done"):
            print(f"[skip] {ds_name} — already patched")
            continue

        print(f"\n--- {ds_name} ---")
        new_results = run_dataset_worker(ds_name)
        if not new_results:
            print(f"  WARNING: no results for {ds_name}, skipping")
            continue

        # Patch only the fixed methods into the checkpoint
        for method in FIXED_METHODS:
            if method in new_results:
                r = new_results[method]
                auc = r.get("auc", 0.0) or 0.0
                cov = r.get("cov", 0.0) or 0.0
                det = r.get("det", 0)
                n = r.get("n", 0)
                info = r.get("info", "")
                print(f"  {method:<18s} AUC={auc:.4f}  Cov={det}/{n} ({100*cov:.0f}%)"
                      + (f" [{info}]" if info else ""))
                checkpoint[ds_name][method] = r

        # Save checkpoint + progress
        save_json(CHECKPOINT_FILE, checkpoint)
        progress[ds_name] = {"done": True}
        save_json(PROGRESS_FILE, progress)
        print(f"  [checkpoint updated]")

    # Print summary of patched methods across datasets
    completed = [d for d in ALL_DATASETS if d in checkpoint and d != "shuttle"]
    print(f"\n\n{'='*100}")
    print(f"  PATCHED METHODS SUMMARY")
    print(f"{'='*100}")
    header = f"  {'Method':<18s}"
    for d in completed:
        header += f"  {d[:8]:>8s}"
    header += f"  {'mAUC':>8s}"
    print(header)
    for method in FIXED_METHODS:
        row = f"  {method:<18s}"
        aucs = []
        for d in completed:
            r = checkpoint.get(d, {}).get(method, {})
            auc = (r.get("auc") or 0.0)
            row += f"  {auc:>8.4f}"
            aucs.append(auc)
        row += f"  {np.mean(aucs):>8.4f}"
        print(row)

    print(f"\nResults saved → {CHECKPOINT_FILE}")


if __name__ == "__main__":
    main()
