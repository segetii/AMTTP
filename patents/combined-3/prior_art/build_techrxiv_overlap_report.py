from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader


def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def find_term_pages(pages: list[str], pattern: re.Pattern[str]) -> list[int]:
    out: list[int] = []
    for i, p in enumerate(pages):
        if pattern.search(p):
            out.append(i + 1)
    return out


def extract_snippets(
    pages: list[str],
    pattern: re.Pattern[str],
    *,
    per_match: int = 1,
    ctx: int = 220,
) -> list[tuple[int, str]]:
    snippets: list[tuple[int, str]] = []
    for i, p in enumerate(pages):
        matches = list(pattern.finditer(p))
        if not matches:
            continue
        for m in matches[:per_match]:
            start = max(0, m.start() - ctx)
            end = min(len(p), m.end() + ctx)
            snippets.append((i + 1, p[start:end]))
    return snippets


def compile_term_pattern(term: str) -> re.Pattern[str]:
    t = term.lower().strip()

    # Multi-word phrases
    if t == "decision matrix":
        return re.compile(r"\bdecision\s+matrix\b")
    if t == "anomaly tensor":
        return re.compile(r"\banomaly\s+tensor\b")
    if t == "spectrum operator":
        return re.compile(r"\bspectrum\s+operator\b")
    if t == "law domain":
        return re.compile(r"\blaw\s+domain\b")
    if t == "adaptive friction":
        return re.compile(r"\badaptive\s+friction\b")
    if t == "time-to-live":
        return re.compile(r"\btime-\s*to-\s*live\b")

    # Hyphen/linebreak tolerant terms
    if t == "pre-settlement":
        return re.compile(r"\bpre-\s*settlement\b")
    if t == "zero-knowledge":
        return re.compile(r"\bzero-\s*knowledge\b")
    if t == "zk-snark":
        return re.compile(r"\bzk-?\s*snarks?\b")
    if t == "non-membership":
        return re.compile(r"\bnon-\s*membership\b")

    # Token/short terms (avoid substring false positives like "ttl" in "settlement",
    # or "block" in "blockchain")
    if t in {"approve", "review", "escrow", "block", "sanctions", "kyc", "groth16", "ttl", "revert", "poseidon", "merkle"}:
        return re.compile(rf"\b{re.escape(t)}\b")

    # Default: literal substring match (escaped)
    return re.compile(re.escape(t))


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    prior_art_dir = base_dir / "prior_art"
    pdf_path = prior_art_dir / "techrxiv_amttp_v1.pdf"

    spec_tex = base_dir / "patent_specification.tex"

    reader = PdfReader(str(pdf_path))
    raw_pages = [(page.extract_text() or "") for page in reader.pages]
    pages = [norm_text(p) for p in raw_pages]

    # Terms that correspond to "exposed" AMTTP v1 elements
    terms = [
        ("pre-settlement", "Pre-settlement controls (general concept)"),
        ("decision matrix", "Deterministic decision matrix"),
        ("approve", "Approve action"),
        ("review", "Review action"),
        ("escrow", "Escrow action / time-locking concept"),
        ("block", "Block action"),
        ("sanctions", "Sanctions screening"),
        ("kyc", "KYC"),
        ("risk range", "Risk range proof concept"),
        ("non-membership", "Non-membership proof concept"),
        ("zero-knowledge", "Zero-knowledge proofs"),
        ("zk-snark", "zk-SNARK mention"),
        ("groth16", "Groth16 mention"),
        ("ttl", "TTL / freshness"),
        # Things you are trying to keep as novelty anchors
        ("anomaly tensor", "Anomaly tensor"),
        ("spectrum operator", "Spectrum operators"),
        ("law domain", "Per-law-domain attribution"),
        ("adaptive friction", "Adaptive friction"),
        ("gamma", "Gamma / friction coefficient notation"),
        ("revert", "Revert / EVM enforcement"),
        ("poseidon", "Poseidon hash"),
        ("merkle", "Merkle tree"),
    ]

    out_lines: list[str] = []
    out_lines.append("# TechRxiv v1 → Combined-3 overlap (term-level)\n")
    out_lines.append(f"- Source PDF: {pdf_path.name} ({len(reader.pages)} pages)")
    out_lines.append(f"- Current UK spec: {spec_tex.name}")
    out_lines.append("")

    out_lines.append("## Term map (page hits)")
    out_lines.append("Term | Meaning | Pages")
    out_lines.append("--- | --- | ---")
    for term, meaning in terms:
        hits = find_term_pages(pages, compile_term_pattern(term))
        pages_str = ", ".join(map(str, hits)) if hits else "(none found)"
        out_lines.append(f"{term} | {meaning} | {pages_str}")

    out_lines.append("")
    out_lines.append("## Snippets (first hit per term)")
    for term, meaning in terms:
        snippets = extract_snippets(pages, compile_term_pattern(term), per_match=1)
        if not snippets:
            continue
        page_num, snippet = snippets[0]
        out_lines.append(f"### {term} — {meaning}")
        out_lines.append(f"Page {page_num}")
        out_lines.append("")
        out_lines.append("> " + snippet.replace("\n", " ").strip())
        out_lines.append("")

    (prior_art_dir / "techrxiv_v1_overlap_terms.md").write_text("\n".join(out_lines), encoding="utf-8")


if __name__ == "__main__":
    main()
