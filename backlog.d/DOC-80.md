ID: DOC-80
Prioritaet: P2
Status: review
Titel: Schritt-fuer-Schritt-Anleitungen aus dem Live-Klicktest (32 Anleitungen, Bilder + GIFs) ins Repo

**Auftrag (23.11.2026):** Die im Live-Klicktest entstandenen Anleitungen so ins Repo einbauen, dass sie auf GitHub funktionieren und den Repo-Konventionen folgen; Grundlage fuer spaetere Erklaervideos.

**Geliefert:** Zehn Ordner `docs/anleitung_<thema>_schritte/` (Patch und Bibliothek, Gruppen, Matrix-Effekte, 2D-Buehne, Show-Dateien, Programmer, Virtual Console, Playback, Ausgabe/WLED, Web und Handy) mit zusammen 32 Anleitungen, je `ANLEITUNG.md` plus `img/` mit Einzelbildern und einem GIF je Ablauf. Eigene Ordner statt Einbau in vorhandene Anleitungen, weil Aufbau (GIF plus Bild je Schritt) und Bildherkunft (Aufnahme aus der echten App statt Bild-Werkzeug mit `bilder.json`) anders sind; jede Anleitung verlinkt die vertiefende vorhandene Anleitung. Neuer Abschnitt „Schritt für Schritt mit GIF“ in `docs/ANLEITUNGEN.md`, Verweis in der README. Texte gegen die heutige Oberflaeche geprueft; Stellen, die Klicktest-Befunde beschrieben oder umgingen (FM-82/83/85, VIZ-115/116, UI-145/146/147, VCB-52, OUT-85), neutral formuliert oder entfernt, dazu vier Bilder/GIFs, die nur einen Fehler zeigten. PNG auf 256 Farben, GIFs mit gemeinsamer Palette: 26 MB Rohmaterial auf 14,8 MB. Nur Deutsch (wie die uebrigen thematischen Anleitungen). Waechter `tests/test_doc80_schritt_anleitungen.py`.

**Offen:** Sobald die genannten Befunde behoben sind, Anleitungen und betroffene Bilder nachziehen (z. B. 3D-Ansicht, Tab-Vervollstaendigung in der Befehlszeile).
