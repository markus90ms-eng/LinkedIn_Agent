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

## Weboberfläche (Alltag)
Doppelklick auf `start_assistent.bat` (oder `py -3.13 -m linkedin_agent web`). Der Browser öffnet sich auf
http://127.0.0.1:8501 und zeigt den nächsten Post: bearbeiten, überarbeiten, neu generieren, verwerfen oder
"Jetzt posten". "Neue Entwürfe erzeugen" füllt die Warteschlange. Läuft nur lokal, solange das Fenster offen ist.

## Bilder zu den Posts
In der Weboberfläche: "Bild erstellen". Claude setzt aus geprüften Bausteinen (Figuren, Laptop, Büro, Laden, Lupe, Karten, Code-Fenster ...) eine passende Illustration zusammen
(SVG) und schreibt die Bildidee dazu, die unter der Vorschau steht. Der Hook steht als Text
darunter. Optional steht unten ein Name (`image_footer: Dein Name` in `config.yaml`, standardmäßig aus). Farbwelt (7 Stück, darunter eine helle) und Bildaufteilung wechseln bei jedem Bild,
nie dieselbe Farbwelt wie bei den letzten Bildern. "Bild neu erstellen" zeichnet ein anderes Motiv. Der Post-Text wird immer
komplett veröffentlicht, das Bild hängt daran (Haken "Bild mitposten"). Die Umwandlung in PNG passiert im Browser, es wird
nichts zusätzlich installiert. Das SVG von Claude wird vorher bereinigt (keine Skripte, Links oder Fremdbilder).

## Eigenes Bild hochladen
In der Weboberfläche beim Post auf "Eigenes Bild hochladen" klicken (PNG, JPG oder WebP). Große Fotos werden im Browser auf
höchstens 2048 Pixel verkleinert, die Vorschau erscheint, optional eine Bildbeschreibung für Screenreader eintragen.
Mit dem Haken "Bild mitposten" wird das Bild zusammen mit dem Text veröffentlicht. "Bild entfernen" löscht es wieder.
