"""
Evidence Upgrade V2 builder.

Purpose: rebuild the AMTTP visa evidence pack around assessor logic rather than
technical documentation. Each document follows: claim -> independent proof ->
why it matters -> verification anchor -> anti-loophole note.

Run from: C:\amttp\research\visa
"""
from pathlib import Path
import shutil

import build_evidence_docx as b

BASE = Path(__file__).parent
V2 = BASE / "Evidence Upgrade V2"
DOCX_DIR = V2 / "01_UPGRADED_DOCX"
SUB_DIR = DOCX_DIR / "SUBMISSION_ORGANISED_BY_CATEGORY"
DOCX_DIR.mkdir(parents=True, exist_ok=True)
SUB_DIR.mkdir(parents=True, exist_ok=True)

# Redirect imported helper save() output into V2 only.
b.OUT_DIR = DOCX_DIR
b.SUB_DIR = SUB_DIR


def verification_table(doc, rows):
    b.add_table(doc, ["Claim", "Evidence", "Independent verification"], rows,
                col_widths=[1.8, 2.4, 2.4])


def impact_box(doc, text):
    p = doc.add_paragraph()
    p.add_run("Why this matters: ").bold = True
    p.add_run(text)


def loophole_note(doc, text):
    p = doc.add_paragraph()
    r = p.add_run("Anti-loophole note: ")
    r.bold = True
    p.add_run(text)


def build_index():
    doc = b.new_doc()
    b.add_header_block(doc, "Evidence Index", "AMTTP Evidence Pack V2 — Assessor Map")
    b.add_section(doc, "1. How to Read This Pack")
    b.add_body(doc,
        "This V2 pack is rebuilt around evidential logic, not code narration. Each exhibit states the criterion, "
        "the precise claim proved, the independent proof source, and the verification anchor. The technical system "
        "is used only where it proves leadership, contribution, impact, or independent uptake.")
    b.add_table(doc, ["Criterion", "Document", "Primary proof", "Anchor"], [
        ["MC", "MC-1 Live Product", "Public deployment + traffic + demo + pilot cross-reference", "amttp.com, Cloudflare, YouTube, sealed pilot"],
        ["MC", "MC-2 Authorship", "Sustained public engineering record", "GitHub commits, repo tree, Colab timestamps"],
        ["MC", "MC-3 On-chain Enforcement", "Deployed enforcement contracts incl. ZK + Kleros", "Sepolia Etherscan + tests"],
        ["OC3", "OC3-1 AI Risk Engine", "ML/graph/rules compliance engine", "benchmarks + services"],
        ["OC3", "OC3-2 Product Interfaces", "War Room + Flutter + RBAC + explainability", "screenshots + RBAC matrix"],
        ["OC3", "OC3-3 SDK & Pilot", "External integration route + signed/sealed pilot", "Schedule A + signatures/seal"],
        ["OC3", "OC3-4 Security", "Audit, fuzzing, gas and reliability proof", "Slither/Echidna/Hardhat"],
        ["OC4", "OC4-1 Research Results", "Reproducible BSDT cross-domain results", "scripts + metrics"],
        ["OC4", "OC4-2 Publications", "DOI-backed public dissemination", "TechRxiv/Zenodo"],
        ["OC4", "OC4-3 Academic Adoption", "Independent postgraduate teaching uptake", "CPE 604 + letter"],
    ], col_widths=[0.6, 1.7, 2.7, 2.0])
    b.add_section(doc, "2. Feature Coverage")
    b.add_table(doc, ["Feature", "Evidence"], [
        ["Pre-settlement AML; approve/review/escrow/block", "MC-1, MC-3, OC3-1"],
        ["Hybrid ML + graph + rules", "OC3-1"],
        ["ZK compliance proofs", "MC-3"],
        ["UUPS on-chain enforcement", "MC-3"],
        ["LayerZero cross-chain support", "OC3-3"],
        ["Kleros-style disputes", "MC-3 + OC3-4"],
        ["Flutter + Next.js War Room + RBAC + XAI", "OC3-2"],
        ["Sanctions/KYC/PEP/georisk/monitoring", "OC3-1"],
        ["SDKs, secured deployment, auditability", "OC3-3, OC3-4"],
    ], col_widths=[3.3, 3.0])
    b.save(doc, "00_Evidence_Index_Mapping.docx", "00_Index/00_Evidence_Index_Mapping.docx")


