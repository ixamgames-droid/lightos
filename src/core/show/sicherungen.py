"""STAB-32: versionierte Sicherungen statt einer einzigen Auto-Save-Datei.

Bis hierher gab es genau EINE Sicherung: ``<App-Daten>/auto_save.lshow``. Ein
kaputter oder ungewollter Stand ueberschrieb darin den letzten guten, und ein
manuelles Speichern ueber eine vorhandene Datei liess vom Vorgaenger nichts
uebrig. Dieses Modul legt daneben den Ordner ``<App-Daten>/sicherungen/`` an:

* **je Show rollierende Versionen** — Dateiname
  ``<Show>__<JJJJMMTT-HHMMSS>__<Anlass>.lshow``;
* **gestaffelte Aufbewahrung** (:func:`zu_behalten`): die letzten
  ``BEHALTE_LETZTE``, dazu je eine pro Stunde der letzten 24 h und je eine pro
  Tag der letzten 14 Tage — plus eine Obergrenze fuer die Gesamtgroesse
  (aelteste zuerst weg);
* **Anlaesse:** Auto-Save, vor einem manuellen Speichern, das eine vorhandene
  Datei ueberschreibt, und bevor ungespeicherte Aenderungen verworfen werden.

Der Absturz-Wiederherstellungsweg (``auto_save.lshow``, STAB-01/05) bleibt
unberuehrt: dieser Ordner ist ein ZUSAETZLICHES Archiv.

**Nie blockierend, nie werfend.** Eine vorhandene Datei wird im Aufrufer nur
per Hardlink gesichert (ein Verzeichniseintrag, keine Datenkopie): das
anschliessende Speichern ersetzt die Show per ``os.replace`` durch eine neue
Datei, der Link behaelt den alten Inhalt und ist ab dann die einzige Datei
dieses Standes. Der Link IST die Sicherung — er wird nie gelesen oder kopiert:
ein offener Lese-Zugriff auf den Link sperrte unter Windows genau das
``os.replace``, mit dem das Speichern die Show ersetzt (beide Namen sind
dieselbe Datei). Bis die Quelle ersetzt ist, teilen sich Quelle und Sicherung
die Daten; LightOS schreibt Shows nie an Ort und Stelle, nur ueber
tmp + ``os.replace``. Kann das Dateisystem keine Hardlinks (FAT, anderes
Laufwerk), wird einmal direkt kopiert, bevor der Aufrufer weiterschreibt — das
Speichern selbst schreibt dieselbe Groessenordnung. Das Aufraeumen laeuft in
einem Hintergrund-Thread. Jeder Fehler landet nur im Log
(``diagnose_log.melde_still``); eine Sicherung darf das Speichern nie stoppen.

**Aufraeumen anhaltbar.** Solange eine Sicherung ausgewaehlt und geoeffnet
wird (:func:`aufraeumen_angehalten`), loescht :func:`raeume_auf` nichts: sonst
koennte die Sicherung, die das Verwerfen der offenen Show eben anlegt, genau
die gewaehlte aeltere Version aus der Staffelung schieben, bevor sie geladen
ist.

Importiert weder Qt noch ``app_state`` — nur Dateien.
"""
from __future__ import annotations

import datetime
import json
import os
import queue
import re
import shutil
import threading
import time
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass

from src.core.paths import app_data_dir

ORDNER = "sicherungen"
ENDUNG = ".lshow"
_STUFE = ".stufe"          # Rest einer frueheren Fassung (Link vor der Kopie)
_TMP = ".tmp"
UNBENANNT = "Unbenannt"

#: Aufbewahrung je Show.
BEHALTE_LETZTE = 10
STUNDEN = 24
TAGE = 14
#: Obergrenze fuer den ganzen Ordner (alle Shows zusammen).
MAX_GESAMT_BYTES = 500 * 1024 * 1024

ANLASS_AUTO = "auto"
ANLASS_VOR_SPEICHERN = "vor-speichern"
ANLASS_VOR_VERWERFEN = "vor-verwerfen"
ANLASS_TEXT = {
    ANLASS_AUTO: "Auto-Save",
    ANLASS_VOR_SPEICHERN: "vor dem Überschreiben",
    ANLASS_VOR_VERWERFEN: "vor dem Verwerfen",
}

