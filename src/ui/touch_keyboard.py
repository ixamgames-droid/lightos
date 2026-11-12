"""Touch / Virtual-Keyboard-Unterstützung (Tablet-Bedienung).

UI-112: Fingertipp in Zahlenfeld = app-eigener Ziffernblock (alle Systeme),
in Textfeld = app-eigene Bildschirmtastatur (Linux/macOS) bzw. System-
Tastatur TabTip (Windows) — siehe ``bildschirm_tastatur``.

Funktionsweise:
  - Der Event-Filter wird IMMER installiert und setzt WA_InputMethodEnabled
    auf alle QSpinBox/QLineEdit-Widgets, damit Windows die Touch-Tastatur
    automatisch erkennt.
  - Zusätzlich wird bei Touch-Modus (erkannt oder per --touch) die OSK
    explizit aufgerufen als Fallback.
"""
from __future__ import annotations
import sys
import os
import subprocess
from PySide6.QtWidgets import (QApplication, QSpinBox, QDoubleSpinBox, QLineEdit,
                                QAbstractSpinBox)
from PySide6.QtCore import Qt, QObject, QEvent, QTimer

_touch_mode: bool = False
_filter_instance: "OskEventFilter | None" = None


def detect_touch_screen() -> bool:
    """True wenn ein Touchscreen erkannt wird (Qt oder Windows-API)."""
    # Qt-Methode
    try:
        from PySide6.QtGui import QInputDevice
        for dev in QInputDevice.devices():
            if dev.type() == QInputDevice.DeviceType.TouchScreen:
                return True
    except Exception:
        pass

    # Windows-Fallback: GetSystemMetrics(SM_DIGITIZER)
    if sys.platform == "win32":
        try:
            import ctypes
            SM_DIGITIZER = 94
            NID_INTEGRATED_TOUCH = 0x40
            NID_EXTERNAL_TOUCH = 0x20
            result = ctypes.windll.user32.GetSystemMetrics(SM_DIGITIZER)
            if result & (NID_INTEGRATED_TOUCH | NID_EXTERNAL_TOUCH):
                return True
        except Exception:
            pass

    return False


_registry_prepared = False


def _enable_tabtip_autoinvoke() -> None:
    """Setzt den Registry-Schlüssel, der TabTip auch im Desktop-Modus
    automatisch beim Fokus auf Eingabefelder erscheinen lässt.
    Nur einmal pro Sitzung nötig.
    """
    global _registry_prepared
    if _registry_prepared or sys.platform != "win32":
        return
    _registry_prepared = True
    try:
        import winreg
        key_path = r"Software\Microsoft\TabletTip\1.7"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        except FileNotFoundError:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
        try:
            winreg.SetValueEx(key, "EnableDesktopModeAutoInvoke", 0, winreg.REG_DWORD, 1)
        finally:
            winreg.CloseKey(key)
    except Exception:
        pass


def _show_windows_osk() -> None:
    """Öffnet die Windows-Bildschirmtastatur (Windows 10 und 11)."""
    if sys.platform != "win32":
        return

    import ctypes

    # Versuch 1: vorhandenes TabTip-Fenster reaktivieren
    # Windows 10 1803+ ignoriert ShowWindow auf IPTip_Main_Window;
    # stattdessen WM_SYSCOMMAND SC_RESTORE senden.
    try:
        hwnd = ctypes.windll.user32.FindWindowW("IPTip_Main_Window", None)
        if hwnd:
            WM_SYSCOMMAND = 0x0112
            SC_RESTORE = 0xF120
            ctypes.windll.user32.SendMessageW(hwnd, WM_SYSCOMMAND, SC_RESTORE, 0)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            return
    except Exception:
        pass

    # Versuch 2: TabTip.exe starten
    tabtip_candidates = [
        os.path.join(
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            r"Common Files\microsoft shared\ink\tabtip.exe",
        ),
        os.path.join(
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            r"Common Files\microsoft shared\ink\tabtip.exe",
        ),
        r"C:\Program Files\Common Files\microsoft shared\ink\tabtip.exe",
    ]
    for path in tabtip_candidates:
        if os.path.exists(path):
            try:
                subprocess.Popen([path])
                return
            except OSError:
                pass

    # Versuch 3: klassische On-Screen-Keyboard als Fallback
    try:
        subprocess.Popen(["osk.exe"])
    except OSError:
        pass


