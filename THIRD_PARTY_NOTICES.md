# Fremd-Komponenten in LightOS (Third-Party Notices)

LightOS selbst steht unter **keiner** Open-Source-Lizenz (Entscheidung des
Projektinhabers): alle Rechte vorbehalten, siehe [`LICENSE`](LICENSE). Diese Datei betrifft nur die **fremden** Dateien, die im Repo
mitgeliefert werden, und alles Fremde, das nur im Windows-Installationspaket steckt
(Python, Qt mit PySide6 und die Python-Pakete, die LightOS benutzt – ab dem Abschnitt
„Windows-Installationspaket“): Ihre Lizenzen erlauben die Weitergabe, verlangen aber,
dass Lizenztext und Urheberhinweise beiliegen. Die Lizenztexte stehen unter
[`licenses/`](licenses/); das Setup installiert diese Datei und den Ordner mit.

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

## Windows-Installationspaket — was außer LightOS darin steckt (LIZ-2)

Das Setup (`LightOS-Setup.exe`) enthält außer LightOS die Laufzeitumgebung Python, die
Oberflächen-Bibliothek Qt mit PySide6 und die Python-Pakete, die LightOS benutzt. Nichts
davon liegt im Repo: das Bauwerkzeug holt die fertigen Pakete beim Bauen von PyPI und packt
sie unverändert ein. LightOS ändert keine dieser Bibliotheken.

- **Woher die Liste stammt:** aus dem gebauten Paket, nicht aus `requirements.txt` – dort
  stehen weder die mittelbaren Abhängigkeiten noch Python selbst. Beim Bauen ordnet
  `packaging/windows/fremdkomponenten.py` jede Datei des Pakets ihrer Herkunft zu und
  vergleicht sie mit seiner Tabelle. Ein Paket ohne Eintrag, eine geänderte Lizenzangabe,
  ein fehlender Lizenztext, eine Datei unbekannter Herkunft: es entsteht kein Setup.
  `tests/test_liz2_fremdlizenzen_setup.py` hält Tabelle und diese Datei beisammen.
- **Versionen:** legt `requirements.txt` nicht fest. Welche Fassung in einem bestimmten Setup
  steckt, steht in diesem Setup selbst: `licenses/BUNDLE-KOMPONENTEN.txt` (beim Bauen
  erzeugt – Name, Version, Lizenz und Bezugsquelle jeder Komponente).
- **Lizenztexte im Setup:** unter `licenses/`. Die der Python-Pakete in genau der Fassung, die
  das eingebaute Paket selbst mitbringt (`licenses/pakete/<Name>-<Version>/`), Pythons
  eigener Text als `licenses/Python-LICENSE.txt`, die übrigen aus diesem Repo.
