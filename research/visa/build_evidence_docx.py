"""
Build all evidence documents as native, well-formatted DOCX files.
No PDF conversion — everything built directly with python-docx.
Run from: C:\amttp\research\visa\
"""
from pathlib import Path
from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import copy, shutil

BASE     = Path(__file__).parent
IMG_DIR  = BASE / "images"
OUT_DIR  = BASE / "EVIDENCE_DOCX_COPIES"
SUB_DIR  = BASE / "SUBMISSION_ORGANISED_BY_CATEGORY"
OUT_DIR.mkdir(exist_ok=True)

# ── Colour palette ────────────────────────────────────────────────────────────
C_NAVY    = RGBColor(0x1a, 0x2a, 0x4a)   # headers
C_RULE    = RGBColor(0x1a, 0x2a, 0x4a)
C_CODE_BG = RGBColor(0xf4, 0xf4, 0xf4)
C_GOLD    = RGBColor(0xc8, 0x9b, 0x00)
C_BLACK   = RGBColor(0x00, 0x00, 0x00)

# ── Base document factory ─────────────────────────────────────────────────────
def new_doc() -> Document:
    doc = Document()
    sec = doc.sections[0]
    sec.page_width  = Cm(21)
    sec.page_height = Cm(29.7)
    sec.top_margin    = Cm(0.9)
    sec.bottom_margin = Cm(0.9)
    sec.left_margin   = Cm(1.55)
    sec.right_margin  = Cm(1.55)
    # Default paragraph style
    style = doc.styles['Normal']
    style.font.name = 'Calibri'
    style.font.size = Pt(8.7)
    style.paragraph_format.space_after = Pt(1)
    return doc

# ── Formatting helpers ────────────────────────────────────────────────────────
def add_header_block(doc, criteria: str, title: str):
    """Top metadata block + horizontal rule + centred title."""
    p = doc.add_paragraph()
    r = p.add_run('Tech Nation Visa — Global Talent (Exceptional Promise)')
    r.bold = True; r.font.size = Pt(10.8); r.font.color.rgb = C_NAVY
    p.paragraph_format.space_after = Pt(1)

    p2 = doc.add_paragraph()
    p2.add_run('Criteria: ').bold = True
    p2.add_run(criteria)
    p2.paragraph_format.space_after = Pt(1)

    p3 = doc.add_paragraph()
    p3.add_run('Applicant: ').bold = True
    p3.add_run('Odeyemi Olusegun Israel')
    p3.paragraph_format.space_after = Pt(2)

    add_hrule(doc)

    p4 = doc.add_paragraph()
    r4 = p4.add_run(title)
    r4.bold = True; r4.font.size = Pt(10.8); r4.font.color.rgb = C_NAVY
    p4.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p4.paragraph_format.space_before = Pt(2)
    p4.paragraph_format.space_after  = Pt(4)

def add_hrule(doc):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after  = Pt(0)
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), '8')
    bottom.set(qn('w:space'), '1')
    bottom.set(qn('w:color'), '1a2a4a')
    pBdr.append(bottom)
    pPr.append(pBdr)

def add_section(doc, title: str):
    p = doc.add_paragraph()
    r = p.add_run(title)
    r.bold = True; r.font.size = Pt(9.8); r.font.color.rgb = C_NAVY
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after  = Pt(1)
    add_hrule(doc)

def add_body(doc, text: str, bold_map: dict = None):
    """Add a body paragraph; bold_map={phrase: True} to bold inline phrases."""
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    if bold_map is None:
        p.add_run(text)
    else:
        # Simple bold injection
        remaining = text
        for phrase in sorted(bold_map, key=len, reverse=True):
            remaining = remaining  # handled below
        # split by bold phrases
        import re
        pattern = '(' + '|'.join(re.escape(k) for k in bold_map) + ')'
        parts = re.split(pattern, text)
        for part in parts:
            run = p.add_run(part)
            if part in bold_map:
                run.bold = True
    return p

def add_exec_summary(doc, text: str):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(3)
    import re
    # bold anything between ** ** or explicit bold markers
    # Also bold leading "I built:" / "I designed..." patterns
    parts = re.split(r'(\*\*.*?\*\*)', text)
    for part in parts:
        if part.startswith('**') and part.endswith('**'):
            run = p.add_run(part[2:-2])
            run.bold = True
        else:
            p.add_run(part)

def add_code_block(doc, lines: list, caption: str = None):
    """Monospace shaded code block."""
    tbl = doc.add_table(rows=1, cols=1)
    tbl.style = 'Table Grid'
    cell = tbl.cell(0, 0)
    # shade background
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), 'F4F4F4')
    tc_pr.append(shd)

    cell.paragraphs[0]._p.getparent().remove(cell.paragraphs[0]._p)
    for line in lines:
        p = cell.add_paragraph()
        r = p.add_run(line)
        r.font.name = 'Courier New'
        r.font.size = Pt(7.0)
        p.paragraph_format.space_after  = Pt(0)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.left_indent  = Cm(0.2)

    doc.add_paragraph()  # spacing after
    if caption:
        add_caption(doc, caption)

def add_caption(doc, text: str):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.italic = True; r.font.size = Pt(7.4); r.font.color.rgb = RGBColor(0x44,0x44,0x44)
    p.paragraph_format.space_after = Pt(1)

def add_image(doc, filename: str, caption: str, width: float = 6.0):
    img_path = IMG_DIR / filename
    if img_path.exists():
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run()
        run.add_picture(str(img_path), width=Inches(min(width, 5.35)))
    else:
        p = doc.add_paragraph(f'[Image: {filename}]')
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_caption(doc, caption)

def add_bullet(doc, items: list):
    for item in items:
        p = doc.add_paragraph(style='List Bullet')
        import re
        parts = re.split(r'(\*\*.*?\*\*)', item)
        for part in parts:
            if part.startswith('**') and part.endswith('**'):
                run = p.add_run(part[2:-2]); run.bold = True
            else:
                p.add_run(part)
        p.paragraph_format.space_after = Pt(2)

def add_table(doc, headers: list, rows: list, col_widths: list = None):
    tbl = doc.add_table(rows=1+len(rows), cols=len(headers))
    tbl.style = 'Table Grid'
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    # header row
    for i, h in enumerate(headers):
        cell = tbl.cell(0, i)
        cell.text = h
        cell.paragraphs[0].runs[0].bold = True
        cell.paragraphs[0].runs[0].font.size = Pt(7.8)
        tc_pr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement('w:shd')
        shd.set(qn('w:val'), 'clear'); shd.set(qn('w:color'), 'auto'); shd.set(qn('w:fill'), 'D9E1F2')
        tc_pr.append(shd)
    # data rows
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cell = tbl.cell(ri+1, ci)
            p = cell.paragraphs[0]
            import re
            parts = re.split(r'(\*\*.*?\*\*)', str(val))
            first = True
            for part in parts:
                run = p.add_run(part[2:-2] if (part.startswith('**') and part.endswith('**')) else part)
                run.font.size = Pt(7.8)
                if part.startswith('**') and part.endswith('**'):
                    run.bold = True
    if col_widths:
        for ci, w in enumerate(col_widths):
            for ri in range(len(rows)+1):
                tbl.cell(ri, ci).width = Inches(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)

def save(doc, filename: str, sub_path: str = None):
    out = OUT_DIR / filename
    doc.save(str(out))
    print(f'  OK  {filename}')
    if sub_path:
        dest = SUB_DIR / sub_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(out), str(dest))

# ═══════════════════════════════════════════════════════════
# MC-1: AMTTP Live Demonstration
# ═══════════════════════════════════════════════════════════
def build_mc1():
    doc = new_doc()
    add_header_block(doc,
        'Mandatory Criteria — Innovation and Technical Leadership',
        'MC-1: Design and Development of AMTTP — A Four-Layer Real-Time Blockchain Compliance System')

    p = doc.add_paragraph()
    p.add_run('Executive Summary: ').bold = True
    p.add_run(
        'I designed and built a four-layer real-time compliance system for blockchain transactions. '
        'Traditional AML tools act only after transactions are completed, while AMTTP assesses risk, '
        'verifies sanctions, and applies contract decisions in less than a second — before any funds '
        'are transferred. In its first public month, the live platform processed ')
    p.add_run('920,848 transactions').bold = True
    p.add_run(' and attracted ')
    p.add_run('1,220 unique visitors').bold = True
    p.add_run(' at amttp.com. Every layer — consumer app, enterprise dashboard, nine-service AI backend, '
              'and blockchain contracts — was built by me.')
    add_body(doc,
        'What this proves for Mandatory Criteria: independent technical leadership, not merely participation. '
        'The evidence combines a public deployment, third-party infrastructure analytics, live product screens, '
        'and a repeatable architecture showing that I personally took an original digital-technology product '
        'from design to public release.')

    add_section(doc, 'Live Public Deployment Evidence')

    tbl = doc.add_table(rows=1, cols=1)
    tbl.style = 'Table Grid'
    cell = tbl.cell(0, 0)
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear'); shd.set(qn('w:color'), 'auto'); shd.set(qn('w:fill'), 'FFFBE6')
    tc_pr.append(shd)
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run('4-MINUTE VIDEO DEMONSTRATION'); r.bold = True; r.font.size = Pt(12)
    p2 = cell.add_paragraph('https://youtu.be/I0dXSN_ScR0')
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p2.runs[0].font.name = 'Courier New'
    p3 = cell.add_paragraph(
        'Public demo: amttp.com  |  Sepolia-backed  |  1,220 unique visitors  |  38,320 requests  |  5 Apr – 5 May 2026')
    p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p3.runs[0].italic = True
    doc.add_paragraph()

    add_image(doc, 'cloudflare_analytics.png',
        'Figure 1: Cloudflare analytics — 1,220 unique visitors, 38,320 requests, '
        '53.54% cache-hit ratio (5 Apr – 5 May 2026). Independently verifiable at amttp.com.',
        width=5.8)

    add_section(doc, 'Technical Contributions')

    all_bullets = [
        '**Pre-settlement enforcement at scale:** 920,848 transactions processed on a live testnet; decisions issued before funds move — not after.',
        '**Dual-model AI scoring:** gradient-boosted classifier + Graph Neural Network; fraud-detection ROC-AUC 0.9999998.',
        '**90%+ cost reduction:** compact distilled model runs on standard CPUs, eliminating specialist GPU hardware.',
        '**Privacy-preserving identity:** sanctions verified on-chain without exposing personal data — GDPR-compliant on a public ledger.',
        '**Regulatory audit trail:** every compliance decision permanently recorded on-chain (FCA / MiCA requirements).',
        '**Zero-downtime upgrades:** UUPS upgradeable contract design — compliance rules change without taking the live platform offline.',
    ]
    import re
    for item in all_bullets:
        p = doc.add_paragraph(style='List Bullet')
        for part in re.split(r'(\*\*.*?\*\*)', item):
            run = p.add_run(part[2:-2] if (part.startswith('**') and part.endswith('**')) else part)
            run.font.size = Pt(8.0)
            if part.startswith('**') and part.endswith('**'):
                run.bold = True
        p.paragraph_format.space_after = Pt(2)

    doc.add_page_break()
    add_image(doc, 'amttp_architecture.png',
        'Figure 2: AMTTP four-layer architecture — Flutter + Next.js (UI) → Express Gateway → '
        'Python FastAPI orchestrator (9 microservices) → 38 Solidity files, 17 Docker containers. '
        'All layers sole-authored.',
        width=6.3)

    doc.add_page_break()
    add_image(doc, 'warroom_dashboard.png',
        'Figure 3: War Room enterprise dashboard (Next.js, port 3006) — live compliance monitoring '
        'for compliance officers. Role-based access enforced server-side.', width=6.0)
    add_image(doc, 'warroom_reports.png',
        'Figure 4: Automated report generation — Daily AML PDF (2.4 MB), '
        'Weekly Risk Assessment (5.1 MB), Monthly FCA SAR (8.7 MB).', width=6.0)

    save(doc, 'MC-1_AMTTP_Live_Demonstration.docx',
         '01_Mandatory_Criteria_MC/MC-1_AMTTP_Live_Demonstration.docx')

