import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path


def _mean_std(values: list[float]) -> tuple[float, float]:
    if not values:
        return float("nan"), float("nan")
    if len(values) == 1:
        return float(values[0]), 0.0
    return float(statistics.fmean(values)), float(statistics.stdev(values))


def _fmt(ms: tuple[float, float], digits: int = 3) -> str:
    m, s = ms
    if m != m:
        return "nan"
    if s == 0.0:
        return f"{m:.{digits}f}"
    return f"{m:.{digits}f}±{s:.{digits}f}"


def _extract_methods(row: list) -> dict[str, dict[str, float]]:
    # Layout is fixed by bsdt_eval_strict.py; this extractor is len-guarded.
    out: dict[str, dict[str, float]] = {}

    out["Base"] = {
        "auc": float(row[5]),
        "f1": float(row[6]),
        "rec": float(row[7]),
        "prec": float(row[8]),
        "fa": float(row[9]),
    }
    out["+MFLS"] = {
        "f1": float(row[12]),
        "rec": float(row[13]),
        "prec": float(row[14]),
        "fa": float(row[15]),
    }

    if len(row) >= 25:
        out["SignedLR"] = {
            "auc": float(row[22]),
            "f1": float(row[18]),
            "rec": float(row[19]),
            "prec": float(row[20]),
            "fa": float(row[21]),
        }

    if len(row) >= 33:
        out["QuadSurf"] = {
            "auc": float(row[29]),
            "f1": float(row[25]),
            "rec": float(row[26]),
            "prec": float(row[27]),
            "fa": float(row[28]),
        }

    if len(row) >= 43:
        out["QuadSurf+ExpGate"] = {
            "auc": float(row[37]),
            "f1": float(row[33]),
            "rec": float(row[34]),
            "prec": float(row[35]),
            "fa": float(row[36]),
        }

    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--path",
        type=str,
        default=r"c:\amttp\papers\comprehensive_bsdt_results_strict_transfer.json",
        help="Path to comprehensive strict(-transfer) JSON.",
    )
    args = ap.parse_args()

    p = Path(args.path)
    d = json.loads(p.read_text(encoding="utf-8"))
    rows = d.get("rows", [])

    transfer_rows = [r for r in rows if str(r[2]).startswith("Transfer-XGB")]
    if not transfer_rows:
        print("No Transfer-XGB rows found.")
        return

    # Group metrics across seeds by (dataset, domain, model, method)
    grouped: dict[tuple[str, str, str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for r in transfer_rows:
        ds, domain, model = str(r[0]), str(r[1]), str(r[2])
        methods = _extract_methods(r)
        for method, metrics in methods.items():
            key = (ds, domain, model, method)
            for metric_name, value in metrics.items():
                grouped[key][metric_name].append(float(value))

    # Print summary
    keys_sorted = sorted(grouped.keys(), key=lambda k: (k[1], k[0], k[2], k[3]))
    current = None
    for ds, domain, model, method in keys_sorted:
        header = (ds, domain, model)
        if header != current:
            current = header
            print(f"\n{ds} ({domain}) / {model}")

        metrics = grouped[(ds, domain, model, method)]
        auc = _fmt(_mean_std(metrics.get("auc", []))) if "auc" in metrics else "-"
        f1 = _fmt(_mean_std(metrics.get("f1", [])))
        rec = _fmt(_mean_std(metrics.get("rec", [])))
        prec = _fmt(_mean_std(metrics.get("prec", [])))
        fa = _fmt(_mean_std(metrics.get("fa", [])), digits=4)

        print(f"  {method:16s}  AUC={auc:11s}  F1={f1:11s}  Rec={rec:11s}  Prec={prec:11s}  FA={fa}")


if __name__ == "__main__":
    main()
