"""Eingebettetes 3D-View-Widget (Three.js) zur Wiederverwendung.

Im Gegensatz zum vollen ``VisualizerWindow`` (Stage-Builder, Tabs, Toolbar)
ist dies ein schlankes Widget: WebView + die wiederverwendbare
``VisualizerBridge``. Es wird in der **Live View** eingebettet, damit man dort
zwischen 2D-Top-Down und 3D umschalten kann, ohne ein eigenes Fenster zu
oeffnen.

VIZ-12 Schritt 6: reines Spiegel-Target am ``VisualizerService``-Singleton
(kein eigener DMX-Push-Timer mehr) — s. ``_setup_service_target``.

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
    QMainWindow,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication

from src.core.app_state import get_state
from src.core.stage.stage_definition import resolve_active_stage
from src.ui.visualizer.visualizer_window import (
    VisualizerBridge, load_stage_html, install_render_crash_guard,
)
from src.ui.visualizer.visualizer_service import get_visualizer_service, VisualizerTarget
from src.ui.weak_slots import weak_slot_fwd


class Visualizer3DView(QWidget):
    """Leichtgewichtige 3D-Ansicht zum Einbetten (z.B. in die Live View).

    VIZ-POPOUT: dieselbe Klasse wird ZWEIMAL genutzt — eingebettet in der Live
    View (``target_name='live_view_mirror'``, ``show_popout_button=True``) und
    als Inhalt des Pop-out-Fensters (``target_name='live_view_popout'``, kein
    Pop-out-Button). Der Target-Name MUSS je Instanz eindeutig sein, sonst
    kollidieren zwei gleichnamige Targets im ``VisualizerService`` (Panel-Fund).
    """

    #: VIZ-POPOUT: die eingebettete View bittet ihren Owner (Live View), sie in
    #: ein eigenes Fenster auszuklinken. Reine Absichts-Meldung — das Ausklinken
    #: (2D-Rueckfall + Fensterbau) orchestriert der Owner, damit die View selbst
    #: wiederverwendbar/kontextfrei bleibt.
    popOutRequested = Signal()

    def __init__(self, parent=None, *, target_name: str = "live_view_mirror",
                 show_popout_button: bool = False):
        super().__init__(parent)
        self._state = get_state()
        self._loaded = False
        self._edit_mode = "view"          # 'view' | 'edit' (kein 'stage')
        self._target_name = target_name
        self._show_popout_button = show_popout_button
        self._setup_ui()
        self._setup_channel()
        self._setup_service_target()

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

        # VIZ-LABELS: Fixture-Namens-Labels ein-/ausblenden. Checkable, gespiegelt
        # gegen den zentralen AppState-Schalter (eine Quelle fuer alle 3D-Views).
        self._btn_labels = QPushButton("🏷 Labels")
        self._btn_labels.setCheckable(True)
        self._btn_labels.setChecked(bool(getattr(self._state, "show_fixture_labels", True)))
        self._btn_labels.setMinimumHeight(30)
        self._btn_labels.setStyleSheet(_style)
        self._btn_labels.setToolTip("Fixture-Namen (#ID + Kurzname) im 3D ein-/ausblenden")
        self._btn_labels.toggled.connect(self._on_labels_toggled)
        bar.addWidget(self._btn_labels)

        bar.addWidget(QLabel("☀"))
        self._sld_brightness = QSlider(Qt.Orientation.Horizontal)
        self._sld_brightness.setRange(0, 100)
        self._sld_brightness.setValue(45)
        self._sld_brightness.setFixedWidth(110)
        self._sld_brightness.setToolTip("Szenen-Helligkeit")
        self._sld_brightness.valueChanged.connect(self._on_brightness_changed)
        bar.addWidget(self._sld_brightness)

        # VIZ-POPOUT: 3D in ein eigenes, frei verschiebbares Fenster loesen
        # (Zweitmonitor). Nur in der eingebetteten View — das Ausklinken selbst
        # macht der Owner (Live View) ueber das popOutRequested-Signal.
        if self._show_popout_button:
            self._btn_popout = QPushButton("⧉ Ausklinken")
            self._btn_popout.setMinimumHeight(30)
            self._btn_popout.setStyleSheet(_style)
            self._btn_popout.setToolTip(
                "3D in ein eigenes Fenster loesen — auf einen zweiten Monitor\n"
                "ziehbar. Fenster schliessen holt die Ansicht zurueck."
            )
            self._btn_popout.clicked.connect(self.popOutRequested.emit)
            bar.addWidget(self._btn_popout)

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
        # VIZ-10: Renderer-Absturz -> Log + Auto-Reload (max. 3x/60s), derselbe
        # Mechanismus wie im VisualizerWindow (siehe RenderCrashGuard dort).
        # weak_slot_fwd statt Bound-Method: self -> guard -> self waere ein
        # GC-Zyklus um den Owner (STAB-10, native AV-Klasse beim GC-Teardown).
        self._render_crash_guard = install_render_crash_guard(
            self._view, status_cb=weak_slot_fwd(self._on_render_crash_giveup),
            # on_reloaded ebenfalls weak (STAB-10-Muster, s. VisualizerWindow).
            on_reloaded=weak_slot_fwd(self._force_full_resync_after_crash))
        load_stage_html(self._view)
        self._view.loadFinished.connect(self._on_load_finished)

    def _setup_service_target(self):
        """VIZ-12 Schritt 6: die Spiegel-View dockt — genau wie das Fenster
        (``VisualizerWindow._setup_service_target``) — an das EINE
        ``VisualizerService``-Singleton an, statt einen eigenen
        ``QTimer``/``_push_dmx_updates`` zu betreiben. Der Service liefert
        Batch-Updates ueber ``self._target.emit_batch`` -> laeuft auf
        ``self._bridge.dmxBatch.emit`` (Bridge-Signatur unveraendert).

        Pro-Target-Zustand (Reload-Token/Echo-Guard/RenderCrashGuard, Trace)
        bleibt in der Bridge/im Widget (Invariante 2) — der Service kennt nur
        die duennen ``on_reset_interaction``/``on_reload``-Callbacks.

        Attach passiert bereits im ``__init__`` (nicht erst bei ``on_shown``),
        damit der Service als Singleton EIN dauerhaftes Ziel kennt; Aktivierung
        (Push-Relevanz) steuert weiterhin ``on_shown``/``on_hidden`` ueber
        ``set_target_active`` — der Service ueberlebt das Widget (Design (a):
        "Fenster/Live-View sind beide nur Konsumenten und duerfen den Service
        ueberleben"), deshalb ``destroyed`` -> nur noch ``detach_target`` als
        Backstop (kein State-Unsubscribe mehr noetig, das laeuft zentral im
        Service, s. ``VisualizerService.shutdown``)."""
        self._service = get_visualizer_service(self._state)
        # getattr-Default: die bestehenden Service-Target-Tests rufen
        # _setup_service_target mit einem SimpleNamespace-Fake-self OHNE
        # _target_name (Fake-self-Muster, s. test_viz12_service) — dort gilt der
        # Alt-Name. Echte Instanzen setzen _target_name im __init__.
        target_name = getattr(self, "_target_name", "live_view_mirror")
        self._target = VisualizerTarget(
            target_name, self._bridge.dmxBatch.emit,
            on_reset_interaction=self._reset_own_interaction_state,
            on_reload=self._reload_own_page,
        )
        self._service.attach_target(self._target)
        # VIZ-12 (Live-Befund): JS fordert nach dem Fixture-Bau selbst den
        # vollen DMX-Bestand an (requestFullResync-Slot der Bridge). getattr:
        # SimpleNamespace-Test-Fakes haben die gebundene Methode nicht.
        self._bridge.full_resync_cb = getattr(
            self, "_force_full_resync_after_crash", None)
        # Leak-Schutz: beim Zerstoeren des Widgets vom Service abdocken — als
        # Backstop, falls das Widget zerstoert wird ohne vorher on_hidden() zu
        # sehen. Destruction-safe: wir capturen nur Service+Target (NICHT
        # self), damit der Slot waehrend ~QWidget nicht auf ein halb-
        # zerstoertes Objekt zugreift. detach_target ist defensiv -> doppelt
        # (on_hidden + destroyed) ist ein No-Op.
        _service = self._service
        _target = self._target
        self.destroyed.connect(lambda *_: _service.detach_target(_target))

    def _force_full_resync_after_crash(self) -> None:
        """VIZ-12 Review-Fix: nach der RenderCrashGuard-Selbstheilung den
        Service-Dirty-Cache fuer DIESES Target invalidieren — sonst bleiben
        seit dem Crash unveraenderte Fixtures auf der frischen Page schwarz."""
        svc = getattr(self, "_service", None)
        target = getattr(self, "_target", None)
        if svc is not None and target is not None:
            svc.force_full_resync(target)

    def _reset_own_interaction_state(self) -> None:
        """VIZ-12 Schritt 6: vom Service ueber ``on_reset_interaction`` bei
        ``service.reset_interaction_state()`` aufgerufen (Stage-Wechsel/
        show_loaded). Stoppt eine laufende Live-Trace (Bridge-eigener Zustand)
        und setzt den Reload-Churn-Guard zurueck — identisches Muster zu
        ``VisualizerWindow._reset_own_interaction_state``."""
        bridge = getattr(self, "_bridge", None)
        if bridge is None:
            return
        try:
            bridge.stop_trace()
        except Exception as e:
            print(f"[Visualizer3DView] reset_interaction_state stop_trace error: {e}")
        try:
            bridge._cancel_reload_guard_fallback()
            bridge._reloading_stage = False
        except Exception as e:
            print(f"[Visualizer3DView] reset_interaction_state reload-guard error: {e}")

    def _reload_own_page(self) -> None:
        """VIZ-12 Schritt 6: vom Service ueber ``on_reload`` bei
        ``service.reload_all_targets()`` aufgerufen ("Szene neu laden" laedt
        laut Orchestrator-Entscheidung 4 BEIDE Pages). Faehrt ``load_stage_html``
        mit Cache-Buster fuer DIESES Target — identisches Muster zu
        ``VisualizerWindow._reload_own_page``."""
        view = getattr(self, "_view", None)
        if view is None:
            return
        load_stage_html(view)

    def _on_load_finished(self, ok: bool):
        if not ok:
            return
        self._loaded = True
        guard = getattr(self, "_render_crash_guard", None)
        if guard is not None:
            guard.reset()   # stabiler Load -> Absturz-Kontingent wieder voll
        QTimer.singleShot(300, self._push_initial_state)
        # Live-Befund VIZ-12: Voll-Resync erst wenn die Page wirklich bereit
        # ist (s. VisualizerWindow._on_load_finished) — sonst verpufft der
        # needs_full-Erstpush und der Dirty-Diff schweigt dauerhaft.
        QTimer.singleShot(350, self._force_full_resync_after_crash)

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
        # VIZ-11 Schritt 9 (Design (b)): dieselbe Resolve-Quelle wie
        # VisualizerWindow._apply_active_stage_from_state — s. stage_definition.py.
        stage, _combo_kind, _combo_name = resolve_active_stage(name)
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
            # VIZ-LABELS: aus der zentralen Quelle lesen (nicht aus dem Button),
            # damit der gepushte Wert immer dem AppState entspricht — der Button
            # ist nur ein Controller, der AppState VOR dem Push schreibt.
            "showLabels":     bool(getattr(self._state, "show_fixture_labels", True)),
        }

    # ── oeffentliche API (von der Live View aufgerufen) ─────────────────────
    def on_shown(self):
        """Beim Einblenden: Bridge-State-Subscriber (re)aktivieren, Service-
        Target aktiv schalten (Push-Relevanz -> Service-Timer laeuft nur bei
        >=1 aktivem Target, s. VisualizerService._update_timer_gate) +
        Fixtures aus der Live View (re)sync. VIZ-12 Schritt 6: kein eigener
        QTimer/_push_dmx_updates mehr — der Service pusht ueber
        ``self._target.emit_batch``."""
        try:
            self._bridge._activate()        # idempotent re-arm nach on_hidden()
        except Exception:
            pass
        svc = getattr(self, "_service", None)
        target = getattr(self, "_target", None)
        if svc is not None and target is not None:
            svc.set_target_active(target, True)
        # VIZ-LABELS (Review-Fix): die View wird beim 2D<->3D-Wechsel / Pop-out-
        # Redock nur versteckt & wiederverwendet (KEIN Page-Reload). Der einzige
        # Settings-Push liegt sonst in _push_initial_state (nur bei loadFinished).
        # Ohne Nachziehen behaelt die Page einen stale showLabels-Wert (z.B. im
        # Pop-out/Vollfenster umgeschaltet) und der Button-Haken laeuft aus der
        # zentralen Quelle heraus -> Nutzerwahl geht still verloren. Daher beim
        # (Wieder-)Einblenden Button + JS-Settings aus AppState resyncen.
        # (getattr-guarded: die Service-Target-Tests rufen on_shown mit einem
        # SimpleNamespace-Fake-self OHNE Button/_collect_settings, s. test_viz12.)
        _btn = getattr(self, "_btn_labels", None)
        if _btn is not None:
            _want = bool(getattr(self._state, "show_fixture_labels", True))
            if _btn.isChecked() != _want:
                _btn.blockSignals(True)
                _btn.setChecked(_want)
                _btn.blockSignals(False)
        if getattr(self, "_loaded", False):
            try:
                self._bridge.push_settings(self._collect_settings())
            except Exception:
                pass
            try:
                self._bridge.requestFixtures()
            except Exception:
                pass

    def on_hidden(self):
        """Beim Ausblenden: Service-Target inaktiv schalten (kein Push mehr an
        dieses Target) + Bridge-State-Subscriber abmelden (Ressourcen schonen,
        kein toter Callback in AppState._callbacks). Das Service-Target BLEIBT
        angedockt (kein detach) — Page/Bridge leben weiter, on_shown()
        resynct ohnehin komplett (needs_full wird beim Reaktivieren gesetzt)."""
        svc = getattr(self, "_service", None)
        target = getattr(self, "_target", None)
        if svc is not None and target is not None:
            svc.set_target_active(target, False)
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

    def _on_labels_toggled(self, checked: bool):
        # VIZ-LABELS: zentrale Quelle ZUERST schreiben, dann pushen (push liest
        # AppState) — so bleiben eingebettete View, Pop-out und Vollfenster
        # konsistent, auch wenn diese Instanz spaeter lazy neu erzeugt wird.
        try:
            self._state.show_fixture_labels = bool(checked)
        except Exception:
            pass
        try:
            self._bridge.push_settings(self._collect_settings())
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


class VisualizerPopoutWindow(QMainWindow):
    """VIZ-POPOUT: schlankes, eigenstaendiges Top-Level-Fenster, das genau EINE
    weitere :class:`Visualizer3DView` hostet (Service-Target ``live_view_popout``).
    Damit laesst sich die 3D-Ansicht auf einen zweiten Monitor ziehen.

    Panel-Entscheidung C: bewusst KEIN Neubau von WebView/Bridge/RenderCrashGuard/
    Pull-Poll — die wiederverwendete :class:`Visualizer3DView` bringt all das schon
    fertig mit. Lifecycle-Vertrag (Panel-Muss): ``closeEvent`` ruft ``on_hidden()``
    der Kind-View (Service-Target inaktiv + ``bridge.dispose()``), ``deleteLater()``
    loest die View aus -> ihr ``destroyed``->``detach_target``-Backstop meldet das
    Target beim Service ab. ``closed`` signalisiert dem Owner (Live View), dass
    wieder in die eingebettete Ansicht angedockt werden soll.

    GPU-Invariante (Panel-Muss): der Owner schaltet die eingebettete 3D-View beim
    Ausklinken auf 2D-Top-Down zurueck, sodass NIE zwei WebGL-Szenen gleichzeitig
    rendern (Adreno-Textur-Budget).
    """

    #: an den Owner: das Fenster wird geschlossen -> bitte wieder andocken.
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LightOS — 3D-Visualizer (Zweitmonitor)")
        # Eigenstaendiges Top-Level-Fenster, damit es frei auf einen anderen
        # Bildschirm gezogen werden kann. WA_DeleteOnClose: beim Schliessen wird
        # das Fenster (und via Qt-Parent die Kind-View) zerstoert -> deren
        # destroyed->detach_target-Backstop meldet das Service-Target sauber ab
        # (kein lingernder Subscriber). closeEvent macht zusaetzlich den
        # deterministischen Teil (on_hidden: Target inaktiv + bridge.dispose).
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._closing = False
        self._view = Visualizer3DView(
            self, target_name="live_view_popout", show_popout_button=False)
        self.setCentralWidget(self._view)
        self._place_on_free_screen()

    @property
    def view(self) -> "Visualizer3DView":
        return self._view

    def _place_on_free_screen(self):
        """Auf einem moeglichst NICHT-primaeren Bildschirm zentrieren (Davids
        Zweitmonitor-Wunsch); faellt auf den Primaerschirm zurueck, wenn nur ein
        Screen vorhanden ist. Immer gegen die AKTUELL vorhandenen Screens
        validiert — so landet das Fenster nie unsichtbar auf einem abgezogenen
        Monitor (Panel-Risiko 'off-screen')."""
        try:
            screens = QGuiApplication.screens()
            primary = QGuiApplication.primaryScreen()
            target = next((s for s in screens if s is not primary), None) or primary
            if target is None:
                self.resize(960, 640)
                return
            geo = target.availableGeometry()
            w = min(1100, max(480, geo.width() - 80))
            h = min(720, max(360, geo.height() - 80))
            self.resize(w, h)
            self.move(geo.center().x() - w // 2, geo.center().y() - h // 2)
        except Exception as e:
            print(f"[VisualizerPopoutWindow] place error: {e}")
            self.resize(960, 640)

    def showEvent(self, event):
        super().showEvent(event)
        # Kind-View aktiv schalten (Target aktiv + voller Resync). Idempotent —
        # showEvent kann bei Fokuswechseln mehrfach feuern.
        try:
            self._view.on_shown()
        except Exception:
            pass

    def closeEvent(self, event):
        # Deterministischer Teil des Teardowns; idempotent gegen doppelte
        # Zustellung (Fenster-X UND Owner-seitiges close()). Die eigentliche
        # Zerstoerung + Target-detach besorgt WA_DeleteOnClose (s. __init__).
        if not self._closing:
            self._closing = True
            try:
                self._view.on_hidden()   # Target inaktiv + bridge.dispose()
            except Exception:
                pass
            self.closed.emit()
        super().closeEvent(event)
