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
        stacks = [{"name": s.name, "cues": len(s.cues)} for s in state.cue_stacks]
        return jsonify({
            "fixtures": len(fixtures),
            "universes": list(state.universes.keys()),
            "cue_stacks": stacks,
            "mock_mode": state.mock_mode,
        })

    @app.route("/api/go", methods=["POST"])
    def api_go():
        state = _get_state()
        if state.cue_stacks:
            state.cue_stacks[0].go()
        return jsonify({"ok": True})

    @app.route("/api/back", methods=["POST"])
    def api_back():
        state = _get_state()
        if state.cue_stacks:
            state.cue_stacks[0].back()
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
        level = float(data.get("level", 1.0))
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
        value = int(data.get("value", 0))
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
        state = _get_state()
        if state.cue_stacks:
            state.cue_stacks[0].go()
        sio.emit("ack", {"action": "go"})

    @sio.on("back")
    def on_back(data=None):
        state = _get_state()
        if state.cue_stacks:
            state.cue_stacks[0].back()
        sio.emit("ack", {"action": "back"})

    @sio.on("fader")
    def on_fader(data):
        slot = int(data.get("slot", 1))
        level = float(data.get("level", 1.0))
        state = _get_state()
        idx = slot - 1
        if 0 <= idx < len(state.playback_engine.executors):
            state.playback_engine.executors[idx].fader_value = max(0.0, min(1.0, level))

    @sio.on("blackout")
    def on_blackout(data):
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
