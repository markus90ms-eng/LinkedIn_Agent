# LinkedIn Agent

Schreibt LinkedIn-Posts in deinem Stil (Claude), du gibst frei, dann wird über die offizielle LinkedIn-API veröffentlicht.

## Einrichtung
1. `pip install -r requirements.txt`, `.env.example` nach `.env` kopieren und `ANTHROPIC_API_KEY` eintragen.
2. LinkedIn-App auf https://www.linkedin.com/developers/ anlegen, Produkte "Share on LinkedIn" und
   "Sign In with LinkedIn using OpenID Connect" aktivieren, Redirect-URL `http://localhost:8765/callback`,
   Client-ID/-Secret in `.env`. Dann einmalig `python -m linkedin_agent auth`.
3. `config.yaml` anpassen (Stil, Themen, RSS-Feeds).

## Ablauf
```
python -m linkedin_agent draft                              # Entwürfe aus RSS + Themen
python -m linkedin_agent draft --topic "KI" --notes "..."   # Entwurf aus eigenen Stichpunkten
python -m linkedin_agent review                             # freigeben / per Anweisung überarbeiten / verwerfen
python -m linkedin_agent publish                            # freigegebene Posts veröffentlichen
```
Es wird nie ohne deine Freigabe gepostet. Automatisierung per Browser/Scraping ist bewusst nicht enthalten (LinkedIn-AGB).
