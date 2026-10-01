"""DOC-16: Szenen abarbeiten — Fenster aufbauen, Szene herstellen, grabben,
markieren, als verlustarm verkleinerte PNG speichern, Manifest schreiben.

Eine Szene beschreibt NUR den Zustand (Sektion, Unter-Reiter, Vorbereitung,
Dialog, Markierungen, Ausschnitt). Wie das Fenster entsteht, wo die Bilder
landen und wie sie verkleinert werden, steht ausschliesslich hier — so sehen
alle Anleitungen gleich aus und eine neue Anleitung ist nur eine Szenen-Datei.

PySide6 wird hier importiert, ``src`` erst in :func:`lauf` (nach der Sandbox).
"""
from __future__ import annotations

import hashlib
import importlib
import io
import json
import os
import pkgutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable

PAKET = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(PAKET))
BREITE, HOEHE = 1600, 900

# Sektionsnamen wie in der Sektionsleiste (src/ui/main_window.py, ``sections``).
SEKTIONEN = ["Bühne", "Patchen", "Programmer", "Virtual Console",
             "Simple Desk", "Playback", "E/A", "BPM"]


class SzenenFehler(RuntimeError):
    """Eine Szene ist nicht (mehr) baubar — z. B. ein markierter Knopf fehlt."""


@dataclass
class Szene:
    """Eine Aufnahme.

    * ``name``        Dateistamm, Konvention ``NN_name`` -> ``NN_name.png``
    * ``sektion``     Index oder Name aus :data:`SEKTIONEN`
    * ``unterreiter`` Text des Unter-Reiters (``None`` = der erste)
    * ``vorher``      ``f(ui)`` stellt den Zustand her (Auswahl, Werte …)
    * ``nachher``     ``f(ui)`` raeumt nach der Aufnahme auf (z. B. ein
      laufendes Tempo stoppen, das sonst in spaeteren Bildern blinkt)
    * ``dialog``      ``f(ui) -> QWidget``: statt des Fensters diesen Dialog
      aufnehmen (nicht-modal geoeffnet, danach geschlossen)
    * ``marken``      Liste ``(finder, nummer, beschriftung[, lage])``; ``finder``
      ist ein objectName, ein Knopf-/Beschriftungstext oder ``f(ui) -> QWidget``;
      ``lage`` (``links``/``rechts``/``oben``/``unten``) ist nur ein Vorzug fuer
      den Nummernkreis — kollidiert er dort, sucht :mod:`marker` selbst einen
      freien Platz
    * ``ausschnitt``  ``None`` (ganzes Fenster), ``"stack"`` (nur die Sektion,
      ohne Menue/Statusleiste), ein Finder wie bei ``marken`` oder ein
      ``(x, y, b, h)``-Rechteck in Fensterkoordinaten
    * ``warte_s``     echte Wartezeit vor dem Grab (Timer-getriebene Widgets)
    * ``groesse``     Fenster- bzw. Dialoggroesse
    * ``braucht_gpu`` offscreen nicht darstellbar (3D) -> wird uebersprungen
    * ``beschriftungen`` Beschriftungen zusaetzlich ins Bild schreiben
    """
    name: str
    sektion: int | str = 0
    unterreiter: str | None = None
    titel: str = ""
    vorher: Callable | None = None
    nachher: Callable | None = None
    dialog: Callable | None = None
    marken: list = field(default_factory=list)
    ausschnitt: Any = None
    warte_s: float = 0.6
    groesse: tuple = (BREITE, HOEHE)
    braucht_gpu: bool = False
    beschriftungen: bool = False


# ── Szenen-Dateien finden ───────────────────────────────────────────────────

def anleitungen() -> list[str]:
    return sorted(m.name[len("szenen_"):] for m in pkgutil.iter_modules([PAKET])
                  if m.name.startswith("szenen_"))


