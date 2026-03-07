"""
Run benchmarks on the 5 new ODDS datasets only.
Checkpoints after every dataset — safe to restart after power cuts.
Already-completed datasets from the checkpoint file are skipped.
"""
import subprocess, sys, json, os
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKER_SCRIPT = os.path.join(SCRIPT_DIR, "worker_eval.py")

NEW_DATASETS = [
    "annthyroid",
    "arrhythmia",
    "satellite",
    "glass",
    "cardio",
]

METHODS = [
    "Fisher-lean", "Fuse-lean", "QuadSurf-lean",
    "MetaFusion", "MetaFusion+", "Hybrid-lean",
    "Fisher-4op", "Fuse-4op", "Hybrid-4op",
]

CHECKPOINT_FILE = os.path.join(
    os.path.dirname(SCRIPT_DIR), "results", "new_datasets_checkpoint.json"
)


def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r") as f:
            return json.load(f)
    return {}


def save_checkpoint(data):
    os.makedirs(os.path.dirname(CHECKPOINT_FILE), exist_ok=True)
    tmp = CHECKPOINT_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, CHECKPOINT_FILE)  # atomic on Windows (same volume)
    print(f"  [checkpoint saved → {CHECKPOINT_FILE}]")


def run_dataset(ds_name):
    """Run worker_eval.py for ds_name and return parsed results dict."""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.dirname(SCRIPT_DIR)
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        result = subprocess.run(
            [sys.executable, "-u", WORKER_SCRIPT, ds_name],
            capture_output=True, text=True, timeout=1800,
            cwd=os.path.dirname(SCRIPT_DIR), env=env,
            encoding="utf-8", errors="replace"
        )
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT after 1800s")
        return {m: {"auc": 0, "cov": 0, "det": 0, "n": 0, "info": "TIMEOUT"} for m in METHODS}

    # Print diagnostic stderr
    if result.stderr:
        for line in result.stderr.strip().split("\n"):
            stripped = line.strip()
            if stripped:
                print(f"  [stderr] {stripped}")

    # Parse JSON results from stdout
    ds_results = {}
    for line in result.stdout.split("\n"):
        if line.startswith("RESULTS_JSON:"):
            ds_results = json.loads(line[len("RESULTS_JSON:"):])
        elif line.strip() and "[Hybrid]" in line:
            print(f"  {line.strip()}")

    if not ds_results and result.returncode != 0:
        print(f"  CRASHED (exit code {result.returncode})")
        ds_results = {m: {"auc": 0, "cov": 0, "det": 0, "n": 0, "info": "CRASH"} for m in METHODS}

    return ds_results


def print_summary(all_results, datasets):
    print(f"\n\n{'='*120}")
    print("  SUMMARY TABLE (new datasets)")
    print(f"{'='*120}")
    header = f"  {'Method':<18s}"
    for dn in datasets:
        header += f"  {dn[:8]:>8s}-A {dn[:8]:>8s}-C"
    header += f"  {'mAUC':>8s} {'mCov':>8s} {'minCov':>8s}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for method in METHODS:
        row = f"  {method:<18s}"
        aucs, covs = [], []
        for dn in datasets:
            r = all_results.get(dn, {}).get(method, {"auc": 0, "cov": 0})
            row += f"  {r['auc']:>10.4f} {100*r['cov']:>7.0f}%"
            aucs.append(r["auc"])
            covs.append(r["cov"])
        row += f"  {np.mean(aucs):>8.4f} {100*np.mean(covs):>7.0f}% {100*min(covs):>7.0f}%"
        print(row)


def main():
    all_results = load_checkpoint()

    already_done = [d for d in NEW_DATASETS if d in all_results]
    to_run = [d for d in NEW_DATASETS if d not in all_results]

    if already_done:
        print(f"Skipping (already in checkpoint): {', '.join(already_done)}")
    print(f"Will run: {', '.join(to_run) if to_run else '(none — all done)'}")

    for ds_name in to_run:
        print(f"\n--- {ds_name} ---")
        ds_results = run_dataset(ds_name)
        all_results[ds_name] = ds_results

        # Print per-method results
        for method in METHODS:
            r = ds_results.get(method, {"auc": 0, "cov": 0, "det": 0, "n": 0, "info": ""})
            info_str = f" [{r['info']}]" if r.get("info") else ""
            print(f"  {method:<18s} AUC={r['auc']:.4f}  Cov={r['det']}/{r['n']} ({100*r['cov']:.0f}%){info_str}")

        # Checkpoint immediately after each dataset
        save_checkpoint(all_results)

    # Final summary showing all completed datasets
    completed = [d for d in NEW_DATASETS if d in all_results]
    if completed:
        print_summary(all_results, completed)

    print("\nDone. Results in:", CHECKPOINT_FILE)


if __name__ == "__main__":
    main()