# ═══════════════════════════════════════════════════════════
# MC-2: GitHub Contributions
# ═══════════════════════════════════════════════════════════
def build_mc2():
    doc = new_doc()
    add_header_block(doc,
        'Mandatory Criteria — Technical Leadership / Innovation',
        'MC-2: Sustained Technical Contributions — GitHub Repository and Codebase Authorship')

    add_section(doc, '1. Executive Summary')
    p = doc.add_paragraph()
    p.add_run('I built the AMTTP codebase as the sole author. The public GitHub repository records ')
    p.add_run('361 commits over eight months').bold = True
    p.add_run(' (September 2025 – April 2026) from my account, covering the full product stack: '
              'Python AI services, a TypeScript API gateway and SDKs, a Dart mobile app, '
              'Solidity smart contracts, and security/research tooling.')
    add_body(doc,
        'The repository verifies both authorship and delivery: commit history, timestamps, and per-file '
        'diffs are public at github.com/segetii/AMTTP. This evidence shows sustained development of a '
        'working product across multiple engineering domains.')

    add_section(doc, '2. Development Activity')
    add_image(doc, 'github_green_squares.png',
        'Figure 1: GitHub activity graph for github.com/segetii — sustained solo engineering across the '
        'full design-to-deployment lifecycle of AMTTP. Each square represents a day with code commits.')

    add_section(doc, '3. Public Verification Record')
    add_body(doc, 'The table below summarises the public development timeline. The volume, cross-domain '
             'consistency, and language diversity confirm this is the output of a single senior engineer '
             'operating across the full technical stack.')

    add_table(doc,
        ['Metric', 'Value'],
        [
            ['Total commits (all branches)', '361'],
            ['Active development period',    'Sep 2025 – Apr 2026'],
            ['Peak month (Mar 2026)',         '191 commits'],
            ['Languages',                    'Python, TypeScript, Dart, Solidity'],
            ['Repository',                   'github.com/segetii/AMTTP'],
        ], col_widths=[3.0, 3.5])
    add_caption(doc, 'Table 1: Public repository summary showing sustained development over eight months in four production languages.')

    add_body(doc, 'Development Activity by Month:')
    add_table(doc,
        ['Month', 'Commits', 'Focus'],
        [
            ['Sep 2025', '1',   'Project inception'],
            ['Oct 2025', '22',  'Smart contract architecture'],
            ['Nov 2025', '—',   'ML model training & dataset work (Google Colab)'],
            ['Dec 2025', '—',   'ML pipeline refinement & validation (Google Colab)'],
            ['Jan 2026', '18',  'ML pipeline integration & microservices'],
            ['Feb 2026', '115', 'Full-stack integration & SDKs'],
            ['Mar 2026', '191', 'Security auditing & production hardening'],
            ['Apr 2026', '14',  'Research papers & documentation'],
        ], col_widths=[1.5, 1.2, 4.0])
    add_caption(doc,
        'Table 2: Monthly cadence (Sep 2025 – Apr 2026). November and December 2025 commits do not appear '
        'in the GitHub graph because ML model training and dataset experimentation during that period were '
        'conducted in Google Colab; the resulting artefacts were integrated into the repository from January 2026 onwards.')

    add_body(doc,
        'Delivered components: live public platform at amttp.com (1,220 visitors, 38,320 requests in month 1); '
        'complete Solidity contract suite deployed and verified on Ethereum Sepolia; nine-service AI compliance '
        'backend; and two developer SDKs enabling third-party integration.')

    doc.add_page_break()
    add_section(doc, '4. Repository Scope and Authorship')
    add_code_block(doc, [
        'AMTTP/ (monorepo root)',
        '+-- contracts/        (38 authored Solidity files) UUPS proxy, ZK-NAF, CrossChain',
        '+-- backend/          (Oracle Gateway + 10 FastAPI microservices)',
        '|   +-- oracle-service/   Express.js TypeScript gateway (port 3001)',
        '|   +-- compliance-service/ orchestrator, sanctions, monitoring',
        '+-- ml/               (XGBoost, LightGBM, GraphSAGE pipelines)',
        '|   +-- Automation/   risk_engine/ + ml_pipeline/ + models/',
        '+-- frontend/',
        '|   +-- frontend/     Next.js App Router (War Room, port 3006)',
        '|   +-- amttp_app/    Flutter (6-platform consumer app, port 3010)',
        '+-- packages/',
        '|   +-- client-sdk/   TypeScript SDK (@amttp/client-sdk)',
        '|   +-- python-sdk/   Python SDK (amttp)',
        '+-- research/         (4 academic papers, visa docs, UDL framework)',
        '+-- patents/          (8 patent specifications, unified filing)',
        '+-- test/             (Hardhat + Foundry smart contract tests)',
        '+-- audit/            (Slither + Echidna security pipeline)',
    ], 'Figure 2: Repository directory structure confirming sole authorship across 5 languages '
       'and 14+ independently deployable services.')

    add_body(doc,
        'Technical significance: Delivering a full-stack compliance platform across blockchain, AI, mobile, '
        'and enterprise web demonstrates end-to-end technical ownership. Every commit, timestamp, and '
        'per-file diff is permanently public at github.com/segetii/AMTTP; authorship is verifiable '
        'without relying on any claim made here.')

    add_section(doc, '5. Supplementary: ML Development Activity (Nov–Dec 2025)')
    add_body(doc,
        'As noted in Table 2, November and December 2025 saw no commits to the public GitHub repository '
        'because model training and dataset experimentation were conducted in Google Colab. The Google '
        'Drive listing below provides independent, Google-timestamped corroboration.')

    add_image(doc, 'google_drive_colab_artifacts.png',
        'Figure 3: Google Drive listing (captured 13 May 2026) showing AMTTP ML artefact folders. '
        'Key entries: AMTTP_Machine_artifacts (Dec 5, 2025) and colab_artifacts_20251207_224303 '
        '(Dec 7, 2025) — the folder name is an auto-generated ISO timestamp (7 Dec 2025, 22:43:03 UTC) '
        'from a Colab export script. AMTTP_Models_GPU (Oct 1, 2025) and AMTTP_Models_v2/_v29 '
        '(Sep 26, 2025) show ML versioning began at project inception.')

    add_section(doc, '6. Technical Breadth — Cross-Domain Deliverables')
    add_body(doc,
        'The codebase spans five production programming languages used simultaneously. Each domain '
        'was designed, written, tested, and deployed by the same author, without a team.')
    add_table(doc,
        ['Domain', 'Language', 'Key Deliverable', 'Public Verification'],
        [
            ['AI / ML',          'Python',     '9-service FastAPI backend + distilled XGBoost/LightGBM', 'github.com/segetii/AMTTP/ml/'],
            ['Blockchain',        'Solidity',   '38 contracts, 10 deployed on Sepolia',                  'sepolia.etherscan.io'],
            ['API Gateway',       'TypeScript', 'Express.js Oracle Service + TypeScript SDK',             'github.com/segetii/AMTTP/backend/'],
            ['Mobile / Web App',  'Dart',       'Flutter 6-platform consumer app (port 3010)',            'github.com/segetii/AMTTP/frontend/amttp_app/'],
            ['Enterprise Web',    'TypeScript', 'Next.js War Room dashboard (port 3006)',                 'github.com/segetii/AMTTP/frontend/frontend/'],
            ['Python SDK',        'Python',     'amttp SDK — PyPI-ready, mirrors TS SDK',                 'github.com/segetii/AMTTP/packages/python-sdk/'],
            ['Security Tooling',  'YAML/Python','Slither + Echidna audit pipeline (38 contracts)',        'github.com/segetii/AMTTP/audit/'],
            ['Smart Contract Tests','JavaScript','Hardhat + Foundry test suites (74 files compiled)',     'github.com/segetii/AMTTP/test/'],
        ], col_widths=[1.5, 1.1, 2.6, 2.2])
    add_caption(doc,
        'Table 3: Public verification matrix — each domain, language, and deliverable is independently '
        'verifiable from the public repository without relying on any claim made in this document. '
        'Building across all eight rows simultaneously is the distinguishing characteristic of sole authorship.')

    save(doc, 'MC-2_GitHub_Contributions.docx',
         '01_Mandatory_Criteria_MC/MC-2_GitHub_Contributions.docx')

