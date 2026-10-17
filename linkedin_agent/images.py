"""Bildmotive zu Posts: Claude zeichnet eine Illustration (SVG), der Hook steht als Text darunter.

Die Umwandlung in PNG für LinkedIn übernimmt der Browser (siehe web.py), damit keine zusätzliche
Software nötig ist. Das SVG von Claude wird vorher gründlich bereinigt (keine Skripte, keine Links).
"""
import random
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

from . import drafts

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
SIZE = 1200
SCENE_HEIGHT = 760
MAX_SCENE_BYTES = 80_000

ALLOWED_TAGS = {
    "g", "defs", "rect", "circle", "ellipse", "line", "polyline", "polygon", "path", "clipPath", "mask",
    "linearGradient", "radialGradient", "stop", "filter", "feGaussianBlur", "feDropShadow", "feOffset",
    "feColorMatrix", "feBlend", "feMerge", "feMergeNode", "feFlood", "feComposite", "feTurbulence",
}

EXAMPLE = """<defs>
<radialGradient id="s-glow" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#3ee0cf" stop-opacity="0.5"/><stop offset="1" stop-color="#2ec4b6" stop-opacity="0"/></radialGradient>
<linearGradient id="s-card" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#40608a"/><stop offset="1" stop-color="#25405f"/></linearGradient>
<linearGradient id="s-hero" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#e3edf8"/></linearGradient>
<linearGradient id="s-btn" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#27b3a6"/><stop offset="1" stop-color="#3ee0cf"/></linearGradient>
<filter id="s-blur"><feGaussianBlur stdDeviation="3"/></filter>
<filter id="s-shadow" x="-40%" y="-40%" width="180%" height="190%"><feDropShadow dx="0" dy="30" stdDeviation="28" flood-color="#000" flood-opacity="0.55"/></filter>
</defs>
<ellipse cx="600" cy="380" rx="520" ry="360" fill="url(#s-glow)"/>
<g filter="url(#s-blur)" opacity="0.9">
  <rect x="150" y="150" width="230" height="300" rx="22" fill="url(#s-card)"/>
  <rect x="820" y="130" width="230" height="300" rx="22" fill="url(#s-card)"/>
</g>
<g transform="translate(600,380) rotate(3)" filter="url(#s-shadow)"><rect x="-150" y="-200" width="300" height="400" rx="30" fill="url(#s-hero)"/></g>
<g transform="translate(600,380) rotate(3)">
  <circle cx="-100" cy="20" r="16" fill="url(#s-btn)"/><path d="M-108 20 l6 7 l11 -13" stroke="#fff" stroke-width="4.5" fill="none" stroke-linecap="round"/>
  <rect x="-68" y="13" width="160" height="14" rx="7" fill="#aebfd3"/>
  <rect x="-110" y="146" width="220" height="52" rx="26" fill="url(#s-btn)"/>
</g>"""

PALETTES = {
    "ozean":   {"bg1": "#0b1c33", "bg2": "#143a63", "accent": "#2ec4b6", "light": "#3ee0cf", "warm": "#ffc857", "deep": "#17406b"},
    "abend":   {"bg1": "#2a1038", "bg2": "#5a1f4d", "accent": "#ff6b8a", "light": "#ff9eb5", "warm": "#ffd166", "deep": "#4a1942"},
    "wald":    {"bg1": "#0c2a22", "bg2": "#14513f", "accent": "#7bd88f", "light": "#b6f2c2", "warm": "#f6c453", "deep": "#14513f"},
    "sonne":   {"bg1": "#3a1d0c", "bg2": "#7a3a12", "accent": "#ffa940", "light": "#ffd08a", "warm": "#fff0c2", "deep": "#8a4515"},
    "violett": {"bg1": "#171040", "bg2": "#3a2a8c", "accent": "#8f7bff", "light": "#b9acff", "warm": "#5ee6c8", "deep": "#2b2370"},
    "schiefer": {"bg1": "#1a2230", "bg2": "#34475f", "accent": "#4db8ff", "light": "#9bd8ff", "warm": "#ff7a7a", "deep": "#2a3a52"},
}

LAYOUTS = [
    "Der Mittelpunkt sitzt zentral (x 600), groß und scharf.",
    "Der Mittelpunkt sitzt rechts (x etwa 760), links davon ruhiger Raum mit weichem Lichtschein.",
    "Der Mittelpunkt sitzt links (x etwa 440), rechts davon kleinere Nebenelemente.",
    "Nahaufnahme: ein einziges großes Objekt füllt fast die ganze Fläche, dahinter weiche Lichtkreise.",
    "Weitwinkel: mehrere kleine Elemente in Perspektive (Reihen, Treppe oder Pfad), ein hervorgehobenes Element.",
    "Symmetrische Szene mit zwei Seiten, die sich gegenüberstehen, in der Mitte der Fokus.",
]

