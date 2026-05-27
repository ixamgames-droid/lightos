"""Touch / Virtual-Keyboard-Unterstützung für Windows-Tablet-Bedienung.

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
        le.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        if not _touch_mode:
            le.setInputMethodHints(Qt.InputMethodHint.ImhFormattedNumbersOnly)
    elif isinstance(widget, QSpinBox):
        le = widget.lineEdit()
        le.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        if not _touch_mode:
            le.setInputMethodHints(Qt.InputMethodHint.ImhDigitsOnly)
    elif isinstance(widget, QLineEdit):
        widget.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        if not _touch_mode:
            parent = widget.parent()
            if isinstance(parent, QDoubleSpinBox):
                widget.setInputMethodHints(Qt.InputMethodHint.ImhFormattedNumbersOnly)
            elif isinstance(parent, QSpinBox):
                widget.setInputMethodHints(Qt.InputMethodHint.ImhDigitsOnly)


# Globaler Stylesheet-Zusatz für Touch-Modus: nur Button-Breite anpassen,
# Höhe und Pfeil-Rendering bleiben bei Qt's Default → kein Layout-Bruch
# in schmalen Toolbars, und die Pfeile bleiben sichtbar.
_TOUCH_STYLESHEET = """
QSpinBox::up-button, QDoubleSpinBox::up-button {
    width: 22px;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    width: 22px;
}
"""


def _apply_touch_styles(app: QApplication) -> None:
    """Hängt den Touch-Stylesheet an die App, ohne bestehende Styles zu ersetzen."""
    existing = app.styleSheet() or ""
    if "/* lightos-touch-style */" in existing:
        return
    app.setStyleSheet(existing + "\n/* lightos-touch-style */\n" + _TOUCH_STYLESHEET)


def _enlarge_spinbox_buttons(widget: QObject) -> None:
    """Setzt PlusMinus-Style auf SpinBoxes; macht die Buttons noch deutlicher."""
    if isinstance(widget, QAbstractSpinBox):
        widget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)


# Fokus-Ursachen die NICHT durch Benutzerinteraktion entstehen (programmatisch)
_PROGRAMMATIC_REASONS = {
    Qt.FocusReason.TabFocusReason,
    Qt.FocusReason.BacktabFocusReason,
    Qt.FocusReason.ActiveWindowFocusReason,
    Qt.FocusReason.PopupFocusReason,
    Qt.FocusReason.ShortcutFocusReason,
    Qt.FocusReason.MenuBarFocusReason,
    Qt.FocusReason.NoFocusReason,
}

# Typen die als Zahlenfelder gelten → TabTip im --touch-Modus immer öffnen
_NUMBER_TYPES = (QSpinBox, QDoubleSpinBox)


class OskEventFilter(QObject):
    """App-weiter Event-Filter für Eingabefelder."""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if event.type() == QEvent.Type.FocusIn:
            if isinstance(obj, (QLineEdit, QSpinBox, QDoubleSpinBox)):
                # Immer konfigurieren → Windows erkennt das Feld als Text-Input
                _configure_widget(obj)

                # Im Touch-Modus (--touch): bei jedem Fokus auf ein Zahlenfeld
                # TabTip öffnen, außer bei rein programmatischem Fokus.
                if _touch_mode:
                    reason = getattr(event, "reason", lambda: None)()
                    is_number_field = isinstance(obj, _NUMBER_TYPES) or (
                        isinstance(obj, QLineEdit) and isinstance(obj.parent(), _NUMBER_TYPES)
                    )
                    if is_number_field and reason not in _PROGRAMMATIC_REASONS:
                        # Leicht verzögern: bei SpinBox kommt FocusIn manchmal
                        # *bevor* der interne QLineEdit das Edit-Fenster setzt;
                        # TabTip ignoriert den Aufruf sonst.
                        QTimer.singleShot(50, _show_osk)

        return False  # Event nicht verbrauchen


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

    _touch_mode = touch

    # Filter immer installieren (WA_InputMethodEnabled braucht kein Touch-Modus)
    _filter_instance = OskEventFilter(app)
    app.installEventFilter(_filter_instance)
    app._touch_keyboard_filter = _filter_instance  # type: ignore[attr-defined]

    # Im Touch-Modus große ±-Buttons auf allen SpinBoxes aktivieren
    # und Windows TabTip-AutoInvoke im Registry aktivieren.
    if touch:
        _apply_touch_styles(app)
        _enable_tabtip_autoinvoke()

    return touch


def is_touch_mode() -> bool:
    """True wenn Touch-Modus aktiv ist."""
    return _touch_mode
