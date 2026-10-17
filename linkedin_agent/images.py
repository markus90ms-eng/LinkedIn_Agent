"""Textkarten für Posts: Claude liefert Kernaussage und Stichpunkte, Pillow zeichnet das Bild."""
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import drafts

SIZE = 1200
MARGIN = 100
BG, ACCENT, TEXT, SOFT = "#0f2742", "#2ec4b6", "#ffffff", "#c9d6e8"
BOLD_FONTS = ["segoeuib.ttf", "arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"]
REGULAR_FONTS = ["segoeui.ttf", "arial.ttf", "Arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"]

SYSTEM = """Du machst aus einem LinkedIn-Post den Text für eine einfache Bildkarte.
Gib ausschließlich JSON aus, ohne Erklärung und ohne Codeblock, in diesem Format:
{"kicker": "...", "headline": "...", "points": ["...", "..."]}

Regeln:
- headline: die Kernaussage des Posts, höchstens 70 Zeichen, als Satz, ohne Hashtags und Emojis.
- kicker: ein kurzes Themenlabel, höchstens 28 Zeichen, zum Beispiel "Recruiting" oder "Sichtbarkeit".
- points: null bis drei kurze Stichpunkte, jeweils höchstens 48 Zeichen, aus dem Tipp des Posts.
- Übernimm nur, was im Post steht. Erfinde keine Zahlen, Zitate oder Fakten.
- Sprache und Ansprache (Sie-Form) wie im Post."""


def _font(names, size):
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _wrap(draw, text, font, width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def parse_spec(raw):
    """Holt das JSON aus der Claude-Antwort und bereinigt es."""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise RuntimeError("Claude hat keine Bildkarte geliefert.")
    spec = json.loads(m.group(0))
    headline = str(spec.get("headline", "")).strip()
    if not headline:
        raise RuntimeError("Die Bildkarte hat keine Kernaussage.")
    return {
        "kicker": str(spec.get("kicker", "")).strip()[:40],
        "headline": headline[:110],
        "points": [str(p).strip()[:70] for p in spec.get("points", [])[:3] if str(p).strip()],
    }


def draw_card(spec, footer, path):
    img = Image.new("RGB", (SIZE, SIZE), BG)
    d = ImageDraw.Draw(img)
    width = SIZE - 2 * MARGIN
    y = MARGIN
    if spec["kicker"]:
        d.text((MARGIN, y), spec["kicker"].upper(), font=_font(BOLD_FONTS, 34), fill=ACCENT)
        y += 70
    d.rectangle([MARGIN, y, MARGIN + 110, y + 10], fill=ACCENT)
    y += 50

    for size in range(112, 47, -4):  # größte Schrift, bei der die Kernaussage noch passt
        head_font = _font(BOLD_FONTS, size)
        lines = _wrap(d, spec["headline"], head_font, width)
        if len(lines) <= 6 and len(lines) * size * 1.2 <= 520:
            break
    for line in lines:
        d.text((MARGIN, y), line, font=head_font, fill=TEXT)
        y += int(size * 1.2)
    y += 50

    point_font = _font(REGULAR_FONTS, 44)
    for point in spec["points"]:
        wrapped = _wrap(d, point, point_font, width - 60)
        d.ellipse([MARGIN, y + 15, MARGIN + 18, y + 33], fill=ACCENT)
        for line in wrapped:
            d.text((MARGIN + 50, y), line, font=point_font, fill=SOFT)
            y += 58
        y += 22

    if footer:
        d.line([MARGIN, SIZE - 150, SIZE - MARGIN, SIZE - 150], fill="#2c4a6e", width=2)
        d.text((MARGIN, SIZE - 120), footer, font=_font(REGULAR_FONTS, 38), fill=SOFT)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")


def make_card(cfg, text, post_id, client=None):
    """Erzeugt die Bildkarte zum Post. Liefert (Dateipfad, Alternativtext)."""
    plain = text.replace("**", "")
    raw = drafts._call(cfg, client or drafts._client(), SYSTEM, f"Post:\n{plain}", max_tokens=800)
    spec = parse_spec(raw)
    path = Path(cfg["db_path"]).parent / "images" / f"{post_id}.png"
    draw_card(spec, cfg.get("image_footer", ""), path)
    alt = spec["headline"] + (" " + " ".join(spec["points"]) if spec["points"] else "")
    return str(path), alt
