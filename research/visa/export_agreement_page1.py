"""
Export page 1 of the both-signed agreement as PNG using Word COM.
Falls back to LibreOffice if Word COM fails.
"""
import os, sys, subprocess

DOCX = r"C:\Users\Administrator\Documents\Segun Odeyemi's PILOT EVALUATION AGREEMENT - BOTH SIGNED.docx"
OUT_PNG = r"C:\amttp\research\visa\images\pilot_agreement_signed.png"
OUT_PDF = r"C:\amttp\research\visa\pilot_agreement_signed.pdf"

os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)

success = False

# ── Method 1: Word COM → PDF → page 1 PNG via pdf2image ─────────────────────
try:
    import win32com.client
    import pythoncom
    pythoncom.CoInitialize()
    word = win32com.client.Dispatch('Word.Application')
    word.Visible = False
    doc = word.Documents.Open(DOCX)
    doc.SaveAs2(OUT_PDF, FileFormat=17)  # wdFormatPDF
    doc.Close(False)
    word.Quit()
    print('PDF exported via Word COM')

    from pdf2image import convert_from_path
    pages = convert_from_path(OUT_PDF, dpi=200, first_page=1, last_page=1)
    pages[0].save(OUT_PNG, 'PNG')
    print(f'Page 1 PNG saved: {OUT_PNG}  size={pages[0].size}')
    success = True
except Exception as e:
    print(f'Word COM/pdf2image failed: {e}')

# ── Method 2: docx2pdf (uses Word internally) ───────────────────────────────
if not success:
    try:
        from docx2pdf import convert
        convert(DOCX, OUT_PDF)
        print('PDF exported via docx2pdf')
        from pdf2image import convert_from_path
        pages = convert_from_path(OUT_PDF, dpi=200, first_page=1, last_page=1)
        pages[0].save(OUT_PNG, 'PNG')
        print(f'Page 1 PNG saved: {OUT_PNG}  size={pages[0].size}')
        success = True
    except Exception as e:
        print(f'docx2pdf failed: {e}')

# ── Method 3: LibreOffice ────────────────────────────────────────────────────
if not success:
    try:
        import glob
        lo_paths = [
            r'C:\Program Files\LibreOffice\program\soffice.exe',
            r'C:\Program Files (x86)\LibreOffice\program\soffice.exe',
        ]
        lo = next((p for p in lo_paths if os.path.exists(p)), None)
        if lo:
            out_dir = os.path.dirname(OUT_PDF)
            result = subprocess.run(
                [lo, '--headless', '--convert-to', 'pdf', '--outdir', out_dir, DOCX],
                capture_output=True, timeout=60
            )
            print(result.stdout.decode(), result.stderr.decode())
            # Find the PDF
            pdfs = glob.glob(os.path.join(out_dir, '*.pdf'))
            pdf = max(pdfs, key=os.path.getmtime) if pdfs else None
            if pdf:
                from pdf2image import convert_from_path
                pages = convert_from_path(pdf, dpi=200, first_page=1, last_page=1)
                pages[0].save(OUT_PNG, 'PNG')
                print(f'Page 1 PNG saved via LibreOffice: {OUT_PNG}')
                success = True
    except Exception as e:
        print(f'LibreOffice failed: {e}')

if not success:
    print('ERROR: All methods failed. Please open the DOCX in Word and Save As PDF manually,')
    print(f'then run: py -3 -c "from pdf2image import convert_from_path; p=convert_from_path(r\'{OUT_PDF}\',dpi=200)[0]; p.save(r\'{OUT_PNG}\')"')
    sys.exit(1)
else:
    print('Done!')
