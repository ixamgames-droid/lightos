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
# WEB-11: woran der laufende Server gebunden ist. Der QR-Code der Handy-Konsole
# darf nur erscheinen, wenn das Handy ihn auch erreicht — „nur dieser PC"
# (127.0.0.1) heisst: kein Code, sondern der noetige Schritt.
_bind_host = ""
_port = 5000


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


def cors_allowlist(port: int = 5000, lan_ip: str | None = None,
                   weitere=()) -> list[str]:
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
    # WEB-11: ``weitere`` = die uebrigen eigenen Adressen dieses Rechners. Mit
    # mehreren Netzwerkkarten (WLAN + Kabel) ist die Adresse der Standard-Route
    # nicht unbedingt die, unter der das Handy den PC sieht; waehlt der Nutzer
    # im QR-Dialog die andere Karte, kaeme die Seite von einem Ursprung, den
    # die Liste nicht kennt — der Socket wuerde abgewiesen. Es bleiben eigene
    # Adressen dieses Rechners, also weiterhin kein fremder Ursprung.
    for andere in weitere or ():
        eintrag = f"http://{andere}:{port}"
        if andere and eintrag not in origins:
            origins.append(eintrag)
    return origins


def _eigene_adressen() -> list[str]:
    """WEB-11: alle brauchbaren IPv4-Adressen der aktiven Netzwerkkarten (nur
    gelesen). Nie eine Ausnahme — im Zweifel leer, dann gilt die bisherige
    Liste aus ``get_lan_ip``."""
    try:
        from src.web import handy_verbindung
        return [a.ip for a in handy_verbindung.brauchbare_adressen(
            handy_verbindung.lese_schnittstellen())]
    except Exception as e:
        print(f"[web] own addresses error: {type(e).__name__}")
        return []


def bind_host() -> str:
    """WEB-11: die Adresse, an die der LAUFENDE Server gebunden ist
    (``0.0.0.0`` = alle Karten, ``127.0.0.1`` = nur dieser PC); leer, wenn er
    nicht laeuft."""
    return _bind_host if _running else ""


def server_port() -> int:
    """WEB-11: der Port des laufenden Servers (sonst der Standard 5000)."""
    return int(_port or 5000)


def erlaubte_hosts() -> set[str] | None:
    """WEB-11: die Adressen, von denen der laufende Server eine Seite samt
    Socket annimmt (aus der Origin-Liste). ``None``, wenn kein Server laeuft
    oder die Liste nicht lesbar ist — dann wird nichts ausgesiebt."""
    app = _flask_app
    if app is None:
        return None
    try:
        from urllib.parse import urlsplit
        return {urlsplit(o).hostname or "" for o in
                app.config.get("CORS_ALLOWED_ORIGINS") or []}
    except Exception:
        return None


# WEB-11: Web-App-Manifest der Handy-Konsole. Farben wie die Seite selbst
# (Hintergrund des Pult-Designs). Bewusst OHNE Service Worker / Offline-Cache:
# der braeuchte HTTPS, das es im Heimnetz ohne Zertifikat nicht gibt — und die
# Seite ist ohne laufende Verbindung zum Pult ohnehin nutzlos.
KONSOLE_MANIFEST = {
    "name": "LightOS Handy-Konsole",
    "short_name": "LightOS",
    "description": "Fernbedienung für das LightOS-Lichtpult im eigenen Netz.",
    "lang": "de",
    "id": "/konsole",
    "start_url": "/konsole",
    "scope": "/",
    "display": "standalone",
    "orientation": "portrait",
    "background_color": "#0d1117",
    "theme_color": "#0d1117",
    "icons": [
        {"src": "/static/icons/konsole-192.png", "sizes": "192x192",
         "type": "image/png", "purpose": "any"},
        {"src": "/static/icons/konsole-512.png", "sizes": "512x512",
         "type": "image/png", "purpose": "any"},
        {"src": "/static/icons/konsole-maskable-512.png", "sizes": "512x512",
         "type": "image/png", "purpose": "maskable"},
    ],
}


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
    # WEB-12: zwei Schluesselarten — ``LIGHTOS_REMOTE_TOKEN`` oeffnet die
    # Handy-Konsole, ``LIGHTOS_FESTE_TOKEN`` die feste Fernbedienung.
    try:
        from src.web import remote_settings
        _flask_app.config["LIGHTOS_REMOTE_TOKEN"] = remote_settings.get_token()
        _flask_app.config["LIGHTOS_FESTE_TOKEN"] = remote_settings.get_feste_token()
    except Exception as e:
        print(f"[web] token init error: {type(e).__name__}")
        _flask_app.config["LIGHTOS_REMOTE_TOKEN"] = ""
        _flask_app.config["LIGHTOS_FESTE_TOKEN"] = ""
    _schluessel_aus_dem_log()
    # NET-03: konkrete Origin-Allowlist statt "*" (Drive-by-CSRF/-WebSocket). Die
    # Liste auch in der App-Config ablegen, damit UI/Tests sie einsehen koennen.
    origins = cors_allowlist(port, weitere=_eigene_adressen())
    _flask_app.config["CORS_ALLOWED_ORIGINS"] = origins
    _socketio = SocketIO(_flask_app, cors_allowed_origins=origins, async_mode="threading")

    _register_auth(_flask_app)
    _register_routes(_flask_app)
    _register_socketio(_socketio)
    return _flask_app, _socketio


