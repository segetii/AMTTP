from __future__ import annotations

import re
from pathlib import Path

import fitz  # PyMuPDF


def extract_pdf_text(pdf_path: Path) -> str:
    doc = fitz.open(str(pdf_path))
    pages_text: list[str] = []
    for i in range(len(doc)):
        text = doc.load_page(i).get_text("text")
        text = re.sub(r"\n{3,}", "\n\n", text)
        pages_text.append(text)
    return "\n\n".join(pages_text)


def main() -> None:
    pdf_path = Path(r"c:\amttp\papers\universal_deviation_law.pdf")
    out_path = Path(r"c:\amttp\papers\universal_deviation_law.extracted.txt")

    full_text = extract_pdf_text(pdf_path)

    # Heuristic section header extraction (useful for quick sanity check)
    headers: list[str] = []
    for line in full_text.splitlines():
        s = line.strip()
        if not s or len(s) > 120:
            continue
        if re.match(
            r"^(\d+\.?\d*\s+)?(Introduction|Related Work|Background|Method|Methods|Approach|"
            r"Mathematical Framework|Experiments|Experimental Evaluation|Results|Discussion|"
            r"Conclusion|Limitations|References)\b",
            s,
            re.IGNORECASE,
        ):
            headers.append(s)

    seen: set[str] = set()
    uniq_headers: list[str] = []
    for h in headers:
        key = h.lower()
        if key not in seen:
            seen.add(key)
            uniq_headers.append(h)

    out_path.write_text(full_text, encoding="utf-8", errors="replace")

    print(f"PDF: {pdf_path}")
    print(f"Wrote: {out_path}")
    print(f"Chars: {len(full_text)}")
    print("\n=== Candidate headers ===")
    for h in uniq_headers[:80]:
        print(h)


if __name__ == "__main__":
    main()
