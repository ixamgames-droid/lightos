#!/usr/bin/env python3
"""TOOL-26: Die ECHTE App in einer Sandbox messen — 3D-fps, Push-Takt, Blackout, Buehnen-Elemente.

Startet LightOS so, wie der Nutzer es startet (``main.main()``: Hauptfenster,
dann der 3D-Visualizer ueber denselben Weg wie der Menuepunkt), und misst im
sichtbaren Fenster. Gedacht fuer Fragen wie „ist das 3D auf diesem Rechner
fluessig?", „stimmt der Push-Takt je Qualitaetsstufe?", „wie schnell wird ein
Blackout im 3D sichtbar?".

    python tools/app_messung.py                      # Mega Arena, alle Stufen
    python tools/app_messung.py --stufen auto,high --dauer 10
    python tools/app_messung.py --show shows/Demo_Show_Full.lshow --messungen buehne,leerlauf
    python tools/app_messung.py --json messung.json --fotos bilder/
    python tools/app_messung.py --repo ../wt-anderer-zweig     # anderen Checkout messen
        (Windows: venv/Scripts/python.exe, Linux/macOS: ./venv/bin/python)

## Zwei feste Regeln

1. **Sandbox-Pflicht.** Datenordner, Show-DB, Bibliothek, Ausgabe-Konfiguration
   und Absturzprotokoll liegen in einem Wegwerf-Ordner. Bevor irgendein
   App-Modul geladen wird, prueft das Werkzeug, dass ``app_data_dir()`` wirklich
   dort landet — sonst bricht es ab (Exit 2). Die echten App-Daten werden nie
   gelesen und nie geschrieben; ``--bibliothek`` kopiert eine ausdruecklich
   genannte Bibliothek HINEIN.
2. **Kein DMX nach aussen.** Die Sandbox hat keine Ausgabe-Konfiguration. Meldet
   die App nach dem Start trotzdem einen Ausgang, bricht das Werkzeug ab, bevor
   es einen einzigen Wert setzt (Exit 2).

## Was gemessen wird

* ``buehne``    Buehnen-Elemente der Szene (Anzahl, sichtbar in Ansehen/Bauen).
* ``leerlauf``  Bildrate der Seite ohne Wertaenderung.
* ``dimmer``    alle dimmbaren Geraete im Sinus (2 Hz; ohne Dimmer-Kanal ueber
                die Farbkanaele): Push-Takt gegen Soll, Bildrate, danach
                fuenfmal Blackout bis das 3D dunkel ist.
* ``gobo``      Moving Heads mit Gobo: Rotation + Schwenk; je Bild der
                ANGEZEIGTE Winkel -> Anteil der Bilder ohne Bewegung.

``dimmer`` und ``gobo`` laufen je einmal mit sichtbarem und mit minimiertem
Hauptfenster (``--hauptfenster``): die 2D-Ansicht im Hauptfenster teilt sich den
UI-Thread mit dem 3D.

## Fallen (gemessen am Windows-ARM-PC, 10.10.2026)

* **Stromquelle.** Auf Akku fiel das 3D mit sichtbarem Hauptfenster auf 7-11
  fps, am Netz 43-51. Die Stromquelle steht deshalb im Bericht; auf Akku warnt
  das Werkzeug.
* **Das Fenster ist echt** und erscheint auf dem Bildschirm; einen
  Offscreen-Modus gibt es bewusst nicht. Die volle App verliert dort den
  GPU-Kontext ("Context lost during MakeCurrent", gemessen unter Windows mit
  ANGLE/D3D11), die Szene baut sich dann nicht auf.
* Beendet wird ueber das Schliessen des Hauptfensters (der Weg des Nutzers).
  Ein harter Ausstieg bei offenem Fenster endete mit PySide6 6.12 in einer
  Access Violation.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Auswahlwert der Qualitaets-Liste -> (Anzeigename, Soll-Push je Sekunde)
STUFEN = {
    "auto": ("Automatisch", None),
    "low": ("Niedrig", 15),
    "high": ("Hoch", 30),
    "max": ("Maximal", 44),
}
MESSUNGEN = ("buehne", "leerlauf", "dimmer", "gobo")
FENSTER = ("sichtbar", "minimiert")
EXIT_REGEL = 2          # Sandbox- oder Ausgabe-Regel verletzt
EXIT_FEHLER = 1


class Regelverstoss(RuntimeError):
    """Sandbox-Pflicht oder „kein DMX nach aussen" waere verletzt."""


# ── reine Bausteine (ohne Qt, im Test geprueft) ─────────────────────────────

