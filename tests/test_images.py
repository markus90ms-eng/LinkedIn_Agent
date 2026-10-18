import json
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import pytest

from linkedin_agent import db, images, linkedin

SCENE = '<defs><linearGradient id="s-a"><stop offset="0" stop-color="#fff"/></linearGradient></defs><circle cx="600" cy="380" r="100" fill="url(#s-a)"/>'


def fake_client(text):
    return SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: SimpleNamespace(
        stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)])))


def test_sanitize_removes_scripts_links_events_and_unknown_tags():
    dirty = ('<script>alert(1)</script><image href="http://evil/x.png"/><foreignObject><div/></foreignObject>'
             '<rect width="10" height="10" onclick="x()" fill="url(http://evil/a)"/>'
             '<circle r="5" style="fill:url(#ok)" xmlns:xlink="http://www.w3.org/1999/xlink"/><a href="javascript:x()"/>')
    clean = images.sanitize_scene(dirty)
    for bad in ("script", "image", "foreignObject", "onclick", "evil", "javascript", "<a "):
        assert bad not in clean
    assert "<rect" in clean and "<circle" in clean and "url(#ok)" in clean


def test_sanitize_rejects_broken_xml():
    with pytest.raises(RuntimeError):
        images.sanitize_scene("<rect><circle></rect>")


def test_compose_is_valid_svg_with_hook_and_footer():
    svg = images.compose_svg(SCENE, "Erst die Aussage, dann der Kanal & mehr <wichtig>", "Markus")
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg") and "Markus" in svg and "&amp;" in svg and "&lt;wichtig&gt;" in svg


def test_long_hook_gets_at_most_three_lines():
    size, lines = images._wrap_hook("Qualifizierte Leute suchen selten nur einen Job " * 4)
    assert len(lines) <= 3
    assert len(lines) == 2 or size <= 76
    for hook in ("Menschen vertrauen Menschen, keinem Logo.", "Qualifizierte Leute suchen selten nur einen Job."):
        size, lines = images._wrap_hook(hook)
        assert 880 + (len(lines) - 1) * int(size * 1.18) <= 1062  # letzte Zeile bleibt über der Namenszeile


def test_make_scene_writes_svg_and_alt(tmp_path):
    cfg = {"model": "m", "db_path": str(tmp_path / "t.db"), "image_footer": "Name"}
    raw = f"<idee>Eine Lupe zeigt Sichtbarkeit.</idee><hook>Mein Hook</hook><alt>Eine Lupe</alt><scene>{SCENE}</scene>"
    path, alt, idea = images.make_scene(cfg, "**Mein Hook**\n\nText", 7, client=fake_client(raw))
    assert path.endswith("7.svg") and alt == "Eine Lupe" and idea == "Eine Lupe zeigt Sichtbarkeit."
    assert "Mein Hook" in open(path, encoding="utf-8").read()


def test_make_scene_falls_back_to_first_line_of_post(tmp_path):
    cfg = {"model": "m", "db_path": str(tmp_path / "t.db")}
    path, _, _ = images.make_scene(cfg, "**Hook aus dem Post** 🙂\n\nRest", 1, client=fake_client(f"<scene>{SCENE}</scene>"))
    assert "Hook aus dem Post" in open(path, encoding="utf-8").read()


def test_missing_scene_is_an_error(tmp_path):
    with pytest.raises(RuntimeError):
        images.make_scene({"model": "m", "db_path": str(tmp_path / "t.db")}, "x", 1, client=fake_client("keine Szene"))


def test_db_migrates_old_database(tmp_path):
    import sqlite3
    p = tmp_path / "old.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE posts (id INTEGER PRIMARY KEY AUTOINCREMENT, status TEXT NOT NULL DEFAULT 'draft', text TEXT NOT NULL, topic TEXT, source_url TEXT, created_at TEXT NOT NULL, published_at TEXT, linkedin_id TEXT)")
    c.commit(); c.close()
    conn = db.connect(p)
    i = db.add_draft(conn, "x")
    db.set_image(conn, i, "a.svg", "alt")
    assert conn.execute("SELECT image_path FROM posts").fetchone()[0] == "a.svg"


