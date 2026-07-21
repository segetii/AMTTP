from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt, Inches
from docx2pdf import convert
import shutil

path = r'C:\amttp\research\visa\SUBMISSION_ORGANISED_BY_CATEGORY\01_Mandatory_Criteria_MC\MC-2_GitHub_Contributions.docx'
doc = Document(path)

# --- 1. Increase all explicit font sizes by +2pt (= +4 half-pts in w:val) ---
MIN_SIZE = 8   # don't touch anything smaller than 8pt
for el in doc.element.body.iter(qn('w:sz')):
    val = el.get(qn('w:val'))
    if val:
        half_pts = int(val)
        if half_pts >= MIN_SIZE * 2:
            el.set(qn('w:val'), str(half_pts + 4))  # +2pt
for el in doc.element.body.iter(qn('w:szCs')):
    val = el.get(qn('w:val'))
    if val:
        half_pts = int(val)
        if half_pts >= MIN_SIZE * 2:
            el.set(qn('w:val'), str(half_pts + 4))  # +2pt

# Update Normal style base font
normal = doc.styles['Normal']
if normal.font.size:
    normal.font.size = Pt(normal.font.size.pt + 2)
else:
    normal.font.size = Pt(11)

print('Font sizes increased by 2pt')

# --- 2. Scale images to 5.5" wide, preserve aspect ratio ---
TARGET_WIDTH_EMU = int(5.5 * 914400)  # 5.5 inches in EMU

for p in doc.paragraphs:
    if 'graphicData' not in p._element.xml:
        continue
    for ext in p._element.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}ext'):
        cx = int(ext.get('cx', 0))
        cy = int(ext.get('cy', 0))
        if cx > 0 and cy > 0:
            ratio = cy / cx
            new_cx = TARGET_WIDTH_EMU
            new_cy = int(new_cx * ratio)
            ext.set('cx', str(new_cx))
            ext.set('cy', str(new_cy))
            print(f'Image resized: {cx/914400:.2f}" -> {new_cx/914400:.2f}" (h: {cy/914400:.2f}" -> {new_cy/914400:.2f}")')

doc.save(path)
print('Saved')

# Export PDF
pdf = path.replace('.docx', '.pdf')
convert(path, pdf)
import PyPDF2
reader = PyPDF2.PdfReader(pdf)
print(f'PDF exported: {len(reader.pages)} pages')
