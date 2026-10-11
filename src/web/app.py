"""LightOS Web Interface — Flask + SocketIO remote control."""
from __future__ import annotations
import threading
import os
from typing import Any

try:
    from flask import Flask, render_template, request, jsonify, session
    from flask_socketio import SocketIO, emit
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

_flask_app: Any = None
_socketio: Any = None
_thread: threading.Thread | None = None
_server: Any = None   # NET-09: Werkzeug-Server-Handle fuer thread-safen shutdown()
_running = False


def _get_state():
    from src.core.app_state import get_state
    return get_state()


def _is_private_ipv4(ip: str) -> bool:
    """True fuer private LAN-Adressen (RFC 1918): 10./172.16-31./192.168.,
    nicht Loopback (127.*) und nicht 0.*. Nur diese sind fuer das isolierte
    Venue-LAN brauchbar."""
    if not ip or ip.startswith(("0.", "127.")):
        return False
    if ip.startswith(("10.", "192.168.")):
        return True
    if ip.startswith("172."):
        try:
            second = int(ip.split(".")[1])
        except (IndexError, ValueError):
            return False
        return 16 <= second <= 31
    return False


def get_lan_ip() -> str:
    """Ermittelt die eigene LAN-IPv4-Adresse fuer die Remote-Anzeige.

    Der Server bindet auf 0.0.0.0 (das ganze LAN), im Verbindungs-Dialog soll
    aber die konkrete Adresse stehen, die der Nutzer am Handy eintippt — nicht
    das irrefuehrende ``localhost`` (NET-02). Trick: ein UDP-Socket "verbinden"
    zu einer externen Adresse; dabei fliesst kein Paket, aber das OS waehlt das
    ausgehende Interface, dessen lokale Adresse wir dann auslesen.

    Die connect-Heuristik liefert aber die Adresse der DEFAULT-Route — bei
    aktivem VPN die VPN-NIC, ohne Internet wirft sie (bzw. 127.*), was fuer die
    isolierten Venue-LANs falsch ist (CDX-06). Faellt sie auf Loopback/nichts
    zurueck, enumerieren wir daher die lokalen NICs und nehmen die erste private
    (10./172.16-31./192.168.) Nicht-Loopback-Adresse. Erst wenn auch das nichts
    findet, bleibt ``127.0.0.1`` — nie ein Crash."""
    import socket
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # 8.8.8.8 ist nur ein Routing-Ziel; es wird nichts gesendet.
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        if ip and not ip.startswith(("0.", "127.")):
            return ip
    except OSError:
        pass
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    # Fallback: die default-Route hat keine brauchbare LAN-IP geliefert
    # (kein Netz oder VPN/Loopback). Lokale NICs enumerieren — ohne externe
    # Dependency, nur ueber die stdlib — und die erste private Adresse nehmen.
    candidates: list[str] = []
    try:
        hostname = socket.gethostname()
        candidates.append(socket.gethostbyname(hostname))
    except OSError:
        pass
    try:
        _name, _aliases, addrs = socket.gethostbyname_ex(socket.gethostname())
        candidates.extend(addrs)
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidates.append(info[4][0])
    except OSError:
        pass

    for ip in candidates:
        if _is_private_ipv4(ip):
            return ip

    return "127.0.0.1"


def remote_url(port: int = 5000) -> str:
    """Vollstaendige LAN-URL fuer das Web-Remote, z.B. ``http://192.168.1.5:5000``."""
    return f"http://{get_lan_ip()}:{port}"


def cors_allowlist(port: int = 5000, lan_ip: str | None = None) -> list[str]:
    """NET-03: konkrete CORS-Origin-Allowlist statt ``"*"``.

    Frueher stand ``cors_allowed_origins="*"`` — JEDE Website im Browser des
    Nutzers durfte damit per fetch/WebSocket auf das LAN-Remote zugreifen
    (Drive-by-CSRF/-WebSocket). Da der Server auf 0.0.0.0 an der bekannten
    LAN-IP:Port haengt, kennen wir die drei legitimen Origins und listen genau
    sie: die LAN-IP (fuers Handy) plus Loopback (Bedienung am Host). Alles offline
    ermittelt (``get_lan_ip`` nutzt nur die stdlib, kein DNS/Cloud)."""
    ip = lan_ip if lan_ip is not None else get_lan_ip()
    origins = [f"http://127.0.0.1:{port}", f"http://localhost:{port}"]
    if ip and ip not in ("127.0.0.1", "localhost"):
        origins.insert(0, f"http://{ip}:{port}")
    return origins