SYSTEM = """Du gestaltest das Bild zu einem LinkedIn-Post: eine hochwertige Vektor-Illustration plus den Hook als Text.
Die Leinwand für die Illustration ist 1200 x 760 Einheiten groß (x von 0 bis 1200, y von 0 bis 760). Der Hintergrund ist
bereits ein dunkler Farbverlauf von @@BG1@@ nach @@BG2@@. Darunter steht später der Hook-Text.

Gib genau diese drei Abschnitte aus, ohne Erklärung davor oder danach:
<hook>Der Hook für das Bild</hook>
<alt>Ein Satz Bildbeschreibung für Screenreader</alt>
<scene>SVG-Elemente der Illustration</scene>

Regeln für <hook>:
- Nimm die erste Zeile des Posts. Entferne Emojis und Sternchen. Länger als 90 Zeichen: sinngemäß kürzen, nichts Neues erfinden.

Regeln für <scene>:
- Nur SVG-Elemente (rect, circle, ellipse, path, polygon, line, g, defs, Verläufe, filter mit feGaussianBlur und feDropShadow). Keine Wurzel <svg>, kein <text>, kein <image>, kein <script>, keine Links.
- Alle id-Namen beginnen mit "s-". Zeichne nur innerhalb von 1200 x 760.
- Eine klare Bildidee, die die Kernaussage des Posts als Metapher zeigt, mit EINEM auffälligen Mittelpunkt (scharf, hell) vor weichem, unscharfem Hintergrund. Tiefe durch Verläufe, weiche Schatten, Lichtschein.
- Farben (nur diese Palette, passend zum Hintergrund): Akzent @@ACCENT@@ und hell @@LIGHT@@, Wärmeton @@WARM@@, Dunkelton @@DEEP@@, dazu Weiß und helle Töne davon.
- Bildaufteilung für diesen Post: @@LAYOUT@@
- Wähle ein eigenes Motiv passend zum Post. Kopiere NICHT das Beispiel (Karten), es zeigt nur Stil und Technik. Menschen nur als freundliche, einfache Avatare (runde Köpfe, wenige Formen).
- Keine Texte, Logos, Marken oder erkennbaren realen Personen. Der Mittelpunkt liegt etwa bei x 600, y 380. Unten (ab y 640) bleibt es ruhig.
- Bleibe unter etwa 6000 Zeichen SVG.

Beispiel für Stil und Technik (Farben und Motiv NICHT übernehmen):
<scene>
""" + EXAMPLE + """
</scene>"""


