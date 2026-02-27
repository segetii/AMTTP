"""Phase-2 only: per-dataset evaluation. Runs each dataset in a subprocess for memory isolation."""
import subprocess, sys, json, os, numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKER_SCRIPT = os.path.join(SCRIPT_DIR, "worker_eval.py")
DATASETS = ["synthetic", "mimic", "mammography", "shuttle", "pendigits"]
METHODS = ["Fisher", "RankFuse", "Hybrid-auto", "Hybrid-blend", "RL-fresh", "RL-pretrained"]

def main():
    priors_path = os.path.join(SCRIPT_DIR, "rl_priors.json")
    all_results = {}

    for ds_name in DATASETS:
        print(f"\n--- {ds_name} ---")
        # Run in subprocess for memory isolation
        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.dirname(SCRIPT_DIR)
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            result = subprocess.run(
                [sys.executable, "-u", WORKER_SCRIPT, ds_name, priors_path],
                capture_output=True, text=True, timeout=1800,
                cwd=os.path.dirname(SCRIPT_DIR), env=env,
                encoding="utf-8", errors="replace"
            )
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT after 1800s")
            all_results[ds_name] = {m: {"auc": 0, "cov": 0, "det": 0, "n": 0, "info": "TIMEOUT"} for m in METHODS}
            for method in METHODS:
                print(f"  {method:<18s} TIMEOUT")
            continue

        # Parse stderr for diagnostics
        if result.stderr:
            for line in result.stderr.strip().split('\n'):
                if line.strip():
                    print(f"  [stderr] {line.strip()}")

        # Parse results from stdout
        ds_results = {}
        for line in result.stdout.split('\n'):
            if line.startswith("RESULTS_JSON:"):
                ds_results = json.loads(line[len("RESULTS_JSON:"):])
            elif line.strip() and "[Hybrid]" in line:
                print(f"  {line.strip()}")

        if not ds_results and result.returncode != 0:
            print(f"  CRASHED (exit code {result.returncode})")
            ds_results = {m: {"auc": 0, "cov": 0, "det": 0, "n": 0, "info": "CRASH"} for m in METHODS}

        all_results[ds_name] = ds_results

        for method in METHODS:
            r = ds_results.get(method, {"auc": 0, "cov": 0, "det": 0, "n": 0, "info": ""})
            info_str = f" [{r['info']}]" if r.get('info') else ""
            print(f"  {method:<18s} AUC={r['auc']:.4f}  Cov={r['det']}/{r['n']} ({100*r['cov']:.0f}%){info_str}")

    # Summary table
    print(f"\n\n{'='*120}")
    print("  SUMMARY TABLE")
    print(f"{'='*120}")

    header = f"  {'Method':<18s}"
    for dn in DATASETS:
        header += f"  {dn[:8]:>8s}-A {dn[:8]:>8s}-C"
    header += f"  {'mAUC':>8s} {'mCov':>8s} {'minCov':>8s}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for method in METHODS:
        row = f"  {method:<18s}"
        aucs, covs = [], []
        for dn in DATASETS:
            r = all_results.get(dn, {}).get(method, {"auc": 0, "cov": 0})
            row += f"  {r['auc']:>10.4f} {100*r['cov']:>7.0f}%"
            aucs.append(r['auc'])
            covs.append(r['cov'])
        row += f"  {np.mean(aucs):>8.4f} {100*np.mean(covs):>7.0f}% {100*min(covs):>7.0f}%"
        print(row)

    # Save
    out_path = os.path.join(SCRIPT_DIR, "hybrid_rl_results.json")
    json.dump(all_results, open(out_path, "w"), indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
