"""FM-53 Etappe 1: die Geraete-Bibliothek beim ersten Start herunterladen.

Entscheidung des Projektinhabers (01.10.2026): LightOS darf beim ersten Start
eine freie Fixture-Bibliothek herunterladen. Die Quellen und Lizenzen stehen in
``docs/recherche/fixture_quellen_2026-10.md`` (FM-55):

* **QLC+-Fixtures** (Apache-2.0) als GitHub-Archiv einer festen Version,
* **Open Fixture Library** (MIT) als QLC+-Export.

Beide Formate liest der VORHANDENE QXF-Import (``qxf_import.import_all_qxf``) —
hier kommt kein zweiter Importer dazu.

Regeln, die dieses Modul garantiert:

* **Nichts ohne Zustimmung.** Das Modul laedt nur, wenn es aufgerufen wird; die
  Frage stellt der Dialog (``src/ui/widgets/bibliothek_download_dialog.py``).
  Ob schon gefragt wurde, steht in ``bibliothek_download.json`` im
  App-Datenordner.
* **Groesse vorher, Pruefsumme nachher.** Die Groesse steht fest je Quelle
  (``Quelle.groesse_ca``) — VOR der Zustimmung geht keine einzige Anfrage ins
  Netz, auch kein HEAD (Review #866). ``herunterladen`` rechnet beim Lesen
  SHA-256 mit. Traegt die Quelle eine Soll-Pruefsumme, wird bei Abweichung
  NICHTS importiert.
* **Bestand bleibt unangetastet.** Der QXF-Import legt nur neue Profile an
  (gleicher Hersteller + Modell wird uebersprungen, Builtins und eigene Profile
  nie ueberschrieben).
* **Herkunft und Lizenz je Profil** stehen in der Tabelle ``profil_herkunft`` in
  ``fixtures.db``: Quelle, Lizenz, Lizenz-Link, Archiv-URL, SHA-256, Zeitpunkt.
  ``FixtureProfile.source`` bleibt ``'qlcplus'`` — das Feld nennt den KANAL
  (QA-72), und ``fixture_db._ist_dual_tilt_spider`` sowie die FM-49-Reparatur
  bauen darauf.
* **Abbrechbar und offline-tolerant.** ``abbrechen()`` wird je Block gefragt;
  ohne Netz kommt ``OfflineFehler`` mit einer lesbaren Meldung, die Bibliothek
  bleibt wie sie war.
* **Nur ``.qxf`` aus dem Archiv**, und keine Datei ausserhalb des Arbeitsordners
  (Pfade mit ``..`` oder absolute Pfade werden verworfen).
"""
from __future__ import annotations

import datetime
import hashlib
import http.client
import json
import os
import shutil
import socket
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from typing import Callable, NamedTuple, Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session

BLOCK = 256 * 1024
ZEITLIMIT_S = 30
_AGENT = "LightOS-Bibliothek/1"


class Quelle(NamedTuple):
    schluessel: str
    name: str
    url: str
    lizenz: str
    lizenz_url: str
    format: str                    # "tar.gz" oder "zip"
    unterordner: str = ""          # nur .qxf unter diesem Pfad im Archiv
    sha256: Optional[str] = None   # Soll-Pruefsumme, falls bekannt
    hinweis: str = ""
    groesse_ca: int = 0            # Bytes, ungefaehr — steht VOR dem Download im Dialog


#: Feste QLC+-Version statt ``master``: gleiche Eingabe bei jedem Download.
QLCPLUS_VERSION = "QLC+_4.14.4"

