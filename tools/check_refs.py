"""Final consistency check for cross-references in the .md paper."""
import re
from collections import Counter

path = 'papers/blind_spot_decomposition_theory.md'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

# All Section X.Y references
refs = re.findall(r'Section\s+(\d+(?:\.\d+)?)', text)
print('All Section X.Y references:')
for ref, cnt in sorted(Counter(refs).items(), key=lambda x: [int(p) for p in x[0].split('.')]):
    print(f'  Section {ref}: {cnt}x')

# Defined section headers
headers = set()
for m in re.finditer(r'^#{2,3}\s+(\d+(?:\.\d+)?)\.\s', text, re.MULTILINE):
    headers.add(m.group(1))

sorted_headers = sorted(headers, key=lambda x: [int(p) for p in x.split('.')])
print(f'\nDefined sections: {sorted_headers}')

# Check for dangling refs
for ref in sorted(set(refs), key=lambda x: [int(p) for p in x.split('.')]):
    if ref not in headers:
        # Could be a subsection reference like 6.12 or appendix
        print(f'  WARNING: Section {ref} referenced but not in headers')

print(f'\nTotal lines: {len(text.splitlines())}')