def lade_szenen(anleitung: str):
    """(SZENEN, ziel_relativ) einer Anleitung. Ziel ist repo-relativ."""
    if anleitung not in anleitungen():
        raise SystemExit(f"[anleitungsbilder] Unbekannte Anleitung '{anleitung}'. "
                         f"Vorhanden: {', '.join(anleitungen()) or '-'}")
    mod = importlib.import_module(f"anleitungsbilder.szenen_{anleitung}")
    szenen = list(getattr(mod, "SZENEN"))
    namen = [s.name for s in szenen]
    doppelt = {n for n in namen if namen.count(n) > 1}
    if doppelt:
        raise SystemExit(f"[anleitungsbilder] {anleitung}: doppelte Szenennamen {sorted(doppelt)}")
    ziel = getattr(mod, "ZIEL", f"docs/{anleitung}/img")
    return szenen, ziel


# ── kleine UI-API fuer die Szenen ───────────────────────────────────────────

class UI:
    """Was eine Szene zum Herstellen ihres Zustands braucht."""

    def __init__(self, app, win, state, info):
        self.app, self.win, self.state, self.info = app, win, state, info

    def pump(self, sekunden: float = 0.0) -> None:
        """Events abarbeiten, auf Wunsch echte Zeit lang (Timer-Widgets).

        ``processEvents()`` ausserhalb von ``exec()`` fuehrt KEINE
        ``deleteLater``-Loeschungen aus. Ersetzte Zell-Widgets (Kurven-Combo der
        Cue-Tabelle) blieben dann an alter Stelle sichtbar im Bild — deshalb
        die DeferredDelete-Events hier ausdruecklich zustellen.
        """
        from PySide6.QtCore import QCoreApplication, QEvent

        def _einmal():
            self.app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        ende = time.monotonic() + max(0.0, sekunden)
        _einmal()
        while time.monotonic() < ende:
            _einmal()
            time.sleep(0.02)
        _einmal()

    # Navigation
    def sektion(self, sektion) -> None:
        idx = SEKTIONEN.index(sektion) if isinstance(sektion, str) else int(sektion)
        self.win._switch_section(idx)
        self.pump(0.1)

    def seite(self):
        return self.win._stack.currentWidget()

    def reiter(self, text: str) -> None:
        from PySide6.QtWidgets import QTabWidget
        seite = self.seite()
        kandidaten = ([seite] if isinstance(seite, QTabWidget) else []) + \
            seite.findChildren(QTabWidget)
        for tabs in kandidaten:
            for i in range(tabs.count()):
                if tabs.tabText(i).replace("&", "").strip() == text:
                    tabs.setCurrentIndex(i)
                    self.pump(0.1)
                    return
        vorhanden = sorted({t.tabText(i) for t in kandidaten for i in range(t.count())})
        raise SzenenFehler(f"Unter-Reiter '{text}' nicht gefunden (vorhanden: {vorhanden})")

    # Zustand
    def waehle(self, fids) -> None:
        self.state.set_selected_fids(list(fids))
        self.pump(0.1)

    def wert(self, fids, attribut: str, wert: int) -> None:
        for f in fids:
            self.state.set_programmer_value(int(f), attribut, int(wert))
        self.pump(0.1)

    # Widgets finden
    def finde(self, finder, wurzel=None):
        """Sichtbares Widget per objectName, Knopf-/Beschriftungstext oder Callable."""
        from PySide6.QtWidgets import QAbstractButton, QLabel, QWidget
        wurzel = wurzel or self.win
        if callable(finder):
            w = finder(self)
            if w is None:
                raise SzenenFehler(f"Finder {getattr(finder, '__name__', finder)!r} lieferte nichts")
            return w
        text = str(finder)
        for w in wurzel.findChildren(QWidget, text):
            if w.isVisible():
                return w
        # „…" und „..." gelten als gleich — im Code steht mal das eine, mal das andere.
        def _norm(t):
            return t.replace("&", "").replace("\u2026", "...").strip()
        ziel = _norm(text)
        for klasse in (QAbstractButton, QLabel):
            for w in wurzel.findChildren(klasse):
                if w.isVisible() and _norm(w.text()) == ziel:
                    return w
        raise SzenenFehler(
            f"Widget '{text}' nicht gefunden (weder objectName noch sichtbarer "
            "Knopf-/Beschriftungstext) — umbenannt? Szene anpassen.")


