"""
Reformat MC-1 v2: increase all font sizes, improve spacing, keep ≤3 pages.
"""
from pathlib import Path
from lxml import etree
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.oxml.ns import qn
import fitz, win32com.client, pythoncom, time

SRC = Path(r'C:\amttp\research\visa\SUBMISSION_ORGANISED_BY_CATEGORY\01_Mandatory_Criteria_MC\MC-1_AMTTP_Live_Demonstration_v2.docx')
PDF = SRC.with_suffix('.pdf')

doc = Document(str(SRC))

NAVY = RGBColor(0x1a, 0x2a, 0x4a)
GRAY = RGBColor(0x44, 0x44, 0x44)

# ── Classify paragraphs by role ──────────────────────────────────────────────
# We identify paragraphs by their current bold /size signature
def is_main_title(p):
    for r in p.runs:
        if r.font.size and round(r.font.size.pt, 1) in (10.5,):
            return True
    return False

def is_section_heading(p):
    for r in p.runs:
        if r.font.size and round(r.font.size.pt, 1) == 9.5:
            return True
    return False

def is_caption(p):
    for r in p.runs:
        if r.font.size and round(r.font.size.pt, 1) == 7.0:
            return True
    return False

def has_image(p):
    return p._element.find('.//' + qn('w:drawing')) is not None

# ── Update font sizes and spacing ─────────────────────────────────────────────
for i, para in enumerate(doc.paragraphs):
    pf = para.paragraph_format
    pf.space_before = Pt(0)

    if has_image(para):
        pf.space_after = Pt(2)
        continue

    if is_main_title(para):
        # Main doc title + criteria title row
        for r in para.runs:
            r.font.size = Pt(12)
        pf.space_after = Pt(3)

    elif is_section_heading(para):
        for r in para.runs:
            r.font.size = Pt(11)
        pf.space_after = Pt(4)

    elif is_caption(para):
        for r in para.runs:
            r.font.size = Pt(8.5)
        pf.space_after = Pt(3)

    else:
        # Body text, bullet points, header rows without explicit size
        for r in para.runs:
            if r.text.strip():
                r.font.size = Pt(10)
        pf.space_after = Pt(3)

# Also fix Normal style base size so unrun paragraphs look right
doc.styles['Normal'].font.size = Pt(10)

# ── Resize images to compensate for larger text ──────────────────────────────
WP_NS = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
A_NS  = 'http://schemas.openxmlformats.org/drawingml/2006/main'
EMU   = 914400 / 2.54  # EMU per cm

# Shrink images to recover space lost to larger fonts
NEW_WIDTHS_CM = {
    0: 10.5,   # Cloudflare analytics
    1:  9.5,   # Architecture diagram (tall — keep narrow to limit height)
    2: 10.5,   # War Room
    3: 10.5,   # Reports
    4: 12.5,   # Pilot agreement (wide side-by-side image)
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

TMP = SRC.parent / ('~tmp_' + SRC.name)
doc.save(str(TMP))
print('Saved to temp.')

# ── Export + count ────────────────────────────────────────────────────────────
pythoncom.CoInitialize()
word = win32com.client.DispatchEx('Word.Application')
word.Visible = False
word.DisplayAlerts = 0
try:
    d = word.Documents.Open(str(TMP), ReadOnly=True)
    d.SaveAs2(str(PDF), FileFormat=17)
    d.Close(False)
finally:
    word.Quit()

pages = fitz.open(str(PDF)).page_count
print(f'PDF pages: {pages}  {"✓ OK" if pages <= 3 else "OVER — reduce images further"}')

import os, shutil
if pages <= 3:
    # Replace original with temp
    try:
        os.replace(str(TMP), str(SRC))
        print('Replaced original.')
    except PermissionError:
        print(f'Close the file in Word, then rename:\n  {TMP}\n→ {SRC}')
else:
    print(f'Temp saved at: {TMP}')