class _SchluesselFilter:
    """WEB-12 (QA96-03): schwaerzt ``?k=…`` in den Zeilen, die Werkzeug je
    Anfrage protokolliert (``"GET /konsole?k=… HTTP/1.1" 200``). Sonst stand
    der Zugangsschluessel im Terminal, im Sitzungs-Log und im Diagnosepaket."""

    def filter(self, record) -> bool:
        try:
            from src.core.diagnose_log import schluessel_schwaerzen
            text = record.getMessage()
            neu = schluessel_schwaerzen(text)
            if neu != text:
                record.msg, record.args = neu, ()
        except Exception:
            pass
        return True


_FILTER = _SchluesselFilter()


def _schluessel_aus_dem_log() -> None:
    """Den Filter an die Logger haengen, die Anfragen protokollieren. Mehrfach
    aufrufbar (``create_app`` laeuft bei jedem Start)."""
    import logging
    for name in ("werkzeug", "engineio.server", "socketio.server"):
        logger = logging.getLogger(name)
        if _FILTER not in logger.filters:
            logger.addFilter(_FILTER)


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
        app.config["LIGHTOS_FESTE_TOKEN"] = remote_settings.get_feste_token()
    except Exception as e:
        print(f"[web] refresh_token error: {type(e).__name__}")


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


# ── WEB-12: getrennte Rechte ────────────────────────────────────────────────
#
# Zwei Schluesselarten (QA96-04): der Schluessel der Handy-Konsole oeffnet NUR
# die Handy-Konsole (was auf einer Handy-Seite liegt), der Schluessel der festen
# Fernbedienung NUR die feste Seite (GO, Executor-Fader, Blackout) — und auch
# die nur, solange sie unter „Erweitert" eingeschaltet ist. Roh-DMX ist ein
# eigener Schalter darunter. Eine Sitzung kann beide Rollen tragen (beide Links
# im selben Browser geoeffnet), jede nur ueber ihren eigenen Schluessel.

ROLLE_KONSOLE = "konsole"
ROLLE_FEST = "fest"

RECHT_KONSOLE = "konsole"       # Handy-Konsole
RECHT_FEST = "fest"             # feste Fernbedienung (eingeschaltet)
RECHT_ROH_DMX = "roh_dmx"       # feste Fernbedienung + Roh-DMX (eingeschaltet)

#: Ohne Anmeldung erreichbar: die Seiten, die den Handshake machen, und was
#: keine Daten traegt.
OFFENE_PFADE = ("/", "/konsole", "/konsole/manifest.webmanifest")

#: Jede Route hinter dem Gate mit dem Recht, das sie verlangt. Eine Route, die
#: hier fehlt, ist fuer jeden gesperrt (403) — eine neu hinzugefuegte Route
#: oeffnet so nie versehentlich die Fernsteuerung (Test: jede Regel der App
#: steht hier oder in ``OFFENE_PFADE``).
ROUTEN_RECHTE = {
    "/api/status": RECHT_FEST,
    "/api/go": RECHT_FEST,
    "/api/back": RECHT_FEST,
    "/api/stop": RECHT_FEST,
    "/api/blackout": RECHT_FEST,
    "/api/executor/<int:slot>/fader": RECHT_FEST,
    "/api/executor/<int:slot>/go": RECHT_FEST,
    "/api/programmer/clear": RECHT_FEST,
    "/api/channel/<int:universe>/<int:channel>": RECHT_ROH_DMX,
    "/api/vc/widgets": RECHT_KONSOLE,
    "/api/vc/widget/<kennung>/aktion": RECHT_KONSOLE,
    "/api/vc/konsole": RECHT_KONSOLE,
    "/api/vc/pult": RECHT_KONSOLE,
}