def _show_osk() -> None:
    """Zeigt die On-Screen-Tastatur an."""
    try:
        im = QApplication.inputMethod()
        if im is not None:
            im.show()
    except Exception:
        pass
    _show_windows_osk()


def _configure_widget(widget: QObject) -> None:
    """Setzt WA_InputMethodEnabled und InputMethodHints.

    Wird IMMER aufgerufen (nicht nur im Touch-Modus), damit Windows
    QSpinBox als Texteingabefeld erkennt und die Tastatur ggf. von
    selbst öffnet.

    Hinweis zu SpinBox-Hints: Im Touch-Modus werden NumberPad-Hints
    NICHT gesetzt, weil TabTip auf manchen Windows-Versionen das
    Numeric-Layout unterdrückt statt anzeigt.  Ohne Hint zeigt es
    zuverlässig das Standard-Layout.
    """
    if isinstance(widget, QDoubleSpinBox):
        le = widget.lineEdit()
        # UI-112: im Touch-Modus uebernimmt der app-eigene Ziffernblock —
        # ohne Eingabemethode oeffnet Windows nicht zusaetzlich TabTip.
        le.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, not _touch_mode)
        if not _touch_mode:
            le.setInputMethodHints(Qt.InputMethodHint.ImhFormattedNumbersOnly)
    elif isinstance(widget, QSpinBox):
        le = widget.lineEdit()
        le.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, not _touch_mode)
        if not _touch_mode:
            le.setInputMethodHints(Qt.InputMethodHint.ImhDigitsOnly)
    elif isinstance(widget, QLineEdit):
        widget.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled,
                            not (_touch_mode and isinstance(widget.parent(), _NUMBER_TYPES)))
        if not _touch_mode:
            parent = widget.parent()
            if isinstance(parent, QDoubleSpinBox):
                widget.setInputMethodHints(Qt.InputMethodHint.ImhFormattedNumbersOnly)
            elif isinstance(parent, QSpinBox):
                widget.setInputMethodHints(Qt.InputMethodHint.ImhDigitsOnly)


# UI-112 (Touch-Audit C-02/D-16): Zahlenfelder am Finger. Die Pfeile waren
# 17x13 px (mit --touch 17x18 px) und lagen ohne Abstand uebereinander. Jetzt
# sitzt „−" links und „+" rechts neben der Zahl, jeder Knopf 40x36 px, der
# Abstand zwischen beiden ist das ganze Zahlenfeld. Gilt nur im Touch-Modus.
ZAHL_KNOPF_B = 40
ZAHL_KNOPF_H = 36


def _icon_url(name: str) -> str:
    try:
        from src.core.paths import programm_datei
        pfad = programm_datei("assets", "icons", name)
    except Exception:
        pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "assets", "icons", name)
    return pfad.replace("\\", "/")


def zahlenfeld_touch_qss(typen: str = "QSpinBox, QDoubleSpinBox") -> str:
    """Touch-Regeln fuer Zahlenfelder: grosse −/+-Knoepfe links/rechts.

    ``typen``: die Selektoren (kommagetrennt), z. B. ``"QSpinBox"`` fuer ein
    Widget-Stylesheet, das selbst nur ``QSpinBox`` stylt (Live-Spalte)."""
    t = [x.strip() for x in typen.split(",") if x.strip()]

    def sel(suffix: str) -> str:
        return ", ".join(f"{x}{suffix}" for x in t)

    plus, minus = _icon_url("zahl_plus.svg"), _icon_url("zahl_minus.svg")
    return (
        f"{sel('')} {{ min-height: {ZAHL_KNOPF_H}px; min-width: 64px; font-size: 15px; }}\n"
        f"{sel('::up-button')} {{ subcontrol-origin: border; "
        f"subcontrol-position: center right; width: {ZAHL_KNOPF_B}px; "
        f"height: {ZAHL_KNOPF_H}px; border-left: 1px solid #161616; }}\n"
        f"{sel('::down-button')} {{ subcontrol-origin: border; "
        f"subcontrol-position: center left; width: {ZAHL_KNOPF_B}px; "
        f"height: {ZAHL_KNOPF_H}px; border-left: none; border-right: 1px solid #161616; }}\n"
        f"{sel('::up-arrow')} {{ image: url({plus}); width: 18px; height: 18px; }}\n"
        f"{sel('::down-arrow')} {{ image: url({minus}); width: 18px; height: 18px; }}\n"
    )