def build_mc1():
    doc = b.new_doc()
    b.add_header_block(doc, "Mandatory Criteria — Innovation and Potential Leadership",
                       "MC-1: Public AMTTP Deployment and External Validation")
    b.add_section(doc, "1. Claim")
    b.add_body(doc,
        "I independently designed and publicly deployed AMTTP, a real-time AML enforcement platform that makes "
        "risk decisions before blockchain settlement. This proves more than technical ability: it shows initiative, "
        "public release, user exposure, and external validation for an original digital-technology product.")
    verification_table(doc, [
        ["Public product exists", "amttp.com live deployment", "Cloudflare analytics + public URL"],
        ["Public interest", "1,220 unique visitors; 38,320 requests", "Cloudflare independent infrastructure analytics"],
        ["Working system", "4-minute demo and product screens", "YouTube demo + War Room screenshots"],
        ["External validation", "Signed/sealed pilot agreement", "Glitterati Estates Schedule A + signature/seal"],
    ])
    impact_box(doc,
        "AMTTP shifts AML from post-event reporting to pre-settlement enforcement, directly addressing a major "
        "digital-asset compliance problem: once assets move on-chain, reversal is difficult or impossible.")
    b.add_image(doc, "cloudflare_analytics.png",
        "Figure 1: Independent Cloudflare analytics for amttp.com — public traffic evidence outside the applicant's control.", width=5.2)
    b.add_image(doc, "amttp_architecture.png",
        "Figure 2: Four-layer architecture: Flutter/Next.js frontends, Express gateway, nine FastAPI services, Solidity contracts.", width=5.2)
    loophole_note(doc,
        "This exhibit does not rely only on screenshots. It ties the product to third-party infrastructure analytics, a public URL, "
        "a video demonstration, and a signed/sealed external pilot document.")
    b.save(doc, "MC-1_AMTTP_Live_Demonstration.docx", "01_Mandatory_Criteria_MC/MC-1_AMTTP_Live_Demonstration.docx")


def build_mc2():
    doc = b.new_doc()
    b.add_header_block(doc, "Mandatory Criteria — Sustained Technical Leadership",
                       "MC-2: Verifiable Sole Authorship and Sustained Engineering Record")
    b.add_section(doc, "1. Claim")
    b.add_body(doc,
        "The AMTTP repository proves sustained, self-directed authorship across blockchain, AI, backend, frontend, SDK, security, "
        "and research tooling. This is not a single prototype; it is a full-stack engineering record spanning September 2025 to April 2026.")
    verification_table(doc, [
        ["Sustained development", "361 commits over eight months", "github.com/segetii/AMTTP commit history"],
        ["Sole-authored breadth", "Python, TypeScript, Dart, Solidity", "repo tree + per-file diffs"],
        ["ML work gap explained", "Nov/Dec Colab artefacts", "Google Drive timestamped export folders"],
        ["Delivery not theory", "contracts, services, frontends, SDKs", "monorepo folders and deployments"],
    ])
    b.add_image(doc, "github_green_squares.png",
        "Figure 1: GitHub activity graph — sustained public development cadence.", width=5.0)
    b.add_image(doc, "google_drive_colab_artifacts.png",
        "Figure 2: Google-timestamped Colab artefacts corroborating ML work outside GitHub during Nov-Dec 2025.", width=5.0)
    b.add_table(doc, ["Domain", "Deliverable", "Verification"], [
        ["AI/ML", "risk engine + benchmarks", "ml/Automation/"],
        ["Blockchain", "38 Solidity contracts", "contracts/ + Sepolia"],
        ["Backend", "gateway + microservices", "backend/"],
        ["Frontend", "Next.js + Flutter", "frontend/"],
        ["Distribution", "TS + Python SDKs", "packages/"],
    ], col_widths=[1.3, 2.5, 2.2])
    loophole_note(doc,
        "The claim is independently inspectable: repository timestamps, file history, folder structure, and Colab timestamps provide a verification chain.")
    b.save(doc, "MC-2_GitHub_Contributions.docx", "01_Mandatory_Criteria_MC/MC-2_GitHub_Contributions.docx")