#: Socket-Ereignisse und ihr Recht (``connect`` verlangt irgendeine Rolle).
EREIGNIS_RECHTE = {
    "go": RECHT_FEST, "back": RECHT_FEST, "stop": RECHT_FEST,
    "fader": RECHT_FEST, "blackout": RECHT_FEST,
    "vc_hallo": RECHT_KONSOLE, "vc_aktion": RECHT_KONSOLE, "vc_pult": RECHT_KONSOLE,
}


def _rollen() -> set:
    """Die Rollen der aktuellen Sitzung — leer, wenn sie zu einer alten
    Auth-Epoche gehoert (Schluessel inzwischen erneuert). Wirft nie."""
    try:
        from src.web import remote_settings
        if session.get("epoch") != remote_settings.get_auth_epoch():
            return set()
        roh = session.get("rollen")
        if not isinstance(roh, list):
            return set()
        return {r for r in roh if r in (ROLLE_KONSOLE, ROLLE_FEST)}
    except Exception as e:
        print(f"[web] rollen error: {type(e).__name__}")
        return set()


def darf(recht: str, rollen=None) -> bool:
    """Hat die aktuelle Sitzung dieses Recht? Die Schalter werden bei JEDEM
    Aufruf gelesen — ein Ausschalten wirkt sofort, auch auf offene Sockets."""
    rollen = _rollen() if rollen is None else rollen
    try:
        from src.web import remote_settings
        if recht == RECHT_KONSOLE:
            return ROLLE_KONSOLE in rollen
        if recht == RECHT_FEST:
            return ROLLE_FEST in rollen and remote_settings.is_feste_seite_enabled()
        if recht == RECHT_ROH_DMX:
            return (ROLLE_FEST in rollen and remote_settings.is_feste_seite_enabled()
                    and remote_settings.is_roh_dmx_enabled())
    except Exception as e:
        print(f"[web] recht error: {type(e).__name__}")
    return False


def geraet() -> str:
    """WEB-12: Kennung dieses Geraets (Browser-Sitzung) — damit ein Handy nur
    den Blackout wieder aufhebt, den es selbst gesetzt hat. Leer ohne Sitzung."""
    try:
        g = session.get("geraet")
        return g if isinstance(g, str) else ""
    except Exception:
        return ""


def _register_auth(app):
    """NET-01 + WEB-12: Gate vor jeder Anfrage. Offen sind nur die Seiten, die
    den Handshake machen, und die statischen Dateien; jede andere Route braucht
    das Recht aus ``ROUTEN_RECHTE`` — im Zweifel 403."""

    @app.before_request
    def _auth_gate():
        try:
            path = request.path or "/"
            if path in OFFENE_PFADE or path.startswith("/static/"):
                return None
            regel = request.url_rule.rule if request.url_rule is not None else None
            recht = ROUTEN_RECHTE.get(regel)
            if recht is not None and darf(recht):
                return None
        except Exception as e:
            print(f"[web] auth gate error: {type(e).__name__}")
        return ("Forbidden", 403)


def _fehler(code: str, status: int):
    """WEB-12: einheitliche Fehlerantwort (QA96-17: kaputte Anfrage aendert
    nichts und sagt es)."""
    return jsonify({"ok": False, "fehler": code}), status


def _zahl(wert, unten: float, oben: float):
    """Eine endliche Zahl im Bereich [unten, oben] — oder None. ``bool`` und
    Text zaehlen nicht (ein ``true`` ist kein Fader-Wert). Nicht geklemmt:
    ausserhalb des Bereichs ist ungueltig."""
    import math
    if isinstance(wert, bool) or not isinstance(wert, (int, float)):
        return None
    if not math.isfinite(wert) or wert < unten or wert > oben:
        return None
    return wert