_ZEITFORMAT = "%Y%m%d-%H%M%S"
_NAME_RE = re.compile(
    r"^(?P<show>.+)__(?P<zeit>\d{8}-\d{6})(?:-(?P<nr>\d+))?"
    r"(?:__(?P<anlass>[a-z-]+))?\.lshow$")


def _melde(exc: BaseException | None = None, text: str = "") -> None:
    try:
        from src.core.diagnose_log import melde_still
        melde_still("sicherung", exc, text)
    except Exception:
        pass


def sicherungs_dir() -> str:
    """Der Sicherungsordner (wird hier NICHT angelegt)."""
    return os.path.join(app_data_dir(), ORDNER)


def show_name_aus_pfad(pfad: str | None) -> str:
    """Anzeigename einer Show: Dateiname ohne Endung, sonst „Unbenannt"."""
    if not pfad:
        return UNBENANNT
    stamm = os.path.splitext(os.path.basename(os.fspath(pfad)))[0].strip()
    return stamm or UNBENANNT


def _datei_stamm(show: str) -> str:
    """Show-Name als sicherer Dateinamen-Teil (ohne ``__``, ohne Pfadzeichen)."""
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", str(show or "").strip())
    s = re.sub(r"_{2,}", "_", s).strip(" ._")
    return (s or UNBENANNT)[:80]


@dataclass(frozen=True)
class Sicherung:
    pfad: str
    show: str
    zeit: datetime.datetime
    anlass: str
    groesse: int

    @property
    def anlass_text(self) -> str:
        return ANLASS_TEXT.get(self.anlass, self.anlass or "")

    @property
    def zeit_text(self) -> str:
        return self.zeit.strftime("%d.%m.%Y %H:%M")


def _lies_eintrag(ordner: str, name: str) -> Sicherung | None:
    m = _NAME_RE.match(name)
    if not m:
        return None
    try:
        zeit = datetime.datetime.strptime(m.group("zeit"), _ZEITFORMAT)
        groesse = os.path.getsize(os.path.join(ordner, name))
    except (ValueError, OSError):
        return None
    return Sicherung(os.path.join(ordner, name), m.group("show"), zeit,
                     m.group("anlass") or "", groesse)


def liste_sicherungen(show: str | None = None,
                      ordner: str | None = None) -> list[Sicherung]:
    """Alle Sicherungen (``show=None``) oder die einer Show — neueste zuerst.

    Die Zeit stammt aus dem Dateinamen, nicht aus dem Aenderungsdatum: ein
    Kopieren/Zurueckspielen des Ordners veraendert die Reihenfolge nicht."""
    ordner = ordner or sicherungs_dir()
    try:
        namen = os.listdir(ordner)
    except OSError:
        return []
    stamm = _datei_stamm(show) if show is not None else None
    raus = []
    for name in namen:
        e = _lies_eintrag(ordner, name)
        if e is not None and (stamm is None or e.show == stamm):
            raus.append(e)
    raus.sort(key=lambda e: (e.zeit, e.pfad), reverse=True)
    return raus


def kurzinfo(pfad: str) -> str:
    """„12 Geräte · 34 Funktionen" — aus der Datei GELESEN, ohne sie zu laden
    (kein State, keine Fixture-DB). Unlesbare Datei -> „nicht lesbar"."""
    try:
        with zipfile.ZipFile(pfad, "r") as zf:
            daten = json.loads(zf.read("show.json").decode("utf-8"))
        patch = daten.get("patch") or []
        fn = daten.get("functions") or {}
        if isinstance(fn, dict):
            fn = fn.get("functions") or []
        return f"{len(patch)} Geräte · {len(fn)} Funktionen"
    except Exception:
        return "nicht lesbar"


# ── Aufbewahrung ─────────────────────────────────────────────────────────────

