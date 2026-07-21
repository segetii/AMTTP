from docx import Document
from docx.oxml.ns import qn
import PyPDF2

path = r'C:\amttp\research\visa\SUBMISSION_ORGANISED_BY_CATEGORY\01_Mandatory_Criteria_MC\MC-2_GitHub_Contributions.docx'
doc = Document(path)

print(f'Paragraphs: {len(doc.paragraphs)}, Tables: {len(doc.tables)}')
print()

# Full body structure with font sizes
body = doc.element.body
para_idx = 0
tbl_idx = 0
for child in body:
    tag = child.tag.split('}')[-1]
    if tag == 'p':
        txt = ''.join(t.text or '' for t in child.iter(qn('w:t')))
        has_img = 'graphicData' in child.xml
        flag = ' [IMG]' if has_img else ''
        sizes = set()
        for rpr in child.findall('.//' + qn('w:rPr')):
            sz = rpr.find(qn('w:sz'))
            if sz is not None:
                sizes.add(int(sz.get(qn('w:val'), 0)) // 2)
        size_str = f' font={sorted(sizes)}' if sizes else ''
        txt_show = txt[:75] if txt.strip() else '[BLANK]'
        print(f'  P[{para_idx:2d}] {txt_show}{flag}{size_str}')
        para_idx += 1
    elif tag == 'tbl':
        rows = child.findall('.//' + qn('w:tr'))
        # Get header row cell texts
        header = []
        for cell in rows[0].findall('.//' + qn('w:tc')):
            header.append(''.join(t.text or '' for t in cell.iter(qn('w:t')))[:30])
        # Get cell font sizes in first data row
        sizes = set()
        for rpr in rows[0].findall('.//' + qn('w:rPr')):
            sz = rpr.find(qn('w:sz'))
            if sz is not None:
                sizes.add(int(sz.get(qn('w:val'), 0)) // 2)
        print(f'  TABLE {tbl_idx} ({len(rows)} rows) font={sorted(sizes)} header={header}')
        tbl_idx += 1

print()
print('=== IMAGES ===')
for i, p in enumerate(doc.paragraphs):
    if 'graphicData' not in p._element.xml:
        continue
    for ext in p._element.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}ext'):
        cx = int(ext.get('cx', 0))
        cy = int(ext.get('cy', 0))
        if cx > 0:
            print(f'  P[{i}] Image: {cx/914400:.2f}" x {cy/914400:.2f}"')

print()
print('=== PAGE MARGINS ===')
from docx.oxml.ns import qn as Q
for sect in doc.sections:
    print(f'  Top:{sect.top_margin.inches:.2f}" Bot:{sect.bottom_margin.inches:.2f}" Left:{sect.left_margin.inches:.2f}" Right:{sect.right_margin.inches:.2f}"')
    print(f'  Page: {sect.page_width.inches:.2f}" x {sect.page_height.inches:.2f}"')

print()
print('=== PARAGRAPH SPACING ===')
for i, p in enumerate(doc.paragraphs):
    pf = p.paragraph_format
    before = pf.space_before.pt if pf.space_before else 0
    after = pf.space_after.pt if pf.space_after else 0
    line = str(pf.line_spacing) if pf.line_spacing else 'inherit'
    if before > 0 or after > 0:
        txt = p.text[:40] if p.text.strip() else '[BLANK]'
        print(f'  P[{i}] "{txt}" before={before}pt after={after}pt line={line}')

print()
pdf = path.replace('.docx', '.pdf')
reader = PyPDF2.PdfReader(pdf)
print(f'PDF pages: {len(reader.pages)}')