# ═══════════════════════════════════════════════════════════
# MC-3: Smart Contracts
# ═══════════════════════════════════════════════════════════
def build_mc3():
    doc = new_doc()
    add_header_block(doc,
        'Mandatory Criteria — Technical Authorship and Smart Contract Engineering',
        'MC-3: Smart Contract Architecture, Polyglot Engineering, and Verified Test Suite')

    add_section(doc, '1. Executive Summary')
    p = doc.add_paragraph()
    p.add_run('I am the sole designer, developer, tester, and deployer of AMTTP\'s blockchain enforcement '
              'layer, with no external development firm or collaborator. A smart contract is a programme '
              'that lives on a public blockchain: once triggered, it executes autonomously with no central '
              'server changing the outcome after execution; every action is permanent and public.')
    doc.add_paragraph()
    p2 = doc.add_paragraph()
    p2.add_run('I wrote ')
    p2.add_run('10 such contracts in Solidity').bold = True
    p2.add_run(' (Ethereum\'s programming language). Each receives AI-generated risk scores and issues '
               'enforceable compliance outcomes — Approve, Review, Hold, or Block — through the contract '
               'logic. A single deployer address and immutable timestamps at ')
    p2.add_run('sepolia.etherscan.io').font.name = 'Courier New'
    p2.add_run(' confirm both sole authorship and the development timeline. First deployment: December 2025. '
               'Full 10-contract re-deployment including ZK cryptographic verifiers: April 2026.')

    add_section(doc, '2. Policy Enforcement Contract')
    add_image(doc, 'vscode_multitab.png',
        'Figure 1: VS Code showing the core AMTTPCoreSecure.sol contract — the IAMTTPPolicyEngine interface '
        'that defines the four compliance outcomes (Approve, Review, Escrow, Block) and the '
        'validateTransaction function signature. The live War Room terminal (port 3006) confirms active '
        'development of the product layer alongside the contract layer.')

    add_section(doc, '3. Automated Test Evidence')
    add_image(doc, 'vscode_hardhat_tests.png',
        'Figure 2: Hardhat test output — 74 Solidity files compiled, 8 integration tests all passing in '
        '13 seconds. Tests cover contract deployment, risk-score-based auto-approval, user policy '
        'enforcement, and transfer limits. Of the 74 files, 38 are original AMTTP contracts; the rest '
        'are audited OpenZeppelin library dependencies.')

    add_section(doc, '4. Technical Significance')
    add_bullet(doc, [
        '**10 deployed contracts, 2 production cycles:** Full re-deployment in April 2026 added ZK-NAF privacy verifiers, extending the contract suite to 10 contracts and confirming sustained development from December 2025 to April 2026.',
        '**Autonomous compliance enforcement:** The IAMTTPPolicyEngine interface converts a risk score from the AI backend into an on-chain outcome, reducing manual intervention as a point of failure.',
        '**Independently verifiable:** Contract addresses, deployer wallet, timestamps, and transaction history are all public on Etherscan — no trust in the applicant\'s assertion is required.',
        '**Test-driven, not just compiled:** 8 integration tests covering the full compliance decision matrix confirm production-grade engineering discipline.',
    ])

    add_section(doc, '5. On-Chain Deployment Evidence (Ethereum Sepolia Testnet)')
    add_body(doc,
        'The AMTTP contracts have been live on Ethereum since December 2025, with a full production '
        're-deployment in April 2026 expanding the suite to 10 contracts including ZK-SNARK privacy '
        'verifiers. Every deployment is publicly recorded. The deployer address 0xBc270F0c...527CaF23F '
        'is the sole signer across both cycles, confirming single-author ownership.')

    add_table(doc,
        ['Contract', 'Address (sepolia.etherscan.io)'],
        [
            ['AMTTPCore (v2)',          '0x05687FBb0f8921ff502BdEbC180b24Ed2B14b612'],
            ['PolicyManager',           '0x4eECb1348988A041B89acA4Aa9348F6e1DD9BcD3'],
            ['PolicyEngine (v2)',        '0xe774E01CbFC63cfb64a0ec054821fDb5A61d8703'],
            ['DisputeResolver (v2)',     '0x9EB935E68DEa685B6feAa9DAB51a46Dcd4da53D7'],
            ['CrossChain (v2)',          '0x4f21b16D56e67c8Fa6AB0e3457deAB2805432953'],
            ['ZK-NAF RiskVerifier',     '0x434FE5D136C20dF81a2E8240F911c2020C10D3b2'],
            ['ZK-NAF KYCVerifier',      '0xf4BEaF8263cCB9f67736512BC168ea8D5ECBDfaA'],
            ['ZK-NAF SanctionsVerifier','0xdef3f2fff995eB2B0Cb3577A3cA9B55916005145'],
            ['zkNAFRouter',             '0xa5D36782089002F945167a83Bd3d2a237820F77C'],
            ['RiskRouter',              '0xE722A6466F9000e0e891254Dc96Bac6a5a49F932'],
        ], col_widths=[2.2, 4.3])

    add_image(doc, 'etherscan_contract.png',
        'Figure 3: Etherscan record for the AMTTP PolicyEngine. "Source Code (Proxy)" badge confirms an '
        'upgradeable contract architecture. The Contract Creator field shows the deployer wallet and '
        'December 2025 timestamp. Compliance-specific calls — "Set Escrow Threshold", '
        '"Set Dispute Resolution" — prove operational use, not a placeholder deployment.')

    add_body(doc,
        'Verification summary: Two full production deployment cycles — including ZK cryptographic verifiers '
        'and a complete automated test suite — completed by a sole engineer. The source code, tests, '
        'deployer wallet, and contract addresses create a direct verification chain from authorship to '
        'live deployment: github.com/segetii/AMTTP | contracts/ | deployments/')

    add_section(doc, '6. Kleros-Compatible Dispute Resolution and Evidence Escrow')
    add_body(doc,
        'AMTTP does not stop at approve/block decisions. High-risk transactions can be routed into a '
        'Kleros-style dispute flow: funds remain in escrow, both parties can submit evidence, an arbitrator '
        'or authorised resolver issues a ruling, and the core contract releases funds to the recipient or '
        'refunds the sender. This closes the main compliance loophole in automated AML systems: a transaction '
        'that is too risky to approve immediately is not simply rejected without process; it is preserved with '
        'an audit trail and a deterministic ruling path.')
    add_table(doc,
        ['Dispute feature', 'Implementation evidence', 'Why it matters'],
        [
            ['Escrow for high-risk transfers', 'AMTTPDisputeResolver + AMTTPCore callback', 'Funds cannot leave while evidence is reviewed'],
            ['Kleros-style evidence events', 'MetaEvidence / Evidence-compatible event flow', 'External arbitrators and regulators can inspect the case record'],
            ['Challenge window', 'Default 24-hour dispute period', 'Prevents irreversible release before challenge'],
            ['Approve / reject ruling', 'executeDisputeRuling releases or refunds', 'Final outcome is deterministic and on-chain'],
        ], col_widths=[1.7, 2.4, 2.4])
    add_caption(doc,
        'Table 2: Dispute-resolution layer. This explicitly covers the Kleros-style AMTTP feature: '
        'escrow, evidence submission, challenge window, and deterministic ruling callback.')

    add_section(doc, '7. ZK-NAF Privacy Architecture')
    add_body(doc,
        'The April 2026 deployment added a three-contract Zero-Knowledge Not-A-Fraud (ZK-NAF) suite: '
        'a RiskVerifier, a KYCVerifier, and a SanctionsVerifier. These contracts confirm that a wallet '
        'passes risk, identity, and sanctions checks — without recording or transmitting the underlying '
        'data. This is a direct GDPR compliance solution: personal data never appears on the public '
        'ledger, but the enforcement outcome is fully verifiable by any regulator.')
    add_code_block(doc, [
        'contract ZKNAFRiskVerifier is Initializable, OwnableUpgradeable, UUPSUpgradeable {',
        '    struct RiskProof { uint256[2] a; uint256[2][2] b; uint256[2] c; uint256[2] input; }',
        '    function verifyRiskProof(RiskProof calldata proof)',
        '        external view returns (bool valid, uint256 riskScore) {',
        '        valid = verifier.verifyProof(proof.a, proof.b, proof.c, proof.input);',
        '        riskScore = valid ? proof.input[0] : 0;',
        '    }',
        '    function batchVerify(RiskProof[] calldata proofs) external view returns (bool[] memory);',
        '}',
    ], 'Figure 4: ZKNAFRiskVerifier.sol — Groth16 ZK-SNARK proof verification. The wallet identity '
       'and risk score are hashed before submission; the contract verifies the proof without ever '
       'seeing the underlying data. Sole-authored, deployed April 2026.')
    add_body(doc,
        'Three deployed ZK verifier contracts confirm that the AMTTP blockchain layer implements '
        'privacy-preserving compliance — not just rule enforcement. This architectural decision '
        'resolves the fundamental conflict between KYC/AML obligations and GDPR data-minimisation '
        'requirements, and represents a direct technical contribution to UK regulatory technology.')

    save(doc, 'MC-3_Smart_Contracts.docx',
         '01_Mandatory_Criteria_MC/MC-3_Smart_Contracts.docx')

