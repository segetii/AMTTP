from pathlib import Path
import time
import fitz
import win32com.client
import pythoncom

BASE = Path(r"C:\amttp\research\visa")
UP = BASE / "Evidence Upgrade V2"
DOCX_DIR = UP / "01_UPGRADED_DOCX"
PDF_DIR = UP / "02_UPGRADED_PDF"
AUDIT_DIR = UP / "03_PAGE_AUDIT"
PDF_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

pythoncom.CoInitialize()
word = win32com.client.DispatchEx("Word.Application")
word.Visible = False
word.DisplayAlerts = 0
results = []
try:
    for docx in sorted(DOCX_DIR.glob("*.docx")):
        if docx.name.startswith("~$"):
            continue
        pdf = PDF_DIR / (docx.stem + ".pdf")
        doc = word.Documents.Open(str(docx), ReadOnly=True)
        doc.SaveAs2(str(pdf), FileFormat=17)
        doc.Close(False)
        time.sleep(0.05)
        with fitz.open(str(pdf)) as p:
            pages = p.page_count
        is_evidence = docx.name.startswith(("00_", "MC-", "OC3-", "OC4-"))
        limit_ok = (pages <= 3) if is_evidence else (pages <= 3)
        results.append((docx.name, pages, "OK" if limit_ok else "OVER_LIMIT"))
finally:
    word.Quit()

out = AUDIT_DIR / "v2_real_pdf_page_counts.txt"
with out.open("w", encoding="utf-8") as f:
    f.write("Evidence Upgrade V2 — real Word-exported PDF page counts\n")
    f.write("=" * 76 + "\n")
    for name, pages, status in results:
        f.write(f"{name:45} {pages:>2} pages  {status}\n")
    f.write("\nPDF output folder: " + str(PDF_DIR) + "\n")
print(out.read_text(encoding="utf-8"))