def build_mc3():
    doc = b.new_doc()
    b.add_header_block(doc, "Mandatory Criteria — On-chain Innovation",
                       "MC-3: Deployed Smart Contract Enforcement, ZK Proofs, and Dispute Escrow")
    b.add_section(doc, "1. Claim")
    b.add_body(doc,
        "AMTTP's blockchain layer turns off-chain AML intelligence into enforceable on-chain outcomes: approve, review, escrow, or block. "
        "The evidence proves deployed authorship, not merely local code: Etherscan addresses, tests, and contract interfaces are public.")
    verification_table(doc, [
        ["Upgradeable enforcement", "UUPS proxy contracts", "Etherscan Source Code (Proxy) records"],
        ["Decision outcomes", "Approve/Review/Escrow/Block policy interface", "AMTTPCore / PolicyEngine tests"],
        ["Privacy compliance", "ZK-NAF verifiers", "Risk/KYC/Sanctions verifier addresses"],
        ["Dispute fairness", "Kleros-style escrow + evidence + ruling callback", "AMTTPDisputeResolver + executeDisputeRuling"],
    ])
    b.add_image(doc, "vscode_multitab.png",
        "Figure 1: Policy interface defining deterministic outcomes before settlement.", width=5.2)
    b.add_image(doc, "etherscan_contract.png",
        "Figure 2: Etherscan deployment evidence showing proxy source record and deployer verification.", width=5.2)
    b.add_section(doc, "2. Contract Verification Matrix")
    b.add_table(doc, ["Contract", "Address / proof", "Purpose"], [
        ["AMTTPCore", "0x05687F...b612", "Escrow and settlement"],
        ["PolicyEngine", "0xe774E0...8703", "Approve/review/escrow/block rules"],
        ["DisputeResolver", "0x9EB935...53D7", "Kleros-style evidence/ruling"],
        ["CrossChain", "0x4f21b1...2953", "LayerZero propagation"],
        ["ZK verifiers", "Risk/KYC/Sanctions addresses", "Private compliance proofs"],
    ], col_widths=[1.5, 2.0, 2.5])
    impact_box(doc,
        "The Kleros-style dispute layer removes a loophole in automated AML: high-risk transfers are not merely blocked or released; "
        "they can be held with evidence and resolved through a deterministic on-chain ruling path.")
    b.add_image(doc, "vscode_hardhat_tests.png",
        "Figure 3: Hardhat tests — deployment and decision-matrix validation.", width=5.0)
    loophole_note(doc,
        "Contract addresses and test output are externally inspectable; the pack does not ask the assessor to trust a private claim of deployment.")
    b.save(doc, "MC-3_Smart_Contracts.docx", "01_Mandatory_Criteria_MC/MC-3_Smart_Contracts.docx")


def build_oc3_1():
    doc = b.new_doc()
    b.add_header_block(doc, "Optional Criteria 3 — Significant Technical Contribution",
                       "OC3-1: AI Risk Engine — Hybrid ML, Graph, Rules, and Services")
    b.add_section(doc, "1. Claim")
    b.add_body(doc,
        "I built the AMTTP risk engine that converts transaction, graph, sanctions, georisk, monitoring, integrity, and explainability signals "
        "into a single compliance verdict. This is the core technical contribution: an operational AI compliance pipeline, not a notebook result.")
    verification_table(doc, [
        ["Model performance", "ROC-AUC 0.9999998 on 625,168 Ethereum transactions", "evaluation outputs + scripts"],
        ["Hybrid architecture", "ML + GraphSAGE + policy rules", "services on ports 8000-8010"],
        ["Operational deployment", "FastAPI microservices + orchestrator", "docker-compose + service code"],
        ["Explainability", "feature importance + factor weights", "integration_service.py + UI panel"],
    ])
    b.add_image(doc, "ml_evaluation_results.png",
        "Figure 1: Raw benchmark output for the production model.", width=5.1)
    b.add_table(doc, ["Service", "Port", "Contribution"], [
        ["ML Risk", "8000", "XGBoost/LightGBM scoring"],
        ["Graph", "8001", "wallet-network analysis"],
        ["Policy/Sanctions/GeoRisk", "8003-8006", "rules, lists, jurisdiction"],
        ["Orchestrator", "8007", "parallel fan-out verdict"],
        ["Integrity/XAI/ZK", "8008-8010", "tamper checks, explanations, proofs"],
    ], col_widths=[1.8, 1.0, 3.2])
    impact_box(doc,
        "The contribution is institutional usefulness: sub-second, explainable, CPU-deployable compliance decisions that can be enforced on-chain.")
    loophole_note(doc,
        "The model claim is supported by benchmark artefacts and service integration, not by an isolated accuracy statement.")
    b.save(doc, "OC3-1_ML_Pipeline.docx", "02_Optional_Criteria_3_OC3/OC3-1_ML_Pipeline.docx")