def _lerp(c1, c2, t):
    a, b = [tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in (c1, c2)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _used_palette(path):
    try:
        m = re.search(r'data-palette="(\w+)"', Path(path).read_text(encoding="utf-8")[:600])
    except OSError:
        return None
    return m.group(1) if m else None


def pick_palette(images_dir, post_id):
    """Zufällige Farbwelt, nie dieselbe wie beim letzten Bild und beim bisherigen Bild dieses Posts."""
    images_dir = Path(images_dir)
    skip = set()
    if images_dir.exists():
        others = sorted((f for f in images_dir.glob("*.svg") if f.stem != str(post_id)),
                        key=lambda f: f.stat().st_mtime, reverse=True)
        skip |= {_used_palette(f) for f in others[:2]}
    skip.add(_used_palette(images_dir / f"{post_id}.svg"))
    choices = [n for n in PALETTES if n not in skip] or list(PALETTES)
    return random.choice(choices)


def build_system(palette_name, layout):
    pal = PALETTES[palette_name]
    out = SYSTEM.replace("@@LAYOUT@@", layout)
    for key, val in pal.items():
        out = out.replace(f"@@{key.upper()}@@", val)
    return out


def parse_response(raw):
    def tag(name):
        m = re.search(rf"<{name}>(.*?)</{name}>", raw, re.S)
        return m.group(1).strip() if m else ""
    hook, alt, scene = tag("hook"), tag("alt"), tag("scene")
    if not scene:
        raise RuntimeError("Claude hat keine Illustration geliefert, bitte noch einmal versuchen.")
    return hook, alt, scene


def sanitize_scene(scene):
    """Lässt nur harmlose SVG-Zeichenelemente durch (keine Skripte, Links, Bilder, Fremdinhalte)."""
    if len(scene.encode("utf-8")) > MAX_SCENE_BYTES:
        raise RuntimeError("Die Illustration ist zu groß, bitte neu erstellen.")
    try:
        root = ET.fromstring(f'<g xmlns="{SVG_NS}">{scene}</g>')
    except ET.ParseError as e:
        raise RuntimeError(f"Die Illustration war fehlerhaft ({e}), bitte neu erstellen.")

    def clean(el):
        for child in list(el):
            local = child.tag.split("}")[-1]
            if child.tag.startswith("{") and not child.tag.startswith("{" + SVG_NS + "}") or local not in ALLOWED_TAGS:
                el.remove(child)
                continue
            for name in list(child.attrib):
                lname = name.split("}")[-1].lower()
                value = child.attrib[name]
                if name.startswith("{") or lname.startswith("on") or lname == "href" \
                        or re.search(r"url\(\s*['\"]?\s*(?!#)", value, re.I) or "javascript:" in value.lower():
                    del child.attrib[name]
            clean(child)

    clean(root)
    return "".join(ET.tostring(c, encoding="unicode") for c in root)


def _wrap_hook(hook):
    """Wählt Schriftgröße und Zeilenumbrüche für den Hook (grobe Breitenschätzung für Fettschrift)."""
    for size in (92, 84, 76, 68, 60, 54):
        per_line = int(1000 / (0.58 * size))
        lines, line = [], ""
        for word in hook.split():
            trial = f"{line} {word}".strip()
            if len(trial) <= per_line or not line:
                line = trial
            else:
                lines.append(line)
                line = word
        if line:
            lines.append(line)
        if len(lines) <= (2 if size > 76 else 3):  # drei Zeilen nur in kleinerer Schrift, sonst stößt der Text an den Namen
            return size, lines
    return 54, lines[:2] + [lines[2][:per_line - 1] + "…"]


def compose_svg(scene, hook, footer="", palette="ozean"):
    pal = PALETTES[palette]
    fade = _lerp(pal["bg1"], pal["bg2"], SCENE_HEIGHT / SIZE)
    size, lines = _wrap_hook(hook)
    y = 880
    text = ""
    for line in lines:
        text += f'<text x="100" y="{y}" font-size="{size}" font-weight="700" fill="#ffffff">{escape(line)}</text>'
        y += int(size * 1.18)
    foot = ""
    if footer:
        foot = (f'<line x1="100" y1="1092" x2="1100" y2="1092" stroke="{_lerp(pal["bg2"], "#ffffff", 0.18)}" stroke-width="2"/>'
                f'<text x="100" y="1142" font-size="34" fill="#c9d6e8">{escape(footer)}</text>')
    return (
        f'<svg xmlns="{SVG_NS}" data-palette="{palette}" width="{SIZE}" height="{SIZE}" viewBox="0 0 {SIZE} {SIZE}" '
        f"font-family=\"'Segoe UI', Arial, 'Liberation Sans', 'DejaVu Sans', sans-serif\">"
        f'<defs><linearGradient id="ui-bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{pal["bg1"]}"/>'
        f'<stop offset="1" stop-color="{pal["bg2"]}"/></linearGradient>'
        f'<linearGradient id="ui-fade" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{fade}" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="{fade}" stop-opacity="1"/></linearGradient>'
        f'<clipPath id="ui-clip"><rect width="{SIZE}" height="{SCENE_HEIGHT}"/></clipPath></defs>'
        f'<rect width="{SIZE}" height="{SIZE}" fill="url(#ui-bg)"/>'
        f'<g clip-path="url(#ui-clip)">{scene}</g>'
        f'<rect y="{SCENE_HEIGHT - 150}" width="{SIZE}" height="150" fill="url(#ui-fade)"/>'
        f'<rect x="100" y="790" width="110" height="10" fill="{pal["accent"]}"/>'
        f'{text}{foot}</svg>'
    )


def _first_line(text):
    first = text.replace("**", "").strip().splitlines()[0] if text.strip() else ""
    return re.sub(r"[^\w\s,.:;!?„“\"'’()/&%€+\-–—äöüÄÖÜß]", "", first).strip()


def make_scene(cfg, text, post_id, client=None):
    """Erzeugt das Bild zum Post als SVG-Datei. Liefert (Dateipfad, Alternativtext)."""
    plain = text.replace("**", "")
    path = Path(cfg["db_path"]).parent / "images" / f"{post_id}.svg"
    palette = pick_palette(path.parent, post_id)
    system = build_system(palette, random.choice(LAYOUTS))
    raw = drafts._call(cfg, client or drafts._client(), system, f"Post:\n{plain}", max_tokens=8000)
    hook, alt, scene = parse_response(raw)
    svg = compose_svg(sanitize_scene(scene), hook or _first_line(text), cfg.get("image_footer", ""), palette)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")
    return str(path), (alt or hook)[:300]