QUELLEN = {
    "qlcplus": Quelle(
        schluessel="qlcplus",
        name=f"QLC+ Fixture-Bibliothek ({QLCPLUS_VERSION.replace('_', ' ')})",
        url=("https://github.com/mcallegari/qlcplus/archive/refs/tags/"
             + urllib.request.quote(QLCPLUS_VERSION, safe="") + ".tar.gz"),
        lizenz="Apache-2.0",
        lizenz_url="https://github.com/mcallegari/qlcplus/blob/master/COPYING",
        format="tar.gz",
        unterordner="resources/fixtures/",
        # Gemessen am 2026-10-02 (12 703 615 Bytes). GitHub erzeugt die
        # /archive/-Dateien bei Bedarf neu und sagt keine bytegleichen Archive
        # zu — weicht eine Datei einmal ab, meldet ``PruefsummeFalsch`` das
        # verstaendlich, und es wird nichts importiert.
        sha256="f90165e00f9a203fb871f50fa4ffc2ed236dce2a836208de22d63cfdbd8090c1",
        hinweis="Das ganze QLC+-Quellarchiv; verwendet werden nur die .qxf-Dateien.",
        groesse_ca=12_703_615,
    ),
    "ofl": Quelle(
        schluessel="ofl",
        name="Open Fixture Library (QLC+-Export)",
        url="https://open-fixture-library.org/download.qlcplus_4.12.2",
        lizenz="MIT",
        lizenz_url=("https://github.com/OpenLightingProject/"
                    "open-fixture-library/blob/master/LICENSE"),
        format="zip",
        hinweis="Einige OFL-Profile stammen ihrerseits aus QLC+ (Apache-2.0).",
        # Keine feste Fassung: der Export waechst mit der Bibliothek, deshalb
        # weder Soll-Pruefsumme noch genaue Groesse (Stand 2026-10: ~2,7 MB).
        groesse_ca=2_700_000,
    ),
}


# ── Fehler ────────────────────────────────────────────────────────────────────

class DownloadFehler(RuntimeError):
    """Oberklasse: der Download hat nichts importiert."""


class OfflineFehler(DownloadFehler):
    """Keine Verbindung — spaeter erneut versuchen."""


class Abgebrochen(DownloadFehler):
    """Der Nutzer hat abgebrochen."""


class PruefsummeFalsch(DownloadFehler):
    """Die Datei stimmt nicht mit der Soll-Pruefsumme ueberein."""


class Ergebnis(NamedTuple):
    neu: int
    fehler: int
    sha256: str
    bytes: int


# ── Merker „schon gefragt“ ───────────────────────────────────────────────────

def merker_pfad() -> str:
    from src.core.paths import app_data_dir
    return os.environ.get("LIGHTOS_BIBLIOTHEK_MERKER") or os.path.join(
        app_data_dir(), "bibliothek_download.json")


def merker_lesen() -> dict:
    try:
        with open(merker_pfad(), encoding="utf-8") as fh:
            daten = json.load(fh)
        return daten if isinstance(daten, dict) else {}
    except (OSError, ValueError):
        return {}


def merker_schreiben(**werte) -> None:
    daten = merker_lesen()
    daten.update(werte)
    pfad = merker_pfad()
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "w", encoding="utf-8") as fh:
        json.dump(daten, fh, ensure_ascii=False, indent=1)


def beim_start_fragen(engine) -> bool:
    """Die Frage beim Start: nur, solange sie nie beantwortet wurde UND die
    Bibliothek nichts ausser den eingebauten Profilen enthaelt.

    „Nicht jetzt“ zaehlt als Antwort (``gefragt``); ein Abbruch durch fehlendes
    Netz nicht — dann kommt die Frage beim naechsten Start wieder.
    """
    if merker_lesen().get("gefragt"):
        return False
    from src.core.database.models import FixtureProfile
    with Session(engine) as s:
        fremde = s.scalars(select(FixtureProfile.id).where(
            FixtureProfile.source != "builtin").limit(1)).first()
    return fremde is None


# ── Netz ──────────────────────────────────────────────────────────────────────

#: Was „keine oder abgerissene Verbindung“ heisst — im Unterschied zu einem
#: Fehler beim Schreiben der Datei.
_NETZFEHLER = (urllib.error.URLError, socket.timeout, ConnectionError,
               http.client.HTTPException)


def _anfrage(url: str):
    return urllib.request.Request(url, headers={"User-Agent": _AGENT})


