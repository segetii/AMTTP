"""
Build Tech Nation evidence folder structure for UK Global Talent Visa.
Maps to: MC (Mandatory) + OC1 (Innovation) + OC3 (Technical Contribution)
Route: Exceptional Promise
"""
import shutil
from pathlib import Path

BASE = Path(r"C:\amttp")
TN = BASE / "technation"

# Clean previous build
if TN.exists():
    shutil.rmtree(TN)

IGNORE = shutil.ignore_patterns(
    "node_modules", ".venv", "__pycache__", ".git",
    "forge-cache", "forge-out", "*.pyc", ".env",
    "foundry-bin", "crytic-export", "cache",
)

# ── Structure ──────────────────────────────────────────────────────
structure = {
    "01_Mandatory_Criteria": {
        "01_Personal_Statement": {
            "files": [
                BASE / "PERSONAL_STATEMENT_V2.md",
            ],
        },
        "02_Recommendation_Letters": {
            # Placeholder folder — user will add signed PDFs
            "files": [],
            "readme": (
                "Place your three signed recommendation letters here:\n"
                "  1. Letter_1_Prof_Computer_Science.pdf  (Research Validator)\n"
                "  2. Letter_2_VP_Sabre_West_Africa.pdf   (Industry Impact)\n"
                "  3. Letter_3_Prof_EE_MIS_Director.pdf   (Trajectory & Character)\n\n"
                "Each letter MUST:\n"
                "  - Be on official letterhead\n"
                "  - Use the phrase 'exceptional promise'\n"
                "  - Reference AMTTP / UDL by name with specific technical details\n"
            ),
        },
        "03_System_Overview_and_Role": {
            "files": [
                BASE / "README.md",
                BASE / "ARCHITECTURE_DIAGRAM.md",
                BASE / "DEPLOYMENT.md",
                BASE / "REVIEWER_GUIDE.md",
                BASE / "DEVELOPER_GUIDE.md",
                BASE / "QUICK_START_GUIDE.md",
                BASE / "docker-compose.full.yml",
                BASE / "Dockerfile",
            ],
        },
    },

    "02_OC1_Innovation": {
        "01_AMTTP_Architecture_and_zkNAF": {
            "files": [
                BASE / "ZKNAF_ARCHITECTURE.md",
                BASE / "FCA_COMPLIANCE.md",
                BASE / "KLEROS_INTEGRATION.md",
                BASE / "LAYERZERO_INTEGRATION.md",
            ],
            "dirs": [
                ("contracts", BASE / "contracts"),  # 41 Solidity files
            ],
        },
        "02_Universal_Deviation_Law": {
            "dirs": [
                ("udl", BASE / "udl"),  # 38 Python modules
            ],
        },
        "03_IEEE_Research_Paper": {
            "files": [
                Path(r"C:\Users\Administrator\Desktop\amttp_techrxiv.pdf"),
            ],
        },
    },

    "03_OC3_Technical_Contribution": {
        "01_ML_Benchmarks_and_Evaluation": {
            "files": [
                BASE / "benchmark_results.txt",
                BASE / "ensemble_results.txt",
                BASE / "prod_results.txt",
                BASE / "paper_results_output.txt",
                BASE / "sota_comparison.txt",
                BASE / "generate_paper_results.py",
            ],
            "dirs": [
                ("notebooks", BASE / "notebooks"),
            ],
        },
        "02_Testing_and_QA": {
            "files": [
                BASE / "AMTTP_Final_Test_Report.docx",
                BASE / "AMTTP_Testing_Guide_With_Results.docx",
                BASE / "TESTING_GUIDE.md",
                BASE / "proof_test_output.txt",
                BASE / "test_production_fpfn.py",
                BASE / "test_energy_benchmark.py",
                BASE / "test_energy_vs_sota.py",
                BASE / "test_fp_fn.py",
                BASE / "test_noregress.py",
            ],
            "dirs": [
                ("tests", BASE / "tests"),
                ("test", BASE / "test"),
            ],
        },
        "03_Smart_Contracts_and_Infrastructure": {
            "files": [
                BASE / "docker-compose.yml",
                BASE / "docker-compose.production.yml",
                BASE / "Makefile",
                BASE / "foundry.toml",
                BASE / "hardhat.config.cjs",
            ],
            "dirs": [
                ("audit", BASE / "audit"),
            ],
        },
    },

    "04_Supporting_Materials": {
        "01_Screenshots": {
            "dirs": [
                ("screenshots", BASE / "screenshots"),
            ],
        },
        "02_Architecture_Diagrams": {
            "files": [
                p for p in Path(r"C:\Users\Administrator\Downloads").glob("AMTTP_Architecture_v4*")
            ],
        },
        "03_ML_Pipeline": {
            "dirs": [
                ("ml", BASE / "ml"),
                ("pipeline", BASE / "pipeline"),
            ],
        },
        "04_Client_SDKs": {
            "dirs": [
                ("client-sdk", BASE / "client-sdk"),
                ("client-sdk-python", BASE / "client-sdk-python"),
            ],
        },
    },
}


def build(parent: Path, tree: dict):
    for name, content in tree.items():
        folder = parent / name
        folder.mkdir(parents=True, exist_ok=True)

        if isinstance(content, dict) and ("files" in content or "dirs" in content or "readme" in content):
            # Leaf node — copy files and dirs
            for f in content.get("files", []):
                if f.exists():
                    shutil.copy2(f, folder / f.name)
                    print(f"  + {f.name}")
                else:
                    print(f"  ! MISSING: {f}")

            for dir_name, dir_path in content.get("dirs", []):
                if dir_path.exists() and dir_path.is_dir():
                    dest = folder / dir_name
                    shutil.copytree(dir_path, dest, ignore=IGNORE)
                    count = sum(1 for _ in dest.rglob("*") if _.is_file())
                    print(f"  + {dir_name}/ ({count} files)")
                else:
                    print(f"  ! MISSING DIR: {dir_path}")

            if "readme" in content:
                (folder / "README.txt").write_text(content["readme"], encoding="utf-8")
                print(f"  + README.txt (instructions)")
        else:
            # Branch node — recurse
            print(f"\n[{name}]")
            build(folder, content)


print("Building Tech Nation evidence folder...\n")
print("[technation]")
build(TN, structure)

# Count totals
total_files = sum(1 for _ in TN.rglob("*") if _.is_file())
total_dirs = sum(1 for _ in TN.rglob("*") if _.is_dir())
print(f"\nDone. {total_files} files in {total_dirs} folders.")
print(f"Location: {TN}")