def build_oc3_2():
    doc = b.new_doc()
    b.add_header_block(doc, "Optional Criteria 3 — Product Contribution",
                       "OC3-2: Compliance Interfaces — War Room, Flutter, RBAC, and Explainability")
    b.add_section(doc, "1. Claim")
    b.add_body(doc,
        "I built two complementary interfaces for the same compliance backend: a Next.js institutional War Room for officers and a Flutter consumer app for end users. "
        "The contribution is productisation: making complex AML decisions usable by different regulated roles.")
    verification_table(doc, [
        ["Institutional UI", "War Room dashboard, alerts, reports", "Next.js screens + port 3006"],
        ["Consumer UI", "Flutter Focus Mode", "Flutter screenshots + six-platform codebase"],
        ["Access control", "R1-R6 RBAC matrix", "shared rbac_config.json"],
        ["Auditability", "Explainability panel", "factor weights in UI + API"],
    ])
    b.add_image(doc, "warroom_alerts.png",
        "Figure 1: War Room alerts — institutional compliance view for R3-R6 roles.", width=5.1)
    b.add_image(doc, "warroom_explainability.png",
        "Figure 2: Explainability panel showing factor-level reasoning for audit trail.", width=5.1)
    b.add_image(doc, "flutter_home_pep.png",
        "Figure 3: Flutter Focus Mode for R1/R2 users; consumer layer connects to the same compliance backend.", width=2.6)
    b.add_image(doc, "flutter_activity_menu.png",
        "Figure 4: Flutter activity/navigation flow for transaction outcomes and disputes.", width=2.6)
    loophole_note(doc,
        "This document is distinct from OC3-1: it proves product/interface delivery and role enforcement, not model accuracy.")
    b.save(doc, "OC3-2_War_Room_Dashboard.docx", "02_Optional_Criteria_3_OC3/OC3-2_War_Room_Dashboard.docx")


def build_oc3_3():
    doc = b.new_doc()
    b.add_header_block(doc, "Optional Criteria 3 — Commercial and Integration Contribution",
                       "OC3-3: SDK Distribution and Signed External Pilot Validation")
    b.add_section(doc, "1. Claim")
    b.add_body(doc,
        "I converted AMTTP from a closed project into externally integrable infrastructure by building TypeScript and Python SDKs, then obtained a signed and company-sealed pilot agreement for evaluation in a real business setting.")
    verification_table(doc, [
        ["SDK distribution path", "TypeScript + Python packages", "packages/client-sdk and packages/python-sdk"],
        ["Cross-chain integration", "LayerZero support across EVM networks", "AMTTPCrossChain contract + SDK"],
        ["External commercial validation", "Signed/sealed pilot agreement", "Schedule A + signature/seal exhibit"],
        ["Bounded claim", "Pilot evaluation, not revenue claim", "agreement wording and scope"],
    ])
    b.add_image(doc, "vscode_sdk_packages.png",
        "Figure 1: Two SDK packages exposing AMTTP to external integrators.", width=5.1)
    b.add_image(doc, "pilot_agreement_signed.png",
        "Figure 2: Schedule A pilot components and signed/sealed signature page together — external validation of evaluation scope.", width=5.35)
    impact_box(doc,
        "The signed/sealed pilot is the strongest commercial evidence: an external company accepted defined AMTTP components for evaluation rather than merely viewing a demo.")
    loophole_note(doc,
        "The claim is deliberately limited to independent pilot validation. It does not overclaim paid production deployment.")
    b.save(doc, "OC3-3_CrossChain_SDK.docx", "02_Optional_Criteria_3_OC3/OC3-3_CrossChain_SDK.docx")