def _laser_gesperrt() -> bool:
    """Ist der Weg zum Laser zu? (Schalter „Laser vom Handy erlauben“ aus.)"""
    from src.core.laser import fern_freigabe
    return not fern_freigabe.laser_erlaubt()


def fest_blackout(daten) -> tuple[dict, int]:
    """WEB-12: Blackout der festen Fernbedienung (HTTP und Socket)."""
    if not isinstance(daten, dict) or not isinstance(daten.get("enabled"), bool):
        return {"ok": False, "fehler": "anfrage_ungueltig"}, 400
    from src.web import fern_pult
    antwort = fern_pult.blackout_setzen(_get_state().output_manager,
                                        daten["enabled"], geraet())
    if not antwort.get("ok"):
        return antwort, 403
    return {"ok": True, "blackout": bool(_get_state().output_manager.blackout)}, 200


def fest_fader(slot, daten) -> tuple[dict, int]:
    """WEB-12: Executor-Fader der festen Fernbedienung (HTTP und Socket)."""
    if not isinstance(daten, dict):
        return {"ok": False, "fehler": "anfrage_ungueltig"}, 400
    level = _zahl(daten.get("level"), 0.0, 1.0)
    if level is None or isinstance(slot, bool) or not isinstance(slot, int):
        return {"ok": False, "fehler": "wert_ungueltig"}, 400
    state = _get_state()
    executors = list(state.playback_engine.executors)
    idx = slot - 1
    if not 0 <= idx < len(executors):
        return {"ok": False, "fehler": "unbekannter_slot"}, 404
    ex = executors[idx]
    try:
        vorher = float(ex.fader_value)
    except (TypeError, ValueError):
        vorher = 0.0
    if level > vorher and _laser_gesperrt():
        from src.core.laser import fern_freigabe
        if fern_freigabe.executor_trifft_laser(state, ex):
            return {"ok": False, "fehler": "laser_gesperrt"}, 403
    ex.fader_value = float(level)
    return {"ok": True}, 200


def fest_transport(aktion: str) -> tuple[dict, int]:
    """WEB-12: GO/BACK/STOP der festen Fernbedienung (HTTP und Socket). GO und
    BACK auf eine Liste mit Laser-Inhalt nur mit dem Schalter; STOP immer."""
    if aktion != "stop" and _laser_gesperrt():
        from src.core.cueliste_ziel import transport_cueliste
        from src.core.laser import fern_freigabe
        state = _get_state()
        if fern_freigabe.cueliste_trifft_laser(state, transport_cueliste(state)):
            return {"ok": False, "fehler": "laser_gesperrt"}, 403
    return {"ok": True, **_transport_info(aktion)}, 200


