"""Spawn-sichere Bootstrap-Schicht fuer alle ``tools/build_*.py``-Generatoren (DEMO-02).

Problem (nur Windows):
    Importiert ein Generator ``app_state``/``output_manager`` und ist in der
    Output-Konfiguration (``universes.json``, App-Datenordner) ein Enttec-Port eingetragen, dann
    erzeugt ``get_state()`` ueber ``apply_output_config() -> add_enttec()`` einen
    :class:`~src.core.dmx.serial_process.EnttecProcessProxy`. Der startet einen
    Kindprozess mit ``multiprocessing`` im ``spawn``-Modus. ``spawn`` RE-IMPORTIERT
    auf Windows das Hauptmodul des Prozesses als ``__mp_main__`` — bei einem
    Generator OHNE ``if __name__ == "__main__":``-Guard laeuft dadurch der gesamte
    Build-Code EIN ZWEITES MAL im Kindprozess. Zwei Prozesse bauen die Show
    gleichzeitig auf derselben SQLite-Show-DB; der FLD-FID-Guard in
    ``AppState.add_fixture`` vergibt fids neu, die der jeweils ANDERE Prozess gerade
    persistiert hat -> nur ein TEIL der Fixtures landet im Patch.
    Symptom: ``python -c "import tools.build_x"`` baut sauber, ``python
    tools/build_x.py`` (Datei = Hauptmodul) nur teilweise.

Fix (Single-Point, kein Guard in ~40 Dateien noetig):
    Dieses Modul setzt — BEIM IMPORT, also bevor ``app_state``/``output_manager``
    geladen werden — dieselben sicheren Umgebungsschalter, die die Test-``conftest.py``
    setzt:

      * ``LIGHTOS_SERIAL_INPROC=1``    -> ``_make_enttec_device`` nimmt den direkten
        In-Prozess-``EnttecPro`` statt des prozess-isolierten Proxys: KEIN
        ``multiprocessing``-``spawn`` mehr -> kein ``__mp_main__``-Re-Import.
      * ``LIGHTOS_NO_OUTPUT_THREAD=1`` -> ``get_state()`` startet den 44-Hz-Output-
        Thread gar nicht erst (ein Generator braucht keine Live-Ausgabe; der Thread
        koennte sonst noch im Prozess senden, waehrend die Show geschrieben wird).
      * ``LIGHTOS_NO_AUDIO_AUTOSTART=1`` -> kein WASAPI-Loopback-Capture im
        Build-Lauf (analog conftest; rein vorsorglich).
      * ``LIGHTOS_SHOW_DB=<tmp>/lightos_gen_<skript>_<pid>.db`` -> isolierte
        Wegwerf-Show-DB statt der geteilten ``current_show.db`` (App-Datenordner)
        (STAB-CURSHOW (a): Generator-Laeufe duerfen Davids echten Show-Zustand
        nicht anfassen; Muster aus ``build_mega_arena_2026.py`` verallgemeinert).
      * ``LIGHTOS_UNIVERSES_JSON=<tmp>/lightos_gen_<skript>_<pid>_universes.json``
        -> eine Ausgabe-Konfiguration, die es nicht gibt (TOOL-19). ``get_state()``
        ruft ``apply_output_config()`` IMMER auf, und das richtete bisher ein, was
        in der ECHTEN ``universes.json`` steht: bei einem Enttec-Eintrag oeffnete
        ein Generator-Lauf den echten seriellen Port, bei Art-Net/sACN die
        Sende-Sockets. ``LIGHTOS_NO_OUTPUT_THREAD`` verhindert nur den Sende-Thread,
        nicht das Oeffnen. Die Datei wird nie angelegt — fehlt sie, richtet
        ``apply_output_config()`` nichts ein.

    ``setdefault`` respektiert eine bereits gesetzte Umgebung (z. B. wenn jemand den
    Generator bewusst mit echtem Output-Prozess oder gegen eine echte DB laufen
    lassen will).

Verwendung:
    Als ALLERERSTE Zeile eines Generators (vor jedem ``src.core``-Import)::

        import _gen_env  # noqa: F401  (setzt spawn-sichere Env-Schalter)

    Die gemeinsame Boilerplate ``tools/_builder.py`` importiert dieses Modul bereits
    automatisch; ``_builder``-basierte Generatoren sind damit ohne weiteres Zutun
    geschuetzt. Generatoren mit eigener Boilerplate fuegen die eine Import-Zeile
    oben hinzu (Beispiele: ``build_demo_show_full.py``, ``build_test_show.py``).
"""
import os
import sys
import tempfile

