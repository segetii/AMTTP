"""
Render corrected PDF pages 1 and 2 to PNG to visually verify there are
no border lines around the corrected areas.
"""
import fitz

doc = fitz.open(r"C:\amttp\research\visa\endorsement_letters\Segun odeyemi_corrected.pdf")
mat = fitz.Matrix(2.0, 2.0)  # 2x zoom = 144 dpi

for pno in [0, 1]:
    pix = doc[pno].get_pixmap(matrix=mat, alpha=False)
    out = rf"C:\amttp\research\visa\endorsement_letters\check_page{pno+1}.png"
    pix.save(out)
    print(f"Saved: {out}")

doc.close()
