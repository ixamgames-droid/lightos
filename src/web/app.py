"""LightOS Web Interface — Flask + SocketIO remote control."""
from __future__ import annotations
import threading
import os
from typing import Any

try:
    from flask import Flask, render_template, request, jsonify
    from flask_socketio import SocketIO, emit
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

_flask_app: Any = None
_socketio: Any = None
_thread: threading.Thread | None = None
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


def create_app() -> tuple:
    """Create and configure the Flask app + SocketIO."""
    global _flask_app, _socketio
    if not HAS_FLASK:
        raise RuntimeError("Flask / flask-socketio not installed")

    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    _flask_app = Flask(__name__, template_folder=template_dir)
    # SECRET_KEY: aus ENV lesen, sonst zufaellig generieren (nie hardcoden!)
    import secrets
    _flask_app.config["SECRET_KEY"] = os.environ.get("LIGHTOS_FLASK_SECRET") or secrets.token_hex(32)
    _socketio = SocketIO(_flask_app, cors_allowed_origins="*", async_mode="threading")

    _register_routes(_flask_app)
    _register_socketio(_socketio)
    return _flask_app, _socketio


def _register_routes(app):

    @app.route("/")
    def index():
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
        # WEB-04: lokale Referenz greifen -> kein TOCTOU-IndexError, falls die
        # Liste zwischen Prüfung und Index-Zugriff nebenläufig geleert wird.
        stacks = _get_state().cue_stacks
        if stacks:
            stacks[0].go()
        return jsonify({"ok": True})

    @app.route("/api/back", methods=["POST"])
    def api_back():
        stacks = _get_state().cue_stacks      # WEB-04: TOCTOU-sicher (lokale Ref)
        if stacks:
            stacks[0].back()
        return jsonify({"ok": True})

    @app.route("/api/stop", methods=["POST"])
    def api_stop():
        # STOP-Button im Remote-UI stoppt die laufende Cueliste (Pendant zu
        # go/back). Vorher rief das Frontend die nicht existierende Route
        # /api/executor/1/back auf -> stiller 404, STOP tat nichts.
        stacks = _get_state().cue_stacks      # WEB-04: TOCTOU-sicher (lokale Ref)
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
        if universe in state.universes and 1 <= channel <= 512:
            state.universes[universe].set_channel(channel, max(0, min(255, value)))
        return jsonify({"ok": True})

    @app.route("/api/programmer/clear", methods=["POST"])
    def api_clear():
        _get_state().clear_programmer()
        return jsonify({"ok": True})


def _register_socketio(sio):

    @sio.on("connect")
    def on_connect():
        state = _get_state()
        emit("status", {"fixtures": len(state.get_patched_fixtures())})

    @sio.on("go")
    def on_go(data=None):
        stacks = _get_state().cue_stacks      # WEB-04: TOCTOU-sicher (lokale Ref)
        if stacks:
            stacks[0].go()
        sio.emit("ack", {"action": "go"})

    @sio.on("back")
    def on_back(data=None):
        stacks = _get_state().cue_stacks      # WEB-04: TOCTOU-sicher (lokale Ref)
        if stacks:
            stacks[0].back()
        sio.emit("ack", {"action": "back"})

    @sio.on("stop")
    def on_stop(data=None):
        stacks = _get_state().cue_stacks      # WEB-04: TOCTOU-sicher (lokale Ref)
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
    global _thread, _running
    if _running:
        return
    if not HAS_FLASK:
        raise RuntimeError("Flask / flask-socketio not installed")

    app, sio = create_app()
    _running = True
    _thread = threading.Thread(
        # allow_unsafe_werkzeug=True: neuere flask-socketio/werkzeug verweigern
        # den Dev-Server sonst mit RuntimeError ("not designed to run in
        # production") -> der WebServer-Thread starb still beim Start und das
        # Remote-Control war nie erreichbar (crash.log 2026-06). LightOS ist ein
        # lokaler LAN-Controller, kein Internet-Dienst -> der Dev-Server ist hier
        # bewusst akzeptabel.
        target=lambda: sio.run(app, host="0.0.0.0", port=port,
                               use_reloader=False, log_output=False,
                               allow_unsafe_werkzeug=True),
        daemon=True,
        name="WebServer"
    )
    _thread.start()
    return port


def stop_server():
    global _running
    _running = False
    if _socketio:
        _socketio.stop()