#: UI-112 (D-16): Haken in den Seitenspalten (Live-Ansicht, Visualizer).
#: Die Spalten tragen ``objectName == "touchSpalte"``; das allgemeine Touch-
#: Stylesheet fuer Haken ueberall ist UI-119 (A-16).
SPALTE_TOUCH_QSS = (
    "#touchSpalte QCheckBox, #touchSpalte QRadioButton { min-height: 36px; spacing: 10px; }\n"
    "#touchSpalte QCheckBox::indicator, #touchSpalte QRadioButton::indicator "
    "{ width: 26px; height: 26px; }\n"
    "#touchSpalte QRadioButton::indicator { border-radius: 13px; }\n"
)


def touch_qss() -> str:
    """Alle Touch-Regeln dieses Moduls (Hauptfenster haengt sie an sein QSS)."""
    return zahlenfeld_touch_qss() + SPALTE_TOUCH_QSS


# Globaler Stylesheet-Zusatz fuer den Touch-Modus (App-weit, fuer Fenster ohne
# Hauptfenster als Eltern). Das Hauptfenster setzt ein eigenes Stylesheet, das
# den App-Stil ueberdeckt — es haengt deshalb ``touch_qss()`` selbst an.
_TOUCH_STYLESHEET = touch_qss()


def _apply_touch_styles(app: QApplication) -> None:
    """Hängt den Touch-Stylesheet an die App, ohne bestehende Styles zu ersetzen."""
    existing = app.styleSheet() or ""
    if "/* lightos-touch-style */" in existing:
        return
    app.setStyleSheet(existing + "\n/* lightos-touch-style */\n" + _TOUCH_STYLESHEET
                      + "\n/* lightos-touch-style-ende */\n")


def _remove_touch_styles(app: QApplication) -> None:
    """UI-112: Touch-Zusatz wieder entfernen (install(touch=False))."""
    existing = app.styleSheet() or ""
    a = existing.find("\n/* lightos-touch-style */\n")
    if a < 0:
        return
    ende = "\n/* lightos-touch-style-ende */\n"
    b = existing.find(ende, a)
    rest = existing[b + len(ende):] if b >= 0 else ""
    app.setStyleSheet(existing[:a] + rest)


def _enlarge_spinbox_buttons(widget: QObject) -> None:
    """Setzt PlusMinus-Style auf SpinBoxes; macht die Buttons noch deutlicher."""
    if isinstance(widget, QAbstractSpinBox):
        widget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)


# Typen die als Zahlenfelder gelten (Touch-Modus: Ziffernblock, UI-112)
_NUMBER_TYPES = (QSpinBox, QDoubleSpinBox)


