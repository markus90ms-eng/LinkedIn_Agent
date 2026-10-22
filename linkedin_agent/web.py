"""Lokale Weboberfläche: nächster Post anzeigen, bearbeiten, neu generieren, posten.

Läuft nur auf 127.0.0.1 und nur, solange das Fenster offen ist.
"""
import base64
import html
import os
import re
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

from . import db, drafts, images, linkedin

PAGE = """<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>LinkedIn-Assistent</title>
<style>
  :root {{ --bg:#f3f2ef; --card:#fff; --text:#1f2328; --muted:#667; --blue:#0a66c2; --red:#b42318; --green:#177245; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#1b1f23; --card:#262b30; --text:#e8eaed; --muted:#9aa4ae; --blue:#6cb2f5; --red:#f0877c; --green:#6fcf97; }} }}
  body {{ margin:0; background:var(--bg); color:var(--text); font:16px/1.5 system-ui,Segoe UI,sans-serif; }}
  main {{ max-width:760px; margin:0 auto; padding:24px 16px 64px; }}
  h1 {{ font-size:22px; margin:0 0 16px; }}
  .card {{ background:var(--card); border-radius:12px; padding:20px; margin-bottom:16px; box-shadow:0 1px 3px rgba(0,0,0,.12); }}
  .meta {{ color:var(--muted); font-size:14px; margin-bottom:8px; }}
  textarea, input[type=text] {{ width:100%; box-sizing:border-box; border:1px solid #8884; border-radius:8px; padding:10px; font:inherit; background:var(--bg); color:var(--text); }}
  textarea {{ min-height:360px; line-height:1.55; }}
  .row {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }}
  button {{ font:inherit; border:1px solid #8886; border-radius:999px; padding:9px 18px; background:transparent; color:var(--text); cursor:pointer; }}
  button.primary {{ background:var(--blue); border-color:var(--blue); color:#fff; font-weight:600; }}
  button.danger {{ color:var(--red); }}
  .msg {{ padding:12px 16px; border-radius:8px; margin-bottom:16px; background:#177245; color:#fff; }}
  .msg.err {{ background:var(--red); }}
  .small {{ font-size:14px; color:var(--muted); }}
  ul {{ padding-left:20px; }} a {{ color:var(--blue); }}
</style></head><body><main>
<h1>LinkedIn-Assistent</h1>
{msg}
{body}
</main></body></html>"""


def _queue(conn):
    return conn.execute("SELECT * FROM posts WHERE status IN ('draft','approved') ORDER BY id").fetchall()


def _form(token, action, post_id, label, cls="", extra="", confirm=""):
    onclick = f" onclick=\"return confirm('{confirm}')\"" if confirm else ""
    return (f'<form method="post" action="/{action}" style="display:inline">'
            f'<input type="hidden" name="token" value="{token}"><input type="hidden" name="id" value="{post_id}">'
            f'{extra}<button class="{cls}"{onclick}>{label}</button></form>')