def zu_behalten(eintraege: list[Sicherung],
                jetzt: datetime.datetime) -> set[str]:
    """Pfade EINER Show, die die Staffelung behaelt.

    * die ``BEHALTE_LETZTE`` neuesten,
    * je Stunde der letzten ``STUNDEN`` h die neueste,
    * je Kalendertag der letzten ``TAGE`` Tage die neueste.

    Auto-Saves und Anlass-Sicherungen (vor dem Ueberschreiben / Verwerfen)
    werden GETRENNT gestaffelt: sonst schoeben zehn Auto-Saves — bei 5 min
    Intervall keine Stunde — genau den Stand hinaus, der vor einem
    versehentlichen Ueberschreiben oder Verwerfen aufgehoben wurde.
    """
    auto = [e for e in eintraege if e.anlass == ANLASS_AUTO]
    anlass = [e for e in eintraege if e.anlass != ANLASS_AUTO]
    return _staffel(auto, jetzt) | _staffel(anlass, jetzt)


def _staffel(eintraege: list[Sicherung], jetzt: datetime.datetime) -> set[str]:
    sortiert = sorted(eintraege, key=lambda e: (e.zeit, e.pfad), reverse=True)
    behalten = {e.pfad for e in sortiert[:BEHALTE_LETZTE]}
    stunden: set = set()
    tage: set = set()
    for e in sortiert:                      # neueste zuerst -> erste je Fach gewinnt
        alter = jetzt - e.zeit
        if alter <= datetime.timedelta(hours=STUNDEN):
            fach = e.zeit.strftime("%Y%m%d%H")
            if fach not in stunden:
                stunden.add(fach)
                behalten.add(e.pfad)
        if alter <= datetime.timedelta(days=TAGE):
            fach = e.zeit.date()
            if fach not in tage:
                tage.add(fach)
                behalten.add(e.pfad)
    return behalten


def _entferne(pfad: str) -> bool:
    """Eine alte Sicherung loeschen — nicht, solange das Aufraeumen angehalten
    ist. Pruefung und Loeschen unter EINER Sperre: wer
    :func:`aufraeumen_angehalten` betreten hat, verliert danach keine Datei
    mehr, auch nicht an einen schon laufenden Durchgang."""
    global _nachholen
    with _halt_lock:
        if _halt:
            _nachholen = True
            return False
        try:
            os.remove(pfad)
            return True
        except FileNotFoundError:
            return True
        except OSError as e:
            _melde(e, "alte Sicherung nicht loeschbar")
            return False


_halt_lock = threading.Lock()
_halt = 0                  # offene ``aufraeumen_angehalten``-Bloecke
_nachholen = False         # ein Aufraeumen fiel in die Pause


def aufraeumen_ist_angehalten() -> bool:
    with _halt_lock:
        return _halt > 0


@contextmanager
def aufraeumen_angehalten():
    """Solange der Block laeuft, loescht :func:`raeume_auf` KEINE Sicherung.

    Fuer „Ältere Version öffnen": zwischen Auswahl und Laden entstehen neue
    Sicherungen (Verwerfen/Speichern der offenen Show, Auto-Save), deren
    Aufraeumen sonst die gewaehlte Version loeschen koennte. Neue Sicherungen
    werden weiter geschrieben. Ein in die Pause gefallenes Aufraeumen wird
    danach im Hintergrund nachgeholt. Schachtelbar, aus jedem Thread."""
    global _halt, _nachholen
    with _halt_lock:
        _halt += 1
    try:
        yield
    finally:
        with _halt_lock:
            _halt -= 1
            holen = _halt == 0 and _nachholen
            if holen:
                _nachholen = False
        if holen:
            _im_hintergrund(raeume_auf)


