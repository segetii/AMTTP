from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Inches
from docx2pdf import convert
import copy, PyPDF2

path = r'C:\amttp\research\visa\Evidence Upgrade V2\00_CURRENT_COPY\OC3-1_ML_Pipeline.docx'
doc = Document(path)

# ── helpers ───────────────────────────────────────────────────────────────────
def make_run_with_text(text, sz_pt=10, bold=False):
    r = OxmlElement('w:r')
    rpr = OxmlElement('w:rPr')
    sz = OxmlElement('w:sz');   sz.set(qn('w:val'),   str(sz_pt * 2)); rpr.append(sz)
    szcs = OxmlElement('w:szCs'); szcs.set(qn('w:val'), str(sz_pt * 2)); rpr.append(szcs)
    if bold:
        rpr.append(OxmlElement('w:b'))
    r.append(rpr)
    t = OxmlElement('w:t'); t.text = text
    t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    r.append(t)
    return r

def make_plain_para(text='', sz_pt=10, bold=False):
    p = OxmlElement('w:p')
    ppr = OxmlElement('w:pPr')
    spng = OxmlElement('w:spacing'); spng.set(qn('w:after'), '40'); ppr.append(spng)
    p.append(ppr)
    if text:
        p.append(make_run_with_text(text, sz_pt=sz_pt, bold=bold))
    return p

def set_cell(cell, text, bold=False, sz_pt=10, center=False, fill=None):
    tc = cell._tc
    for p in tc.findall(qn('w:p')): tc.remove(p)
    p = OxmlElement('w:p')
    if center:
        ppr = OxmlElement('w:pPr'); jc = OxmlElement('w:jc')
        jc.set(qn('w:val'), 'center'); ppr.append(jc); p.append(ppr)
    p.append(make_run_with_text(text, sz_pt=sz_pt, bold=bold))
    if fill:
        tcpr = tc.find(qn('w:tcPr'))
        if tcpr is None: tcpr = OxmlElement('w:tcPr'); tc.insert(0, tcpr)
        shd = OxmlElement('w:shd')
        shd.set(qn('w:val'), 'clear'); shd.set(qn('w:color'), 'auto')
        shd.set(qn('w:fill'), fill); tcpr.append(shd)
    if fill and fill != 'FFFFFF':
        # White text on dark fill
        rpr = p.find('.//' + qn('w:rPr'))
        if rpr is None: rpr = OxmlElement('w:rPr'); p.find(qn('w:r')).insert(0, rpr)
        col = OxmlElement('w:color'); col.set(qn('w:val'), 'FFFFFF'); rpr.append(col)
    tc.append(p)

# ═══════════════════════════════════════════════════════════════════════════
# 1. BUILD ARCHITECTURE TABLE
# ═══════════════════════════════════════════════════════════════════════════
arch_table = doc.add_table(rows=6, cols=4)
arch_table.style = 'Table Grid'

headers = ['Stage', 'Component', 'Technology', 'Purpose']
for i, h in enumerate(headers):
    set_cell(arch_table.cell(0, i), h, bold=True, sz_pt=10, center=True, fill='1F4E79')

rows_data = [
    ('1 — Data',
     '625,168 Ethereum transactions',
     'Historical on-chain records\n372 confirmed fraudulent',
     'Labelled training corpus'),
    ('2 — Teacher Stack',
     'Composite compliance framework',
     'XGBoost + LightGBM + GraphSAGE + AML policy rules',
     'Generates rich soft-label signal; combines ML, graph topology, and deterministic rules'),
    ('3 — Distillation',
     'Knowledge transfer',
     'Soft-label distillation from teacher → student',
     'Compresses composite intelligence into lightweight CPU-deployable models'),
    ('4 — Student Ensemble',
     'Deployable inference layer',
     'Student LightGBM + Student XGBoost weighted ensemble',
     'CPU-only — no GPU required; near-teacher performance at fraction of cost'),
    ('5 — Production',
     'Live FastAPI microservice',
     'Port 8000 · async · Pydantic-validated',
     'Real-time fraud score delivered to compliance orchestrator (port 8007)'),
]
row_fills = ['D6E4F0', 'BDD7EE', 'D6E4F0', 'BDD7EE', 'D6E4F0']
for r_idx, (row_data, fill) in enumerate(zip(rows_data, row_fills), start=1):
    for c_idx, text in enumerate(row_data):
        set_cell(arch_table.cell(r_idx, c_idx), text,
                 bold=(c_idx == 0), sz_pt=10, fill=fill)

