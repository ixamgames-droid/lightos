"""Eingebettetes 3D-View-Widget (Three.js) zur Wiederverwendung.

Im Gegensatz zum vollen ``VisualizerWindow`` (Stage-Builder, Tabs, Toolbar)
ist dies ein schlankes Widget: WebView + die wiederverwendbare
``VisualizerBridge`` + DMX-Push-Timer. Es wird in der **Live View** eingebettet,
damit man dort zwischen 2D-Top-Down und 3D umschalten kann, ohne ein eigenes
Fenster zu oeffnen.

Modus: Ansehen (Kamera) + Fixtures per Drag bewegen. Buehne/Trassen bauen bleibt
bewusst dem dedizierten ``VisualizerWindow`` vorbehalten.

Positions-Quelle ist die Live View: Beim Anzeigen werden die in der Live View
platzierten Strahler automatisch ins 3D uebernommen (``requestFixtures`` ->
``_sync_positions_from_live_view`` in der Bridge); eine 3D-Verschiebung schreibt
X/Z dort zurueck.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSlider,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import Qt, QTimer

from src.core.app_state import get_state, get_channels_for_patched
from src.core.stage.stage_definition import (
    load_stage, get_default_simple, DEFAULT_PRESETS,
)
from src.ui.visualizer.visualizer_window import (
    VisualizerBridge, load_stage_html, install_render_crash_guard,
)
from src.ui.weak_slots import weak_slot_fwd


class Visualizer3DView(QWidget):
    """Leichtgewichtige 3D-Ansicht zum Einbetten (z.B. in die Live View)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = get_state()
        self._loaded = False
        self._edit_mode = "view"          # 'view' | 'edit' (kein 'stage')
        self._setup_ui()
        self._setup_channel()
        self._dmx_timer = QTimer(self)
        self._dmx_timer.timeout.connect(self._push_dmx_updates)

    # ── UI ──────────────────────────────────────────────────────────────────
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QHBoxLayout()
        bar.setContentsMargins(6, 4, 6, 4)
        bar.setSpacing(6)
        _style = (
            "QPushButton { background:#1a2a3a; color:#9acbff; border:1px solid #2a4a6a;"
            " border-radius:4px; padding:6px 10px; font-size:12px; }"
            " QPushButton:hover { background:#223344; color:#bfe0ff; }"
            " QPushButton:checked { background:#1f6feb; color:#fff; border-color:#1f6feb; }"
        )

        self._btn_move = QPushButton("✋ Ansehen")
        self._btn_move.setCheckable(True)
        self._btn_move.setMinimumHeight(30)
        self._btn_move.setStyleSheet(_style)
        self._btn_move.setToolTip(
            "Aus: nur Kamera drehen/zoomen (Ansehen).\n"
            "An: Strahler per Drag im 3D verschieben (X/Z wandert ins Bühnen-Layout).\n"
            "Bühne/Trassen bearbeiten: dafür das separate 3D-Editor-Fenster nutzen."
        )
        self._btn_move.toggled.connect(self._on_move_toggled)
        bar.addWidget(self._btn_move)

        btn_cam = QPushButton("⌖ Kamera")
        btn_cam.setMinimumHeight(30)
        btn_cam.setStyleSheet(_style)
        btn_cam.setToolTip("Kamera zurücksetzen")
        btn_cam.clicked.connect(self._reset_camera)
        bar.addWidget(btn_cam)

        bar.addWidget(QLabel("☀"))
        self._sld_brightness = QSlider(Qt.Orientation.Horizontal)
        self._sld_brightness.setRange(0, 100)
        self._sld_brightness.setValue(45)
        self._sld_brightness.setFixedWidth(110)
        self._sld_brightness.setToolTip("Szenen-Helligkeit")
        self._sld_brightness.valueChanged.connect(self._on_brightness_changed)
        bar.addWidget(self._sld_brightness)

        bar.addStretch()
        self._lbl_hint = QLabel("3D — im Bühnen-Layout platzierte Strahler erscheinen automatisch")
        self._lbl_hint.setStyleSheet("color:#666; font-size:10px;")
        bar.addWidget(self._lbl_hint)
        root.addLayout(bar)

        self._view = QWebEngineView()
        try:
            profile = self._view.page().profile()
            profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
            profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
            )
        except Exception as e:
            print(f"[Visualizer3DView] cache-disable error: {e}")
        s = self._view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        root.addWidget(self._view, 1)

    # ── WebChannel ──────────────────────────────────────────────────────────
    def _setup_channel(self):
        self._bridge = VisualizerBridge(self._state, self)
        self._channel = QWebChannel(self)
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)
        # Leak-Schutz: beim Zerstoeren des Widgets den State-Subscriber der Bridge
        # abmelden — als Backstop, falls das Widget zerstoert wird ohne vorher
        # on_hidden() zu sehen. Destruction-safe: wir capturen nur die State-
        # Referenz + den gebundenen Callback (NICHT self), damit der Slot waehrend
        # ~QWidget nicht auf ein halb-zerstoertes Objekt zugreift. unsubscribe ist
        # defensiv -> doppelt (on_hidden + destroyed) ist ein No-Op.
        _state = self._state
        _on_state = self._bridge._on_state
        self.destroyed.connect(lambda *_: _state.unsubscribe(_on_state))
        # VIZ-10: Renderer-Absturz -> Log + Auto-Reload (max. 3x/60s), derselbe
        # Mechanismus wie im VisualizerWindow (siehe RenderCrashGuard dort).
        # weak_slot_fwd statt Bound-Method: self -> guard -> self waere ein
        # GC-Zyklus um den Owner (STAB-10, native AV-Klasse beim GC-Teardown).
        self._render_crash_guard = install_render_crash_guard(
            self._view, status_cb=weak_slot_fwd(self._on_render_crash_giveup))
        load_stage_html(self._view)
        self._view.loadFinished.connect(self._on_load_finished)

    def _on_load_finished(self, ok: bool):
        if not ok:
            return
        self._loaded = True
        guard = getattr(self, "_render_crash_guard", None)
        if guard is not None:
            guard.reset()   # stabiler Load -> Absturz-Kontingent wieder voll
        QTimer.singleShot(300, self._push_initial_state)

    def _on_render_crash_giveup(self, message: str):
        """VIZ-10: nach 3 automatischen Neustarts in 60s aufgeben — sichtbare
        Statusmeldung statt stiller Endlosschleife toter Reloads."""
        self._lbl_hint.setText(message)

    def _push_initial_state(self):
        try:
            self._bridge.push_settings(self._collect_settings())
            self._bridge.push_view_mode("3D")
            self._bridge.push_edit_mode(self._edit_mode)
            self._apply_active_stage()
            self._bridge.requestFixtures()
        except Exception as e:
            print(f"[Visualizer3DView] push_initial_state error: {e}")

    def _apply_active_stage(self):
        """Aktive Buehne (read-only Anzeige) anhand AppState laden."""
        name = getattr(self._state, "active_stage_name", "simple") or "simple"
        stage = None
        if name in DEFAULT_PRESETS:
            stage = DEFAULT_PRESETS[name]()
        else:
            stage = load_stage(name)
        if stage is None:
            stage = get_default_simple()
        try:
            self._bridge.push_stage_definition(stage)
        except Exception as e:
            print(f"[Visualizer3DView] apply stage error: {e}")

    def _collect_settings(self) -> dict:
        return {
            "beamOpacity":    0.35,
            "showCones":      True,
            "showFloorSpots": True,
            "showFog":        True,
            "snapToGrid":     True,
            "gridStep":       1.0,
            "brightness":     self._sld_brightness.value() / 100.0,
            "autoBrightness": False,
            "dockEnabled":    False,
        }

    # ── DMX-Push (nur waehrend sichtbar) ────────────────────────────────────
    def _push_dmx_updates(self):
        try:
            for fixture in self._state.get_patched_fixtures():
                if fixture.fid not in self._state.visualizer_positions:
                    continue
                if fixture.universe not in self._state.universes:
                    continue
                universe = self._state.universes[fixture.universe]
                attrs: dict[str, int] = {}
                seen: dict[str, int] = {}
                for ch in get_channels_for_patched(fixture):
                    addr = fixture.address + ch.channel_number - 1
                    if 1 <= addr <= 512:
                        # Mehrkopf (Spider): N-tes Vorkommen = Kopf N ("attr#N").
                        a = ch.attribute
                        h = seen.get(a, 0)
                        seen[a] = h + 1
                        key = a if h == 0 else f"{a}#{h}"
                        attrs[key] = universe.get_channel(addr)
                self._bridge.push_dmx_update(fixture.fid, attrs)
        except Exception as e:
            print(f"[Visualizer3DView] dmx update error: {e}")

    # ── oeffentliche API (von der Live View aufgerufen) ─────────────────────
    def on_shown(self):
        """Beim Einblenden: State-Subscriber (re)aktivieren, Timer starten +
        Fixtures aus der Live View (re)sync."""
        try:
            self._bridge._activate()        # idempotent re-arm nach on_hidden()
        except Exception:
            pass
        if not self._dmx_timer.isActive():
            self._dmx_timer.start(33)
        if self._loaded:
            try:
                self._bridge.requestFixtures()
            except Exception:
                pass

    def on_hidden(self):
        """Beim Ausblenden: Timer stoppen + State-Subscriber abmelden
        (Ressourcen schonen, kein toter Callback in AppState._callbacks). Die
        3D-Szene rendert nur sichtbar; on_shown() resynct ohnehin komplett."""
        if self._dmx_timer.isActive():
            self._dmx_timer.stop()
        try:
            self._bridge.dispose()
        except Exception:
            pass

    # ── Steuerung ───────────────────────────────────────────────────────────
    def _on_move_toggled(self, checked: bool):
        self._edit_mode = "edit" if checked else "view"
        self._btn_move.setText("✚ Fixtures bewegen" if checked else "✋ Ansehen")
        try:
            self._bridge.push_edit_mode(self._edit_mode)
        except Exception:
            pass

    def _reset_camera(self):
        try:
            self._bridge.cameraReset.emit()
        except Exception:
            pass

    def _on_brightness_changed(self, value: int):
        try:
            self._bridge.brightnessSignal.emit(value / 100.0)
        except Exception:
            pass