# ── Aufnahme ────────────────────────────────────────────────────────────────

def _rechteck_in(quelle, w):
    from PySide6.QtCore import QPoint, QRect
    if w is quelle:
        return QRect(0, 0, w.width(), w.height())
    if not quelle.isAncestorOf(w):
        raise SzenenFehler(f"Markiertes Widget {w.objectName() or type(w).__name__} "
                           "liegt nicht im aufgenommenen Bereich")
    return QRect(w.mapTo(quelle, QPoint(0, 0)), w.size())


def _hindernisse(quelle, versatz):
    """Beschriftete Bereiche im aufgenommenen Bild (fuer die Kreis-Lage).

    Eine zusammengesetzte Flaeche (Dialog als Bild ueber dem Fenster) hat
    keine echten Kinder; sie bringt ihre Bereiche als ``_doku_hindernisse``
    (Liste von ``QRect`` in Flaechen-Koordinaten) selbst mit.
    """
    from PySide6.QtCore import QPoint
    from . import marker
    v = QPoint(-versatz.x(), -versatz.y()) if versatz is not None else None
    aus = marker.hindernisse(quelle, versatz=v)
    aus += list(getattr(quelle, "_doku_hindernisse", None) or [])
    return aus


def aufnehmen(ui: UI, szene: Szene):
    """Stellt die Szene her und liefert ``(QPixmap, marken_info)``."""
    from PySide6.QtCore import QRect
    from . import marker
    ui.win.resize(*(szene.groesse if szene.dialog is None else (BREITE, HOEHE)))
    ui.sektion(szene.sektion)
    if szene.unterreiter:
        ui.reiter(szene.unterreiter)
    if szene.vorher:
        szene.vorher(ui)
    ui.pump(szene.warte_s)
    dlg = None
    try:
        if szene.dialog is not None:
            dlg = szene.dialog(ui)
            dlg.resize(*szene.groesse)
            dlg.show()
            ui.pump(max(0.5, szene.warte_s))
            quelle, versatz = dlg, None
        else:
            quelle, versatz = ui.win, None
            a = szene.ausschnitt
            if a == "stack":
                quelle = ui.seite()
            elif isinstance(a, tuple) and len(a) == 4:
                versatz = QRect(*a)
            elif a is not None:
                quelle = ui.finde(a)
        marken = []
        for eintrag in szene.marken:
            finder, nr = eintrag[0], eintrag[1]
            text = eintrag[2] if len(eintrag) > 2 else ""
            lage = eintrag[3] if len(eintrag) > 3 else None
            w = ui.finde(finder, wurzel=quelle if dlg is not None else ui.win)
            r = _rechteck_in(quelle, w)
            if versatz is not None:
                r.translate(-versatz.x(), -versatz.y())
            marken.append((r, nr, text, lage))
        pix = quelle.grab(versatz) if versatz is not None else quelle.grab()
        marker.zeichnen(pix, marken, beschriftungen=szene.beschriftungen,
                        hindernisse=_hindernisse(quelle, versatz) if marken else ())
        info = [{"nummer": nr, "beschriftung": t} for _r, nr, t, _l in marken]
        return pix, info
    finally:
        if dlg is not None:
            dlg.close()
            dlg.deleteLater()
            ui.pump(0.1)
        if szene.nachher:
            szene.nachher(ui)
            ui.pump(0.1)


