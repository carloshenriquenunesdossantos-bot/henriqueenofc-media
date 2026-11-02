#!/usr/bin/env python3
"""Monta um Story 1080x1920 a partir de uma foto + blocos de texto (série @henriqueenofc).

Uso: python3 make_story.py FOTO SAIDA.jpg '{"label":"4H56 — DIA 1","hook":"...","line":"...","body":"...","tag":"...","focus":0.55,"y0":250}'
Chaves do spec: label (etiqueta de série, opcional), hook (gancho, grande), line (frase-síntese), body (corpo curto),
tag (bordão na base, opcional), focus (0 topo..1 base, recorte vertical da foto), y0 (altura inicial do texto),
hook_size/line_size/body_size/tag_size/label_size (px), accent (RGB, padrão amarelo 255,196,0).
Fontes: Inter Display em /usr/share/fonts/opentype/inter/ (Debian/Ubuntu: apt-get install fonts-inter); há fallback automático.
"""
import sys, json
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

FONT_DIR = "/usr/share/fonts/opentype/inter/"
F_BLACK = FONT_DIR + "InterDisplay-Black.otf"
F_XBOLD = FONT_DIR + "InterDisplay-ExtraBold.otf"
F_BOLD = FONT_DIR + "InterDisplay-Bold.otf"
F_SEMI = FONT_DIR + "Inter-SemiBold.otf"
F_MED = FONT_DIR + "Inter-Medium.otf"

W, H = 1080, 1920


def _fallback_font():
    import glob
    for pat in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/**/*Bold*.ttf", "/usr/share/fonts/**/*.ttf", "/usr/share/fonts/**/*.otf"):
        hits = glob.glob(pat, recursive=True)
        if hits:
            return hits[0]
    return None


def font(path, size):
    """Inter Display (apt: fonts-inter) com fallback para qualquer fonte do sistema."""
    for cand in (path, F_BOLD, _fallback_font()):
        if not cand:
            continue
        try:
            return ImageFont.truetype(cand, size)
        except OSError:
            continue
    return ImageFont.load_default()


def fit_cover(im, w, h, focus=0.5):
    """Recorta a imagem para cobrir w x h, mantendo proporção. focus = posição vertical do recorte (0 topo, 1 base)."""
    r = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * r), round(im.height * r)), Image.LANCZOS)
    x = (im.width - w) // 2
    y = round((im.height - h) * focus)
    return im.crop((x, y, x + w, y + h))


def gradient(w, h, top_alpha, bottom_alpha):
    g = Image.new("L", (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        g.putpixel((0, y), round(top_alpha + (bottom_alpha - top_alpha) * t))
    return g.resize((w, h))


def wrap(draw, text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if draw.textlength(trial, font=fnt) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def draw_block(draw, x, y, text, fnt, fill, max_w, spacing=1.08, shadow=True):
    lines = wrap(draw, text, fnt, max_w)
    lh = round(fnt.size * spacing)
    for ln in lines:
        if shadow:
            draw.text((x + 3, y + 4), ln, font=fnt, fill=(0, 0, 0, 160))
        draw.text((x, y), ln, font=fnt, fill=fill)
        y += lh
    return y


def build(photo, out, spec):
    base = ImageOps.exif_transpose(Image.open(photo)).convert("RGB")
    im = fit_cover(base, W, H, spec.get("focus", 0.5)).convert("RGBA")

    # escurece topo e base para legibilidade
    top = gradient(W, 900, 190, 0)
    bot = gradient(W, 700, 0, 200)
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dark.paste((8, 8, 10, 255), (0, 0, W, 900), top)
    dark.paste((8, 8, 10, 255), (0, H - 700, W, H), bot)
    im = Image.alpha_composite(im, dark)

    d = ImageDraw.Draw(im)
    margin = 72
    max_w = W - 2 * margin

    y = spec.get("y0", 300)
    accent = tuple(spec.get("accent", (255, 196, 0)))

    # etiqueta de série (ex.: "4H56 — DIA 1")
    label = spec.get("label")
    if label:
        fl = font(F_BOLD, spec.get("label_size", 40))
        d.rectangle((margin, y + 8, margin + 14, y + fl.size + 4), fill=accent + (255,))
        d.text((margin + 34, y), label, font=fl, fill=accent + (255,))
        y += fl.size + 34

    # linha de abertura (gancho)
    y = draw_block(d, margin, y, spec["hook"], font(F_BLACK, spec.get("hook_size", 150)), (255, 255, 255, 255), max_w, 0.98)
    y += 18
    # frase-síntese
    y = draw_block(d, margin, y, spec["line"], font(F_XBOLD, spec.get("line_size", 74)), (255, 255, 255, 255), max_w, 1.08)
    y += 30
    # barra de destaque
    d.rectangle((margin, y, margin + 140, y + 10), fill=accent + (255,))
    y += 44
    # corpo
    y = draw_block(d, margin, y, spec["body"], font(F_MED, spec.get("body_size", 44)), (235, 235, 235, 255), max_w, 1.22)

    # bordão na base
    tag = spec.get("tag")
    if tag:
        f = font(F_BLACK, spec.get("tag_size", 64))
        tw = d.textlength(tag, font=f)
        ty = H - 330
        d.rectangle((margin - 4, ty - 4, margin + tw + 28, ty + f.size + 22), fill=accent + (255,))
        d.text((margin + 12, ty + 4), tag, font=f, fill=(12, 12, 12, 255))

    im.convert("RGB").save(out, quality=94)
    print("ok", out)


if __name__ == "__main__":
    photo, out, spec = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
    build(photo, out, spec)