def render(conn, token, msg="", error=False):
    esc = html.escape
    queue = _queue(conn)
    published = conn.execute("SELECT * FROM posts WHERE status='published' ORDER BY id DESC LIMIT 5").fetchall()
    parts = []
    if queue:
        p, rest = queue[0], queue[1:]
        has_img = bool(p["image_path"]) and os.path.exists(p["image_path"])
        img_block = ""
        if has_img:
            ver = int(os.path.getmtime(p["image_path"]))
            ext = os.path.splitext(p["image_path"])[1].lstrip(".").lower()
            kind = "svg" if ext == "svg" else "file"
            img_block = (f'<img id="preview" data-kind="{kind}" src="/img/{p["id"]}.{ext}?v={ver}" alt="Bildvorschau" '
                         f'style="max-width:420px;width:100%;border-radius:8px;margin-top:12px;display:block">'
                         f'<input type="hidden" name="png" id="png">'
                         f'<p class="small">Bildidee: {esc(p["image_idea"] or "")}</p>'
                         f'<label class="small"><input type="checkbox" name="with_image" value="1" checked> Bild mitposten</label>')
        img_buttons = ('<button formaction="/image">Bild neu erstellen</button>'
                       '<button formaction="/imageremove" class="danger">Bild entfernen</button>') if has_img \
            else '<button formaction="/image">Bild erstellen</button>'
        img_buttons += '<button type="button" onclick="document.getElementById(\'upfile\').click()">Eigenes Bild hochladen</button>'
        upload_block = (f'<input type="file" id="upfile" accept="image/png,image/jpeg,image/webp" hidden onchange="uploadImage(this)">'
                        f'<input type="hidden" name="upload" id="upload">'
                        f'<input type="text" name="alt" placeholder="Bildbeschreibung für Screenreader (optional, gilt für das hochgeladene Bild)" '
                        f'value="{esc(p["image_alt"] or "") if has_img and not str(p["image_path"]).endswith(".svg") else ""}" style="margin-top:12px">')
        src = f' · <a href="{esc(p["source_url"])}" target="_blank" rel="noopener">Quelle</a>' if p["source_url"] else ""
        parts.append(
            f'<div class="card"><div class="meta">Nächster Post · Thema: {esc(p["topic"] or "-")}{src} · '
            f'{len(rest)} weitere in der Warteschlange</div>'
            f'<form method="post" action="/post" id="main">'
            f'<input type="hidden" name="token" value="{token}"><input type="hidden" name="id" value="{p["id"]}">'
            f'<textarea name="text">{esc(p["text"])}</textarea>{img_block}{upload_block}'
            f'<div class="row">'
            f'<button class="primary" onclick="return preparePost()">Jetzt posten</button>'
            f'<button type="button" onclick="wrapBold()" title="Markierten Text fett machen">Fett</button>'
            f'<button formaction="/save">Änderungen speichern</button>{img_buttons}</div></form>'
            f'<p class="small">Fett: Text markieren und auf „Fett“ klicken (setzt ** um die Stelle). '
            f'Beim Posten wird daraus fette Schrift. Sparsam nutzen, Screenreader lesen sie schlecht vor.</p>'
            f'<div class="row">'
            f'{_form(token, "regenerate", p["id"], "Neu generieren")}'
            f'{_form(token, "reject", p["id"], "Verwerfen", "danger", confirm="Diesen Entwurf verwerfen?")}</div>'
            f'<form method="post" action="/revise" class="row"><input type="hidden" name="token" value="{token}">'
            f'<input type="hidden" name="id" value="{p["id"]}">'
            f'<input type="text" name="instruction" placeholder="Anweisung, z. B. kürzer, mehr Biss, anderer Einstieg" required>'
            f'<button>Überarbeiten</button></form></div>')
        parts.append(
            f'<div class="card"><div class="meta">Bildwunsch für ChatGPT · wird NICHT mitgepostet</div>'
            f'<form method="post" action="/prompt" id="promptform" '
            f'onsubmit="document.getElementById(\'ptext\').value=document.querySelector(\'#main textarea\').value">'
            f'<input type="hidden" name="token" value="{token}"><input type="hidden" name="id" value="{p["id"]}">'
            f'<input type="hidden" name="text" id="ptext">'
            f'<textarea name="prompt_text" id="promptText" style="min-height:200px" '
            f'placeholder="Noch kein Bildwunsch. Klicke auf „Bildwunsch vorschlagen“, dann schreibt Claude einen passend zum Text.">{esc(p["image_prompt"] or "")}</textarea>'
            f'<div class="row"><button class="primary" formaction="/promptnew">{"Neu vorschlagen" if p["image_prompt"] else "Bildwunsch vorschlagen"}</button>'
            f'<button type="button" id="copyBtn" onclick="copyPrompt()">Kopieren</button>'
            f'<button formaction="/promptsave">Speichern</button></div>'
            f'<div class="row"><input type="text" name="instruction" placeholder="Anpassen, z. B. ohne Personen, heller, eher ein Büro">'
            f'<button>Anpassen</button></div></form>'
            f'<p class="small">Ablauf: kopieren, in ChatGPT einfügen, Bild erzeugen lassen, herunterladen und oben mit „Eigenes Bild hochladen“ anhängen. '
            f'Der Bildwunsch basiert auf dem Text im Feld oben, der dabei mitgespeichert wird.</p></div>')
        if rest:
            items = "".join(f"<li>{esc(r['text'][:90])}…</li>" for r in rest[:5])
            parts.append(f'<div class="card"><div class="meta">Danach folgen</div><ul>{items}</ul></div>')
    else:
        parts.append('<div class="card">Keine Entwürfe mehr. Erzeuge neue, dann erscheint hier der nächste Post.</div>')
    parts.append('<div class="card">' + _form(token, "generate", 0, "Neue Entwürfe erzeugen")
                 + '<span class="small"> Dauert etwa eine Minute.</span></div>')
    if published:
        items = "".join(f"<li>{esc((r['published_at'] or '')[:10])}: {esc(r['text'][:70])}…</li>" for r in published)
        parts.append(f'<div class="card"><div class="meta">Zuletzt veröffentlicht</div><ul>{items}</ul></div>')
    parts.append("""<script>
function preparePost() {
  if (!confirm('Jetzt öffentlich auf LinkedIn veröffentlichen?')) return false;
  const img = document.getElementById('preview');
  const box = document.querySelector('#main input[name=with_image]');
  if (img && img.dataset.kind === 'svg' && box && box.checked) {
    if (!img.complete || !img.naturalWidth) { alert('Das Bild ist noch nicht geladen. Bitte kurz warten und noch einmal klicken.'); return false; }
    try {
      const c = document.createElement('canvas'); c.width = 1200; c.height = 1200;
      c.getContext('2d').drawImage(img, 0, 0, 1200, 1200);
      document.getElementById('png').value = c.toDataURL('image/png');
    } catch (e) { alert('Das Bild konnte nicht umgewandelt werden: ' + e); return false; }
  }
  return true;
}
function uploadImage(input) {
  const f = input.files[0];
  if (!f) return;
  const im = new Image();
  im.onload = () => {
    const k = Math.min(1, 2048 / Math.max(im.naturalWidth, im.naturalHeight));
    const c = document.createElement('canvas');
    c.width = Math.round(im.naturalWidth * k); c.height = Math.round(im.naturalHeight * k);
    const ctx = c.getContext('2d');
    const encode = (png) => {
      if (!png) { ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, c.width, c.height); }
      ctx.drawImage(im, 0, 0, c.width, c.height);
      return c.toDataURL(png ? 'image/png' : 'image/jpeg', 0.9);
    };
    let data = encode(f.type === 'image/png');
    if (data.length > 6000000) data = encode(false);  // große PNG-Fotos als JPEG, sonst zu groß für LinkedIn
    document.getElementById('upload').value = data;
    const form = document.getElementById('main');
    form.action = '/upload';
    form.submit();
  };
  im.onerror = () => alert('Diese Datei kann ich nicht als Bild lesen. Bitte PNG oder JPG nehmen.');
  im.src = URL.createObjectURL(f);
}
function copyPrompt() {
  const t = document.getElementById('promptText');
  const b = document.getElementById('copyBtn');
  if (!t.value.trim()) { alert('Es gibt noch keinen Bildwunsch zum Kopieren.'); return; }
  const done = () => { b.textContent = 'Kopiert ✓'; setTimeout(() => b.textContent = 'Kopieren', 1600); };
  t.select();
  if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(t.value).then(done, () => { document.execCommand('copy'); done(); });
  else { document.execCommand('copy'); done(); }
}
function wrapBold() {
  const t = document.querySelector('#main textarea');
  const a = t.selectionStart, b = t.selectionEnd;
  if (a === b) { alert('Erst die Stelle im Text markieren, die fett werden soll.'); return; }
  const sel = t.value.slice(a, b);
  const wrapped = sel.startsWith('**') && sel.endsWith('**') && sel.length > 4 ? sel.slice(2, -2) : '**' + sel + '**';
  t.setRangeText(wrapped, a, b, 'select');
  t.focus();
}
</script>""")
    banner = f'<div class="msg{" err" if error else ""}">{esc(msg)}</div>' if msg else ""
    return PAGE.format(msg=banner, body="\n".join(parts))


