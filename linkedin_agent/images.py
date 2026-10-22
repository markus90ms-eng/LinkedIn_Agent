"""Bildmotive zu Posts: Claude setzt eine Illustration aus geprüften Bausteinen zusammen, der Hook steht darunter.

Die Umwandlung in PNG für LinkedIn übernimmt der Browser (siehe web.py), damit keine zusätzliche
Software nötig ist. Alles, was Claude liefert, wird bereinigt (keine Skripte, Links oder Fremdbilder).
"""
import random
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

from . import bausteine, drafts

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
SIZE = 1200
SCENE_HEIGHT = 760
MAX_SCENE_BYTES = 120_000

ALLOWED_TAGS = {
    "g", "defs", "rect", "circle", "ellipse", "line", "polyline", "polygon", "path", "clipPath", "mask",
    "linearGradient", "radialGradient", "stop", "filter", "feGaussianBlur", "feDropShadow", "feOffset",
    "feColorMatrix", "feBlend", "feMerge", "feMergeNode", "feFlood", "feComposite", "feTurbulence",
}

PALETTES = {
    "ozean":   {"bg1": "#0b1c33", "bg2": "#143a63", "accent": "#2ec4b6", "light": "#3ee0cf", "warm": "#ffc857", "deep": "#17406b"},
    "abend":   {"bg1": "#2a1038", "bg2": "#5a1f4d", "accent": "#ff6b8a", "light": "#ff9eb5", "warm": "#ffd166", "deep": "#4a1942"},
    "wald":    {"bg1": "#0c2a22", "bg2": "#14513f", "accent": "#7bd88f", "light": "#b6f2c2", "warm": "#f6c453", "deep": "#14513f"},
    "sonne":   {"bg1": "#3a1d0c", "bg2": "#7a3a12", "accent": "#ffa940", "light": "#ffd08a", "warm": "#fff0c2", "deep": "#8a4515"},
    "violett": {"bg1": "#171040", "bg2": "#3a2a8c", "accent": "#8f7bff", "light": "#b9acff", "warm": "#5ee6c8", "deep": "#2b2370"},
    "schiefer": {"bg1": "#1a2230", "bg2": "#34475f", "accent": "#4db8ff", "light": "#9bd8ff", "warm": "#ff7a7a", "deep": "#2a3a52"},
    "hell":    {"bg1": "#f4f7fb", "bg2": "#dfe8f4", "accent": "#f28c4a", "light": "#f6b98b", "warm": "#f2c14e", "deep": "#2b4a77",
                "text": "#14284a", "hell": True},
}

LAYOUTS = [
    "Der Mittelpunkt sitzt zentral (x 600), groß und scharf.",
    "Der Mittelpunkt sitzt rechts (x etwa 760), links davon ruhiger Raum mit weichem Lichtschein.",
    "Der Mittelpunkt sitzt links (x etwa 440), rechts davon kleinere Nebenelemente.",
    "Nahaufnahme: ein einziges großes Objekt füllt fast die ganze Fläche, dahinter weiche Lichtkreise.",
    "Zwei Seiten stehen sich gegenüber (links und rechts), in der Mitte der Fokus.",
]

