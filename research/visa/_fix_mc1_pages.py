"""
Rebuild MC-1_v2 with tight spacing so it fits in 3 pages.
Strategy:
  1. Re-open v2, strip all empty paragraphs
  2. Set space_before=0, space_after=Pt(1) on every paragraph
  3. Resize the pilot image inline shape via XML to Cm(15.5) wide
  4. Export + verify <= 3 pages
"""
from pathlib import Path
import copy, time
from lxml import etree
from docx import Document
from docx.shared import Pt, Cm, Emu
import fitz, win32com.client, pythoncom

SRC = Path(r'C:\amttp\research\visa\SUBMISSION_ORGANISED_BY_CATEGORY\01_Mandatory_Criteria_MC\MC-1_AMTTP_Live_Demonstration_v2.docx')

doc = Document(str(SRC))

# ── 1. Remove empty paragraphs ────────────────────────────────────────────────
from docx.oxml.ns import qn
body = doc.element.body
to_remove = []
for p in body.findall(qn('w:p')):
    texts = ''.join(n.text or '' for n in p.iter(qn('w:t')))
    # Check if paragraph has inline shapes (images) — keep those
    has_drawing = p.find('.//' + qn('w:drawing')) is not None
    has_table = False  # tables are separate
    if not texts.strip() and not has_drawing:
        to_remove.append(p)

print(f'Removing {len(to_remove)} empty paragraphs')
for p in to_remove:
    body.remove(p)

# ── 2. Tighten paragraph spacing ──────────────────────────────────────────────
from docx.oxml import OxmlElement
for para in doc.paragraphs:
    pf = para.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after  = Pt(1)

# ── 3. Resize the pilot image (largest inline shape) ─────────────────────────
# Find all inline shapes and identify the pilot one (widest)
# python-docx inline_shapes are in order of document appearance
# Original had 4 images; pilot is index 4 (0-based)
EMU_PER_CM = 914400 / 2.54
TARGET_W = int(15.5 * EMU_PER_CM)   # 15.5 cm in EMU

drawings = doc.element.body.findall('.//' + qn('w:drawing'))
print(f'Total drawings: {len(drawings)}')

# For each drawing, look for wp:inline/wp:extent and a:ext
WP_NS  = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
A_NS   = 'http://schemas.openxmlformats.org/drawingml/2006/main'

for i, drw in enumerate(drawings):
    # wp:inline
    inline = drw.find(f'{{{WP_NS}}}inline')
    if inline is None:
        continue
    extent = inline.find(f'{{{WP_NS}}}extent')
    if extent is None:
        continue
    cx = int(extent.get('cx', 0))
    cy = int(extent.get('cy', 0))
    print(f'  Drawing {i}: cx={cx} ({cx/914400*2.54:.1f}cm) cy={cy} ({cy/914400*2.54:.1f}cm)')

    # Find if this is the pilot image (it's the last / the 5th one, index 4)
    if i == 4:
        aspect = cy / cx if cx else 1
        new_cx = TARGET_W
        new_cy = int(new_cx * aspect)
        extent.set('cx', str(new_cx))
        extent.set('cy', str(new_cy))
        # Also update a:ext inside graphic data
        for ext in inline.findall(f'.//{{{A_NS}}}ext'):
            ext.set('cx', str(new_cx))
            ext.set('cy', str(new_cy))
        print(f'  → Resized pilot image to {new_cx/914400*2.54:.1f}cm x {new_cy/914400*2.54:.1f}cm')

doc.save(str(SRC))
print('Saved.')

# ── 4. Export to PDF and check pages ─────────────────────────────────────────
PDF = SRC.with_suffix('.pdf')
pythoncom.CoInitialize()
word = win32com.client.DispatchEx('Word.Application')
word.Visible = False
word.DisplayAlerts = 0
try:
    d = word.Documents.Open(str(SRC), ReadOnly=True)
    d.SaveAs2(str(PDF), FileFormat=17)
    d.Close(False)
finally:
    word.Quit()

pages = fitz.open(str(PDF)).page_count
print(f'PDF pages: {pages}  {"OK" if pages <= 3 else "OVER — need more trimming"}')