# Robust gegen verschobene Imports: setzt die Schalter sofort beim Import dieses
# Moduls. setdefault -> eine bereits gesetzte (bewusste) Umgebung gewinnt.
os.environ.setdefault("LIGHTOS_SERIAL_INPROC", "1")
os.environ.setdefault("LIGHTOS_NO_OUTPUT_THREAD", "1")
os.environ.setdefault("LIGHTOS_NO_AUDIO_AUTOSTART", "1")
# Headless: kein echtes Qt-Display fuer einen reinen JSON/DB-Build-Lauf.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# STAB-CURSHOW (a): Generatoren/Tools duerfen nie auf der geteilten
# Show-DB (App-Datenordner) arbeiten — ShowBuilder(reset=True) macht dort reset_show()
# und patcht hinein, parallele Laeufe (oder eine offene App) desyncen die DB.
# Isolierte Wegwerf-DB pro Lauf; Skript-Stem + PID, damit zwei gleichzeitig
# laufende Generatoren sich keine Temp-DB teilen.
_stem = os.path.splitext(os.path.basename(sys.argv[0] or ""))[0] or "interactive"
_stem = "".join(c if (c.isalnum() or c in "-_") else "_" for c in _stem)
os.environ.setdefault(
    "LIGHTOS_SHOW_DB",
    os.path.join(tempfile.gettempdir(), f"lightos_gen_{_stem}_{os.getpid()}.db"),
)
# QA-83: dasselbe fuer den VC-Asset-Cache. ``import_to_cache`` (Galerie-Bilder,
# z. B. build_mega_arena_2026.py) und das Selbstpruef-Laden der fertigen Show
# legten die Bilder sonst in den ECHTEN Datenordner. Die Show bettet sie beim
# Speichern ohnehin ein; die App entpackt sie beim Laden in ihren Cache.
os.environ.setdefault(
    "LIGHTOS_VC_ASSETS_DIR",
    os.path.join(tempfile.gettempdir(), f"lightos_gen_{_stem}_{os.getpid()}_vc_assets"),
)
# TOOL-19: kein Generator oeffnet einen echten DMX-Ausgang. ``get_state()``
# wendet die Ausgabe-Konfiguration an, sobald es sie findet — also zeigt die
# Variable auf eine Datei, die es nicht gibt (sie wird auch nie angelegt).
# ``setdefault`` wie bei den Schaltern oben: ein schon gesetzter Wert ist eine
# bewusste Umlenkung (Testlauf, Bild-Sandbox, ``verify_stage_reload``) und
# gewinnt. Die Startskripte setzen die Variable nicht.
_UNIVERSES_VOR_DER_UMLENKUNG = os.environ.get("LIGHTOS_UNIVERSES_JSON") or None
os.environ.setdefault(
    "LIGHTOS_UNIVERSES_JSON",
    os.path.join(tempfile.gettempdir(),
                 f"lightos_gen_{_stem}_{os.getpid()}_universes.json"),
)


def echte_universes_json() -> str:
    """Pfad der Ausgabe-Konfiguration, die OHNE die Umlenkung oben gelten wuerde
    — nur zum LESEN.

    Die Umlenkung trifft jeden Leser von ``user_data_file("universes.json")``,
    auch den, der gar keinen Ausgang oeffnen, sondern nur nachsehen will:
    ``build_spot90_testshow.py`` waehlt aus der echten Konfiguration das
    Universum mit Ausgang und prueft seinen Patch am Ende dagegen. Mit der
    Umlenkung fiel es still auf Universum 1 zurueck, und die Schlusspruefung
    las dieselbe fehlende Datei — am Rig mit dem Ausgang auf Universum 3 waere
    eine Test-Show entstanden, die nichts sendet (Codex-Review #1017).

    Hatte der Aufrufer die Variable selbst gesetzt (Testlauf, Sandbox), ist
    SEIN Wert die gemeinte Konfiguration."""
    if _UNIVERSES_VOR_DER_UMLENKUNG:
        return _UNIVERSES_VOR_DER_UMLENKUNG
    from src.core.paths import app_data_dir
    return os.path.join(app_data_dir(), "universes.json")