SYSTEM = """Du gestaltest das Bild zu einem LinkedIn-Post: eine saubere, flache Vektor-Illustration im Stil moderner
Business- und Software-Illustrationen, dazu der Hook als Text. Die Leinwand der Illustration ist 1200 x 760 Einheiten
groß (x 0 bis 1200, y 0 bis 760). Hintergrund: @@MODE@@ Darunter steht später der Hook. Wichtiges liegt zwischen y 40 und y 600.

Gib genau diese Abschnitte aus, ohne Text davor oder danach:
<idee>Ein Satz: Was zeigt das Bild, und warum passt es zur Kernaussage des Posts?</idee>
<hook>Der Hook für das Bild</hook>
<alt>Ein Satz Bildbeschreibung für Screenreader</alt>
<scene>Die Szene aus Bausteinen</scene>

Vorgehen:
1. Bestimme die Kernaussage des Posts in einem Satz.
2. Wähle EINE Bildidee, die genau diese Aussage zeigt. Das Bild muss zum Inhalt des Posts passen. Nimm nichts nur zur Dekoration auf:
   kein Diagramm, wenn es nicht um Zahlen oder Wachstum geht; keine Lupe, wenn es nicht ums Finden oder Gefundenwerden geht; kein Code-Fenster ohne IT-Bezug.
3. Baue die Szene aus den Bausteinen. Weniger ist mehr: ein klarer Mittelpunkt, wenig Nebenelemente, nichts überlappt unsauber.

Passende Bildideen:
- Team, Mitarbeiter gewinnen, Arbeitgeber, Recruiting: <room/> (nur hell) mit sitzenden und stehenden Personen am Tisch, oder <card kind="jobad"/> als Mittelpunkt.
- Sichtbarkeit, gefunden werden, Google, Suche, Standort: <laden/> mit <lupe/> und <pin/>, ggf. wenige Personen.
- KI, Kommunikation, Kundenfragen, Dialog: <card kind="chat"/> und <card kind="dots"/>, Person am Laptop.
- Zahlen, Wachstum, Ergebnis: <card kind="chart"/>.
- Tipps, Vorgehen, Checkliste: <card kind="checklist"/>.
- IT, Technik, Digitalisierung: <card kind="code"/> mit Person am Laptop.
- Vertrauen, Menschen, Zielgruppe: drei bis fünf <person/> nebeneinander (pose hips, wave, crossed) auf einer Linie, dahinter <glow/>.

Bausteine (alle Werte optional, Farben als #rrggbb, Koordinaten in der Leinwand):
- <person x y scale skin hair style top pants pose glasses flip/> Stehende Figur, x/y = Mitte der Füße (y zwischen 560 und 650), scale 0.9 bis 1.1.
  style: short, long, bun, curly, side. pose: down, hips, crossed, tablet, wave. glasses: 1. flip: 1 spiegelt.
  skin: #f1c7a3, #f7d9bd, #c58a65, #8d5a3b oder #e0aa84. hair: #4a2f22, #1c1613, #d9a441, #a8643a, #d9742f. Kleidung aus der Palette und neutralen Tönen.
- <seated x table_y .../> Sitzende Person hinter einem Tisch (gleiche Werte wie person; table_y = Oberkante des Tischs, etwa 470). Reihenfolge: erst seated, dann laptop, dann table.
- <laptop x y w h color/> Rückseite eines Laptops, y = Tischkante (etwa 472 bei table_y 470).
- <table x y w/> Tisch, y = Oberkante (etwa 470), w = Breite.
- <card kind x y w .../> Karte mit Schatten. kind: checklist, chart, chat, dots, jobad, code. w 200 bis 420. Farben accent, light, warm, deep.
- <laden x y scale/> Ladengeschäft mit Markise (y = Boden, etwa 585). <lupe x y scale/> Lupe. <pin x y scale/> Standort-Pin (y = Spitze).
- <plant x y scale/> Pflanze. <sparkle x y size color/> Funkeln (sparsam, höchstens zwei). <glow x y rx ry color/> weicher Lichtschein, am besten als erstes Element.
- <room/> heller Büroraum mit Fenster, Lampen und Regal, Boden ab y 600. Nur auf hellem Hintergrund, immer als erstes Element.
Zusätzlich sind einfache Formen (rect, circle, path) mit Verläufen erlaubt, wenn nötig.

Regeln: höchstens 7 Personen, mindestens 120 Einheiten Abstand zwischen Figuren, nichts über den Rand hinaus. Keine Texte, Logos, Marken oder
erkennbaren realen Personen. Farben nur aus dieser Palette: Akzent @@ACCENT@@, hell @@LIGHT@@, Wärme @@WARM@@, Dunkel @@DEEP@@, dazu Weiß und neutrale Töne.
Bildaufteilung für diesen Post: @@LAYOUT@@

Beispiel (Post über Stellenanzeigen, helle Palette):
<idee>Eine einzelne, menschlich gestaltete Stellenanzeige steht im Mittelpunkt, weil der Post sagt, dass Bewerber ein erkennbares Umfeld suchen.</idee>
<hook>Qualifizierte Leute suchen selten nur einen Job.</hook>
<alt>Eine Stellenanzeige mit drei Gesichtern in einem hellen Büro.</alt>
<scene>
<room/>
<seated x="420" table_y="470" top="#f28c4a"/><laptop x="420" y="472"/>
<seated x="780" table_y="470" skin="#c58a65" hair="#1c1613" style="curly" top="#2b4a77"/><laptop x="780" y="472"/>
<table x="600" y="470" w="600"/>
<person x="1010" y="640" skin="#8d5a3b" hair="#0f0a08" style="bun" top="#f6b98b" pose="crossed"/>
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
    """Zufällige Farbwelt, nie dieselbe wie bei den letzten Bildern und beim bisherigen Bild dieses Posts."""
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
    if pal.get("hell"):
        mode = f"ein heller Verlauf von {pal['bg1']} nach {pal['bg2']}. Nutze <room/> oder helle Karten und kräftige Kleidungsfarben."
    else:
        mode = f"ein dunkler Verlauf von {pal['bg1']} nach {pal['bg2']}. Helle Karten und Figuren heben sich davon ab, <room/> ist hier nicht erlaubt."
    out = SYSTEM.replace("@@MODE@@", mode).replace("@@LAYOUT@@", layout)
    for key in ("accent", "light", "warm", "deep"):
        out = out.replace(f"@@{key.upper()}@@", pal[key])
    return out


def parse_response(raw):
    def tag(name):
        m = re.search(rf"<{name}>(.*?)</{name}>", raw, re.S)
        return m.group(1).strip() if m else ""
    hook, alt, idea, scene = tag("hook"), tag("alt"), tag("idee"), tag("scene")
    if not scene:
        raise RuntimeError("Claude hat keine Illustration geliefert, bitte noch einmal versuchen.")
    return hook, alt, idea, scene


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


def build_scene(raw_scene, palette):
    """Baustein-Tags zu SVG ausschreiben und das Ergebnis bereinigen."""
    try:
        expanded = bausteine.expand(raw_scene, light=bool(PALETTES[palette].get("hell")), pal=PALETTES[palette])
    except ET.ParseError as e:
        raise RuntimeError(f"Die Illustration war fehlerhaft ({e}), bitte neu erstellen.")
    return sanitize_scene(expanded)


def _wrap(hook, size):
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
    return lines


def _wrap_hook(hook, footer=True):
    """Wählt die größte Schrift, bei der der Hook in höchstens drei Zeilen passt, ohne einzelnes Wort in der
    letzten Zeile (grobe Breitenschätzung für Fettschrift)."""
    limit = 1062 if footer else 1110  # mit Namenszeile bleibt weniger Platz
    fits = [(size, _wrap(hook, size)) for size in (92, 84, 76, 68, 60, 54)]
    fits = [(size, lines) for size, lines in fits
            if len(lines) <= 3 and 880 + (len(lines) - 1) * int(size * 1.18) <= limit]
    for size, lines in fits:
        if len(lines) == 1 or len(lines[-1]) >= 8:
            return size, lines
    if fits:
        return fits[0]
    lines = _wrap(hook, 54)
    return 54, lines[:2] + [lines[2][:30] + "…"] if len(lines) > 2 else lines


def compose_svg(scene, hook, footer="", palette="ozean"):
    pal = PALETTES[palette]
    fade = _lerp(pal["bg1"], pal["bg2"], SCENE_HEIGHT / SIZE)
    text_color = pal.get("text", "#ffffff")
    size, lines = _wrap_hook(hook, bool(footer))
    y = 880
    text = ""
    for line in lines:
        text += f'<text x="100" y="{y}" font-size="{size}" font-weight="700" fill="{text_color}">{escape(line)}</text>'
        y += int(size * 1.18)
    foot = ""
    if footer:
        foot = (f'<line x1="100" y1="1092" x2="1100" y2="1092" stroke="{_lerp(pal["bg2"], text_color, 0.18)}" stroke-width="2"/>'
                f'<text x="100" y="1142" font-size="34" fill="{_lerp(pal["bg2"], text_color, 0.75)}">{escape(footer)}</text>')
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
    """Erzeugt das Bild zum Post als SVG-Datei. Liefert (Dateipfad, Alternativtext, Bildidee)."""
    plain = text.replace("**", "")
    path = Path(cfg["db_path"]).parent / "images" / f"{post_id}.svg"
    palette = pick_palette(path.parent, post_id)
    system = build_system(palette, random.choice(LAYOUTS))
    raw = drafts._call(cfg, client or drafts._client(), system, f"Post:\n{plain}", max_tokens=8000)
    hook, alt, idea, scene = parse_response(raw)
    svg = compose_svg(build_scene(scene, palette), hook or _first_line(text), cfg.get("image_footer", ""), palette)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")
    return str(path), (alt or hook)[:300], idea[:400]


PROMPT_STYLE = "fotorealistisch, natürliches Licht, ruhige Farben, hochwertige Werbefotografie, leichte Tiefenschärfe"

PROMPT_SYSTEM = """Du schreibst einen Bildwunsch (Prompt) für einen KI-Bildgenerator wie ChatGPT. Das Bild begleitet einen LinkedIn-Post.
Vorgehen: Bestimme die Kernaussage des Posts. Beschreibe EINE konkrete Szene, die genau diese Aussage zeigt, nichts nur zur Dekoration.
Gib ausschließlich den fertigen Bildwunsch aus, direkt zum Einfügen in ChatGPT, ohne Erklärung davor oder danach.