def _num(data, key, default, cast):
    """Robuste Zahl-Coercion aus einem (JSON-)Dict: bei fehlendem, nicht-
    numerischem oder nicht-endlichem (int(inf)/int(NaN)) Wert wird der Default
    zurückgegeben — kein ungefangener HTTP 500 / Handler-Crash aus einem
    fehlerhaften Remote-Payload heraus (WEB-02). Die anschließenden Clamps
    (max/min) bleiben die einzige Wert-Leitplanke."""
    try:
        return cast(data.get(key, default))
    except (TypeError, ValueError, OverflowError):
        return default


def bediene_cueliste(state, aktion: str):
    """UI-66: GO/Zurueck/Stop des Web-Remotes (REST + Socket) auf die
    Transport-Ziel-Liste (gewaehlte, wenn auf einem Executor; sonst erster
    Executor der aktuellen Page mit Liste; sonst erste gebundene; sonst ohne
    Licht) — Regel zentral in src/core/cueliste_ziel.py (zieht auch den
    A3D-40-Snapshot)."""
    from src.core.cueliste_ziel import bediene_cueliste as _bediene
    return _bediene(state, aktion)


def _listen_name(stack):
    return getattr(stack, "name", None) if stack is not None else None


def _transport_info(aktion: str) -> dict:
    """Fuehrt die Aktion aus; liefert ``liste`` (Name/None), ``licht`` (bool) und
    bei fehlendem Licht eine ``warnung`` — fuer REST-JSON und Socket-ack."""
    from src.core.cueliste_ziel import liegt_auf_executor
    state = _get_state()
    stack = bediene_cueliste(state, aktion)
    licht = liegt_auf_executor(state, stack)
    info = {"liste": _listen_name(stack), "licht": licht}
    if stack is None:
        info["warnung"] = "Keine Cueliste vorhanden"
    elif not licht:
        info["warnung"] = "Keine Cueliste liegt auf einem Executor — kein Licht"
    return info


def _transport_antwort(aktion: str):
    return jsonify({"ok": True, **_transport_info(aktion)})


def create_app(port: int = 5000) -> tuple:
    """Create and configure the Flask app + SocketIO."""
    global _flask_app, _socketio
    if not HAS_FLASK:
        raise RuntimeError("Flask / flask-socketio not installed")

    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    # WEB-06: der Socket.IO-Client liegt lokal unter static/ — nichts aus dem
    # Internet. Ordner ausdruecklich setzen (wie templates), damit die Aufloesung
    # im gefrorenen Build nicht an Flasks root_path-Erkennung haengt.
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    _flask_app = Flask(__name__, template_folder=template_dir,
                       static_folder=static_dir, static_url_path="/static")
    # SECRET_KEY: aus ENV lesen, sonst zufaellig generieren (nie hardcoden!)
    import secrets
    _flask_app.config["SECRET_KEY"] = os.environ.get("LIGHTOS_FLASK_SECRET") or secrets.token_hex(32)
    # NET-01: Session-Cookie haerten — HttpOnly (kein JS-Zugriff) + SameSite=Strict
    # (kein Cross-Site-Mitsenden, ergaenzt die Origin-Allowlist gegen CSRF).
    _flask_app.config["SESSION_COOKIE_HTTPONLY"] = True
    _flask_app.config["SESSION_COOKIE_SAMESITE"] = "Strict"
    # NET-01: Token bei erstem create_app erzeugen + persistieren (Wiederverwendung
    # bei Neustart). Fehlt das Settings-Modul (z. B. Test-Stub), bleibt es leer.
    try:
        from src.web import remote_settings
        _flask_app.config["LIGHTOS_REMOTE_TOKEN"] = remote_settings.get_token()
    except Exception as e:
        print(f"[web] token init error: {e}")
        _flask_app.config["LIGHTOS_REMOTE_TOKEN"] = ""
    # NET-03: konkrete Origin-Allowlist statt "*" (Drive-by-CSRF/-WebSocket). Die
    # Liste auch in der App-Config ablegen, damit UI/Tests sie einsehen koennen.
    origins = cors_allowlist(port)
    _flask_app.config["CORS_ALLOWED_ORIGINS"] = origins
    _socketio = SocketIO(_flask_app, cors_allowed_origins=origins, async_mode="threading")

    _register_auth(_flask_app)
    _register_routes(_flask_app)
    _register_socketio(_socketio)
    return _flask_app, _socketio


def refresh_token(app) -> None:
    """Laedt das aktuelle Token frisch aus den Prefs in ``app.config`` — nach einer
    Token-Rotation (``remote_settings.regenerate_token()``) aufrufen, damit der
    LAUFENDE Server den NEUEN ``?k=``-Link akzeptiert und den ALTEN abweist (kein
    Neustart). Die Invalidierung bereits authentisierter Sessions erledigt die
    mit-erhoehte ``auth_epoch`` (Gate). Beides zusammen macht die Rotation
    vollstaendig wirksam (Security-Review)."""
    try:
        from src.web import remote_settings
        app.config["LIGHTOS_REMOTE_TOKEN"] = remote_settings.get_token()
    except Exception as e:
        print(f"[web] refresh_token error: {e}")


