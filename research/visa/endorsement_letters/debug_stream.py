"""
Dump raw content stream around the three corrected line positions
to see exactly what PDF operators are present.
"""
import fitz

# Check BOTH the original (after one redaction applied) and the corrected output
for fname, label in [
    (r"C:\amttp\research\visa\endorsement_letters\Segun odeyemi_corrected.pdf", "CORRECTED"),
]:
    print(f"\n{'='*60}")
    print(f"FILE: {label}")
    doc = fitz.open(fname)

    for pno, target_ys in [(0, [470, 543]), (1, [649])]:
        page = doc[pno]
        page.clean_contents()
        xrefs = page.get_contents()
        print(f"\n  Page {pno+1}: {len(xrefs)} content xref(s)")
        for xref in xrefs:
            raw = doc.xref_stream(xref)
            print(f"  xref {xref}: {len(raw)} bytes, first 10 bytes type={type(raw)}")
            # Search for 're' operator in the stream
            lines = raw.split(b'\n')
            for i, line in enumerate(lines):
                # Look for lines containing 're' and nearby lines for context
                if b' re' in line or line.strip() == b're':
                    # Print context: 3 lines before and after
                    start = max(0, i-3)
                    end = min(len(lines), i+4)
                    print(f"    --- 're' at byte-line {i} ---")
                    for j in range(start, end):
                        marker = ">>>" if j == i else "   "
                        print(f"    {marker} [{j}]: {lines[j]}")
            # Also search for 'B' and 'b' operators
            print(f"  Occurrences of standalone B: {raw.count(b'\\nB\\n') + raw.count(b' B\\n') + raw.count(b'\\nB ')}")
            import re as regex
            b_ops = regex.findall(rb'(?<!\w)B(?!\w)', raw)
            f_ops = regex.findall(rb'(?<!\w)f(?!\w)', raw)
            print(f"  Standalone B count: {len(b_ops)}, standalone f count: {len(f_ops)}")
    doc.close()
