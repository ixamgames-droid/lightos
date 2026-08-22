"""Uhr-Vorspann fuer den Zeitbomben-Waechter (QA-63).

Liegt dieses Verzeichnis im ``PYTHONPATH`` und ist ``LIGHTOS_ZEITSPRUNG_TAGE``
gesetzt, sieht der ganze Prozess die Systemuhr um so viele Tage vorgerueckt —
**bevor irgendein Modul importiert ist**. Genau darauf kommt es an:
Produktionsmodule rechnen gleitende Schwellen oft schon beim Import aus, und
viele Testdateien machen ``from datetime import date`` ganz oben. Ein
pytest-Plugin oder eine Fixture kaeme dafuer zu spaet — ``sitecustomize`` laeuft
in ``site.py``, also vor der ersten Zeile Anwendungscode.

Zwei Staerken, ueber ``LIGHTOS_ZEITSPRUNG_UHR`` gewaehlt:

``datum`` (Vorgabe)
    Nur ``datetime.datetime.now/utcnow/today`` und ``datetime.date.today``.
    Das ist die Quelle, aus der ``collect_crash_report._cold_before()`` seine
    30-Tage-Grenze zieht — also die Schwelle, an der QA-62 detoniert ist.

``alle``
    Zusaetzlich ``time.time`` und ``time.localtime/gmtime`` ohne Argument.

★★ **Warum ``time.time`` NICHT in der Vorgabe steckt — gemessen 2026-08-22 an
der ganzen Suite.** Dateien tragen ihre ``st_mtime`` aus der ECHTEN Uhr des
Betriebssystems; die laesst sich nicht mitverschieben. Wer „wie alt ist diese
Datei" als ``time.time() - st_mtime`` rechnet, sieht mit verschobener
``time.time`` jede eben erst geschriebene Datei zehn Jahre alt. Drei Dateien
werden dadurch rot, ohne im Entferntesten Zeitbomben zu sein:

* ``tests/test_vc_asset_gc.py::test_dedup_write_refreshes_mtime``
* ``tests/test_janitor.py::ArtifactAgeTest::test_stale_by_mtime``
* ``tests/test_qa58_bibliothek_schema_unberuehrt.py`` (raeumt „alte Leichen" ab)

Und sie waren die EINZIGEN Funde, die ``time.time`` beitrug: im selben
Streifzug (615 Dateien) blieb danach nichts uebrig, was eine Zeitbombe gewesen
waere. Drei sichere Fehlalarme gegen null Treffer — und ein Waechter, der
Fehlalarme liefert, wird abgeschaltet. Darum ist ``alle`` eine bewusste Wahl
fuer einen Streifzug und nicht die Vorgabe des Gates.

★ Die Falle beim Bauen (ebenfalls gemessen): ``date.today()`` ist in CPython
NICHT unabhaengig von ``time.time`` — ``datetime_date_today`` ruft das
``time``-Modul auf. Eine Fassung, die BEIDES um denselben Betrag verschob,
lieferte ``date.today()`` doppelt verschoben (bei +400 Tagen 2028-10-30 statt
2027-09-26). ``_VorgerueckteDate.today()`` leitet sich hier darum aus
``_echt_datetime.now()`` ab — das haengt am C-Systemtakt, nicht am gepatchten
``time.time`` — und der Sprung wird genau einmal addiert.

★ Was in KEINER Staerke angefasst wird: ``time.monotonic`` und
``time.perf_counter``. Sie messen Zeitspannen (Timeouts, Qt-Timer,
pytest-timeout). Sie mitzuziehen aendert an Differenzen nichts und kann nur
schaden.

Ohne die Umgebungsvariable tut diese Datei nichts — sie darf deshalb gefahrlos
in einem ``PYTHONPATH`` stehenbleiben.
"""
import os

_tage = os.environ.get("LIGHTOS_ZEITSPRUNG_TAGE", "").strip()
if _tage not in ("", "0"):
    import datetime as _dt
    import sys as _sys

    _delta = _dt.timedelta(days=int(_tage))
    _echt_date, _echt_datetime = _dt.date, _dt.datetime

    class _VorgerueckteDatetime(_echt_datetime):
        @classmethod
        def now(cls, tz=None):
            return _echt_datetime.now(tz) + _delta

        @classmethod
        def utcnow(cls):
            return _echt_datetime.utcnow() + _delta

        @classmethod
        def today(cls):
            return _echt_datetime.now() + _delta

    class _VorgerueckteDate(_echt_date):
        @classmethod
        def today(cls):
            # NICHT _echt_date.today() — das laeuft ueber time.time und waere
            # in der Staerke "alle" schon verschoben (s. Docstring).
            return (_echt_datetime.now() + _delta).date()

    _dt.date = _VorgerueckteDate
    _dt.datetime = _VorgerueckteDatetime

    _staerke = os.environ.get("LIGHTOS_ZEITSPRUNG_UHR", "datum").strip() or "datum"
    if _staerke == "alle":
        import time as _time
        _sekunden = _delta.total_seconds()
        _echt_time = _time.time
        _echt_localtime = _time.localtime
        _echt_gmtime = _time.gmtime

        def _zeit():
            return _echt_time() + _sekunden

        _time.time = _zeit
        _time.localtime = lambda s=None: _echt_localtime(_zeit() if s is None else s)
        _time.gmtime = lambda s=None: _echt_gmtime(_zeit() if s is None else s)

    # Beleg IM Prozess, dass der Vorspann gelaufen ist. ``zeitbomben_gate``
    # rechnet damit den WIRKLICHEN Kalendertag zurueck, wenn es selbst schon
    # unter vorgerueckter Uhr laeuft (``echt_heute()``) — die Variable
    # ``LIGHTOS_ZEITSPRUNG_TAGE`` allein wuerde das auch dann behaupten, wenn
    # sie jemand ohne diesen Vorspann setzt.
    os.environ["LIGHTOS_ZEITSPRUNG_AKTIV"] = _tage

    print(f"[zeitsprung] Uhr um {_tage} Tage vorgerueckt (Staerke: {_staerke})",
          file=_sys.stderr)
