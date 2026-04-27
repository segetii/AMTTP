path = r'C:\amttp\research\adaptive-friction\pipeline\results\run_crypto_pairs_v11.py'
with open(path, encoding='utf-8') as f:
    src = f.read()

# The double-brace issue is from using a .format()-style string template.
# The affected region is from the [6] block start to the "Results table" comment.
block_start = "    # \u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n    #  [6]  v11: FAST"
block_end   = "\n    # \u2500\u2500 Results table"

i_start = src.index(block_start)
i_end   = src.index(block_end)
segment = src[i_start:i_end]
original_len = len(segment)

# Fix double-braces but keep f-string {var:fmt} intact.
# Strategy: only replace {{ and }} that are NOT inside an f-string interpolation.
# The dict literals all use {{ }} for the dict braces; the f-string format specs
# like {pct_hi_f:.1f} should remain single-brace.
# Since the patch used a regular Python string (not f-string) with {{ for literal {,
# ALL {{ and }} in this segment that are NOT part of a multi-char format spec should be fixed.

# Simpler: just replace {{ -> { and }} -> } everywhere in the segment,
# EXCEPT for the f-string lines (those lines have "f\"" prefix).
import re
lines = segment.split('\n')
fixed_lines = []
for line in lines:
    stripped = line.lstrip()
    if stripped.startswith('f"') or stripped.startswith("f'") or stripped.startswith('print(f"') or stripped.startswith('print(f\''):
        # f-string line: {{ and }} are intentional (escaped braces in f-strings)
        fixed_lines.append(line)
    else:
        # Regular Python: {{ means literal { in a format() call → convert to actual {
        fixed = line.replace('{{', '{').replace('}}', '}')
        fixed_lines.append(fixed)

segment_fixed = '\n'.join(fixed_lines)
print(f"Changed chars: {len(segment_fixed) - original_len}")

src_new = src[:i_start] + segment_fixed + src[i_end:]

with open(path, 'w', encoding='utf-8') as f:
    f.write(src_new)
print(f"saved. total lines: {src_new.count(chr(10))}")