def sandbox_umgebung(wurzel: str) -> dict[str, str]:
    """Umgebungsvariablen, die JEDEN Schreibort der App in ``wurzel`` legen.

    Windows liest ``APPDATA``, Linux ``XDG_DATA_HOME``, macOS den Heimatordner —
    deshalb alle drei. ``LIGHTOS_UNIVERSES_JSON`` zeigt auf eine Datei, die es
    nicht gibt: ohne Ausgabe-Konfiguration richtet die App keinen Ausgang ein.
    """
    w = os.path.abspath(wurzel)
    env = {
        "APPDATA": os.path.join(w, "appdata"),
        "LOCALAPPDATA": os.path.join(w, "localappdata"),
        "XDG_DATA_HOME": os.path.join(w, "xdg_data"),
        "XDG_CONFIG_HOME": os.path.join(w, "xdg_config"),
        "XDG_CACHE_HOME": os.path.join(w, "xdg_cache"),
        "LIGHTOS_SHOW_DB": os.path.join(w, "show.db"),
        "LIGHTOS_FIXTURE_DB": os.path.join(w, "fixtures.db"),
        "LIGHTOS_UNIVERSES_JSON": os.path.join(w, "universes.json"),
        "LIGHTOS_CRASH_LOG": os.path.join(w, "crash.log"),
        "LIGHTOS_SACN_CID": os.path.join(w, "sacn_cid"),
        "LIGHTOS_NO_AUDIO_AUTOSTART": "1",
        "LIGHTOS_SERIAL_INPROC": "1",
        "LIGHTOS_NO_RECOVERY_PROMPT": "1",
        "LIGHTOS_NO_DATENUMZUG": "1",
    }
    if sys.platform == "darwin":
        env["HOME"] = os.path.join(w, "home")
    return env


#: Schalter aus Testlauf oder Generator, mit denen die App NICHT mehr laeuft wie
#: beim Nutzer. Ohne Ausgabe-Thread kommt kein Wert im 3D an (gemessen: Push 0,
#: als das Werkzeug aus pytest heraus gestartet wurde); offscreen gibt es kein Bild.
STOERENDE_SCHALTER = ("LIGHTOS_NO_OUTPUT_THREAD",)


def bereinige_umgebung(environ) -> list[str]:
    """Entfernt geerbte Schalter, die die Messung verfaelschen; liefert ihre Namen."""
    entfernt = [n for n in STOERENDE_SCHALTER if n in environ]
    if str(environ.get("QT_QPA_PLATFORM", "")).lower() == "offscreen":
        entfernt.append("QT_QPA_PLATFORM")
    for n in entfernt:
        environ.pop(n, None)
    return entfernt


def liegt_in(pfad: str, wurzel: str) -> bool:
    """True, wenn ``pfad`` in ``wurzel`` liegt (nach Aufloesung, ohne Gross-/Klein-
    Unterschied unter Windows)."""
    try:
        p = os.path.normcase(os.path.realpath(pfad))
        w = os.path.normcase(os.path.realpath(wurzel))
        return os.path.commonpath([p, w]) == w
    except ValueError:          # verschiedene Laufwerke
        return False


def pruefe_sandbox(wurzel: str, datenordner: str, weitere: dict[str, str] | None = None) -> None:
    """Sandbox-Pflicht: der Datenordner der App und alle umgelenkten Dateien
    muessen in ``wurzel`` liegen — sonst :class:`Regelverstoss`."""
    draussen = []
    if not liegt_in(datenordner, wurzel):
        draussen.append(f"Datenordner {datenordner}")
    for name, pfad in (weitere or {}).items():
        if not pfad or not liegt_in(pfad, wurzel):
            draussen.append(f"{name} {pfad or '(nicht gesetzt)'}")
    if draussen:
        raise Regelverstoss(
            "Sandbox-Pflicht verletzt, nichts gestartet. Ausserhalb der Sandbox: "
            + "; ".join(draussen))


def pruefe_keine_ausgabe(ausgaenge) -> None:
    """„Kein DMX nach aussen": ``ausgaenge`` ist die Liste aus
    ``output_manager.ausgabe_status()`` — jeder Eintrag ist einer zu viel."""
    liste = list(ausgaenge or [])
    if liste:
        namen = ", ".join(f"U{a.get('universum')} {a.get('weg')}" for a in liste)
        raise Regelverstoss(
            f"In der Sandbox ist ein DMX-Ausgang eingerichtet ({namen}) — "
            "abgebrochen, bevor ein Wert gesetzt wurde.")


def bild_statistik(zeiten_ms) -> dict:
    """Kennzahlen aus den Zeitstempeln aufeinanderfolgender Bilder (ms)."""
    t = list(zeiten_ms or [])
    if len(t) < 3:
        return {"bilder": len(t), "fehler": "zu wenige Bilder"}
    dts = [b - a for a, b in zip(t, t[1:])]
    sortiert = sorted(dts)
    return {
        "bilder": len(t),
        "fps": round((len(t) - 1) / ((t[-1] - t[0]) / 1000.0), 1),
        "dt_median_ms": round(statistics.median(dts), 1),
        "dt_p95_ms": round(sortiert[min(len(sortiert) - 1, int(len(sortiert) * 0.95))], 1),
        "dt_max_ms": round(max(dts), 1),
        "bilder_ueber_25ms": sum(1 for x in dts if x > 25.0),
        "bilder_ueber_50ms": sum(1 for x in dts if x > 50.0),
    }


def _kreis(x: float) -> float:
    return (x + math.pi) % (2 * math.pi) - math.pi