def is_running() -> bool:
    """Laeuft der Web-Server gerade? CDX-24: die UI darf das NICHT am QAction-
    Haken ablesen — der kann vom echten Zustand abweichen (z. B. wenn ein Fehler
    nach erfolgreichem Start den Haken zuruecksetzt), und daran haengt die
    Entscheidung, ob ein Bind-Wechsel einen Neustart braucht (NET-09)."""
    return bool(_running)


def refresh_running_token() -> bool:
    """CDX-24: ``refresh_token`` fuer den LAUFENDEN Server, ohne dass ein Aufrufer
    an das modulprivate ``_flask_app`` muss.

    Noetig, weil die UI nach ``remote_settings.regenerate_token()`` sonst nichts
    ausrichtet: der Gate liest das Token aus ``app.config`` (dort landet es nur in
    ``create_app``), der laufende Server wuerde also weiter den ALTEN ``?k=``-Link
    akzeptieren. Gibt True zurueck, wenn ein Server lief und nachgezogen wurde.
    """
    app = _flask_app
    if app is None:
        return False
    refresh_token(app)
    disconnect_all_clients()
    return True


def disconnect_all_clients() -> int:
    """CDX-24: alle offenen Socket.IO-Verbindungen trennen. Gibt die Anzahl zurueck.

    Ohne das bleibt die Token-Rotation ein halbes Versprechen: das
    ``before_request``-Gate sperrt zwar jede HTTP-Anfrage der alten Epoche, aber
    ein SCHON VERBUNDENER WebSocket laeuft nicht mehr durch dieses Gate — und die
    Event-Handler (``go``/``back``/…) pruefen einzeln gar nichts. Ein Handy, das
    vor der Rotation verbunden war, koennte also weitersteuern, obwohl der Nutzer
    gerade „alle bisherigen Geraete ungueltig machen" gedrueckt hat.

    Defensiv: ein Fehler hier darf die Rotation selbst nie kippen.
    """
    sio = _socketio
    if sio is None:
        return 0
    n = 0
    try:
        server = getattr(sio, "server", None)
        manager = getattr(server, "manager", None) if server is not None else None
        if manager is None:
            return 0
        # Teilnehmer-Snapshot ZUERST materialisieren — wir trennen waehrend der
        # Iteration, das veraendert die zugrundeliegende Struktur.
        sids = [sid for sid, _eio in list(manager.get_participants("/", None))]
        for sid in sids:
            try:
                server.disconnect(sid, namespace="/")
                n += 1
            except Exception:
                pass
    except Exception as e:
        print(f"[web] disconnect_all_clients error: {e}")
    return n


def _register_auth(app):
    """NET-01: Token-Gate. Alle Routen ausser der Allowlist ('/', statische
    Assets) verlangen eine authentisierte Session. Die '/'-Route macht den
    Token-Handshake (``?k=<token>``)."""

    @app.before_request
    def _auth_gate():
        # never-crash: ein Fehler hier darf den Server nicht lahmlegen — aber auch
        # nicht ungeschuetzt durchlassen (im Zweifel 403).
        try:
            path = request.path or "/"
            # Allowlist: Startseite (macht den Handshake) + statische Assets.
            # WEB-09: die Seite der Handy-Konsole macht denselben Handshake —
            # so taugt ihr Link mit Schluessel als Lesezeichen auf dem
            # Startbildschirm. Ausgeliefert wird dort nur die leere Huelle;
            # jeder Inhalt kommt ueber /api/ bzw. den Socket, also hinter dem Gate.
            if path in ("/", "/konsole") or path.startswith("/static/"):
                return None
            if session.get("authed") is True:
                # Security-Review: die Session muss zur AKTUELLEN Auth-Epoche passen
                # -> ein 'Token neu erzeugen' (epoch++) wirft bestehende Sessions raus.
                from src.web import remote_settings
                if session.get("epoch") == remote_settings.get_auth_epoch():
                    return None
        except Exception as e:
            print(f"[web] auth gate error: {e}")
        return ("Forbidden", 403)


