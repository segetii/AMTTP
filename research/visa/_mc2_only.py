"""Run MC-2 upgrade only — reads original, saves to temp, replaces if closed."""
from pathlib import Path
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.enum.text import WD_ALIGN_PARAGRAPH
import fitz, win32com.client, pythoncom, os

FOLDER = Path(r'C:\amttp\research\visa\SUBMISSION_ORGANISED_BY_CATEGORY\01_Mandatory_Criteria_MC')
NAVY  = RGBColor(0x1a, 0x2a, 0x4a)
WHITE = RGBColor(0xff, 0xff, 0xff)

def has_image(p):
    return p._element.find('.//' + qn('w:drawing')) is not None

def bump_fonts(doc):
    for para in doc.paragraphs:
        para.paragraph_format.space_before = Pt(0)
        if has_image(para):
            para.paragraph_format.space_after = Pt(1)
            continue
        for r in para.runs:
            if not r.text.strip(): continue
            sz = r.font.size.pt if r.font.size else None
            if sz is None:        r.font.size = Pt(9)
            elif sz <= 7.5:       r.font.size = Pt(8)
            elif sz <= 8.5:       r.font.size = Pt(9)
            elif sz <= 9.5:       r.font.size = Pt(10.5)
            elif sz <= 11.0:      r.font.size = Pt(11.5)
        para.paragraph_format.space_after = Pt(1 if has_image(para) else 2)
    doc.styles['Normal'].font.size = Pt(9)

def make_verif_table(doc, rows):
    tbl = doc.add_table(rows=len(rows), cols=3)
    tbl.style = 'Table Grid'
    col_ws = [Cm(4.2), Cm(6.5), Cm(7.2)]
    for row in tbl.rows:
        for i, cell in enumerate(row.cells):
            cell.width = col_ws[i]
    for r_idx, (c1, c2, c3) in enumerate(rows):
        is_hdr = r_idx == 0
        for c_idx, text in enumerate([c1, c2, c3]):
            cell = tbl.rows[r_idx].cells[c_idx]
            cell.text = ''
            p = cell.paragraphs[0]
            run = p.add_run(text)
            run.bold = is_hdr
            run.font.size = Pt(8.5)
            run.font.color.rgb = WHITE if is_hdr else RGBColor(0x1a, 0x1a, 0x1a)
            tc = cell._tc
            tcPr = tc.get_or_add_tcPr()
            tcMar = OxmlElement('w:tcMar')
            for side in ('w:top','w:bottom','w:left','w:right'):
                m = OxmlElement(side)
                m.set(qn('w:w'), '55'); m.set(qn('w:type'), 'dxa')
                tcMar.append(m)
            tcPr.append(tcMar)
            fill = '1a2a4a' if is_hdr else ('f0f4f8' if r_idx % 2 == 0 else 'ffffff')
            shd = OxmlElement('w:shd')
            shd.set(qn('w:val'),'clear'); shd.set(qn('w:color'),'auto')
            shd.set(qn('w:fill'), fill)
            tcPr.append(shd)
    return tbl

def insert_table_after_para(doc, para_idx, rows):
    tbl = make_verif_table(doc, rows)
    tbl_elem = tbl._tbl
    doc.element.body.remove(tbl_elem)
    doc.paragraphs[para_idx]._element.addnext(tbl_elem)

def shrink_images(doc, width_map):
    WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
    A  = 'http://schemas.openxmlformats.org/drawingml/2006/main'
    EMU = 914400 / 2.54
    for i, drw in enumerate(doc.element.body.findall('.//' + qn('w:drawing'))):
        if i not in width_map: continue
        inline = drw.find(f'{{{WP}}}inline')
        if inline is None: continue
        extent = inline.find(f'{{{WP}}}extent')
        if extent is None: continue
        cx, cy = int(extent.get('cx',0)), int(extent.get('cy',0))
        if not cx: continue
        new_cx = int(width_map[i] * EMU)
        new_cy = int(new_cx * cy / cx)
        extent.set('cx', str(new_cx)); extent.set('cy', str(new_cy))
        for ext in inline.findall(f'.//{{{A}}}ext'):
            ext.set('cx', str(new_cx)); ext.set('cy', str(new_cy))
        print(f'  img {i}: {cx/EMU:.1f}x{cy/EMU:.1f} → {new_cx/EMU:.1f}x{new_cy/EMU:.1f}cm')

