"""
Upgrade MC-2 and MC-3 in SUBMISSION_ORGANISED_BY_CATEGORY:
1. Bump fonts to match MC-1 (10pt body, 11pt headings, 8.5pt captions)
2. Insert verification table after header block
3. Append anti-loophole note
4. Export + verify <= 3 pages each
"""
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

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def has_image(p):
    return p._element.find('.//' + qn('w:drawing')) is not None

def bump_fonts(doc):
    """Increase all font sizes to match MC-1 style."""
    for para in doc.paragraphs:
        pf = para.paragraph_format
        pf.space_before = Pt(0)
        if has_image(para):
            pf.space_after = Pt(1)
            continue
        for r in para.runs:
            if not r.text.strip():
                continue
            sz = r.font.size.pt if r.font.size else None
            if sz is None:
                r.font.size = Pt(10)
            elif sz <= 7.5:      # captions
                r.font.size = Pt(8)
            elif sz <= 8.5:      # body / bullets
                r.font.size = Pt(9)
            elif sz <= 9.5:      # section headings
                r.font.size = Pt(10.5)
            elif sz <= 11.0:     # main title
                r.font.size = Pt(11.5)
        if has_image(para):
            pf.space_after = Pt(1)
        else:
            pf.space_after = Pt(2)
    doc.styles['Normal'].font.size = Pt(9)

def make_verif_table(doc, rows):
    """Build a navy-header 3-col verification table."""
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
            # padding
            tcMar = OxmlElement('w:tcMar')
            for side in ('w:top','w:bottom','w:left','w:right'):
                m = OxmlElement(side)
                m.set(qn('w:w'), '55'); m.set(qn('w:type'), 'dxa')
                tcMar.append(m)
            tcPr.append(tcMar)
            # background
            fill = '1a2a4a' if is_hdr else ('f0f4f8' if r_idx % 2 == 0 else 'ffffff')
            shd = OxmlElement('w:shd')
            shd.set(qn('w:val'),'clear'); shd.set(qn('w:color'),'auto')
            shd.set(qn('w:fill'), fill)
            tcPr.append(shd)
    return tbl

def insert_table_after_para(doc, para_idx, rows):
    """Insert verification table after paragraphs[para_idx]."""
    tbl = make_verif_table(doc, rows)
    tbl_elem = tbl._tbl
    body = doc.element.body
    body.remove(tbl_elem)
    doc.paragraphs[para_idx]._element.addnext(tbl_elem)