def _register_routes(app):

    def _handshake():
        # NET-01 + WEB-12: ``?k=<schluessel>`` per constant-time-Vergleich gegen
        # BEIDE Schluesselarten. Jede gibt nur ihre eigene Rolle. Die Sitzung
        # bekommt die aktuelle Auth-Epoche gestempelt -> „Schluessel erneuern"
        # (epoch++) entwertet bestehende Sitzungen im Gate.
        try:
            k = request.args.get("k")
            if not k:
                return
            import secrets as _secrets
            from src.web import remote_settings
            epoche = remote_settings.get_auth_epoch()
            rollen = set(_rollen())             # leer bei alter Epoche
            for rolle, schluessel in (
                    (ROLLE_KONSOLE, app.config.get("LIGHTOS_REMOTE_TOKEN") or ""),
                    (ROLLE_FEST, app.config.get("LIGHTOS_FESTE_TOKEN") or "")):
                if schluessel and _secrets.compare_digest(str(k), str(schluessel)):
                    rollen.add(rolle)
                    session["rollen"] = sorted(rollen)
                    session["epoch"] = epoche
                    if not isinstance(session.get("geraet"), str):
                        session["geraet"] = _secrets.token_hex(8)
        except Exception as e:
            print(f"[web] handshake error: {type(e).__name__}")

    def _konsole_an() -> bool:
        try:
            from src.web import vc_remote
            return bool(vc_remote.ist_aktiv())
        except Exception:
            return False

    _HINWEIS = ("<!DOCTYPE html><html lang=\"de\"><head><meta charset=\"UTF-8\">"
                "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
                "<title>LightOS Remote</title><style>body{{background:#0d1117;color:#e6edf3;"
                "font-family:sans-serif;padding:32px 20px;line-height:1.5}}a{{color:#58a6ff}}"
                "</style></head><body><h1 style=\"font-size:20px\">LightOS Remote</h1>"
                "<p>{text}</p></body></html>")

    @app.after_request
    def _ohne_referer(antwort):
        # WEB-12: Seiten, die mit ``?k=`` geoeffnet werden (/ und /konsole),
        # geben die Adresse mit Schluessel nie als Referer weiter.
        if request.path in ("/", "/konsole"):
            antwort.headers["Referrer-Policy"] = "no-referrer"
        return antwort

    @app.route("/")
    def index():
        _handshake()
        rollen = _rollen()
        if darf(RECHT_FEST, rollen):
            # WEB-09: die feste Seite verlinkt auf die Handy-Konsole, wenn sie
            # eingeschaltet ist UND diese Sitzung sie oeffnen darf.
            return render_template(
                "index.html",
                konsole_an=_konsole_an() and darf(RECHT_KONSOLE, rollen),
                roh_dmx=darf(RECHT_ROH_DMX, rollen))
        if ROLLE_KONSOLE in rollen:
            # WEB-12: der Schluessel der Handy-Konsole oeffnet die feste Seite
            # nicht — er fuehrt zur Konsole.
            return _HINWEIS.format(
                text="Dieser Link gehört zur <a href=\"/konsole\">Handy-Konsole</a>.")
        if ROLLE_FEST in rollen:
            return _HINWEIS.format(
                text="Die feste Fernbedienung ist ausgeschaltet. Einschalten am Pult: "
                     "Ausgabe → Web-Remote: Verbindung & Token → Erweitert.")
        return _HINWEIS.format(
            text="Kein Zugang. Den Link oder QR-Code aus LightOS öffnen "
                 "(Ausgabe → Web-Remote: Verbindung & Token).")

    @app.route("/konsole")
    def konsole_seite():
        # WEB-09: die Handy-Konsole. Die Seite selbst traegt keine Daten der
        # Show — Seiten und Zustand holt sie ueber /api/vc/konsole und den Socket.
        _handshake()
        antwort = app.make_response(render_template(
            "konsole.html", feste_seite=darf(RECHT_FEST)))
        # Nie aus dem Zwischenspeicher: nach einem Update soll das Handy nicht
        # mit einer alten Seite gegen eine neue Schnittstelle sprechen.
        antwort.headers["Cache-Control"] = "no-store"
        # WEB-12: der Link mit Schluessel soll nicht als Referer weitergehen.
        antwort.headers["Referrer-Policy"] = "no-referrer"
        return antwort

    @app.route("/konsole/manifest.webmanifest")
    def konsole_manifest():
        # WEB-11: Web-App-Manifest fuer „Zum Startbildschirm hinzufuegen".
        # ★ ``start_url`` traegt KEINEN Schluessel: das Manifest ist ohne
        # Anmeldung abrufbar. Die Seite kommt vom Startbildschirm ueber ihre
        # bestehende Sitzung bzw. den im Handy gemerkten Schluessel wieder
        # hinein (s. konsole.html).
        import json as _json
        antwort = app.response_class(
            _json.dumps(KONSOLE_MANIFEST, ensure_ascii=False, indent=1),
            mimetype="application/manifest+json")
        antwort.headers["Cache-Control"] = "no-cache"
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

    # UI-66: GO/BACK/STOP treffen die Transport-Ziel-Liste (gewaehlte, wenn auf
    # einem Executor; sonst erster Executor der aktuellen Page mit Liste; ...) —
    # dieselbe wie Leertaste, Kommandozeile und OSC. Antwort nennt 'liste' +
    # 'licht' (+ 'warnung'). WEB-04/A3D-40: der Snapshot gegen ein gleichzeitiges
    # Leeren der Listen liegt in cueliste_ziel.
    @app.route("/api/go", methods=["POST"])
    def api_go():
        antwort, code = fest_transport("go")
        return jsonify(antwort), code

    @app.route("/api/back", methods=["POST"])
    def api_back():
        antwort, code = fest_transport("back")
        return jsonify(antwort), code

    @app.route("/api/stop", methods=["POST"])
    def api_stop():
        antwort, code = fest_transport("stop")
        return jsonify(antwort), code

    @app.route("/api/blackout", methods=["POST"])
    def api_blackout():
        # WEB-12 (QA96-17): ohne gueltiges ``enabled`` bleibt alles, wie es ist.
        antwort, code = fest_blackout(request.get_json(silent=True))
        return jsonify(antwort), code

    @app.route("/api/executor/<int:slot>/fader", methods=["POST"])
    def api_fader(slot: int):
        antwort, code = fest_fader(slot, request.get_json(silent=True))
        return jsonify(antwort), code

    @app.route("/api/executor/<int:slot>/go", methods=["POST"])
    def api_exec_go(slot: int):
        state = _get_state()
        executors = list(state.playback_engine.executors)
        idx = slot - 1
        if not 0 <= idx < len(executors):
            return _fehler("unbekannter_slot", 404)
        if _laser_gesperrt():
            from src.core.laser import fern_freigabe
            if fern_freigabe.executor_trifft_laser(state, executors[idx]):
                return _fehler("laser_gesperrt", 403)
        executors[idx].press_btn("go")
        return jsonify({"ok": True})

    @app.route("/api/channel/<int:universe>/<int:channel>", methods=["POST"])
    def api_channel(universe: int, channel: int):
        data = request.get_json(silent=True)
        wert = _zahl(data.get("value") if isinstance(data, dict) else None, 0, 255)
        if wert is None or wert != int(wert):
            return _fehler("wert_ungueltig", 400)
        state = _get_state()
        if not 1 <= channel <= 512 or universe not in state.universes:
            return _fehler("unbekannter_kanal", 404)
        if _laser_gesperrt():
            from src.core.laser import fern_freigabe
            if fern_freigabe.adresse_ist_laser(state, universe, channel):
                return _fehler("laser_gesperrt", 403)
        # WEB-01: nicht mehr direkt ins Live-Universe (der 44-Hz-Renderer
        # ueberschriebe gepatchte Kanaele jeden Frame), sondern ueber die
        # Input-Override-Schicht — haelt als diskreter Einzelbefehl (REPLACE,
        # vom Source-Timeout ausgenommen).
        state.set_input_channel(universe, channel, int(wert), source="web")
        return jsonify({"ok": True})

    @app.route("/api/programmer/clear", methods=["POST"])
    def api_clear():
        _get_state().clear_programmer()
        return jsonify({"ok": True})

    # ── WEB-08: VC-Widgets ueber ihre Kennung ─────────────────────────────────
    # Grundlage der Handy-Konsole (WEB-07). Recht ``konsole`` (WEB-12) und
    # zusaetzlich standardmaessig AUS (``remote_settings.vc_remote_enabled``).
    # Die Aktion laeuft im UI-Thread (``VCFernbedienung``), nie hier.

    @app.route("/api/vc/widgets")
    def api_vc_widgets():
        from src.web import vc_remote
        return jsonify(vc_remote.widget_liste())

    @app.route("/api/vc/widget/<kennung>/aktion", methods=["POST"])
    def api_vc_widget_aktion(kennung: str):
        from src.web import vc_remote
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get("aktion"), str):
            antwort = {"ok": False, "fehler": "anfrage_ungueltig"}
        elif data["aktion"] in ("druecken", "loslassen"):
            # WEB-12: Halten geht nur ueber den Socket — nur dort laesst eine
            # abgerissene Verbindung los, was sie haelt. Ueber HTTP ein Tipp.
            antwort = {"ok": False, "fehler": "nur_ueber_socket"}
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
            antwort = vc_remote.pult(gm=data.get("gm"), blackout=data.get("blackout"),
                                     geraet=geraet())
        return jsonify(antwort), vc_remote.status_fuer(antwort)


