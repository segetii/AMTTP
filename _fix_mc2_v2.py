from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Pt
from docx2pdf import convert
import copy, PyPDF2

path = r'C:\amttp\research\visa\SUBMISSION_ORGANISED_BY_CATEGORY\01_Mandatory_Criteria_MC\MC-2_GitHub_Contributions.docx'
doc = Document(path)
body = doc.element.body

# ---- Helper: make a plain paragraph element with text, copying rPr from a reference para ----
def make_para(text, ref_para_el, bold=False):
    new_p = OxmlElement('w:p')
    new_r = OxmlElement('w:r')
    # Copy run properties from first run of reference
    ref_runs = ref_para_el.findall('.//' + qn('w:r'))
    if ref_runs:
        ref_rpr = ref_runs[0].find(qn('w:rPr'))
        if ref_rpr is not None:
            new_rpr = copy.deepcopy(ref_rpr)
            if bold:
                b_el = OxmlElement('w:b')
                new_rpr.insert(0, b_el)
            new_r.insert(0, new_rpr)
    # Copy paragraph properties from reference
    ref_ppr = ref_para_el.find(qn('w:pPr'))
    if ref_ppr is not None:
        new_p.insert(0, copy.deepcopy(ref_ppr))
    new_t = OxmlElement('w:t')
    new_t.text = text
    new_t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    new_r.append(new_t)
    new_p.append(new_r)
    return new_p

def make_blank_para(ref_para_el):
    new_p = OxmlElement('w:p')
    ref_ppr = ref_para_el.find(qn('w:pPr'))
    if ref_ppr is not None:
        new_p.insert(0, copy.deepcopy(ref_ppr))
    return new_p

# ---- Walk body children to find TABLE 2 (index 2 among tables) ----
children = list(body)
tbl_count = 0
table2_pos = None
for i, child in enumerate(children):
    tag = child.tag.split('}')[-1]
    if tag == 'tbl':
        tbl_count += 1
        if tbl_count == 3:  # TABLE 2 is the 3rd table (0-indexed: 2)
            table2_pos = i
            print(f'Found TABLE 2 at body child index {i}')
            break

# Reference paras: use section heading P[18] for section heading style
#                  use Table 1 caption P[20] for caption style  
# We need to get these by walking body paras
para_elements = [c for c in children if c.tag.split('}')[-1] == 'p']
# P[18] = "3. Public Verification Record" (section heading) -> index 18 in top-level paras
# P[20] = "Table 1: caption" -> index 20
section_heading_ref = para_elements[18]   # "3. Public Verification Record"
caption_ref = para_elements[20]            # "Table 1: caption"
blank_ref   = para_elements[21]            # a blank para

print('Section heading ref:', ''.join(t.text or '' for t in section_heading_ref.iter(qn('w:t'))))
print('Caption ref:', ''.join(t.text or '' for t in caption_ref.iter(qn('w:t')))[:60])

# ---- 1. Insert after TABLE 2: blank + Table2 caption + blank + Section4 heading ----
table2_el = children[table2_pos]

tbl2_caption_text = (
    "Table 2: Monthly cadence (Sep 2025 \u2013 Apr 2026). November and December 2025 commits "
    "do not appear in the GitHub graph because ML model training and dataset experimentation "
    "during that period were conducted in Google Colab; the resulting artefacts were "
    "integrated into the repository from January 2026 onwards."
)
section4_text = "4. Repository Scope and Authorship"

blank1    = make_blank_para(blank_ref)
cap_para  = make_para(tbl2_caption_text, caption_ref)
blank2    = make_blank_para(blank_ref)
sec4_para = make_para(section4_text, section_heading_ref, bold=True)

# Insert after table2_el
insert_after = table2_pos
for new_el in [blank1, cap_para, blank2, sec4_para]:
    insert_after += 1
    body.insert(insert_after, new_el)

print('Inserted Table 2 caption and Section 4 heading')

# ---- 2. Remove dangling Figure 2 caption and excess blanks ----
# After insertion, re-walk to find top-level paragraphs by text
children2 = list(body)
para_elements2 = [(i, c) for i, c in enumerate(children2) if c.tag.split('}')[-1] == 'p']

to_remove = []
for idx, (body_i, p_el) in enumerate(para_elements2):
    txt = ''.join(t.text or '' for t in p_el.iter(qn('w:t'))).strip()
    # Remove dangling Figure 2 caption
    if txt.startswith('Figure 2:') and 'directory structure' in txt:
        to_remove.append((body_i, p_el, 'Figure 2 dangling caption'))

# Also remove runs of 3+ consecutive blanks (collapse to 1)
# Find all blank top-level paras
blank_runs = []
run = []
for idx, (body_i, p_el) in enumerate(para_elements2):
    txt = ''.join(t.text or '' for t in p_el.iter(qn('w:t'))).strip()
    has_img = 'graphicData' in p_el.xml
    if not txt and not has_img:
        run.append((body_i, p_el))
    else:
        if len(run) >= 2:
            # keep first blank, remove rest
            for bi, pel in run[1:]:
                to_remove.append((bi, pel, 'excess blank'))
        run = []
if len(run) >= 2:
    for bi, pel in run[1:]:
        to_remove.append((bi, pel, 'excess blank'))

# Deduplicate and sort descending so removal by element works
seen = set()
unique_remove = []
for bi, pel, reason in to_remove:
    eid = id(pel)
    if eid not in seen:
        seen.add(eid)
        unique_remove.append((bi, pel, reason))

for bi, pel, reason in unique_remove:
    print(f'Removing: {reason} -- "{("".join(t.text or "" for t in pel.iter(qn("w:t"))))[:50]}"')
    body.remove(pel)

print('Cleanup done')

# ---- 3. Fix Table 3 font (7pt -> 10pt) ----
tbl3 = doc.tables[3]
for el in tbl3._tbl.iter(qn('w:sz')):
    el.set(qn('w:val'), '20')
for el in tbl3._tbl.iter(qn('w:szCs')):
    el.set(qn('w:val'), '20')
print('Table 3 fixed to 10pt')

doc.save(path)
print('Saved, paragraphs:', len(doc.paragraphs))

convert(path, path.replace('.docx', '.pdf'))
pdf = path.replace('.docx', '.pdf')
reader = PyPDF2.PdfReader(pdf)
print(f'PDF: {len(reader.pages)} pages')
