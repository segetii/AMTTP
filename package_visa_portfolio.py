import os
import shutil
import zipfile
from pathlib import Path

def create_portfolio():
    base_dir = Path("C:/amttp")
    portfolio_dir = base_dir / "Global_Talent_Visa_Portfolio"
    
    # Clean up existing if any
    if portfolio_dir.exists():
        shutil.rmtree(portfolio_dir)
    portfolio_dir.mkdir(parents=True)

    # Define Evidence Categories (Tech Nation Criteria)
    categories = {
        "Evidence_1_Academic_Excellence": {
            "desc": "Optional Criteria 4: Exceptional ability in the field by academic contributions.",
            "files": [
                "papers/AMTTP_Polished_Publish.docx", # If exists
                "papers/AMTTP_ACADEMIC_ARTICLE.md",
                "papers/MATHEMATICAL_FORMULATION.md",
                "generate_paper_results.py",
                "paper_results_output.txt",
                "sota_comparison.txt"
            ],
            "dirs": ["notebooks", "plots"]
        },
        "Evidence_2_Technical_Innovation": {
            "desc": "Optional Criteria 1: Proof of innovation in the digital technology sector.",
            "files": [
                "ARCHITECTURE_DIAGRAM.md",
                "ZKNAF_ARCHITECTURE.md",
                "FCA_COMPLIANCE.md",
                "KLEROS_INTEGRATION.md",
                "LAYERZERO_INTEGRATION.md",
                "docker-compose.yml",
                "docker-compose.full.yml"
            ],
            "dirs": ["contracts", "ml", "pipeline", "udl"]
        },
        "Evidence_3_Engineering_Excellence": {
            "desc": "Optional Criteria 3: Significant technical contributions to the field.",
            "files": [
                "AMTTP_Final_Test_Report.docx",
                "AMTTP_Testing_Guide_With_Results.docx",
                "benchmark_results.txt",
                "prod_results.txt",
                "proof_test_output.txt",
                "ensemble_results.txt",
                "test_production_fpfn.py",
                "test_energy_benchmark.py"
            ],
            "dirs": ["tests", "test", "audit", "coverage"]
        },
        "Evidence_4_Product_Impact": {
            "desc": "Mandatory Criteria: Proof of recognition for work beyond the applicant's occupation / Product-led growth.",
            "files": [
                "README.md",
                "DEVELOPER_GUIDE.md",
                "QUICK_START_GUIDE.md",
                "DEPLOYMENT.md",
                "REVIEWER_GUIDE.md"
            ],
            "dirs": ["frontend", "client-sdk", "client-sdk-python", "docs"]
        }
    }

    # Create mapping document
    mapping_content = [
        "# UK Global Talent Visa (Tech Nation) - Evidence Mapping",
        "## Applicant: [Your Name]",
        "## Project: AMTTP (Anti-Money Laundering Transaction Trust Protocol) v4.0\n",
        "This portfolio contains the complete source code, architecture, and evaluation metrics for AMTTP, demonstrating exceptional talent in digital technology (Machine Learning, Blockchain, and Distributed Systems).\n"
    ]

    for cat_name, cat_data in categories.items():
        cat_dir = portfolio_dir / cat_name
        cat_dir.mkdir()
        
        mapping_content.append(f"### {cat_name.replace('_', ' ')}")
        mapping_content.append(f"**Tech Nation Criteria:** {cat_data['desc']}\n")
        mapping_content.append("**Included Artifacts:**")
        
        # Copy files
        for f in cat_data.get("files", []):
            src = base_dir / f
            if src.exists():
                shutil.copy2(src, cat_dir / src.name)
                mapping_content.append(f"- `{src.name}`")
            else:
                # Check if it's in Downloads (like the polished docx)
                if f == "papers/AMTTP_Polished_Publish.docx":
                    dl_src = Path("C:/Users/Administrator/Downloads/AMTTP_Polished_Publish.docx")
                    if dl_src.exists():
                        shutil.copy2(dl_src, cat_dir / "AMTTP_Polished_Publish.docx")
                        mapping_content.append(f"- `AMTTP_Polished_Publish.docx` (IEEE Transactions Preprint)")
        
        # Copy directories
        for d in cat_data.get("dirs", []):
            src = base_dir / d
            if src.exists() and src.is_dir():
                # Ignore node_modules, .venv, etc.
                ignore_patterns = shutil.ignore_patterns('node_modules', '.venv', '__pycache__', '.git', 'forge-cache', 'forge-out')
                shutil.copytree(src, cat_dir / src.name, ignore=ignore_patterns)
                mapping_content.append(f"- `{src.name}/` (Source Code Directory)")
                
        mapping_content.append("\n")

    # Write mapping document
    with open(portfolio_dir / "VISA_EVIDENCE_MAPPING.md", "w", encoding="utf-8") as f:
        f.write("\n".join(mapping_content))

    # Create ZIP archive
    print("Creating ZIP archive...")
    zip_path = base_dir / "AMTTP_Global_Talent_Portfolio.zip"
    if zip_path.exists():
        zip_path.unlink()
        
    shutil.make_archive(str(portfolio_dir), 'zip', portfolio_dir)
    print(f"Successfully created portfolio at: {zip_path}")
    print(f"Evidence mapping written to: {portfolio_dir / 'VISA_EVIDENCE_MAPPING.md'}")

if __name__ == "__main__":
    create_portfolio()
