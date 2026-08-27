
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Impostazioni
size = (512, 512)
background_color = (15, 18, 37)  # #0f1225
gold = (212, 175, 55)
white = (255, 255, 255)

# Crea base
img = Image.new('RGBA', size, (0,0,0,0))
d = ImageDraw.Draw(img)

# Cerchio di base con gradiente (semplificato con bordo)
d.ellipse((20, 20, 492, 492), fill=(15, 18, 37), outline=(212, 175, 55), width=20)

# "E" stilizzata
# Cerchiamo un font di sistema (Arial o simile)
try:
    font = ImageFont.truetype("arial.ttf", 350)
except:
    font = ImageFont.load_default()

# Centratura testo "E"
text = "E"
bbox = d.textbbox((0, 0), text, font=font)
w = bbox[2] - bbox[0]
h = bbox[3] - bbox[1]
x = (size[0] - w) / 2
y = (size[1] - h) / 2 - 20 # Offset per centratura visiva

d.text((x, y), text, font=font, fill=gold)

# Aggiungi filtro per renderla professionale
img = img.filter(ImageFilter.SMOOTH_MORE)

# Salva come ICO con varie dimensioni
icon_sizes = [(32, 32), (64, 64), (128, 128), (256, 256)]
img.save("Ermes.ico", format="ICO", sizes=icon_sizes)
print("Nuova icona professionale creata: Ermes.ico")
