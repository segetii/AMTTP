"""Process Segun's signature: remove blue paper background, keep only ink."""
from PIL import Image, ImageFilter
import numpy as np
from scipy import ndimage
import sys

src = r'C:\Users\Administrator\Downloads\WhatsApp Image 2026-05-14 at 11.38.33 (1).jpeg'
out = r'C:\Users\Administrator\Documents\segun_sig.png'

img = Image.open(src).convert('RGB')
w, h = img.size
print(f'Original size: {w}x{h}')

# Crop to top 62% (remove bottom fold/shadow) and 88% width (remove top-right smudge)
crop_right = int(w * 0.88)
crop_bottom = int(h * 0.62)
img = img.crop((0, 0, crop_right, crop_bottom))
print(f'After crop: {img.size}')

# Blur slightly to reduce JPEG compression artifacts
img = img.filter(ImageFilter.GaussianBlur(radius=0.8))

arr = np.array(img, dtype=np.float32)

# Luminance
lum = 0.299*arr[:,:,0] + 0.587*arr[:,:,1] + 0.114*arr[:,:,2]

# Very tight threshold — only the darkest ink (< 80 out of 255)
mask = lum < 80

# Fill small holes in ink strokes using dilation/closing
mask = ndimage.binary_closing(mask, structure=np.ones((3,3)), iterations=1)

# Remove isolated noise blobs (keep only large connected components)
labeled, num_features = ndimage.label(mask)
print(f'Connected components: {num_features}')

component_sizes = ndimage.sum(mask, labeled, range(1, num_features+1))
# Keep components > 200 pixels — the signature strokes are all much bigger
large_components = np.where(np.array(component_sizes) > 200)[0] + 1
clean_mask = np.isin(labeled, large_components)
print(f'Kept {len(large_components)} components')

# Build RGBA: ink=black opaque, background=transparent
rgba = np.zeros((arr.shape[0], arr.shape[1], 4), dtype=np.uint8)
rgba[clean_mask] = [0, 0, 0, 255]
rgba[~clean_mask] = [255, 255, 255, 0]

result = Image.fromarray(rgba, 'RGBA')

# Tight crop with padding
bbox = result.getbbox()
print(f'Ink bounding box: {bbox}')
if bbox:
    pad = 12
    left = max(0, bbox[0]-pad)
    upper = max(0, bbox[1]-pad)
    right = min(result.width, bbox[2]+pad)
    lower = min(result.height, bbox[3]+pad)
    result = result.crop((left, upper, right, lower))

result.save(out)
print(f'Saved: {out}  final size={result.size}')
