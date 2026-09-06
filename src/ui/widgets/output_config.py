"""Output-Konfigurations-Dialog (Enttec / Art-Net / sACN / Universe-Manager)."""
from __future__ import annotations
import json
import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QGroupBox, QFormLayout, QCheckBox, QLineEdit,
    QSpinBox, QTabWidget, QWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer
import serial.tools.list_ports
from src.core.app_state import get_state
from src.core.dmx.enttec_pro import EnttecPro, ENTTEC_VID, ENTTEC_PID

# ⚠️ Umlenkbar — und das ist keine Test-Bequemlichkeit, sondern Datenschutz.
#
# Der Pfad ist RELATIV zum Arbeitsverzeichnis, und `_persist_output` schreibt
# ihn bei jedem „Übernehmen"/„Verbinden" neu. Wer die Suite im Repo-Ordner
# fährt — also der Normalfall —, schrieb damit in **genau die Datei, ohne die
# kein DMX rausgeht**: gemessen legte `tests/test_output_config_lifecycle.py`
# eine vollständige 5-Zeilen-Konfiguration an (Enttec `COM_FAKE`, zwei
# Art-Net-Broadcasts, zwei sACN). Auf einem Rechner, wo der Arbeitsbaum
# zugleich der Betriebsordner ist, ersetzt ein Testlauf so die echte
# Ausgangs-Konfiguration durch eine erfundene — ohne Meldung, und `git status`
# schweigt, weil `data/*.json` gitignored ist.
#
# Die Umlenkung folgt demselben Muster wie `LIGHTOS_SHOW_DB` /
# `LIGHTOS_FIXTURE_DB` / `LIGHTOS_CRASH_LOG` (s. `tests/conftest.py`): Default
# unverändert, im Test ein Wegwerf-Pfad. Der Wächter dazu ist
# `tests/test_universes_json_isolation.py`.
_UNIV_CONFIG_PATH = os.environ.get(
    "LIGHTOS_UNIVERSES_JSON") or os.path.join("data", "universes.json")

# A3D-33: gueltiger interner Universe-Bereich — identisch zu den 1..32-Spinboxen der
# Tabs und der 32-Zeilen-Grenze in _univ_add. Die freie '#'-Spalte des Universe-Tables
# hatte KEINEN Range-Guard -> -1/70000 landeten in universes.json und liessen
# apply_output_config Art-Net werfen bzw. sACN still auf ein falsches Universum wrappen.
_UNIVERSE_MIN, _UNIVERSE_MAX = 1, 32


def _list_ifaces() -> list:
    """NET-04: NICs fuer die Auswahl — Fehler kosten hoechstens die Liste."""
    try:
        from src.core.dmx.output_iface import list_output_interfaces
        return list_output_interfaces()
    except Exception:
        return []


def _iface_pref() -> str:
    try:
        from src.ui.views.programmer_view import _load_prefs
        return (_load_prefs().get("output_iface_ip") or "").strip()
    except Exception:
        return ""


def _effektives_ziel(typ: str, patch: str, extern: int | None = None) -> str:
    """Wohin geht diese Zeile WIRKLICH? — so, wie ``apply_output_config`` es aufloest.

    Der rohe ``patch``-Text taugt nicht als Schluessel: ``apply_output_config``
    (``app_state.py``) setzt fuer Art-Net ``patch or "255.255.255.255"`` und fuer
    sACN ``patch or None`` (= Multicast). Ein leeres Feld und die ausgeschriebene
    Broadcast-Adresse sind also DASSELBE Ziel — verglichen man die Rohtexte,
    blieben genau diese beiden unentdeckt.

    ⚠️ **Bei sACN reicht ein Platzhalter fuer „Multicast" NICHT** (CDX-47, Codex
    zu PR #574). Die erste Fassung setzte hier ``"<Multicast>"`` — ein fester
    Text fuer eine Adresse, die in Wahrheit **vom Universum abhaengt**:
    ``SACNSender._dest()`` rechnet ``239.255.<hi>.<lo>``. Eine leere Zeile auf
    Universum 3 geht damit auf ``239.255.0.3``, und eine Zeile, die genau das
    ausschreibt, auf dieselbe Adresse — der Platzhalter verglich aber
    ``"<Multicast>"`` gegen ``"239.255.0.3"`` und meldete nichts.

    *Das ist exakt die Fehlerklasse, gegen die diese Funktion gebaut wurde,
    eine Ebene tiefer:* der Default wurde nicht ausgerechnet, sondern benannt.
    Ein Name kann nicht kollidieren, eine Adresse schon. Schlimmer noch, ein
    Test hielt die falsche Aussage ausdruecklich fest
    (``test_sacn_leer_ist_multicast_und_nicht_gleich_einer_unicast_ip``) — die
    Behauptung stand damit im Code UND im Gate.
    """
    if typ == "ArtNet":
        return patch or "255.255.255.255"
    if typ == "sACN":
        if patch:
            return patch
        # Multicast-Ziel ausrechnen statt benennen — dieselbe Formel wie
        # SACNSender._dest(). Ohne bekanntes Universum bleibt nur ein
        # Platzhalter; er kollidiert dann nur mit seinesgleichen.
        if extern is None:
            return "<Multicast ohne Universum>"
        return f"239.255.{(extern >> 8) & 0xFF}.{extern & 0xFF}"
    return patch                      # Enttec: der Port selbst ist das Ziel


def _effektives_universum(typ: str, num: int, extern) -> int | None:
    """Welche externe Universe-Nummer geht raus? — Defaults je Protokoll.

    ⚠️ **Die Defaults sind NICHT gleich**, und genau daran ist die erste Fassung
    gescheitert: sie rechnete fuer alle Typen ``num - 1``. ``_send_all``
    (``output_manager.py``) macht aber

        artnet.send_dmx(ext if ext is not None else univ_num - 1, data)
        sacn.send_dmx(  ext if ext is not None else univ_num,     data)

    — Art-Net zaehlt ab 0, sACN ab 1. Folge der falschen Annahme: sACN-Zeile 1
    ohne Angabe (geht real auf 1) und sACN-Zeile 2 mit ausdruecklicher 1 (geht
    real auf 1) bekamen die Schluessel 0 und 1 — **eine echte Kollision ohne
    Warnung**. Und umgekehrt lieferte sACN-Zeile 2 ohne Angabe (real 2) mit
    Zeile 3 auf ausdruecklich 1 (real 1) beide Male den Schluessel 1 — ein
    **Fehlalarm**. Der Dialog meldete also mal nichts, mal das Falsche.

    ``None`` fuer Enttec: dort gibt es gar keine externe Nummer
    (``enttec.send_dmx(data)`` ohne Universum). Zwei Zeilen auf demselben Port
    kollidieren deshalb IMMER — ihre internen Nummern sind dafuer bedeutungslos.
    """
    if typ == "Enttec":
        return None
    if extern is not None:
        return int(extern)
    return num if typ == "sACN" else num - 1


def _doppelte_ziele(rows: list[dict]) -> list[tuple[str, str]]:
    """OUT-07: findet Universen, die auf dasselbe Ziel senden.

    Zwei Zeilen kollidieren, wenn sie denselben **Adaptertyp**, dasselbe
    **effektive Ziel** (Port bzw. IP nach Default-Aufloesung) und dieselbe
    **effektive externe Universe-Nummer** haben — beides so gerechnet, wie der
    Sende-Pfad es tut, nicht wie das Eingabefeld es zeigt (s.
    ``_effektives_ziel`` / ``_effektives_universum``).

    **Warum nur melden und nicht korrigieren:** welches der beiden Universen
    gemeint war, weiss nur der Bediener. Automatisch umzunummerieren hiesse zu
    raten — und im schlechtesten Fall schaltet man damit das falsche Rig dunkel.
    Reine Diagnose also, dieselbe Haltung wie bei `enttec_pro.diagnose_port()`.

    Rueckgabe: je Kollision ein Paar (Zeilenliste, Beschreibung) — leer, wenn
    alles eindeutig ist.
    """
    gesehen: dict[tuple, list[int]] = {}
    for i, e in enumerate(rows, start=1):
        typ = (e.get("output") or "Disabled").strip()
        if typ in ("", "Disabled"):
            continue                       # abgeschaltet kollidiert mit nichts
        # Reihenfolge: erst das Universum, dann das Ziel — bei sACN haengt die
        # Multicast-Adresse vom Universum ab (s. `_effektives_ziel`).
        extern = _effektives_universum(
            typ, int(e.get("num", 1)), e.get("out_universe"))
        ziel = _effektives_ziel(typ, (e.get("patch") or "").strip(), extern)
        gesehen.setdefault((typ, ziel, extern), []).append(i)

    treffer = []
    for (typ, ziel, extern), zeilen in gesehen.items():
        if len(zeilen) < 2:
            continue
        wohin = ziel or "Standard-Ziel"
        # Enttec hat keine externe Nummer — sie in der Meldung zu erfinden waere
        # irrefuehrend ("externes Universum None" erst recht).
        was = (f"{typ} → {wohin}" if extern is None
               else f"{typ} → {wohin}, externes Universum {extern}")
        treffer.append((", ".join(f"Zeile {z}" for z in zeilen), was))
    return treffer