def herunterladen(quelle: Quelle, ziel: str,
                  fortschritt: Optional[Callable[[int, Optional[int]], None]] = None,
                  abbrechen: Callable[[], bool] = lambda: False,
                  oeffnen=urllib.request.urlopen) -> tuple:
    """Laedt ``quelle`` nach ``ziel`` -> ``(sha256, bytes)``.

    Liest in Bloecken, fragt je Block ``abbrechen()`` und meldet
    ``fortschritt(gelesen, gesamt)``. Bei Abbruch, Netzfehler oder falscher
    Pruefsumme wird die halbe Datei entfernt."""
    pruef = hashlib.sha256()
    gelesen = 0
    try:
        with oeffnen(_anfrage(quelle.url), timeout=ZEITLIMIT_S) as antwort, \
                open(ziel, "wb") as fh:
            try:
                gesamt = int(antwort.headers.get("Content-Length"))
            except (TypeError, ValueError):
                gesamt = None
            while True:
                if abbrechen():
                    raise Abgebrochen("Download abgebrochen")
                block = antwort.read(BLOCK)
                if not block:
                    break
                fh.write(block)
                pruef.update(block)
                gelesen += len(block)
                if fortschritt:
                    fortschritt(gelesen, gesamt)
    except DownloadFehler:
        _weg(ziel)
        raise
    except _NETZFEHLER as e:
        _weg(ziel)
        raise OfflineFehler(f"Download von {quelle.url} unterbrochen: {e}") from e
    except OSError as e:            # Platte voll, keine Schreibrechte …
        _weg(ziel)
        raise DownloadFehler(f"Download nicht speicherbar: {e}") from e
    summe = pruef.hexdigest()
    if quelle.sha256 and summe.lower() != quelle.sha256.lower():
        _weg(ziel)
        raise PruefsummeFalsch(
            f"Die heruntergeladene Datei weicht von der geprüften Fassung ab "
            f"({gelesen} Bytes, SHA-256 {summe[:16]}… statt {quelle.sha256[:16]}…). "
            f"GitHub erzeugt solche Archive nicht immer bytegleich. Es wurde nichts "
            f"importiert — bitte später erneut versuchen oder die andere Quelle wählen.")
    return summe, gelesen


def _weg(pfad: str) -> None:
    try:
        os.remove(pfad)
    except OSError:
        pass


# ── Entpacken ─────────────────────────────────────────────────────────────────

def _sicherer_name(name: str, unterordner: str) -> Optional[str]:
    """Relativer Zielpfad fuer ein Archiv-Mitglied — oder ``None``.

    Nur ``.qxf``. Das erste Pfadglied ist bei GitHub-Archiven der Ordner
    ``<repo>-<version>/``; ``unterordner`` wird dahinter gesucht."""
    name = name.replace("\\", "/")
    if not name.lower().endswith(".qxf"):
        return None
    teile = [t for t in name.split("/") if t not in ("", ".")]
    if not teile or name.startswith("/") or ".." in teile or ":" in teile[0]:
        return None
    pfad = "/".join(teile)
    if unterordner:
        stelle = pfad.find(unterordner)
        if stelle < 0:
            return None
        pfad = pfad[stelle + len(unterordner):]
    return pfad or None


def entpacken(archiv: str, quelle: Quelle, zielordner: str,
              abbrechen: Callable[[], bool] = lambda: False) -> list:
    """Schreibt die ``.qxf``-Dateien des Archivs nach ``zielordner`` -> Pfade."""
    erhalten = []

    def schreiben(relativ, quelle_fh):
        ziel = os.path.normpath(os.path.join(zielordner, relativ))
        if os.path.commonpath([os.path.abspath(zielordner), os.path.abspath(ziel)]) \
                != os.path.abspath(zielordner):
            return
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        with open(ziel, "wb") as aus:
            shutil.copyfileobj(quelle_fh, aus)
        erhalten.append(ziel)

    try:
        if quelle.format == "zip":
            with zipfile.ZipFile(archiv) as z:
                for info in z.infolist():
                    if abbrechen():
                        raise Abgebrochen("Entpacken abgebrochen")
                    relativ = _sicherer_name(info.filename, quelle.unterordner)
                    if relativ and not info.is_dir():
                        with z.open(info) as fh:
                            schreiben(relativ, fh)
        else:
            with tarfile.open(archiv, "r:*") as t:
                for info in t:
                    if abbrechen():
                        raise Abgebrochen("Entpacken abgebrochen")
                    if not info.isfile():
                        continue        # keine Links, Geraete, Ordner
                    relativ = _sicherer_name(info.name, quelle.unterordner)
                    if relativ:
                        fh = t.extractfile(info)
                        if fh is not None:
                            with fh:
                                schreiben(relativ, fh)
    except (zipfile.BadZipFile, tarfile.TarError, EOFError) as e:
        raise DownloadFehler(f"Archiv nicht lesbar: {e}") from e
    return erhalten


# ── Herkunft je Profil ────────────────────────────────────────────────────────

def _tabelle_anlegen(conn) -> None:
    conn.execute(text(
        "CREATE TABLE IF NOT EXISTS profil_herkunft ("
        " fixture_id INTEGER PRIMARY KEY,"
        " quelle TEXT, lizenz TEXT, lizenz_url TEXT,"
        " archiv_url TEXT, sha256 TEXT, zeitpunkt TEXT)"))


