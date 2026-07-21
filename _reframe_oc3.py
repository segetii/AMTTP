from docx import Document
from docx.oxml.ns import qn
import shutil

path = r'C:\amttp\research\visa\Evidence Upgrade V2\00_CURRENT_COPY\OC3-1_ML_Pipeline.docx'
doc = Document(path)

def set_para_text(para, new_text):
    """Replace full paragraph text, preserving run formatting of first run."""
    # Keep first run, clear all others
    runs = para.runs
    if not runs:
        # Paragraph has no runs — write direct w:t
        from docx.oxml import OxmlElement
        r = OxmlElement('w:r')
        t = OxmlElement('w:t')
        t.text = new_text
        t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        r.append(t)
        para._element.append(r)
        return
    # Set first run text
    for t in runs[0]._element.iter(qn('w:t')):
        t.text = new_text
        t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        break
    # Remove extra runs
    for run in runs[1:]:
        runs[0]._element.getparent().remove(run._element)

# ========================================================
# P[5] Executive Summary line - remove hard metric lead
# ========================================================
p5 = doc.paragraphs[5]
set_para_text(p5,
    "Executive Summary: I designed, trained, and deployed the AI fraud-detection engine used by AMTTP. "
    "My role covered every stage of the ML lifecycle: feature engineering, training, evaluation, "
    "knowledge distillation, and production deployment. "
    "The system runs as a nine-service compliance orchestrator combining gradient-boosted ML, "
    "graph-network analysis, and deterministic AML policy evaluation — designed for CPU-only deployment "
    "with no specialist hardware requirement."
)
print('P[5] done')

# ========================================================
# P[6] Validation Results line - soften extreme metrics
# ========================================================
p6 = doc.paragraphs[6]
set_para_text(p6,
    "Validation Results: Benchmark evaluation on 625,168 real Ethereum transactions (372 confirmed "
    "fraudulent) produced very high ROC-AUC scores across all student models (see Table 1), "
    "no false positives observed during evaluation, and strong PR-AUC and MCC scores. "
    "Temporal holdout and no-leakage scripts are available in the public repository for independent "
    "verification."
)
print('P[6] done')

# ========================================================
# P[9] First body paragraph - reframe Teacher Stack up front
# ========================================================
p9 = doc.paragraphs[9]
set_para_text(p9,
    "The AMTTP compliance engine is built as a composite decision stack, not a standalone ML classifier. "
    "The teacher stack combines gradient-boosted models, graph-network analysis via GraphSAGE, and "
    "deterministic AML policy rule evaluation into a single orchestrated compliance framework. "
    "Student models are distilled from this composite system to enable CPU-only deployment while "
    "preserving most operational performance characteristics. "
    "The production student ensemble achieves near-perfect ROC-AUC on the evaluated benchmark dataset "
    "(exact figures in Table 1), reflecting the quality of the composite teacher signal rather than "
    "any single isolated ML model."
)
print('P[9] done')

# ========================================================
# P[17] "Precision: 100%, Zero false positives..."
# ========================================================
p17 = doc.paragraphs[17]
set_para_text(p17,
    "Precision: No false positives were observed during benchmark evaluation — "
    "362 confirmed fraud cases were correctly flagged across a dataset of 625,168 transactions. "
    "Because the teacher stack incorporates deterministic AML rules alongside ML scoring, precision "
    "is structurally reinforced beyond what a pure ML classifier would achieve."
)
print('P[17] done')

# ========================================================
# P[18] PR-AUC line - minor tweak
# ========================================================
p18 = doc.paragraphs[18]
set_para_text(p18,
    "PR-AUC: 0.9997 — Strong precision-recall balance; critical in compliance contexts where false "
    "positives unnecessarily freeze legitimate transactions."
)
print('P[18] done')

# ========================================================
# P[19] MCC line - keep as is, already reasonable
# ========================================================

