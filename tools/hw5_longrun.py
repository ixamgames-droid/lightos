#!/usr/bin/env python3
"""HW-5 — Enttec-Ausgang im Langzeitbetrieb (>8 h) messen.

Die Backlog-Frage lautet woertlich: *bricht der Ausgang irgendwann weg? Wenn ja,
nach wie vielen Stunden, und kommt er von selbst zurueck?* Genau das misst dieses
Werkzeug — und zwar ueber DENSELBEN Codepfad, den die App benutzt
(``EnttecPro.send_dmx`` -> ``serial.write``), nicht ueber einen Nachbau.

WARUM BLACKOUT DER DEFAULT IST
------------------------------
Der Lauf sendet standardmaessig 512 Nullen pro Frame. Das belastet den fraglichen
Pfad vollstaendig (gleiche Paketgroesse, gleiche Rate, gleiche Dauer), macht aber
kein Licht an. Was physisch an der Enttec-DMX-Leitung haengt, weiss dieses Skript
naemlich NICHT: im aktuellen Show-Patch liegt alles auf Universe 1 (Art-Net), das
Enttec-Universe ist leer. Stundenlang blind Kanaele zu bespielen kann bei Movern,
Spidern oder Lasern reale Folgen haben — deshalb ist jede sichtbare Ausgabe ein
bewusstes Opt-in (``--heartbeat-channel``) und niemals Default.

Fuer den Sichtbeweis am Rig gibt es ``--probe``: ein kurzer, gedrosselter Ramp auf
EINEM ausgewaehlten Kanal, den man jederzeit neben dem laufenden Test starten kann
(dann aber den Langzeitlauf kurz stoppen — es kann nur ein Prozess den Port halten).

WAS DAS WERKZEUG SIEHT — UND WAS NICHT
--------------------------------------
Sichtbar in Software: Schreibfehler, das OUT-02-Auto-Disable nach 20 Fehlern in
Folge, der gedrosselte Reconnect (inkl. SERIAL-02-Portwechsel per VID/PID), ein
zulaufender Sendepuffer (``out_waiting``) und Schleifen-Stocker (Frame-Abstand).

NICHT sichtbar: der *stille* Tod, bei dem der FTDI weiter Bytes annimmt, aber keine
gueltigen DMX-Frames mehr auf die Leitung legt. Dagegen hilft nur der Blick aufs
Rig — darum endet der Bericht ausdruecklich mit dieser Einschraenkung, statt
Gruen zu melden, was er nicht gemessen hat.

Aufruf::

    venv/bin/python tools/hw5_longrun.py --hours 12
    venv/bin/python tools/hw5_longrun.py --probe --heartbeat-channel 115-118
    venv/bin/python tools/hw5_longrun.py --status            # laufenden Lauf ansehen
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.dmx.enttec_pro import EnttecPro, find_enttec_port  # noqa: E402

DEFAULT_STATUS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "..", "logs", "hw5_status.json")


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class Run:
    """Haelt Zaehler + Zustandsuebergaenge EINES Langzeitlaufs."""

    def __init__(self, dev: EnttecPro, log_path: str, status_path: str):
        self.dev = dev
        self.log_path = log_path
        self.status_path = status_path
        self.t0 = time.monotonic()
        self.frames_ok = 0
        self.frames_while_dead = 0
        self.write_errors = 0
        self.max_out_waiting = 0
        self.max_frame_gap_s = 0.0
        self.events: list[str] = []
        self._was_disabled = False
        self._port = dev.port
        self._prev_fail = 0

    # ── Protokoll ────────────────────────────────────────────────────────────
    def log(self, line: str) -> None:
        text = f"[{_ts()}] {line}"
        print(text, flush=True)
        try:
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(text + "\n")
        except OSError:
            pass

    def event(self, line: str) -> None:
        """Zustandsuebergang — landet im Log UND in der Ereignisliste des Berichts."""
        self.events.append(f"{_ts()} {line}")
        self.log(f"*** {line}")

    # ── Messung ──────────────────────────────────────────────────────────────
    def observe(self) -> None:
        """Nach jedem Frame den Geraetezustand abklopfen.

        ``send_dmx`` schluckt seine Exceptions bewusst (ein Output-Thread, der an
        einem Frame stirbt, waere schlimmer als ein verworfenes Frame). Ein Fehler
        ist von aussen deshalb nur am *Hochzaehlen* des internen Fehlerzaehlers zu
        erkennen — daher der Zugriff auf ``_fail_count``. Bewusst gewaehlt: die
        Alternative waere, ``serial.write`` zu umgehen und damit einen anderen
        Pfad zu messen als den, um den es geht.
        """
        fail = getattr(self.dev, "_fail_count", 0)
        if fail > self._prev_fail:
            self.write_errors += fail - self._prev_fail
            if self._prev_fail == 0:
                self.event(f"SCHREIBFEHLER beginnt (Fehler #{self.write_errors} gesamt)")
        elif fail == 0 and self._prev_fail > 0 and not self.dev.is_disabled():
            self.event(f"Schreibfehler-Serie erholt sich nach {self._prev_fail} Fehlern "
                       f"— Ausgang laeuft weiter")
        self._prev_fail = fail

        dead = self.dev.is_disabled()
        if dead and not self._was_disabled:
            self.event(f"AUSGANG TOT — OUT-02-Auto-Disable nach {EnttecPro.FAIL_LIMIT} "
                       f"Fehlern in Folge, nach {self.hours():.2f} h Laufzeit")
        elif not dead and self._was_disabled:
            self.event(f"AUSGANG VON SELBST ZURUECK nach {self.hours():.2f} h "
                       f"(Reconnect ohne App-Neustart)")
        self._was_disabled = dead

        if self.dev.port != self._port:
            self.event(f"PORTWECHSEL {self._port} -> {self.dev.port} "
                       f"(SERIAL-02: nach Replug haengt der Enttec an neuer Nummer)")
            self._port = self.dev.port

        try:
            if self.dev.is_open():
                self.max_out_waiting = max(self.max_out_waiting,
                                           int(self.dev._ser.out_waiting))
        except Exception:
            pass

    def hours(self) -> float:
        return (time.monotonic() - self.t0) / 3600.0

    def snapshot(self) -> dict:
        return {
            "stand": _ts(),
            "laufzeit_h": round(self.hours(), 3),
            "port": self.dev.port,
            "frames_gesendet": self.frames_ok,
            "frames_waehrend_tot": self.frames_while_dead,
            "schreibfehler": self.write_errors,
            "aktuell_offen": bool(self.dev.is_open()),
            "aktuell_tot": bool(self.dev.is_disabled()),
            "max_sendepuffer_bytes": self.max_out_waiting,
            "max_frame_abstand_s": round(self.max_frame_gap_s, 3),
            "ereignisse": self.events,
        }

    def write_status(self) -> None:
        """Atomar, damit ein paralleles --status nie eine halbe Datei liest."""
        tmp = self.status_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.snapshot(), fh, indent=1, ensure_ascii=False)
            os.replace(tmp, self.status_path)
        except OSError:
            pass

    def report(self) -> str:
        s = self.snapshot()
        verdikt = ("Ausgang lief durchgehend — kein Wegbrechen gemessen."
                   if not self.events else
                   "Ausgang hatte Aussetzer — siehe Ereignisse.")
        lines = [
            "",
            "=" * 72,
            f"HW-5 Langzeitlauf — Bericht ({_ts()})",
            "=" * 72,
            f"  Laufzeit          : {s['laufzeit_h']:.2f} h",
            f"  Port              : {s['port']}",
            f"  Frames gesendet   : {s['frames_gesendet']:,}".replace(",", "."),
            f"  Schreibfehler     : {s['schreibfehler']}",
            f"  Frames trotz tot  : {s['frames_waehrend_tot']}",
            f"  Port offen (Ende) : {s['aktuell_offen']}",
            f"  Port tot   (Ende) : {s['aktuell_tot']}",
            f"  max. Sendepuffer  : {s['max_sendepuffer_bytes']} Byte",
            f"  max. Frame-Abstand: {s['max_frame_abstand_s']:.3f} s",
            "",
            f"  VERDIKT: {verdikt}",
        ]
        if s["ereignisse"]:
            lines.append("")
            lines.append("  Ereignisse:")
            lines += [f"    - {e}" for e in s["ereignisse"]]
        lines += [
            "",
            "  EINSCHRAENKUNG: gemessen ist der Schreibpfad (Port offen, writes gehen",
            "  durch, kein Auto-Disable). Ein STILLER Tod — FTDI nimmt Bytes an, legt",
            "  aber keine gueltigen DMX-Frames mehr auf die Leitung — ist von hier aus",
            "  nicht sichtbar. Dafuer braucht es den Blick aufs Rig:",
            "      venv/bin/python tools/hw5_longrun.py --probe --heartbeat-channel <N-M>",
            "=" * 72,
            "",
        ]
        return "\n".join(lines)


def _frame_blackout() -> bytes:
    return bytes(512)


def parse_channel_spec(spec) -> list[int]:
    """``"115"`` · ``"115-118"`` · ``"115,117"`` -> Liste von DMX-Kanaelen.

    ★ Warum ein BEREICH und nicht ein Kanal: am Rig haengt ein Geraet, dessen
    Profil man im Zweifel nicht kennt („so ein kleiner U-King, weiss aber nicht
    genau welcher"). Ein Ramp auf EINEM Kanal ist dann eine Wette: liegt auf
    Kanal 1 der Master-Dimmer und stehen die Farben auf 0, bleibt das Geraet
    **dunkel** — und ein dunkles Geraet beweist nichts, weder ueber den Ausgang
    noch ueber das Kabel. Rampen dagegen Dimmer UND Farben gemeinsam, ist das
    Ergebnis bei jedem gaengigen Layout sichtbar (Dimmer+RGB genauso wie reines
    RGBW). Kanaele ausserhalb des Bereichs bleiben auf 0 — das Geraet wird
    also weiterhin nur dort bespielt, wo es der Aufrufer ausdruecklich sagt.

    Ungueltige/leere Angaben ergeben ``[]`` = Blackout (der sichere Default).
    """
    out: list[int] = []
    for teil in str(spec or "").replace(" ", "").split(","):
        if not teil:
            continue
        try:
            if "-" in teil[1:]:
                a, b = teil.split("-", 1)
                lo, hi = int(a), int(b)
                if lo > hi:
                    lo, hi = hi, lo
                out.extend(range(lo, hi + 1))
            else:
                out.append(int(teil))
        except ValueError:
            continue
    return [c for c in dict.fromkeys(out) if 1 <= c <= 512]


def _frame_heartbeat(channels, level: int, phase: float) -> bytes:
    """Sanfter Dreieck-Ramp auf den angegebenen Kanaelen — Bewegung, nicht
    Standbild.

    Ein statischer Wert taugt als Lebenszeichen nicht: DMX haelt den letzten Wert,
    ein toter Ausgang sieht dann exakt aus wie ein lebender. Nur eine sichtbare
    Aenderung unterscheidet beides.

    Alle genannten Kanaele rampen GEMEINSAM (gleiche Phase): bei einem
    Dimmer+RGB-Geraet oeffnet der Dimmer waehrend die Farbe hochkommt, bei einem
    reinen RGBW-Geraet wird es gemeinsam heller. Beides ist sichtbar, ohne das
    Profil zu kennen.
    """
    data = bytearray(512)
    tri = 2.0 * phase if phase < 0.5 else 2.0 * (1.0 - phase)
    val = max(0, min(255, int(round(tri * level))))
    if isinstance(channels, int):
        channels = [channels]
    for ch in channels or ():
        if 1 <= int(ch) <= 512:
            data[int(ch) - 1] = val
    return bytes(data)


def cmd_status(status_path: str) -> int:
    try:
        with open(status_path, encoding="utf-8") as fh:
            s = json.load(fh)
    except OSError:
        print(f"Kein laufender HW-5-Lauf gefunden ({status_path} fehlt).")
        return 1
    print(json.dumps(s, indent=1, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", help="Serieller Port (Default: per VID/PID suchen)")
    ap.add_argument("--hz", type=float, default=40.0, help="Frame-Rate (Default 40)")
    ap.add_argument("--hours", type=float, default=12.0, help="Laufdauer (Default 12)")
    ap.add_argument("--log", help="Log-Datei (Default: logs/hw5_longrun_<start>.log)")
    ap.add_argument("--status-file", default=None, help="Status-JSON fuer --status")
    ap.add_argument("--status", action="store_true",
                    help="nur den Stand eines laufenden Tests ausgeben")
    ap.add_argument("--heartbeat-channel", default="",
                    help="OPT-IN: sichtbarer Ramp auf diesen Kanaelen — EIN Kanal "
                         "(\"115\"), ein BEREICH (\"115-118\") oder eine Liste "
                         "(\"115,117\"). Leer/0 = aus (Blackout). Bereich nehmen, "
                         "wenn das Profil unbekannt ist: liegt auf dem ersten Kanal "
                         "der Master-Dimmer, bleibt ein Ein-Kanal-Ramp bei Farben "
                         "auf 0 unsichtbar.")
    ap.add_argument("--heartbeat-level", type=int, default=64,
                    help="Spitzenwert des Ramps (Default 64 = gedaempft)")
    ap.add_argument("--probe", action="store_true",
                    help="nur ein kurzer 20-s-Sichttest, dann Ende")
    args = ap.parse_args(argv)

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logdir = os.path.abspath(os.path.join(root, "..", "logs"))
    os.makedirs(logdir, exist_ok=True)
    status_path = args.status_file or os.path.join(logdir, "hw5_status.json")

    if args.status:
        return cmd_status(status_path)

    port = args.port or find_enttec_port()
    if not port:
        print("Kein Enttec per VID/PID gefunden und kein --port angegeben.")
        return 2

    log_path = args.log or os.path.join(
        logdir, f"hw5_longrun_{time.strftime('%Y%m%d_%H%M%S')}.log")

    hb_channels = parse_channel_spec(args.heartbeat_channel)
    if args.probe and not hb_channels:
        print("--probe braucht --heartbeat-channel <N|N-M> — sonst waere der "
              "Sichttest unsichtbar. Kanaele bewusst waehlen: das Skript kennt "
              "den Patch der Enttec-Leitung nicht.")
        return 2

    try:
        dev = EnttecPro(port)
    except Exception as e:
        print(f"Port {port} liess sich nicht oeffnen: {e}")
        return 2

    run = Run(dev, log_path, status_path)
    duration_h = (20.0 / 3600.0) if args.probe else args.hours
    _hb_txt = (f"Kanal {hb_channels[0]}" if len(hb_channels) == 1
               else f"Kanaele {hb_channels[0]}-{hb_channels[-1]}"
               if hb_channels else "")
    mode = (f"Sichttest 20 s, Ramp auf {_hb_txt} "
            f"(Spitze {args.heartbeat_level})" if args.probe else
            (f"Heartbeat-Ramp auf {_hb_txt} "
             f"(Spitze {args.heartbeat_level})" if hb_channels
             else "Blackout (512 Nullen) — kein Licht, voller Schreibpfad"))
    run.log(f"HW-5 Langzeitlauf startet — Port {port}, {args.hz:g} Hz, "
            f"{duration_h:.2f} h geplant, Modus: {mode}")
    run.log(f"Log: {log_path}   Status: {status_path}")

    stop = {"flag": False}

    def _on_signal(_sig, _frm):
        stop["flag"] = True

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    period = 1.0 / max(1.0, args.hz)
    deadline = run.t0 + duration_h * 3600.0
    next_frame = time.monotonic()
    last_frame_at = time.monotonic()
    next_log = run.t0 + 60.0
    hb_period = 8.0     # ein sichtbarer Auf-/Ab-Zyklus alle 8 s

    try:
        while not stop["flag"] and time.monotonic() < deadline:
            now = time.monotonic()
            if now < next_frame:
                time.sleep(min(period, next_frame - now))
                continue
            gap = now - last_frame_at
            if run.frames_ok:                      # das erste Frame hat keinen Abstand
                run.max_frame_gap_s = max(run.max_frame_gap_s, gap)
            last_frame_at = now
            next_frame = now + period

            if hb_channels:
                phase = ((now - run.t0) % hb_period) / hb_period
                frame = _frame_heartbeat(hb_channels,
                                         args.heartbeat_level, phase)
            else:
                frame = _frame_blackout()

            was_dead = dev.is_disabled()
            dev.send_dmx(frame)
            if was_dead:
                run.frames_while_dead += 1
            else:
                run.frames_ok += 1
            run.observe()

            if now >= next_log:
                next_log = now + 60.0
                s = run.snapshot()
                run.log(f"{s['laufzeit_h']:.2f} h — {s['frames_gesendet']} Frames, "
                        f"{s['schreibfehler']} Fehler, offen={s['aktuell_offen']}, "
                        f"tot={s['aktuell_tot']}, Puffer<={s['max_sendepuffer_bytes']} B, "
                        f"Frame-Abstand<={s['max_frame_abstand_s']:.3f} s")
                run.write_status()
    finally:
        if stop["flag"]:
            run.log("Abbruchsignal erhalten — fahre sauber herunter.")
        # Immer schwarz hinterlassen: ein Heartbeat-Lauf soll nicht mit stehendem
        # Wert enden (DMX haelt sonst den letzten Pegel).
        try:
            for _ in range(8):
                dev.send_dmx(_frame_blackout())
                time.sleep(0.02)
        except Exception:
            pass
        run.write_status()
        report = run.report()
        run.log(report)
        dev.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
