"""
Build Personal Statement as DOCX + PDF without LaTeX.

Outputs (in this folder only):
  - personal_statement_final.docx
  - personal_statement_final.pdf
  - SUBMISSION_ORGANISED_BY_CATEGORY/04_Supporting_Evidence/Personal_Statement_Final.pdf
  - SUBMISSION_ORGANISED_BY_CATEGORY/04_Supporting_Evidence/Personal_Statement_Final.docx

Edit STATEMENT below to change content. Re-run:  py -3 build_personal_statement.py
"""

import re
import shutil
from pathlib import Path

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# ---------------------------------------------------------------------------
# CONTENT
# ---------------------------------------------------------------------------
TITLE = "Personal Statement"
NAME = "Olusegun Israel Odeyemi"
SUBTITLE = "UK Global Talent Visa \u2014 Digital Technology (Exceptional Promise)"

# Use **bold** markers for inline bold, and prefix headings with "## ".
STATEMENT = """\
I am applying under the Global Talent route (Exceptional Promise) as a security engineer and technical founder working at the intersection of cybersecurity, machine learning, and privacy-preserving verification. My case rests on a stack of independently verifiable outputs: a publicly deployed compliance platform, a sole-authored full-stack codebase, 38 Solidity files spanning core contracts, interfaces, and supporting modules, reproducible ML benchmarks, a live enterprise dashboard, security audit artefacts, four research preprints with documented academic adoption, and a UK patent filing. Together, these establish original innovation and a credible trajectory toward leadership in the UK’s digital technology sector.

## Strategic Motivation and the UK Roadmap

Britain leads globally in regulatory innovation. The **FCA\u2019s** evolving digital-asset framework, HM Treasury\u2019s stablecoin proposals, and the Bank of England\u2019s wholesale CBDC programme have together created an unmatched demand for the precise category of infrastructure I have built: **crypto-compliance middleware** that performs pre-settlement, on-chain, privacy-preserving enforcement. AMTTP is engineered as regulator-aligned middleware capable of supporting the **Travel Rule**, MLR 2017 risk-based monitoring, and **MiCA** obligations natively at the protocol layer.

My five-year roadmap is to incorporate a UK-headquartered RegTech company in **Derby**, drawing engineering talent from the Midlands technology corridor while engaging directly with London\u2019s regulatory and fintech community. Within that horizon I plan to **create 8\u201312 skilled engineering and compliance roles in the UK** (smart-contract, ML, zero-knowledge, and regulatory engineering) and convert AMTTP from a validated open protocol into a licensed **Compliance-as-a-Service** provider, supplying **crypto-compliance infrastructure** to UK fintechs, banks, and regulated digital-finance institutions. This directly supports the UK\u2019s positioning as a global hub for safe digital finance.

## Innovation: The AMTTP Protocol

To address the structural fragmentation in digital-asset compliance, I spent my **first three years in the United Kingdom** in sustained, independent research and development. Operating outside conventional institutional structures gave me the freedom to approach the problem from first principles. Pursuing this work independently was a deliberate strategic choice: it preserved the architectural autonomy and unencumbered IP position required to bring a complete, founder-owned compliance platform to the UK market. During that period I developed the mathematical and technical foundations of the platform, engineering the risk engine, the smart-contract enforcement layer, and the security architecture. That deliberate technical incubation culminated, from late 2025 onwards, in the public release of my work \u2014 live deployment, a public codebase, security-audit validations, formal IP filings, and research preprints. I rely not on conventional job titles, but on what I have demonstrably built, published, and had independently recognised.

The result is the **Anti-Money Laundering Transaction Transfer Protocol (AMTTP)**. Where conventional tooling acts post-settlement, AMTTP enables risk decisions before transaction finality. As an **independent founder**, working without institutional sponsorship, venture funding, or a delivery team, I architected and delivered the entire system end to end — spanning a Flutter consumer application and **Next.js** War Room dashboard, a **TypeScript Express.js** API gateway, a nine-service Python orchestrator, and the underlying smart-contract layer. This is not theoretical work: the platform is live on a Sepolia-backed environment at **amttp.com**, with public usage attested by independent Cloudflare analytics. Holding sole technical leadership of a system of this scope, while it remained publicly operational, evidences a capacity to lead production-grade digital infrastructure at a level rarely demonstrated outside a funded company.

## Technical Contribution and Security Excellence

My focus is the harder edge of compliance: privacy and verifiability. Grounded in formal cybersecurity training certified by **CompTIA Security+**, I applied defensive-architecture and threat-modelling discipline across every layer of the stack. Through **zkNAF**, I integrated **Groth16** zero-knowledge proofs so that sanctions checks and KYC confirmations may be performed without exposing personal data on a public ledger. To establish institutional-grade resilience, I subjected the contract layer to **Slither** static analysis and **Echidna** property-based fuzzing at deep iteration sequences, and complemented this with a Hardhat integration suite covering deployment, transfer logic, and policy enforcement. Together with the audited contract suite, these artefacts evidence engineering discipline well beyond the threshold expected at the Promise stage.

## Machine Learning, Operational Efficiency, and Intellectual Property

I designed and evaluated knowledge-distilled ML models on a dataset of **more than 625,000 Ethereum address samples**, producing distilled **XGBoost** and **LightGBM** students that retain strong fraud-detection performance while running on commodity CPUs. This eliminates the dependency on specialist GPU infrastructure and addresses the principal commercial barrier to deploying advanced detection in regulated environments. I protected this innovation by filing **UK Patent Application No. 1026066039** on **4 March 2026**, covering the ML risk-scoring pipeline, blockchain compliance architecture, zero-knowledge identity workflows, and adaptive-friction mechanisms.

## Academic Uptake and Outside Contribution

Although developed independently of any university, the research underpinning AMTTP has attracted early external recognition. Across my broader body of four research preprints, three specific papers \u2014 the **Universal Deviation Principle**, **Blind-Spot Decomposition and the Geometry of System Collapse**, and the **AMTTP architecture preprint** \u2014 were adopted in **April 2026** as recommended readings for the postgraduate course **CPE 604** by **Dr Sunday Adeola Ajagbe**, an independent academic with no prior supervisory relationship to me. Course slides and the associated module materials evidence direct integration into a live, accredited postgraduate curriculum. The selection was made on mathematical merit across a domain separate from financial compliance, which independently validates the generalisability of the underlying frameworks.

## Conclusion: Exceptional Promise

My profile is defined by **sustained independent execution as a founder**. Without a corporate brand or institutional sponsorship, I have produced a coherent body of work \u2014 a deployed platform, a public codebase, audited contracts, reproducible ML benchmarks, peer-cited research, and a UK patent filing \u2014 that demonstrates a capacity for leadership rather than mere participation. I am seeking endorsement to scale these innovations within the UK ecosystem: to **incorporate in Derby**, to **create skilled engineering and compliance roles**, to engage UK fintechs and regulators, and to advance the technical standards of British RegTech. The evidence submitted alongside this statement is not background colour for a narrative; it is the substance of the case.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def split_blocks(text: str):
    """Yield (kind, content) blocks. kind in {"heading", "para"}."""
    for raw in [b.strip() for b in text.strip().split("\n\n") if b.strip()]:
        if raw.startswith("## "):
            yield "heading", raw[3:].strip()
        else:
            yield "para", raw


def count_words(text: str) -> int:
    plain = BOLD_RE.sub(r"\1", text)
    plain = re.sub(r"##\s+", "", plain)
    return len(re.findall(r"\b[\w\u2019'-]+\b", plain))


# ---------------------------------------------------------------------------
# DOCX builder
# ---------------------------------------------------------------------------
def build_docx(out_path: Path):
    doc = Document()
    for section in doc.sections:
        section.top_margin = Cm(2.2)
        section.bottom_margin = Cm(2.2)
        section.left_margin = Cm(2.2)
        section.right_margin = Cm(2.2)

    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    # Title block
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(TITLE)
    run.bold = True
    run.font.size = Pt(18)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(NAME)
    r.font.size = Pt(13)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(SUBTITLE)
    r.font.size = Pt(11)
    r.italic = True

    doc.add_paragraph()

    for kind, content in split_blocks(STATEMENT):
        if kind == "heading":
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after = Pt(2)
            r = p.add_run(content)
            r.bold = True
            r.font.size = Pt(12)
            r.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
        else:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.space_after = Pt(6)
            p.paragraph_format.line_spacing = 1.25
            cursor = 0
            for m in BOLD_RE.finditer(content):
                if m.start() > cursor:
                    p.add_run(content[cursor:m.start()])
                br = p.add_run(m.group(1))
                br.bold = True
                cursor = m.end()
            if cursor < len(content):
                p.add_run(content[cursor:])

    doc.save(out_path)


# ---------------------------------------------------------------------------
# PDF builder (ReportLab)
# ---------------------------------------------------------------------------
def build_pdf(out_path: Path):
    styles = getSampleStyleSheet()
    base = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        alignment=TA_JUSTIFY,
        spaceAfter=8,
    )
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    name_style = ParagraphStyle(
        "Name",
        parent=base,
        fontSize=13,
        alignment=TA_CENTER,
        spaceAfter=2,
    )
    sub_style = ParagraphStyle(
        "Sub",
        parent=base,
        fontSize=11,
        alignment=TA_CENTER,
        fontName="Helvetica-Oblique",
        spaceAfter=14,
    )
    heading_style = ParagraphStyle(
        "Heading",
        parent=base,
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor="#1F3A5F",
        alignment=TA_LEFT,
        spaceBefore=10,
        spaceAfter=4,
    )

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=2.2 * cm,
        rightMargin=2.2 * cm,
        topMargin=2.2 * cm,
        bottomMargin=2.2 * cm,
        title="Personal Statement - Odeyemi Olusegun Israel",
        author=NAME,
    )

    story = [
        Paragraph(TITLE, title_style),
        Paragraph(NAME, name_style),
        Paragraph(SUBTITLE, sub_style),
    ]

    for kind, content in split_blocks(STATEMENT):
        if kind == "heading":
            story.append(Paragraph(content, heading_style))
        else:
            html = BOLD_RE.sub(r"<b>\1</b>", content)
            story.append(Paragraph(html, base))

    doc.build(story)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    here = Path(__file__).parent
    docx_path = here / "personal_statement_final.docx"
    pdf_path = here / "personal_statement_final.pdf"

    build_docx(docx_path)
    build_pdf(pdf_path)

    submission_dir = here / "SUBMISSION_ORGANISED_BY_CATEGORY" / "04_Supporting_Evidence"
    submission_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pdf_path, submission_dir / "Personal_Statement_Final.pdf")
    shutil.copy2(docx_path, submission_dir / "Personal_Statement_Final.docx")

    wc = count_words(STATEMENT)
    print(f"Word count: {wc}")
    if wc > 1000:
        print(f"OVER by: {wc - 1000}")
    else:
        print(f"Allowance left: {1000 - wc}")
    print(f"DOCX: {docx_path}")
    print(f"PDF : {pdf_path}")
    print(f"Deployed to: {submission_dir}")


if __name__ == "__main__":
    main()
