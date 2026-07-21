"""
Convert all deployed evidence PDFs to DOCX.
Also cleans up LaTeX auxiliary scatter files (.aux, .log, .out).
Run from: C:\amttp\research\visa\
"""
import os
import glob
import shutil
from pathlib import Path
from pdf2docx import Converter

BASE    = Path(__file__).parent
SUB_DIR = BASE / "SUBMISSION_ORGANISED_BY_CATEGORY"
DOCX_DIR = BASE / "EVIDENCE_DOCX_COPIES"
DOCX_DIR.mkdir(exist_ok=True)

# Map: source PDF -> output DOCX name
PDF_MAP = {
    SUB_DIR / "01_Mandatory_Criteria_MC"  / "MC-1_AMTTP_Live_Demonstration.pdf"  : "MC-1_AMTTP_Live_Demonstration.docx",
    SUB_DIR / "01_Mandatory_Criteria_MC"  / "MC-2_GitHub_Contributions.pdf"       : "MC-2_GitHub_Contributions.docx",
    SUB_DIR / "01_Mandatory_Criteria_MC"  / "MC-3_Smart_Contracts.pdf"            : "MC-3_Smart_Contracts.docx",
    SUB_DIR / "02_Optional_Criteria_3_OC3"/ "OC3-1_ML_Pipeline.pdf"              : "OC3-1_ML_Pipeline.docx",
    SUB_DIR / "02_Optional_Criteria_3_OC3"/ "OC3-2_War_Room_Dashboard.pdf"        : "OC3-2_War_Room_Dashboard.docx",
    SUB_DIR / "02_Optional_Criteria_3_OC3"/ "OC3-3_CrossChain_SDK.pdf"            : "OC3-3_CrossChain_SDK.docx",
    SUB_DIR / "02_Optional_Criteria_3_OC3"/ "OC3-4_Security_Auditing.pdf"         : "OC3-4_Security_Auditing.docx",
    SUB_DIR / "03_Optional_Criteria_4_OC4"/ "OC4-1_BSDT_Research.pdf"            : "OC4-1_BSDT_Research.docx",
    SUB_DIR / "03_Optional_Criteria_4_OC4"/ "OC4-2_Academic_Publications.pdf"     : "OC4-2_Academic_Publications.docx",
    SUB_DIR / "03_Optional_Criteria_4_OC4"/ "OC4-3_Academic_Adoption.pdf"         : "OC4-3_Academic_Adoption.docx",
    SUB_DIR / "04_Supporting_Evidence"    / "Personal_Statement_Final.pdf"         : "Personal_Statement_Final.docx",
    SUB_DIR / "04_Supporting_Evidence"    / "CV_Odeyemi_Olusegun_Israel.pdf"       : "CV_Odeyemi_Olusegun_Israel.docx",
    SUB_DIR / "04_Supporting_Evidence"    / "Supporting_IP_Patent.pdf"             : "Supporting_IP_Patent.docx",
    SUB_DIR / "00_Recommendation_Letters" / "Letter_A_Ogunjuyigbe_Corrected.pdf"   : "Letter_A_Ogunjuyigbe.docx",
    SUB_DIR / "00_Recommendation_Letters" / "Letter_B_Ajagbe.pdf"                  : "Letter_B_Ajagbe.docx",
}

print("=" * 60)
print("Converting PDFs to DOCX")
print("=" * 60)

ok = 0
fail = 0
for pdf_path, docx_name in PDF_MAP.items():
    docx_path = DOCX_DIR / docx_name
    if not pdf_path.exists():
        print(f"  SKIP (not found): {pdf_path.name}")
        continue
    try:
        cv = Converter(str(pdf_path))
        cv.convert(str(docx_path), start=0, end=None)
        cv.close()
        print(f"  OK  {docx_name}")
        ok += 1
    except Exception as e:
        print(f"  FAIL {docx_name}: {e}")
        fail += 1

print()
print(f"Converted: {ok}  |  Failed: {fail}")
print(f"DOCX files in: {DOCX_DIR}")

# ── Clean up LaTeX scatter files ────────────────────────────────────────────
print()
print("=" * 60)
print("Cleaning LaTeX auxiliary files")
print("=" * 60)

LATEX_JUNK = ["*.aux", "*.log", "*.out", "*.synctex.gz", "*.toc", "*.fls", "*.fdb_latexmk"]
removed = 0
for pattern in LATEX_JUNK:
    for f in BASE.glob(pattern):
        f.unlink()
        removed += 1

print(f"  Removed {removed} auxiliary files")
print()
print("Done.")
