"""
Increase image sizes in MC-1 v2, especially the pilot agreement.
Works from the temp (font-increased) version.
"""
from pathlib import Path
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
import fitz, win32com.client, pythoncom

FOLDER = Path(r'C:\amttp\research\visa\SUBMISSION_ORGANISED_BY_CATEGORY\01_Mandatory_Criteria_MC')
TMP_SRC = FOLDER / '~tmp_MC-1_AMTTP_Live_Demonstration_v2.docx'
OUT     = FOLDER / 'MC-1_AMTTP_Live_Demonstration_v2.docx'
PDF     = FOLDER / 'MC-1_AMTTP_Live_Demonstration_v2.pdf'

doc = Document(str(TMP_SRC))

WP_NS = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
A_NS  = 'http://schemas.openxmlformats.org/drawingml/2006/main'
EMU   = 914400 / 2.54

# ── Resize images ─────────────────────────────────────────────────────────────
# Usable width = 21cm - 1.55cm - 1.55cm = 17.9cm
# Drawing 1 (architecture) is very tall (aspect ~1.45), keep narrow
NEW_WIDTHS_CM = {
    0: 13.0,   # Cloudflare analytics
    1:  7.0,   # Architecture diagram (very tall — keep narrow to reduce height)
    2: 13.0,   # War Room
    3: 13.0,   # Reports
    4: 16.5,   # Pilot agreement — nearly full usable width
}

drawings = doc.element.body.findall('.//' + qn('w:drawing'))
for i, drw in enumerate(drawings):
    inline = drw.find(f'{{{WP_NS}}}inline')
    if inline is None:
        continue
    extent = inline.find(f'{{{WP_NS}}}extent')
    if extent is None:
        continue
    cx = int(extent.get('cx', 0))
    cy = int(extent.get('cy', 0))
    if cx == 0:
        continue
    tw = NEW_WIDTHS_CM.get(i)
    if tw is None:
        continue
    aspect = cy / cx
    new_cx = int(tw * EMU)
    new_cy = int(new_cx * aspect)
    extent.set('cx', str(new_cx))
    extent.set('cy', str(new_cy))
    for ext in inline.findall(f'.//{{{A_NS}}}ext'):
        ext.set('cx', str(new_cx))
        ext.set('cy', str(new_cy))
    print(f'Drawing {i}: {cx/EMU:.1f}x{cy/EMU:.1f}cm → {tw:.1f}x{new_cy/EMU:.1f}cm')

# ── Tighten spacing to recover vertical space ─────────────────────────────────
def has_image(p):
    return p._element.find('.//' + qn('w:drawing')) is not None

for para in doc.paragraphs:
    pf = para.paragraph_format
    pf.space_before = Pt(0)
    if has_image(para):
        pf.space_after = Pt(1)
    elif any(r.font.size and round(r.font.size.pt, 1) == 11.0 for r in para.runs):
        # Section headings
        pf.space_after = Pt(3)
    elif any(r.font.size and round(r.font.size.pt, 1) == 8.5 for r in para.runs):
        # Captions
        pf.space_after = Pt(2)
    else:
        pf.space_after = Pt(2)

doc.save(str(OUT))
print(f'Saved to: {OUT.name}')

# ── Export PDF + page count ───────────────────────────────────────────────────
pythoncom.CoInitialize()
word = win32com.client.DispatchEx('Word.Application')
word.Visible = False
word.DisplayAlerts = 0
try:
    d = word.Documents.Open(str(OUT), ReadOnly=True)
    d.SaveAs2(str(PDF), FileFormat=17)
    d.Close(False)
finally:
    word.Quit()

pages = fitz.open(str(PDF)).page_count
print(f'PDF pages: {pages}  {"✓ 3 pages OK" if pages <= 3 else "OVER — need further adjustment"}')
