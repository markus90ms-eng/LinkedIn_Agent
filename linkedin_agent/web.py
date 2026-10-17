"""Lokale Weboberfläche: nächster Post anzeigen, bearbeiten, neu generieren, posten.

Läuft nur auf 127.0.0.1 und nur, solange das Fenster offen ist.
"""
import html
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

from . import db, drafts, linkedin

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
        src = f' · <a href="{esc(p["source_url"])}" target="_blank" rel="noopener">Quelle</a>' if p["source_url"] else ""
        parts.append(
            f'<div class="card"><div class="meta">Nächster Post · Thema: {esc(p["topic"] or "-")}{src} · '
            f'{len(rest)} weitere in der Warteschlange</div>'
            f'<form method="post" action="/post" id="main">'
            f'<input type="hidden" name="token" value="{token}"><input type="hidden" name="id" value="{p["id"]}">'
            f'<textarea name="text">{esc(p["text"])}</textarea>'
            f'<div class="row">'
            f'<button class="primary" onclick="return confirm(\'Jetzt öffentlich auf LinkedIn veröffentlichen?\')">Jetzt posten</button>'
            f'<button type="button" onclick="wrapBold()" title="Markierten Text fett machen">Fett</button>'
            f'<button formaction="/save">Änderungen speichern</button></div></form>'
            f'<p class="small">Fett: Text markieren und auf „Fett“ klicken (setzt ** um die Stelle). '
            f'Beim Posten wird daraus fette Schrift. Sparsam nutzen, Screenreader lesen sie schlecht vor.</p>'
            f'<div class="row">'
            f'{_form(token, "regenerate", p["id"], "Neu generieren")}'
            f'{_form(token, "reject", p["id"], "Verwerfen", "danger", confirm="Diesen Entwurf verwerfen?")}</div>'
            f'<form method="post" action="/revise" class="row"><input type="hidden" name="token" value="{token}">'
            f'<input type="hidden" name="id" value="{p["id"]}">'
            f'<input type="text" name="instruction" placeholder="Anweisung, z. B. kürzer, mehr Biss, anderer Einstieg" required>'
            f'<button>Überarbeiten</button></form></div>')
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

        def _redirect(self, msg, error=False):
            q = urlencode({"msg": msg, "err": "1" if error else ""})
            self._send(303, "", {"Location": f"/?{q}"})

        def do_GET(self):
            if self.headers.get("Host") not in allowed_hosts:
                return self._send(403, "Forbidden")
            q = parse_qs(urlparse(self.path).query)
            conn = db.connect(cfg["db_path"])
            try:
                page = render(conn, token, q.get("msg", [""])[0], bool(q.get("err", [""])[0]))
            finally:
                conn.close()
            self._send(200, page)

        def do_POST(self):
            if self.headers.get("Host") not in allowed_hosts:
                return self._send(403, "Forbidden")
            length = int(self.headers.get("Content-Length") or 0)
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
            if action == "post":
                with lock:  # verhindert Doppelposts bei doppeltem Klick
                    fresh = conn.execute("SELECT status FROM posts WHERE id=?", (pid,)).fetchone()
                    if fresh["status"] not in ("draft", "approved"):
                        raise RuntimeError("Dieser Post wurde bereits veröffentlicht.")
                    text = form["text"].strip()
                    if not text:
                        raise RuntimeError("Der Text ist leer.")
                    db.update_text(conn, pid, text)
                    ref = linkedin.publish(text)
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