def herkunft_lesen(engine, fixture_id: int) -> Optional[dict]:
    """Quelle und Lizenz eines heruntergeladenen Profils — ``None`` sonst."""
    with engine.begin() as conn:
        _tabelle_anlegen(conn)
        zeile = conn.execute(text(
            "SELECT quelle, lizenz, lizenz_url, archiv_url, sha256, zeitpunkt "
            "FROM profil_herkunft WHERE fixture_id = :i"), {"i": fixture_id}).first()
    if zeile is None:
        return None
    return dict(zip(("quelle", "lizenz", "lizenz_url", "archiv_url", "sha256",
                     "zeitpunkt"), zeile))


def _profil_ids(engine) -> set:
    from src.core.database.models import FixtureProfile
    with Session(engine) as s:
        return set(s.scalars(select(FixtureProfile.id)))


def importieren(engine, qxf_ordner: str, quelle: Quelle, sha256: str,
                fortschritt=None) -> tuple:
    """QXF-Import des Ordners + Herkunft je NEUEM Profil -> ``(neu, fehler)``.

    ``import_all_qxf`` arbeitet auf der Engine aus ``fixture_db.engine()`` —
    ``engine`` muss dieselbe sein (im Betrieb ist sie es; Tests setzen sie)."""
    from src.core.database.qxf_import import import_all_qxf
    vorher = _profil_ids(engine)
    try:
        _ok, fehler = import_all_qxf(qxf_ordner, progress_cb=fortschritt)
    finally:
        # Auch bei einem Abbruch aus dem Fortschritt heraus: was schon
        # angelegt ist, bekommt seine Herkunft.
        neu = sorted(_profil_ids(engine) - vorher)
        jetzt = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        with engine.begin() as conn:
            _tabelle_anlegen(conn)
            for fid in neu:
                conn.execute(text(
                    "INSERT OR REPLACE INTO profil_herkunft VALUES "
                    "(:i, :q, :l, :lu, :u, :s, :z)"),
                    {"i": fid, "q": quelle.name, "l": quelle.lizenz,
                     "lu": quelle.lizenz_url, "u": quelle.url, "s": sha256, "z": jetzt})
    return len(neu), fehler


# ── Alles zusammen ────────────────────────────────────────────────────────────

def bibliothek_herunterladen(quelle: Quelle, engine=None,
                             fortschritt: Optional[Callable[[str, int, Optional[int]], None]] = None,
                             abbrechen: Callable[[], bool] = lambda: False,
                             oeffnen=urllib.request.urlopen) -> Ergebnis:
    """Download -> Pruefsumme -> nur ``.qxf`` entpacken -> QXF-Import.

    ``fortschritt(phase, wert, gesamt)`` mit ``phase`` in
    ``"download"``/``"entpacken"``/``"import"``. Der Arbeitsordner liegt im
    Temp-Bereich und wird in jedem Fall entfernt."""
    if engine is None:
        from src.core.database.fixture_db import engine as fdb_engine
        engine = fdb_engine()

    def melde(phase):
        return (lambda a, b=None: fortschritt(phase, a, b)) if fortschritt else None

    with tempfile.TemporaryDirectory(prefix="lightos_bibliothek_") as tmp:
        archiv = os.path.join(tmp, "archiv")
        summe, groesse = herunterladen(quelle, archiv, melde("download"), abbrechen, oeffnen)
        dateien = entpacken(archiv, quelle, os.path.join(tmp, "qxf"), abbrechen)
        if not dateien:
            raise DownloadFehler("Im Archiv steckt keine einzige .qxf-Datei.")
        if abbrechen():
            raise Abgebrochen("Vor dem Import abgebrochen")
        imp = melde("import")

        def import_fortschritt(i, gesamt, _ok):
            if abbrechen():
                raise Abgebrochen("Import abgebrochen")
            if imp:
                imp(i, gesamt)

        neu, fehler = importieren(engine, os.path.join(tmp, "qxf"), quelle, summe,
                                  import_fortschritt)
    merker_schreiben(gefragt=True, quelle=quelle.schluessel, sha256=summe,
                     zeitpunkt=datetime.datetime.now(datetime.timezone.utc)
                     .strftime("%Y-%m-%dT%H:%M:%SZ"), neu=neu)
    return Ergebnis(neu, fehler, summe, groesse)
