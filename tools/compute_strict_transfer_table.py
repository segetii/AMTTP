import json
import statistics
from collections import defaultdict
from pathlib import Path


def mean_std(vals: list[float]) -> tuple[float, float]:
    if len(vals) == 1:
        return vals[0], 0.0
    return statistics.fmean(vals), statistics.stdev(vals)


def fmt(ms: tuple[float, float]) -> str:
    m, s = ms
    return f"{m:.3f}" if s == 0.0 else f"{m:.3f}±{s:.3f}"


def fmt_pct(ms: tuple[float, float]) -> str:
    m, s = ms
    m *= 100
    s *= 100
    return f"{m:.1f}%" if s == 0.0 else f"{m:.1f}%±{s:.1f}%"


def main() -> None:
    path = Path(r"c:\amttp\papers\comprehensive_bsdt_results_strict_transfer_only.json")
    d = json.loads(path.read_text(encoding="utf-8"))
    rows = d["rows"]

    idx = {
        "base_auc": 5,
        "base_f1": 6,
        "base_fdr": 9,
        "corr_f1": 12,
        "corr_fdr": 15,
        "slr_auc": 22,
        "slr_f1": 18,
        "slr_fdr": 21,
        "quad_auc": 29,
        "quad_f1": 25,
        "quad_fdr": 28,
        "qexp_auc": 37,
        "qexp_f1": 33,
        "qexp_fdr": 36,
    }

    grouped: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for r in rows:
        ds, domain, model = str(r[0]), str(r[1]), str(r[2])
        if not model.startswith("Transfer-XGB"):
            continue
        key = (ds, domain)
        for name, j in idx.items():
            grouped[key][name].append(float(r[j]))

    order = [
        ("Elliptic", "IN-DOMAIN"),
        ("XBlock", "IN-DOMAIN"),
        ("Credit Card", "OUT-DOMAIN"),
        ("Shuttle", "OUT-DOMAIN"),
        ("Mammography", "OUT-DOMAIN"),
        ("Pendigits", "OUT-DOMAIN"),
    ]

    print("| Dataset | Domain | Base F1 | +MFLS F1 | +MFLS FDR | SignedLR F1 | SignedLR FDR | QuadSurf F1 | QuadSurf FDR | ExpGate F1 | ExpGate FDR |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    per_dataset_means = {
        "base_f1": [],
        "base_fdr": [],
        "corr_f1": [],
        "corr_fdr": [],
        "slr_f1": [],
        "slr_fdr": [],
        "quad_f1": [],
        "quad_fdr": [],
        "qexp_f1": [],
        "qexp_fdr": [],
    }
    per_dataset_auc_means = {"base_auc": [], "slr_auc": [], "quad_auc": [], "qexp_auc": []}
    for ds, dom in order:
        key = (ds, dom)
        if key not in grouped:
            continue
        base_ms = mean_std(grouped[key]["base_f1"])
        corr_ms = mean_std(grouped[key]["corr_f1"])
        corr_fdr_ms = mean_std(grouped[key]["corr_fdr"])
        slr_ms = mean_std(grouped[key]["slr_f1"])
        slr_fdr_ms = mean_std(grouped[key]["slr_fdr"])
        quad_ms = mean_std(grouped[key]["quad_f1"])
        quad_fdr_ms = mean_std(grouped[key]["quad_fdr"])
        qexp_ms = mean_std(grouped[key]["qexp_f1"])
        fdr_ms = mean_std(grouped[key]["qexp_fdr"])

        base = fmt(base_ms)
        corr = fmt(corr_ms)
        corr_fdr = fmt_pct(corr_fdr_ms)
        slr = fmt(slr_ms)
        slr_fdr = fmt_pct(slr_fdr_ms)
        quad = fmt(quad_ms)
        quad_fdr = fmt_pct(quad_fdr_ms)
        qexp = fmt(qexp_ms)
        fdr = fmt_pct(fdr_ms)

        per_dataset_means["base_f1"].append(base_ms[0])
        per_dataset_means["base_fdr"].append(mean_std(grouped[key]["base_fdr"])[0])
        per_dataset_means["corr_f1"].append(corr_ms[0])
        per_dataset_means["corr_fdr"].append(mean_std(grouped[key]["corr_fdr"])[0])
        per_dataset_means["slr_f1"].append(slr_ms[0])
        per_dataset_means["slr_fdr"].append(mean_std(grouped[key]["slr_fdr"])[0])
        per_dataset_means["quad_f1"].append(quad_ms[0])
        per_dataset_means["quad_fdr"].append(mean_std(grouped[key]["quad_fdr"])[0])
        per_dataset_means["qexp_f1"].append(qexp_ms[0])
        per_dataset_means["qexp_fdr"].append(fdr_ms[0])

        per_dataset_auc_means["base_auc"].append(mean_std(grouped[key]["base_auc"])[0])
        per_dataset_auc_means["slr_auc"].append(mean_std(grouped[key]["slr_auc"])[0])
        per_dataset_auc_means["quad_auc"].append(mean_std(grouped[key]["quad_auc"])[0])
        per_dataset_auc_means["qexp_auc"].append(mean_std(grouped[key]["qexp_auc"])[0])
        print(f"| {ds} | {dom} | {base} | {corr} | {corr_fdr} | {slr} | {slr_fdr} | {quad} | {quad_fdr} | {qexp} | {fdr} |")

    print("\nSignedLR vs +MFLS (strict protocol; test split; mean±std over seeds):")
    print("| Dataset | +MFLS F1 | +MFLS FDR | SignedLR F1 | SignedLR FDR | SignedLR AUC | ΔF1 |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for ds, dom in order:
        key = (ds, dom)
        if key not in grouped:
            continue

        corr_f1_ms = mean_std(grouped[key]["corr_f1"])
        corr_fdr_ms = mean_std(grouped[key]["corr_fdr"])
        slr_f1_ms = mean_std(grouped[key]["slr_f1"])
        slr_fdr_ms = mean_std(grouped[key]["slr_fdr"])
        slr_auc_ms = mean_std(grouped[key]["slr_auc"])

        delta = slr_f1_ms[0] - corr_f1_ms[0]

        print(
            f"| {ds} | {fmt(corr_f1_ms)} | {fmt_pct(corr_fdr_ms)} | {fmt(slr_f1_ms)} | {fmt_pct(slr_fdr_ms)} | {fmt(slr_auc_ms)} | {delta:+.3f} |"
        )

    print(
        f"| **Mean** | **{statistics.fmean(per_dataset_means['corr_f1']):.3f}** | **{statistics.fmean(per_dataset_means['corr_fdr'])*100:.1f}%** | "
        f"**{statistics.fmean(per_dataset_means['slr_f1']):.3f}** | **{statistics.fmean(per_dataset_means['slr_fdr'])*100:.1f}%** | "
        f"**{statistics.fmean(per_dataset_auc_means['slr_auc']):.3f}** | **{(statistics.fmean(per_dataset_means['slr_f1'])-statistics.fmean(per_dataset_means['corr_f1'])):+.3f}** |"
    )

    print("\nAggregate means across datasets (computed over per-dataset seed-means):")
    print(f"  Base:    F1={statistics.fmean(per_dataset_means['base_f1']):.3f}  AUC={statistics.fmean(per_dataset_auc_means['base_auc']):.3f}")
    print(f"  +MFLS:   F1={statistics.fmean(per_dataset_means['corr_f1']):.3f}  FDR={statistics.fmean(per_dataset_means['corr_fdr'])*100:.1f}%")
    print(f"  SignedLR:F1={statistics.fmean(per_dataset_means['slr_f1']):.3f}  AUC={statistics.fmean(per_dataset_auc_means['slr_auc']):.3f}  FDR={statistics.fmean(per_dataset_means['slr_fdr'])*100:.1f}%")
    print(f"  QuadSurf:F1={statistics.fmean(per_dataset_means['quad_f1']):.3f}  AUC={statistics.fmean(per_dataset_auc_means['quad_auc']):.3f}  FDR={statistics.fmean(per_dataset_means['quad_fdr'])*100:.1f}%")
    print(f"  ExpGate: F1={statistics.fmean(per_dataset_means['qexp_f1']):.3f}  AUC={statistics.fmean(per_dataset_auc_means['qexp_auc']):.3f}  FDR={statistics.fmean(per_dataset_means['qexp_fdr'])*100:.1f}%")


if __name__ == "__main__":
    main()
