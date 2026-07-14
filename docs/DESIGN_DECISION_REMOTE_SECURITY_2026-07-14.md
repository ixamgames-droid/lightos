# Design Decision — Remote-Absicherung (WEB-01 · NET-03 · NET-01)

Datum: 2026-07-14 · Branch: `auto/remote-security`

LightOS hat zwei Fernsteuer-Eingaenge: das Web-Remote (Flask + SocketIO, HTTP)
und den OSC-Server (UDP). Beide waren bisher ungeschuetzt und teils funktional
kaputt. Diese Runde macht sie **per Default sicher, offline-faehig und ohne den
Handy-Workflow zu brechen**. Umgesetzt in strikter Reihenfolge WEB-01 → NET-03 →
NET-01 (funktional entkoppelt zuerst, groesster Diff zuletzt).

## WEB-01 — Renderer-Bypass des Web-/OSC-Einzelkanals (funktional)

**Problem:** `/api/channel` (`web/app.py`) und `/lightos/ch` (`osc_server.py`)
riefen `universe.set_channel()` **direkt** auf. Der zentrale 44-Hz-Renderer
(`app_state._render_frame`) berechnet gepatchte Kanaele aber jeden Frame neu und
ueberschrieb den Wert sofort wieder — er flackerte und hielt nur ~1 Frame (~23 ms).

**Entscheidung:** Beide Eingaenge gehen jetzt ueber die **bereits existierende
Input-Override-Schicht** (`input_layer`, gemischt in `_render_frame` Schritt
4b-Input). Neue Methode `AppState.set_input_channel(universe, channel, value,
source='remote')`:

- schreibt unter `_input_lock` in `input_layer[universe][channel]`;
- vermerkt den Kanal zusaetzlich in `_remote_input_channels` (`{univ: set(ch)}`).

Der Renderer behandelt diese Kanaele **abweichend von einem Art-Net/sACN-Stream**:

- **immer REPLACE** — unabhaengig vom Per-Universe-Merge-Mode (ein diskreter
  Befehl ersetzt, er mischt nicht HTP);
- **vom NET-05-Stale-Timeout ausgenommen** — ein Web-POST ist ein diskreter
  Einzelbefehl, kein Stream, und darf nach ~2,5 s nicht verworfen werden. Dazu
  werden beim Source-Timeout nur die Stream-Kanaele einer Universe entfernt, die
  Remote-Kanaele bleiben stehen. Remote-only-Universen setzen gar kein
  `input_last_seen` und altern damit nie.

Auf einer **gemischten Universe** (Art-Net + Web/OSC auf demselben Universe, bei
Davids Ein-Universe-Rig der Normalfall) verfaellt der Stream-Anteil bei Stale
korrekt, der Web-Anteil bleibt.

`clear_programmer()` (globaler Clear, `fid is None`) ist der **Release-Pfad** und
raeumt die Web/OSC-Werte via neuem `clear_remote_input()` mit; Art-Net/sACN-Kanaele
derselben Universe bleiben unberuehrt. Range-Guards (`universe in universes`,
`1<=channel<=512`, `0<=value<=255`) und Never-crash-Stil bleiben.

Verdrahtung: `web/app.py:api_channel` → `state.set_input_channel(..., 'web')`,
`osc_server._handle_channel` → `set_input_channel(..., 'osc')`.

## NET-03 — CORS-Allowlist statt `"*"`

`SocketIO(..., cors_allowed_origins="*")` erlaubte JEDER Website im Browser des
Nutzers fetch/WebSocket-Zugriff aufs LAN-Remote (Drive-by). Da der Server auf der
bekannten LAN-IP:Port haengt, sind die legitimen Origins bekannt: neue Funktion
`cors_allowlist(port, lan_ip=None)` liefert
`[http://<lan-ip>:<port>, http://127.0.0.1:<port>, http://localhost:<port>]`
(offline via `get_lan_ip`, nur stdlib). `create_app(port)` uebergibt die Liste an
SocketIO und legt sie unter `app.config["CORS_ALLOWED_ORIGINS"]` ab. OSC (UDP) ist
nicht betroffen.

## NET-01 — Token-Auth + Bind

**Web (HTTP+SocketIO):** Bind **bleibt 0.0.0.0** (127.0.0.1 wuerde das Handy
aussperren), geschuetzt durch **ein pro Setup persistiertes Token**:

- `src/web/remote_settings.py` persistiert Token + Toggles in
  `%APPDATA%/LightOS/ui_prefs.json` (Key `remote`; Pfad via `LIGHTOS_PREFS_DIR`
  fuer Tests umlenkbar). Token = `secrets.token_urlsafe(6)` (kurz & tippbar).
  `get_token()` erzeugt+speichert beim ersten Aufruf, `regenerate_token()` =
  'Token neu erzeugen'.
- `@before_request`-Gate (never-crash): alle Routen ausser Allowlist (`/`,
  `/static/…`) → 403, wenn `session['authed']` nicht True.
- `/`-Route: `request.args.get('k')` per `secrets.compare_digest` gegen das
  Token; Treffer → `session['authed']=True`. Cookie `HttpOnly` + `SameSite=Strict`.
- SocketIO-`connect`: unauthentisierte Verbindung → `return False` (Riegel gegen
  Drive-by-WebSockets, wo CORS nicht zuverlaessig greift).
- Toggle **'LAN-/Handy-Remote'** (Default AN, sicher weil Token davor): AUS →
  `start_server` bindet 127.0.0.1 statt 0.0.0.0. Der Verbindungs-Dialog
  (`main_window`) zeigt Token + Direkt-Link `http://<lan-ip>:<port>/?k=<token>`.

**OSC (UDP):** `OscServer.__init__` Default-`ip` = **`127.0.0.1`** (Loopback);
neuer `set_bind_ip()`. Der Startup-Aufrufer (`main_window._toggle_osc_server`)
bindet 0.0.0.0 nur, wenn der sichtbare Toggle **'OSC ueber Netzwerk'** (Default
AUS) gesetzt ist.

## FOLLOW-UP (bewusst NICHT in dieser Runde)

- **QR-Bild** des Direkt-Links (jetzt nur tippbares Token + URL, keine externe
  Dependency / kein QR-Generator).
- **OSC-Source-Allowlist** (per-IP-Filter des UDP-Eingangs) — OSC bleibt vorerst
  nur ueber den Loopback-/LAN-Toggle abgesichert.
- **Token-Rotation pro Start** (aktuell pro Setup persistiert + manuelles
  'neu erzeugen').
- Voller **UI-Toggle-Dialog** (NET-02) fuer die beiden Settings-Flags — die Flags
  sind persistiert und werden respektiert, die dedizierte UI-Einbindung liefert
  die Integrationsrunde.

## Tests

- `tests/test_web_osc_input_channel.py` (WEB-01): Wert haelt nach `_render_frame`
  auf gepatchtem Kanal, REPLACE schlaegt hoeheren Show-Wert, ueberlebt Stale-
  Timeout, gemischte Universe (Art-Net verfaellt / Web bleibt), Clear-Release.
- `tests/test_remote_auth.py` (NET-01/03): /api ohne Session → 403; Handshake →
  authed → /api erlaubt; falsches Token → 403; SocketIO unauth abgelehnt / authed
  akzeptiert; OSC-Default-ip 127.0.0.1; CORS-Allowlist ist Liste ≠ `*`;
  Token-Persistenz/-Rotation, Toggle-Defaults.
- `tests/test_web_app.py` an das Auth-Gate + `set_input_channel` angepasst.