def png_bytes(pix) -> bytes:
    """QPixmap -> verlustarm verkleinerte PNG (8-Bit-Palette, ohne Dithering).

    UI-Bilder haben wenige Flaechenfarben; 256 Palettenfarben ohne Dithering
    sehen aus wie das Original und landen bei 1600 x 900 unter 150 KB.
    """
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PIL import Image
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pix.toImage().save(buf, "PNG")
    buf.close()
    bild = Image.open(io.BytesIO(bytes(ba))).convert("RGB")
    pal = bild.quantize(colors=256, method=Image.Quantize.MEDIANCUT,
                        dither=Image.Dither.NONE)
    aus = io.BytesIO()
    pal.save(aus, "PNG", optimize=True)
    return aus.getvalue()


def schrift(win) -> str:
    """Tatsaechlich gerenderte Schrift (QSS-Wunsch -> Ersatz dieses Rechners)."""
    from PySide6.QtGui import QFontInfo
    from PySide6.QtWidgets import QLabel
    probe = next((w for w in win.findChildren(QLabel) if w.isVisible() and w.text()), win)
    gewuenscht = probe.font().family()
    echt = QFontInfo(probe.font()).family()
    return echt if echt == gewuenscht else f"{echt} (statt {gewuenscht})"


def fast_gleich(alt_pfad: str, neu: bytes, *, schwelle: int = 48,
               anteil: float = 0.0005) -> bool:
    """True, wenn sich das neue Bild vom vorhandenen nur unmerklich unterscheidet.

    Die Palette wird je Bild neu berechnet: ein einziger Pixel, der zwischen
    zwei Laeufen anders glimmt (gemessen: Lampenmitte in der 2D-Buehne),
    verschiebt die Palette und damit die md5 des ganzen Bildes. Damit ein
    Neu-Rendern nicht jedes Mal alle Bilder im git-Diff aendert, bleibt die
    alte Datei liegen, solange weniger als ``anteil`` der Pixel um mehr als
    ``schwelle`` (je Kanal, 0…255) abweichen.
    """
    from PIL import Image, ImageChops
    if not os.path.exists(alt_pfad):
        return False
    try:
        a = Image.open(alt_pfad).convert("RGB")
        b = Image.open(io.BytesIO(neu)).convert("RGB")
    except Exception:
        return False
    if a.size != b.size:
        return False
    diff = ImageChops.difference(a, b).convert("L").point(
        lambda v: 255 if v > schwelle else 0)
    return diff.histogram()[255] < anteil * a.size[0] * a.size[1]


def git_stand() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or "?"
    except Exception:
        return "?"


# ── Lauf ────────────────────────────────────────────────────────────────────

