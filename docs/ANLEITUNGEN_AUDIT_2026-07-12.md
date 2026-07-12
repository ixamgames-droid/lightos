# Anleitungen-/Bild-Audit — 2026-07-12 (DOC-10)

Automatisierter Check aller Doku-Bild-Referenzen + gezielte Auffrischung. Baut auf
[ANLEITUNGEN_AUDIT_2026-06-19.md](ANLEITUNGEN_AUDIT_2026-06-19.md) /
[…20.md](ANLEITUNGEN_AUDIT_2026-06-20.md) auf.

## Methode

[`tools/check_doc_images.py`](../tools/check_doc_images.py) durchsucht **alle** `docs/**.md`
+ `README.md` nach Bild-Referenzen — Markdown `![alt](pfad)` **und** HTML `<img src="…">` —
und prüft, ob der (relativ zur .md-Datei aufgelöste) Pfad existiert. Externe (`http(s)`,
`data:`) und **auskommentierte** (`<!-- … -->`) Referenzen werden übersprungen.

```bash
python tools/check_doc_images.py          # Report
python tools/check_doc_images.py --list-ok # + OK-Zähler je Datei
```

## Ergebnis

| Kennzahl | Wert |
|---|---|
| Geprüfte Bild-Referenzen | **248** |
| Dateien mit Bildern | 69 |
| Tote Links **vorher** | 5 |
| Tote Links **nachher** | **0** ✅ |

### Behoben — Pfad-Bug (kein fehlendes Bild)

`docs/anleitung_hochzeit_komplett/mini_gruenes_lauflicht/ANLEITUNG.md` referenzierte 5 Bilder
als `img/mini_gruenes_lauflicht/…` — die Dateien liegen aber eine Ebene höher im geteilten
Ordner `../img/mini_gruenes_lauflicht/` (wie bei den Schwester-Mini-Anleitungen). Alle 5
Referenzen (`01_bank1.png`, `04_solid_gruen.png`, `05_bank2.png`, `06_chase_frame.png`,
`gruenes_lauflicht.gif`) auf `../img/…` korrigiert — **keine neuen Screenshots nötig**, die
Bilder existierten bereits.

### Keine Aktion — auskommentierte Platzhalter

Zwei ursprünglich als „tot" gemeldete Referenzen (`ANLEITUNG.md` → `programmer_helper.png`,
`ANLEITUNG_MUSIK_SYNC.md` → `03_autoshow_fuer_lied.png`) stehen in HTML-Kommentaren
(`<!-- … -->`) — bewusste, nicht gerenderte Platzhalter. Der Checker ignoriert Kommentare;
kein Handlungsbedarf.

## Dauerhaftes Gate

Neu: [`tests/test_doc_images.py`](../tests/test_doc_images.py) lässt das Test-Gate rot werden,
sobald eine Anleitung/README ein nicht existierendes Bild referenziert (Pfad-Tippfehler oder
gelöschtes Bild). Damit bleibt „tote Bild-Links = 0" dauerhaft erzwungen.

## Offen (separater Folge-Schritt)

Der Checker fängt **fehlende** Bilder, nicht **veraltete** (Screenshot zeigt eine ältere
UI-Version). Ein Abgleich Screenshot ↔ aktuelle UI erfordert eine Live-Sichtung (Computer-Use)
und wird als eigener Schritt geführt (DOC-10, Teil b). Neu hinzugekommene 3D-Modell-Bilder:
[FIXTURE_3D_GALLERY.md](FIXTURE_3D_GALLERY.md) (DOC-11).
