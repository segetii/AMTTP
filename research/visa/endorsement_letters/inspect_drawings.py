import fitz
doc = fitz.open('Segun odeyemi_corrected.pdf')
for i, page in enumerate(doc):
    annots = list(page.annots())
    drawings = page.get_drawings()
    print(f'Page {i+1}: annots={len(annots)}, drawings={len(drawings)}')
    for d in drawings:
        dtype  = d.get('type')
        drect  = d.get('rect')
        dcolor = d.get('color')
        dfill  = d.get('fill')
        dwidth = d.get('width')
        print(f'  drawing type={dtype} rect={drect} color={dcolor} fill={dfill} width={dwidth}')
doc.close()