def bewegung_statistik(winkel_rad) -> dict:
    """Wie gleichmaessig sich ein angezeigter Winkel von Bild zu Bild bewegt.

    ``stand_anteil`` ist der Anteil der Bilder OHNE Bewegung: nahe 0 heisst
    fluessig, ein hoher Wert heisst, der Winkel springt nur je DMX-Update."""
    w = list(winkel_rad or [])
    if len(w) < 3:
        return {"fehler": "zu wenige Werte"}
    schritte = [abs(_kreis(b - a)) for a, b in zip(w, w[1:])]
    bewegt = sorted(x for x in schritte if x > 1e-5)
    if not bewegt:
        return {"stand_anteil": 1.0, "bewegt": 0}
    med = statistics.median(bewegt)
    return {
        "stand_anteil": round(1 - len(bewegt) / len(schritte), 3),
        "schritt_median_grad": round(math.degrees(med), 2),
        "schritt_p95_grad": round(math.degrees(bewegt[min(len(bewegt) - 1, int(len(bewegt) * 0.95))]), 2),
        "schritt_max_grad": round(math.degrees(bewegt[-1]), 2),
        "spruenge_ueber_3x_median": sum(1 for x in bewegt if x > 3 * med),
    }


def stromquelle() -> str:
    """'Netz', 'Akku' oder 'unbekannt' — nur lesend, ohne Zusatzpakete."""
    try:
        if sys.platform == "win32":
            import ctypes

            class _Status(ctypes.Structure):
                _fields_ = [("ac", ctypes.c_ubyte), ("flag", ctypes.c_ubyte),
                            ("prozent", ctypes.c_ubyte), ("sparen", ctypes.c_ubyte),
                            ("rest", ctypes.c_ulong), ("voll", ctypes.c_ulong)]
            s = _Status()
            if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s)):  # type: ignore[attr-defined]
                return {0: "Akku", 1: "Netz"}.get(s.ac, "unbekannt")
            return "unbekannt"
        basis = "/sys/class/power_supply"
        if os.path.isdir(basis):
            netz = None
            for name in os.listdir(basis):
                typ = os.path.join(basis, name, "type")
                online = os.path.join(basis, name, "online")
                if os.path.isfile(typ) and os.path.isfile(online):
                    with open(typ, encoding="utf-8") as fh:
                        if fh.read().strip() != "Mains":
                            continue
                    with open(online, encoding="utf-8") as fh:
                        netz = fh.read().strip() == "1" or bool(netz)
            if netz is not None:
                return "Netz" if netz else "Akku"
    except Exception:
        pass
    return "unbekannt"


def _zahl(x, stellen=1) -> str:
    if x is None:
        return "-"
    return f"{x:.{stellen}f}".replace(".", ",") if isinstance(x, float) else str(x)


def tabelle(ergebnis: dict) -> str:
    """Kurzbericht als Tabelle (fuer die Tafel bzw. den PR)."""
    zeilen = ["| Stufe | Messung | Hauptfenster | fps | Bilder > 50 ms | Push/s (Soll) "
              "| Blackout Median | Bilder ohne Bewegung |",
              "|---|---|---|---|---|---|---|---|"]
    for stufe, daten in (ergebnis.get("stufen") or {}).items():
        name = daten.get("anzeige") or stufe
        soll = daten.get("soll_push")
        for m in daten.get("messungen", []):
            bild = m.get("bild") or {}
            push = m.get("push_hz")
            push_text = "-" if push is None else (
                f"{_zahl(float(push))} ({soll})" if soll else _zahl(float(push)))
            gobo = (m.get("gobo") or {}).get("stand_anteil")
            zeilen.append("| {} | {} | {} | {} | {} | {} | {} | {} |".format(
                name, m.get("messung"), m.get("hauptfenster", "-"),
                _zahl(bild.get("fps")), bild.get("bilder_ueber_50ms", "-"), push_text,
                "-" if m.get("blackout_median_ms") is None else f"{m['blackout_median_ms']} ms",
                "-" if gobo is None else f"{round(gobo * 100)} %"))
    return "\n".join(zeilen)


def baue_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="app_messung.py",
        description="Echte LightOS-App in einer Sandbox messen (3D-fps, Push-Takt, "
                    "Blackout, Buehnen-Elemente). Nie echte App-Daten, kein DMX nach aussen.")
    p.add_argument("--show", metavar="DATEI",
                   help=".lshow, die geladen wird (Kopie). Ohne Angabe wird die Mega Arena "
                        "frisch in die Sandbox gebaut.")
    p.add_argument("--stufen", default="auto,low,high,max",
                   help="Qualitaetsstufen, Komma-getrennt: " + ", ".join(STUFEN))
    p.add_argument("--messungen", default=",".join(MESSUNGEN),
                   help="Komma-getrennt: " + ", ".join(MESSUNGEN))
    p.add_argument("--hauptfenster", default=",".join(FENSTER),
                   help="Lagen des Hauptfensters fuer dimmer/gobo: " + ", ".join(FENSTER))
    p.add_argument("--dauer", type=float, default=10.0, metavar="S",
                   help="Messdauer je Abschnitt in Sekunden (Vorgabe 10)")
    p.add_argument("--json", metavar="DATEI", help="Ergebnis zusaetzlich als JSON schreiben")
    p.add_argument("--fotos", metavar="ORDNER",
                   help="Bildschirmfotos des 3D-Fensters dorthin (Buehne, Gobo je Stufe)")
    p.add_argument("--bibliothek", metavar="DATEI",
                   help="Diese fixtures.db in die Sandbox KOPIEREN (sonst nur eingebaute Profile)")
    p.add_argument("--repo", metavar="ORDNER", default=REPO,
                   help="Checkout, dessen App gemessen wird (Vorgabe: dieser)")
    p.add_argument("--zeitlimit", type=float, default=900.0, metavar="S",
                   help="Harter Abbruch nach so vielen Sekunden (Vorgabe 900)")
    return p