def build_oc3_4():
    doc = b.new_doc()
    b.add_header_block(doc, "Optional Criteria 3 — Reliability and Security Contribution",
                       "OC3-4: Auditability, Fuzzing, Gas Validation, and Immutable Evidence")
    b.add_section(doc, "1. Claim")
    b.add_body(doc,
        "AMTTP was not only built; it was tested for institutional reliability. I ran static analysis, adversarial fuzzing, integration tests, and gas validation across the smart-contract layer.")
    verification_table(doc, [
        ["Static analysis", "Slither audit", "audit artefacts in repository"],
        ["Adversarial testing", "Echidna property fuzzing", "50,000 randomised sequences"],
        ["Integration tests", "Hardhat test suite", "passing test output"],
        ["Cost viability", "gas validation report", "operation-level cost evidence"],
    ])
    b.add_code_block(doc, [
        "slither contracts/ --config-file audit/slither.config.json",
        "Scope: 38 original AMTTP contracts + inherited OpenZeppelin dependencies",
        "Reviewed: access control, reentrancy, upgrade safety, unchecked calls",
    ], "Figure 1: Slither audit command and scope — reproducible from the public repository.")
    b.add_code_block(doc, [
        "testLimit: 50000",
        "seqLen: 100",
        "workers: 4",
        "properties: owner-only upgrades, escrow conservation, no unauthorized release",
    ], "Figure 2: Echidna fuzzing configuration — adversarial random transaction sequences.")
    b.add_image(doc, "vscode_hardhat_tests.png",
        "Figure 3: Hardhat integration tests — deployment and decision-flow verification.", width=5.0)
    b.add_image(doc, "gas_report.png",
        "Figure 4: Gas validation report showing production-cost awareness.", width=5.0)
    loophole_note(doc,
        "This exhibit proves reliability discipline. It is separated from MC-3, which proves deployed contract innovation.")
    b.save(doc, "OC3-4_Security_Auditing.docx", "02_Optional_Criteria_3_OC3/OC3-4_Security_Auditing.docx")


def build_oc4_1():
    doc = b.new_doc()
    b.add_header_block(doc, "Optional Criteria 4 — Research Contribution",
                       "OC4-1: BSDT Research — Reproducible Cross-Domain Results")
    b.add_section(doc, "1. Claim")
    b.add_body(doc,
        "I developed Blind-Spot Decomposition Theory (BSDT), a general diagnostic framework tested beyond AMTTP: fraud, cryptocurrency collapse, banking stress, and grid instability.")
    verification_table(doc, [
        ["Fraud benchmarks", "99.94% false-positive reduction", "test_mode4.py / benchmark outputs"],
        ["Cross-domain result", "Terra/Luna 30-hour warning", "public on-chain data"],
        ["Grid result", "ERCOT 72-hour warning", "public ERCOT data"],
        ["Reproducibility", "792 evaluations", "run_bsdt_benchmarks.py"],
    ])
    b.add_table(doc, ["Scenario", "Result", "Why relevant"], [
        ["12 fraud datasets", "zero missed fraud in 10/12", "AML relevance"],
        ["Terra/Luna", "30-hour warning", "digital-asset risk"],
        ["ERCOT", "AUC 0.9997", "cross-domain generality"],
        ["FDIC banks", "AUROC 0.867", "financial systemic risk"],
    ], col_widths=[2.0, 1.8, 2.3])
    impact_box(doc,
        "OC4 is not based only on writing papers; it is based on a reproducible research programme with measurable cross-domain results.")
    loophole_note(doc,
        "All headline results are tied to scripts or public datasets, reducing cherry-picking risk.")
    b.save(doc, "OC4-1_BSDT_Research.docx", "03_Optional_Criteria_4_OC4/OC4-1_BSDT_Research.docx")