# ═══════════════════════════════════════════════════════════
# OC3-1: ML Pipeline
# ═══════════════════════════════════════════════════════════
def build_oc3_1():
    doc = new_doc()
    add_header_block(doc,
        'Optional Criteria 3 — Significant Technical, Commercial, or Entrepreneurial Contributions',
        'OC3-1: Machine Learning Pipeline & Model Validation')

    p = doc.add_paragraph()
    p.add_run('Executive Summary: ').bold = True
    p.add_run('I designed, trained, and deployed the AI fraud-detection engine used by AMTTP. '
              'My role covered every stage: data preprocessing, model architecture, knowledge '
              'distillation, ensemble design, and live deployment as a microservice.')
    p2 = doc.add_paragraph()
    p2.add_run('Validation Results: ').bold = True
    p2.add_run('ROC-AUC 0.9999998 on ')
    p2.add_run('625,168 real Ethereum transactions').bold = True
    p2.add_run(' (372 confirmed fraudulent), zero false positives, 90%+ cost reduction through '
               'CPU-only deployment. Every result is independently reproducible from benchmark '
               'scripts in the public repository.')

    add_section(doc, '1. Model Architecture and Results')
    p = doc.add_paragraph()
    p.add_run('The production ensemble model achieves a ')
    p.add_run('ROC-AUC of 0.9999998').bold = True
    p.add_run(' — ROC-AUC measures how reliably a model separates two categories; 1.0 is the '
              'maximum score and 0.5 is random guessing — with ')
    p.add_run('zero false positives').bold = True
    p.add_run(' across the full 625,168-transaction dataset. It runs on standard office-grade CPUs, '
              'reducing dependence on specialist GPU hardware. The architecture uses knowledge '
              'distillation: a large "teacher" model transfers learned patterns to a smaller '
              '"student" model that preserves high accuracy at over 90% lower infrastructure cost.')

    add_body(doc, 'Feature Importance Implementation (source: ml/Automation/risk_engine/integration_service.py):')
    add_code_block(doc, [
        'def _get_feature_importance(self, method: str) -> Dict[str, float]:',
        '    """Top-10 global feature importances (gain-based)."""',
        '    if method in ("ensemble", "xgboost") and self.xgb_model:',
        '        booster = self.xgb_model.get_booster()',
        '        importance = booster.get_score(importance_type="gain")',
        '',
        '        # Map fN -> human-readable feature names',
        '        feat_names = self.preprocessors.get("feature_names", [])',
        '        sorted_imp = sorted(importance.items(),',
        '                            key=lambda x: x[1], reverse=True)[:10]',
        '        total = sum(v for _, v in sorted_imp) or 1.0',
        '',
        '        return {name: round(v / total, 4) for k, v in sorted_imp}',
        '    elif method == "lightgbm" and self.lgbm_model:',
        '        importance = self.lgbm_model.feature_importance(type="gain")',
        '        return dict(zip(names, importance.tolist()))',
    ], 'Figure 1: Production code from risk_engine/integration_service.py showing gain-based feature '
       'importance extraction, supporting both XGBoost and LightGBM models. This enables compliance '
       'officers to understand and audit every automated decision — a regulatory requirement under FCA guidance.')

    add_section(doc, '2. Independently Verified Accuracy Results')

    add_table(doc,
        ['Model', 'ROC-AUC', 'PR-AUC', 'F1', 'Role in Ensemble'],
        [
            ['Student LightGBM',    '0.99999969', '0.99951', '0.9906', 'Strongest single model'],
            ['Student XGBoost',     '0.98976',    '0.96935', '0.9767', 'CPU-optimised deployment model'],
            ['Teacher XGBoost',     '0.99690',    '—',       '—',      'Teacher knowledge source'],
            ['**Student Ensemble**','**0.99999980**','**0.99968**','**0.9864**','**Final production score**'],
        ], col_widths=[1.8, 1.1, 1.1, 0.9, 2.0])
    add_caption(doc,
        'Table 1: Ensemble model performance on 625,168 Ethereum transaction samples. '
        'Independently reproducible from benchmark scripts in the public repository.')

    add_bullet(doc, [
        '**Precision: 100%, Zero false positives** — 362 confirmed fraud cases correctly identified with 0 false accusations across the full 625,168-sample evaluation set.',
        '**PR-AUC: 0.9997** — Strong precision-recall balance; critical in compliance contexts where false positives freeze legitimate transactions.',
        '**MCC: 0.9906** — Matthews Correlation Coefficient confirming balanced performance on both the fraudulent and clean transaction classes.',
        '**90%+ cost reduction:** CPU-only deployment makes this accessible to any financial institution without specialist hardware investment.',
        '**No hindsight bias:** Temporal holdout validation confirmed by dedicated audit scripts (test_no_leakage*.py) in the public repository.',
    ])

    doc.add_page_break()
    add_image(doc, 'ml_evaluation_results.png',
        'Figure 2: evaluation_results_v2.json open in VS Code — the raw benchmark output confirming '
        'Teacher Stack ROC-AUC 1.0, 0 false positives (fp: 0.0), and Student XGB ROC-AUC 0.9898 '
        'on 625,168 real-world transaction samples.')

    add_section(doc, '3. Live Microservice Integration')
    add_body(doc,
        'The risk engine runs as a live FastAPI microservice (port 8000). Transaction payloads arrive '
        'from the Express.js Oracle Gateway, are scored at sub-second latency, and flow into a compliance '
        'orchestrator (port 8007) that queries nine specialist services in parallel: ML Risk, Graph '
        'Analysis, FCA Sanctions, Policy Engine, Monitoring, GeoRisk, Data Integrity, Explainability, '
        'and ZK-NAF. A composite verdict is issued and enforced on-chain by the Solidity contract.')
    add_body(doc,
        'Technical significance: ROC-AUC 0.9999998 with zero false positives, on commodity CPUs, '
        'demonstrates that institutional-grade compliance AI is achievable without the specialist '
        'infrastructure that currently excludes smaller financial institutions. Built without a team.')

    add_section(doc, '4. Nine-Service Compliance Orchestrator')
    add_body(doc,
        'The ML risk engine does not operate in isolation. Every transaction verdict is the '
        'product of nine specialist services queried in parallel by the compliance orchestrator '
        '(port 8007). The orchestrator fans out to all services simultaneously, collects their '
        'responses, and issues a composite decision — Approve, Review, Escrow, or Block — '
        'in under one second end-to-end.')
    add_table(doc,
        ['Service', 'Port', 'Role'],
        [
            ['ML Risk API',           '8000', 'XGBoost/LightGBM fraud score'],
            ['Graph Service',          '8001', 'GraphSAGE wallet-network analysis'],
            ['Policy Engine',          '8003', 'FCA/MiCA rule evaluation'],
            ['Sanctions Service',      '8004', 'OFAC/HM Treasury list matching'],
            ['Monitoring Service',     '8005', 'Behavioural pattern anomaly detection'],
            ['GeoRisk Service',        '8006', 'Jurisdiction and geolocation risk'],
            ['Compliance Orchestrator','8007', 'Parallel fan-out, composite verdict'],
            ['Integrity Service',      '8008', 'Data integrity and tamper detection'],
            ['Explainability Service', '8009', 'Decision factor extraction (FCA audit trail)'],
            ['ZK-NAF Service',         '8010', 'Zero-knowledge identity/sanctions proof'],
        ], col_widths=[2.2, 0.7, 3.5])
    add_caption(doc,
        'Table 2: All nine compliance microservices — each independently deployable, each sole-authored. '
        'The orchestrator architecture means any service can be upgraded or replaced without '
        'affecting the compliance decision pipeline, meeting FCA change-management requirements.')
    add_body(doc,
        'All nine services use FastAPI with Pydantic validation, async request handling, and '
        'structured JSON logging. The architecture is designed for horizontal scaling — each '
        'service can be replicated independently based on load. The full service stack is defined '
        'in docker-compose.yml and deployable with a single command.')

    save(doc, 'OC3-1_ML_Pipeline.docx',
         '02_Optional_Criteria_3_OC3/OC3-1_ML_Pipeline.docx')

# ═══════════════════════════════════════════════════════════
# OC3-2: War Room Dashboard
# ═══════════════════════════════════════════════════════════
def build_oc3_2():
    doc = new_doc()
    add_header_block(doc,
        'Optional Criteria 3 — Product & Engineering Impact',
        'OC3-2: UI Integrity Architecture, RBAC Enforcement, and Bybit-Class Attack Prevention')

    add_section(doc, '1. Executive Summary')
    p = doc.add_paragraph()
    p.add_run('I built: ').bold = True
    p.add_run('an enterprise compliance interface with cryptographic UI integrity guarantees, '
              'six-tier role-based access control, and AI decision explainability — sole-authored '
              'from first line to live deployment. In February 2025, attackers at Bybit replaced '
              'the compliance approval interface with a manipulated version, causing staff to '
              'unknowingly authorise a ')
    p.add_run('$1.5 billion theft').bold = True
    p.add_run('. Every War Room screen component carries a cryptographic fingerprint; any '
              'substitution is detected and blocked before any approval signature is collected. '
              'The architecture I designed closes that exact attack class.')

    add_section(doc, '2. UI Integrity Implementation')
    add_body(doc,
        'The file ui-integrity.ts provides four layered defences: (1) every screen component carries '
        'a unique cryptographic fingerprint; (2) approvals are signed against actual transaction data, '
        'not the displayed text; (3) the server independently validates the fingerprint before acting; '
        'and (4) a final confirmation is shown in a secure, isolated context. If an attacker replaces '
        'any part of the interface, the fingerprints will not match and the transaction is blocked '
        'before any approval can be given.')

    add_image(doc, 'vscode_ui_integrity_header.png',
        'Figure 1: ui-integrity.ts lines 1–32 — header names the Bybit attack vector, lists four '
        'prevention layers, implements SHA-256 hashing via Web Crypto API. Any interface substitution '
        'breaks every hash.')
    add_image(doc, 'vscode_ui_integrity_impl.png',
        'Figure 2: ui-integrity.ts lines 160–190 — four independent hashes (sourceHash, domHash, '
        'eventHandlersHash, combinedHash) per UI component. Hashing source code and live DOM '
        'independently detects the Bybit attack pattern.')

    add_section(doc, '3. Role-Based Access Control')
    add_table(doc,
        ['Role', 'Label', 'Interface', 'Key Capabilities'],
        [
            ['R1', 'End User',           'Flutter (Focus Mode)',   'Own transactions only'],
            ['R2', 'PEP End User',        'Flutter (Focus Mode)',   'Enhanced monitoring, restricted view'],
            ['R3', 'Compliance Officer',  'Next.js (War Room)',     'All transactions, report generation'],
            ['R4', 'Risk Analyst',        'Next.js (War Room)',     'Detection studio, policy editing'],
            ['R5', 'Administrator',       'Next.js (War Room)',     'User management, enforcement actions'],
            ['R6', 'Super Admin',         'Next.js (War Room)',     'Emergency override, full audit access'],
        ], col_widths=[0.6, 1.8, 2.0, 2.5])
    add_caption(doc,
        'Each role is defined in a shared configuration file used by both the mobile app and the web '
        'dashboard. Access restrictions are enforced at the backend server level rather than on the '
        'visible interface, meaning they cannot be bypassed by manipulating what appears on screen.')

    doc.add_page_break()
    add_image(doc, 'warroom_alerts.png',
        'Figure 3: War Room Alerts panel (Compliance Officers and above, enforced server-side) — '
        '100 live critical alerts with severity scores and flag reasons. Role access is denied at '
        'the backend, so bypassing the UI restriction gains nothing.')

    add_section(doc, '4. Model Explainability and Audit Trail')
    add_body(doc,
        'If an officer receives a "CRITICAL — Block" decision with no reasoning, they cannot detect '
        'a manipulated model. The Explainability panel surfaces the contributing factors and their '
        'weighting for every automated decision, satisfying FCA/MiCA audit trail requirements.')
    add_image(doc, 'warroom_explainability.png',
        'Figure 4: Decision Explainability panel for a CRITICAL alert — contributing factors and their '
        'weights: High Risk Transfer 85%, Velocity Anomaly 78%, Sanctioned Address Proximity 65%, '
        'with direct link to the graph network view. Satisfies FCA/MiCA audit trail requirements '
        'without additional tooling.')

    add_section(doc, '5. Consumer-Facing Layer — Flutter Focus Mode (R1/R2)')
    add_body(doc,
        'The War Room serves compliance officers (R3–R6). The complementary consumer-facing layer '
        'is a Flutter mobile app targeting R1 (End User) and R2 (Politically Exposed Person). '
        'Both interfaces use the same backend and the same RBAC configuration — the product covers '
        'the full user spectrum from individual wallet holders to enterprise compliance teams. '
        'This dual-interface design is a deliberate architectural choice: a single compliance '
        'verdict is surfaced in a contextually appropriate UI for each role.')
    # ── Flutter screenshots side by side ────────────────────────────────────
    from docx.oxml import OxmlElement as _OxmlElement
    from docx.oxml.ns import qn as _qn
    from docx.shared import Cm as _Cm

    flutter_tbl = doc.add_table(rows=2, cols=2)
    flutter_tbl.style = 'Table Grid'
    flutter_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Remove all borders so it looks like a clean layout
    def _no_borders(tbl):
        tbl_pr = tbl._tbl.tblPr
        tbl_borders = _OxmlElement('w:tblBorders')
        for side in ('top','left','bottom','right','insideH','insideV'):
            b = _OxmlElement(f'w:{side}')
            b.set(_qn('w:val'), 'none')
            tbl_borders.append(b)
        tbl_pr.append(tbl_borders)
    _no_borders(flutter_tbl)

    # Set equal column widths (~3.0" each)
    for col in flutter_tbl.columns:
        for cell in col.cells:
            cell.width = _Cm(7.6)

    IMG_W = Inches(2.9)
    for ci, (fname, fig_label) in enumerate([
        ('flutter_home_pep.png',    'Figure 5: Home screen\n(R2 PEP / Enhanced Monitoring)'),
        ('flutter_activity_menu.png', 'Figure 6: Activity feed\n& navigation menu'),
    ]):
        img_cell = flutter_tbl.cell(0, ci)
        cap_cell = flutter_tbl.cell(1, ci)
        # Image paragraph
        ip = img_cell.paragraphs[0]
        ip.alignment = WD_ALIGN_PARAGRAPH.CENTER
        img_path = IMG_DIR / fname
        if img_path.exists():
            ip.add_run().add_picture(str(img_path), width=IMG_W)
        else:
            ip.add_run(f'[{fname}]')
        # Caption paragraph
        cp = cap_cell.paragraphs[0]
        cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cr = cp.add_run(fig_label)
        cr.italic = True
        cr.font.size = Pt(7.6)
        cr.font.color.rgb = RGBColor(0x44, 0x44, 0x44)

    doc.add_paragraph()
    add_caption(doc,
        'Flutter Focus Mode: Home (R2 PEP) and Activity feed. Both screens connect to the same '
        'backend and RBAC configuration as the War Room. Sole-authored in Dart; runs on iOS, '
        'Android, Web, macOS, Windows, and Linux from a single codebase.')

    save(doc, 'OC3-2_War_Room_Dashboard.docx',
         '02_Optional_Criteria_3_OC3/OC3-2_War_Room_Dashboard.docx')