def _register_routes(app):

    def _handshake():
        # NET-01: Token-Handshake. ``?k=<token>`` per constant-time-Vergleich gegen
        # das persistierte Token; bei Treffer die Session als authed markieren.
        try:
            k = request.args.get("k")
            if k:
                import secrets as _secrets
                from src.web import remote_settings
                # Laufzeit-Token = app.config (bei create_app aus den Prefs gecacht;
                # ``refresh_token(app)`` haelt es nach einer Rotation aktuell). Die
                # Session bekommt die aktuelle Auth-Epoche gestempelt -> ein 'Token
                # neu erzeugen' (epoch++) invalidiert bestehende Sessions im Gate.
                token = app.config.get("LIGHTOS_REMOTE_TOKEN") or ""
                if token and _secrets.compare_digest(str(k), str(token)):
                    session["authed"] = True
                    session["epoch"] = remote_settings.get_auth_epoch()
        except Exception as e:
            print(f"[web] handshake error: {e}")

    def _konsole_an() -> bool:
        try:
            from src.web import vc_remote
            return bool(vc_remote.ist_aktiv())
        except Exception:
            return False

    @app.route("/")
    def index():
        _handshake()
        # WEB-09: die feste Seite verlinkt auf die Handy-Konsole, wenn sie
        # eingeschaltet ist.
        return render_template("index.html", konsole_an=_konsole_an())

    @app.route("/konsole")
    def konsole_seite():
        # WEB-09: die Handy-Konsole. Die Seite selbst traegt keine Daten der
        # Show — Seiten und Zustand holt sie ueber /api/vc/konsole und den Socket.
        _handshake()
        antwort = app.make_response(render_template("konsole.html"))
        # Nie aus dem Zwischenspeicher: nach einem Update soll das Handy nicht
        # mit einer alten Seite gegen eine neue Schnittstelle sprechen.
        antwort.headers["Cache-Control"] = "no-store"
        return antwort

    @app.route("/api/status")
    def status():
        state = _get_state()
        fixtures = state.get_patched_fixtures()
        # WEB-05: über eine Kopie iterieren — der Web-Thread läuft nebenläufig zum
        # UI-/Output-Thread; ein Show-Load darf hier kein „changed size during
        # iteration" auslösen.
        stacks = [{"name": s.name, "cues": len(s.cues)} for s in list(state.cue_stacks)]
        # Executor-Fader-Zustaende (aktuelle Page) mitliefern, damit das Remote-UI
        # seine Fader INITIAL auf den ECHTEN Wert setzt statt hart auf 100% (Bug:
        # index.html initialisierte alle Fader mit value=255/„100%" ohne Sync).
        try:
            exec_faders = [round(float(e.fader_value), 3)
                           for e in list(state.playback_engine.executors)[:10]]
        except Exception:
            exec_faders = []
        return jsonify({
            "fixtures": len(fixtures),
            "universes": list(state.universes.keys()),
            "cue_stacks": stacks,
            "executors": exec_faders,
            "mock_mode": state.mock_mode,
        })

    @app.route("/api/go", methods=["POST"])
    def api_go():
        # WEB-04/A3D-40: echten Snapshot ziehen (list(...)). Die 'lokale Referenz'
        # allein war KEIN Schutz — sie aliast dieselbe Live-Liste, die show_file beim
        # Laden per cue_stacks.clear() IN-PLACE leert; zwischen 'if stacks:' und
        # 'stacks[0]' gab das weiterhin einen IndexError (HTTP 500). list(...) kopiert
        # -> index-sicher (identisches Muster wie /api/status). Den Snapshot zieht
        # jetzt cueliste_ziel.ziel_cueliste.
        # UI-66: trifft die Transport-Ziel-Liste (gewaehlte, wenn auf einem
        # Executor; sonst erster Executor der aktuellen Page mit Liste; ...) —
        # dieselbe wie Leertaste, Kommandozeile und OSC (frueher fest
        # cue_stacks[0]). Antwort nennt 'liste' + 'licht' (+ 'warnung').
        return _transport_antwort("go")

    @app.route("/api/back", methods=["POST"])
    def api_back():
        return _transport_antwort("back")   # UI-66, s. api_go

    @app.route("/api/stop", methods=["POST"])
    def api_stop():
        # STOP-Button im Remote-UI stoppt die laufende Cueliste (Pendant zu
        # go/back). Vorher rief das Frontend die nicht existierende Route
        # /api/executor/1/back auf -> stiller 404, STOP tat nichts.
        return _transport_antwort("stop")   # UI-66, s. api_go

    @app.route("/api/blackout", methods=["POST"])
    def api_blackout():
        data = request.get_json(silent=True) or {}
        enabled = bool(data.get("enabled", False))
        _get_state().output_manager.set_blackout(enabled)
        return jsonify({"ok": True, "blackout": enabled})

    @app.route("/api/executor/<int:slot>/fader", methods=["POST"])
    def api_fader(slot: int):
        data = request.get_json(silent=True) or {}
        level = _num(data, "level", 1.0, float)   # WEB-02: kein 500 bei kaputtem Payload
        state = _get_state()
        executors = state.playback_engine.executors
        idx = slot - 1
        if 0 <= idx < len(executors):
            executors[idx].fader_value = max(0.0, min(1.0, level))
        return jsonify({"ok": True})

    @app.route("/api/executor/<int:slot>/go", methods=["POST"])
    def api_exec_go(slot: int):
        state = _get_state()
        executors = state.playback_engine.executors
        idx = slot - 1
        if 0 <= idx < len(executors):
            executors[idx].press_btn("go")
        return jsonify({"ok": True})

    @app.route("/api/channel/<int:universe>/<int:channel>", methods=["POST"])
    def api_channel(universe: int, channel: int):
        data = request.get_json(silent=True) or {}
        value = _num(data, "value", 0, int)      # WEB-02: kein 500 bei kaputtem Payload
        state = _get_state()
        # WEB-01: nicht mehr direkt ins Live-Universe (der 44-Hz-Renderer
        # ueberschriebe gepatchte Kanaele jeden Frame), sondern ueber die
        # Input-Override-Schicht — haelt als diskreter Einzelbefehl (REPLACE,
        # vom Source-Timeout ausgenommen). Range-Guards liegen in set_input_channel.
        state.set_input_channel(universe, channel, value, source="web")
        return jsonify({"ok": True})

    @app.route("/api/programmer/clear", methods=["POST"])
    def api_clear():
        _get_state().clear_programmer()
        return jsonify({"ok": True})

    # ── WEB-08: VC-Widgets ueber ihre Kennung ─────────────────────────────────
    # Grundlage der Handy-Konsole (WEB-07). Beide Routen liegen hinter demselben
    # Schluessel-Gate wie alles unter /api/ (``_auth_gate`` kennt nur '/' und
    # '/static/' als Ausnahmen). Zusaetzlich standardmaessig AUS
    # (``remote_settings.vc_remote_enabled``): ohne Auswahl, welche Widgets aufs
    # Handy duerfen, gaebe die Schnittstelle sonst jedes fernbedienbare frei.
    # Die Aktion laeuft im UI-Thread (``VCFernbedienung``), nie hier.

    @app.route("/api/vc/widgets")
    def api_vc_widgets():
        from src.web import vc_remote
        return jsonify(vc_remote.widget_liste())

    @app.route("/api/vc/widget/<kennung>/aktion", methods=["POST"])
    def api_vc_widget_aktion(kennung: str):
        from src.web import vc_remote
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            antwort = {"ok": False, "fehler": "anfrage_ungueltig"}
        else:
            antwort = vc_remote.widget_aktion(kennung, data.get("aktion"),
                                              data.get("wert"))
        return jsonify(antwort), vc_remote.status_fuer(antwort)

    # ── WEB-09: Handy-Konsole ─────────────────────────────────────────────────
    # Seiten + Zustand in einem Abruf (erster Aufbau der Seite, Rueckfall ohne
    # Socket) und Grand Master/Blackout der festen Leiste.

    @app.route("/api/vc/konsole")
    def api_vc_konsole():
        from src.web import vc_remote
        return jsonify(vc_remote.konsole())

    @app.route("/api/vc/pult", methods=["POST"])
    def api_vc_pult():
        from src.web import vc_remote
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            antwort = {"ok": False, "fehler": "anfrage_ungueltig"}
        else:
            antwort = vc_remote.pult(gm=data.get("gm"), blackout=data.get("blackout"))
        return jsonify(antwort), vc_remote.status_fuer(antwort)


