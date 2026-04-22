#!/usr/bin/env python3
"""Archive tabular SIAM replication assets (no CuPy/NS path required).

This bundles:
- SIAM manuscript sources
- CPU experiment scripts from research/udl/energyv3
- Generated text logs for causal/physics/ERCOT benchmarks
- A manifest with environment + git metadata
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import platform
import shutil
import subprocess
from pathlib import Path

SIAM_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SIAM_ROOT.parent.parent

SOURCE_FILES = [
    SIAM_ROOT / "main.tex",
    SIAM_ROOT / "appendix_computational_ns.tex",
    SIAM_ROOT / "siam.bst",
    SIAM_ROOT / "siamltex.cls",
    REPO_ROOT / "research" / "udl" / "energyv3" / "test_causal_physics.py",
    REPO_ROOT / "research" / "udl" / "energyv3" / "test_physics_engine_results.py",
    REPO_ROOT / "research" / "udl" / "energyv3" / "test_physics_ercot_supply.py",
    REPO_ROOT / "research" / "udl" / "energyv3" / "test_full_engine_results.py",
]

RESULT_GLOBS = [
    str(REPO_ROOT / "causal_physics_results.txt"),
    str(REPO_ROOT / "physics_engine_results.txt"),
    str(REPO_ROOT / "physics_ercot_supply_results.txt"),
    str(REPO_ROOT / "full_engine_results.txt"),
    str(SIAM_ROOT / "*.pdf"),
    str(SIAM_ROOT / "*.png"),
]


def _run_cmd(cmd: list[str]) -> str:
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
        return out.strip()
    except Exception:
        return ""


def _copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", default="replication_artifacts")
    parser.add_argument("--archive-name", default="")
    args = parser.parse_args()

    now = dt.datetime.now(dt.timezone.utc)
    ts = now.strftime("%Y%m%d_%H%M%S")

    out_root = SIAM_ROOT / args.output_root
    run_dir = out_root / f"tabular_run_{ts}"
    src_dir = run_dir / "source"
    res_dir = run_dir / "results"
    src_dir.mkdir(parents=True, exist_ok=True)
    res_dir.mkdir(parents=True, exist_ok=True)

    src_manifest: list[str] = []
    for p in SOURCE_FILES:
        if p.exists():
            rel = p.relative_to(REPO_ROOT)
            _copy(p, src_dir / rel)
            src_manifest.append(str(rel).replace("\\", "/"))

    res_manifest: list[str] = []
    for pattern in RESULT_GLOBS:
        for item in glob.glob(pattern):
            p = Path(item)
            if p.is_file():
                rel = p.relative_to(REPO_ROOT)
                _copy(p, res_dir / rel)
                res_manifest.append(str(rel).replace("\\", "/"))

    manifest = {
        "timestamp_utc": now.isoformat(),
        "repo_root": str(REPO_ROOT),
        "python": _run_cmd(["py", "-3", "-V"]),
        "platform": platform.platform(),
        "git_commit": _run_cmd(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"]),
        "source_files": sorted(src_manifest),
        "result_files": sorted(set(res_manifest)),
        "notes": "Tabular replication bundle for WorldBank/FDIC/ERCOT CPU scripts.",
    }

    manifest_path = run_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    if args.archive_name:
        arch_base = Path(args.archive_name)
        if not arch_base.is_absolute():
            arch_base = (SIAM_ROOT / arch_base).resolve()
        arch_base = arch_base.with_suffix("")
    else:
        arch_base = (out_root / f"siam_tabular_repro_{ts}").resolve()

    arch_base.parent.mkdir(parents=True, exist_ok=True)
    archive = shutil.make_archive(str(arch_base), "zip", root_dir=str(run_dir))

    print(f"Run directory: {run_dir}")
    print(f"Manifest: {manifest_path}")
    print(f"Archive: {archive}")
    print(f"Source files: {len(src_manifest)}")
    print(f"Result files: {len(set(res_manifest))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