# ═══════════════════════════════════════════════════════════
# OC3-3: CrossChain SDK
# ═══════════════════════════════════════════════════════════
def build_oc3_3():
    doc = new_doc()
    add_header_block(doc,
        'Optional Criteria 3 — Significant Technical and Entrepreneurial Contribution',
        'OC3-3: Cross-Chain Interoperability & SDK Distribution')

    add_section(doc, '1. Executive Summary')
    p = doc.add_paragraph()
    p.add_run('I built: ').bold = True
    p.add_run('compliance enforcement across seven simultaneous blockchain networks — closing the '
              'cross-chain evasion gap where a blacklisted wallet moves freely to a different chain — '
              'and two developer SDKs that compress third-party integration from weeks of custom '
              'infrastructure work to hours, exposing nine specialist AI compliance services behind '
              'a single import.')
    doc.add_paragraph()
    add_body(doc,
        'The problem: conventional compliance tools enforce rules on one blockchain. A blacklisted '
        'wallet simply moves assets to a different network and transacts freely. I solved this by '
        'propagating risk scores and block decisions across seven networks via LayerZero — a '
        'cross-blockchain messaging protocol that transmits signed data packets between networks. '
        'A wallet blocked anywhere is blocked everywhere. EVM (Ethereum Virtual Machine) is the '
        'shared code standard across Ethereum, Polygon, Arbitrum, Optimism, Base, BSC, and '
        'Avalanche, meaning enforcement code written once applies to all of them.')
    add_body(doc,
        'Two developer SDKs — TypeScript (@amttp/client-sdk) and Python (amttp) — accompany the '
        'core system, exposing the full compliance stack behind a simple import. Neither wraps an '
        'existing library; both were written from scratch.')

    add_body(doc, 'Cross-Chain Contract Integration (from contracts/AMTTPCrossChain.sol):')
    add_code_block(doc, [
        'contract AMTTPCrossChain is Initializable, OwnableUpgradeable,',
        '    UUPSUpgradeable, ILayerZeroReceiver {',
        '',
        '    mapping(address => mapping(uint16 => uint256))',
        '        public crossChainRiskScores;',
        '    mapping(address => bool) public globallyBlocked;',
        '    ILayerZeroEndpoint public lzEndpoint;',
        '',
        '    function sendRiskScore(',
        '        uint16 _dstChainId, address _targetAddress,',
        '        uint256 _riskScore, bytes calldata _adapterParams',
        '    ) external payable whenNotPaused nonReentrant {',
        '        require(_riskScore <= 1000, "Invalid risk score");',
        '        bytes memory payload = abi.encode(',
        '            MSG_RISK_SCORE, _targetAddress, _riskScore);',
        '        lzEndpoint.send{value: msg.value}(',
        '            _dstChainId, trustedRemotes[_dstChainId],',
        '            payload, payable(msg.sender), address(0),',
        '            _adapterParams);',
        '    }',
        '}',
    ], 'Figure 1: AMTTPCrossChain.sol — upgradeable Solidity contract implementing LayerZero '
       'cross-chain message passing. A risk score or block decision on one of 7 EVM networks is '
       'encoded, signed, and broadcast to all connected chains. nonReentrant and whenNotPaused '
       'guards prevent replay and denial-of-service.')

    add_section(doc, '2. Developer SDK Distribution')
    add_bullet(doc, [
        '**TypeScript SDK (@amttp/client-sdk):** For web and application developers. Provides AI-powered risk scoring, blockchain enforcement integration, identity compliance checks, and support for multiple blockchain networks.',
        '**Python SDK (amttp):** For data scientists and backend engineers. Provides the same capabilities in Python — the standard language in financial analytics and data science teams.',
    ])

    add_image(doc, 'vscode_sdk_packages.png',
        'Figure 2: VS Code workspace showing both SDKs fully structured and ready for distribution. '
        'Both packages are sole-authored: no collaborative commits, no fork from an existing SDK. '
        'Each wraps the full nine-service AMTTP compliance stack behind a single import.')

    add_section(doc, '3. Commercial Readiness and UK Ecosystem Value')
    add_body(doc,
        'Cross-chain enforcement and distribution-ready SDKs transform AMTTP from a research system '
        'into a deployable compliance product. The architectural decision to implement enforcement at '
        'the cross-chain messaging layer — rather than as a post-settlement reporting tool — means a '
        'block decision propagates to all seven networks within the same transaction cycle. A wallet '
        'cannot evade by moving chains.')
    add_body(doc,
        'The two SDKs directly address the principal integration barrier for regulated institutions: '
        'a bank, payment processor, or fintech operating on any of the seven supported networks can '
        'integrate the full nine-service compliance stack within hours, in their preferred language, '
        'without rebuilding or understanding the underlying infrastructure. This eliminates a cost '
        'and complexity barrier that would otherwise require a dedicated blockchain engineering team.')
    add_body(doc,
        'For UK digital-finance institutions operating under FCA digital-asset rules, Travel Rule '
        'obligations, or MiCA cross-border requirements, the enforcement layer and its distribution '
        'tooling represent production-ready infrastructure they can adopt immediately. I designed, '
        'built, and sole-authored every component.')

    doc.add_page_break()
    add_section(doc, '4. Pilot Deployment Agreement')
    add_body(doc,
        'A formal Pilot Evaluation Agreement has been executed with an enterprise partner, confirming '
        'independent commercial interest in evaluating AMTTP in a real business environment. This is framed '
        'as pilot-stage external validation, not a claim of paid production adoption. The agreement covers '
        'the cross-chain enforcement layer and the developer SDKs documented in this exhibit. It was signed '
        'and company-sealed by the partner after independent review — with no prior professional relationship '
        'between the parties.')
    add_body(doc,
        'The signed and sealed Schedule A/signature exhibit is reproduced below. Key terms: (a) the partner '
        'is evaluating defined AMTTP pilot components; (b) the scope includes onboarding/KYC, risk scoring, '
        'integrity checks, dispute/evidence workflow, and monitoring/reporting; (c) the agreement is '
        'non-exclusive and preserves the applicant\'s ability to commercialise the technology independently.')

    # ─── Pilot Agreement signed image ───────────────────────────────────────
    add_image(doc, 'pilot_agreement_signed.png',
        'Figure 3: Signed and company-sealed Pilot Evaluation Agreement exhibit — Schedule A pilot '
        'components and signature page together. Independent commercial validation that AMTTP is being '
        'evaluated externally as deployable compliance infrastructure.',
        width=5.8)
    doc.add_paragraph()

    save(doc, 'OC3-3_CrossChain_SDK.docx',
         '02_Optional_Criteria_3_OC3/OC3-3_CrossChain_SDK.docx')

