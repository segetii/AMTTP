from pathlib import Path
import time
import fitz
import win32com.client
import pythoncom

BASE = Path(r"C:\amttp\research\visa")
UP = BASE / "EVIDENCE_UPGRADE"
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
        doc.SaveAs2(str(pdf), FileFormat=17)  # wdFormatPDF
        doc.Close(False)
        time.sleep(0.1)
        with fitz.open(str(pdf)) as p:
            pages = p.page_count
        results.append((docx.name, pages, pdf.name))
finally:
    word.Quit()

out = AUDIT_DIR / "real_pdf_page_counts.txt"
with out.open("w", encoding="utf-8") as f:
    f.write("Real PDF page counts (Word COM export)\n")
    f.write("=" * 70 + "\n")
    for name, pages, pdfname in results:
        status = "OK" if (name.startswith("00_") or pages <= 3) else "OVER_LIMIT"
        f.write(f"{name:45} {pages:>2} pages  {status}\n")
    f.write("\nPDF output folder: " + str(PDF_DIR) + "\n")

print(out.read_text(encoding="utf-8"))