def _register_socketio(sio):

    @sio.on("connect")
    def on_connect():
        # NET-01/NET-03: unauthentisierte WebSocket-Verbindung ablehnen — das ist
        # zugleich der Riegel gegen Drive-by-WebSockets (der CORS-Check greift bei
        # WS nicht zuverlaessig). Nur eine Session mit erfolgtem Token-Handshake
        # darf verbinden.
        try:
            if session.get("authed") is not True:
                return False
            # CDX-24: auch die EPOCHE pruefen, genau wie das HTTP-Gate. Sonst
            # duerfte eine Session, die vor einer Token-Rotation authentisiert
            # wurde, danach noch neu verbinden — die Rotation soll aber ALLE
            # bisherigen Anmeldungen entwerten.
            from src.web import remote_settings
            if session.get("epoch") != remote_settings.get_auth_epoch():
                return False
        except Exception as e:
            print(f"[web] socket connect gate error: {e}")
            return False
        state = _get_state()
        emit("status", {"fixtures": len(state.get_patched_fixtures())})

    @sio.on("go")
    def on_go(data=None):
        # UI-66: Transport-Ziel-Liste (cueliste_ziel.py), s. api_go.
        sio.emit("ack", {"action": "go", **_transport_info("go")})

    @sio.on("back")
    def on_back(data=None):
        # UI-66: Transport-Ziel-Liste (cueliste_ziel.py), s. api_go.
        sio.emit("ack", {"action": "back", **_transport_info("back")})

    @sio.on("stop")
    def on_stop(data=None):
        # UI-66: Transport-Ziel-Liste (cueliste_ziel.py), s. api_go.
        sio.emit("ack", {"action": "stop", **_transport_info("stop")})

    @sio.on("fader")
    def on_fader(data=None):
        data = data or {}                     # WEB-03: leerer Emit -> kein AttributeError
        slot = _num(data, "slot", 1, int)     # WEB-02: kein Handler-Crash bei kaputtem Payload
        level = _num(data, "level", 1.0, float)
        state = _get_state()
        idx = slot - 1
        if 0 <= idx < len(state.playback_engine.executors):
            state.playback_engine.executors[idx].fader_value = max(0.0, min(1.0, level))

    @sio.on("blackout")
    def on_blackout(data=None):
        data = data or {}                     # WEB-03: leerer Emit -> kein AttributeError
        enabled = bool(data.get("enabled", False))
        _get_state().output_manager.set_blackout(enabled)

    # ── WEB-09: Handy-Konsole ueber den Socket ────────────────────────────────
    #
    # Rueckmeldung Pult -> Handy: die Bruecke der Konsole gibt Aenderungen an
    # ``vc_remote.melde`` ab; von hier gehen sie an den Raum der Zuschauer.
    # Aktionen Handy -> Pult: dieselbe Pruefkette wie ueber HTTP
    # (``vc_remote.widget_aktion``), nur ohne den Aufbau einer Anfrage je
    # Fader-Schritt.
    #
    # ⚠️ Der Schluessel wird beim Verbinden geprueft (``on_connect``) — eine
    # offene Verbindung laeuft danach aber nicht mehr durch das HTTP-Gate. Jedes
    # Ereignis der Handy-Konsole prueft deshalb selbst noch einmal Anmeldung UND
    # Epoche und trennt die Verbindung, wenn sie nicht (mehr) gilt.
    from flask_socketio import join_room, disconnect
    from src.web import vc_remote

    RAUM = "vc_konsole"
    # Je Verbindung und Widget die Nummer des letzten Fader-Werts. Socket.IO
    # arbeitet die Ereignisse einer Verbindung in eigenen Threads ab: ohne die
    # Nummer koennte ein aelterer Wert den neueren ueberholen und der Fader am
    # Ende auf einem Zwischenstand stehen.
    folge: dict = {}
    folge_lock = threading.Lock()

    def _senden(ereignis, daten):
        sio.emit(ereignis, daten, to=RAUM)

    vc_remote.setze_sender(_senden)

    def _berechtigt() -> bool:
        try:
            from src.web import remote_settings
            if (session.get("authed") is True
                    and session.get("epoch") == remote_settings.get_auth_epoch()):
                return True
        except Exception as e:
            print(f"[web] socket gate error: {e}")
        try:
            disconnect()
        except Exception:
            pass
        return False

    def _veraltet(sid, schluessel, nummer) -> bool:
        """True, wenn zu ``schluessel`` schon ein Wert mit hoeherer Nummer kam."""
        if isinstance(nummer, bool) or not isinstance(nummer, (int, float)):
            return False                    # ohne Nummer: immer ausfuehren
        with folge_lock:
            je_sid = folge.setdefault(sid, {})
            if nummer <= je_sid.get(schluessel, float("-inf")):
                return True
            je_sid[schluessel] = nummer
            return False

    @sio.on("vc_hallo")
    def on_vc_hallo(data=None):
        """Das Handy zeigt die Konsole an: als Zuschauer fuehren und den ganzen
        Stand schicken. Kommt nach JEDEM Verbinden — das ist der vollstaendige
        Abgleich nach einer Wiederverbindung."""
        if not _berechtigt():
            return {"ok": False, "fehler": "kein_zugang"}
        join_room(RAUM)
        vc_remote.zuschauer_dazu(request.sid)   # VOR dem Abgleich, s. Bruecke
        stand = vc_remote.konsole()
        emit("vc_konsole", stand)
        return {"ok": True}

    @sio.on("vc_aktion")
    def on_vc_aktion(data=None):
        if not _berechtigt():
            return {"ok": False, "fehler": "kein_zugang"}
        if not isinstance(data, dict):
            return {"ok": False, "fehler": "anfrage_ungueltig"}
        kennung, aktion = data.get("id"), data.get("aktion")
        if aktion == "setzen" and _veraltet(request.sid, kennung, data.get("n")):
            return {"ok": True, "veraltet": True}
        antwort = vc_remote.widget_aktion(kennung, aktion, data.get("wert"))
        if isinstance(kennung, str):
            if aktion == "druecken" and antwort.get("ok"):
                vc_remote.gehalten_merken(request.sid, kennung, True)
            elif aktion == "loslassen":
                vc_remote.gehalten_merken(request.sid, kennung, False)
        return antwort

    @sio.on("vc_pult")
    def on_vc_pult(data=None):
        if not _berechtigt():
            return {"ok": False, "fehler": "kein_zugang"}
        if not isinstance(data, dict):
            return {"ok": False, "fehler": "anfrage_ungueltig"}
        if "gm" in data and _veraltet(request.sid, "#gm", data.get("n")):
            return {"ok": True, "veraltet": True}
        return vc_remote.pult(gm=data.get("gm"), blackout=data.get("blackout"))

    @sio.on("disconnect")
    def on_disconnect(*_args):
        # Verbindung weg — egal warum (WLAN, Seite geschlossen, Schluessel
        # gewechselt, Server aus): gehaltene Tasten loslassen.
        sid = request.sid
        with folge_lock:
            folge.pop(sid, None)
        vc_remote.zuschauer_weg(sid)