# ═══════════════════════════════════════════════════════════
# OC3-4: Security Auditing
# ═══════════════════════════════════════════════════════════
def build_oc3_4():
    doc = new_doc()
    add_header_block(doc,
        'Optional Criteria 3 — Supporting Technical Evidence',
        'OC3-4: Security Architecture & Automated Smart Contract Auditing')

    p = doc.add_paragraph()
    p.add_run('Executive Summary: ').bold = True
    p.add_run('I conducted a full institutional-grade security audit of all ')
    p.add_run('38 AMTTP smart contracts').bold = True
    p.add_run(', using the same categories of tools used in professional blockchain audits.')
    add_body(doc,
        'Smart contracts run on a public blockchain with no central server and limited room for delayed '
        'remediation: a code flaw can be exploited quickly and permanently recorded. The audit used '
        'three complementary methods: static vulnerability scanning (Slither, developed by Trail of '
        'Bits), adversarial fuzz testing with 50,000 random inputs (Echidna), and on-chain execution '
        'cost validation (Hardhat). Every artefact is independently reproducible from the public repository.')

    add_section(doc, '1. Audit Scope and Tools')
    add_body(doc,
        'The audit used three complementary methods across all 38 contracts: (1) Slither — the standard '
        'static analyser for blockchain contracts, developed by Trail of Bits — scanned every line of '
        'code for known vulnerability patterns; (2) Echidna generated 50,000 randomised adversarial '
        'transaction sequences of 100 steps each to confirm that critical access-control rules hold '
        'under attack conditions; and (3) Hardhat measured the on-chain computational cost of every '
        'contract operation, confirming production viability under Ethereum\'s network limits.')

    add_section(doc, '2. Slither Static Analysis Findings')
    add_body(doc,
        'Slither was run against all 38 original AMTTP contracts. Each finding was reviewed, '
        'severity-classified, and resolved before any contract was deployed.')

    add_code_block(doc, [
        'MockArbitrator.withdraw() sends eth to arbitrary user',
        '   Dangerous calls: address(msg.sender).transfer(address(this).balance)',
        '',
        'Reentrancy in AMTTPDisputeResolver.challengeTransaction(bytes32):',
        '   External calls:',
        '   - disputeID = arbitrator.createDispute{value: arbitrationCost}(...)',
        '   State variables written after the call(s):',
        '   - escrow.status = EscrowStatus.Challenged',
        '',
        'AMTTPCore.initiateSwapERC20() ignores return value by',
        '   IERC20(token).transferFrom(msg.sender, address(this), amount)',
        '',
        'AMTTP.completeSwap(bytes32,bytes32) ignores return value by',
        '   IERC20(s.token).transfer(s.seller, s.amount)',
        '',
        'AMTTPBiconomyModule.riskCache is never initialized.',
    ], 'Figure 1: Actual Slither output from the AMTTP audit run (4 Jan 2026) across all 38 contracts. '
       'Each finding — reentrancy in AMTTPDisputeResolver, unchecked transfer return values, uninitialised '
       'riskCache — was reviewed, severity-classified, and resolved before mainnet deployment. '
       'The raw log is independently reproducible.')

    add_section(doc, '3. Echidna Fuzz Testing (Property-Based Verification)')
    add_body(doc,
        'Echidna is a professional security tool that generates thousands of random, unpredictable '
        'inputs to stress-test a system and find failure cases that structured tests would miss. '
        'Configured against the full AMTTP contract suite, it confirmed that critical access-control '
        'rules — such as "only an authorised source can submit a risk score" — hold under adversarial '
        'conditions. This level of property-based verification is normally commissioned from specialist '
        'security audit firms; the configuration and property definitions are in the public repository '
        'and independently reproducible.')

    doc.add_page_break()
    add_body(doc, 'Verified Echidna configuration (audit/echidna.yaml):')
    add_code_block(doc, [
        'testMode: assertion',
        'testLimit: 50000',
        'seqLen: 100',
        'shrinkLimit: 5000',
        'corpusDir: "corpus"',
        'coverage: true',
        'workers: 4',
        'deployer: "0x10000"',
        'sender: ["0x10000", "0x20000", "0x30000"]',
    ], 'Figure 2: Echidna configuration — 50,000 test sequences of 100 steps each, 4 parallel workers, '
       'corpus-guided fuzzing with coverage tracking. This configuration matches professional '
       'audit-grade fuzz testing.')

    add_section(doc, '4. Hardhat Integration Tests')
    add_image(doc, 'vscode_hardhat_tests.png',
        'Figure 3: Hardhat test run — 74 Solidity files compiled, 8 integration tests passing in '
        '13 seconds. Tests validate deployment, risk-score-based auto-approval, policy enforcement, '
        'and transfer limits. Of 74 files, 38 are original AMTTP contracts; the remainder are '
        'audited OpenZeppelin dependencies.')

    add_body(doc,
        'Technical significance: Running Slither, Echidna, and Hardhat against a 38-contract suite — '
        'and resolving all findings before deployment — is a standard professional security practice. '
        'Performing this work independently demonstrates engineering discipline well beyond the '
        'threshold normally expected at the Exceptional Promise stage.')

    add_section(doc, '5. Gas Validation Report')
    add_body(doc,
        'On-chain execution cost — "gas" — is a hard constraint on contract viability. A contract '
        'that consumes more gas than the Ethereum block limit cannot execute; one that consumes '
        'excessive gas becomes economically unviable for users. Hardhat\'s gas reporter was run '
        'against the full AMTTP contract suite to confirm that every compliance operation '
        'executes within practical cost limits.')
    add_image(doc, 'gas_report.png',
        'Figure 4: Hardhat Gas Reporter output — per-method and per-contract execution cost '
        'for the AMTTP contract suite. Key calls: validateTransaction (core enforcement), '
        'sendRiskScore (cross-chain propagation), verifyRiskProof (ZK verification). '
        'All operations confirmed within Ethereum mainnet block gas limits and economically '
        'viable at current ETH gas prices. Sole-authored, independently reproducible.')
    add_body(doc,
        'Gas optimisation decisions: the UUPS upgradeable proxy pattern reduces deployment cost '
        'versus transparent proxies; the viaIR compiler setting (50 optimisation runs) minimises '
        'bytecode size; ZK proof verification is batched where possible to amortise the fixed '
        'overhead of the pairing check. All three decisions are documented in hardhat.config.cjs.')

    save(doc, 'OC3-4_Security_Auditing.docx',
         '02_Optional_Criteria_3_OC3/OC3-4_Security_Auditing.docx')

# ═══════════════════════════════════════════════════════════
# OC4-1: BSDT Research
# ═══════════════════════════════════════════════════════════
def build_oc4_1():
    doc = new_doc()
    add_header_block(doc,
        'Optional Criteria 4 — Academic Contributions through Research',
        'OC4-1: Blind-Spot Decomposition Theory (BSDT) Framework')

    p = doc.add_paragraph()
    p.add_run('Executive Summary: ').bold = True
    p.add_run('I independently developed Blind-Spot Decomposition Theory (BSDT), a mathematical '
              'framework for diagnosing systematic failure modes in AI fraud-detection models.')
    add_body(doc,
        'AI models do not fail randomly. They miss cases in predictable patterns: transactions that '
        'mimic normal behaviour slip through undetected, and the specific reasons (data gaps, timing '
        'anomalies, distributional camouflage) are invisible to standard accuracy metrics. I developed '
        'BSDT to decompose these blind spots into four measurable components and produce a single '
        'correction score, without requiring the underlying model to be retrained. Validated on '
        'financial fraud data, then applied — unchanged — to power-grid stability and cryptocurrency '
        'market collapse, it demonstrates a generalisable mathematical structure rather than a '
        'domain-specific fix.')

    add_section(doc, '1. Cross-Domain Results')
    add_bullet(doc, [
        '**Reduces fraudulent-transaction false-positive rates by 99.94%** (from 36,469 false alerts down to 22 in benchmark datasets)',
        '**Predicted the 2021 Texas ERCOT power-grid collapse 72 hours before it occurred** (AUC 0.9997 on publicly available grid data)',
        '**Issued a 30-hour advance warning of the Terra/Luna cryptocurrency collapse** in 2022 — all from the same mathematical model, retrained on no new data.',
    ])
    add_body(doc,
        'The cross-domain results are the key evidence: a model trained on financial fraud detects '
        'instability precursors in structurally different time-series without modification.')

    add_body(doc, 'BSDT Four-Channel Decomposition:')
    add_code_block(doc, [
        'δ_C = 1 - clip(‖x - μ_ref‖ / d_max, 0, 1)          (Camouflage)',
        'δ_G = (# near-zero features) / p                     (Feature Gap)',
        'δ_A = σ((d_Mahal - d̃_ref) / d̃_ref)                  (Activity Anomaly)',
        'δ_T = σ(0.5 · (d_kNN / d̃_kNN,ref - 2))              (Temporal Novelty)',
        '',
        'E_BS = Σ δ_i²                                        (Total blind-spot energy)',
        'MFLS = ‖∇E_BS‖_F                                     (Gradient-norm score)',
        'Combined = 0.5 · Ê_BS + 0.5 · MFLŜ                  (Equal-weight average)',
    ], 'Figure 1: The four-channel BSDT decomposition. Each channel captures a distinct mode by which '
       'an AI model can miss fraud. The combined MFLS score enables targeted remediation without '
       'retraining the model from scratch. Validated across fraud detection, power-grid stability, '
       'and cryptocurrency collapse datasets.')

    add_section(doc, '2. Research Code Implementation')
    add_body(doc,
        'BSDT is an optional diagnostic tool for enterprise clients needing to understand why their '
        'AI models generate blind spots, or to add a correction layer over existing systems. '
        'Publication metrics and academic adoption evidence are in OC4-2 and OC4-3.')
    add_code_block(doc, [
        'class BSDTChannels:',
        '    """Blind-Spot Detection Tensor — four complementary channels."""',
        '',
        '    def fit(self, X_ref: np.ndarray) -> "BSDTChannels":',
        '        self.mu_ = X_ref.mean(axis=0)',
        '        self.d_max_ = max(float(np.linalg.norm(X_ref - self.mu_, axis=1).max()), self.eps)',
        '        self.mahal_ref_median_ = float(np.median(self._mahalanobis(X_ref)))',
        '        self.ref_knn_median_ = float(np.median(ref_dists[:, -1]))',
        '',
        '    def mfls(self, X: np.ndarray) -> np.ndarray:',
        '        return np.linalg.norm(self._gradient_vectors(X), axis=1)',
        '',
        '    def score(self, X: np.ndarray) -> np.ndarray:',
        '        e = self.energy(X)',
        '        m = self.mfls(X)',
        '        return 0.5 * (e / e.max()) + 0.5 * (m / m.max())',
    ], 'Figure 2: Working production code implementing the BSDT framework (system_mode.py in the public '
       'repository). fit() calibrates against a reference dataset; mfls() computes the gradient-norm '
       'missed-fraud score; score() returns the equal-weight combined output.')

    doc.add_page_break()
    add_section(doc, '3. Cross-Domain Validation')
    add_table(doc,
        ['Dataset / Domain', 'Result', 'Key metric'],
        [
            ['Fraud benchmark (single run)',        '99.94% false-positive reduction',      '36,469 → 22 alerts'],
            ['12 fraud datasets (66 variants)',      'Zero missed fraud in 10/12',            'Mean F1 0.787'],
            ['2021 Texas ERCOT power grid',          '72-hour advance warning',               'AUC 0.9997'],
            ['2022 Terra/Luna cryptocurrency',       '30-hour advance warning',               'On-chain data only'],
            ['2008 US banking crisis (FDIC)',        'Six-quarter early warning',             'AUROC 0.867'],
        ], col_widths=[2.4, 2.4, 1.8])
    add_caption(doc,
        'Table 1: BSDT validated across five independent scenarios spanning three problem domains. '
        'All data sources are publicly available; no privileged information was used in any evaluation. '
        'Benchmark scripts are in the public repository.')

    add_body(doc,
        'The cross-domain results show that BSDT captures a repeatable mathematical structure rather '
        'than a domain-specific pattern. The model was trained once on financial fraud data and applied '
        'without modification to power-grid sensor readings and cryptocurrency market data — structurally '
        'distinct time-series domains. The ERCOT 72-hour signal identifies the same frequency-deviation '
        'precursors later documented in the official FERC/NERC post-incident investigation. The 2008 '
        'banking crisis result extends the signal to a six-quarter horizon. The 792-evaluation study '
        '(66 variants, 12 datasets) establishes statistical reliability beyond any individual benchmark.')

    add_body(doc,
        'Technical significance: A diagnostic framework that reduces AML false-positive alerts by '
        '99.94%, issued a 30-hour warning before the Terra/Luna cryptocurrency collapse, and identified '
        'a national power-grid failure 72 hours in advance — all from one mathematical model, trained '
        'once — is a substantial contribution to applied mathematics and financial risk. It was produced '
        'independently, published openly, and adopted into university teaching without any prior contact. '
        'Publication record: OC4-2. Academic adoption: OC4-3.')

    add_section(doc, '4. Reproducibility and Validation Scale')
    add_body(doc,
        'A single benchmark result can be coincidental. BSDT was evaluated across '
        '792 experimental runs (66 model variants on 12 independent datasets) to establish '
        'statistical reliability. All benchmark scripts are in the public repository and '
        'independently executable.')
    add_table(doc,
        ['Script', 'What it tests', 'Result'],
        [
            ['test_no_leakage_all.py',    'Zero data leakage across all 12 fraud datasets',       'Pass — all temporal splits clean'],
            ['test_mode4.py',             'BSDT blind-spot correction on fraud benchmarks',        '99.94% FP reduction, 0 missed fraud'],
            ['test_mode6_bench.py',       '66-variant systematic comparison',                      'Best model wins 10/12 datasets'],
            ['test_molecular_bench.py',   'Cross-domain: molecule property prediction',            'BSDT improves MAE on 4/6 targets'],
            ['test_geo_cyber.py',         'Cross-domain: cyber threat + geopolitical risk',        'AUC improvement vs baseline'],
            ['run_bsdt_benchmarks.py',    'Full 792-evaluation orchestration script',              'All 66 variants, 12 datasets'],
        ], col_widths=[2.2, 2.8, 1.9])
    add_caption(doc,
        'Table 2: Public benchmark scripts in the repository root. Each file is independently '
        'runnable: py -3 <script>. The 792-evaluation scale eliminates cherry-picking as '
        'an explanation for the results.')
    add_code_block(doc, [
        '# Run full BSDT benchmark suite (792 evaluations)',
        '# From repository root:',
        'py -3 run_bsdt_benchmarks.py',
        '',
        '# Reproduce the key fraud result:',
        'py -3 test_mode4.py',
        '',
        '# Verify zero data leakage:',
        'py -3 test_no_leakage_all.py',
        '',
        '# Cross-domain: ERCOT power grid + Terra/Luna crypto:',
        'py -3 test_geo_cyber.py',
    ], 'Figure 3: Reproduction commands. All scripts run on standard Python 3.11+ with '
       'scikit-learn, XGBoost, LightGBM, and NumPy. No GPU required. '
       'Expected runtime: 2–8 minutes per script on a standard laptop.')

    save(doc, 'OC4-1_BSDT_Research.docx',
         '03_Optional_Criteria_4_OC4/OC4-1_BSDT_Research.docx')

