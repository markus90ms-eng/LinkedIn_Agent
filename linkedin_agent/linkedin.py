"""LinkedIn-Anbindung über die offizielle API (OAuth 2.0 + Posts API).

Voraussetzung: LinkedIn-App auf https://www.linkedin.com/developers/ mit den Produkten
"Share on LinkedIn" und "Sign In with LinkedIn using OpenID Connect".
Redirect-URL der App: http://localhost:8765/callback
"""
import json
import os
import re
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests

TOKEN_FILE = Path("data/linkedin_token.json")
REDIRECT_URI = "http://localhost:8765/callback"
API_VERSION = "202405"
RESERVED = re.compile(r"([\\|{}@\[\]()<>*_~])")  # '#' bleibt unescaped, damit Hashtags funktionieren


def escape_commentary(text):
    """Escaped LinkedIn-Sonderzeichen ("little text format"), sonst wird der Post abgeschnitten."""
    return RESERVED.sub(r"\\\1", text)


def build_payload(author_urn, text):
    return {
        "author": author_urn,
        "commentary": escape_commentary(text),
        "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }


def authorize():
    """Einmaliger Login im Browser; speichert Access-Token und Personen-URN."""
    cid, secret = os.environ["LINKEDIN_CLIENT_ID"], os.environ["LINKEDIN_CLIENT_SECRET"]
    state = secrets.token_urlsafe(16)
    params = {"response_type": "code", "client_id": cid, "redirect_uri": REDIRECT_URI,
              "state": state, "scope": "openid profile w_member_social"}
    result = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = parse_qs(urlparse(self.path).query)
            result["code"], result["state"] = q.get("code", [None])[0], q.get("state", [None])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write("Fertig – du kannst dieses Fenster schließen.".encode())

        def log_message(self, *a):
            pass

    url = "https://www.linkedin.com/oauth/v2/authorization?" + urlencode(params)
    print("Öffne im Browser:", url)
    webbrowser.open(url)
    HTTPServer(("localhost", 8765), Handler).handle_request()
    if result.get("state") != state or not result.get("code"):
        raise RuntimeError("Autorisierung fehlgeschlagen (State/Code ungültig).")
    r = requests.post("https://www.linkedin.com/oauth/v2/accessToken", data={
        "grant_type": "authorization_code", "code": result["code"], "redirect_uri": REDIRECT_URI,
        "client_id": cid, "client_secret": secret}, timeout=30)
    r.raise_for_status()
    token = r.json()
    me = requests.get("https://api.linkedin.com/v2/userinfo",
                      headers={"Authorization": f"Bearer {token['access_token']}"}, timeout=30)
    me.raise_for_status()
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps({"access_token": token["access_token"],
                                      "expires_in": token.get("expires_in"),
                                      "author": f"urn:li:person:{me.json()['sub']}"}))
    TOKEN_FILE.chmod(0o600)
    print("Gespeichert in", TOKEN_FILE)


def publish(text):
    """Veröffentlicht einen Post und liefert die LinkedIn-Post-ID."""
    if not TOKEN_FILE.exists():
        raise RuntimeError("Nicht eingeloggt – erst `python -m linkedin_agent auth` ausführen.")
    tok = json.loads(TOKEN_FILE.read_text())
    r = requests.post("https://api.linkedin.com/rest/posts", json=build_payload(tok["author"], text), headers={
        "Authorization": f"Bearer {tok['access_token']}",
        "LinkedIn-Version": API_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
    }, timeout=30)
    if r.status_code != 201:
        raise RuntimeError(f"LinkedIn-Fehler {r.status_code}: {r.text}")
    return r.headers.get("x-restli-id", "")