def _halter_hinweis(port: int) -> str:
    """Der Befehl, mit dem man den Halter des Ports findet — je Plattform.

    ⚠️ Bis XPLAT-30 stand hier fest ``ss -lptn``. Das Werkzeug gibt es auf
    Windows nicht; die Meldung schickte also genau die Nutzer ins Leere, bei
    denen der Fall ueberhaupt erst auftreten kann.
    """
    if os.name == "nt":
        return f"`netstat -ano | findstr :{port}` (die letzte Spalte ist die PID)."
    return f"`ss -lptn 'sport = :{port}'`."


def start_server(port: int = 5000):
    """Start the web server in a background thread."""
    global _thread, _running, _server
    if _running:
        return
    if not HAS_FLASK:
        raise RuntimeError("Flask / flask-socketio not installed")

    app, _sio = create_app(port)   # _sio == _socketio-Global (Middleware sitzt an app)
    # NET-01: Bind-Host am Toggle 'LAN-/Handy-Remote' ausrichten. AN (Default) ->
    # 0.0.0.0 (das Handy im LAN erreicht es, Token schuetzt). AUS -> 127.0.0.1
    # (nur der Host selbst, kein LAN-Zugriff).
    host = "0.0.0.0"
    try:
        from src.web import remote_settings
        if not remote_settings.is_lan_remote_enabled():
            host = "127.0.0.1"
    except Exception as e:
        print(f"[web] lan-remote flag read error: {e}")
    # NET-09: Frueher lief der Server via ``sio.run(app, ...)`` — das ruft intern
    # ``werkzeug.serving.run_simple`` (bzw. ``make_server(...).serve_forever()``),
    # gibt aber KEIN Server-Handle her, und ``socketio.stop()`` beendet den
    # Dev-Server aus einem Fremd-Thread (Qt-Menue-Toggle) NICHT zuverlaessig ->
    # der Listen-Socket auf :5000 blieb bis zum App-Ende offen ("Web: aus" log).
    # Fix: denselben Werkzeug-Server EXPLIZIT halten. Die SocketIO-Middleware
    # haengt bereits an ``app.wsgi_app`` (``SocketIO(app, async_mode="threading")``)
    # -> ``make_server(host, port, app, threaded=True)`` bedient HTTP UND SocketIO
    # identisch zu vorher, und ``srv.shutdown()`` beendet ``serve_forever()``
    # thread-safe (Socket schliesst beim Toggle 'aus').
    from werkzeug.serving import make_server, BaseWSGIServer
    # NET-11: ``make_server`` ruft bei belegtem Port ``sys.exit(1)`` — es wirft
    # also ``SystemExit``, und das ist KEINE ``Exception``. Jeder Aufrufer, der
    # ``except Exception`` schreibt (der Menue-Schalter in main_window tut genau
    # das, und richtigerweise), laesst es durch: der SystemExit steigt aus dem
    # Qt-Slot heraus und beendet LightOS auf der Stelle. Gemessen: Port belegt ->
    # ``SystemExit(1)``, Prozess weg, ohne Dialog und ohne Meldung im Menue.
    #
    # Deshalb wird hier aus dem Kontrollfluss-Signal ein gewoehnlicher Fehler:
    # ``OSError`` ist der Typ, den ein fehlgeschlagenes Binden ohnehin haette,
    # und den die Aufrufer schon behandeln. Das schuetzt ALLE Aufrufer (Menue,
    # OSC, Kommandozeile) statt nur den einen, der zuerst auffiel.
    # XPLAT-30: Auf Windows griff der NET-11-Schutz oben NIE, weil dort gar
    # nichts fehlschlaegt. ``make_server`` setzt ``SO_REUSEADDR``, und diese
    # Option bedeutet auf den beiden Plattformen etwas VERSCHIEDENES:
    #
    #   Linux   — „nach TIME_WAIT wieder binden duerfen". Notwendig, damit der
    #             Menue-Schalter aus/ein sofort wieder starten kann.
    #   Windows — „einen belegten Port MITBENUTZEN duerfen". Der zweite Bind
    #             gelingt, und es laufen ZWEI Server auf demselben Port; welche
    #             Instanz eine Verbindung bekommt, ist nicht definiert.
    #
    # Gemessen auf diesem Rechner: ohne die Option scheitert der zweite Bind
    # auch auf Windows (WSAEADDRINUSE 10048); MIT der Option gelingt er. Die
    # App meldete deshalb „Web laeuft", und je nach Zufall antwortete mal die
    # eine, mal die andere Instanz — stiller als ein Absturz und schwerer zu
    # finden als ein Fehler.
    #
    # ★ Deshalb wird die Option NUR auf Windows abgeschaltet, und nur um diesen
    # einen Aufruf herum. Dann faellt der belegte Port wieder in den
    # SystemExit-Pfad unten, den es laengst gibt — ein zweiter, eigener
    # Meldeweg waere dieselbe Frage an zwei Stellen beantwortet.
    #
    # ⚠️ Auf Linux bleibt sie an: dort hiesse Abschalten, dass „Web aus, Web
    # an" nach einer echten Verbindung an TIME_WAIT scheitert. Auf Windows ist
    # genau das gemessen NICHT der Fall (aus/ein direkt nach einer bedienten
    # Verbindung startet weiterhin).
    _reuse_alt = BaseWSGIServer.allow_reuse_address
    if os.name == "nt":
        BaseWSGIServer.allow_reuse_address = False
    try:
        _server = make_server(host, port, app, threaded=True)
    except SystemExit as e:
        raise OSError(
            f"Port {port} ist belegt — ein anderes Programm (oder eine zweite "
            f"LightOS-Instanz) haelt ihn bereits. Das Web-Interface wurde NICHT "
            f"gestartet; LightOS laeuft weiter. Wer den Halter sucht: "
            f"{_halter_hinweis(port)}"
        ) from e
    finally:
        BaseWSGIServer.allow_reuse_address = _reuse_alt
    _running = True
    _thread = threading.Thread(
        target=_server.serve_forever,
        daemon=True,
        name="WebServer"
    )
    _thread.start()
    return port