# ═══════════════════════════════════════════════════════════
# OC4-2: Academic Publications
# ═══════════════════════════════════════════════════════════
def build_oc4_2():
    doc = new_doc()
    add_header_block(doc,
        'Optional Criteria 4 — Academic Contributions through Research',
        'OC4-2: Academic Publications & Global Research Impact')

    add_section(doc, '1. Executive Summary')
    p = doc.add_paragraph()
    p.add_run('I wrote and published ')
    p.add_run('four research papers').bold = True
    p.add_run(' without institutional affiliation, co-authors, or promotion budget on TechRxiv '
              '(the IEEE engineering preprint platform) and Zenodo (a CERN-hosted open-access '
              'research archive). In under ten weeks they recorded ')
    p.add_run('365 views and 210 downloads').bold = True
    p.add_run('. Three were independently selected as required reading for an accredited '
              'postgraduate course by a ')
    p.add_run('Top 2% World Scientist').bold = True
    p.add_run(' (Stanford University annual citation impact ranking), without any prior contact '
              'with me. The course evidence is documented separately in OC4-3.')

    add_section(doc, '2. The AMTTP Infrastructure Paper (TechRxiv)')
    add_table(doc,
        ['Field', 'Detail'],
        [
            ['Published',  '27 February 2026'],
            ['Metrics',    '230 Views, 153 Downloads (as of 5 May 2026)'],
            ['Platform',   'TechRxiv — IEEE engineering preprint server'],
            ['DOI',        '10.36227/techrxiv.177220113.33816607/v1'],
        ], col_widths=[1.5, 5.0])
    add_body(doc,
        'The first paper, introducing the AMTTP system design to the academic community — specifically '
        'how the blockchain enforcement layer and the AI fraud-detection engine are connected. '
        'It recorded 230 views and 153 downloads in roughly ten weeks, with no institutional promotion.')
    add_image(doc, 'techrxiv_amttp.png',
        'Figure 1: TechRxiv analytics — 230 views, 153 downloads; 10 weeks, no institutional promotion.')

    add_section(doc, '3. Blind-Spot Decomposition Theory — BSDT (Zenodo)')
    add_table(doc,
        ['Field', 'Detail'],
        [
            ['Published',  '5 March 2026'],
            ['Metrics',    '135 Views, 57 Downloads (as of 5 May 2026)'],
            ['Platform',   'Zenodo — CERN-hosted open-access archive'],
            ['DOI',        '10.5281/zenodo.18870590'],
        ], col_widths=[1.5, 5.0])
    add_image(doc, 'zenodo_bsdt.png',
        'Figure 2: Zenodo analytics — 135 views, 57 downloads for the BSDT paper.')

    add_section(doc, '4. Blind-Spot Decomposition and the Geometry of System Collapse (Zenodo)')
    add_table(doc,
        ['Field', 'Detail'],
        [
            ['Published',  '16 March 2026'],
            ['Platform',   'Zenodo — CERN-hosted open-access archive'],
            ['DOI',        '10.5281/zenodo.19038783'],
        ], col_widths=[1.5, 5.0])
    add_body(doc,
        'This paper extends BSDT using topology and control theory, testing whether the same framework '
        'detects instability beyond financial fraud. It was applied to three independent crisis datasets '
        '(2008 US banking crisis, Terra/Luna collapse, 2021 Texas power-grid failure) without retraining; '
        'quantitative results are in OC4-1. This is generalisable mathematical theory, not '
        'product-specific implementation.')
    add_image(doc, 'zenodo_geometry.png',
        'Figure 3: Zenodo — Geometry of System Collapse. Three crisis datasets, no retraining. AUROC 0.9997 on ERCOT.')

    add_section(doc, '5. Universal Deviation Principle (Zenodo)')
    add_table(doc,
        ['Field', 'Detail'],
        [
            ['Published',  'March 2026'],
            ['Platform',   'Zenodo — CERN-hosted open-access archive'],
            ['DOI',        '10.5281/zenodo.19037688'],
        ], col_widths=[1.5, 5.0])
    add_body(doc,
        'A multi-operator framework for anomaly detection and classification with sensitivity '
        'guarantees. Selected as recommended reading in CPE 604 alongside the BSDT and AMTTP papers.')
    add_image(doc, 'zenodo_udp.png',
        'Figure 4: Zenodo record for the Universal Deviation Principle paper. '
        'DOI: 10.5281/zenodo.19037688. Published March 2026.')

    add_section(doc, '6. Combined Impact Summary')
    add_body(doc,
        'Four papers, three platforms, under ten weeks from first submission to academic adoption — '
        'all without institutional affiliation, co-authors, or any promotion budget.')
    add_table(doc,
        ['Paper', 'Platform', 'Views', 'Downloads', 'Adopted (CPE 604)'],
        [
            ['AMTTP Infrastructure',          'TechRxiv', '230', '153', 'Yes'],
            ['BSDT Framework',                'Zenodo',   '135', '57',  'Yes'],
            ['Geometry of System Collapse',   'Zenodo',   '—',   '—',   'Yes'],
            ['Universal Deviation Principle', 'Zenodo',   '—',   '—',   'No'],
            ['**Total**',                     '—',        '**365**', '**210**', '**3 of 4**'],
        ], col_widths=[2.6, 1.0, 0.8, 1.1, 1.5])
    add_caption(doc,
        'Table 1: Four-paper research impact. Three of four papers independently selected for '
        'CPE 604 postgraduate teaching. 365 views and 210 downloads across TechRxiv and Zenodo '
        'in under ten weeks, entirely organic.')
    add_body(doc,
        'The view and download counts are independently verifiable at the DOI pages listed above. '
        'The platform analytics are public and not controlled by the author. The academic adoption '
        'record is documented separately in OC4-3 with the signed confirmation letter and '
        'CPE 604 course slides.')
    add_body(doc,
        'Limit of claim: these are open preprints/archive publications rather than journal-accepted papers. '
        'Their evidential value comes from public DOI records, organic readership metrics, and independent '
        'selection into postgraduate teaching by a named external academic, not from an asserted peer-review status.')

    save(doc, 'OC4-2_Academic_Publications.docx',
         '03_Optional_Criteria_4_OC4/OC4-2_Academic_Publications.docx')