Der Bildwunsch:
- beginnt mit "Erstelle ein quadratisches Bild (1:1):"
- beschreibt Motiv, Umgebung, Bildaufbau, Licht, Stimmung und Farben konkret, auf Deutsch, in 60 bis 120 Wörtern
- Stil: @@STYLE@@
- endet mit dem Satz: "Kein Text, keine Buchstaben, keine Logos, keine Wasserzeichen im Bild."
- zeigt keine erkennbaren realen Personen, Marken oder Produkte; Menschen nur als natürliche Alltagsfiguren, wenn der Post sie braucht
- passt zu einem seriösen B2B-Auftritt (Unternehmen, Marketing, Recruiting), nicht kitschig, keine Stock-Klischees wie Handschlag oder Glühbirne
Der Autor des Posts ist Vertriebler und berät Mittelständler."""


def make_prompt(cfg, post_text, previous=None, instruction=None, client=None):
    """Bildwunsch für ChatGPT zum Post. Mit previous und instruction wird ein bestehender Wunsch angepasst."""
    system = PROMPT_SYSTEM.replace("@@STYLE@@", cfg.get("image_prompt_style") or PROMPT_STYLE)
    plain = post_text.replace("**", "")
    if previous and instruction:
        user = f"Post:\n{plain}\n\nBisheriger Bildwunsch:\n{previous}\n\nÄndere ihn so: {instruction}\nGib nur den neuen Bildwunsch aus."
    else:
        user = f"Post:\n{plain}"
    raw = drafts._call(cfg, client or drafts._client(), system, user, max_tokens=900)
    return raw.strip().strip("`").strip('"„“').strip()