def stop_server():
    # NET-09: Den Werkzeug-Server sauber herunterfahren. ``srv.shutdown()`` ist
    # thread-safe und unterbricht ``serve_forever()``; ``server_close()`` gibt den
    # Listen-Socket frei -> :5000 ist SOFORT beim Toggle 'aus' frei (frueher blieb
    # er bis App-Ende offen). Idempotent + fehlertolerant.
    global _running, _server, _thread, _flask_app, _socketio
    _running = False
    # CDX-24 (Safety): BESTEHENDE Verbindungen ZUERST kappen — `server_close()`
    # gibt nur den LISTEN-Socket frei. Werkzeugs `ThreadedWSGIServer` laeuft mit
    # `daemon_threads = True`, deshalb sammelt `ThreadingMixIn` seine Handler-
    # Threads gar nicht ein und joint beim Schliessen nichts: ein bereits auf
    # WebSocket hochgestufter Client lief bisher UNBEGRENZT weiter und konnte GO,
    # STOP, Fader und Blackout schicken, obwohl der Nutzer das Web-Interface
    # ausgeschaltet bzw. auf „nur dieser PC" gestellt hatte. Genau der Notfall-
    # Pfad („Handy weg", „Token kompromittiert") hielt also nicht.
    # Reihenfolge ist zwingend: nach einem `start_server()` zeigt `_socketio` auf
    # die NEUE Instanz, die alten Clients waeren dann gar nicht mehr adressierbar.
    disconnect_all_clients()
    srv, _server = _server, None
    if srv is not None:
        try:
            srv.shutdown()          # entblockt serve_forever()
        except Exception as e:
            print(f"[web] server shutdown error: {e}")
        try:
            srv.server_close()      # gibt den Listen-Socket frei
        except Exception:
            pass
    t, _thread = _thread, None
    if t is not None and t.is_alive():
        t.join(timeout=3.0)
    # WEB-09: was jetzt noch als gehalten gefuehrt wird, loslassen, und die
    # Rueckmeldung abmelden — die Bruecke der Konsole soll nicht in einen
    # abgebauten Server senden.
    try:
        from src.web import vc_remote
        vc_remote.alle_loslassen()
        vc_remote.setze_sender(None)
    except Exception as e:
        print(f"[web] vc_remote shutdown error: {e}")
    # CDX-24: Globals mit abraeumen — sonst meldet `refresh_running_token()` auch
    # nach dem Ausschalten noch Erfolg (`_flask_app` blieb gesetzt), und der Dialog
    # behauptet „Neues Token aktiv" fuer einen Server, der gar nicht laeuft.
    _flask_app = None
    _socketio = None