# ═══════════════════════════════════════════════════════════
# OC4-3: Academic Adoption (CPE 604)
# ═══════════════════════════════════════════════════════════
def build_oc4_3():
    doc = new_doc()
    add_header_block(doc,
        'Optional Criteria 4 — Academic Contributions through Research',
        'OC4-3: Academic Uptake in CPE 604 Teaching Materials')

    add_section(doc, '1. Executive Summary')
    p = doc.add_paragraph()
    p.add_run('Dr Sunday Adeola Ajagbe — ')
    p.add_run('Top 2% of World Scientists 2025').bold = True
    p.add_run(' (Stanford University annual citation impact study), Senior Lecturer at Abiola '
              'Ajimobi Technical University, Research Associate at the University of Zululand — '
              'independently selected three papers I wrote as required reading for his postgraduate '
              'course ')
    p.add_run('CPE 604: Techniques in Machine Learning for Low-Resource Languages').bold = True
    p.add_run('.')
    add_body(doc,
        'There was no prior relationship. The papers were not submitted for review. Dr Ajagbe '
        'discovered them independently, evaluated them on academic merit, and formally incorporated '
        'them into an accredited syllabus. The evidence is independently verifiable: the course '
        'slide deck, institutional logo, course title, and paper DOIs are submitted as exhibits '
        'alongside Dr Ajagbe\'s signed reference letter.')
    add_body(doc,
        'What this proves for OC4: external academic uptake. The strongest point is not simply that papers '
        'were uploaded online; it is that a credentialled academic with a public research profile selected '
        'three of them for postgraduate teaching without solicitation, payment, collaboration, or prior contact.')

    add_image(doc, 'cpe604_slide_course.png',
        'Figure 1: CPE 604 lecture slide open in PowerPoint Online, displaying the official Abiola '
        'Ajimobi Technical University logo and course title. This confirms an active, accredited '
        'postgraduate programme — not a private reading list or informal recommendation.')

    add_section(doc, '2. Recommended Reading Evidence')
    add_body(doc,
        'The final slide of the CPE 604 lecture deck (Slide 8 of 8) lists the following works under '
        '"Recommended Readings", alongside established peer-reviewed papers in the field:')
    add_bullet(doc, [
        'Odeyemi, O. (2026). Universal Deviation Principle: A Multi-Operator Framework for Anomaly Detection and Classification with Sensitivity Guarantees. Zenodo. DOI: 10.5281/zenodo.19037688',
        'Odeyemi, O. (2026). Blind-Spot Decomposition and the Geometry of System Collapse. Zenodo. DOI: 10.5281/zenodo.19038783',
        'Odeyemi, O. (2026). AMTTP: A Four-Layer Architecture for Deterministic Compliance Enforcement in Institutional DeFi. TechRxiv. DOI: 10.36227/techrxiv.177220113.33816607/v1',
    ])

    add_image(doc, 'cpe604_slide_references.png',
        'Figure 2: CPE 604 lecture deck, final slide (Slide 8 of 8) — Recommended Readings list. '
        'Three of my publications appear alongside established peer-reviewed papers (Bojar et al. 2018, '
        'Nekoto et al. 2020, Artetxe et al. 2019) at positions 1, 3, and 7 in the list. The placement '
        'confirms these were evaluated on their academic merit, not included as a courtesy.')

    add_section(doc, '3. Cross-Domain Academic Relevance')
    add_body(doc,
        'CPE 604 focuses on machine learning for low-resource natural languages — an application domain '
        'separate from financial compliance. Dr Ajagbe selected these papers on their mathematical '
        'content: BSDT and UDP are generalisable frameworks applicable wherever AI models exhibit '
        'systematic blind spots, and their inclusion in a language-technology course independently '
        'supports that claim.')
    add_body(doc,
        'These papers appear alongside established peer-reviewed work by Bojar et al. (2018) and '
        'Nekoto et al. (2020) — researchers with institutional affiliations and established citation '
        'records. The placement was based on merit and made without prior contact with the author.')

    add_section(doc, '4. Academic Significance')
    add_body(doc,
        'A senior academic included work produced by someone with no institutional affiliation, no '
        'prior relationship, and no presence in the course\'s subject area in an accredited '
        'postgraduate syllabus. The subject distance makes the evidence stronger: CPE 604 teaches '
        'machine learning for low-resource natural languages — entirely separate from financial '
        'compliance. Dr Ajagbe selected these papers on their mathematical content, independently '
        'judging the research suitable for formal postgraduate teaching.')
    add_body(doc,
        'Supporting materials: Signed reference letter from Dr Ajagbe · CPE 604 lecture handout · '
        'CPE 604 lecture slides.')

    add_section(doc, '5. Referee Credentials — Independent Verification')
    add_body(doc,
        'The academic adoption is evidenced by a named senior academic with a publicly verifiable '
        'research record. Dr Ajagbe\'s credentials can be independently confirmed through the Stanford '
        'University annual citation impact study and through academic database profiles.')
    add_table(doc,
        ['Credential', 'Detail', 'Verification'],
        [
            ['Academic rank',    'Senior Lecturer — Abiola Ajimobi Technical University (AATU)', 'institutional.aatu.edu.ng'],
            ['Research role',    'Research Associate — University of Zululand, South Africa',   'unizulu.ac.za'],
            ['Citation standing','Top 2% of World Scientists 2025',                              'Stanford University annual ranking'],
            ['Research area',    'Machine Learning, NLP, Embedded Systems, Cybersecurity',       'Scopus / Google Scholar'],
            ['Published papers', '70+ peer-reviewed articles (Scopus-indexed)',                  'scopus.com — search: Ajagbe Sunday Adeola'],
            ['h-index',         'Verified through Scopus researcher profile',                   'scopus.com'],
            ['Course',          'CPE 604: Techniques in Machine Learning for Low-Resource Languages', 'AATU postgraduate programme'],
        ], col_widths=[1.7, 2.8, 1.9])
    add_caption(doc,
        'Table 2: Dr Ajagbe\'s verifiable academic credentials. The Stanford Top 2% ranking '
        'is based on standardised citation metrics (c-score) published annually by Ioannidis et al. '
        'Every row in this table is independently confirmable from public sources — no trust in '
        'the applicant\'s assertion is required.')
    add_body(doc,
        'Evidence chain: (1) Dr Ajagbe is a real, active senior academic with a strong international '
        'research record — confirmed via Scopus and the Stanford ranking. (2) CPE 604 is a real '
        'accredited postgraduate course — confirmed by the submitted slide deck with institutional '
        'logo and course title. (3) Three of my papers appear in the CPE 604 recommended reading list '
        '— confirmed by the slide deck extract. (4) Dr Ajagbe had no prior relationship with me — '
        'confirmed in his signed reference letter. The combination of all four points constitutes '
        'independent peer validation of the research quality by a credentialled external evaluator.')

    save(doc, 'OC4-3_Academic_Adoption.docx',
         '03_Optional_Criteria_4_OC4/OC4-3_Academic_Adoption.docx')

# ═══════════════════════════════════════════════════════════
# Evidence Index: Criteria and Feature Mapping
# ═══════════════════════════════════════════════════════════
def build_evidence_index():
    doc = new_doc()
    add_header_block(doc,
        'Evidence Index — Criteria Mapping and Verification Anchors',
        'AMTTP Evidence Pack: What Each Document Proves')

    add_section(doc, '1. Criteria Map')
    add_body(doc,
        'This index is not a substitute for the evidence documents. It is a navigation layer for the assessor: '
        'each row states the criterion, the submitted evidence, the claim being proved, and the independent '
        'verification anchor. It is included to reduce ambiguity and prevent the technical exhibits from being '
        'read as isolated screenshots.')
    add_table(doc,
        ['Criterion', 'Evidence', 'What it proves', 'Verification anchor'],
        [
            ['MC', 'MC-1 Live Demonstration', 'Original digital product publicly deployed and operated', 'amttp.com, Cloudflare analytics, YouTube demo'],
            ['MC', 'MC-2 GitHub Contributions', 'Sustained sole-authored engineering across stack', 'github.com/segetii/AMTTP, commit history'],
            ['MC', 'MC-3 Smart Contracts', 'On-chain enforcement architecture and deployment authorship', 'Sepolia Etherscan addresses, Hardhat tests'],
            ['OC3', 'OC3-1 ML Pipeline', 'Significant technical contribution: ML + graph + rules risk engine', 'benchmark outputs, public scripts, Docker services'],
            ['OC3', 'OC3-2 War Room + Flutter', 'Product contribution: institutional and consumer compliance interfaces', 'Next.js/Flutter screenshots, RBAC config'],
            ['OC3', 'OC3-3 SDK + Pilot Agreement', 'External integration path and commercial pilot validation', 'signed/sealed Schedule A and signature exhibit'],
            ['OC3', 'OC3-4 Security Auditing', 'Production maturity: static analysis, fuzzing, gas validation', 'Slither, Echidna, Hardhat reports'],
            ['OC4', 'OC4-1 BSDT Research', 'Research contribution with reproducible cross-domain results', 'public benchmark scripts and results'],
            ['OC4', 'OC4-2 Publications', 'Public research dissemination with DOI metrics', 'TechRxiv/Zenodo DOI pages'],
            ['OC4', 'OC4-3 Academic Adoption', 'Independent academic uptake by named senior academic', 'CPE 604 slides + Dr Ajagbe letter'],
        ], col_widths=[0.7, 1.8, 2.6, 2.0])

    add_section(doc, '2. AMTTP Feature Coverage')
    add_table(doc,
        ['AMTTP feature', 'Primary evidence', 'Coverage'],
        [
            ['Pre-settlement AML enforcement', 'MC-1, MC-3, OC3-1', 'Covered'],
            ['Approve / Review / Escrow / Block decisions', 'MC-3, OC3-1', 'Covered'],
            ['Hybrid ML + graph + rules scoring', 'OC3-1', 'Covered'],
            ['Zero-knowledge compliance proofs', 'MC-3 §7', 'Covered'],
            ['Upgradeable UUPS enforcement contracts', 'MC-3 §5', 'Covered'],
            ['Cross-chain LayerZero support', 'OC3-3', 'Covered'],
            ['Kleros-style dispute resolution', 'MC-3 §6', 'Covered after upgrade'],
            ['Flutter consumer app + Next.js War Room', 'OC3-2', 'Covered'],
            ['Six-level RBAC', 'OC3-2 §3', 'Covered'],
            ['Explainable AI', 'OC3-2 §4, OC3-1', 'Covered'],
            ['Sanctions, KYC, PEP, georisk, monitoring services', 'OC3-1 §4', 'Covered'],
            ['SDKs for external integration', 'OC3-3 §2', 'Covered'],
            ['Cloudflare/nginx-secured deployment', 'MC-1, OC3-4', 'Covered'],
            ['Auditability / immutable evidence storage', 'OC3-2, OC3-4, MC-3', 'Covered'],
        ], col_widths=[2.6, 2.1, 1.5])

    add_section(doc, '3. Risk Controls Added in the Upgraded Pack')
    add_bullet(doc, [
        '**External validation separated from technical complexity:** OC3-3 now frames the pilot agreement as pilot-stage commercial validation, not overclaimed production adoption.',
        '**Kleros/dispute feature no longer implicit:** MC-3 now has a dedicated dispute-resolution and evidence-escrow section.',
        '**Academic claim bounded accurately:** OC4-2 states that DOI/preprint evidence is not being claimed as journal peer review; OC4-3 supplies the independent adoption proof.',
        '**Verification anchors made explicit:** each document is mapped to public URLs, addresses, DOIs, signed letters, or reproducible scripts.',
        '**Assessor navigation improved:** this index tells the reviewer exactly which document supports which criterion and which feature.',
    ])

    save(doc, '00_Evidence_Index_Mapping.docx',
         '00_Index/00_Evidence_Index_Mapping.docx')

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════
if __name__ == '__main__':
    print('=' * 60)
    print('Building all evidence documents (native DOCX)')
    print('=' * 60)
    build_evidence_index()
    build_mc1()
    build_mc2()
    build_mc3()
    build_oc3_1()
    build_oc3_2()
    build_oc3_3()
    build_oc3_4()
    build_oc4_1()
    build_oc4_2()
    build_oc4_3()
    print()
    print(f'All files saved to: {OUT_DIR}')
    print(f'Deployed to:        {SUB_DIR}')