def _liste(wert: str, erlaubt, was: str) -> list[str]:
    teile = [t.strip() for t in (wert or "").split(",") if t.strip()]
    fremd = [t for t in teile if t not in erlaubt]
    if fremd or not teile:
        raise SystemExit(f"app_messung.py: {was} unbekannt: {', '.join(fremd) or '(leer)'} "
                         f"— erlaubt: {', '.join(erlaubt)}")
    return teile


# ── Messung in der laufenden App ────────────────────────────────────────────

_JS_ANZAHL = "Object.keys((window.__lightos||{}).fixtures||{}).length"
_JS_HELL = ("Object.values(window.__lightos.fixtures).reduce((a,f)=>"
            "a+((f.spot&&f.spot.intensity)||0)"
            "+((f.beam&&f.beam.visible&&f.beam.material)?f.beam.material.opacity:0),0)")
_JS_INFO = """(function(){ const L = window.__lightos; const o = {};
  const v = (k, fn) => { try { o[k] = fn(); } catch (e) { o[k] = 'ERR ' + e; } };
  v('gpuTier', () => typeof L.gpuTier === 'function' ? L.gpuTier() : L.gpuTier);
  v('probe', () => L.gpuProbeInfo());
  v('pixelRatio', () => L.pixelRatio());
  v('schattenBudget', () => L.shadowBudgetInfo());
  v('dynAufloesung', () => L.dynamicResolutionInfo());
  v('buehne', () => Object.keys(L.stageObjects).length);
  v('umgebung', () => L.umgebungInfo());
  v('render', () => L.renderInfo());
  return JSON.stringify(o); })()"""
_JS_BUEHNE = r"""(function(){ try { const L = window.__lightos; const out = [];
  for (const [id, so] of Object.entries(L.stageObjects)) { const m = so.mesh; let meshes = 0, vis = 0;
    if (m) m.traverse(o => { if (o.isMesh) { meshes++; if (o.visible) vis++; } });
    out.push({id, typ: (so.data && (so.data.type || so.data.kind)), name: (so.data && so.data.name),
              sichtbar: !!(m && m.visible), meshes, meshSichtbar: vis}); }
  return JSON.stringify(out); } catch (e) { return JSON.stringify({err: String(e)}); } })()"""
_JS_LICHT = """(function(){ try { const L = window.__lightos; const out = [];
  const info = L.spotPoolInfo ? L.spotPoolInfo() : {halter: []};
  const lights = L.spotPoolLights ? L.spotPoolLights() : [];
  for (const fid of %s) { const f = L.fixtures[String(fid)]; if (!f) { out.push({fid, fehlt: true}); continue; }
    const i = (info.halter || []).indexOf(fid); const l = i >= 0 ? lights[i] : null;
    const fm = f.floorSpot && f.floorSpot.material;
    out.push({fid, spot: f.spot ? +f.spot.intensity.toFixed(3) : null,
              pool: l ? +l.intensity.toFixed(3) : null, muster: !!(fm && fm.map),
              texBreite: fm && fm.map && fm.map.image ? fm.map.image.width : null}); }
  return JSON.stringify(out); } catch (e) { return JSON.stringify({err: String(e)}); } })()"""
_JS_ZAEHLER_AN = """(function(){ const L = window.__lightos; const f = L.fixtures['%s'];
  const S = window.__appMessung = {t: [], g: [], p: [], stop: false};
  function tick(now){ if (S.stop) return; S.t.push(now);
    if (f) { S.g.push(f.beam ? f.beam.rotation.y : 0); S.p.push(f.yoke ? f.yoke.rotation.y : 0); }
    requestAnimationFrame(tick); }
  requestAnimationFrame(tick); return 1; })()"""
_JS_ZAEHLER_AUS = ("(function(){ const S = window.__appMessung; if (!S) return '{}'; S.stop = true;"
                   " return JSON.stringify({t: S.t, g: S.g, p: S.p}); })()")