def _coerce_universe_num(text, fallback: int) -> tuple[int, bool]:
    """Universe-Nummer aus einem freien Tabellenfeld robust in den gueltigen
    Bereich [``_UNIVERSE_MIN``..``_UNIVERSE_MAX``] zwingen.

    Rueckgabe ``(nummer, angepasst?)``:
    - Nicht parsebar (leer/Muell) -> ``(fallback, False)``: unveraendertes Verhalten,
      der Aufrufer setzt still den Zeilen-Default (Zeilenindex+1).
    - Parsebar aber ausserhalb -> auf die naechste Grenze geklemmt, ``angepasst=True``.
    - Innerhalb -> ``(nummer, False)``.
    """
    try:
        n = int(str(text).strip())
    except (ValueError, TypeError, AttributeError):
        return fallback, False
    clamped = max(_UNIVERSE_MIN, min(_UNIVERSE_MAX, n))
    return clamped, clamped != n


def _load_universe_config() -> list[dict]:
    if not os.path.exists(_UNIV_CONFIG_PATH):
        return []
    try:
        with open(_UNIV_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_universe_config(rows: list[dict]) -> bool:
    """Schreibt ``universes.json``. ``True`` = geschrieben, ``False`` = nicht.

    QA-50: Der Rueckgabewert ist der ganze Punkt. Vorher verschwand ein
    Schreibfehler in einem ``print``, und der Dialog meldete anschliessend
    „Gespeichert" — bei vollem Datentraeger, fehlenden Rechten oder einem
    schreibgeschuetzten Ordner also eine Erfolgsmeldung fuer etwas, das nie
    passiert ist. Beim naechsten Start stand dann die alte Konfiguration da
    und niemand wusste, warum.

    Vorbild ist ``channel_groups_view.py``, das schon so gebaut ist: bool
    zurueckgeben, der Aufrufer prueft und meldet.
    """
    try:
        os.makedirs(os.path.dirname(_UNIV_CONFIG_PATH), exist_ok=True)
        with open(_UNIV_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[output_config] save universes error: {e}")
        return False


def _gespeicherte_ausgabe_zeile(typ: str) -> dict | None:
    """OUT-50: die gespeicherte ``universes.json``-Zeile fuer einen Ausgabetyp
    (``"Enttec"`` / ``"ArtNet"`` / ``"sACN"``) — oder ``None``.

    Der **gemeinsame Ladepfad** aller drei Tabs. Bis OUT-50 gab es ihn nur fuer
    das Enttec-Universum (OUT-ENTTECUNIV); Art-Net, sACN und der COM-Port lasen
    ihren gespeicherten Wert nie und starteten jedes Mal auf dem Widget-Default.

    **Mehrere Zeilen -> die KLEINSTE Universumsnummer gewinnt** — willkuerlich,
    aber vorhersehbar. Bei Enttec ist mehr als eine Zeile ohnehin schon ein
    Konfigurationsfehler (ein Enttec Pro hat einen Ausgang). Bei Art-Net/sACN
    ist es dagegen ein voellig normales Mehr-Universen-Setup: der Tab kann nur
    EINES zeigen, und dann ist die kleinste Nummer die harmloseste Wahl. Wer
    mehrere Universen pflegt, tut das im Universen-Tab — der zeigt alle.

    ``num`` ausserhalb [1..32] und unparsbare Zeilen werden uebergangen: eine
    kaputte Zeile darf den Dialog nicht aufhalten.

    Der Typ-Vergleich ist bewusst **exakt und case-sensitiv** — genau wie in
    ``AppState.apply_output_config``. Beide muessen dieselbe Zeile meinen, sonst
    zeigt der Dialog etwas anderes an, als die App tatsaechlich eingerichtet hat.
    """
    treffer: list[tuple[int, dict]] = []
    for r in _load_universe_config():
        if not isinstance(r, dict):
            continue
        try:
            if (r.get("output") or "").strip() != typ:
                continue
            num = int(r.get("num", 0))
        except (TypeError, ValueError, AttributeError):
            continue
        if _UNIVERSE_MIN <= num <= _UNIVERSE_MAX:
            treffer.append((num, r))
    if not treffer:
        return None
    return min(treffer, key=lambda t: t[0])[1]


def _patch_text(zeile: dict) -> str:
    """Das ``patch``-Feld einer Zeile als getrimmter Text.

    ``universes.json`` ist eine von Hand editierbare Datei. Steht dort etwas
    anderes als ein String (``"patch": 3``), wuerde ``.strip()`` mit einem
    ``AttributeError`` aus dem Konstruktor fliegen — und der Ausgabe-Dialog
    liesse sich **gar nicht mehr oeffnen**, also ausgerechnet das Werkzeug,
    mit dem man den Fehler beheben wuerde. Eine kaputte Zeile darf hoechstens
    ihren eigenen Wert kosten.
    """
    wert = zeile.get("patch")
    return "" if wert is None else str(wert).strip()


def _gespeichertes_enttec_universum(vorgabe: int = 1) -> int:
    """Universumsnummer der gespeicherten Enttec-Zeile (OUT-ENTTECUNIV).

    Liefert die Nummer des Universums, das zuletzt auf Enttec stand. Gibt es
    mehrere, gewinnt die KLEINSTE — willkuerlich, aber vorhersehbar; ein Enttec
    Pro hat ohnehin nur einen Ausgang, mehrere Zeilen sind bereits ein
    Konfigurationsfehler.

    Ohne gespeicherte Enttec-Zeile bleibt es bei ``vorgabe`` (1) — das ist der
    Zustand einer frischen Installation und dort auch richtig.
    """
    zeile = _gespeicherte_ausgabe_zeile("Enttec")
    if zeile is None:
        return int(vorgabe)
    return int(zeile.get("num", vorgabe))


def _gespeicherter_enttec_port() -> str:
    """OUT-50 (a): der zuletzt benutzte COM-Port der Enttec-Zeile — oder ``""``.

    Die zweite Haelfte von HW-5c: ``_refresh_ports`` fuellte die Liste, waehlte
    aber nie den gespeicherten Port vor. „Verbinden" nahm damit den **ersten
    Port der Liste** — auf einem Rechner mit mehreren FTDI-Geraeten also ein
    beliebiges anderes — und schrieb ihn ueber ``_persist_output`` auch noch
    nach ``universes.json`` zurueck. Genau dasselbe Muster wie beim Universum.
    """
    zeile = _gespeicherte_ausgabe_zeile("Enttec")
    return _patch_text(zeile) if zeile else ""


_UNSET = object()   # A3D-15: "Argument nicht uebergeben" vs. explizit None unterscheiden.


def _persist_output(num: int, output: str, patch: str, out_universe=_UNSET) -> bool:
    """Schreibt/aktualisiert eine Zeile in universes.json, damit eine zur
    Laufzeit hergestellte Ausgabe-Verbindung beim naechsten Start automatisch
    wieder eingerichtet wird (apply_output_config). Ohne das war jede Verbindung
    nach einem Neustart weg -> 'es kommt kein Output'.

    A3D-15: ``out_universe`` = externe Art-Net-/sACN-Universe-Nummer.
    - ``_UNSET`` (Default) = das Feld NICHT anfassen. Wichtig: Enttec-/sACN-
      „Übernehmen" rufen ohne Wert und duerfen eine per Universe-Tabelle (OUT-03)
      gesetzte externe Universe NICHT loeschen (Review-Fund: sonst stiller
      Datenverlust + falscher Output ueber Neustarts).
    - ``None`` = explizit entfernen (Art-Net-Default univ-1, leer = Default wie die
      Tabellen-Spalte).
    - Wert = setzen. So ueberlebt die im Art-Net-Tab gewaehlte externe Universe
      einen Neustart (apply_output_config liest sie).

    QA-50: Gibt jetzt zurueck, ob die Datei wirklich geschrieben wurde. Die
    Aufrufer haengen ihre „(gespeichert)"-Meldung daran — sonst steht dort
    Erfolg, waehrend die Einstellung den naechsten Start nicht ueberlebt.
    """
    rows = _load_universe_config()
    found = False
    for r in rows:
        if int(r.get("num", -1)) == int(num):
            r["output"] = output
            r["patch"] = patch
            if out_universe is None:
                r.pop("out_universe", None)
            elif out_universe is not _UNSET:
                r["out_universe"] = int(out_universe)
            found = True
            break
    if not found:
        entry = {"num": int(num), "name": f"Universe {num}",
                 "output": output, "patch": patch}
        if out_universe is not None and out_universe is not _UNSET:
            entry["out_universe"] = int(out_universe)
        rows.append(entry)
    return _save_universe_config(rows)


class OutputConfigDialog(QDialog):
    # OUT-51: So oft wird nach „Verbinden" hoechstens nachgefragt, ob der Port
    # wirklich offen ist (je ~0,9 s). Der Serial-Worker wird als eigener Prozess
    # gestartet — bis der den Port offen hat, vergeht ein Moment, und in dieser
    # Zeit waeren „Verbunden" und „geht nicht" beide gelogen.
    _MAX_PRUEF_VERSUCHE = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ausgabe konfigurieren")
        self.setMinimumWidth(500)
        # MU-02 (Review): das je Tab TATSAECHLICH belegte Universum merken, damit
        # das Abwaehlen genau dieses raeumt und nicht den aktuellen Spin-Wert (der
        # inzwischen auf ein fremdes Universum zeigen kann).
        self._artnet_active_univ: int | None = None
        self._sacn_active_univ: int | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()

        # ── Enttec Tab ────────────────────────────────────────────────────────
        enttec_tab = QWidget()
        ef = QFormLayout(enttec_tab)

        self._combo_port = QComboBox()
        self._refresh_ports()
        ef.addRow("COM-Port:", self._combo_port)

        refresh_btn = QPushButton("Ports aktualisieren")
        # ★ Bewusst eine parameterlose Bound-Method statt eines Lambdas — aus
        # ZWEI Gruenden, und beide sind schon einmal teuer geworden:
        #  * `clicked` liefert ein `checked`-Bool als erstes Argument. Direkt an
        #    `_refresh_ports` gehaengt landete das in `bevorzugt` und der
        #    Parameter meinte etwas anderes als sein Name sagt.
        #  * Ein `self` fangendes Lambda pinnt den Dialog GC-unsichtbar
        #    (Dialog -> Button -> Lambda -> Dialog), Fallenklasse STAB-09/10.
        #    Bound-Methods haelt PySide dagegen nur schwach.
        refresh_btn.clicked.connect(self._ports_neu_einlesen)
        ef.addRow("", refresh_btn)

        self._spin_enttec_univ = QSpinBox()
        self._spin_enttec_univ.setRange(1, 32)
        # ★ OUT-ENTTECUNIV: die gespeicherte Universumsnummer VORBELEGEN.
        # (Belegt wird sie jetzt im gemeinsamen `_lade_gespeicherte_ausgaben`
        # am Ende von `_setup_ui` — zusammen mit Port, Art-Net und sACN, die
        # nach OUT-50 an genau demselben fehlenden Ladeschritt litten.)
        #
        # Ohne das stand die Spinbox bei jedem Oeffnen des Ausgabe-Tabs auf dem
        # Minimum der Range, also auf 1 — der gespeicherte Wert wurde nie
        # gelesen (vier Fundstellen fuer dieses Widget, davon KEINE ladend).
        # Ein Klick auf „Verbinden" nahm dann diese 1, oeffnete den Enttec auf
        # Universum 1 und schrieb das ueber `_persist_output` auch noch zurueck
        # in universes.json.
        #
        # Folgen, die genau so bei David auftraten (2026-08-05, echtes Geraet):
        #  * Sein Balken haengt auf Universum 3. Nach jedem Besuch des
        #    Ausgabe-Tabs sendete LightOS Universum 1 auf die Leitung — einen
        #    LEEREN Puffer. Gemessen: Puffer U3 = 145 Kanaele > 0, gesendet
        #    wurden 0 Bytes > 0. Die Software rechnete richtig und schickte das
        #    falsche Universum.
        #  * Die Auswahl „hielt nicht": Tab zu, Tab auf, wieder Universum 1.
        #  * Und es erklaert HW-5c — den seit Wochen offenen „Rueckfall in
        #    universes.json, Ursache offen". Die Ursache war dieses Widget.
        ef.addRow("Universe:", self._spin_enttec_univ)

        connect_btn = QPushButton("Verbinden")
        connect_btn.clicked.connect(self._connect_enttec)
        self._lbl_enttec_status = QLabel("Nicht verbunden")
        ef.addRow("", connect_btn)
        ef.addRow("Status:", self._lbl_enttec_status)

        tabs.addTab(enttec_tab, "Enttec Pro USB")

        # ── Art-Net Tab ───────────────────────────────────────────────────────
        artnet_tab = QWidget()
        af = QFormLayout(artnet_tab)

        self._check_artnet = QCheckBox("Art-Net aktivieren")
        af.addRow(self._check_artnet)

        # ── NET-04: Ausgangs-Netzwerkkarte ───────────────────────────────────
        # Bis hierhin ging das nur ueber die Env-Variable LIGHTOS_OUTPUT_IFACE,
        # im Betrieb also gar nicht. Auf einem Venue-PC mit WLAN UND Lichtnetz
        # sendet Linux den Broadcast nur ueber die Default-Route — die Fixtures
        # bleiben schwarz, waehrend die Oberflaeche „Aktiv" meldet.
        #
        # Geraetegebunden gespeichert (ui_prefs.json), NICHT in der Show: die
        # Netzwerkkarte ist eine Eigenschaft des RECHNERS, die Show wandert
        # zwischen Rechnern. Dieselbe Ueberlegung wie bei viz_quality_tier.
        self._combo_iface = QComboBox()
        self._combo_iface.addItem("Automatisch (Betriebssystem entscheidet)", "")
        for eintrag in _list_ifaces():
            bcast = eintrag.get("broadcast")
            text = f"{eintrag['name']} — {eintrag['ip']}"
            if bcast:
                text += f"  (Broadcast {bcast})"
            else:
                text += "  (kein Subnetz erkannt)"
            self._combo_iface.addItem(text, eintrag["ip"])
        gewaehlt = _iface_pref()
        if gewaehlt:
            i = self._combo_iface.findData(gewaehlt)
            if i >= 0:
                self._combo_iface.setCurrentIndex(i)
            else:
                # Die gespeicherte Karte gibt es nicht mehr (anderes Netz,
                # USB-Adapter abgezogen). NICHT stillschweigend auf Automatik
                # zuruecksetzen — dann suchte der Nutzer den Fehler im Rig.
                self._combo_iface.addItem(
                    f"{gewaehlt} — derzeit nicht gefunden", gewaehlt)
                self._combo_iface.setCurrentIndex(self._combo_iface.count() - 1)
        self._combo_iface.setToolTip(
            "Ueber welche Netzwerkkarte Art-Net und sACN hinausgehen.\n"
            "Automatisch = wie bisher ueber die Standardroute des Systems.\n"
            "Mit gewaehlter Karte geht Art-Net an deren gerichteten\n"
            "Broadcast (z. B. 192.168.1.255) statt an 255.255.255.255 —\n"
            "der wird von Routern nicht weitergereicht.\n"
            "Gilt fuer diesen Rechner, nicht fuer die Show. Neue Verbindungen\n"
            "nutzen die Karte sofort, bestehende ab dem naechsten Start.")
        self._combo_iface.currentIndexChanged.connect(self._apply_iface_choice)
        af.addRow("Netzwerkkarte:", self._combo_iface)

        # OUT-04: Ziel-Universum, auf das „Übernehmen" wirkt (analog Enttec) — nicht
        # mehr pauschal ALLE Universen. (Das separate „Startuniversum"-Feld unten ist
        # die EXTERNE Universe-Nummer und gehört zu OUT-03.)
        self._spin_artnet_univ = QSpinBox()
        self._spin_artnet_univ.setRange(1, 32)
        af.addRow("Universe:", self._spin_artnet_univ)

        self._edit_artnet_ip = QLineEdit("255.255.255.255")
        af.addRow("Ziel-IP / Broadcast:", self._edit_artnet_ip)

        self._spin_artnet_start_univ = QSpinBox()
        self._spin_artnet_start_univ.setRange(0, 32767)
        self._spin_artnet_start_univ.setToolTip(
            'Externe Art-Net-Universe-Nummer für "Übernehmen". Default = '
            'internes Universum − 1 (abwärtskompatibel).')
        af.addRow("Art-Net Startuniversum:", self._spin_artnet_start_univ)
        # A3D-15: die externe Universe folgt standardmaessig dem internen Universum
        # (univ-1 = Alt-Verhalten) bzw. einer bereits gespeicherten Wahl — so setzt
        # ein unbeabsichtigtes „Übernehmen" nicht still auf Universe 0/eine falsche
        # Nummer und eine gespeicherte externe Universe wird beim Neuwahl gezeigt.
        self._spin_artnet_univ.valueChanged.connect(self._sync_artnet_start_univ_default)
        self._sync_artnet_start_univ_default()

        apply_artnet_btn = QPushButton("Übernehmen")
        apply_artnet_btn.clicked.connect(self._apply_artnet)
        self._lbl_artnet_status = QLabel("Inaktiv")
        af.addRow("", apply_artnet_btn)
        af.addRow("Status:", self._lbl_artnet_status)

        tabs.addTab(artnet_tab, "Art-Net")

        # ── sACN Tab ──────────────────────────────────────────────────────────
        sacn_tab = QWidget()
        sf = QFormLayout(sacn_tab)

        self._check_sacn = QCheckBox("sACN (E1.31) aktivieren")
        sf.addRow(self._check_sacn)

        # OUT-04: Ziel-Universum, auf das „Übernehmen" wirkt (nicht mehr alle).
        self._spin_sacn_univ = QSpinBox()
        self._spin_sacn_univ.setRange(1, 32)
        sf.addRow("Universe:", self._spin_sacn_univ)

        self._check_sacn_multicast = QCheckBox("Multicast (239.255.0.x)")
        self._check_sacn_multicast.setChecked(True)
        sf.addRow(self._check_sacn_multicast)

        self._edit_sacn_ip = QLineEdit("")
        self._edit_sacn_ip.setPlaceholderText("Leer = Multicast")
        sf.addRow("Unicast Ziel-IP:", self._edit_sacn_ip)

        apply_sacn_btn = QPushButton("Übernehmen")
        apply_sacn_btn.clicked.connect(self._apply_sacn)
        self._lbl_sacn_status = QLabel("Inaktiv")
        sf.addRow("", apply_sacn_btn)
        sf.addRow("Status:", self._lbl_sacn_status)

        tabs.addTab(sacn_tab, "sACN (E1.31)")

        # ── DMX Input Tab ──────────────────────────────────────────────────────
        input_tab = QWidget()
        if_l = QVBoxLayout(input_tab)
        if_l.addWidget(QLabel(
            "Empfängt DMX-Daten via Art-Net (Port 6454) oder sACN (Port 5568)\n"
            "und mergt sie in lokale Universen (HTP / LTP / REPLACE)."
        ))

        # Art-Net Input
        ain_box = QGroupBox("Art-Net Input")
        ain_l = QFormLayout(ain_box)
        self._check_artnet_in = QCheckBox("Art-Net Input aktivieren")
        ain_l.addRow(self._check_artnet_in)

        self._spin_artnet_in_univ = QSpinBox()
        self._spin_artnet_in_univ.setRange(1, 32767)
        self._spin_artnet_in_univ.setValue(1)
        ain_l.addRow("Eingehendes Universe:", self._spin_artnet_in_univ)

        self._spin_artnet_in_out = QSpinBox()
        self._spin_artnet_in_out.setRange(1, 32)
        self._spin_artnet_in_out.setValue(1)
        ain_l.addRow("Merge in Universe:", self._spin_artnet_in_out)

        self._combo_artnet_in_mode = QComboBox()
        self._combo_artnet_in_mode.addItems(["HTP", "LTP", "REPLACE"])
        ain_l.addRow("Merge-Modus:", self._combo_artnet_in_mode)

        ain_btn = QPushButton("Übernehmen")
        ain_btn.clicked.connect(self._apply_artnet_input)
        self._lbl_artnet_in_status = QLabel("Inaktiv")
        ain_l.addRow("", ain_btn)
        ain_l.addRow("Status:", self._lbl_artnet_in_status)
        if_l.addWidget(ain_box)

        # sACN Input
        sin_box = QGroupBox("sACN Input")
        sin_l = QFormLayout(sin_box)
        self._check_sacn_in = QCheckBox("sACN Input aktivieren")
        sin_l.addRow(self._check_sacn_in)

        self._spin_sacn_in_univ = QSpinBox()
        self._spin_sacn_in_univ.setRange(1, 63999)
        self._spin_sacn_in_univ.setValue(1)
        sin_l.addRow("Eingehendes Universe:", self._spin_sacn_in_univ)

        self._spin_sacn_in_out = QSpinBox()
        self._spin_sacn_in_out.setRange(1, 32)
        self._spin_sacn_in_out.setValue(1)
        sin_l.addRow("Merge in Universe:", self._spin_sacn_in_out)

        self._combo_sacn_in_mode = QComboBox()
        self._combo_sacn_in_mode.addItems(["HTP", "LTP", "REPLACE"])
        sin_l.addRow("Merge-Modus:", self._combo_sacn_in_mode)

        sin_btn = QPushButton("Übernehmen")
        sin_btn.clicked.connect(self._apply_sacn_input)
        self._lbl_sacn_in_status = QLabel("Inaktiv")
        sin_l.addRow("", sin_btn)
        sin_l.addRow("Status:", self._lbl_sacn_in_status)
        if_l.addWidget(sin_box)

        if_l.addStretch(1)
        tabs.addTab(input_tab, "DMX Input")

        # ── Universe Manager Tab ───────────────────────────────────────────────
        univ_tab = QWidget()
        uf = QVBoxLayout(univ_tab)
        uf.addWidget(QLabel(
            "Universen verwalten - bis zu 32 Universen.\n"
            "Pro Universe: Name, Output-Typ (Disabled / Enttec / sACN / ArtNet), "
            "Patch-Adresse, optionale externe Universe-Nummer."
        ))
        self._univ_table = QTableWidget(0, 5)
        self._univ_table.setHorizontalHeaderLabels(
            ["#", "Name", "Output", "Patch (Port/IP)", "Ext-Universe"]
        )
        # OUT-03: "Ext-Universe" = optionale externe Art-Net/sACN-Universe-Nummer.
        # Leer = Default (Art-Net num-1, sACN num).
        self._univ_table.horizontalHeaderItem(4).setToolTip(
            "Optionale externe Art-Net/sACN-Universe-Nummer. "
            "Leer = Standard (Art-Net #-1, sACN #)."
        )
        self._univ_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._univ_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._univ_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._univ_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._univ_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._univ_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        uf.addWidget(self._univ_table, 1)

        uf_btns = QHBoxLayout()
        b_add = QPushButton("+ Universe hinzufügen")
        b_add.clicked.connect(self._univ_add)
        b_del = QPushButton("Löschen")
        b_del.setObjectName("btn_danger")
        b_del.clicked.connect(self._univ_delete)
        b_save = QPushButton("Speichern")
        b_save.clicked.connect(self._univ_save)
        uf_btns.addWidget(b_add); uf_btns.addWidget(b_del); uf_btns.addWidget(b_save)
        uf_btns.addStretch(1)
        uf.addLayout(uf_btns)
        tabs.addTab(univ_tab, "Universen")
        self._univ_load_table()

        # ★ OUT-50: ALLE Ausgabe-Tabs aus universes.json vorbelegen — der eine
        # Schritt, den es bis hierhin nur fuer das Enttec-Universum gab.
        self._lade_gespeicherte_ausgaben()

        layout.addWidget(tabs)

        btn_close = QPushButton("Schließen")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def _lade_gespeicherte_ausgaben(self):
        """★ OUT-50 — der gemeinsame Ladeschritt fuer Enttec, Art-Net und sACN.

        **Warum es diesen Schritt braucht.** Am 2026-08-05 blieb Davids
        LED-Balken dunkel, weil die Enttec-Universumsspinbox ihren gespeicherten
        Wert nie las (OUT-ENTTECUNIV). Der Audit danach fand denselben Fehler
        noch **dreimal im selben Dialog**: der COM-Port, der komplette
        Art-Net-Tab und der komplette sACN-Tab wurden ebenfalls nie geladen.
        Jedes Oeffnen des Dialogs zeigte also Widget-Defaults statt der
        Wirklichkeit — und weil „Verbinden"/„Uebernehmen" den angezeigten Wert
        **zurueckschreiben**, war das nicht nur eine falsche Anzeige, sondern
        ein Ueberschreiben der echten Konfiguration:

        * Art-Net: Universum 1 und ``255.255.255.255`` statt der gespeicherten
          Zeile -> „Uebernehmen" legte eine **Phantom-Zeile auf Universum 1** an.
        * sACN: der Multicast-Haken stand **hart auf True** -> „Uebernehmen"
          ersetzte eine gespeicherte Unicast-IP durch einen Leerstring.
        * COM-Port: siehe ``_gespeicherter_enttec_port``.

        **Die Datei ist hier die richtige Quelle**, nicht der laufende
        ``OutputManager``: genau diese Zeilen wendet ``apply_output_config``
        beim Start an. Was hier steht, ist also das, was eingerichtet wurde.

        **Und deshalb steht in den Status-Labels „Gespeichert", nicht „Aktiv".**
        Ob der Adapter wirklich sendet, weiss dieser Dialog nicht — der Port
        kann seit dem Start weg sein. Eine gruene „Aktiv"-Meldung aus einer
        Datei zu bauen waere exakt die Fehlerklasse, die OUT-51 aufarbeitet
        (Anzeige meldet Anwesenheit statt Zustand). Hier wird nur behauptet,
        was belegt ist: was in ``universes.json`` steht.

        Fehlt eine Zeile, bleibt der Tab bei seinen Defaults — der Zustand einer
        frischen Installation, und dort sind sie richtig.
        """
        # ── Enttec ────────────────────────────────────────────────────────────
        enttec = _gespeicherte_ausgabe_zeile("Enttec")
        if enttec is not None:
            num = int(enttec.get("num", 1))
            port = _patch_text(enttec)
            self._spin_enttec_univ.setValue(num)
            if port:
                self._enttec_port_waehlen(port)
                self._lbl_enttec_status.setText(
                    f"Gespeichert: {port} → Universe {num}")

        # ── Art-Net ───────────────────────────────────────────────────────────
        artnet = _gespeicherte_ausgabe_zeile("ArtNet")
        if artnet is not None:
            num = int(artnet.get("num", 1))
            ip = _patch_text(artnet)
            self._spin_artnet_univ.setValue(num)
            if ip:
                self._edit_artnet_ip.setText(ip)
            self._check_artnet.setChecked(True)
            # MU-02: das belegte Universum merken, sonst raeumt ein Abwaehlen
            # („Art-Net aktivieren" aus + „Uebernehmen") gar nichts — der Haken
            # waere zwar erstmals ehrlich gesetzt, aber wirkungslos abwaehlbar.
            self._artnet_active_univ = num
            self._lbl_artnet_status.setText(
                f"Gespeichert: {ip or 'Broadcast'} · Universe {num}")
        # Erst NACH dem Setzen des Universums: die externe Art-Net-Universe
        # (A3D-15) haengt am gewaehlten internen Universum. Explizit gerufen,
        # weil `setValue` bei unveraendertem Wert kein `valueChanged` sendet.
        self._sync_artnet_start_univ_default()

        # ── sACN ──────────────────────────────────────────────────────────────
        sacn = _gespeicherte_ausgabe_zeile("sACN")
        if sacn is not None:
            num = int(sacn.get("num", 1))
            ip = _patch_text(sacn)
            self._spin_sacn_univ.setValue(num)
            self._edit_sacn_ip.setText(ip)
            # Leerer patch = Multicast (so liest es apply_output_config und so
            # schreibt es `_apply_sacn`). Der Haken folgt der Datei, statt
            # unabhaengig von ihr auf True zu stehen.
            self._check_sacn_multicast.setChecked(not ip)
            self._check_sacn.setChecked(True)
            self._sacn_active_univ = num
            self._lbl_sacn_status.setText(
                f"Gespeichert: {('Unicast → ' + ip) if ip else 'Multicast'}"
                f" · Universe {num}")

    def _apply_iface_choice(self):
        """NET-04: Auswahl geraetegebunden sichern.

        Bewusst OHNE Neustart der laufenden Sender: die greifen die NIC beim
        naechsten Aufbau ab (`ArtNetSender.__init__`, `bind_to_output_iface`).
        Sie hier mitten im Betrieb neu zu bauen hiesse, den DMX-Strom fuer einen
        Moment abreissen zu lassen — waehrend Licht auf der Buehne steht.
        Der Hinweistext sagt genau das.
        """
        ip = self._combo_iface.currentData() or ""
        try:
            from src.ui.views.programmer_view import _save_prefs
            _save_prefs({"output_iface_ip": ip})
        except Exception as e:
            print(f"[output_config] iface-Pref nicht gespeichert: {e}")

    def _ports_neu_einlesen(self):
        """Slot des „Ports aktualisieren"-Knopfes (s. Begruendung dort)."""
        self._refresh_ports()

    def _refresh_ports(self, bevorzugt: str | None = None):
        """Portliste neu aufbauen — **ohne die Auswahl zu verlieren**.

        OUT-50 (a): vorher fuellte diese Methode nur die Liste. Damit stand nach
        jedem Aufbau (und nach jedem Klick auf „Ports aktualisieren") der ERSTE
        Port da, und „Verbinden" nahm ihn. Jetzt gewinnt in dieser Reihenfolge:
        ein ausdruecklich uebergebener Port, sonst die aktuelle Auswahl, sonst
        der in ``universes.json`` gespeicherte.
        """
        aktuell = (bevorzugt or self._combo_port.currentData()
                   or _gespeicherter_enttec_port())
        self._combo_port.clear()
        for p in serial.tools.list_ports.comports():
            label = f"{p.device}"
            if p.description:
                label += f"  —  {p.description}"
            if p.vid == ENTTEC_VID and p.pid == ENTTEC_PID:
                label += "  [Enttec Pro]"
            self._combo_port.addItem(label, p.device)
        self._enttec_port_waehlen(aktuell)
        if self._combo_port.count() == 0:
            self._combo_port.addItem("Kein Port gefunden", "")

    def _enttec_port_waehlen(self, port: str | None):
        """Einen Port in der Liste auswaehlen; fehlt er, ihn sichtbar machen.

        ★ Der fehlende Port darf NICHT still auf den ersten zurueckfallen —
        genau das ist der Fehler, den OUT-50 behebt. Ein Enttec-Kabel steckt mal
        woanders, ein Portname kann von einer anderen Plattform stammen
        (``COM3`` auf Linux, HW-5b). Faellt die Auswahl dann stumm auf ein
        fremdes FTDI-Geraet, oeffnet „Verbinden" das falsche Geraet **und
        speichert es**. Deshalb dasselbe Vorgehen wie bei der Netzwerkkarte
        (NET-04): als „derzeit nicht gefunden" anhaengen und auswaehlen. Ein
        Klick auf „Verbinden" scheitert dann sichtbar im Status-Label — das ist
        die ehrlichere von zwei Fehlermeldungen.
        """
        if not port:
            return
        i = self._combo_port.findData(port)
        if i >= 0:
            self._combo_port.setCurrentIndex(i)
            return
        self._combo_port.addItem(f"{port} — derzeit nicht gefunden", port)
        self._combo_port.setCurrentIndex(self._combo_port.count() - 1)

    def _connect_enttec(self):
        port = self._combo_port.currentData()
        if not port:
            self._lbl_enttec_status.setText("Kein Port gewählt")
            return
        univ = self._spin_enttec_univ.value()
        state = get_state()
        om = state.output_manager

        # Sicherstellen dass das Universe existiert
        if univ not in state.universes:
            state.universes[univ] = om.add_universe(univ)

        # add_enttec() ist thread-sicher: es schliesst eine evtl. offene
        # Verbindung auf demselben Port/Universe selbst (unter dem Output-Lock),
        # bevor es die neue oeffnet. KEIN direkter Zugriff auf om._enttec_outputs
        # aus dem UI-Thread mehr -> verhindert den Deadlock mit dem Output-Thread.
        try:
            # MU-01: erst ALLE Alt-Adapter dieses Universums entfernen/schliessen
            # (auch ArtNet/sACN), sonst bleibt bei einem Cross-Typ-Wechsel der alte
            # Adapter aktiv -> Doppel-Output/Leak. Analog apply_output_config (OUT-05).
            om.remove_output(univ)
            om.add_enttec(univ, port)
            # QA-50: „(gespeichert)" nur sagen, wenn es auch gespeichert ist.
            gespeichert = _persist_output(univ, "Enttec", port)
            # ★ OUT-51: NICHT „Verbunden" melden. `add_enttec` startet den
            # Serial-Worker, mehr weiss es in diesem Moment nicht — der Port
            # kann tot sein, und dann stand hier trotzdem gruen „Verbunden".
            # Der Erfolg, den dieser Zweig sicher kennt, ist „eingerichtet und
            # gespeichert"; ob DMX rausgeht, sagt erst der Adapter selbst,
            # gleich, und dann traegt es `_enttec_status_nachtragen` nach.
            self._lbl_enttec_status.setText(
                f"Eingerichtet: {port} → Universe {univ} "
                f"{'(gespeichert)' if gespeichert else '(NICHT gespeichert!)'}, "
                f"verbinde …")
            self._enttec_pruef_univ = univ
            self._enttec_pruef_versuche = 0
            self._enttec_status_pruefen_spaeter()
        except Exception as e:
            self._lbl_enttec_status.setText(f"Fehler: {e}")

    # ── OUT-51: den echten Verbindungsstatus nachtragen ──────────────────────

    def _enttec_status_pruefen_spaeter(self, ms: int = 900):
        """Den Adapter gleich noch einmal fragen — der Timer haengt am Dialog.

        ``QTimer(self)`` statt ``QTimer.singleShot``: so stirbt der Timer mit
        dem Dialog. Ein freier SingleShot dagegen feuerte auch dann noch, wenn
        der Nutzer den Dialog laengst geschlossen hat — der Slot liefe auf ein
        zerstoertes C++-Objekt (``RuntimeError``).
        """
        t = getattr(self, "_enttec_pruef_timer", None)
        if t is None:
            t = QTimer(self)
            t.setSingleShot(True)
            t.timeout.connect(self._enttec_status_nachtragen)
            self._enttec_pruef_timer = t
        t.start(ms)

    def _enttec_status_nachtragen(self):
        """Meldet, ob der eben eingerichtete Adapter WIRKLICH sendet.

        Solange der Worker noch im Verbindungsaufbau steckt, fragt die Methode
        gedrosselt weiter (bis ``_MAX_PRUEF_VERSUCHE``) — der Spawn des
        Serial-Prozesses und das Oeffnen des Ports brauchen ein paar hundert
        Millisekunden, und in dieser Zeit waere jede der beiden Endaussagen
        falsch.
        """
        from src.core.dmx.output_manager import (
            geraet_zustand, ZUSTAND_SENDET, ZUSTAND_TOT, ZUSTAND_VERBINDET)
        univ = getattr(self, "_enttec_pruef_univ", None)
        if univ is None:
            return
        try:
            dev = get_state().output_manager._enttec_outputs.get(univ)
        except Exception:
            dev = None
        if dev is None:
            # Adapter ist inzwischen wieder weg (anderer Tab, Universe-Wechsel)
            # -> keine Meldung ueber etwas, das es nicht mehr gibt.
            return
        zustand = geraet_zustand(dev)
        port = getattr(dev, "port", "?")
        if zustand == ZUSTAND_VERBINDET:
            self._enttec_pruef_versuche += 1
            if self._enttec_pruef_versuche < self._MAX_PRUEF_VERSUCHE:
                self._enttec_status_pruefen_spaeter()
                return
            # Nach der Anlaufzeit immer noch „verbindet": das ist keine
            # Erfolgsmeldung mehr, aber auch kein bewiesener Ausfall.
            self._lbl_enttec_status.setText(
                f"{port} → Universe {univ}: antwortet nicht — Port/Kabel prüfen")
            return
        if zustand == ZUSTAND_SENDET:
            self._lbl_enttec_status.setText(
                f"Verbunden: {port} → Universe {univ} (gespeichert)")
        elif zustand == ZUSTAND_TOT:
            self._lbl_enttec_status.setText(
                f"{port} → Universe {univ}: Port lässt sich nicht öffnen — "
                f"gespeichert, aber es geht kein DMX raus")
        else:
            # Der Adapter kann keine Auskunft geben (In-Prozess-Fallback ohne
            # Statusfeld). Dann bleibt die ehrliche Teilaussage stehen.
            self._lbl_enttec_status.setText(
                f"Eingerichtet: {port} → Universe {univ} (gespeichert)")

    def _sync_artnet_start_univ_default(self):
        """A3D-15: die Startuniversum-Spinbox auf einen sinnvollen Wert fuer das
        aktuell gewaehlte interne Universum stellen — eine bereits gespeicherte
        externe Art-Net-Universe, sonst den abwaertskompatiblen Default (univ-1).
        Verhindert, dass ein „Übernehmen" ohne bewusste Eingabe auf Universe 0
        (Spinbox-Minimum) setzt, und zeigt eine gespeicherte Wahl nach Reload/
        Universumswechsel wieder an."""
        univ = self._spin_artnet_univ.value()
        persisted = None
        try:
            for r in _load_universe_config():
                if int(r.get("num", -1)) == univ and (r.get("output") or "") == "ArtNet":
                    v = r.get("out_universe")
                    if v is not None and str(v).strip() != "":
                        persisted = int(v)
                    break
        except (ValueError, TypeError):
            persisted = None
        target = persisted if persisted is not None else max(0, univ - 1)
        self._spin_artnet_start_univ.blockSignals(True)
        self._spin_artnet_start_univ.setValue(target)
        self._spin_artnet_start_univ.blockSignals(False)

    def _apply_artnet(self):
        univ = self._spin_artnet_univ.value()
        state = get_state()
        if not self._check_artnet.isChecked():
            # MU-02 (+Review): Abwaehlen raeumt das beim Apply belegte Universum
            # (nicht den aktuellen Spin-Wert — der koennte inzwischen auf ein fremdes
            # Universum zeigen und dessen Adapter faelschlich killen).
            if self._artnet_active_univ is not None:
                state.output_manager.remove_output(self._artnet_active_univ)
                self._artnet_active_univ = None
            self._lbl_artnet_status.setText("Inaktiv")
            return
        ip = self._edit_artnet_ip.text().strip() or "255.255.255.255"
        # OUT-04: NUR das gewählte Universum belegen. Die frühere Schleife über ALLE
        # Universen überschrieb jede andere Adapter-Zuweisung — live UND in
        # universes.json (`_persist_output` je Universum) → Mixed-Setups zerstört.
        # `_persist_output` aktualisiert jetzt nur diese eine Zeile, andere bleiben.
        if univ not in state.universes:
            state.universes[univ] = state.output_manager.add_universe(univ)
        # MU-01: erst ALLE Alt-Adapter dieses Universums entfernen/schliessen, sonst
        # bleibt bei einem Cross-Typ-Wechsel (z. B. Enttec->ArtNet) der alte Adapter
        # aktiv -> Doppel-Output/Leak. Analog apply_output_config (OUT-05).
        state.output_manager.remove_output(univ)
        # A3D-15: externe Art-Net-Universe aus der (bisher toten) Startuniversum-
        # Spinbox durchreichen. Weicht sie NICHT vom Default (univ-1) ab -> None,
        # damit der Send-Pfad den abwaertskompatiblen Default (univ_num-1) nutzt und
        # universes.json sauber bleibt (Konvention "leer = Default", wie die Tabelle).
        start = self._spin_artnet_start_univ.value()
        out_u = start if start != univ - 1 else None
        state.output_manager.add_artnet(univ, ip, out_universe=out_u)
        self._artnet_active_univ = univ   # MU-02: fuer korrektes Abwaehlen merken
        gespeichert = _persist_output(univ, "ArtNet", ip, out_universe=out_u)
        # A3D-15 (Review-Fund #2): die Universe-Tabelle wurde nur beim Setup gefuellt
        # und kennt die eben persistierte externe Universe nicht -> ein spaeteres
        # „Speichern" im Universen-Tab wuerde sie aus der (stalen, leeren) Ext-Zelle
        # ueberschreiben. Tabelle neu laden, damit die Ext-Zelle den aktuellen Stand
        # zeigt und Tab und Datei konsistent bleiben.
        try:
            self._univ_load_table()
        except Exception:
            pass
        _ext_txt = f" → Art-Net-Universe {start}" if out_u is not None else ""
        # QA-50: „(gespeichert)" nur, wenn die Datei wirklich geschrieben wurde.
        self._lbl_artnet_status.setText(
            f"Aktiv → {ip} · Universe {univ}{_ext_txt} "
            f"{'(gespeichert)' if gespeichert else '(NICHT gespeichert!)'}")

    # ── Universe Manager ─────────────────────────────────────────────────────

    def _univ_load_table(self):
        rows = _load_universe_config()
        # OUT-50 (Review-Fund am eigenen Diff): dieselbe Haertung wie in
        # `_patch_text` — steht in der von Hand editierbaren Datei eine Zahl
        # oder eine Liste, wo ein Text erwartet wird, warf der
        # QTableWidgetItem-Konstruktor beim Dialog-Bau. Der Ausgabe-Dialog liess
        # sich dann gar nicht mehr oeffnen, also ausgerechnet das Werkzeug zum
        # Reparieren. Nicht-Zeilen fliegen raus, Werte werden zu Text gemacht.
        rows = [r for r in rows if isinstance(r, dict)]
        if not rows:
            # Provide an initial example row
            rows = [{"num": 1, "name": "Main", "output": "Disabled", "patch": ""}]
        self._univ_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            num_item = QTableWidgetItem(str(r.get("num", i + 1)))
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._univ_table.setItem(i, 0, num_item)
            self._univ_table.setItem(i, 1, QTableWidgetItem(str(r.get("name", "Universe"))))
            combo = QComboBox()
            for opt in ("Disabled", "Enttec", "sACN", "ArtNet"):
                combo.addItem(opt)
            combo.setCurrentText(str(r.get("output", "Disabled")))
            self._univ_table.setCellWidget(i, 2, combo)
            self._univ_table.setItem(i, 3, QTableWidgetItem(_patch_text(r)))
            # OUT-03: externe Universe-Nummer (leer = Default). None/fehlt -> "".
            ext = r.get("out_universe")
            ext_item = QTableWidgetItem("" if ext is None else str(ext))
            ext_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._univ_table.setItem(i, 4, ext_item)

    def _univ_add(self):
        row = self._univ_table.rowCount()
        if row >= 32:
            QMessageBox.information(self, "Limit", "Maximal 32 Universen.")
            return
        self._univ_table.insertRow(row)
        self._univ_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self._univ_table.setItem(row, 1, QTableWidgetItem(f"Universe {row + 1}"))
        combo = QComboBox()
        for opt in ("Disabled", "Enttec", "sACN", "ArtNet"):
            combo.addItem(opt)
        self._univ_table.setCellWidget(row, 2, combo)
        self._univ_table.setItem(row, 3, QTableWidgetItem(""))
        self._univ_table.setItem(row, 4, QTableWidgetItem(""))

    def _univ_delete(self):
        rows = sorted({i.row() for i in self._univ_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self._univ_table.removeRow(r)

    def _univ_save(self):
        rows = []
        adjusted: list[tuple[int, int]] = []   # A3D-33: (Zeilennr, geklemmte Nummer)
        for r in range(self._univ_table.rowCount()):
            num_item = self._univ_table.item(r, 0)
            name_item = self._univ_table.item(r, 1)
            patch_item = self._univ_table.item(r, 3)
            ext_item = self._univ_table.item(r, 4)
            combo = self._univ_table.cellWidget(r, 2)
            # A3D-33: die freie '#'-Spalte auf [1..32] klemmen, BEVOR sie persistiert
            # und via apply_output_config als Universe-Key/Adapter angewandt wird
            # (sonst Art-Net-Wurf bzw. stiller sACN-Wrap auf ein falsches Universum).
            num, was_adjusted = _coerce_universe_num(
                num_item.text() if num_item else "", r + 1)
            if was_adjusted:
                adjusted.append((r + 1, num))
                if num_item is not None:
                    num_item.setText(str(num))   # UI spiegelt den gespeicherten Wert
            entry = {
                "num": num,
                "name": name_item.text() if name_item else f"Universe {num}",
                "output": combo.currentText() if combo else "Disabled",
                "patch": patch_item.text() if patch_item else "",
            }
            # OUT-03: externe Universe-Nummer nur speichern, wenn gesetzt & gueltig
            # (leer/ungueltig -> Feld weglassen = abwaertskompatibler Default).
            ext_text = ext_item.text().strip() if ext_item else ""
            if ext_text:
                try:
                    entry["out_universe"] = int(ext_text)
                except ValueError:
                    pass
            rows.append(entry)
        if adjusted:
            _lst = ", ".join(f"Zeile {r}: → {n}" for r, n in adjusted)
            QMessageBox.warning(
                self, "Universe-Nummer angepasst",
                f"Universe-Nummern müssen zwischen {_UNIVERSE_MIN} und "
                f"{_UNIVERSE_MAX} liegen. Angepasst: {_lst}.")

        # OUT-07: zwei Universen auf DASSELBE Ziel sind ein Bedienfehler, den die
        # Software bisher still mitgemacht hat. Beide senden dann auf dieselbe
        # externe Nummer, der Empfänger bekommt abwechselnd zwei verschiedene
        # Inhalte und zeigt Flackern — ohne dass irgendwo etwas gemeldet wird.
        # Nur WARNEN, nicht korrigieren: welches der beiden Universen gemeint
        # war, weiß nur der Bediener. Eine automatische Umnummerierung würde
        # raten und dabei möglicherweise das falsche Rig dunkel schalten.
        for zeilen, was in _doppelte_ziele(rows):
            QMessageBox.warning(
                self, "Zwei Universen auf demselben Ziel",
                f"{was}\n\nBetroffen: {zeilen}.\n\nBeide senden dorthin — der "
                f"Empfänger bekommt abwechselnd zwei verschiedene Inhalte. "
                f"Gespeichert wird trotzdem; wenn das Absicht ist, ignorieren "
                f"Sie diesen Hinweis.")

        # ★ QA-50: Hier stand ein „Gespeichert"-Dialog, der NICHTS geprueft hat
        # — weder ob die Datei geschrieben wurde noch ob das Anwenden geklappt
        # hat. Beide Fehler waren nur im Terminal zu sehen, das im Betrieb
        # niemand offen hat. Ein Dialog, der Erfolg behauptet, ist schlimmer als
        # gar keine Rueckmeldung: er beendet die Suche nach dem Fehler.
        if not _save_universe_config(rows):
            QMessageBox.critical(
                self, "Nicht gespeichert",
                f"Die Universen-Konfiguration konnte nicht geschrieben werden:\n"
                f"{_UNIV_CONFIG_PATH}\n\nDie Aenderungen gelten nur bis zum "
                f"Beenden. Schreibrechte und freien Speicherplatz pruefen.")
            return
        # Sofort anwenden, damit Änderungen ohne Neustart greifen.
        angewandt, fehler = True, ""
        try:
            get_state().apply_output_config()
        except Exception as e:
            angewandt, fehler = False, str(e)
            print(f"[output_config] apply after save error: {e}")
        if angewandt:
            QMessageBox.information(self, "Gespeichert", _UNIV_CONFIG_PATH)
        else:
            QMessageBox.warning(
                self, "Gespeichert, aber nicht angewendet",
                f"Die Datei wurde geschrieben ({_UNIV_CONFIG_PATH}), das "
                f"Einrichten der Ausgaenge ist aber gescheitert:\n\n{fehler}\n\n"
                f"Nach einem Neustart wird es erneut versucht.")

    def _apply_sacn(self):
        univ = self._spin_sacn_univ.value()
        state = get_state()
        if not self._check_sacn.isChecked():
            # MU-02 (+Review): das beim Apply belegte Universum raeumen, nicht den
            # aktuellen Spin-Wert (koennte auf ein fremdes Universum zeigen).
            if self._sacn_active_univ is not None:
                state.output_manager.remove_output(self._sacn_active_univ)
                self._sacn_active_univ = None
            self._lbl_sacn_status.setText("Inaktiv")
            return
        ip_text = self._edit_sacn_ip.text().strip()
        target_ip = None if (self._check_sacn_multicast.isChecked() or not ip_text) else ip_text
        try:
            # OUT-04: NUR das gewählte Universum belegen (nicht mehr alle über eine
            # Schleife überschreiben); andere universes.json-Zeilen bleiben erhalten.
            if univ not in state.universes:
                state.universes[univ] = state.output_manager.add_universe(univ)
            # MU-01: erst ALLE Alt-Adapter dieses Universums entfernen/schliessen, sonst
            # bleibt bei einem Cross-Typ-Wechsel der alte Adapter aktiv -> Doppel-Output/
            # Leak. Analog apply_output_config (OUT-05).
            # ★★★ NET-12: `ausser="sacn"` — der laufende sACN-Sender bleibt
            # stehen, damit `add_sacn` ihn ueber `_swap_device` MIT Uebergabe
            # austauscht. Vorher wurde er hier per `pop` entfernt und
            # geschlossen; ohne Nachfolger in der Registry greift die
            # Uebergabe-Sperre nicht, und `close()` schickte eine
            # E1.31-Stream-Termination fuer ein WEITERLAUFENDES Universum.
            # Gemessen: 5 von 5 Uebernahmen mit unveraenderter Konfiguration.
            # Der MU-01-Grund fuer diesen Aufruf bleibt erhalten — die FREMDEN
            # Adaptertypen werden weiterhin entfernt.
            state.output_manager.remove_output(univ, ausser="sacn")
            state.output_manager.add_sacn(univ, target_ip)
            self._sacn_active_univ = univ   # MU-02: fuer korrektes Abwaehlen merken
            gespeichert = _persist_output(univ, "sACN", target_ip or "")
            mode = "Multicast (239.255.0.x)" if target_ip is None else f"Unicast → {target_ip}"
            # QA-50: Der Adapter laeuft — aber ob die Zeile auf der Platte steht,
            # ist eine zweite Frage. Vorher stand „(gespeichert)" auch dann da,
            # wenn das Schreiben scheiterte, und die Ausgabe war nach dem
            # naechsten Start wieder weg.
            self._lbl_sacn_status.setText(
                f"Aktiv · {mode} · Universe {univ} "
                f"{'(gespeichert)' if gespeichert else '(NICHT gespeichert!)'}")
        except Exception as e:
            self._lbl_sacn_status.setText(f"Fehler: {e}")

    # ── DMX Input ────────────────────────────────────────────────────────────

    @staticmethod
    def _clear_stale_input_merges(rx, new_in_u: int, new_out_u: int):
        """NET-08: Vor dem Einrichten einer neuen Input-Merge-Konfiguration die
        zuvor gesetzte(n) raeumen. Sonst mischt eine auf ein anderes eingehendes
        Universe umgestellte Quelle (z. B. U5 -> U7) ueber die alte Merge-Config +
        den weiterhin aktiven Empfangs-Handler in dasselbe out-Universe weiter.
        Nutzt die vorhandenen ``remove_merge``/``clear_input_merge``-Lifecycles
        (NET-05/NET-07)."""
        merges = getattr(rx, "_merges", None)
        if not merges:
            return
        new_in = int(new_in_u)
        new_out = int(new_out_u)
        stale = [in_u for in_u in list(merges.keys()) if int(in_u) != new_in]
        # Alte out-Universen merken, um eingefrorene Eingangs-Schichten zu leeren.
        stale_outs = {int(merges[in_u][0]) for in_u in stale}
        # NET-08b (Review): Bleibt das EINGANGS-Universum gleich, wechselt aber nur das
        # AUSGANGS-Universum, so bleibt der Merge-Eintrag (in==new_in) erhalten und
        # set_merge remappt ihn — die ALTE out-Schicht würde sonst nie geleert und hinge
        # bis zum NET-05-Timeout (~2,5s) als eingefrorener DMX. Sein altes out mitnehmen.
        for k in list(merges.keys()):
            if int(k) == new_in:
                stale_outs.add(int(merges[k][0]))
                break
        # Nichts zu räumen: keine anderen in_u UND kein abweichendes altes out
        # (Erst-Konfiguration oder unveränderte in/out).
        if not stale and stale_outs <= {new_out}:
            return
        for in_u in stale:
            rx.remove_merge(in_u)
        try:
            st = get_state()
            for out_u in stale_outs:
                if out_u != new_out:
                    st.clear_input_merge(out_u)
        except Exception:
            pass

    def _input_status_text(self, in_u, out_u, mode):
        """NET-07/CDX-02: Baut das Eingangs-Status-Label. Ist out_u NICHT als Output
        gepatcht, verwirft ``_render_frame`` die gemergten Kanaele -> statt "Aktiv"
        "wirkungslos" melden.

        CDX-02b (Review): Maszgeblich ist der AKTUELLE Patch-Stand ``state.universes``
        (genau was ``_render_frame`` zum Verwerfen prueft, app_state.py) — NICHT der
        ``input_unconfigured``-Zaehler. Der Zaehler wird erst vom RX-Thread NACH dem
        ersten empfangenen+gerenderten Frame hochgezaehlt: beim Klick auf "Uebernehmen"
        stuende er sonst noch auf 0 (Warnung verpasst, obwohl gerade der zu warnende
        Fall) bzw. bliebe nach nachtraeglichem Patchen stehen (falsche Warnung). Der
        direkte ``universes``-Check stimmt sofort beim Klick und verschwindet nach dem
        Patchen ohne Frame-Abhaengigkeit."""
        base = f"Aktiv: U{in_u} -> U{out_u} ({mode})"
        try:
            universes = getattr(get_state(), "universes", None)
            if universes is not None and int(out_u) not in universes:
                return (
                    f"Aktiv, aber wirkungslos (U{out_u} nicht als Output "
                    f"gepatcht): U{in_u} -> U{out_u} ({mode})"
                )
        except Exception:
            pass
        return base

    def _apply_artnet_input(self):
        try:
            from src.core.dmx.artnet_input import get_artnet_receiver
            rx = get_artnet_receiver()
            if not self._check_artnet_in.isChecked():
                rx.stop()
                self._lbl_artnet_in_status.setText("Gestoppt")
                return
            if not rx.is_running():
                rx.start()
            in_u = self._spin_artnet_in_univ.value()
            out_u = self._spin_artnet_in_out.value()
            mode = self._combo_artnet_in_mode.currentText()
            self._clear_stale_input_merges(rx, in_u, out_u)
            rx.set_merge(in_u, out_u, mode)
            self._lbl_artnet_in_status.setText(
                self._input_status_text(in_u, out_u, mode)
            )
        except Exception as e:
            self._lbl_artnet_in_status.setText(f"Fehler: {e}")

    def _apply_sacn_input(self):
        try:
            from src.core.dmx.sacn_input import get_sacn_receiver
            rx = get_sacn_receiver()
            if not self._check_sacn_in.isChecked():
                rx.stop()
                self._lbl_sacn_in_status.setText("Gestoppt")
                return
            in_u = self._spin_sacn_in_univ.value()
            out_u = self._spin_sacn_in_out.value()
            mode = self._combo_sacn_in_mode.currentText()
            if not rx.is_running():
                rx.start(universes=[in_u])
            else:
                rx.join_universe(in_u)
            self._clear_stale_input_merges(rx, in_u, out_u)
            rx.set_merge(in_u, out_u, mode)
            self._lbl_sacn_in_status.setText(
                self._input_status_text(in_u, out_u, mode)
            )
        except Exception as e:
            self._lbl_sacn_in_status.setText(f"Fehler: {e}")