# ========================================================
# P[21] No hindsight bias - tighten
# ========================================================
p21 = doc.paragraphs[21]
set_para_text(p21,
    "No evaluation leakage: The teacher stack was trained on the full labelled dataset; "
    "student distillation and deployment evaluation used temporal holdout methodology. "
    "Dedicated audit scripts (test_no_leakage*.py) are publicly available in the repository "
    "and confirm no data leakage in the student evaluation pipeline."
)
print('P[21] done')

# ========================================================
# P[24] Figure 2 caption - reframe Teacher 1.0
# ========================================================
p24 = doc.paragraphs[24]
set_para_text(p24,
    "Figure 2: evaluation_results_v2.json open in VS Code — raw benchmark output from the compliance "
    "orchestration evaluation run. The teacher stack score reflects the composite system (ML + graph + "
    "policy rules combined); the student ensemble score reflects the distilled deployable model. "
    "Full benchmark scripts and outputs are publicly reproducible from the repository."
)
print('P[24] done')

# ========================================================
# P[27] Live microservice paragraph - soften latency claim, fix FCA
# ========================================================
p27 = doc.paragraphs[27]
set_para_text(p27,
    "The risk engine runs as a live FastAPI microservice (port 8000). Transaction payloads arrive from "
    "the Express.js Oracle Service and are forwarded to the compliance orchestrator. "
    "The orchestrator fans out to all nine services simultaneously using async aiohttp, then aggregates "
    "the composite verdict — delivering real-time orchestration while each service remains independently "
    "replaceable and scalable. "
    "Structured JSON logging and a dedicated Explainability Service provide per-decision audit trails "
    "designed to support the auditability expectations common in regulated financial environments."
)
print('P[27] done')

# ========================================================
# P[28] Technical significance - biggest change: de-emphasise metrics
# ========================================================
p28 = doc.paragraphs[28]
set_para_text(p28,
    "Technical significance: The value of this system is not the benchmark metrics alone. "
    "It is the combination of: (1) a hybrid compliance-intelligence architecture integrating ML, "
    "graph networks, and deterministic policy rules; (2) knowledge distillation enabling "
    "CPU-only deployment with no specialist hardware; (3) a nine-service orchestration layer "
    "providing independently deployable, auditable components; and (4) explainability infrastructure "
    "that surfaces per-decision factor weights for regulatory review. "
    "This makes institutional-grade compliance enforcement accessible without a GPU infrastructure budget."
)
print('P[28] done')

# ========================================================
# P[33] Table 2 caption - fix FCA language
# ========================================================
p33 = doc.paragraphs[33]
set_para_text(p33,
    "Table 2: All nine compliance microservices — each independently deployable, each sole-authored. "
    "The Policy Engine and Explainability Service are specifically designed to support the auditability "
    "expectations common in regulated financial environments, including change-management traceability."
)
print('P[33] done')

# ========================================================
# P[34] Final paragraph - remove "FCA" regulatory authority claims
# ========================================================
p34 = doc.paragraphs[34]
set_para_text(p34,
    "All nine services use FastAPI with Pydantic validation, async request handling, and structured JSON "
    "logging. The architecture is designed for independent horizontal scaling: any individual service "
    "can be upgraded, replaced, or replicated without modifying the others. "
    "This reflects a deliberate infrastructure engineering decision prioritising operational resilience "
    "and regulatory auditability over monolithic simplicity."
)
print('P[34] done')

doc.save(path)
print('\nSaved to primary copy.')

# Sync to other copies
copies = [
    r'C:\amttp\research\visa\Evidence Upgrade V2\01_UPGRADED_DOCX\OC3-1_ML_Pipeline.docx',
    r'C:\amttp\research\visa\Evidence Upgrade V2\01_UPGRADED_DOCX\SUBMISSION_ORGANISED_BY_CATEGORY\03_Optional_Criteria_OC\OC3-1_ML_Pipeline.docx',
]
import os
for c in copies:
    if os.path.exists(os.path.dirname(c)):
        shutil.copy2(path, c)
        print(f'Synced: {c}')
    else:
        print(f'SKIP (dir missing): {c}')
