import fitz
doc = fitz.open('Segun odeyemi.pdf')
p = doc[0]

terms = ['0.9879', 'proof-of-concept stage, developed']
for term in terms:
    hits = p.search_for(term)
    if not hits:
        print('NOT FOUND:', term)
        continue
    hr = hits[0]
    print(f'--- [{term}] hit rect: x0={hr.x0:.2f} y0={hr.y0:.2f} x1={hr.x1:.2f} y1={hr.y1:.2f} ---')
    # full line
    line_rect = fitz.Rect(50, hr.y0 - 1, 562, hr.y1 + 1)
    raw = p.get_text('rawdict', clip=line_rect)
    for b in raw['blocks']:
        for l in b.get('lines', []):
            for s in l.get('spans', []):
                chars = s.get('chars', [])
                t = ''.join(c.get('c','') for c in chars) if chars else ''
                ox, oy = s['origin']
                sz = s['size']
                x0s = s.get('bbox', [0,0,0,0])
                print(f'  span text={repr(t)}  origin=({ox:.2f},{oy:.2f})  size={sz:.2f}  bbox={[round(v,2) for v in s.get("bbox",[])]}')
    print()

# Also page 2
p2 = doc[1]
hits2 = p2.search_for('proof-of-concept stage, its')
if hits2:
    hr2 = hits2[0]
    print(f'--- [page2 proof-of-concept] hit rect: x0={hr2.x0:.2f} y0={hr2.y0:.2f} x1={hr2.x1:.2f} y1={hr2.y1:.2f} ---')
    line_rect2 = fitz.Rect(50, hr2.y0 - 1, 562, hr2.y1 + 1)
    raw2 = p2.get_text('rawdict', clip=line_rect2)
    for b in raw2['blocks']:
        for l in b.get('lines', []):
            for s in l.get('spans', []):
                chars = s.get('chars', [])
                t = ''.join(c.get('c','') for c in chars) if chars else ''
                ox, oy = s['origin']
                sz = s['size']
                print(f'  span text={repr(t)}  origin=({ox:.2f},{oy:.2f})  size={sz:.2f}  bbox={[round(v,2) for v in s.get("bbox",[])]}')

doc.close()
