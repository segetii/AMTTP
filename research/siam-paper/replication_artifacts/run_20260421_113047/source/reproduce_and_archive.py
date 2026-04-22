#!/usr/bin/env python3
"""
Reproduce SIAM paper experiments and archive code/results.

Usage examples:
  python reproduce_and_archive.py --archive-only
  python reproduce_and_archive.py --run-phases nu-critical road-forward full-stress
  python reproduce_and_archive.py --run-phases nu-critical --archive-name siam_repro.zip

Notes:
- The three experiment scripts were authored for a shared Colab session.
  This runner executes selected scripts in a single Python process via runpy
  so class/state definitions can be reused across phases.
- GPU/CuPy-heavy runs can be long. Use --archive-only to package current state.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import glob
import json
import os
import platform
import runpy
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PHASE_TO_SCRIPT = {
    "nu-critical": ROOT / "nu_critical_experiment.py",
    "road-forward": ROOT / "road_forward_experiments.py",
    "full-stress": ROOT / "full_stress_test.py",
}

EXPECTED_OUTPUT_GLOBS = [
    "nu_critical_artifacts/**",
    "road_forward_results.json",
    "road_forward_experiments.png",
    "road_forward_experiments.pdf",
    "full_stress_test_results.json",
    "full_stress_test.png",
    "full_stress_test.pdf",
    "main.pdf",
    "compile_out*.txt",
    "*.pdf",
    "*.png",
    "*.txt",
    "*.json",
]

SOURCE_GLOBS = [
    "main.tex",
    "appendix_computational_ns.tex",
    "siam.bst",
    "siamltex.cls",
    "nu_critical_experiment.py",
    "road_forward_experiments.py",
    "full_stress_test.py",
    "reproduce_and_archive.py",
]


def _run_cmd(cmd: list[str]) -> str:
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
        return out.strip()
    except Exception:
        return ""


def _safe_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)


def _collect_files(patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        for p in glob.glob(str(ROOT / pattern), recursive=True):
            pp = Path(p)
            if pp.exists():
                files.append(pp)
    # Stable unique ordering
    uniq = sorted(set(files), key=lambda x: str(x).lower())
    return uniq


def run_phase(script_path: Path, log_path: Path, shared_globals: dict) -> dict:
    started = time.time()
    status = "ok"
    error = ""

    with log_path.open("w", encoding="utf-8", errors="replace") as log_f:
        print(f"[phase] script={script_path}", file=log_f)
        print(f"[phase] started={dt.datetime.utcnow().isoformat()}Z", file=log_f)
        try:
            with contextlib.redirect_stdout(log_f), contextlib.redirect_stderr(log_f):
                runpy.run_path(str(script_path), init_globals=shared_globals)
        except Exception as ex:  # noqa: BLE001
            status = "failed"
            error = f"{type(ex).__name__}: {ex}"
            print(f"[phase] ERROR: {error}", file=log_f)

    return {
        "script": str(script_path),
        "status": status,
        "error": error,
        "duration_seconds": round(time.time() - started, 3),
        "log": str(log_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reproduce SIAM paper runs and archive outputs")
    parser.add_argument(
        "--run-phases",
        nargs="+",
        choices=list(PHASE_TO_SCRIPT.keys()),
        default=[],
        help="Experiment phases to execute in-order",
    )
    parser.add_argument(
        "--archive-only",
        action="store_true",
        help="Skip execution and archive current code/results",
    )
    parser.add_argument(
        "--archive-name",
        default="",
        help="Optional output zip path (default: siam_repro_<timestamp>.zip)",
    )
    parser.add_argument(
        "--output-root",
        default="replication_artifacts",
        help="Directory for manifests, logs, staged files, and zip",
    )

    args = parser.parse_args()

    if not args.archive_only and not args.run_phases:
        parser.error("Specify --archive-only or at least one phase in --run-phases")

    now_utc = dt.datetime.now(dt.timezone.utc)
    ts = now_utc.strftime("%Y%m%d_%H%M%S")
    output_root = (ROOT / args.output_root).resolve()
    run_dir = output_root / f"run_{ts}"
    logs_dir = run_dir / "logs"
    src_dir = run_dir / "source"
    results_dir = run_dir / "results"
    logs_dir.mkdir(parents=True, exist_ok=True)
    src_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict = {
        "timestamp_utc": now_utc.isoformat(),
        "root": str(ROOT),
        "python": sys.version,
        "platform": platform.platform(),
        "git_commit": _run_cmd(["git", "-C", str(ROOT), "rev-parse", "HEAD"]),
        "git_status_short": _run_cmd(["git", "-C", str(ROOT), "status", "--short"]),
        "execution": {
            "archive_only": bool(args.archive_only),
            "phases": args.run_phases,
            "phase_results": [],
        },
        "artifacts": {
            "source_files": [],
            "result_files": [],
        },
    }

    # Execute requested phases in a shared interpreter context.
    if not args.archive_only:
        shared_globals: dict = {"__name__": "__main__"}
        for phase in args.run_phases:
            script_path = PHASE_TO_SCRIPT[phase]
            log_path = logs_dir / f"{phase}.log"
            phase_result = run_phase(script_path, log_path, shared_globals)
            phase_result["phase"] = phase
            manifest["execution"]["phase_results"].append(phase_result)

    # Stage source files
    for pattern in SOURCE_GLOBS:
        for p in glob.glob(str(ROOT / pattern), recursive=True):
            pp = Path(p)
            rel = pp.relative_to(ROOT)
            dst = src_dir / rel
            _safe_copy(pp, dst)
            manifest["artifacts"]["source_files"].append(str(rel).replace("\\", "/"))

    # Stage result files
    result_files = _collect_files(EXPECTED_OUTPUT_GLOBS)
    for p in result_files:
        rel = p.relative_to(ROOT)
        dst = results_dir / rel
        _safe_copy(p, dst)
        manifest["artifacts"]["result_files"].append(str(rel).replace("\\", "/"))

    # Write manifest
    manifest_path = run_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # Build zip archive
    if args.archive_name:
        archive_path = Path(args.archive_name)
        if not archive_path.is_absolute():
            archive_path = (ROOT / archive_path).resolve()
        archive_base = archive_path.with_suffix("")
    else:
        archive_base = (output_root / f"siam_repro_{ts}").resolve()

    archive_base.parent.mkdir(parents=True, exist_ok=True)
    archive_file = shutil.make_archive(str(archive_base), "zip", root_dir=str(run_dir))

    print("Reproduction/archive complete")
    print(f"Run directory: {run_dir}")
    print(f"Manifest: {manifest_path}")
    print(f"Archive: {archive_file}")
    print(f"Staged source files: {len(manifest['artifacts']['source_files'])}")
    print(f"Staged result files: {len(manifest['artifacts']['result_files'])}")

    # Non-zero exit if any requested phase failed
    if not args.archive_only:
        any_failed = any(
            r.get("status") != "ok"
            for r in manifest["execution"].get("phase_results", [])
        )
        return 1 if any_failed else 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
