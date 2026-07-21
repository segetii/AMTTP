"""Count explicit page breaks in DOCX XML to verify page structure."""
import glob, os, zipfile
from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

def count_page_sections(docx_path):
    with zipfile.ZipFile(docx_path) as z:
        xml = z.read('word/document.xml')
    tree = etree.fromstring(xml)
    breaks = tree.findall('.//{%s}br[@{%s}type="page"]' % (W, W))
    # Use namespaced attribute correctly
    ns_type = '{%s}type' % W
    page_breaks = [b for b in tree.findall('.//{%s}br' % W) if b.get(ns_type) == 'page']
    return 1 + len(page_breaks)

folder = r'C:\amttp\research\visa\EVIDENCE_DOCX_COPIES'
files = sorted(glob.glob(folder + r'\MC-*.docx') + glob.glob(folder + r'\OC*.docx'))
print(f"{'File':<45} {'Explicit sections':>18}")
print('-' * 65)
for f in files:
    sections = count_page_sections(f)
    name = os.path.basename(f)
    print(f"{name:<45} {sections:>18}")
