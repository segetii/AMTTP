"""Fix: move conformal methods inside each engine class body.

The previous patch inserted methods between classes (outside class body).
This fix removes the misplaced methods and re-inserts them inside each class.
"""
import os, sys, re

FP = os.path.join(os.path.dirname(__file__), 'udl', 'system_mode.py')
with open(FP, encoding='utf-8') as f:
    content = f.read()

# Strategy: find each block of misplaced methods (between end of class body
# and the separator comment), remove it, then re-insert inside the class.

# The misplaced blocks start with "    # ─── Conformal scoring methods"
# and end just before the separator comments.

# Let's identify and extract the three blocks.

# Pattern: content between "return scores\n\n\n" and the separator
# For MolecularEngine: between its "return scores" and "GRAVITY ENGINE" separator
# For GravityModeEngine: between its "return scores" and "HYBRID ENGINE" separator
# For HybridGravityEngine: between its "return blended" and "SPECTRA" separator

import textwrap


def extract_and_move_methods(content, class_end_marker, separator_marker):
    """Find conformal methods between class_end_marker and separator, 
    remove them, and insert before class_end_marker."""
    
    # Find the conformal block
    conf_start_marker = '    # ─── Conformal scoring methods'
    
    # Find the separator
    sep_idx = content.index(separator_marker)
    
    # Find the conformal block that's closest before this separator
    search_start = max(0, sep_idx - 15000)  # look within 15KB before separator
    chunk = content[search_start:sep_idx]
    
    conf_pos_in_chunk = chunk.rfind(conf_start_marker)
    if conf_pos_in_chunk == -1:
        return content, None
    
    conf_global_start = search_start + conf_pos_in_chunk
    conf_global_end = sep_idx
    
    # Extract the conformal block
    conf_block = content[conf_global_start:conf_global_end].rstrip()
    
    # Remove the block (and any trailing whitespace)
    content = content[:conf_global_start] + '\n\n' + content[conf_global_end:]
    
    return content, conf_block


# ── 1. MolecularEngine ──
content, mol_block = extract_and_move_methods(
    content,
    'return scores',
    '# ═══════════════════════════════════════════════════════════════════\n#  GRAVITY ENGINE'
)

# ── 2. GravityModeEngine ──
content, grav_block = extract_and_move_methods(
    content,
    'return scores',
    '# ═══════════════════════════════════════════════════════════════════\n#  HYBRID ENGINE'
)

# ── 3. HybridGravityEngine ──
content, hybrid_block = extract_and_move_methods(
    content,
    'return blended',
    '# ═══════════════════════════════════════════════════════════════════\n#  SPECTRA FALSE-ALARM FILTER'
)

print(f'Extracted blocks: Mol={mol_block is not None}, Grav={grav_block is not None}, Hybrid={hybrid_block is not None}')

# Now insert each block INSIDE the class, before the class-ending separator.
# For MolecularEngine: insert the block before the GRAVITY ENGINE separator, 
# but indented as a class method (already has correct indentation from original patch).

# Actually, the blocks already have correct 4-space indentation as they were
# generated with `self.` methods. We just need to insert them in the right place.

# MolecularEngine ends with "return scores" followed by blank lines,
# then the GRAVITY ENGINE separator. Insert the block after the last method 
# of MolecularEngine (after its final "return scores").

# Find the last "return scores" before each separator and insert after it.

def insert_before_separator(content, separator, block):
    """Insert the conformal block just before the separator comment,
    keeping it inside the class body."""
    if block is None:
        return content
    idx = content.index(separator)
    # Go back to find the newline before the separator
    # We want to insert between the last blank line and the separator
    return content[:idx] + block + '\n\n\n' + content[idx:]


if mol_block:
    content = insert_before_separator(
        content,
        '# ═══════════════════════════════════════════════════════════════════\n#  GRAVITY ENGINE',
        mol_block
    )

if grav_block:
    content = insert_before_separator(
        content, 
        '# ═══════════════════════════════════════════════════════════════════\n#  HYBRID ENGINE',
        grav_block
    )

if hybrid_block:
    content = insert_before_separator(
        content,
        '# ═══════════════════════════════════════════════════════════════════\n#  SPECTRA FALSE-ALARM FILTER',
        hybrid_block
    )

with open(FP, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'File: {len(content)} bytes')

# Verify no syntax error
import py_compile
try:
    py_compile.compile(FP, doraise=True)
    print('Syntax OK')
except py_compile.PyCompileError as e:
    print(f'Syntax ERROR: {e}')