def build_oc4_2():
    doc = b.new_doc()
    b.add_header_block(doc, "Optional Criteria 4 — Research Dissemination",
                       "OC4-2: DOI-backed Publications and Bounded Impact Metrics")
    b.add_section(doc, "1. Claim")
    b.add_body(doc,
        "I publicly disseminated four research papers through DOI-backed platforms. This exhibit supports OC4 as dissemination evidence; the stronger external-impact evidence is OC4-3 academic adoption.")
    verification_table(doc, [
        ["AMTTP paper", "TechRxiv DOI + 230 views / 153 downloads", "10.36227/techrxiv.177220113.33816607/v1"],
        ["BSDT paper", "Zenodo DOI + 135 views / 57 downloads", "10.5281/zenodo.18870590"],
        ["Geometry paper", "Zenodo DOI", "10.5281/zenodo.19038783"],
        ["UDP paper", "Zenodo DOI", "10.5281/zenodo.19037688"],
    ])
    b.add_image(doc, "techrxiv_amttp.png",
        "Figure 1: TechRxiv analytics for AMTTP infrastructure paper.", width=5.0)
    b.add_image(doc, "zenodo_bsdt.png",
        "Figure 2: Zenodo analytics for BSDT paper.", width=5.0)
    b.add_table(doc, ["Metric", "Value", "Limit of claim"], [
        ["Views/downloads", "365 views; 210 downloads", "organic readership metric"],
        ["Publication type", "TechRxiv / Zenodo", "preprint/archive, not journal peer review"],
        ["External uptake", "3 papers selected in CPE 604", "proved in OC4-3"],
    ], col_widths=[1.5, 2.0, 2.5])
    loophole_note(doc,
        "This document does not mislabel preprints as peer-reviewed journal articles. It uses them as public dissemination and DOI evidence.")
    b.save(doc, "OC4-2_Academic_Publications.docx", "03_Optional_Criteria_4_OC4/OC4-2_Academic_Publications.docx")


def build_oc4_3():
    doc = b.new_doc()
    b.add_header_block(doc, "Optional Criteria 4 — Independent Academic Adoption",
                       "OC4-3: CPE 604 Postgraduate Teaching Uptake by External Academic")
    b.add_section(doc, "1. Claim")
    b.add_body(doc,
        "The strongest OC4 evidence is independent adoption: Dr Sunday Adeola Ajagbe, a senior academic and Stanford Top 2% World Scientist, selected three of my papers as recommended reading for CPE 604 without prior relationship, payment, or solicitation.")
    verification_table(doc, [
        ["External evaluator", "Dr Sunday Adeola Ajagbe", "public academic profile + signed letter"],
        ["No prior relationship", "confirmed in reference letter", "independent statement"],
        ["Course adoption", "CPE 604 slide deck", "institutional logo + course title"],
        ["Specific papers", "three Odeyemi papers listed", "recommended reading slide + DOIs"],
    ])
    b.add_image(doc, "cpe604_slide_course.png",
        "Figure 1: Official CPE 604 course slide with institutional branding.", width=5.0)
    b.add_image(doc, "cpe604_slide_references.png",
        "Figure 2: Recommended readings slide listing three papers by the applicant alongside established literature.", width=5.0)
    b.add_table(doc, ["Why this is strong", "Explanation"], [
        ["Independent", "selected without collaboration or prior contact"],
        ["External", "decision made by a named senior academic"],
        ["Academic", "incorporated into postgraduate teaching materials"],
        ["Cross-domain", "ML for low-resource languages is separate from AML/DeFi"],
    ], col_widths=[1.8, 4.2])
    loophole_note(doc,
        "The evidence is not self-citation or self-publication only; it is external academic use evidenced by slides and a signed letter.")
    b.save(doc, "OC4-3_Academic_Adoption.docx", "03_Optional_Criteria_4_OC4/OC4-3_Academic_Adoption.docx")


def main():
    print("=" * 70)
    print("Building Evidence Upgrade V2 — redesigned assessor-facing pack")
    print("=" * 70)
    builders = [
        build_index,
        build_mc1, build_mc2, build_mc3,
        build_oc3_1, build_oc3_2, build_oc3_3, build_oc3_4,
        build_oc4_1, build_oc4_2, build_oc4_3,
    ]
    for fn in builders:
        fn()
    # Carry over non-generated supporting docs into V2 output folder.
    src_dir = BASE / "EVIDENCE_DOCX_COPIES"
    for name in [
        "CV_Odeyemi_Olusegun_Israel.docx",
        "Letter_A_Ogunjuyigbe.docx",
        "Letter_B_Ajagbe.docx",
        "Personal_Statement_Final.docx",
        "Supporting_IP_Patent.docx",
        "Tech Nation Vis1.docx",
    ]:
        src = src_dir / name
        if src.exists():
            shutil.copy2(src, DOCX_DIR / name)
    print(f"V2 DOCX saved to: {DOCX_DIR}")
    print(f"V2 category folder: {SUB_DIR}")


if __name__ == "__main__":
    main()