- **Python-Pakete** (Bezugsquelle des Quelltexts; die eingebaute Fassung kommt von
  <https://pypi.org>):

| Paket | Lizenz | Bezugsquelle |
|---|---|---|
| bidict | MPL-2.0 | <https://github.com/jab/bidict> |
| blinker | MIT | <https://github.com/pallets-eco/blinker> |
| cffi | MIT-0 | <https://github.com/python-cffi/cffi> |
| click | BSD-3-Clause | <https://github.com/pallets/click> |
| colorama | BSD-3-Clause | <https://github.com/tartley/colorama> |
| flask | BSD-3-Clause | <https://github.com/pallets/flask> |
| flask-socketio | MIT | <https://github.com/miguelgrinberg/Flask-SocketIO> |
| h11 | MIT | <https://github.com/python-hyper/h11> |
| importlib-resources | Apache-2.0 | <https://github.com/python/importlib_resources> |
| itsdangerous | BSD-3-Clause | <https://github.com/pallets/itsdangerous> |
| jinja2 | BSD-3-Clause | <https://github.com/pallets/jinja> |
| libusb-package | Apache-2.0 | <https://github.com/pyocd/libusb-package> |
| markupsafe | BSD-3-Clause | <https://github.com/pallets/markupsafe> |
| numpy | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | <https://github.com/numpy/numpy> |
| packaging | Apache-2.0 OR BSD-2-Clause | <https://github.com/pypa/packaging> |
| pycparser | BSD-3-Clause | <https://github.com/eliben/pycparser> |
| pyinstaller | GPL-2.0-or-later WITH Bootloader-exception | <https://github.com/pyinstaller/pyinstaller> |
| pyinstaller-hooks-contrib | Apache-2.0 | <https://github.com/pyinstaller/pyinstaller-hooks-contrib> |
| pyserial | BSD-3-Clause | <https://github.com/pyserial/pyserial> |
| pyside6-addons | LGPL-3.0-only | <https://download.qt.io/official_releases/QtForPython/pyside6/> |
| pyside6-essentials | LGPL-3.0-only | <https://download.qt.io/official_releases/QtForPython/pyside6/> |
| pyside6-pdf | LGPL-3.0-only | <https://download.qt.io/official_releases/QtForPython/pyside6/> |
| pyside6-webengine | LGPL-3.0-only | <https://download.qt.io/official_releases/QtForPython/pyside6/> |
| python-engineio | MIT | <https://github.com/miguelgrinberg/python-engineio> |
| python-osc | Unlicense | <https://github.com/attwad/python-osc> |
| python-rtmidi | MIT | <https://github.com/SpotlightKid/python-rtmidi> |
| python-socketio | MIT | <https://github.com/miguelgrinberg/python-socketio> |
| pyusb | BSD-3-Clause | <https://github.com/pyusb/pyusb> |
| setuptools | MIT | <https://github.com/pypa/setuptools> |
| shiboken6 | LGPL-3.0-only | <https://download.qt.io/official_releases/QtForPython/pyside6/> |
| simple-websocket | MIT | <https://github.com/miguelgrinberg/simple-websocket> |
| soundcard | BSD-3-Clause | <https://github.com/bastibe/SoundCard> |
| sqlalchemy | MIT | <https://github.com/sqlalchemy/sqlalchemy> |
| typing-extensions | PSF-2.0 | <https://github.com/python/typing_extensions> |
| werkzeug | BSD-3-Clause | <https://github.com/pallets/werkzeug> |
| wsproto | MIT | <https://github.com/python-hyper/wsproto> |

**bidict** steht unter der Mozilla Public License 2.0: wer eine ihrer Dateien ändert und
weitergibt, muss die geänderte Datei offenlegen. LightOS gibt bidict unverändert weiter; der
Quelltext liegt unter der genannten Adresse, der Lizenztext im Setup.

Die Abschnitte danach erklären, was über die Tabelle hinausgeht: Python, Qt mit PySide6
(LGPL), Chromium und FFmpeg in Qt, weitere enthaltene Bibliotheken und der Startlader.
Zu pyusb, libusb und libusb-package stehen eigene Abschnitte weiter oben.

## Python — Laufzeitumgebung (im Windows-Installationspaket)

- **Herkunft:** CPython für Windows (x64) von <https://www.python.org>, Quelltext
  <https://www.python.org/downloads/source/>. Eingebaut wird die Fassung, mit der das Setup gebaut
  wurde (die Pipeline nimmt 3.12); die genaue Nummer steht in `licenses/BUNDLE-KOMPONENTEN.txt`.
- **Urheber:** Copyright © 2001–2023 Python Software Foundation; All Rights Reserved
  (Stand Python 3.12; maßgeblich ist die beiliegende Lizenzdatei).
- **Lizenz:** Python Software Foundation License Version 2 (PSF-2.0). Der Text liegt dem
  Setup als `licenses/Python-LICENSE.txt` bei – eine Kopie der `LICENSE.txt` genau der
  Python-Installation, mit der gebaut wurde.
- **Darin enthalten:** Der Windows-Build von Python bringt eigene Fremdbibliotheken mit, als
  Dateien im Programmordner (`libcrypto-3.dll`, `libssl-3.dll` – OpenSSL, Apache-2.0;
  `libffi-8.dll` – libffi, MIT; `sqlite3.dll` – SQLite, gemeinfrei) oder eingebaut (bzip2,
  zlib, XZ, Expat). Die Hinweise zu bzip2, libffi und OpenSSL stehen in derselben
  `LICENSE.txt`; die vollständige Aufstellung führt die Python-Dokumentation
  („Licenses and Acknowledgements for Incorporated Software“,
  <https://docs.python.org/3.12/license.html>).

## Qt und PySide6 — Oberfläche, 3D-Fenster, Ton (im Windows-Installationspaket)

- **Herkunft:** Qt 6 (<https://www.qt.io>) und die Python-Anbindung PySide6 („Qt for Python“,
  <https://pyside.org>), als fertige Pakete von PyPI: `PySide6_Essentials`, `PySide6_Addons`,
  `PySide6_WebEngine`, `PySide6_Pdf`, `shiboken6`. Unverändert eingebaut.
- **Urheber:** Copyright © The Qt Company Ltd. and other contributors.
- **Lizenz:** GNU Lesser General Public License, Version 3 (LGPL-3.0-only) –
  [`licenses/LGPL-3.0.txt`](licenses/LGPL-3.0.txt). Die LGPLv3 ergänzt die GNU General
  Public License, Version 3, deren Text deshalb mit beiliegt:
  [`licenses/GPL-3.0.txt`](licenses/GPL-3.0.txt). Qt bietet die hier eingebauten Module
  wahlweise unter LGPLv3 oder GPL an; LightOS nutzt sie unter der LGPLv3.
- **Quelltext:** Qt – <https://download.qt.io/official_releases/qt/> (Ordner der eingebauten
  Version, z. B. `6.12/6.12.0/`); PySide6 und shiboken6 –
  <https://download.qt.io/official_releases/QtForPython/pyside6/> (Ordner `PySide6-<Version>-src`);
  Qt WebEngine – <https://code.qt.io/cgit/qt/qtwebengine.git/>. Die eingebaute Version steht
  in `licenses/BUNDLE-KOMPONENTEN.txt`.
- **Eingebaute Qt-Module:** Qt Core, Qt GUI, Qt Multimedia, Qt Network, Qt OpenGL, Qt PDF, Qt Positioning, Qt Print Support, Qt Qml, Qt Quick, Qt Quick Widgets, Qt Serial Port, Qt SVG, Qt WebChannel, Qt WebEngine, Qt Widgets.
  Als Dateien: `Qt6Core.dll`, `Qt6Gui.dll`, `Qt6Multimedia.dll`, `Qt6MultimediaWidgets.dll`, `Qt6Network.dll`, `Qt6OpenGL.dll`, `Qt6Pdf.dll`, `Qt6Positioning.dll`, `Qt6PrintSupport.dll`, `Qt6Qml.dll`, `Qt6QmlMeta.dll`, `Qt6QmlModels.dll`, `Qt6QmlWorkerScript.dll`, `Qt6Quick.dll`, `Qt6QuickWidgets.dll`, `Qt6SerialPort.dll`, `Qt6Svg.dll`, `Qt6WebChannel.dll`, `Qt6WebEngineCore.dll`, `Qt6WebEngineWidgets.dll`, `Qt6Widgets.dll`
  – dazu die Qt-Plugins unter `_internal/PySide6/plugins/` und `QtWebEngineProcess.exe`.
  Mehr nicht: von Qt kommt nur ins Setup, was LightOS oder eines dieser Plugins wirklich
  lädt (`packaging/windows/qt_umfang.py`). Der QML-Ordner von Qt entfällt ganz.
- **Nicht eingebaut – Module, die es nur unter der GPL gibt:** Qt Canvas Painter, Qt Charts, Qt CoAP, Qt Data Visualization, Qt Graphs, Qt GRPC, Qt HTTP Server, Qt Lottie Animation, Qt MQTT, Qt Network Authorization, Qt Qml Compiler, Qt Quick 3D, Qt Quick Timeline, Qt Virtual Keyboard, Qt Wayland Compositor.
  Diese Module bietet Qt in der Open-Source-Ausgabe **nicht** unter der LGPL an, sondern nur
  unter der GPLv3 (Qt-Dokumentation, „Qt Licensing“). LightOS benutzt keines davon; das
  Bauwerkzeug hätte einige trotzdem eingesammelt. Der Bau bricht ab, wenn eine Datei eines
  solchen Moduls oder ein Qt-Modul ohne Eintrag im Paket liegt.
- **Was die LGPL verlangt und wie LightOS es erfüllt:**
  - *Hinweis:* diese Datei und `licenses/BUNDLE-KOMPONENTEN.txt` liegen dem Setup bei und
    nennen Qt, PySide6 und die Lizenz.
  - *Lizenztexte:* LGPLv3 und GPLv3 liegen bei (siehe oben).
  - *Dynamisch gebunden:* jede Qt-Bibliothek ist eine eigene Datei unter
    `_internal/PySide6/` und wird zur Laufzeit geladen; nichts davon ist in `LightOS.exe`
    eingebaut. Das gilt auch für die Python-Teile von PySide6 und shiboken6 – sie liegen
    als lesbare `.py`-Dateien daneben, nicht im Archiv der exe.
  - *Austauschbar:* eine Datei lässt sich durch eine andere, schnittstellengleiche Fassung
    derselben Qt-Reihe ersetzen (gleicher Name, gleicher Ort) – LightOS lädt dann diese.
  - *Unverändert:* LightOS ändert weder Qt noch PySide6.
  - *Quelltext:* unter den oben genannten Adressen.

## Chromium — in Qt WebEngine (im Windows-Installationspaket)

- **Herkunft:** Qt WebEngine (für das 3D-Fenster) enthält den Browser-Kern Chromium
  (<https://www.chromium.org>); er steckt in `Qt6WebEngineCore.dll` und den Dateien unter
  `_internal/PySide6/resources/`. Quelltext in der von Qt verwendeten Fassung:
  <https://code.qt.io/cgit/qt/qtwebengine-chromium.git/>.
- **Urheber:** Copyright © The Chromium Authors und die Urheber der darin enthaltenen
  Bibliotheken.
- **Lizenz:** BSD-3-Clause für Chromium selbst; die enthaltenen Bibliotheken stehen unter
  eigenen Lizenzen, die strengste davon ist die LGPL 2.1
  ([`licenses/LGPL-2.1-libusb.txt`](licenses/LGPL-2.1-libusb.txt) ist derselbe Lizenztext).
  Die Aufstellung aller enthaltenen Bibliotheken mit ihren Lizenztexten führt die
  Qt-Dokumentation: „Qt WebEngine Licensing“,
  <https://doc.qt.io/qt-6/qtwebengine-licensing.html>.
- **Im Setup:** [`licenses/QtWebEngine-THIRD-PARTY.txt`](licenses/QtWebEngine-THIRD-PARTY.txt)
  – alle dort genannten Bibliotheken (125) mit Lizenz, Projektseite und Lizenztext, für
  Qt WebEngine 6.140.0 (Chromium 140), die Fassung in PySide6 6.12.0. Die PySide6-Pakete
  bringen diese Aufstellung nicht mit (auch nicht in `qtwebengine_resources.pak`); die Datei
  entsteht aus den Seiten der Qt-Dokumentation mit
  `packaging/windows/fremdlizenzen_sammeln.py webengine`. Der Bau liest die Version aus
  `Qt6WebEngineCore.dll` und bricht ab, wenn die Datei eine andere beschreibt.

## FFmpeg — in Qt Multimedia (im Windows-Installationspaket)

- **Herkunft:** FFmpeg (<https://ffmpeg.org>), von Qt gebaut und in den PySide6-Paketen
  mitgeliefert: `avcodec-*.dll`, `avformat-*.dll`, `avutil-*.dll`, `swresample-*.dll`,
  `swscale-*.dll` unter `_internal/PySide6/`. LightOS spielt und liest damit Tondateien. Der
  Quelltext liegt im Qt-Modul Qt Multimedia (`src/3rdparty/ffmpeg`, Archiv
  `qtmultimedia-everywhere-src-<Version>.tar.xz` unter der Qt-Adresse oben); Version und
  Lizenzen nennt die Qt-Dokumentation
  (<https://doc.qt.io/qt-6/qtmultimedia-attribution-ffmpeg.html>).
- **Urheber:** Copyright © 2000–2023 the FFmpeg developers.
- **Lizenz:** GNU Lesser General Public License, Version 2.1 oder später –
  [`licenses/LGPL-2.1-libusb.txt`](licenses/LGPL-2.1-libusb.txt) (derselbe Lizenztext);
  einzelne Teile unter BSD-, ISC- und MIT-Lizenzen. Nach Angabe von Qt enthalten die
  mitgelieferten Bibliotheken keine der wahlweisen GPL- oder LGPLv3-Teile von FFmpeg.
  Nachgelesen in den Dateien selbst (PySide6 6.12.0, `avutil`, `avcodec`): sie nennen als
  Lizenz „LGPL version 2.1 or later“, und ihre Bau-Angaben enthalten weder `--enable-gpl`
  noch `--enable-nonfree` noch `--enable-version3`.
- **LGPL:** wie bei Qt – eigene Dateien, zur Laufzeit geladen, austauschbar, unverändert.

## Weitere enthaltene Bibliotheken (im Windows-Installationspaket)

Sie kommen nicht als eigene Pakete, sondern stecken in Python, in den PySide6-Paketen oder
in numpy. Das Bauwerkzeug erkennt sie an ihren Dateien.

- **OpenBLAS** (in numpy, `numpy.libs/libscipy_openblas*.dll`) – BSD-3-Clause,
  <https://github.com/OpenMathLib/OpenBLAS>. Lizenztext und die Hinweise zu den darin
  enthaltenen Teilen (LAPACK, GCC-Laufzeitbibliothek mit Ausnahmeklausel) stehen in der
  Lizenzdatei von numpy (`licenses/pakete/numpy-<Version>/LICENSE.txt`).
- **Mesa llvmpipe** (`_internal/PySide6/opengl32sw.dll`) – OpenGL in Software, von Qt als
  fertige Datei beigelegt
  (<https://download.qt.io/development_releases/prebuilt/llvmpipe/windows/>); Mesa steht
  überwiegend unter der MIT-Lizenz (<https://docs.mesa3d.org/license.html>). Qt lädt die
  Datei nur, wenn Software-OpenGL verlangt wird. Die Datei in PySide6 6.12.0 ist Mesa
  11.2.2 mit statisch eingebundenem LLVM 3.6.2 (Versionskennung in der Datei; bis auf die
  Signatur gleich Qts Archiv `opengl32sw-64-mesa_11_2_2-signed_sha256.7z`). Lizenztexte:
  [`licenses/Mesa-opengl32sw.txt`](licenses/Mesa-opengl32sw.txt) – Mesas MIT-Lizenz, die
  Boost-Lizenz der C11-Thread-Emulation, die BSD-Lizenz von Jimenez's MLAA, die Lizenz von
  LLVM 3.6.2 (University of Illinois/NCSA) mit den Hinweisen zu regex und MD5; alles aus den
  Original-Quellarchiven (<https://archive.mesa3d.org/>, <https://releases.llvm.org/>),
  erzeugt mit `packaging/windows/fremdlizenzen_sammeln.py mesa`. Der Bau prüft die
  Mesa-Version der Datei gegen die Lizenzdatei.
- **Microsoft Visual C++ Laufzeit** (`VCRUNTIME140*.dll`, `MSVCP140*.dll`) – von Microsoft,
  **nicht** Open Source. Sie kommt ausschließlich aus der Python-Installation und aus den
  Paketen (PySide6, shiboken6, numpy), nie von anderswo auf dem Bau-Rechner – eine solche
  Datei unbekannter Herkunft bricht den Bau ab. Ihre Weitergabe richtet sich nach Microsofts
  Bedingungen für „Distributable Code“ (siehe den Abschnitt „Additional Conditions for this
  Windows binary build“ in `licenses/Python-LICENSE.txt`).
- **Nicht eingebaut – Universal C Runtime** (`ucrtbase.dll`, `api-ms-win-*.dll`): sie gehört
  zu Windows 10 und 11, und das Setup verlangt Windows 10. Das Bauwerkzeug hätte sie aus
  einem zufälligen Ordner des Bau-Rechners eingesammelt; sie entfällt, und der Bau wie der
  Selbsttest des fertigen Programms melden, wenn doch eine dabei ist.

## PyInstaller — Startlader von LightOS.exe (im Windows-Installationspaket)

- **Herkunft:** PyInstaller (<https://pyinstaller.org>, Quelltext
  <https://github.com/pyinstaller/pyinstaller>). Das Bauwerkzeug selbst wird nicht
  mitgeliefert – in `LightOS.exe` stecken nur sein Startlader und einige Lade-Hilfen.
- **Urheber:** Copyright © 2010–2023 PyInstaller Development Team; Copyright © 2005–2009
  Giovanni Bajo; aufbauend auf Arbeit von McMillan Enterprises, Inc. (© 2002).
- **Lizenz:** GPL 2.0 oder später mit Ausnahme für den Startlader („Bootloader Exception“):
  Die Ausnahme erlaubt ausdrücklich, den Startlader in eigene Programme einzubauen und diese
  ohne Auflagen aus der GPL weiterzugeben. Der Text liegt dem Setup bei
  (`licenses/pakete/pyinstaller-<Version>/COPYING.txt`); die Lade-Hilfen aus
  pyinstaller-hooks-contrib stehen unter Apache-2.0.

## pyserial — serielle Schnittstelle (im Windows-Installationspaket)

- **Herkunft:** pyserial (<https://github.com/pyserial/pyserial>), von PyPI, unverändert.
- **Urheber:** Copyright © 2001–2020 Chris Liechti.
- **Lizenz:** BSD 3-Clause –
  [`licenses/BSD-3-Clause-pyserial.txt`](licenses/BSD-3-Clause-pyserial.txt) (die Datei
  `LICENSE.txt` aus pyserial 3.5; das Paket selbst bringt keinen Lizenztext mit).
- **Wofür:** Enttec-Adapter und andere serielle DMX-Interfaces.

## python-osc — OSC-Nachrichten (im Windows-Installationspaket)

- **Herkunft:** python-osc (<https://github.com/attwad/python-osc>), von PyPI, unverändert.
- **Urheber:** attwad und Beitragende; in die Gemeinfreiheit entlassen.
- **Lizenz:** The Unlicense –
  [`licenses/Unlicense-python-osc.txt`](licenses/Unlicense-python-osc.txt) (die Datei
  `LICENSE.txt` aus python-osc 1.10.2; das Paket selbst bringt keinen Lizenztext mit).
- **Wofür:** OSC-Ein- und -Ausgang (z. B. TouchOSC).

## Controller-Bibliothek — eigene Arbeit, CC0

- **Ort:** `data/controller_library/` (ein JSON-Profil je Eingabegerät), im Repo und im
  Windows-Installationspaket.
- **Herkunft:** eigene Arbeit. Die Profile beschreiben, welche Taste welche MIDI-Note sendet –
  zusammengetragen aus öffentlich zugänglichen Herstellerunterlagen und aus dem LightOS-Code;
  jedes Profil nennt seine Quelle im Feld `source`. Es wurde kein fremder Datenbestand
  kopiert.
- **Lizenz:** CC0 (Verzicht auf alle Rechte) – so steht es im Feld `license` jedes Profils
  und in [`data/controller_library/README.md`](data/controller_library/README.md). Das ist
  die eine Stelle, an der LightOS eigene Dateien ausdrücklich freigibt.
- **Abgrenzung zu QLC+:** LightOS kann Eingabeprofile aus QLC+ (`.qxi`, Apache-2.0)
  **einlesen** (`tools/import_qlc_input_profile.py`). Solche Profile landen im Datenordner
  des Nutzers, tragen die Kennung `qlc_…`, die Quelle „QLC+-Inputprofil“ und die Lizenz
  „Apache-2.0 (QLC+ …)“. Im mitgelieferten Ordner liegt keines davon;
  `tests/test_liz2_fremdlizenzen_setup.py` prüft das.

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