def make_handler(cfg, token, port):
    post_lock = threading.Lock()
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, headers=None):
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _send_bytes(self, code, data, content_type):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def _redirect(self, msg, error=False):
            q = urlencode({"msg": msg, "err": "1" if error else ""})
            self._send(303, "", {"Location": f"/?{q}"})

        def do_GET(self):
            if self.headers.get("Host") not in allowed_hosts:
                return self._send(403, "Forbidden")
            m = re.fullmatch(r"/img/(\d+)\.(svg|png|jpg)", urlparse(self.path).path)
            if m:
                return self._image(int(m.group(1)))
            q = parse_qs(urlparse(self.path).query)
            conn = db.connect(cfg["db_path"])
            try:
                page = render(conn, token, q.get("msg", [""])[0], bool(q.get("err", [""])[0]))
            finally:
                conn.close()
            self._send(200, page)

        def _image(self, pid):
            conn = db.connect(cfg["db_path"])
            try:
                row = conn.execute("SELECT image_path FROM posts WHERE id=?", (pid,)).fetchone()
            finally:
                conn.close()
            path = row["image_path"] if row else None
            if not path or not os.path.exists(path):
                return self._send(404, "Kein Bild")
            kind = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg"}.get(os.path.splitext(path)[1].lower())
            if not kind:
                return self._send(404, "Kein Bild")
            with open(path, "rb") as f:
                self._send_bytes(200, f.read(), kind)

        def do_POST(self):
            if self.headers.get("Host") not in allowed_hosts:
                return self._send(403, "Forbidden")
            length = int(self.headers.get("Content-Length") or 0)
            if length > 12_000_000:
                return self._send(413, "Zu groß")
            form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True).items()}
            if not secrets.compare_digest(form.get("token", ""), token):
                return self._send(403, "Ungültiges Token")
            action = urlparse(self.path).path.strip("/")
            conn = db.connect(cfg["db_path"])
            try:
                msg = self._act(conn, action, form, post_lock)
            except Exception as e:  # Fehler anzeigen statt Server abstürzen lassen
                return self._redirect(f"Fehler: {e}", True)
            finally:
                conn.close()
            self._redirect(msg)

        @staticmethod
        def _drop_images(post_id):
            folder = os.path.join(os.path.dirname(cfg["db_path"]) or ".", "images")
            for name in (f"{post_id}.svg", f"{post_id}.png", f"{post_id}.upload.png", f"{post_id}.upload.jpg"):
                if os.path.exists(os.path.join(folder, name)):
                    os.remove(os.path.join(folder, name))

        @staticmethod
        def _save_upload(post_id, data_url):
            m = re.fullmatch(r"data:image/(png|jpeg);base64,(.+)", data_url or "", re.S)
            if not m:
                raise RuntimeError("Das Bild wurde nicht übertragen. Bitte PNG oder JPG nehmen und noch einmal versuchen.")
            data = base64.b64decode(m.group(2))
            ok = data.startswith(b"\x89PNG") if m.group(1) == "png" else data.startswith(b"\xff\xd8\xff")
            if not ok or len(data) > 4_500_000:
                raise RuntimeError("Das Bild ist ungültig oder größer als 4,5 MB.")
            folder = os.path.join(os.path.dirname(cfg["db_path"]) or ".", "images")
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, f"{post_id}.upload.{'png' if m.group(1) == 'png' else 'jpg'}")
            with open(path, "wb") as f:
                f.write(data)
            return path

        @staticmethod
        def _save_png(svg_path, data_url):
            prefix = "data:image/png;base64,"
            if not data_url.startswith(prefix):
                raise RuntimeError("Das Bild wurde nicht übertragen. Bitte Seite neu laden und noch einmal versuchen.")
            data = base64.b64decode(data_url[len(prefix):])
            if not data.startswith(b"\x89PNG") or len(data) > 4_500_000:
                raise RuntimeError("Das Bild ist ungültig oder zu groß.")
            png = os.path.splitext(svg_path)[0] + ".png"
            with open(png, "wb") as f:
                f.write(data)
            return png

        def _act(self, conn, action, form, lock):
            pid = int(form.get("id") or 0)
            row = conn.execute("SELECT * FROM posts WHERE id=?", (pid,)).fetchone() if pid else None
            if action == "generate":
                ids = drafts.create_drafts(cfg, conn)
                return f"{len(ids)} neue Entwürfe erzeugt."
            if row is None or row["status"] not in ("draft", "approved"):
                raise RuntimeError("Dieser Post ist nicht mehr offen.")
            if action == "save":
                db.update_text(conn, pid, form["text"])
                return "Gespeichert."
            if action == "promptsave":
                db.set_prompt(conn, pid, form.get("prompt_text", "").strip())
                return "Bildwunsch gespeichert."
            if action in ("promptnew", "prompt"):
                text = (form.get("text") or row["text"]).strip()
                db.update_text(conn, pid, text)  # Änderungen im Textfeld gehen beim Neuladen nicht verloren
                previous, instruction = form.get("prompt_text", "").strip(), form.get("instruction", "").strip()
                if action == "prompt" and not (previous and instruction):
                    raise RuntimeError("Zum Anpassen braucht es einen vorhandenen Bildwunsch und eine Anweisung.")
                prompt = images.make_prompt(cfg, text, previous or None, instruction or None) if action == "prompt" \
                    else images.make_prompt(cfg, text)
                db.set_prompt(conn, pid, prompt)
                return "Bildwunsch angepasst." if action == "prompt" else "Bildwunsch vorgeschlagen. Du kannst ihn anpassen und kopieren."
            if action == "upload":
                db.update_text(conn, pid, form["text"])
                self._drop_images(pid)
                path = self._save_upload(pid, form.get("upload", ""))
                db.set_image(conn, pid, path, form.get("alt", "").strip()[:300], "Eigenes Bild")
                return "Bild hochgeladen. Es wird mitgepostet, solange der Haken gesetzt ist."
            if action == "image":
                db.update_text(conn, pid, form["text"])
                old = row["image_path"]
                path, alt, idea = images.make_scene(cfg, form["text"], pid)
                if old and not str(old).endswith(".svg") and os.path.exists(old):
                    os.remove(old)  # früher hochgeladenes Bild wird durch das neue Motiv ersetzt
                db.set_image(conn, pid, path, alt, idea)
                return "Bild erstellt. Bitte unten ansehen, bei Bedarf neu erstellen."
            if action == "imageremove":
                db.update_text(conn, pid, form["text"])
                self._drop_images(pid)
                db.set_image(conn, pid, None, None)
                return "Bild entfernt."
            if action == "post":
                with lock:  # verhindert Doppelposts bei doppeltem Klick
                    fresh = conn.execute("SELECT status FROM posts WHERE id=?", (pid,)).fetchone()
                    if fresh["status"] not in ("draft", "approved"):
                        raise RuntimeError("Dieser Post wurde bereits veröffentlicht.")
                    text = form["text"].strip()
                    if not text:
                        raise RuntimeError("Der Text ist leer.")
                    db.update_text(conn, pid, text)
                    path = None
                    if form.get("with_image") and row["image_path"]:
                        if str(row["image_path"]).endswith(".svg"):
                            path = self._save_png(row["image_path"], form.get("png", ""))
                        elif os.path.exists(row["image_path"]):
                            path = row["image_path"]  # hochgeladenes Bild, bereits PNG oder JPG
                    ref = linkedin.publish(text, path, row["image_alt"])
                    db.mark_published(conn, pid, ref)
                return "Veröffentlicht. Der Post ist jetzt auf LinkedIn."
            if action == "regenerate":
                db.update_text(conn, pid, drafts.generate_text(cfg, row["topic"] or "Vertrieb"))
                return "Neuer Text erzeugt."
            if action == "revise":
                db.update_text(conn, pid, drafts.revise(cfg, row["text"], form["instruction"]))
                return "Überarbeitet."
            if action == "reject":
                db.set_status(conn, pid, "rejected")
                return "Verworfen."
            raise RuntimeError("Unbekannte Aktion.")

    return Handler


def serve(cfg, port=8501, open_browser=True):
    token = secrets.token_urlsafe(24)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(cfg, token, port))
    url = f"http://127.0.0.1:{port}/"
    print(f"Assistent läuft auf {url}  (Fenster offen lassen, mit Strg+C beenden)")
    if open_browser:
        threading.Timer(0.8, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