# ── MC-2 ─────────────────────────────────────────────────────────────────────
mc2_src = FOLDER / 'MC-2_GitHub_Contributions.docx'
mc2_pdf = FOLDER / 'MC-2_GitHub_Contributions.pdf'
doc2 = Document(str(mc2_src))

# Remove redundant / MC-1-duplicate paragraphs
remove_mc2 = [
    'Delivered components: live public platform at amttp.com',
    'The table below summarises the public development timeline.',
    'Development Activity by Month:',
    'The codebase spans five production programming languages used simultaneously.',
]
shorten_mc2 = {
    'Technical significance: Delivering a full-stack compliance platform':
    'Every commit, timestamp, and per-file diff is permanently public at '
    'github.com/segetii/AMTTP — authorship is verifiable without relying on any claim made here.',
}
for p in list(doc2.paragraphs):
    for marker in remove_mc2:
        if p.text.strip().startswith(marker):
            p._element.getparent().remove(p._element)
            print(f'  removed: {p.text[:65]}')
            break
    for marker, replacement in shorten_mc2.items():
        if p.text.strip().startswith(marker):
            for r in p.runs: r.text = ''
            if p.runs: p.runs[0].text = replacement
            else: p.add_run(replacement)
            print(f'  shortened: {marker[:50]}')
            break

# Remove monorepo directory code-block table
for tbl in list(doc2.tables):
    cell_text = tbl.rows[0].cells[0].text if tbl.rows else ''
    if 'AMTTP/' in cell_text and '+--' in cell_text:
        tbl._tbl.getparent().remove(tbl._tbl)
        print('  removed: monorepo directory code-block table')

# Insert verification table after para [6]
mc2_rows = [
    ('Claim', 'Evidence', 'Independent verification'),
    ('Sole authorship',       '361 commits from single GitHub account',   'github.com/segetii/AMTTP — public, diff-inspectable'),
    ('Sustained development', '8 months continuous (Sep 2025–Apr 2026)',  'Monthly commit cadence table (Table 2)'),
    ('Nov–Dec gap explained', 'ML training in Google Colab (not GitHub)', 'Google Drive auto-timestamped folder names'),
    ('Cross-domain scope',    '5 languages, 14+ independent services',    'Per-domain public repo URLs — Table 3 below'),
]
insert_table_after_para(doc2, 6, mc2_rows)
bump_fonts(doc2)
shrink_images(doc2, {0: 11.0, 1: 10.5})

p = doc2.add_paragraph()
p.paragraph_format.space_before = Pt(3)
p.paragraph_format.space_after  = Pt(0)
r1 = p.add_run('Anti-loophole note: ')
r1.bold = True; r1.font.size = Pt(9); r1.font.color.rgb = NAVY
r2 = p.add_run(
    'This exhibit does not rely on the applicant\'s description of activity. '
    'Every commit, timestamp, and per-file diff is independently inspectable at '
    'github.com/segetii/AMTTP. The November–December gap is corroborated by '
    'Google-timestamped Colab artefact folder names (auto-generated ISO timestamps), '
    'not self-reported dates.')
r2.bold = False; r2.font.size = Pt(9)

tmp = FOLDER / '~mc2_final.docx'
doc2.save(str(tmp))

pythoncom.CoInitialize()
word = win32com.client.DispatchEx('Word.Application')
word.Visible = False; word.DisplayAlerts = 0
try:
    d = word.Documents.Open(str(tmp), ReadOnly=True)
    d.SaveAs2(str(mc2_pdf), FileFormat=17)
    d.Close(False)
finally:
    word.Quit()

pages = fitz.open(str(mc2_pdf)).page_count
print(f'MC-2 PDF pages: {pages} {"✓" if pages<=3 else "OVER"}')

if pages <= 3:
    try:
        os.replace(str(tmp), str(mc2_src))
        print(f'Done: {mc2_src.name}')
    except PermissionError:
        print(f'Still locked — close Word and rename:\n  {tmp.name}\n→ {mc2_src.name}')
