# Fremd-Komponenten in LightOS (Third-Party Notices)

LightOS selbst steht unter **keiner** Open-Source-Lizenz (Entscheidung des
Projektinhabers). Diese Datei betrifft die **fremden** Dateien, die im Repo
mitgeliefert werden, und – seit OUT-76 – die Bibliotheken für uDMX-Adapter, die
nur im Windows-Installationspaket stecken (pyusb, libusb, libusb-package): Ihre
Lizenzen erlauben die Weitergabe, verlangen aber, dass Lizenztext und
Urheberhinweise beiliegen. Die Lizenztexte stehen unter [`licenses/`](licenses/);
das Setup installiert diese Datei und den Ordner mit.

Neue fremde Dateien nur mit Eintrag hier — `tests/test_proc18_fremd_lizenzhinweise.py`
prüft, dass jede Datei in den unten genannten Ordnern aufgeführt ist.

**3D-Modelle sind eigene Arbeit (VIZ-66, 2026-10-02):** Bis dahin lagen unter
`src/ui/visualizer/assets/models/` 19 Modelldateien aus QLC+ (Apache-2.0). Sie sind
entfernt; alle Geräte- und Traversen-Körper im 3D-Visualizer entstehen im Code aus
three.js-Grundkörpern (`scene_src/fixtures/builders.js`, `scene_src/stage/stage_objects.js`).
Damit liefert LightOS keine Apache-2.0-Dateien mehr mit. Ein Wächter
(`tests/test_viz66_keine_fremden_modelle.py`) verhindert, dass wieder `.dae`/`.obj`-Dateien
ins Repo kommen.

## Geräte-Bibliothek

- **Ort:** `fixtures/bibliothek/` (eine JSON-Datei je Gerät, Format in
  [`fixtures/bibliothek/SCHEMA.md`](fixtures/bibliothek/SCHEMA.md)).
- **Herkunft je Datei:** steht im Pflichtfeld `herkunft` der Datei selbst
  (`art`, `lizenz`, bei fremden Vorlagen zusätzlich `urheber`, `original`, `geaendert`).
  Selbst geschriebene Profile (`lizenz: eigen`) sind keine fremden Dateien.