def test_publish_with_image_uploads_then_posts(tmp_path, monkeypatch):
    img = tmp_path / "c.png"; img.write_bytes(b"png")
    tok = tmp_path / "tok.json"
    tok.write_text(json.dumps({"access_token": "t", "author": "urn:li:person:1", "version": "202610"}))
    monkeypatch.setattr(linkedin, "TOKEN_FILE", tok)
    calls = []

    def fake_request(method, url, **kw):
        calls.append((method, url, kw.get("json")))
        if "initializeUpload" in url:
            return SimpleNamespace(status_code=200, json=lambda: {"value": {"uploadUrl": "https://up", "image": "urn:li:image:9"}})
        return SimpleNamespace(status_code=201, headers={"x-restli-id": "urn:li:share:5"}, text="")
    monkeypatch.setattr(linkedin.requests, "request", fake_request)
    monkeypatch.setattr(linkedin.requests, "put", lambda url, **kw: SimpleNamespace(status_code=201, text=""))
    assert linkedin.publish("Text", str(img), "Alt") == "urn:li:share:5"
    assert calls[-1][2]["content"]["media"] == {"id": "urn:li:image:9", "altText": "Alt"}


def test_palette_never_repeats_last_images_or_own_previous(tmp_path):
    folder = tmp_path / "images"
    folder.mkdir()
    import os, time
    for i, name in enumerate(("ozean", "abend", "wald")):
        f = folder / f"{i + 1}.svg"
        f.write_text(images.compose_svg("<circle r='5'/>", "x", "", name), encoding="utf-8")
        os.utime(f, (time.time() + i, time.time() + i))
    for _ in range(40):
        chosen = images.pick_palette(folder, 9)
        assert chosen not in ("abend", "wald")  # die zwei zuletzt erzeugten Bilder
    for _ in range(40):
        assert images.pick_palette(folder, 1) not in ("abend", "wald", "ozean")  # auch nicht die eigene frühere


def test_bausteine_are_expanded_validated_and_clamped():
    scene = ('<person x="300" y="900" skin="javascript:evil" top="#ff0000" pose="boom" glasses="1"/>'
             '<card kind="code" x="100" y="100" w="9999"/><card kind="chart" x="600" y="100"/>'
             '<evil onclick="x()"/><seated x="500" table_y="470"/><laptop x="500" y="472"/><table x="600" y="470"/>'
             '<lupe/><laden/><pin/><sparkle/><glow/>')
    svg = images.build_scene(scene, "ozean")
    assert svg.count('id="s-sh"') == 1                       # Schatten-Filter nur einmal definiert
    assert "evil" not in svg and "javascript" not in svg and "onclick" not in svg
    assert "#ff0000" in svg and "translate(300,650)" in svg   # Farbe geprüft, Fußposition begrenzt
    assert "translate(500,618)" in svg                        # sitzende Figur: Hüfte auf Tischkante
    ET.fromstring(images.compose_svg(svg, "Hook", "", "ozean"))


def test_room_only_on_light_palette():
    assert "s-wall" in images.build_scene("<room/>", "hell")
    assert "s-wall" not in images.build_scene("<room/>", "ozean")


def test_light_palette_uses_dark_text_and_prompt_mentions_mode():
    svg = images.compose_svg("<circle r='5'/>", "Hook", "Name", "hell")
    assert 'fill="#14284a"' in svg
    assert "heller Verlauf" in images.build_system("hell", images.LAYOUTS[0])
    assert "dunkler Verlauf" in images.build_system("ozean", images.LAYOUTS[0])
    assert "@@" not in images.build_system("hell", images.LAYOUTS[0])


def test_too_many_macros_are_capped():
    svg = images.build_scene("<sparkle/>" * 200, "ozean")
    assert svg.count("<path") <= 60


def test_positions_are_kept_inside_the_canvas():
    svg = images.build_scene('<pin x="600" y="10"/><lupe x="5" y="5"/><card kind="jobad" x="1150" y="600" w="400"/>', "ozean")
    assert "translate(600,160) scale(1)" in svg   # Pin rutscht unter den oberen Rand
    assert "translate(130,160) scale(1)" in svg   # Lupe bleibt vollständig im Bild
    assert "translate(790,86.6667) scale(1.33333)" in svg  # Karte endet über der Textfläche und vor dem rechten Rand