# Set column widths
for row in arch_table.rows:
    row.cells[0].width = Inches(1.0)
    row.cells[1].width = Inches(1.5)
    row.cells[2].width = Inches(2.3)
    row.cells[3].width = Inches(2.2)

# ── Move table to AFTER P[9] ──────────────────────────────────────────────────
body = doc.element.body
children = list(body)
tbl_el = arch_table._tbl
body.remove(tbl_el)

target = 'The AMTTP compliance engine is built as a composite decision stack'
insert_after_body_idx = None
para_count = 0
for i, child in enumerate(children):
    if child.tag.split('}')[-1] == 'p':
        txt = ''.join(t.text or '' for t in child.iter(qn('w:t')))
        if target in txt:
            insert_after_body_idx = i
            print(f'Anchor at body[{i}] — para index {para_count}')
            break
        para_count += 1

cap_text = (
    "Table: ML Knowledge Distillation Pipeline — five stages from labelled on-chain data "
    "through composite teacher training, soft-label distillation, and student ensemble, "
    "to CPU-only live microservice deployment."
)
blank1   = make_plain_para()
cap_para = make_plain_para(cap_text, sz_pt=10)
blank2   = make_plain_para()

pos = insert_after_body_idx + 1
for el in [blank1, tbl_el, cap_para, blank2]:
    body.insert(pos, el); pos += 1

print('Architecture table inserted')

# ═══════════════════════════════════════════════════════════════════════════
# 2. RESTORE blank P[17] and P[18] (Precision + PR-AUC paragraphs)
# ═══════════════════════════════════════════════════════════════════════════
# After +4 offset from table insertion, originals at P[17/18] are now P[21/22] ish.
# Find them by being consecutive blanks just before MCC paragraph.
all_paras = doc.paragraphs
mcc_idx = None
for i, p in enumerate(all_paras):
    if p.text.startswith('MCC: 0.9906'):
        mcc_idx = i; print(f'MCC para at index {i}')
        break

precision_text = (
    "Precision: No false positives were observed during benchmark evaluation — "
    "362 confirmed fraud cases correctly flagged across 625,168 transactions. "
    "The teacher stack's deterministic AML rules structurally reinforce precision "
    "beyond what a pure ML classifier would achieve."
)
pr_auc_text = (
    "PR-AUC: 0.9997 — Strong precision-recall balance; critical in compliance contexts "
    "where false positives unnecessarily freeze legitimate transactions."
)

def fill_blank_para(para, text, sz_pt=10):
    """Replace blank paragraph content entirely."""
    p_el = para._element
    # Remove any existing runs
    for r in p_el.findall(qn('w:r')): p_el.remove(r)
    p_el.append(make_run_with_text(text, sz_pt=sz_pt))

if mcc_idx and mcc_idx >= 2:
    p1 = all_paras[mcc_idx - 2]
    p2 = all_paras[mcc_idx - 1]
    print(f'P[mcc-2] = "{p1.text[:50]}"')
    print(f'P[mcc-1] = "{p2.text[:50]}"')
    if not p1.text.strip():
        fill_blank_para(p1, precision_text)
        print('Restored Precision para')
    if not p2.text.strip():
        fill_blank_para(p2, pr_auc_text)
        print('Restored PR-AUC para')

doc.save(path)
print('Saved. Paragraphs:', len(doc.paragraphs))

# Sync + PDF
import shutil, os
for c in [r'C:\amttp\research\visa\Evidence Upgrade V2\01_UPGRADED_DOCX\OC3-1_ML_Pipeline.docx']:
    shutil.copy2(path, c); print('Synced:', c)

convert(path, path.replace('.docx', '.pdf'))
reader = PyPDF2.PdfReader(path.replace('.docx', '.pdf'))
print(f'PDF: {len(reader.pages)} pages')