def append_loophole(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after  = Pt(0)
    r1 = p.add_run('Anti-loophole note: ')
    r1.bold = True; r1.font.size = Pt(10); r1.font.color.rgb = NAVY
    r2 = p.add_run(text)
    r2.bold = False; r2.font.size = Pt(10)

def shrink_images(doc, width_map):
    """Resize drawings by index. width_map = {idx: cm}"""
    WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
    A  = 'http://schemas.openxmlformats.org/drawingml/2006/main'
    EMU = 914400 / 2.54
    drawings = doc.element.body.findall('.//' + qn('w:drawing'))
    for i, drw in enumerate(drawings):
        if i not in width_map: continue
        inline = drw.find(f'{{{WP}}}inline')
        if not inline: continue
        extent = inline.find(f'{{{WP}}}extent')
        if not extent: continue
        cx, cy = int(extent.get('cx',0)), int(extent.get('cy',0))
        if not cx: continue
        new_cx = int(width_map[i] * EMU)
        new_cy = int(new_cx * cy / cx)
        extent.set('cx', str(new_cx)); extent.set('cy', str(new_cy))
        for ext in inline.findall(f'.//{{{A}}}ext'):
            ext.set('cx', str(new_cx)); ext.set('cy', str(new_cy))
        print(f'  img {i}: {cx/EMU:.1f}x{cy/EMU:.1f} → {new_cx/EMU:.1f}x{new_cy/EMU:.1f}cm')

def export_and_count(src_path, pdf_path):
    pythoncom.CoInitialize()
    word = win32com.client.DispatchEx('Word.Application')
    word.Visible = False; word.DisplayAlerts = 0
    try:
        d = word.Documents.Open(str(src_path), ReadOnly=True)
        d.SaveAs2(str(pdf_path), FileFormat=17)
        d.Close(False)
    finally:
        word.Quit()
    return fitz.open(str(pdf_path)).page_count

def save_and_check(doc, src, pdf, label):
    tmp = src.parent / f'~upg_{src.name}'
    doc.save(str(tmp))
    pages = export_and_count(tmp, pdf)
    print(f'{label}: {pages} pages {"✓" if pages<=3 else "OVER"}')
    if pages <= 3:
        try:
            os.replace(str(tmp), str(src))
            print(f'  Saved: {src.name}')
        except PermissionError:
            print(f'  Close in Word then rename: {tmp.name} → {src.name}')
    else:
        print(f'  Temp kept at: {tmp.name}')
    return pages

# ──────────────────────────────────────────────────────────────────────────────
# MC-2
# ──────────────────────────────────────────────────────────────────────────────
print('=== MC-2 ===')
mc2_src = FOLDER / 'MC-2_GitHub_Contributions.docx'
mc2_pdf = FOLDER / 'MC-2_GitHub_Contributions.pdf'
doc2 = Document(str(mc2_src))

# Remove redundant paragraphs that duplicate MC-1:
# Para [21]: "Delivered components: live public platform at amttp.com (1,220 visitors...)"
# Para [27]: opening "Technical significance: Delivering a full-stack compliance..." sentence
# Work by matching text to avoid index drift
remove_mc2 = [
    'Delivered components: live public platform at amttp.com',
    # Redundant intro paragraphs — table headings speak for themselves
    'The table below summarises the public development timeline.',
    'Development Activity by Month:',
    # Redundant section 6 intro — Table 4 is self-explanatory
    'The codebase spans five production programming languages used simultaneously.',
]
shorten_mc2 = {
    # Replace verbose para with just the verification sentence
    'Technical significance: Delivering a full-stack compliance platform':
    'Every commit, timestamp, and per-file diff is permanently public at '
    'github.com/segetii/AMTTP — authorship is verifiable without relying on any claim made here.',
}
for p in list(doc2.paragraphs):
    for marker in remove_mc2:
        if p.text.strip().startswith(marker):
            p._element.getparent().remove(p._element)
            print(f'  MC-2 removed: {p.text[:60]}')
            break
    for marker, replacement in shorten_mc2.items():
        if p.text.strip().startswith(marker):
            for r in p.runs:
                r.text = ''
            if p.runs:
                p.runs[0].text = replacement
            else:
                p.add_run(replacement)
            print(f'  MC-2 shortened: {marker[:50]}')
            break

# Also remove Table 3 (index 3 in original = monorepo directory code block — unreadable)
# After deletions above, find the table with monorepo content and remove it
for tbl in list(doc2.tables):
    cell_text = tbl.rows[0].cells[0].text if tbl.rows else ''
    if 'AMTTP/' in cell_text and '+--' in cell_text:
        tbl._tbl.getparent().remove(tbl._tbl)
        print('  MC-2 removed: monorepo directory code-block table')

# Verification table — insert after para [6] (first exec summary body paragraph)
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

append_loophole(doc2,
    'This exhibit does not rely on the applicant\'s description of activity. '
    'Every commit, timestamp, and per-file diff is independently inspectable at '
    'github.com/segetii/AMTTP. The November–December gap is corroborated by '
    'Google-timestamped Colab artefact folder names (auto-generated ISO timestamps), '
    'not self-reported dates.')

save_and_check(doc2, mc2_src, mc2_pdf, 'MC-2')

# ──────────────────────────────────────────────────────────────────────────────
# MC-3
# ──────────────────────────────────────────────────────────────────────────────
print()
print('=== MC-3 ===')
mc3_src = FOLDER / 'MC-3_Smart_Contracts.docx'
mc3_pdf = FOLDER / 'MC-3_Smart_Contracts.pdf'
doc3 = Document(str(mc3_src))

# Remove Section 4 "Technical Significance" — 4 bullets that repeat the exec summary
# They start with these markers:
remove_mc3 = [
    '4. Technical Significance',
    '10 deployed contracts, 2 production cycles:',
    'Autonomous compliance enforcement:',
    'Independently verifiable: Contract addresses',
    'Test-driven, not just compiled:',
    # Also remove the War Room mention from Figure 1 caption (MC-1 territory)
    # and the verbose "Verification summary" which repeats para [26]
    'Verification summary: Two full production deployment cycles',
]
body3 = doc3.element.body
for p in list(doc3.paragraphs):
    for marker in remove_mc3:
        if p.text.strip().startswith(marker):
            p._element.getparent().remove(p._element)
            print(f'  MC-3 removed: {p.text[:70]}')
            break

# Verification table — insert after para [6] (first exec summary body paragraph)
mc3_rows = [
    ('Claim', 'Evidence', 'Independent verification'),
    ('Contracts deployed',    '10 contracts, 2 deployment cycles',              'sepolia.etherscan.io — immutable public blockchain'),
    ('Sole authorship',       'Single deployer wallet 0xBc270F0c…527CaF23F',   'Etherscan Contract Creator field'),
    ('Test-driven',           '74 files compiled, 8 integration tests passing', 'Hardhat screenshot — timestamped output'),
    ('ZK privacy layer',      '3 ZK-SNARK verifier contracts, Apr 2026',        'Contract addresses in Table 1 below'),
]
insert_table_after_para(doc3, 6, mc3_rows)

bump_fonts(doc3)
shrink_images(doc3, {0: 11.0, 1: 11.0, 2: 11.0})

append_loophole(doc3,
    'This exhibit does not rely on code screenshots alone. Every contract address '
    'maps to an independently verifiable public blockchain record at sepolia.etherscan.io. '
    'Deployer wallet, deployment timestamps, and verified source code are all '
    'publicly inspectable without trusting any claim made in this document.')

save_and_check(doc3, mc3_src, mc3_pdf, 'MC-3')
