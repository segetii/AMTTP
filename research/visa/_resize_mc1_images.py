"""
Aggressive resize of all images in MC-1 v2 to get to 3 pages.
"""
from pathlib import Path
import time
from lxml import etree
from docx import Document
from docx.shared import Pt, Cm
import fitz, win32com.client, pythoncom

SRC = Path(r'C:\amttp\research\visa\SUBMISSION_ORGANISED_BY_CATEGORY\01_Mandatory_Criteria_MC\MC-1_AMTTP_Live_Demonstration_v2.docx')
PDF = SRC.with_suffix('.pdf')

doc = Document(str(SRC))

WP_NS = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
A_NS  = 'http://schemas.openxmlformats.org/drawingml/2006/main'
from docx.oxml.ns import qn

EMU = 914400 / 2.54  # EMU per cm

# Target widths in cm for each drawing (0-indexed)
# Drawing 1 is the tall architecture diagram — cap its width to reduce height
TARGETS = {
    0: 12.0,   # Cloudflare analytics
    1: 11.0,   # Architecture diagram (19.7cm tall -> ~15.8cm tall at 11cm wide)
    2: 12.0,   # War Room
    3: 12.0,   # Reports
    4: 13.5,   # Pilot agreement
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
    aspect = cy / cx
    target_w_cm = TARGETS.get(i)
    if target_w_cm is None:
        continue
    new_cx = int(target_w_cm * EMU)
    new_cy = int(new_cx * aspect)
    extent.set('cx', str(new_cx))
    extent.set('cy', str(new_cy))
    for ext in inline.findall(f'.//{{{A_NS}}}ext'):
        ext.set('cx', str(new_cx))
        ext.set('cy', str(new_cy))
    print(f'Drawing {i}: {cx/EMU:.1f}x{cy/EMU:.1f}cm → {new_cx/EMU:.1f}x{new_cy/EMU:.1f}cm')

doc.save(str(SRC))
print('Saved.')

# Export and count
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
print(f'PDF pages: {pages}  {"✓ OK" if pages <= 3 else "OVER"}')
