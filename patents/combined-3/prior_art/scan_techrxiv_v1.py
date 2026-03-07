from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader


def main() -> None:
    prior_art_dir = Path(__file__).resolve().parent
    pdf_path = prior_art_dir / "techrxiv_amttp_v1.pdf"
    out_path = prior_art_dir / "techrxiv_v1_term_scan.txt"

    reader = PdfReader(str(pdf_path))
    text_pages = [(i + 1, (page.extract_text() or "")) for i, page in enumerate(reader.pages)]
    text = "\n".join(t for _, t in text_pages)

    norm = re.sub(r"\s+", " ", text).lower()

    # IMPORTANT: use regex/word-boundary matching for short tokens to avoid
    # substring false positives (e.g., "ttl" occurs inside "settlement").
    term_patterns: list[tuple[str, re.Pattern[str]]] = [
        # UDL/anomaly tensor / law-domain attribution
        ("anomaly tensor", re.compile(r"\banomaly\s+tensor\b")),
        ("spectrum operator", re.compile(r"\bspectrum\s+operator\b")),
        ("law domain", re.compile(r"\blaw\s+domain\b")),
        ("attribution", re.compile(r"\battribution\b")),
        ("boundary-centred", re.compile(r"\bboundary-centred\b")),
        # adaptive friction / gamma
        ("adaptive friction", re.compile(r"\badaptive\s+friction\b")),
        ("friction coefficient", re.compile(r"\bfriction\s+coefficient\b")),
        ("gamma*(x)", re.compile(r"gamma\*\(x\)", re.IGNORECASE)),
        ("gamma*", re.compile(r"gamma\*", re.IGNORECASE)),
        # enforcement profile
        ("enforcement profile", re.compile(r"\benforcement\s+profile\b")),
        ("decision matrix", re.compile(r"\bdecision\s+matrix\b")),
        # on-chain enforcement mechanics
        ("pre-settlement", re.compile(r"\bpre-\s*settlement\b")),
        ("escrow", re.compile(r"\bescrow\b")),
        ("revert", re.compile(r"\brevert\b")),
        ("time-to-live", re.compile(r"\btime-\s*to-\s*live\b")),
        ("ttl", re.compile(r"\bttl\b")),
        # zk proof plumbing
        ("groth16", re.compile(r"\bgroth16\b")),
        ("zk-snark", re.compile(r"\bzk-?\s*snarks?\b")),
        ("zero-knowledge", re.compile(r"\bzero-\s*knowledge\b")),
        ("poseidon", re.compile(r"\bposeidon\b")),
        ("merkle", re.compile(r"\bmerkle\b")),
        # compliance examples
        ("sanctions", re.compile(r"\bsanctions\b")),
        ("kyc", re.compile(r"\bkyc\b")),
        ("risk range proof", re.compile(r"\brisk\s+range\s+proofs?\b")),
    ]

    ctx_term_patterns: list[tuple[str, re.Pattern[str]]] = [
        ("pre-settlement", re.compile(r"\bpre-\s*settlement\b")),
        ("escrow", re.compile(r"\bescrow\b")),
        ("ttl", re.compile(r"\bttl\b")),
        ("groth16", re.compile(r"\bgroth16\b")),
        ("sanctions", re.compile(r"\bsanctions\b")),
        ("kyc", re.compile(r"\bkyc\b")),
        ("risk range proof", re.compile(r"\brisk\s+range\s+proofs?\b")),
    ]

    def contexts(pattern: re.Pattern[str], limit: int = 2) -> list[str]:
        matches = list(pattern.finditer(norm))
        out: list[str] = []
        for match in matches[:limit]:
            idx = match.start()
            start = max(0, idx - 220)
            end = min(len(norm), idx + 320)
            out.append(norm[start:end])
        return out

    pages_with_pre_settlement = [
        str(page_num)
        for page_num, page_text in text_pages
        if re.search(r"\bpre-\s*settlement\b", (page_text or "").lower())
    ]

    report_lines: list[str] = []
    report_lines.append(f"pages {len(reader.pages)}")
    report_lines.append("")
    report_lines.append("TERM CHECK (regex / word-boundary match)")
    for label, pattern in term_patterns:
        report_lines.append(f"{label:18s} -> {bool(pattern.search(norm))}")

    for label, pattern in ctx_term_patterns:
        ctx = contexts(pattern)
        if not ctx:
            continue
        report_lines.append("")
        report_lines.append(f"=== contexts for {label} (showing up to 2) ===")
        for snippet in ctx:
            report_lines.append(snippet)
            report_lines.append("---")

    report_lines.append("")
    report_lines.append("PAGES WITH pre-settlement:")
    report_lines.append(", ".join(pages_with_pre_settlement) if pages_with_pre_settlement else "(none)")

    out_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
