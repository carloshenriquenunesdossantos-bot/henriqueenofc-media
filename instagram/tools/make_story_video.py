#!/usr/bin/env python3
"""Monta um Story de VÍDEO 1080x1920 (série @henriqueenofc): recorta/enquadra o vídeo,
grava a camada de texto (mesmo estilo do make_story.py) e exporta H.264 + AAC.

Uso:
  python3 make_story_video.py ENTRADA.mp4 SAIDA.mp4 '{"label":"LINHA DE FRENTE","hook":"...","line":"...","body":"...","tag":"...","start":5,"duration":30,"focus":0.5,"y0":250,"mute":false}'

Chaves do spec (todas opcionais menos hook/line/body):
  start (s), duration (s, máx. 60 para Story), focus (0 esq./topo .. 1 dir./base — posição do recorte quando o vídeo não é 9:16),
  y0 (altura inicial do texto), label, tag, accent (RGB), mute (true remove o áudio), fade (s, fade do texto; padrão 0.4).
"""
import json
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "/usr/share/fonts/opentype/inter/"
F_BLACK = FONT_DIR + "InterDisplay-Black.otf"
F_XBOLD = FONT_DIR + "InterDisplay-ExtraBold.otf"
F_BOLD = FONT_DIR + "InterDisplay-Bold.otf"
F_MED = FONT_DIR + "Inter-Medium.otf"
W, H = 1080, 1920


def font(path, size):
    for cand in (path, F_BOLD):
        try:
            return ImageFont.truetype(cand, size)
        except OSError:
            continue
    return ImageFont.load_default()


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


def draw_block(draw, x, y, text, fnt, fill, max_w, spacing=1.08):
    lh = round(fnt.size * spacing)
    for ln in wrap(draw, text, fnt, max_w):
        draw.text((x + 3, y + 4), ln, font=fnt, fill=(0, 0, 0, 160))
        draw.text((x, y), ln, font=fnt, fill=fill)
        y += lh
    return y


def gradient(w, h, top_alpha, bottom_alpha):
    g = Image.new("L", (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        g.putpixel((0, y), round(top_alpha + (bottom_alpha - top_alpha) * t))
    return g.resize((w, h))


def overlay_png(spec, out_png):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dark.paste((8, 8, 10, 255), (0, 0, W, 900), gradient(W, 900, 190, 0))
    dark.paste((8, 8, 10, 255), (0, H - 700, W, H), gradient(W, 700, 0, 200))
    im = Image.alpha_composite(im, dark)
    d = ImageDraw.Draw(im)
    margin, max_w = 72, W - 144
    y = spec.get("y0", 250)
    accent = tuple(spec.get("accent", (255, 196, 0)))
    label = spec.get("label")
    if label:
        fl = font(F_BOLD, spec.get("label_size", 40))
        d.rectangle((margin, y + 8, margin + 14, y + fl.size + 4), fill=accent + (255,))
        d.text((margin + 34, y), label, font=fl, fill=accent + (255,))
        y += fl.size + 34
    y = draw_block(d, margin, y, spec["hook"], font(F_BLACK, spec.get("hook_size", 118)), (255, 255, 255, 255), max_w, 0.98)
    y += 18
    y = draw_block(d, margin, y, spec["line"], font(F_XBOLD, spec.get("line_size", 66)), (255, 255, 255, 255), max_w, 1.08)
    y += 30
    d.rectangle((margin, y, margin + 140, y + 10), fill=accent + (255,))
    y += 44
    draw_block(d, margin, y, spec["body"], font(F_MED, spec.get("body_size", 44)), (235, 235, 235, 255), max_w, 1.22)
    tag = spec.get("tag")
    if tag:
        f = font(F_BLACK, spec.get("tag_size", 64))
        tw = d.textlength(tag, font=f)
        ty = H - 330
        d.rectangle((margin - 4, ty - 4, margin + tw + 28, ty + f.size + 22), fill=accent + (255,))
        d.text((margin + 12, ty + 4), tag, font=f, fill=(12, 12, 12, 255))
    im.save(out_png)


def probe(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
        "stream=width,height,duration,r_frame_rate:stream_tags=rotate:side_data=rotation",
        "-of", "json", path])
    info = json.loads(out)["streams"][0]
    w, h = int(info["width"]), int(info["height"])
    rot = int(info.get("tags", {}).get("rotate", 0) or 0)
    for sd in info.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(abs(sd["rotation"]))
    if rot in (90, 270):
        w, h = h, w
    dur = float(info.get("duration") or subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]).decode().strip())
    return w, h, dur


def build(src, out, spec):
    w, h, dur = probe(src)
    start = float(spec.get("start", 0))
    duration = float(spec.get("duration", min(60, dur - start)))
    duration = max(3, min(duration, 60, dur - start))
    focus = float(spec.get("focus", 0.5))
    fade = float(spec.get("fade", 0.4))

    # escala para cobrir 1080x1920 e recorta com foco
    if w / h > W / H:  # mais largo que 9:16 → recorta nas laterais
        vf = f"scale=-2:{H},crop={W}:{H}:(iw-{W})*{focus}:0"
    else:              # mais alto/estreito → recorta em cima/baixo
        vf = f"scale={W}:-2,crop={W}:{H}:0:(ih-{H})*{focus}"
    vf += ",setsar=1,fps=30"

    with tempfile.TemporaryDirectory() as td:
        png = os.path.join(td, "overlay.png")
        overlay_png(spec, png)
        filt = (
            f"[0:v]{vf}[v];"
            f"[1:v]format=rgba,fade=t=in:st=0:d={fade}:alpha=1[o];"
            f"[v][o]overlay=0:0:format=auto[out]"
        )
        cmd = ["ffmpeg", "-y", "-ss", f"{start}", "-t", f"{duration}", "-i", src,
               "-loop", "1", "-framerate", "30", "-t", f"{duration}", "-i", png,
               "-filter_complex", filt, "-map", "[out]"]
        if spec.get("mute"):
            cmd += ["-an"]
        else:
            cmd += ["-map", "0:a?", "-c:a", "aac", "-b:a", "128k", "-ar", "44100"]
        # -t também na saída: garante o corte mesmo com a imagem em loop
        cmd += ["-t", f"{duration}", "-c:v", "libx264", "-profile:v", "high", "-level", "4.0",
                "-pix_fmt", "yuv420p", "-preset", spec.get("preset", "fast"), "-crf", "20",
                "-movflags", "+faststart", "-shortest", out]
        subprocess.check_call(cmd)
    print("ok", out, f"{duration:.1f}s", f"fonte {w}x{h} {dur:.1f}s")


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2], json.loads(sys.argv[3]))
