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


def create_app(port: int = 5000) -> tuple:
    """Create and configure the Flask app + SocketIO."""
    global _flask_app, _socketio
    if not HAS_FLASK:
        raise RuntimeError("Flask / flask-socketio not installed")

    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    _flask_app = Flask(__name__, template_folder=template_dir)
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
            if path == "/" or path.startswith("/static/"):
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

    @app.route("/")
    def index():
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
        return render_template("index.html")

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
        # -> index-sicher (identisches Muster wie /api/status).
        stacks = list(_get_state().cue_stacks)
        if stacks:
            stacks[0].go()
        return jsonify({"ok": True})

    @app.route("/api/back", methods=["POST"])
    def api_back():
        stacks = list(_get_state().cue_stacks)  # WEB-04/A3D-40: echter Snapshot
        if stacks:
            stacks[0].back()
        return jsonify({"ok": True})

    @app.route("/api/stop", methods=["POST"])
    def api_stop():
        # STOP-Button im Remote-UI stoppt die laufende Cueliste (Pendant zu
        # go/back). Vorher rief das Frontend die nicht existierende Route
        # /api/executor/1/back auf -> stiller 404, STOP tat nichts.
        stacks = list(_get_state().cue_stacks)  # WEB-04/A3D-40: echter Snapshot
        if stacks:
            stacks[0].stop()
        return jsonify({"ok": True})

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
        except Exception as e:
            print(f"[web] socket connect gate error: {e}")
            return False
        state = _get_state()
        emit("status", {"fixtures": len(state.get_patched_fixtures())})

    @sio.on("go")
    def on_go(data=None):
        stacks = list(_get_state().cue_stacks)  # WEB-04/A3D-40: echter Snapshot
        if stacks:
            stacks[0].go()
        sio.emit("ack", {"action": "go"})

    @sio.on("back")
    def on_back(data=None):
        stacks = list(_get_state().cue_stacks)  # WEB-04/A3D-40: echter Snapshot
        if stacks:
            stacks[0].back()
        sio.emit("ack", {"action": "back"})

    @sio.on("stop")
    def on_stop(data=None):
        stacks = list(_get_state().cue_stacks)  # WEB-04/A3D-40: echter Snapshot
        if stacks:
            stacks[0].stop()
        sio.emit("ack", {"action": "stop"})

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
    from werkzeug.serving import make_server
    _server = make_server(host, port, app, threaded=True)
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
    global _running, _server, _thread
    _running = False
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
