import math

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SIZE = 512
CENTER = SIZE // 2
DARK = (10, 12, 28)
BLUE = (15, 18, 37)
GOLD = (212, 175, 55)
GOLD2 = (240, 210, 100)

def radial_gradient(draw, size, cx, cy):
    for x in range(size):
        for y in range(size):
            d = math.hypot(x - cx, y - cy) / (size * 0.7)
            t = min(d, 1.0)
            r = int(DARK[0] + (BLUE[0] - DARK[0]) * (1 - t))
            g = int(DARK[1] + (BLUE[1] - DARK[1]) * (1 - t))
            b = int(DARK[2] + (BLUE[2] - DARK[2]) * (1 - t))
            draw.point((x, y), fill=(r, g, b))

# Background circle with gradient
bg = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
dr = ImageDraw.Draw(bg)
radial_gradient(dr, SIZE, CENTER, CENTER)

# Circle clip
msk = Image.new('L', (SIZE, SIZE), 0)
ImageDraw.Draw(msk).ellipse((10, 10, SIZE - 10, SIZE - 10), fill=255)
bg.putalpha(msk)

# Outer gold ring
dr2 = ImageDraw.Draw(bg)
dr2.ellipse((10, 10, SIZE - 10, SIZE - 10), outline=GOLD, width=4)
dr2.ellipse((36, 36, SIZE - 36, SIZE - 36), outline=GOLD, width=1)

# Cardinal dots
for deg in [45, 135, 225, 315]:
    r = deg * math.pi / 180
    d = 224
    px = CENTER + int(d * math.cos(r))
    py = CENTER + int(d * math.sin(r))
    dr2.ellipse((px - 4, py - 4, px + 4, py + 4), fill=GOLD)

# Render "E" text with system font, precisely center via pixel analysis
font_size = 340
font = None
for name in ["arial.ttf", "segoeui.ttf", "tahoma.ttf", "C:\\Windows\\Fonts\\arial.ttf"]:
    try:
        font = ImageFont.truetype(name, font_size)
        break
    except:
        continue

if font is None:
    font = ImageFont.load_default()

# Get text mask to calculate exact center of mass
txt = Image.new('L', (SIZE, SIZE), 0)
tdr = ImageDraw.Draw(txt)
bbox = tdr.textbbox((0, 0), "E", font=font)
tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
# Initial placement
tx = (SIZE - tw) // 2 - bbox[0]
ty = (SIZE - th) // 2 - bbox[1]
tdr.text((tx, ty), "E", font=font, fill=255)

# Find actual pixel bounds
pxs = txt.load()
xmin, xmax, ymin, ymax = SIZE, 0, SIZE, 0
for x in range(SIZE):
    for y in range(SIZE):
        if pxs[x, y] > 0:
            xmin = min(xmin, x)
            xmax = max(xmax, x)
            ymin = min(ymin, y)
            ymax = max(ymax, y)

# Center of mass adjustment
cx_txt = (xmin + xmax) // 2
cy_txt = (ymin + ymax) // 2
adjust_x = CENTER - cx_txt
adjust_y = CENTER - cy_txt - 6  # -6 visual nudge
tx += adjust_x
ty += adjust_y

# Gold "E" with shadow
E_layer = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
edr = ImageDraw.Draw(E_layer)
edr.text((tx + 3, ty + 3), "E", font=font, fill=(0, 0, 0, 60))
edr.text((tx, ty), "E", font=font, fill=GOLD2)
# Thicker gold stroke by rendering slightly offset
for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
    edr.text((tx + ox, ty + oy), "E", font=font, fill=GOLD)
edr.text((tx, ty), "E", font=font, fill=GOLD2)

img = Image.alpha_composite(bg, E_layer)

# Gloss top half
gl = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
gdr = ImageDraw.Draw(gl)
for y in range(SIZE // 2):
    a = int(15 * (1 - y / (SIZE // 2)))
    gdr.line([(0, y), (SIZE, y)], fill=(255, 255, 255, a))
gl.putalpha(msk)
img = Image.alpha_composite(img, gl)

img = img.filter(ImageFilter.SMOOTH_MORE)

img.save("Ermes.png", format="PNG")
sizes = [(32, 32), (48, 48), (64, 64), (96, 96), (128, 128), (256, 256)]
img.save("Ermes.ico", format="ICO", sizes=sizes)
print(f"OK: Ermes.ico ({len(sizes)} sizes) + Ermes.png")
