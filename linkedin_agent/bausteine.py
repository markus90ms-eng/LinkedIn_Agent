"""Geprüfte Bausteine für die Bildmotive (flache Vektorgrafik).

Claude setzt diese Bausteine als einfache Tags zusammen, zum Beispiel
<person x="300" y="600" skin="#f1c7a3" top="#2ec4b6" pose="crossed"/>.
Alle Werte werden hier geprüft und begrenzt, so bleiben Proportionen und Farben sauber,
egal was Claude schreibt.
"""
import math
import re
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
MAX_MACROS = 60
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _num(v, lo, hi, default):
    try:
        return min(hi, max(lo, float(v)))
    except (TypeError, ValueError):
        return default


def _col(v, default):
    return v if isinstance(v, str) and HEX.match(v) else default


def _enum(v, options, default):
    return v if v in options else default


def _mix(c1, c2, t):
    a, b = [tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in (c1, c2)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _flag(v):
    return str(v).lower() in ("1", "true", "ja")


def _limb(pts, w, color):
    d = "M" + " L".join(f"{x:g} {y:g}" for x, y in pts)
    return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/>'


def _hair(style, c):
    back = front = ""
    if style == "short":
        front = f'<path d="M-30 -318 C-34 -358 34 -358 30 -318 C24 -338 -22 -341 -30 -318Z" fill="{c}"/>'
    elif style == "long":
        back = f'<path d="M-33 -322 C-42 -366 42 -366 33 -322 L40 -255 Q0 -240 -40 -255Z" fill="{c}"/>'
        front = f'<path d="M-30 -322 C-24 -352 22 -354 30 -322 C16 -338 -12 -334 -30 -322Z" fill="{c}"/>'
    elif style == "bun":
        back = f'<circle cx="0" cy="-358" r="14" fill="{c}"/>'
        front = f'<path d="M-30 -318 C-34 -358 34 -358 30 -318 C24 -338 -22 -341 -30 -318Z" fill="{c}"/>'
    elif style == "curly":
        front = "".join(f'<circle cx="{dx}" cy="{-336 + abs(dx) * 0.35:.1f}" r="14" fill="{c}"/>' for dx in (-24, -12, 0, 12, 24))
    else:  # side
        front = f'<path d="M-30 -316 C-34 -360 36 -360 31 -322 C26 -342 -6 -332 -30 -316Z" fill="{c}"/>'
    return back, front


def _arm(side, kind, top, skin):
    m = -1 if side == "L" else 1
    P = lambda px, py: (m * px, py)
    if kind == "hips":
        return _limb([P(44, -262), P(76, -222)], 19, top) + _limb([P(76, -222), P(46, -178)], 15, skin) + f'<circle cx="{m * 44}" cy="-174" r="10" fill="{skin}"/>'
    if kind == "crossed":
        ey = -236 if side == "L" else -214
        return _limb([P(44, -262), P(38, -224)], 19, top) + _limb([P(38, -224), (-m * 28, ey)], 15, skin) + f'<circle cx="{-m * 28}" cy="{ey}" r="10" fill="{skin}"/>'
    if kind == "tablet" and side == "R":
        return (_limb([P(44, -262), P(62, -220)], 19, top) + _limb([P(62, -220), P(30, -206)], 15, skin)
                + '<g transform="rotate(-10 20 -230)"><rect x="-2" y="-262" width="44" height="64" rx="6" fill="#26364f"/>'
                '<rect x="2" y="-258" width="36" height="54" rx="3" fill="#bcd7f2"/></g>' + f'<circle cx="30" cy="-206" r="10" fill="{skin}"/>')
    if kind == "wave" and side == "R":
        return _limb([P(44, -262), P(68, -292)], 19, top) + _limb([P(68, -292), P(76, -338)], 15, skin) + f'<circle cx="77" cy="-346" r="11" fill="{skin}"/>'
    return _limb([P(44, -262), P(52, -214)], 19, top) + _limb([P(52, -214), P(56, -176)], 15, skin) + f'<circle cx="{m * 56}" cy="-170" r="10" fill="{skin}"/>'


def person(a, ctx, seated=False):
    x = _num(a.get("x"), 0, 1200, 600)
    s = _num(a.get("scale"), 0.5, 1.6, 1.0)
    if seated:  # Hüfte liegt auf der Tischkante (table_y), der Tisch wird danach gezeichnet
        y = max(_num(a.get("table_y"), 300, 600, 470), 30 + 210 * s) + 148 * s
    else:
        y = min(max(_num(a.get("y"), 200, 760, 620), 40 + 358 * s), 650)
    skin = _col(a.get("skin"), "#f1c7a3")
    top, pants = _col(a.get("top"), "#2b4a77"), _col(a.get("pants"), "#34466a")
    style = _enum(a.get("style"), ("short", "long", "bun", "curly", "side"), "short")
    hair = _col(a.get("hair"), "#4a2f22")
    pose = _enum(a.get("pose"), ("down", "hips", "crossed", "tablet", "wave"), "down")
    left = "down" if pose in ("tablet", "wave") else pose
    back, front = _hair(style, hair)
    sx = -s if _flag(a.get("flip")) else s
    g = f'<g transform="translate({x:g},{y:g}) scale({sx:g},{s:g})">'
    g += '<ellipse cx="0" cy="2" rx="62" ry="10" fill="#000" opacity="0.12"/>'
    g += '<ellipse cx="-17" cy="-7" rx="21" ry="9" fill="#1f2a3d"/><ellipse cx="17" cy="-7" rx="21" ry="9" fill="#1f2a3d"/>'
    g += f'<rect x="-31" y="-160" width="27" height="150" rx="12" fill="{pants}"/><rect x="4" y="-160" width="27" height="150" rx="12" fill="{pants}"/>'
    g += f'<path d="M-41 -272 Q-49 -272 -49 -256 L-45 -148 L45 -148 L49 -256 Q49 -272 41 -272Z" fill="{top}"/>'
    g += back + f'<rect x="-9" y="-292" width="18" height="26" rx="6" fill="{skin}"/>'
    g += _arm("L", left, top, skin) + _arm("R", pose, top, skin)
    g += f'<ellipse cx="0" cy="-318" rx="27" ry="30" fill="{skin}"/>' + front
    g += '<ellipse cx="-10" cy="-318" rx="2.8" ry="3.4" fill="#1f2d3d"/><ellipse cx="10" cy="-318" rx="2.8" ry="3.4" fill="#1f2d3d"/>'
    g += '<path d="M-9 -304 Q0 -296 9 -304" stroke="#1f2d3d" stroke-width="2.6" fill="none" stroke-linecap="round"/>'
    g += '<circle cx="-17" cy="-308" r="5" fill="#ff8a8a" opacity="0.25"/><circle cx="17" cy="-308" r="5" fill="#ff8a8a" opacity="0.25"/>'
    if _flag(a.get("glasses")):
        g += ('<circle cx="-10" cy="-318" r="8.5" fill="none" stroke="#1f2d3d" stroke-width="2"/><circle cx="10" cy="-318" r="8.5" fill="none" stroke="#1f2d3d" stroke-width="2"/>'
              '<path d="M-2 -318 L2 -318" stroke="#1f2d3d" stroke-width="2"/>')
    ctx["count_people"] = ctx.get("count_people", 0) + 1
    return g + "</g>"


def seated(a, ctx):
    return person(a, ctx, seated=True)


def plant(a, ctx):
    x, y, s = _num(a.get("x"), 0, 1200, 100), _num(a.get("y"), 100, 760, 600), _num(a.get("scale"), 0.3, 1.5, 0.8)
    pot, leaf = _col(a.get("pot"), "#e57f84"), _col(a.get("leaf"), "#5fae7a")
    out = f'<g transform="translate({x:g},{y:g}) scale({s:g})">'
    for ang, ln in ((-35, 70), (-15, 90), (0, 100), (15, 88), (35, 66)):
        r = math.radians(ang)
        ex, ey = math.sin(r) * ln, -math.cos(r) * ln
        out += f'<path d="M0 -10 Q{ex * 0.3 + 8:.1f} {ey * 0.6:.1f} {ex:.1f} {ey:.1f} Q{ex * 0.3 - 8:.1f} {ey * 0.5:.1f} 0 -10Z" fill="{leaf}"/>'
    return out + f'<path d="M-26 -14 L26 -14 L20 34 Q0 40 -20 34Z" fill="{pot}"/></g>'


def laptop(a, ctx):
    x, y = _num(a.get("x"), 0, 1200, 600), _num(a.get("y"), 100, 760, 472)
    w, h = _num(a.get("w"), 80, 260, 130), _num(a.get("h"), 50, 160, 84)
    c = _col(a.get("color"), "#cfd8e6")
    return (f'<g><rect x="{x - w / 2:g}" y="{y - h:g}" width="{w:g}" height="{h:g}" rx="7" fill="{c}"/>'
            f'<circle cx="{x:g}" cy="{y - h / 2:g}" r="7" fill="#fff" opacity="0.9"/>'
            f'<rect x="{x - w / 2 - 8:g}" y="{y - 6:g}" width="{w + 16:g}" height="8" rx="4" fill="#b4c0d3"/></g>')


def table(a, ctx):
    x, y, w = _num(a.get("x"), 0, 1200, 670), _num(a.get("y"), 300, 640, 470), _num(a.get("w"), 200, 1000, 660)
    pal = ctx.get("pal") or {}
    if ctx.get("light") or not pal:
        panel, top, edge = "#f6f8fc", "#ffffff", "#dbe3ef"
    else:  # auf dunklem Hintergrund: Tisch in Tönen der Farbwelt statt weißem Block
        panel, top, edge = _mix(pal["deep"], "#000000", 0.15), _mix(pal["deep"], "#ffffff", 0.35), _mix(pal["deep"], "#ffffff", 0.5)
    return (f'<ellipse cx="{x:g}" cy="{y + 172:g}" rx="{w / 2 + 40:g}" ry="14" fill="#000" opacity="0.14"/>'
            f'<rect x="{x - w / 2 + 20:g}" y="{y + 18:g}" width="{w - 40:g}" height="150" rx="6" fill="{panel}" stroke="{edge}" stroke-width="3"/>'
            f'<rect x="{x - w / 2:g}" y="{y:g}" width="{w:g}" height="22" rx="8" fill="{top}" stroke="{edge}" stroke-width="3"/>')


def _shadow(ctx):
    if not ctx.get("shadow"):
        ctx["shadow"] = True
        ctx["defs"].append('<filter id="s-sh" x="-30%" y="-30%" width="170%" height="190%"><feDropShadow dx="0" dy="22" stdDeviation="20" '
                           'flood-color="#000" flood-opacity="0.4"/></filter>')


def card(a, ctx):
    x, y = _num(a.get("x"), 0, 1200, 100), _num(a.get("y"), 0, 700, 100)
    w = _num(a.get("w"), 120, 420, 290)
    kind = _enum(a.get("kind"), ("checklist", "chart", "chat", "dots", "jobad", "code"), "checklist")
    A, D = _col(a.get("accent"), "#2ec4b6"), _col(a.get("deep"), "#17406b")
    L, W = _col(a.get("light"), "#9ff5ea"), _col(a.get("warm"), "#ffc857")
    base_w = {"checklist": 290, "chart": 290, "chat": 220, "dots": 200, "jobad": 300, "code": 340}[kind]
    s = w / base_w
    h = {"checklist": 210, "chart": 230, "chat": 96, "dots": 86, "jobad": 400, "code": 230}[kind] * s
    x, y = min(max(x, 10), 1190 - w), min(max(y, 20), 620 - h)
    _shadow(ctx)
    g = f'<g transform="translate({x:g},{y:g}) scale({s:g})">'
    if kind == "checklist":
        g += f'<rect width="290" height="210" rx="24" fill="#fff" filter="url(#s-sh)"/><rect x="26" y="28" width="130" height="18" rx="9" fill="{D}"/>'
        for i, wd in enumerate((170, 140, 156)):
            yy = 84 + i * 38
            g += (f'<circle cx="42" cy="{yy}" r="14" fill="{A}"/><path d="M35 {yy} l5 6 l10 -12" stroke="#fff" stroke-width="4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
                  f'<rect x="68" y="{yy - 7}" width="{wd}" height="14" rx="7" fill="#c9d4e6"/>')
    elif kind == "chart":
        g += f'<rect width="290" height="230" rx="24" fill="#fff" filter="url(#s-sh)"/>'
        for i, hgt in enumerate((50, 80, 66, 112, 138)):
            g += f'<rect x="{30 + i * 48}" y="{200 - hgt}" width="32" height="{hgt}" rx="8" fill="{A if i % 2 == 0 else L}"/>'
        g += (f'<polyline points="46,136 94,106 142,122 190,76 238,38" fill="none" stroke="{W}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>'
              f'<circle cx="238" cy="38" r="9" fill="{W}"/>')
    elif kind == "chat":
        g += f'<rect width="220" height="96" rx="36" fill="{A}" filter="url(#s-sh)"/><rect x="30" y="30" width="150" height="14" rx="7" fill="#fff"/><rect x="30" y="56" width="100" height="14" rx="7" fill="#fff" opacity="0.8"/>'
    elif kind == "dots":
        g += f'<rect width="200" height="86" rx="34" fill="#fff" filter="url(#s-sh)"/><circle cx="55" cy="43" r="14" fill="{A}"/><circle cx="100" cy="43" r="14" fill="{L}"/><circle cx="145" cy="43" r="14" fill="{W}"/>'
    elif kind == "code":  # Code-Fenster für Technik- und IT-Themen
        g += (f'<rect width="340" height="230" rx="20" fill="#1c2b45" filter="url(#s-sh)"/><rect width="340" height="40" rx="20" fill="#2a3d5f"/><rect y="20" width="340" height="20" fill="#2a3d5f"/>'
              '<circle cx="26" cy="20" r="6" fill="#ff7a7a"/><circle cx="48" cy="20" r="6" fill="#ffc857"/><circle cx="70" cy="20" r="6" fill="#6fdc8c"/>')
        for i, (ind, wd, col) in enumerate(((0, 120, A), (24, 170, L), (24, 130, W), (48, 150, "#8aa2c0"), (24, 90, L), (0, 60, A), (0, 140, "#8aa2c0"))):
            g += f'<rect x="{28 + ind}" y="{64 + i * 22}" width="{wd}" height="10" rx="5" fill="{col}"/>'
    else:  # jobad: Stellenprofil mit drei Gesichtern, Haken und Knopf
        g += '<rect width="300" height="400" rx="30" fill="#fff" stroke="#e3edf8" stroke-width="3" filter="url(#s-sh)"/>'
        for i, (sk, hr, bg) in enumerate((("#f1c7a3", "#4a2f22", "#dff6f2"), ("#c58a65", "#1c1613", "#fdf0d0"), ("#f7d9bd", "#a8643a", "#d6e6f7"))):
            cx = 74 + i * 76
            g += (f'<circle cx="{cx}" cy="72" r="38" fill="{bg}" stroke="#fff" stroke-width="5"/><circle cx="{cx}" cy="76" r="18" fill="{sk}"/>'
                  f'<path d="M{cx - 19} 72 C{cx - 16} 50 {cx + 16} 50 {cx + 19} 72 C{cx + 12} 60 {cx - 12} 60 {cx - 19} 72Z" fill="{hr}"/>'
                  f'<circle cx="{cx - 6}" cy="77" r="2.4" fill="#1f2d3d"/><circle cx="{cx + 6}" cy="77" r="2.4" fill="#1f2d3d"/>'
                  f'<path d="M{cx - 6} 85 Q{cx} 90 {cx + 6} 85" stroke="#1f2d3d" stroke-width="2.2" fill="none" stroke-linecap="round"/>')
        g += f'<rect x="40" y="138" width="190" height="22" rx="11" fill="{D}"/><rect x="40" y="172" width="125" height="12" rx="6" fill="#b7c7da"/>'
        for yy, wd in ((226, 160), (272, 130), (318, 148)):
            g += (f'<circle cx="50" cy="{yy}" r="16" fill="{A}"/><path d="M42 {yy} l6 7 l11 -13" stroke="#fff" stroke-width="4.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
                  f'<rect x="82" y="{yy - 7}" width="{wd}" height="14" rx="7" fill="#aebfd3"/>')
        g += f'<rect x="40" y="346" width="220" height="40" rx="20" fill="{A}"/><rect x="100" y="362" width="100" height="10" rx="5" fill="#fff"/>'
    return g + "</g>"


def lupe(a, ctx):
    s = _num(a.get("scale"), 0.4, 1.6, 1.0)
    x = min(max(_num(a.get("x"), 0, 1200, 800), 130 * s), 1190 - 200 * s)
    y = min(max(_num(a.get("y"), 0, 760, 360), 30 + 130 * s), 600 - 200 * s)
    A = _col(a.get("accent"), "#2ec4b6")
    return (f'<g transform="translate({x:g},{y:g}) scale({s:g})"><circle r="118" fill="{A}" fill-opacity="0.18" stroke="#fff" stroke-width="22"/>'
            '<path d="M83 83 L180 180" stroke="#fff" stroke-width="30" stroke-linecap="round"/>'
            '<path d="M-60 -40 A70 70 0 0 1 -10 -75" stroke="#fff" stroke-opacity="0.7" stroke-width="12" fill="none" stroke-linecap="round"/></g>')


def pin(a, ctx):
    s = _num(a.get("scale"), 0.4, 2.0, 1.0)
    x, y = _num(a.get("x"), 50, 1150, 600), max(_num(a.get("y"), 0, 760, 200), 30 + 130 * s)
    return (f'<g transform="translate({x:g},{y:g}) scale({s:g})"><path d="M0 0 C0 0 -45 -50 -45 -84 A45 45 0 0 1 45 -84 C45 -50 0 0 0 0Z" fill="{_col(a.get("color"), "#ffc857")}"/>'
            f'<circle cy="-84" r="17" fill="{_col(a.get("deep"), "#17406b")}"/></g>')


def laden(a, ctx):
    s = _num(a.get("scale"), 0.4, 1.4, 1.0)
    x, y = min(max(_num(a.get("x"), 0, 1200, 600), 230 * s), 1200 - 230 * s), min(max(_num(a.get("y"), 200, 700, 585), 30 + 325 * s), 620)
    A, D = _col(a.get("accent"), "#2ec4b6"), _col(a.get("deep"), "#17406b")
    g = f'<g transform="translate({x:g},{y:g}) scale({s:g})"><rect x="-220" y="-265" width="440" height="265" rx="14" fill="#f4f7fb"/>'
    for i in range(7):
        g += f'<rect x="{-220 + i * 63}" y="-323" width="63" height="62" fill="{A if i % 2 == 0 else "#fff"}"/>'
    for cx, col in ((-189, A), (-63, A), (63, A), (189, A), (-126, "#fff"), (0, "#fff"), (126, "#fff")):
        g += f'<circle cx="{cx}" cy="-261" r="31" fill="{col}"/>'
    g += (f'<rect x="-50" y="-155" width="90" height="155" rx="8" fill="{D}"/><circle cx="25" cy="-75" r="6" fill="#ffc857"/>'
          '<rect x="-192" y="-185" width="120" height="100" rx="8" fill="#cfe3f7"/><rect x="72" y="-185" width="120" height="100" rx="8" fill="#cfe3f7"/>')
    return g + "</g>"


def sparkle(a, ctx):
    x, y, r = _num(a.get("x"), 0, 1200, 300), _num(a.get("y"), 0, 760, 150), _num(a.get("size"), 10, 80, 40)
    k = r * 0.28
    return (f'<path d="M{x:g} {y - r:g} L{x + k:g} {y - k:g} L{x + r:g} {y:g} L{x + k:g} {y + k:g} L{x:g} {y + r:g} L{x - k:g} {y + k:g} L{x - r:g} {y:g} L{x - k:g} {y - k:g}Z" '
            f'fill="{_col(a.get("color"), "#ffc857")}"/>')


def glow(a, ctx):
    ctx["n"] = ctx.get("n", 0) + 1
    gid = f"s-glow{ctx['n']}"
    c = _col(a.get("color"), "#3ee0cf")
    ctx["defs"].append(f'<radialGradient id="{gid}"><stop offset="0" stop-color="{c}" stop-opacity="0.5"/><stop offset="1" stop-color="{c}" stop-opacity="0"/></radialGradient>')
    return (f'<ellipse cx="{_num(a.get("x"), 0, 1200, 600):g}" cy="{_num(a.get("y"), 0, 760, 380):g}" rx="{_num(a.get("rx"), 80, 700, 520):g}" '
            f'ry="{_num(a.get("ry"), 80, 500, 340):g}" fill="url(#{gid})"/>')


def room(a, ctx):
    """Helles Büro: Wand, Fenster mit Skyline, Lampen, Regal, Boden ab y 600. Nur auf heller Farbwelt."""
    if not ctx.get("light"):
        return ""
    s = ('<defs><linearGradient id="s-wall" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#eef3fa"/><stop offset="1" stop-color="#dce6f3"/></linearGradient>'
         '<linearGradient id="s-sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#c3dcf6"/><stop offset="1" stop-color="#eaf4fd"/></linearGradient>'
         '<linearGradient id="s-cone" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff" stop-opacity="0.75"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/></linearGradient></defs>')
    s += '<rect width="1200" height="760" fill="url(#s-wall)"/><rect y="600" width="1200" height="160" fill="#d3deec"/><rect y="594" width="1200" height="8" fill="#c4d1e2"/>'
    s += '<rect x="360" y="70" width="770" height="300" rx="6" fill="url(#s-sky)" stroke="#fff" stroke-width="10"/>'
    s += '<g fill="#fff" opacity="0.9"><ellipse cx="520" cy="130" rx="52" ry="18"/><ellipse cx="560" cy="120" rx="36" ry="16"/><ellipse cx="900" cy="170" rx="60" ry="18"/></g>'
    s += '<g fill="#b8cee6">' + "".join(f'<rect x="{x}" y="{360 - h}" width="{w}" height="{h}"/>' for x, w, h in (
        (380, 60, 120), (445, 45, 170), (495, 70, 100), (570, 50, 200), (625, 66, 140), (700, 52, 110), (758, 64, 180), (826, 48, 130), (880, 70, 95), (955, 50, 160), (1010, 60, 120), (1075, 50, 150))) + '</g>'
    s += '<g fill="#fff"><rect x="548" y="70" width="8" height="300"/><rect x="738" y="70" width="8" height="300"/><rect x="928" y="70" width="8" height="300"/></g>'
    for lx in (170, 450, 730, 1010):
        s += (f'<line x1="{lx}" y1="0" x2="{lx}" y2="40" stroke="#98a6bb" stroke-width="4"/><path d="M{lx - 34} 72 L{lx - 16} 38 L{lx + 16} 38 L{lx + 34} 72Z" fill="#a9b7cf"/>'
              f'<polygon points="{lx - 30},74 {lx + 30},74 {lx + 150},430 {lx - 150},430" fill="url(#s-cone)" opacity="0.5"/>')
    s += ('<rect x="40" y="190" width="270" height="404" rx="6" fill="#fff" stroke="#d0dae8" stroke-width="3"/>'
          '<g stroke="#d0dae8" stroke-width="3"><line x1="40" y1="340" x2="310" y2="340"/><line x1="40" y1="490" x2="310" y2="490"/><line x1="175" y1="190" x2="175" y2="594"/></g>'
          '<rect x="62" y="262" width="80" height="78" rx="4" fill="#f3b27a"/><rect x="196" y="282" width="86" height="58" rx="4" fill="#f4c7c3"/>'
          '<rect x="62" y="420" width="90" height="70" rx="4" fill="#9ab7de"/><rect x="200" y="404" width="80" height="86" rx="4" fill="#cfd8e6"/>'
          '<rect x="62" y="520" width="96" height="74" rx="4" fill="#cfd8e6"/><rect x="196" y="526" width="84" height="68" rx="4" fill="#f3b27a"/>'
          '<circle cx="176" cy="130" r="30" fill="#fff" stroke="#9aa9bf" stroke-width="5"/><path d="M176 130 L176 112 M176 130 L190 136" stroke="#6f7f96" stroke-width="4" stroke-linecap="round"/>')
    return s + plant({"x": "90", "y": "190", "scale": "0.7"}, ctx)


MACROS = {"person": person, "seated": seated, "plant": plant, "laptop": laptop, "table": table, "card": card, "lupe": lupe,
          "pin": pin, "laden": laden, "sparkle": sparkle, "glow": glow, "room": room}


def expand(scene, light=False, pal=None):
    """Ersetzt die Baustein-Tags durch geprüftes SVG. Unbekannte Tags bleiben für die spätere Bereinigung stehen."""
    root = ET.fromstring(f'<g xmlns="{SVG_NS}">{scene}</g>')
    ctx = {"defs": [], "light": light, "pal": pal, "count": 0}

    def walk(el):
        for child in list(el):
            local = child.tag.split("}")[-1]
            if local in MACROS:
                idx = list(el).index(child)
                el.remove(child)
                ctx["count"] += 1
                if ctx["count"] <= MAX_MACROS:
                    piece = ET.fromstring(f'<g xmlns="{SVG_NS}">{MACROS[local](dict(child.attrib), ctx)}</g>')
                    el.insert(idx, piece)
            else:
                walk(child)

    walk(root)
    defs = "".join(ctx["defs"])
    body = "".join(ET.tostring(c, encoding="unicode") for c in root)
    return (f"<defs>{defs}</defs>" if defs else "") + body
