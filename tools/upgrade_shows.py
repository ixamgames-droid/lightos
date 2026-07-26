"""Alt-Shows auf das aktuelle Show-Format (``show_file.SHOW_VERSION``) heben.

Eine ``.lshow`` aus einer aelteren LightOS-Version laedt weiter (der Loader ist
rueckwaertskompatibel und ergaenzt fehlende Felder mit Defaults) — die DATEI
bleibt dabei aber auf ihrem alten Stand, bis sie einmal aus der App heraus
gespeichert wird. Dieses Skript macht genau diesen einen Schritt bewusst und
nachpruefbar: ``load_show`` -> ``save_show`` auf denselben Pfad.

Aufruf::

    venv/Scripts/python.exe tools/upgrade_shows.py            # alle shows/*.lshow
    venv/Scripts/python.exe tools/upgrade_shows.py --check    # nur pruefen (CI/Gate)
    venv/Scripts/python.exe tools/upgrade_shows.py shows/a.lshow shows/b.lshow

Sicherheitsnetze (das Skript schreibt in Nutzerdaten — jedes ist Absicht):

  * **Backup zuerst.** Vor dem Ueberschreiben entsteht
    ``<name>.lshow.bak-v<altversion>`` (gitignored, s. .gitignore ``shows/*.lshow.bak*``).
  * **Kein Verlust von Top-Level-Bloecken.** Nach dem Speichern wird geprueft, dass
    KEIN Schluessel aus der Alt-Datei verschwunden ist. ``layout`` schreibt
    ``save_show`` nur, wenn es uebergeben wird -> wird aus der Alt-Datei
    durchgereicht (sonst faellt der Fenster-/Dock-Layout-Block still weg).
  * **Kein Verlust von Inhalten.** Fixtures, Funktionen, VC-Widgets, Cue-Stacks und
    Paletten werden vor/nach gezaehlt und muessen exakt uebereinstimmen.
  * **Fixpunkt.** Nach dem Upgrade muss ein weiterer load->save-Zyklus die Datei
    strukturgleich lassen (dieselbe Invariante wie
    ``tests/test_show_roundtrip_fixpoint.py``).
  * **Fremdformate werden nicht angefasst.** Eine ``show.json`` ohne jeden
    LightOS-Block ist keine Alt-Show, sondern ein Fremdformat — die wuerde ein
    load->save zu einer leeren Show plattmachen. Solche Dateien werden gemeldet
    und uebersprungen (der Loader lehnt sie seit 2026-07-26 ohnehin ab).

Schlaegt eine Pruefung an, stellt das Skript die Datei aus dem Backup wieder her
und beendet mit Exit-Code 1 — eine halb migrierte Show bleibt nie stehen.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import _gen_env  # noqa: F401,E402  # DEMO-02: spawn-sichere Env-Schalter vor src.core

try:
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
except Exception:                                   # pragma: no cover
    _app = None

from src.core.show import show_file                                  # noqa: E402
from src.core.show.show_file import SHOW_VERSION, load_show, save_show  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── Lesen/Zaehlen ───────────────────────────────────────────────────────────────

def read_show_json(path: str) -> dict:
    with zipfile.ZipFile(path, "r") as zf:
        return json.loads(zf.read("show.json").decode("utf-8"))


def zip_entries(path: str) -> set[str]:
    """Alle ZIP-Einträge — `show.json` plus eingebettete VC-Assets (VC-IMG:
    Button-Hintergrundbilder/GIFs unter ``assets/vc/``). Muss ein Upgrade
    überleben, sonst wären die Bilder weg."""
    with zipfile.ZipFile(path, "r") as zf:
        return set(zf.namelist())


def count_widgets(vc) -> int:
    """VC-Widgets zaehlen — flach (``widgets``), nach Seiten (``pages``) UND die
    Kinder verschachtelter VCFrames (die stehen in einer eigenen ``widgets``-Liste
    IM Frame-Widget). Wuerde hier nur die oberste Liste gezaehlt, bliebe der
    Verlust von Frame-Kindern unbemerkt.

    Gezaehlt wird NUR, was unter einem ``widgets``-Schluessel steht (in beliebiger
    Tiefe) — nicht jede beliebige Liste. Sonst zaehlten Farb-/Binding-Listen mit,
    und ein Upgrade, das additive Default-Listen ergaenzt, wuerde die Invariante
    faelschlich als Inhaltsverlust melden."""
    if isinstance(vc, dict):
        total = 0
        for key, value in vc.items():
            if key == "widgets" and isinstance(value, list):
                total += len(value) + sum(count_widgets(w) for w in value)
            else:
                total += count_widgets(value)
        return total
    if isinstance(vc, list):
        return sum(count_widgets(v) for v in vc)
    return 0


def content_counts(data: dict) -> dict:
    """Die Inhalte, die ein Upgrade unter KEINEN Umstaenden veraendern darf."""
    functions = data.get("functions")
    fn_list = functions.get("functions") if isinstance(functions, dict) else functions
    palettes = data.get("palettes")
    pal_list = palettes.get("palettes") if isinstance(palettes, dict) else palettes
    return {
        "fixtures": len(data.get("patch") or []),
        "funktionen": len(fn_list or []),
        "vc-widgets": count_widgets(data.get("virtual_console")),
        "cue-stacks": len(data.get("cue_stacks") or []),
        "paletten": len(pal_list or []),
    }


def is_lightos_show(data: dict) -> bool:
    """Spiegelt das Fremdformat-Gate in ``show_file.load_show``."""
    return "version" in data or bool(show_file._KNOWN_SHOW_BLOCKS & set(data))


def normalized(value):
    """JSON strukturgleich vergleichbar machen (Key-Typen koennen wandern)."""
    if isinstance(value, dict):
        return {str(k): normalized(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalized(v) for v in value]
    return value


# ── Upgrade eines Files ─────────────────────────────────────────────────────────

def upgrade(path: str) -> tuple[str, str]:
    """Eine Show migrieren. Liefert ``(status, detail)`` mit status in
    ``aktuell`` | ``migriert`` | ``fremd`` | ``fehler``."""
    before = read_show_json(path)
    before_entries = zip_entries(path)
    old_version = before.get("version")

    if not is_lightos_show(before):
        return "fremd", (
            f"kein LightOS-Format (Schluessel: {', '.join(sorted(before)[:6])}…) — "
            "nicht angefasst")
    if old_version == SHOW_VERSION:
        return "aktuell", f"schon v{SHOW_VERSION}"

    backup = f"{path}.bak-v{old_version or 'unbekannt'}"
    shutil.copy2(path, backup)

    def _restore(reason: str) -> tuple[str, str]:
        shutil.copy2(backup, path)
        return "fehler", f"{reason} — Datei aus {os.path.basename(backup)} zurueckgeholt"

    ok, msg = load_show(path)
    if not ok:
        return _restore(f"load_show fehlgeschlagen: {msg}")

    # save_show schreibt "layout" NUR, wenn es uebergeben wird -> durchreichen.
    save_show(path, layout=before.get("layout"))
    after = read_show_json(path)

    if after.get("version") != SHOW_VERSION:
        return _restore(f"Version nach dem Speichern {after.get('version')!r}")
    lost_entries = sorted(before_entries - zip_entries(path))
    if lost_entries:
        return _restore(f"ZIP-Eintraege verloren (VC-Assets?): {lost_entries}")
    lost = sorted(set(before) - set(after))
    if lost:
        return _restore(f"Top-Level-Bloecke verloren: {lost}")
    before_counts, after_counts = content_counts(before), content_counts(after)
    if before_counts != after_counts:
        diff = {k: (before_counts[k], after_counts[k])
                for k in before_counts if before_counts[k] != after_counts[k]}
        return _restore(f"Inhalte veraendert (vorher, nachher): {diff}")

    # Fixpunkt: ein weiterer Zyklus darf die Datei nicht mehr veraendern.
    ok, msg = load_show(path)
    if not ok:
        return _restore(f"Neu geschriebene Datei laedt nicht: {msg}")
    probe = os.path.join(tempfile.mkdtemp(prefix="lightos_upgrade_"), "probe.lshow")
    save_show(probe, layout=after.get("layout"))
    if normalized(read_show_json(probe)) != normalized(after):
        return _restore("kein Fixpunkt — ein weiterer load/save wuerde die Datei "
                        "erneut aendern (Save/Load-Asymmetrie im Code!)")

    return "migriert", (f"v{old_version or '—'} -> v{SHOW_VERSION}, "
                        f"{after_counts['fixtures']} Fixtures / "
                        f"{after_counts['funktionen']} Funktionen / "
                        f"{after_counts['vc-widgets']} VC-Widgets erhalten")


def check(path: str) -> tuple[str, str]:
    """Nur pruefen (schreibt nichts)."""
    data = read_show_json(path)
    if not is_lightos_show(data):
        return "fremd", f"kein LightOS-Format (Schluessel: {', '.join(sorted(data)[:6])}…)"
    version = data.get("version")
    if version == SHOW_VERSION:
        return "aktuell", f"v{SHOW_VERSION}"
    return "veraltet", f"v{version or '—'} (aktuell ist v{SHOW_VERSION})"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("paths", nargs="*",
                    help="Show-Dateien (Default: alle shows/*.lshow im Repo)")
    ap.add_argument("--check", action="store_true",
                    help="nur pruefen, nichts schreiben (Exit 1, wenn etwas veraltet ist)")
    args = ap.parse_args(argv)

    paths = args.paths or sorted(glob.glob(os.path.join(_ROOT, "shows", "*.lshow")))
    if not paths:
        print("Keine Shows gefunden.")
        return 0

    mark = {"aktuell": "[ ok ]", "migriert": "[ up ]", "veraltet": "[alt ]",
            "fremd": "[fremd]", "fehler": "[FAIL]"}
    tally: dict[str, int] = {}
    for path in paths:
        try:
            status, detail = check(path) if args.check else upgrade(path)
        except Exception as exc:                            # defekte/fremde Datei
            status, detail = "fehler", f"{type(exc).__name__}: {exc}"
        tally[status] = tally.get(status, 0) + 1
        print(f"{mark.get(status, '[ ?? ]')} {os.path.basename(path)}: {detail}")

    print("== " + " · ".join(f"{n}x {s}" for s, n in sorted(tally.items())) +
          f" ueber {len(paths)} Show(s) ==")
    if tally.get("fehler"):
        return 1
    if args.check and (tally.get("veraltet") or tally.get("fremd")):
        print("Hinweis: `tools/upgrade_shows.py` ohne --check hebt die veralteten "
              "Dateien an; Fremdformate muessen neu gebaut werden.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