- **Aus QLC+ umgebaute Profile** (`herkunft.art: qlcplus`): Vorlage aus QLC+
  (<https://github.com/mcallegari/qlcplus>, `resources/fixtures/`), Copyright © Heikki
  Junnila, Massimo Callegari und die QLC+-Beitragenden (Urheber der einzelnen Datei in
  `herkunft.urheber`). Lizenz: Apache License 2.0 —
  [`licenses/Apache-2.0.txt`](licenses/Apache-2.0.txt). Die Dateien sind geändert
  (Apache-2.0 §4b): ins LightOS-Format umgebaut; was genau, steht in `herkunft.geaendert`.
- **Aus der Open Fixture Library umgebaute Profile** (`herkunft.art: ofl`): MIT-Lizenz.
  Der MIT-Lizenztext der Open Fixture Library wird mit dem ersten solchen Profil unter
  `licenses/` abgelegt und hier verlinkt — `tests/test_fm56_bibliothek_waechter.py`
  verlangt das.

## three.js — 3D-Bibliothek (r128)

- **Herkunft:** three.js (<https://github.com/mrdoob/three.js>), Release r128.
- **Urheber:** Copyright © 2010-2021 three.js authors.
- **Lizenz:** MIT — [`licenses/MIT-three.js.txt`](licenses/MIT-three.js.txt).
- **Dateien:**
  - `assets/vendor/three.min.js`
  - `src/ui/visualizer/three_local.js`

## Socket.IO-Client — Verbindung der Web-Remote (4.7.5)

- **Herkunft:** socket.io-client (<https://github.com/socketio/socket.io>), Version 4.7.5,
  Datei `dist/socket.io.min.js` aus dem npm-Paket
  (<https://registry.npmjs.org/socket.io-client/-/socket.io-client-4.7.5.tgz>), unverändert.
- **Urheber:** Copyright © 2014-2024 Guillermo Rauch.
- **Lizenz:** MIT — [`licenses/MIT-socket.io.txt`](licenses/MIT-socket.io.txt).
- **Dateien:**
  - `src/web/static/socket.io.min.js`
- **SHA-256:** `73eba16bc895fdfa454e27ecb80def31ede8d861f99e175ff93b110eabec044f`
  (`tests/test_web06_socketio_lokal.py` prüft die Bytes).
- **Warum im Repo:** Die Web-Remote läuft im lokalen Netz ohne Internet; die Seite lädt
  deshalb nichts von fremden Servern (WEB-06). Version passend zum Server
  (python-socketio 5.x / python-engineio 4.x, Socket.IO-Protokoll 5).

## pyusb — USB-Zugriff für uDMX-Adapter (im Windows-Installationspaket)

- **Herkunft:** pyusb (<https://github.com/pyusb/pyusb>), Version laut `requirements.txt`
  (mindestens 1.2.1). Liegt **nicht im Repo**: das fertige Python-Paket kommt beim Bauen des
  Windows-Setups von PyPI (<https://pypi.org/project/pyusb/>) und wird unverändert
  mitgeliefert (Python-Modul `usb`).
- **Urheber:** Copyright © 2009–2017 Wander Lairson Costa; Copyright © 2009–2021 PyUSB
  contributors.
- **Lizenz:** BSD 3-Clause — [`licenses/BSD-3-Clause-pyusb.txt`](licenses/BSD-3-Clause-pyusb.txt).
- **Wofür:** die Ausgabe-Art „uDMX (USB)“ (OUT-68, OUT-76). Eine Bibliothek, kein Treiber.

## libusb — USB-Bibliothek unter pyusb (im Windows-Installationspaket)

- **Herkunft:** libusb (<https://libusb.info>, Quelltext
  <https://github.com/libusb/libusb>). Liegt **nicht im Repo**: die fertige Bibliothek
  `libusb-1.0.dll` kommt beim Bauen des Windows-Setups aus dem Python-Paket libusb-package
  (siehe nächster Abschnitt) und wird unverändert mitgeliefert. Welche Fassung von libusb
  das ist, sagt die Versionsnummer von libusb-package: `1.0.30.0` enthält libusb 1.0.30
  (Quelltext dieser Fassung: <https://github.com/libusb/libusb/releases/tag/v1.0.30>).
- **Urheber:** Copyright © 2001 Johannes Erdfelt; © 2007–2009 Daniel Drake; © 2010–2012
  Peter Stuge; © 2008–2016 Nathan Hjelm; © 2009–2013 Pete Batard; © 2009–2013 Ludovic
  Rousseau; © 2010–2012 Michael Plante; © 2011–2013 Hans de Goede; © 2012–2013 Martin
  Pieuchot; © 2012–2013 Toby Gray; © 2013–2018 Chris Dickens und weitere Beitragende
  (Datei `AUTHORS` im Quelltext).
- **Lizenz:** GNU Lesser General Public License, Version 2.1 oder später —
  [`licenses/LGPL-2.1-libusb.txt`](licenses/LGPL-2.1-libusb.txt) (die Datei `COPYING` aus
  libusb 1.0.30).
- **Was die LGPL verlangt und wie LightOS es erfüllt:**
  - *Dynamisch gebunden:* libusb liegt als eigene Datei im Programmordner
    (`_internal/libusb_package/libusb-1.0.dll`) und wird zur Laufzeit geladen; sie ist nicht
    in `LightOS.exe` eingebaut. Das Bauwerkzeug legt dieselbe Datei ein zweites Mal direkt
    nach `_internal/`; geladen wird die im Ordner `libusb_package`.
  - *Austauschbar:* die Datei lässt sich durch eine andere, schnittstellengleiche Fassung
    von libusb 1.0 ersetzen (gleicher Name, gleicher Ort) – LightOS lädt dann diese.
  - *Unverändert:* LightOS ändert libusb nicht.
  - *Quelltext:* unter den oben genannten Adressen; der Lizenztext liegt bei.
- **Wofür:** wie pyusb. Eine Bibliothek, kein Treiber – einen Treiber liefert und installiert
  LightOS nicht.

## libusb-package — libusb als Python-Paket (im Windows-Installationspaket)

- **Herkunft:** libusb-package (<https://github.com/pyocd/libusb-package>), Version laut
  `requirements.txt` (mindestens 1.0.26). Liegt **nicht im Repo**: kommt beim Bauen des
  Windows-Setups von PyPI (<https://pypi.org/project/libusb-package/>) und wird unverändert
  mitgeliefert. Es bringt die Bibliothek aus dem vorigen Abschnitt mit und findet sie zur
  Laufzeit; es selbst braucht das Python-Paket importlib_resources
  (<https://github.com/python/importlib_resources>, ebenfalls Apache License 2.0).
- **Urheber:** Copyright © 2021–2023 Chris Reed; Copyright © 2022 Mitchell Kline.
- **Lizenz:** Apache License 2.0 — [`licenses/Apache-2.0.txt`](licenses/Apache-2.0.txt).

## Apache License 2.0 — für Geräteprofile auf QLC+-Basis

- **Lizenztext:** [`licenses/Apache-2.0.txt`](licenses/Apache-2.0.txt).
- **Wofür:** Die eigene Geräte-Bibliothek (FM-56, `fixtures/bibliothek/`) darf Profile enthalten,
  die aus QLC+ (Copyright © Heikki Junnila, Massimo Callegari und die QLC+-Beitragenden)
  übernommen und von LightOS überarbeitet wurden. Jede solche Datei nennt ihre Herkunft,
  den Urheber, die Originaldatei und die Änderungen selbst (Feld `herkunft`).

## Geräte-Bibliothek zum Herunterladen (nicht im Repo, FM-53)

LightOS kann eine freie Fixture-Bibliothek **auf Nachfrage** herunterladen
(Erststart-Frage bzw. **Datenbank → Geräte-Bibliothek herunterladen...**). Diese Dateien liegen **nicht** im Repo
und werden nicht mit LightOS weitergegeben; sie kommen direkt von der Quelle auf
den Rechner des Nutzers.

- **QLC+ Fixture-Bibliothek** — GitHub-Archiv einer festen QLC+-Version
  (<https://github.com/mcallegari/qlcplus>), verwendet werden nur die `.qxf`-Dateien.
  Lizenz: Apache License 2.0 — [`licenses/Apache-2.0.txt`](licenses/Apache-2.0.txt).
- **Open Fixture Library** — QLC+-Export (<https://open-fixture-library.org>).
  Lizenz: MIT (<https://github.com/OpenLightingProject/open-fixture-library/blob/master/LICENSE>);
  einzelne Profile stammen ihrerseits aus QLC+ (Apache-2.0).

**Herkunft und Lizenz je Profil** speichert LightOS beim Import in der Tabelle
`profil_herkunft` der Geräte-Datenbank: Quelle, Lizenz, Lizenz-Link, Archiv-Adresse,
SHA-256 und Zeitpunkt. Eigene und schon vorhandene Profile bleiben unberührt.
Details: [`docs/FIXTURE_SOURCES.md`](docs/FIXTURE_SOURCES.md).