def _register_socketio(sio):

    from flask_socketio import join_room, disconnect
    from src.web import vc_remote

    def _berechtigt(recht: str):
        """WEB-12 (QA96-20): JEDES Ereignis prueft selbst — eine offene
        Verbindung laeuft nicht mehr durch das HTTP-Gate. Gilt die Sitzung gar
        nicht mehr (Schluessel erneuert), wird getrennt. Rueckgabe: None = darf,
        sonst die Fehlerantwort."""
        rollen = _rollen()
        if not rollen:
            try:
                disconnect()
            except Exception:
                pass
            return {"ok": False, "fehler": "kein_zugang"}
        if not darf(recht, rollen):
            return {"ok": False, "fehler": "kein_recht"}
        return None

    @sio.on("connect")
    def on_connect(auth=None):
        # NET-01/NET-03: unauthentisierte WebSocket-Verbindung ablehnen — das ist
        # zugleich der Riegel gegen Drive-by-WebSockets (der CORS-Check greift bei
        # WS nicht zuverlaessig). CDX-24: auch die Epoche (in ``_rollen``).
        try:
            if not _rollen():
                return False
        except Exception as e:
            print(f"[web] socket connect gate error: {type(e).__name__}")
            return False
        if darf(RECHT_FEST):
            state = _get_state()
            emit("status", {"fixtures": len(state.get_patched_fixtures())})

    # ── feste Fernbedienung ───────────────────────────────────────────────────
    # WEB-12: Antwort nur an den Absender (frueher ``sio.emit`` an ALLE —
    # auch an die Handys der Konsole) und als Rueckgabe fuer den Rueckruf.

    def _transport(aktion):
        nein = _berechtigt(RECHT_FEST)
        if nein:
            return nein
        antwort, _code = fest_transport(aktion)
        emit("ack", {"action": aktion, **antwort})
        return antwort

    @sio.on("go")
    def on_go(data=None):
        return _transport("go")

    @sio.on("back")
    def on_back(data=None):
        return _transport("back")

    @sio.on("stop")
    def on_stop(data=None):
        return _transport("stop")

    @sio.on("fader")
    def on_fader(data=None):
        nein = _berechtigt(RECHT_FEST)
        if nein:
            return nein
        if not isinstance(data, dict):
            return {"ok": False, "fehler": "anfrage_ungueltig"}
        return fest_fader(data.get("slot"), data)[0]

    @sio.on("blackout")
    def on_blackout(data=None):
        nein = _berechtigt(RECHT_FEST)
        if nein:
            return nein
        return fest_blackout(data)[0]

    # ── WEB-09: Handy-Konsole ueber den Socket ────────────────────────────────
    #
    # Rueckmeldung Pult -> Handy: die Bruecke der Konsole gibt Aenderungen an
    # ``vc_remote.melde`` ab; von hier gehen sie an den Raum der Zuschauer.
    # Aktionen Handy -> Pult: dieselbe Pruefkette wie ueber HTTP
    # (``vc_remote.widget_aktion``), nur ohne den Aufbau einer Anfrage je
    # Fader-Schritt.

    RAUM = "vc_konsole"
    # Je Verbindung und Widget die Nummer des letzten Fader-Werts. Socket.IO
    # arbeitet die Ereignisse einer Verbindung in eigenen Threads ab: ohne die
    # Nummer koennte ein aelterer Wert den neueren ueberholen und der Fader am
    # Ende auf einem Zwischenstand stehen.
    folge: dict = {}
    folge_lock = threading.Lock()
    # WEB-12: Obergrenze der gemerkten Nummern je Verbindung — eine Flut
    # erfundener Kennungen belegt sonst Speicher bis zum Abbau der Verbindung.
    FOLGE_MAX_JE_SID = 1024
    sio.lightos_vc_folge = folge            # nur lesend, fuer Tests

    def _senden(ereignis, daten):
        sio.emit(ereignis, daten, to=RAUM)

    vc_remote.setze_sender(_senden)

    def _veraltet(sid, schluessel, nummer) -> bool:
        """True, wenn zu ``schluessel`` schon ein Wert mit hoeherer Nummer kam."""
        if isinstance(nummer, bool) or not isinstance(nummer, (int, float)):
            return False                    # ohne Nummer: immer ausfuehren
        with folge_lock:
            je_sid = folge.setdefault(sid, {})
            if nummer <= je_sid.get(schluessel, float("-inf")):
                return True
            if schluessel in je_sid or len(je_sid) < FOLGE_MAX_JE_SID:
                je_sid[schluessel] = nummer
            return False

    @sio.on("vc_hallo")
    def on_vc_hallo(data=None):
        """Das Handy zeigt die Konsole an: als Zuschauer fuehren und den ganzen
        Stand schicken. Kommt nach JEDEM Verbinden — das ist der vollstaendige
        Abgleich nach einer Wiederverbindung."""
        nein = _berechtigt(RECHT_KONSOLE)
        if nein:
            return nein
        join_room(RAUM)
        vc_remote.zuschauer_dazu(request.sid)   # VOR dem Abgleich, s. Bruecke
        stand = vc_remote.konsole()
        emit("vc_konsole", stand)
        return {"ok": True}

    @sio.on("vc_aktion")
    def on_vc_aktion(data=None):
        nein = _berechtigt(RECHT_KONSOLE)
        if nein:
            return nein
        if not isinstance(data, dict):
            return {"ok": False, "fehler": "anfrage_ungueltig"}
        kennung, aktion = data.get("id"), data.get("aktion")
        # Nur Text kommt weiter: eine Liste oder ein Objekt als Kennung taugte
        # nicht einmal als Schluessel der Folgenummern (TypeError im Handler).
        if not isinstance(kennung, str) or not isinstance(aktion, str):
            return {"ok": False, "fehler": "anfrage_ungueltig"}
        # WEB-12: Kennung VOR jeder Buchfuehrung pruefen — eine erfundene,
        # beliebig lange Kennung legt sonst einen Eintrag in ``folge`` an und
        # einen Auftrag in den UI-Thread.
        from src.ui.virtualconsole.vc_widget import kennung_gueltig
        if not kennung_gueltig(kennung):
            return {"ok": False, "fehler": "anfrage_ungueltig"}
        if aktion == "setzen" and _veraltet(request.sid, kennung, data.get("n")):
            return {"ok": True, "veraltet": True}
        if aktion == "druecken":
            # WEB-12 (Codex #1030/#1039/#1041): gehalten wird je Halter
            # gezaehlt — ein Druck auf eine Taste, die schon das Pult oder ein
            # anderes Handy haelt, macht dieses Handy nicht zum Halter, der sie
            # beim Loslassen oder Abreissen wieder loslaesst.
            return vc_remote.halten(request.sid, kennung)
        if aktion == "loslassen":
            return vc_remote.loslassen_von(request.sid, kennung)
        return vc_remote.widget_aktion(kennung, aktion, data.get("wert"))

    @sio.on("vc_pult")
    def on_vc_pult(data=None):
        nein = _berechtigt(RECHT_KONSOLE)
        if nein:
            return nein
        if not isinstance(data, dict):
            return {"ok": False, "fehler": "anfrage_ungueltig"}
        if "gm" in data and _veraltet(request.sid, "#gm", data.get("n")):
            return {"ok": True, "veraltet": True}
        return vc_remote.pult(gm=data.get("gm"), blackout=data.get("blackout"),
                              geraet=geraet())

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
    global _thread, _running, _server, _bind_host, _port
    if _running:
        return
    if not HAS_FLASK:
        raise RuntimeError("Flask / flask-socketio not installed")

    app, _sio = create_app(port)   # _sio == _socketio-Global (Middleware sitzt an app)
    # NET-01: Bind-Host am Toggle 'LAN-/Handy-Remote' ausrichten. AN -> 0.0.0.0
    # (das Handy im LAN erreicht es, der Schluessel schuetzt). AUS (ab Werk,
    # WEB-12) -> 127.0.0.1 (nur der Host selbst, kein LAN-Zugriff).
    # WEB-12: im Zweifel nur dieser PC (die Einstellung ist ab Werk aus).
    host = "127.0.0.1"
    try:
        from src.web import remote_settings
        if remote_settings.is_lan_remote_enabled():
            host = "0.0.0.0"
    except Exception as e:
        print(f"[web] lan-remote flag read error: {type(e).__name__}")
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
    _bind_host, _port = host, int(port)
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
    global _running, _server, _thread, _flask_app, _socketio, _bind_host, _port
    _running = False
    _bind_host, _port = "", 5000
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
        # WEB-12: wer einen Blackout gesetzt hat, gilt mit dem Server nicht mehr.
        from src.web import fern_pult
        fern_pult.vergessen()
    except Exception as e:
        print(f"[web] vc_remote shutdown error: {e}")
    # CDX-24: Globals mit abraeumen — sonst meldet `refresh_running_token()` auch
    # nach dem Ausschalten noch Erfolg (`_flask_app` blieb gesetzt), und der Dialog
    # behauptet „Neues Token aktiv" fuer einen Server, der gar nicht laeuft.
    _flask_app = None
    _socketio = None
