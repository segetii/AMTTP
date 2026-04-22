"""
build_unified_paper_deviation_report.py
======================================
Build a unified paper-vs-observed deviation report for:
    - ERCOT AUC target 0.9940
    - FRED AUC target 0.9999
    - Mol+ExpoGate table row (AUROC/FAR/Recall/Precision/first alarm)

Notes:
    - ERCOT observed is taken from the original supply-only ERCOT output
        (wind/solar/gas/coal/nuclear) when available.
    - FRED observed is taken from the closest available proxy in
        results/full_engine_results.json (Bank Hybrid AUC), because no explicit
        FRED-tagged JSON metric is present in C:/amttp/results.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
GSIB_DIR = Path(__file__).resolve().parent / "results" / "gsib_real"
OUT_JSON = GSIB_DIR / "unified_paper_deviation_report.json"
OUT_TXT = GSIB_DIR / "unified_paper_deviation_report.txt"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_ercot_supply_hybrid_auc(path: Path) -> float | None:
    """
    Parse the best Hybrid(Mol+Grav) AUC from ERCOT SUPPLY-ONLY section.
    """
    if not path.exists():
        return None

    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        text = raw.decode("utf-16", errors="replace")
    else:
        text = raw.decode("utf-8", errors="replace")
    text = text.replace("\x00", "")

    start = text.find("ERCOT SUPPLY-ONLY")
    if start == -1:
        return None
    end = text.find("ERCOT COMBINED", start)
    section = text[start:] if end == -1 else text[start:end]

    aucs = []
    for m in re.finditer(r"Hybrid\(Mol\+Grav\).*?AUC\s*=\s*([0-9]+\.[0-9]+)", section, flags=re.DOTALL):
        aucs.append(float(m.group(1)))

    if not aucs:
        return None
    return max(aucs)


def main() -> dict:
    targets = {
        "ercot_auc": 0.9940,
        "fred_auc": 0.9999,
        "mol_expogate": {
            "auroc": 0.867,
            "far_pct": 0.0,
            "recall_pct": 38.5,
            "precision_pct": 100.0,
            "gfc_first_alarm": "2007-Q4",
        },
    }

    ercot_src_candidates = [
        ROOT / "physics_ercot_supply_results.txt",
        ROOT / "research" / "siam-paper" / "replication_artifacts" / "tabular_run_20260421_120530" / "results" / "physics_ercot_supply_results.txt",
    ]
    ercot_src = None
    ercot_best_name = "Hybrid(Mol+Grav)"
    ercot_best_auc = None
    ercot_source_note = ""

    for cand in ercot_src_candidates:
        parsed = _parse_ercot_supply_hybrid_auc(cand)
        if parsed is not None:
            ercot_src = cand
            ercot_best_auc = parsed
            ercot_source_note = "Parsed from ERCOT supply-only original-data report."
            break

    if ercot_best_auc is None:
        # Fallback: prior prospective report path.
        ercot_src = ROOT / "results" / "ercot_prospective_results.json"
        ercot_data = _load_json(ercot_src)
        ercot_engines = ercot_data.get("engines", {})
        for name, payload in ercot_engines.items():
            auc = float(payload.get("auc", 0.0))
            if ercot_best_auc is None or auc > ercot_best_auc:
                ercot_best_auc = auc
                ercot_best_name = name
        ercot_source_note = "Fallback to prospective ERCOT JSON because supply-only report was unavailable or unparsable."

    fred_src = ROOT / "results" / "full_engine_results.json"
    fred_data = _load_json(fred_src)
    fred_proxy_auc = float(fred_data.get("Bank", {}).get("Hybrid", {}).get("auc", 0.0))

    gsib_src = GSIB_DIR / "paper_calibrated_adaptive_p99_gsib_real.json"
    gsib_data = _load_json(gsib_src)
    gsib_obs = gsib_data["results"]["posthoc_in_sample"]["Mol+ExpoGate"]["adaptive_p99"]
    gsib_obs_strict = gsib_data["results"]["strict_pre2007"]["Mol+ExpoGate"]["adaptive_p99"]

    unified = {
        "targets": targets,
        "ercot": {
            "source": str(ercot_src),
            "best_engine": ercot_best_name,
            "observed_auc": round(float(ercot_best_auc), 4),
            "delta_vs_target": round(float(ercot_best_auc) - targets["ercot_auc"], 4),
            "source_note": ercot_source_note,
        },
        "fred": {
            "source": str(fred_src),
            "observed_auc_proxy": round(fred_proxy_auc, 4),
            "proxy_note": "No explicit FRED-tagged JSON metric found under C:/amttp/results; using Bank/Hybrid AUC as closest available proxy.",
            "delta_vs_target": round(fred_proxy_auc - targets["fred_auc"], 4),
        },
        "mol_expogate": {
            "source": str(gsib_src),
            "observed_posthoc_in_sample": gsib_obs,
            "observed_strict_pre2007": gsib_obs_strict,
            "delta_posthoc_in_sample": {
                "auroc": round(float(gsib_obs["auroc"]) - targets["mol_expogate"]["auroc"], 4),
                "far_pct": round(float(gsib_obs["far_pct"]) - targets["mol_expogate"]["far_pct"], 1),
                "recall_pct": round(float(gsib_obs["recall_pct"]) - targets["mol_expogate"]["recall_pct"], 1),
                "precision_pct": round(float(gsib_obs["precision_pct"]) - targets["mol_expogate"]["precision_pct"], 1),
                "gfc_first_alarm_target": targets["mol_expogate"]["gfc_first_alarm"],
                "gfc_first_alarm_observed": gsib_obs["gfc_first_alarm"],
            },
        },
    }

    OUT_JSON.write_text(json.dumps(unified, indent=2), encoding="utf-8")

    lines = []
    lines.append("Unified Paper Deviation Report")
    lines.append("=")
    lines.append("")
    lines.append("ERCOT AUC")
    lines.append(
        f"  target={targets['ercot_auc']:.4f}  observed={unified['ercot']['observed_auc']:.4f} "
        f"(best engine: {ercot_best_name})  delta={unified['ercot']['delta_vs_target']:+.4f}"
    )
    lines.append(f"  source={ercot_src}")
    lines.append(f"  note={ercot_source_note}")
    lines.append("")
    lines.append("FRED AUC")
    lines.append(
        f"  target={targets['fred_auc']:.4f}  observed(proxy)={unified['fred']['observed_auc_proxy']:.4f} "
        f"delta={unified['fred']['delta_vs_target']:+.4f}"
    )
    lines.append(f"  source={fred_src}")
    lines.append(f"  note={unified['fred']['proxy_note']}")
    lines.append("")
    lines.append("Mol+ExpoGate (Adaptive P99 table row)")
    d = unified["mol_expogate"]["delta_posthoc_in_sample"]
    obs = unified["mol_expogate"]["observed_posthoc_in_sample"]
    lines.append(
        f"  AUROC: target={targets['mol_expogate']['auroc']:.4f} observed={obs['auroc']:.4f} delta={d['auroc']:+.4f}"
    )
    lines.append(
        f"  FAR%:  target={targets['mol_expogate']['far_pct']:.1f} observed={obs['far_pct']:.1f} delta={d['far_pct']:+.1f}"
    )
    lines.append(
        f"  Recall%: target={targets['mol_expogate']['recall_pct']:.1f} observed={obs['recall_pct']:.1f} delta={d['recall_pct']:+.1f}"
    )
    lines.append(
        f"  Prec.%:  target={targets['mol_expogate']['precision_pct']:.1f} observed={obs['precision_pct']:.1f} delta={d['precision_pct']:+.1f}"
    )
    lines.append(
        f"  GFC first: target={d['gfc_first_alarm_target']} observed={d['gfc_first_alarm_observed']}"
    )
    lines.append(f"  source={gsib_src}")

    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_TXT}")
    return unified


if __name__ == "__main__":
    main()