class Messung:
    """Treibt die laufende App. Erwartet, dass QApplication und Hauptfenster stehen."""

    def __init__(self, hauptfenster, args, ergebnis: dict, melde):
        from PySide6.QtWidgets import QApplication
        from src.core.app_state import get_state
        self.app = QApplication.instance()
        self.mw = hauptfenster
        self.args = args
        self.erg = ergebnis
        self.melde = melde
        self.st = get_state()
        self.viz = None
        self.treiber = None

    # Ereignisschleife selbst drehen (es laeuft kein app.exec()).
    def pump(self, sek: float) -> None:
        ende = time.perf_counter() + sek
        while time.perf_counter() < ende:
            self.app.processEvents()
            time.sleep(0.002)

    def js(self, ausdruck: str, limit: float = 5.0):
        kiste = []
        self.viz._view.page().runJavaScript(ausdruck, lambda r: kiste.append(r))
        ende = time.perf_counter() + limit
        while not kiste and time.perf_counter() < ende:
            self.app.processEvents()
            time.sleep(0.001)
        return kiste[0] if kiste else None

    def jsj(self, ausdruck: str, limit: float = 5.0):
        roh = self.js(ausdruck, limit)
        try:
            return json.loads(roh) if roh else None
        except Exception:
            return {"roh": str(roh)[:200]}

    def warte(self, ausdruck: str, limit: float = 60.0) -> bool:
        ende = time.perf_counter() + limit
        while time.perf_counter() < ende:
            if self.js(ausdruck):
                return True
            self.pump(0.2)
        return False

    def foto(self, name: str):
        if not self.args.fotos:
            return None
        try:
            os.makedirs(self.args.fotos, exist_ok=True)
            self.viz.raise_()
            self.viz.activateWindow()
            self.pump(0.6)
            g = self.viz.frameGeometry()
            bild = self.viz.screen().grabWindow(0, g.x(), g.y(), g.width(), g.height())
            pfad = os.path.join(self.args.fotos, name)
            bild.save(pfad)
            return pfad
        except Exception as e:                       # noqa: BLE001
            self.melde(f"Foto {name} fehlgeschlagen: {e}")
            return None

    # ── Vorbereitung ──────────────────────────────────────────────────────
    def vorbereiten(self) -> None:
        from PySide6.QtCore import Qt, QTimer
        from src.core.app_state import get_channels_for_patched, open_value_for
        st = self.st
        ende = time.perf_counter() + 60
        while time.perf_counter() < ende and not st.get_patched_fixtures():
            self.pump(0.3)
        self.pump(3.0)
        pruefe_keine_ausgabe(st.output_manager.ausgabe_status())
        geraete = list(st.get_patched_fixtures())
        if not geraete:
            raise RuntimeError("Die Show hat keine gepatchten Geraete (oder wurde nicht geladen).")
        self.fids = [f.fid for f in geraete]
        self.voll, self.dimkanal, self.gobo = {}, {}, []
        alle_attribute = set()
        for f in geraete:
            try:
                kanaele = list(get_channels_for_patched(f))
            except Exception:                        # noqa: BLE001
                kanaele = []
            attrs = [getattr(c, "attribute", "") for c in kanaele]
            alle_attribute.update(a for a in attrs if a)
            d = {}
            for a in ("dimmer", "intensity"):
                if a in attrs:
                    d[a] = 255
                    self.dimkanal.setdefault(f.fid, [a])
            farben = [a for a in ("color_r", "color_g", "color_b", "white") if a in attrs]
            for a in farben:
                d[a] = 255
            if f.fid not in self.dimkanal and farben:
                self.dimkanal[f.fid] = farben        # RGB-Geraet ohne Dimmer-Kanal
            offen = open_value_for(f, "shutter", -1)
            if "shutter" in attrs and offen >= 0:
                d["shutter"] = offen
            self.voll[f.fid] = d
            if "gobo_wheel" in attrs and getattr(f, "fixture_type", "") == "moving_head":
                bereiche = sorted(getattr(kanaele[attrs.index("gobo_wheel")], "ranges", []) or [],
                                  key=lambda r: r.range_from)
                if len(bereiche) >= 2:
                    b = bereiche[min(3, len(bereiche) - 1)]
                    self.gobo.append({"fid": f.fid, "wert": (b.range_from + b.range_to) // 2})
        self.erg["show"] = {"geraete": len(geraete), "dimmbar": len(self.dimkanal),
                            "gobo_moving_heads": len(self.gobo),
                            "attribute": sorted(alle_attribute),
                            "titel": self.mw.windowTitle()}
        self.melde(f"Show geladen: {len(geraete)} Geraete, {len(self.dimkanal)} dimmbar, "
                   f"{len(self.gobo)} Gobo-Moving-Heads")

        t0 = time.perf_counter()
        self.mw._open_visualizer()                   # derselbe Weg wie der Menuepunkt
        self.viz = self.mw._visualizer_window
        if self.viz is None:
            raise RuntimeError("Der 3D-Visualizer liess sich nicht oeffnen (QtWebEngine?).")
        self.viz.resize(1600, 900)
        self.viz.move(60, 40)
        if not self.warte(f"{_JS_ANZAHL} >= {len(self.fids)}", 120):
            raise RuntimeError("Die 3D-Szene hat die Geraete nicht aufgebaut (Zeitlimit).")
        self.erg["szene_steht_nach_s"] = round(time.perf_counter() - t0, 1)
        schirm = self.viz.screen()
        self.erg["bildschirm"] = {"hz": schirm.refreshRate(), "skalierung": schirm.devicePixelRatio(),
                                  "groesse": [schirm.size().width(), schirm.size().height()]}
        self.melde(f"Szene steht nach {self.erg['szene_steht_nach_s']} s, "
                   f"Bildschirm {self.erg['bildschirm']}")
        self.pump(2.0)

        self.modus = None
        start = time.perf_counter()

        def tick():
            if self.modus is None:
                return
            t = time.perf_counter() - start
            with st._prog_lock:
                if self.modus == "dimmer":
                    for fid, kanaele in self.dimkanal.items():
                        d = dict(self.voll[fid])
                        wert = int(127 + 127 * math.sin(2 * math.pi * 2 * t + fid))
                        for kanal in kanaele:
                            d[kanal] = wert
                        st.programmer[fid] = d
                elif self.modus == "gobo":
                    for g in self.gobo:
                        d = st.programmer.setdefault(g["fid"], {})
                        d["gobo_rotation"] = int((t * 42.5) % 256)                  # 6 s je Umlauf
                        d["pan"] = int(128 + 40 * math.sin(2 * math.pi * t / 5.0))   # 5 s je Schwenk
        self.treiber = QTimer()
        self.treiber.setTimerType(Qt.TimerType.PreciseTimer)
        self.treiber.setInterval(10)
        self.treiber.timeout.connect(tick)
        self.treiber.start()

    def programmer_leeren(self) -> None:
        self.modus = None
        with self.st._prog_lock:
            self.st.programmer.clear()

    # ── einzelne Messungen ────────────────────────────────────────────────
    def abschnitt(self, fid) -> dict:
        """Ein Messfenster: Bilder der Seite und Pushes des Kanals zaehlen."""
        kanal = self.viz._dmx_push
        self.js(_JS_ZAEHLER_AN % fid)
        s0, t0 = dict(kanal.stats), time.perf_counter()
        self.pump(self.args.dauer)
        s1, dt = dict(kanal.stats), time.perf_counter() - t0
        roh = self.jsj(_JS_ZAEHLER_AUS, 10.0) or {}
        return {
            "push_hz": round((s1["batches"] - s0["batches"]) / dt, 1),
            "push_kib_s": round((s1["bytes"] - s0["bytes"]) / dt / 1024, 1),
            "timeouts": s1.get("timeouts", 0) - s0.get("timeouts", 0),
            "resets": s1.get("resets", 0) - s0.get("resets", 0),
            "nicht_bereit": s1.get("nicht_bereit", 0) - s0.get("nicht_bereit", 0),
            "bild": bild_statistik(roh.get("t")),
            "_g": roh.get("g"), "_p": roh.get("p"),
        }

    def blackout(self) -> dict:
        st = self.st
        with st._prog_lock:
            for fid in self.fids:
                st.programmer[fid] = dict(self.voll[fid])
        zeiten, vorher0 = [], None
        for _ in range(5):
            st.output_manager.set_blackout(False)
            self.pump(1.2)
            vorher = self.js(_JS_HELL) or 0
            vorher0 = vorher if vorher0 is None else vorher0
            if vorher <= 0.001:
                continue
            b0 = time.perf_counter()
            st.output_manager.set_blackout(True)
            while time.perf_counter() - b0 < 3.0:
                v = self.js(_JS_HELL, limit=1.0)
                if v is not None and v <= 0.001:
                    zeiten.append(round((time.perf_counter() - b0) * 1000))
                    break
                self.app.processEvents()
        st.output_manager.set_blackout(False)
        return {"blackout_ms": zeiten, "blackout_gemessen": f"{len(zeiten)}/5",
                "blackout_median_ms": round(statistics.median(zeiten)) if zeiten else None,
                "blackout_max_ms": max(zeiten) if zeiten else None,
                "helligkeit_vorher": round(vorher0 or 0, 1)}

    def fenster_lage(self, lage: str) -> None:
        if lage == "minimiert":
            self.mw.showMinimized()
        else:
            self.mw.showNormal()
        self.pump(1.5)
        self.viz.raise_()

    def stufe(self, stufe: str, erste: bool) -> None:
        viz = self.viz
        anzeige, soll = STUFEN[stufe]
        e = self.erg["stufen"][stufe] = {"soll_push": soll, "messungen": []}
        idx = viz._combo_quality.findData(stufe)
        if idx < 0:
            e["fehler"] = "Stufe in dieser Version nicht waehlbar"
            return
        t0 = time.perf_counter()
        if viz._combo_quality.currentIndex() != idx:
            viz._combo_quality.setCurrentIndex(idx)
            self.pump(3.0)
            self.warte(f"{_JS_ANZAHL} >= {len(self.fids)}", 90)
            e["wechsel_s"] = round(time.perf_counter() - t0, 1)
            self.pump(3.0)
        self.programmer_leeren()
        self.pump(1.0)
        e["anzeige"] = f"{anzeige} ({viz._lbl_gpu_tier.text()})" if stufe == "auto" else anzeige
        e["info"] = self.jsj(_JS_INFO)
        if soll is None:
            try:
                e["soll_push"] = soll = round(1.0 / viz._dmx_push.min_interval_s)
            except Exception:                        # noqa: BLE001
                pass
        self.melde(f"\n=== Stufe {stufe}: {viz._lbl_gpu_tier.text()}"
                   f" | Probe: {(e['info'] or {}).get('probe')}")
        was = self.args.messungen
        fid0 = self.gobo[0]["fid"] if self.gobo else self.fids[0]

        if "buehne" in was and erste:
            buehne = {}
            for modus in ("view", "edit"):
                self.js(f"window.__lightos.setEditMode('{modus}')")
                self.pump(1.5)
                objekte = self.jsj(_JS_BUEHNE)
                info = self.jsj(_JS_INFO) or {}
                buehne[modus] = {"anzahl": info.get("buehne"), "umgebung": info.get("umgebung"),
                                 "objekte": objekte, "foto": self.foto(f"buehne_{stufe}_{modus}.png")}
            self.js("window.__lightos.setEditMode('view')")
            self.pump(1.0)
            self.erg["buehne"] = buehne
            self.melde(f"   Buehne: {buehne['view']['anzahl']} Elemente, Ansehen fasst zusammen: "
                       f"{buehne['view']['umgebung']}")

        if "leerlauf" in was:
            m = self.abschnitt(fid0)
            m.pop("_g"), m.pop("_p")
            m.update({"messung": "leerlauf", "hauptfenster": "sichtbar"})
            e["messungen"].append(m)
            self.melde(f"   Leerlauf: {m['bild']}")

        if "dimmer" in was and self.dimkanal:
            for lage in self.args.hauptfenster:
                self.fenster_lage(lage)
                self.modus = "dimmer"
                self.pump(1.5)
                m = self.abschnitt(fid0)
                m.pop("_g"), m.pop("_p")
                self.modus = None
                m.update(self.blackout())
                m.update({"messung": "dimmer", "hauptfenster": lage})
                e["messungen"].append(m)
                self.programmer_leeren()
                self.melde(f"   Dimmer-Sinus, Hauptfenster {lage}: Push {m['push_hz']}/s (Soll {soll}), "
                           f"{m['bild'].get('fps')} fps, Blackout {m['blackout_median_ms']} ms")
            self.fenster_lage("sichtbar")

        if "gobo" in was and self.gobo:
            fids = json.dumps([g["fid"] for g in self.gobo])
            with self.st._prog_lock:
                for g in self.gobo:
                    d = dict(self.voll[g["fid"]])
                    d.update({"pan": 128, "tilt": 128, "gobo_wheel": 0, "gobo_rotation": 0})
                    self.st.programmer[g["fid"]] = d
            self.pump(1.5)
            e["licht_offen"] = self.jsj(_JS_LICHT % fids)
            with self.st._prog_lock:
                for g in self.gobo:
                    self.st.programmer[g["fid"]]["gobo_wheel"] = g["wert"]
            self.pump(1.5)
            e["licht_gobo"] = self.jsj(_JS_LICHT % fids)
            e["foto_gobo"] = self.foto(f"gobo_{stufe}.png")
            for lage in self.args.hauptfenster:
                self.fenster_lage(lage)
                self.modus = "gobo"
                self.pump(1.5)
                m = self.abschnitt(fid0)
                self.modus = None
                m["gobo"] = bewegung_statistik(m.pop("_g"))
                m["pan"] = bewegung_statistik(m.pop("_p"))
                m.update({"messung": "gobo", "hauptfenster": lage})
                e["messungen"].append(m)
                self.melde(f"   Gobo + Schwenk, Hauptfenster {lage}: {m['bild'].get('fps')} fps, "
                           f"Push {m['push_hz']}/s, Bilder ohne Gobo-Bewegung "
                           f"{m['gobo'].get('stand_anteil')}")
            self.fenster_lage("sichtbar")
            self.programmer_leeren()

    def lauf(self) -> None:
        self.vorbereiten()
        erste = True
        for stufe in self.args.stufen:
            self.stufe(stufe, erste)
            erste = False
        self.programmer_leeren()
        if self.treiber is not None:
            self.treiber.stop()


# ── Start ───────────────────────────────────────────────────────────────────

def _baue_mega_arena(repo: str, ziel: str, env: dict[str, str], melde) -> None:
    melde("Baue die Mega Arena frisch in die Sandbox (ca. 1 min) ...")
    umgebung = dict(os.environ)
    umgebung.update(env)
    umgebung.update({"LIGHTOS_GEN_OUT": ziel, "QT_QPA_PLATFORM": "offscreen",
                     "PYTHONUTF8": "1"})
    r = subprocess.run([sys.executable, os.path.join(repo, "tools", "build_mega_arena_2026.py")],
                       cwd=repo, env=umgebung, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=600)
    if r.returncode != 0 or not os.path.isfile(ziel):
        raise RuntimeError("Mega Arena liess sich nicht bauen:\n"
                           + "\n".join((r.stdout + r.stderr).splitlines()[-15:]))


def _meta(repo: str) -> dict:
    import platform
    import sysconfig
    meta = {"zeit": time.strftime("%Y-%m-%dT%H:%M:%S"), "stromquelle": stromquelle(),
            "betriebssystem": platform.platform(), "python": platform.python_version(),
            "interpreter": sysconfig.get_platform()}
    try:
        r = subprocess.run(["git", "-C", repo, "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=20)
        meta["commit"] = r.stdout.strip() or "?"
    except Exception:                                # noqa: BLE001
        meta["commit"] = "?"
    return meta


def main(argv=None) -> int:
    args = baue_parser().parse_args(argv)
    args.stufen = _liste(args.stufen, STUFEN, "Stufe")
    args.messungen = _liste(args.messungen, MESSUNGEN, "Messung")
    args.hauptfenster = _liste(args.hauptfenster, FENSTER, "Hauptfenster-Lage")
    repo = os.path.abspath(args.repo)
    if not os.path.isfile(os.path.join(repo, "main.py")):
        raise SystemExit(f"app_messung.py: kein LightOS-Checkout: {repo}")
    for name in ("show", "bibliothek"):
        pfad = getattr(args, name)
        if pfad and not os.path.isfile(pfad):
            raise SystemExit(f"app_messung.py: --{name}: Datei nicht gefunden: {pfad}")
    show_quelle = os.path.abspath(args.show) if args.show else None
    for name in ("json", "fotos", "bibliothek"):
        if getattr(args, name):
            setattr(args, name, os.path.abspath(getattr(args, name)))

    def melde(text: str) -> None:
        print(text, flush=True)

    ergebnis = {"meta": _meta(repo), "stufen": {}}
    if ergebnis["meta"]["stromquelle"] == "Akku":
        melde("WARNUNG: Der Rechner laeuft auf AKKU — Bildraten und Zeiten sind dann nicht "
              "mit Netz-Messungen vergleichbar.")

    wurzel = tempfile.mkdtemp(prefix="lightos_app_messung_")
    env = sandbox_umgebung(wurzel)
    os.environ.update(env)
    entfernt = bereinige_umgebung(os.environ)   # gemessen wird wie beim Nutzer, im echten Fenster
    if entfernt:
        ergebnis["meta"]["entfernte_schalter"] = entfernt
        melde("Hinweis: geerbte Schalter entfernt: " + ", ".join(entfernt))

    def schreibe() -> None:
        if args.json:
            os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
            with open(args.json, "w", encoding="utf-8") as fh:
                json.dump(ergebnis, fh, indent=1, ensure_ascii=False, default=str)

    def abschluss(code: int) -> int:
        schreibe()
        if ergebnis["stufen"]:
            melde("\n" + tabelle(ergebnis))
        melde(f"\nStromquelle: {ergebnis['meta']['stromquelle']} | Commit {ergebnis['meta']['commit']}"
              + (f" | JSON: {args.json}" if args.json else ""))
        return code

    # Sandbox-Pflicht — VOR jedem App-Modul ausser der Pfad-Aufloesung.
    sys.path.insert(0, repo)
    try:
        from src.core.paths import app_data_dir
        pruefe_sandbox(wurzel, app_data_dir(), {
            k: os.environ.get(k, "") for k in
            ("LIGHTOS_SHOW_DB", "LIGHTOS_FIXTURE_DB", "LIGHTOS_UNIVERSES_JSON",
             "LIGHTOS_CRASH_LOG", "LIGHTOS_SACN_CID")})
    except Regelverstoss as e:
        melde(f"ABBRUCH: {e}")
        return EXIT_REGEL

    try:
        for pfad in (env["APPDATA"], env["LOCALAPPDATA"], env["XDG_DATA_HOME"],
                     env["XDG_CONFIG_HOME"], env["XDG_CACHE_HOME"], env.get("HOME", "")):
            if pfad:
                os.makedirs(pfad, exist_ok=True)
        if args.bibliothek:
            shutil.copy2(args.bibliothek, env["LIGHTOS_FIXTURE_DB"])
        show = os.path.join(wurzel, os.path.basename(show_quelle) if show_quelle
                            else "Mega_Arena_2026.lshow")
        if show_quelle:
            shutil.copy2(show_quelle, show)
        else:
            _baue_mega_arena(repo, show, env, melde)
    except Exception as e:                           # noqa: BLE001
        melde(f"FEHLER: {e}")
        return EXIT_FEHLER
    os.chdir(wurzel)

    def waechter() -> None:
        time.sleep(args.zeitlimit)
        ergebnis["fehler"] = f"Zeitlimit {args.zeitlimit:.0f} s erreicht"
        abschluss(EXIT_FEHLER)
        os._exit(EXIT_FEHLER)
    threading.Thread(target=waechter, daemon=True).start()

    from PySide6.QtWidgets import QApplication
    import main as lightos_main

    zustand = {"code": 0}

    def statt_exec(*_a, **_k) -> int:
        app = QApplication.instance()
        mw = next((w for w in app.topLevelWidgets() if type(w).__name__ == "MainWindow"), None)
        messung = None
        try:
            if mw is None:
                raise RuntimeError("Kein Hauptfenster gefunden.")
            messung = Messung(mw, args, ergebnis, melde)
            messung.lauf()
        except Regelverstoss as e:
            ergebnis["fehler"] = str(e)
            melde(f"ABBRUCH: {e}")
            zustand["code"] = EXIT_REGEL
        except BaseException as e:                   # noqa: BLE001
            import traceback
            traceback.print_exc()
            ergebnis["fehler"] = repr(e)
            zustand["code"] = EXIT_FEHLER
        abschluss(zustand["code"])
        try:                                         # der Weg des Nutzers: Hauptfenster schliessen
            if messung is not None:
                messung.programmer_leeren()
            if mw is not None:
                mw.close()
                ende = time.perf_counter() + 3.0
                while time.perf_counter() < ende:
                    app.processEvents()
                    time.sleep(0.005)
        except Exception:                            # noqa: BLE001
            pass
        return zustand["code"]

    QApplication.exec = staticmethod(statt_exec)
    sys.argv = [os.path.join(repo, "main.py"), "--show", show]
    lightos_main.main()                              # endet in _finalize_and_exit(code)
    return zustand["code"]


if __name__ == "__main__":
    sys.exit(main())
