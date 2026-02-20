from docx import Document
import re
doc = Document(r'C:\Users\Administrator\Downloads\OLusegunAMTTP.docx')

patterns = [
    (r'multi.?agents?\s+are\s+being', 'multi-agents grammar'),
    (r"Its\s+responsible", "Its vs It's"),
    (r'[Dd]ata speaks', 'colloquial'),
    (r'tax of determinism', 'colloquial'),
    (r'[Cc]andour about shortcomings matters', 'informal'),
    (r'highest priority.*right away', 'informal'),
    (r'Ruby and XGBoost', 'Ruby error'),
    (r'AQ1', 'AQ1 unclear'),
    (r'recalcitration', 'misspelling'),
    (r'fans? out', 'colloquial'),
    (r"baked\s+in", 'colloquial'),
    (r'succeeded to produce', 'grammar'),
    (r'no single person', 'informal'),
    (r'so-called', 'hedging'),
    (r'needs? to be done right away', 'informal'),
    (r'artefacts are available', 'subject-verb'),
    (r'Eighteen|Eigh teen|18 smart|18 Solidity|18 Ethereum', 'contract count'),
    (r'17 services', 'service count'),
    (r'8889', 'wrong Flutter port'),
    (r'Prometheus|Grafana', 'phantom service'),
]

for i, p in enumerate(doc.paragraphs):
    text = p.text
    if not text.strip():
        continue
    for pat, label in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            start = max(0, m.start() - 25)
            end = min(len(text), m.end() + 25)
            print(f'  Para {i} [{label}]: "...{text[start:end]}..."')