def lauf(auftraege, *, sb, pruefen: bool = False, ausgabe: str | None = None,
         nur: set | None = None) -> int:
    """``auftraege``: Liste ``(anleitung, szenen, ziel_relativ)``. Rueckgabe = Exit-Code.

    ``ausgabe`` ersetzt den Zielordner (alle Anleitungen darunter je in einen
    Unterordner) — fuer Tests und ``--pruefen``.
    """
    from . import sandbox
    import main as lo_main
    lo_main._setup_webengine_diagnostics()
    from PySide6.QtCore import QCoreApplication, Qt, qVersion
    from PySide6.QtWidgets import QApplication
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    app = QApplication.instance() or QApplication(["lightos-anleitungsbilder"])
    app.setApplicationName("LightOS")
    lo_main._install_font_substitutions()
    # Wie main.main(): Qt-Standardknoepfe (Yes/No/Cancel …) deutsch — sonst
    # zeigten die Bilder englische Knoepfe, die App aber deutsche (UI-64h).
    lo_main._install_qt_translator(app)

    pf = sandbox.selbstpruefung(sb)
    print("SANDBOX " + json.dumps(pf, sort_keys=True), flush=True)
    sandbox.nebenwirkungen_abschalten()

    t0 = time.time()
    from . import demo_show
    show_pfad, info = demo_show.bauen(sb.pfade["cwd"])
    from src.core.app_state import get_state
    from src.core.show.show_file import load_show
    from src.ui.main_window import MainWindow
    win = MainWindow(kiosk=False, touch=False)
    win.resize(BREITE, HOEHE)
    win.show()
    ui = UI(app, win, get_state(), info)
    ui.pump(0.5)
    ok, meldung = load_show(show_pfad)
    if not ok:
        raise SystemExit(f"[anleitungsbilder] Demo-Show laedt nicht: {meldung}")
    try:
        win._refresh_all_views()
    except Exception as e:
        print(f"[anleitungsbilder] refresh: {e}")
    # Falle aus der Probe: ohne diesen Aufruf bleibt die Cue-Tabelle leer.
    pv = getattr(win, "_playback_view", None)
    if pv is not None and hasattr(pv, "_refresh_stack_combo"):
        pv._refresh_stack_combo()
    ui.pump(0.5)
    print(f"[anleitungsbilder] Fenster + Demo-Show bereit in {time.time() - t0:.1f} s, "
          f"Schrift {schrift(win)}", flush=True)

    fehler = 0
    stand = git_stand()
    for anleitung, szenen, ziel_rel in auftraege:
        if ausgabe:
            ziel = os.path.join(ausgabe, anleitung)
        else:
            ziel = os.path.join(REPO, ziel_rel)
        os.makedirs(ziel, exist_ok=True)
        manifest_pfad = os.path.join(ziel, "bilder.json")
        alt = {}
        if os.path.exists(manifest_pfad):
            try:
                with open(manifest_pfad, encoding="utf-8") as f:
                    alt = {b["datei"]: b for b in json.load(f).get("bilder", [])}
            except Exception:
                alt = {}
        eintraege = dict(alt)
        for szene in szenen:
            if nur and szene.name not in nur:
                continue
            datei = f"{szene.name}.png"
            if szene.braucht_gpu and os.environ.get("QT_QPA_PLATFORM") == "offscreen":
                print(f"[anleitungsbilder] {anleitung}/{datei}: UEBERSPRUNGEN — braucht "
                      "eine GPU (3D/WebGL bleibt offscreen schwarz).", flush=True)
                continue
            try:
                pix, marken = aufnehmen(ui, szene)
                daten = png_bytes(pix)
            except SzenenFehler as e:
                print(f"[anleitungsbilder] {anleitung}/{datei}: FEHLER — {e}", flush=True)
                fehler += 1
                if not pruefen:
                    return 2
                continue
            pfad = os.path.join(ziel, datei)
            if fast_gleich(pfad, daten):
                with open(pfad, "rb") as f:
                    daten = f.read()
                hinweis = " (unveraendert)"
            else:
                with open(pfad, "wb") as f:
                    f.write(daten)
                hinweis = " (neu)" if datei not in alt else " (Inhalt geaendert)"
            md5 = hashlib.md5(daten).hexdigest()
            if pruefen:
                im_repo = os.path.join(REPO, ziel_rel, datei)
                if not os.path.exists(im_repo):
                    hinweis = f" (fehlt noch in {ziel_rel}/)"
                elif fast_gleich(im_repo, daten):
                    hinweis = " (wie im Repo)"
                else:
                    hinweis = " (weicht vom Stand im Repo ab — neu rendern?)"
            print(f"[anleitungsbilder] {anleitung}/{datei}: {pix.width()}x{pix.height()}, "
                  f"{len(daten) // 1024} KB{hinweis}", flush=True)
            eintraege[datei] = {
                "datei": datei, "szene": szene.name, "titel": szene.titel,
                "groesse": [pix.width(), pix.height()], "marken": marken,
                "md5": md5,
            }
        if not pruefen:
            manifest = {
                "anleitung": anleitung,
                "werkzeug": "tools/anleitungsbilder.py",
                "stand": stand,
                "schrift": schrift(win),
                "qt": qVersion(),
                "hinweis": "Pixelgleich nur auf demselben Rechner mit demselben "
                           "Schriftsatz; neu erzeugen mit "
                           f"'venv/bin/python tools/anleitungsbilder.py {anleitung}'.",
                "bilder": [eintraege[k] for k in sorted(eintraege)],
            }
            with open(manifest_pfad, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
                f.write("\n")
    return 1 if fehler else 0