def raeume_auf(jetzt: datetime.datetime | None = None,
               ordner: str | None = None,
               max_bytes: int | None = None) -> list[str]:
    """Staffelung je Show anwenden, dann die Groessengrenze (aelteste zuerst
    weg, ueber alle Shows). Liefert die geloeschten Pfade. Wirft nie.

    Loescht nichts, solange :func:`aufraeumen_angehalten` offen ist (wird
    danach nachgeholt)."""
    global _nachholen
    geloescht: list[str] = []
    try:
        with _halt_lock:
            if _halt:
                _nachholen = True
                return geloescht
        ordner = ordner or sicherungs_dir()
        jetzt = jetzt or datetime.datetime.now()
        grenze = MAX_GESAMT_BYTES if max_bytes is None else max_bytes
        _reste_fertigstellen(ordner)
        alle = liste_sicherungen(ordner=ordner)
        je_show: dict[str, list[Sicherung]] = {}
        for e in alle:
            je_show.setdefault(e.show, []).append(e)
        bleibt: list[Sicherung] = []
        for eintraege in je_show.values():
            behalten = zu_behalten(eintraege, jetzt)
            for e in eintraege:
                if e.pfad in behalten:
                    bleibt.append(e)
                elif _entferne(e.pfad):
                    geloescht.append(e.pfad)
        bleibt.sort(key=lambda e: (e.zeit, e.pfad))          # aelteste zuerst
        gesamt = sum(e.groesse for e in bleibt)
        # Die allerneueste bleibt immer — auch wenn sie allein die Grenze sprengt.
        for e in bleibt[:-1]:
            if gesamt <= grenze:
                break
            if _entferne(e.pfad):
                geloescht.append(e.pfad)
                gesamt -= e.groesse
    except Exception as e:
        _melde(e, "Aufraeumen der Sicherungen")
    return geloescht


def _reste_fertigstellen(ordner: str) -> None:
    """Uebrig gebliebene Stufen-/Temp-Dateien einer beendeten Sitzung: ein
    eingefrorener Link (``.stufe``, fruehere Fassung dieses Moduls) hat
    gueltigen Inhalt und wird zur Sicherung; eine halbe Temp-Kopie wird
    verworfen. Nur Dateien, an denen gerade niemand arbeitet."""
    try:
        namen = os.listdir(ordner)
    except OSError:
        return
    with _aktiv_lock:
        aktiv = set(_aktiv)
    for name in namen:
        pfad = os.path.join(ordner, name)
        try:
            if name.endswith(ENDUNG + _STUFE):
                ziel = pfad[:-len(_STUFE)]
                if ziel in aktiv or not _NAME_RE.match(name[:-len(_STUFE)]):
                    continue
                if os.path.exists(ziel):
                    os.remove(pfad)
                else:
                    os.replace(pfad, ziel)
            elif name.endswith(ENDUNG + _TMP):
                # NUR eigene Temp-Kopien: ``save_show`` legt seine Temp-Datei
                # (``.show-….lshow.tmp``) im selben Ordner an, waehrend es eine
                # Sicherung vor dem Verwerfen schreibt — die gehoert ihm.
                if (_NAME_RE.match(name[:-len(_TMP)])
                        and pfad[:-len(_TMP)] not in aktiv):
                    os.remove(pfad)
        except OSError as e:
            _melde(e, "Rest einer Sicherung nicht aufraeumbar")


# ── Hintergrund-Arbeiter ─────────────────────────────────────────────────────

_auftraege: "queue.Queue" = queue.Queue()
_arbeiter: threading.Thread | None = None
_arbeiter_lock = threading.Lock()
_aktiv: set[str] = set()          # Zielpfade, an denen gerade gearbeitet wird
_aktiv_lock = threading.Lock()


def _arbeite() -> None:
    while True:
        fn = _auftraege.get()
        try:
            fn()
        except Exception as e:                      # darf den Thread nie beenden
            _melde(e, "Sicherung im Hintergrund")
        finally:
            _auftraege.task_done()


def _im_hintergrund(fn) -> None:
    global _arbeiter
    with _arbeiter_lock:
        if _arbeiter is None or not _arbeiter.is_alive():
            _arbeiter = threading.Thread(target=_arbeite, daemon=True,
                                         name="lightos-sicherungen")
            _arbeiter.start()
    _auftraege.put(fn)


def warte_bis_fertig(timeout: float = 5.0) -> bool:
    """Bis alle Hintergrund-Auftraege durch sind (Tests, Programmende)."""
    fertig = threading.Event()
    _im_hintergrund(fertig.set)
    return fertig.wait(timeout)


# ── Schreiben ────────────────────────────────────────────────────────────────

def _kopiere_atomar(quelle: str, ziel: str) -> None:
    tmp = ziel + _TMP
    try:
        shutil.copyfile(quelle, tmp)
        os.replace(tmp, ziel)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


