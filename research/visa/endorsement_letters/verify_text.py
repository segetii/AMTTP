import fitz
doc = fitz.open(r"C:\amttp\research\visa\endorsement_letters\Segun odeyemi_corrected.pdf")
txt = "".join(p.get_text() for p in doc)
checks = [
    ("proof-of-concept", 0),
    ("early deployment stage", 2),
    ("0.9999998", 1),
    ("0.9879", 0),
]
for term, expected in checks:
    count = txt.count(term)
    status = "OK" if count == expected else "FAIL"
    print(f'  "{term}": {count}x (expected {expected}) — {status}')
doc.close()
