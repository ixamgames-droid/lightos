"""STAB-41: Kindprozess fuer den Nachstell-Test „n-ter Dialog stuerzt ab“.

Laeuft NUR als eigener Prozess (aufgerufen von
``tests/test_stab41_dialoge_freigeben.py``), damit ein nativer Absturz den
Testlauf nicht mitreisst. Baut in einer Sandbox
(``tools/anleitungsbilder/sandbox.py``: alle Datenpfade in einen Wegwerf-
Ordner, kein Ausgabe-Thread, kein MIDI, keine Web-Remote) das echte
Hauptfenster, oeffnet die Dialoge ueber die echten App-Methoden
(``MainWindow._open_…``) mehrfach nacheinander und schliesst jedes neue
Fenster per Timer mit ``reject()`` bzw. ``close()`` — wie der Klick-Test vom
16.11.2026. Anders als der Klick-Test raeumt dieses Skript NICHT selbst auf
(kein ``deleteLater``, keine erzwungene GC): die App muss ihre Dialoge selbst
freigeben.

Ausgabe (stdout, je eine Zeile):
  ``NACH <name> KINDER <n>``  — QDialog-Nachfahren des Hauptfensters
  ``AUSNAHME <text>``          — Python-Ausnahme in einem Slot
  ``ERGEBNIS ok <dialoge> <zuwachs> <ausnahmen>``

Aufruf: ``python tests/_stab41_dialog_kind.py <basis> <runden> [oeffner,…]``
"""
from __future__ import annotations

import os
import sys
import time

HIER = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HIER)
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, REPO)

from anleitungsbilder import sandbox  # noqa: E402  (importiert kein src)

# Die Dialoge des Klick-Tests (Reihenfolge wie dort) — alle ueber die echte
# Methode des Hauptfensters.
OEFFNER = (
    "_open_osc_einstellungen",
    "_open_output_config",
    "_open_channel_modifiers",
    "_open_input_profile_editor",
    "_open_gesten_dialog",
    "_tastenkuerzel_zeigen",
    "_validate_show",
    "_open_fixture_editor",
    "_open_profil_auswahl",
    "_open_music_window",
    "_new_show",
)


def main() -> int:
    basis = sys.argv[1]
    runden = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    oeffner = tuple(sys.argv[3].split(",")) if len(sys.argv) > 3 else OEFFNER
    sb = sandbox.einrichten(basis=basis)
    # Was die Test-conftest zusaetzlich hart umlenkt — hier ebenso.
    arbeit = sb.pfade["cwd"]
    os.environ["LIGHTOS_KEIN_USB"] = "1"
    os.environ["LIGHTOS_LIZENZ_TESTLAUF"] = "1"
    os.environ.pop("LIGHTOS_LIZENZ", None)
    os.environ.pop("LIGHTOS_ECHTE_AUSGABE", None)
    os.environ["LIGHTOS_OSC_ZUORDNUNGEN"] = os.path.join(arbeit, "osc_zuordnungen.json")
    os.environ["LIGHTOS_DMX_FERNSTEUERUNG"] = os.path.join(arbeit, "fernsteuerung.json")

    from PySide6.QtCore import QCoreApplication, QEvent, QTimer, Qt
    from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMenu
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    app = QApplication(["lightos-stab41"])
    app.setApplicationName("LightOS")
    sandbox.selbstpruefung(sb)
    sandbox.nebenwirkungen_abschalten()
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
    QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")

    ausnahmen: list[str] = []

    def haken(typ, wert, tb):
        ausnahmen.append(f"{typ.__name__}: {wert}")
        print(f"AUSNAHME {typ.__name__}: {wert}", flush=True)
    sys.excepthook = haken

    from src.ui.main_window import MainWindow
    win = MainWindow(kiosk=False, touch=False)
    win.resize(1366, 768)
    win.show()

    def pump(s: float) -> None:
        ende = time.monotonic() + s
        while True:
            app.processEvents()
            # wie die Hauptschleife der App: zurueckgestellte Loeschungen
            # (deleteLater) zustellen — sonst liefen sie hier nie.
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            if time.monotonic() >= ende:
                break
            time.sleep(0.01)

    pump(0.5)

    def kinder() -> int:
        return len(win.findChildren(QDialog))

    gesehen: set[int] = set()
    vorher: set[int] = set()

    def schliesser():
        for w in app.topLevelWidgets():
            if not w.isVisible() or w is win or id(w) in vorher or id(w) in gesehen:
                continue
            typ = w.windowType()
            if isinstance(w, QMenu) or typ in (Qt.WindowType.ToolTip, Qt.WindowType.Popup):
                continue
            gesehen.add(id(w))
            # wie der Klick-Test: kurz stehen lassen, dann schliessen
            QTimer.singleShot(150, w.reject if isinstance(w, QDialog) else w.close)

    timer = QTimer()
    timer.setInterval(30)
    timer.timeout.connect(schliesser)
    timer.start()

    dialoge = 0
    kinder_start = kinder()
    kinder_max = kinder_start
    print(f"START KINDER {kinder_start}", flush=True)
    for runde in range(runden):
        for name in oeffner:
            gesehen.clear()
            vorher.clear()
            vorher.update(id(w) for w in app.topLevelWidgets() if w.isVisible())
            print(f"OEFFNE {runde} {name}", flush=True)
            getattr(win, name)()
            dialoge += 1
            # nicht-modale Fenster (Musik) schliessen lassen
            ende = time.monotonic() + 2.0
            while time.monotonic() < ende:
                pump(0.05)
                offen = [w for w in app.topLevelWidgets()
                         if id(w) in gesehen and w.isVisible()]
                if gesehen and not offen:
                    break
            pump(0.05)
            n = kinder()
            kinder_max = max(kinder_max, n)
            print(f"NACH {name} KINDER {n}", flush=True)
        # Ansicht wechseln -> _refresh_undo_labels (Nebenbefund)
        for k in (1, 0):
            win._stack.setCurrentIndex(k)
            pump(0.05)
    timer.stop()
    print(f"ERGEBNIS ok {dialoge} {kinder_max - kinder_start} {len(ausnahmen)}",
          flush=True)
    sys.stdout.flush()
    os._exit(0)  # Abbau des Hauptfensters ist nicht Gegenstand dieses Tests


if __name__ == "__main__":
    sys.exit(main())