class OskEventFilter(QObject):
    """App-weiter Event-Filter für Eingabefelder.

    UI-112: Im Touch-Modus oeffnet ein Fingertipp (Druck + Loslassen ohne Zug)
    in ein Zahlenfeld den app-eigenen Ziffernblock, in ein Textfeld die app-
    eigene Bildschirmtastatur (ausser unter Windows: dort die System-
    Tastatur). Maus und echte Tastatur oeffnen nie etwas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._druck_feld = None
        self._druck_pos = None

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        typ = event.type()
        if typ in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            if _touch_mode and isinstance(obj, QLineEdit):
                self._finger_tipp(obj, event, typ == QEvent.Type.MouseButtonPress)
        elif typ == QEvent.Type.FocusIn:
            if isinstance(obj, (QLineEdit, QSpinBox, QDoubleSpinBox)):
                # Immer konfigurieren → Windows erkennt das Feld als Text-Input
                _configure_widget(obj)
        return False  # Event nicht verbrauchen

    def _finger_tipp(self, feld: QLineEdit, event, druck: bool) -> None:
        try:
            from src.ui import ziehen_scrollen as zs
            if event.button() != Qt.MouseButton.LeftButton or not zs.ist_touch(event):
                return
            pos = event.globalPosition()
        except Exception:
            return
        if druck:
            self._druck_feld, self._druck_pos = feld, pos
            return
        start, gedrueckt = self._druck_pos, self._druck_feld
        self._druck_feld = self._druck_pos = None
        if start is None or gedrueckt is not feld:
            return
        d = pos - start
        if abs(d.x()) + abs(d.y()) > QApplication.startDragDistance() * zs.TOUCH_FAKTOR:
            return                      # Zug (Text markieren), kein Tipp
        from src.ui import bildschirm_tastatur as bt
        if bt.ziel_fuer(feld) is None:
            if (sys.platform != "win32" or isinstance(feld.parent(), QAbstractSpinBox)
                    or feld.isReadOnly() or not feld.isEnabled()):
                return
            QTimer.singleShot(50, _show_osk)      # Windows: System-Tastatur
            return
        # Nach dem Loslassen: das Feld hat Fokus und Cursor schon gesetzt.
        QTimer.singleShot(0, lambda f=feld: _oeffnen_wenn_gueltig(f))


def _oeffnen_wenn_gueltig(feld) -> None:
    try:
        from shiboken6 import isValid
        if not isValid(feld) or not feld.isVisible():
            return
        from src.ui import bildschirm_tastatur as bt
        bt.oeffnen(feld)
    except Exception as e:                       # nie die Bedienung abbrechen
        print(f"[touch_keyboard] Bildschirmtastatur: {e}")


def install(app: QApplication, touch: bool | None = None) -> bool:
    """Installiert Touch-Keyboard-Unterstützung.

    *touch*: True = erzwingen, False = deaktivieren, None = auto-erkennen.
    Gibt True zurück wenn Touch-Modus aktiv ist.

    Der Event-Filter (für WA_InputMethodEnabled) wird IMMER installiert,
    unabhängig vom Touch-Modus.
    """
    global _touch_mode, _filter_instance

    if touch is None:
        touch = detect_touch_screen()

    _touch_mode = bool(touch)

    # Filter immer installieren (WA_InputMethodEnabled braucht kein Touch-Modus)
    # — UI-111: nur einmal, auch wenn install() mehrfach laeuft.
    vorhanden = getattr(app, "_touch_keyboard_filter", None)
    if vorhanden is None:
        _filter_instance = OskEventFilter(app)
        app.installEventFilter(_filter_instance)
        app._touch_keyboard_filter = _filter_instance  # type: ignore[attr-defined]
    else:
        _filter_instance = vorhanden

    # Im Touch-Modus große ±-Buttons auf allen SpinBoxes aktivieren
    # und Windows TabTip-AutoInvoke im Registry aktivieren.
    if touch:
        _apply_touch_styles(app)
        _enable_tabtip_autoinvoke()
    else:
        _remove_touch_styles(app)

    return touch


def setze_touch_modus(an: bool) -> None:
    """UI-111: Touch-Zustand setzen, ohne Filter, Stylesheet oder Registry.

    Das Hauptfenster ruft das mit seinem ``touch``-Wert auf, BEVOR es seine
    Ansichten baut — so lesen Programmer, Laser-Bausteine und VC-Effekt-
    Editor denselben Zustand wie das Hauptfenster (vorher war
    ``is_touch_mode()`` immer False, weil ``install()`` nie lief)."""
    global _touch_mode
    _touch_mode = bool(an)


def is_touch_mode() -> bool:
    """True wenn Touch-Modus aktiv ist."""
    return _touch_mode
