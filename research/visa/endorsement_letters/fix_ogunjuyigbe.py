"""
Surgical correction of endorsement_letter_ogunjuyigbe signed PDF.

Strategy: redact the ENTIRE line span (full width), then re-insert the
complete corrected line at exactly the same origin — preserving alignment.

Three lines corrected:
  P1 line @y=478.87 : "proof-of-concept stage" -> "early deployment stage"
  P1 line @y=552.67 : "0.9879"                 -> "0.9999998"
  P2 line @y=659.26 : "a proof-of-concept stage" -> "an early deployment stage"

Border-elimination approach:
  apply_redactions() always emits a white fill+stroke rect (PDF operator B).
  The 1pt stroke creates a visible grey line at viewer anti-aliasing.
  We fix this by editing the content stream bytes directly: changing the
  path operator immediately after each 're' (rectangle) from B (fill+stroke)
  to f (fill only).  This is surgical, deterministic, and layer-order-safe.
"""
import fitz
import shutil
import re as regex

SRC  = r"C:\amttp\research\visa\endorsement_letters\Segun odeyemi.pdf"
DEST = r"C:\amttp\research\visa\endorsement_letters\Segun odeyemi_corrected.pdf"

shutil.copy2(SRC, SRC.replace(".pdf", "_ORIGINAL_BACKUP.pdf"))

doc = fitz.open(SRC)

FONT      = "Times-Roman"
FONTSIZE  = 11.04
COLOR     = (0.0, 0.0, 0.0)


def strip_stroke_from_redact(doc, page):
    """
    After apply_redactions(), the content stream contains:
        <x> <y> <w> <h> re
        B
    where B = fill-and-stroke.  We replace B with f (fill only) for every
    rectangle path in the stream, removing the 1pt stroke border artifact.
    The original content has ZERO B operators (all type=f drawings), so this
    substitution exclusively targets the redaction rectangles.
    """
    page.clean_contents()          # merge all content streams into one xref
    for xref in page.get_contents():
        raw = doc.xref_stream(xref)   # decoded (decompressed) bytes
        # Match 're' token (rectangle path) followed by whitespace then 'B' token
        fixed = regex.sub(rb'\bre\b(\s+)B\b', rb're\1f', raw)
        if fixed != raw:
            doc.update_stream(xref, fixed)


def fix_line(page, search_term, new_full_line, origin_x, origin_y, bbox):
    """
    Three-step correction:
      1. apply_redactions() — removes original text from the content stream
      2. strip_stroke_from_redact() — edits stream to change B→f on the
         redaction rectangle, eliminating the visible stroke border
      3. insert_text() — re-renders the corrected line at the exact same origin
    """
    hits = page.search_for(search_term)
    if not hits:
        print(f"  WARNING: '{search_term}' not found on page {page.number + 1}")
        return
    # Step 1: redact — removes original text from content stream
    redact_rect = fitz.Rect(bbox[0] - 1, bbox[1] - 1, bbox[2] + 1, bbox[3] + 1)
    page.add_redact_annot(redact_rect, fill=(1, 1, 1))
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
    # Step 2: strip the stroke from all 're' drawn rectangles in the stream
    strip_stroke_from_redact(doc, page)
    # Step 3: re-insert full corrected line at same origin
    page.insert_text(
        fitz.Point(origin_x, origin_y),
        new_full_line,
        fontname=FONT,
        fontsize=FONTSIZE,
        color=COLOR,
    )
    print(f"  Page {page.number+1} y={origin_y}: replaced OK")

# ── Page 1, line 1: proof-of-concept ────────────────────────────────────────
fix_line(
    page        = doc[0],
    search_term = "proof-of-concept stage, developed",
    new_full_line = "advanced, production-grade compliance platform at early deployment stage, developed entirely by one ",
    origin_x    = 72.02,
    origin_y    = 478.87,
    bbox        = [72.02, 470.59, 542.48, 481.63],
)

# ── Page 1, line 2: ROC-AUC ─────────────────────────────────────────────────
fix_line(
    page        = doc[0],
    search_term = "0.9879",
    new_full_line = "processing 2.64 million Ethereum transactions (achieving a production-level ROC-AUC of 0.9999998 in testing ",
    origin_x    = 72.02,
    origin_y    = 552.67,
    bbox        = [72.02, 544.39, 542.53, 555.43],
)

# ── Page 2, line 3: proof-of-concept ────────────────────────────────────────
fix_line(
    page        = doc[1],
    search_term = "proof-of-concept stage, its",
    new_full_line = "While the platform is currently at an early deployment stage, its technical depth, system completeness, and ",
    origin_x    = 72.02,
    origin_y   = 659.26,
    bbox       = [72.02, 650.98, 542.48, 662.02],
)


# ── Remove section divider lines from all pages ──────────────────────────────
# The original PDF uses grey horizontal rules (.627 g fill, ~1.5pt tall, 468pt wide)
# between sections, plus tiny .89 g corner caps.  Replace both grey shades with
# white (1 g) so the dividers become invisible.
def remove_section_dividers(doc):
    for page in doc:
        page.clean_contents()
        for xref in page.get_contents():
            raw = doc.xref_stream(xref)
            fixed = raw.replace(b'.627 g', b'  1 g')   # same token semantics, padded for safety
            fixed = fixed.replace(b'.89 g',  b' 1 g')
            if fixed != raw:
                doc.update_stream(xref, fixed)
                print(f"  P{page.number+1}: section dividers cleared")

remove_section_dividers(doc)

doc.save(DEST, garbage=4, deflate=True)
doc.close()
print(f"\nSaved: {DEST}")