#: Kopier-Versuche, wenn die Quelle kurz gesperrt ist (Windows: Virenscanner,
#: Suchindex, Cloud-Sync halten frisch geschriebene Dateien fuer Augenblicke).
KOPIER_VERSUCHE = 4
KOPIER_PAUSE_S = 0.05


def _kopiere_mit_wiederholung(quelle: str, ziel: str) -> None:
    """``_kopiere_atomar``, bei ``PermissionError`` (gesperrte Datei) nach kurzer
    Pause erneut. Andere Fehler (Platte voll, Quelle weg) sofort weiter."""
    for versuch in range(1, KOPIER_VERSUCHE + 1):
        try:
            _kopiere_atomar(quelle, ziel)
            return
        except PermissionError:
            if versuch == KOPIER_VERSUCHE:
                raise
            time.sleep(KOPIER_PAUSE_S * versuch)


def neuer_pfad(show: str, anlass: str,
               jetzt: datetime.datetime | None = None,
               ordner: str | None = None) -> str:
    """Freier Zielpfad fuer eine neue Sicherung; legt den Ordner an."""
    ordner = ordner or sicherungs_dir()
    os.makedirs(ordner, exist_ok=True)
    jetzt = jetzt or datetime.datetime.now()
    kopf = f"{_datei_stamm(show)}__{jetzt.strftime(_ZEITFORMAT)}"
    schwanz = f"__{anlass}{ENDUNG}" if anlass else ENDUNG
    nr = 1
    with _aktiv_lock:
        while True:
            pfad = os.path.join(ordner, kopf + (f"-{nr}" if nr > 1 else "") + schwanz)
            if not (os.path.exists(pfad) or os.path.exists(pfad + _STUFE)
                    or pfad in _aktiv):
                return pfad
            nr += 1


def sichere_datei(quelle: str, show: str, anlass: str,
                  jetzt: datetime.datetime | None = None) -> str | None:
    """Den JETZIGEN Inhalt von ``quelle`` als neue Sicherung ablegen.

    Kehrt sofort zurueck (siehe Modul-Docstring); der Aufrufer darf ``quelle``
    danach per ``os.replace`` ersetzen — auch unter Windows sofort: an der
    Quelle bleibt kein Zugriff offen. Liefert den Zielpfad oder ``None``
    (keine Quelle / Fehler — nur geloggt)."""
    try:
        quelle = os.fspath(quelle)
        if not os.path.isfile(quelle):
            return None
        jetzt = jetzt or datetime.datetime.now()
        ziel = neuer_pfad(show, anlass, jetzt)
        try:
            # Der Link ist die Sicherung (s. Modul-Docstring) — kein Lesen.
            try:
                os.link(quelle, ziel)
            except FileExistsError:
                # derselbe Name im selben Augenblick vergeben -> naechster
                ziel = neuer_pfad(show, anlass, jetzt)
                os.link(quelle, ziel)
        except (OSError, NotImplementedError, AttributeError):
            # Kein Hardlink moeglich -> einmal direkt kopieren. Die Kopie ist
            # fertig und geschlossen, bevor der Aufrufer die Quelle ersetzt.
            with _aktiv_lock:
                _aktiv.add(ziel)
            try:
                _kopiere_mit_wiederholung(quelle, ziel)
            finally:
                with _aktiv_lock:
                    _aktiv.discard(ziel)
        _im_hintergrund(lambda: raeume_auf(jetzt))
        return ziel
    except Exception as e:
        _melde(e, "Sicherung nicht anlegbar")
        return None


def sichere_stand(schreiben, show: str, anlass: str,
                  jetzt: datetime.datetime | None = None) -> str | None:
    """Den Stand im Speicher sichern: ``schreiben(pfad)`` schreibt die Show
    selbst atomar (``save_show``). Fuer Staende, die in keiner Datei stehen
    (ungespeicherte Aenderungen vor dem Verwerfen). Wirft nie."""
    try:
        jetzt = jetzt or datetime.datetime.now()
        ziel = neuer_pfad(show, anlass, jetzt)
        schreiben(ziel)
        _im_hintergrund(lambda: raeume_auf(jetzt))
        return ziel
    except Exception as e:
        _melde(e, "Sicherung vor dem Verwerfen")
        return None
