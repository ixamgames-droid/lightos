"""QA-17 Doc-Link-Checker: findet TOTE relative Markdown-Querverweise.

Durchsucht docs/**.md + README.md + BACKLOG.md + ROADMAP.md + CHANGELOG.md nach
Markdown-Links ``[text](ziel)`` (KEINE Bilder ``![...]`` — die deckt
check_doc_images.py ab) und prueft, ob das (relativ zur .md-Datei aufgeloeste) Ziel
existiert. Uebersprungen: externe (http/https/mailto), reine Anker (#…), data:, und
Ziele in Code-Bloecken/-Spans (Beispiel-Syntax). Bei ``datei.md#anker`` wird nur die
Datei geprueft (Anker ignoriert).

Exit 0 = keine toten Links, Exit 1 = tote Links (CI-tauglich).
  python tools/check_doc_links.py            # Report
  python tools/check_doc_links.py --list-ok  # + OK-Zaehler je Datei
"""
import os
import re
import sys
import urllib.parse

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# [text](ziel) aber NICHT ![alt](ziel): negatives Lookbehind auf '!'.
MD_LINK = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
CODE_FENCE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
INLINE_CODE = re.compile(r"`[^`\n]*`")

# BACKLOG_ARCHIVE.md gehoert dazu: --archive schiebt laufend Doku-Links aus der
# gegateten BACKLOG.md dorthin — ohne Eintrag hier waeren genau die Verweise
# ungeprueft, die das Gate schuetzen soll (Review-Fund 2026-07-28).
FRAGMENT_ORDNER = "changelog.d"   # PROC-09
TOP_LEVEL = ("README.md", "BACKLOG.md", "BACKLOG_ARCHIVE.md", "ROADMAP.md",
             "CHANGELOG.md")


def _iter_md_files():
    for base, dirs, files in os.walk(os.path.join(REPO, "docs")):
        # Archiv-Ordner (``_archiv``/``_archive``) sind bewusst nicht gepflegt und
        # von Graph/Lint/Changelog ausgenommen -> nicht auf tote Links pruefen.
        dirs[:] = [d for d in dirs if not d.startswith("_arch")]
        for fn in files:
            if fn.lower().endswith(".md"):
                yield os.path.join(base, fn)
    # ★ QA-55: ALLE Markdown-Dateien im Repo-Wurzelverzeichnis, nicht mehr eine
    # Liste von fuenf. Ungeprueft blieben sonst ausgerechnet die Dateien, die
    # ein Neuzugang zuerst liest: WORKFLOW.md, INSTALL.md, ARCHITECTURE.md,
    # CONTRIBUTING.md, AGENTS.md, COORDINATION.md. Eine Aufzaehlung vergisst
    # jede kuenftige Datei automatisch — ein Verzeichnis-Scan nicht.
    for fn in sorted(os.listdir(REPO)):
        if fn.lower().endswith(".md"):
            yield os.path.join(REPO, fn)
    # PROC-09: CHANGELOG-Fragmente. Sie landen spaeter woertlich in
    # CHANGELOG.md — ein toter Link soll schon im PR auffallen, nicht erst
    # nach dem Sammel-Lauf auf main.
    frag = os.path.join(REPO, FRAGMENT_ORDNER)
    if os.path.isdir(frag):
        for fn in sorted(os.listdir(frag)):
            if fn.lower().endswith(".md"):
                yield os.path.join(frag, fn)


def _basis_ordner(md: str) -> str:
    """Ordner, gegen den relative Links aufgeloest werden.

    PROC-09: Ein Fragment ``changelog.d/<datum>-<ID>.md`` wird spaeter Teil
    von ``CHANGELOG.md`` im Repo-Wurzelverzeichnis; seine Links muessen also
    von DORT aus stimmen (``docs/x.md``, nicht ``../docs/x.md``). Nach dem
    eigenen Ordner geprueft waere jeder korrekte Fragment-Link tot — und jeder
    „reparierte" nach dem Sammeln."""
    ordner = os.path.dirname(md)
    if (os.path.basename(ordner) == FRAGMENT_ORDNER
            and os.path.dirname(ordner) == REPO
            and os.path.basename(md) != "README.md"):
        return REPO
    return ordner


def _slug(text: str) -> str:
    """Ueberschrift -> Anker, nach GitHubs Regel.

    ⚠️ Die Feinheit, an der eine erste Fassung dieses Gates scheiterte:
    GitHub ersetzt **jedes einzelne** Leerzeichen durch ``-``; es fasst sie
    NICHT zusammen. „Sync — der Teil" wird deshalb zu ``sync--der-teil`` mit
    ZWEI Bindestrichen (der Gedankenstrich faellt weg, seine beiden
    Leerzeichen bleiben). Mit ``\\s+`` zusammengefasst meldete das Gate
    **neun** tote Anker, von denen fuenf gar keine waren — und der naechste
    Schritt waere gewesen, korrekte Links „zu reparieren".
    """
    t = text.strip().lower()
    t = re.sub(r"[^\w\s-]", "", t, flags=re.UNICODE)   # Emoji/Satzzeichen weg
    return t.strip().replace(" ", "-")


def _anker(pfad: str) -> set:
    """Alle Sprungziele einer Datei: Ueberschriften + explizite HTML-Anker."""
    try:
        text = open(pfad, "r", encoding="utf-8", errors="replace").read()
    except Exception:
        return set()
    text = CODE_FENCE.sub("", text)
    anker = {_slug(m.group(1))
             for m in re.finditer(r"^#{1,6}\s+(.+?)\s*$", text, re.M)}
    anker |= {m.group(1).lower()
              for m in re.finditer(r'<a\s+(?:name|id)="([^"]+)"', text)}
    return anker


def scan():
    total = 0
    dead = []
    per_file_ok = {}
    for md in _iter_md_files():
        try:
            text = open(md, "r", encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        text = HTML_COMMENT.sub("", text)
        text = CODE_FENCE.sub("", text)
        text = INLINE_CODE.sub("", text)
        md_dir = _basis_ordner(md)
        ok = 0
        for m in MD_LINK.finditer(text):
            ref = m.group(1).strip()
            if ref.startswith(("http://", "https://", "data:", "mailto:", "tel:")):
                continue
            datei_teil, _, anker_teil = ref.partition("#")
            r = urllib.parse.unquote(datei_teil)
            anker_teil = urllib.parse.unquote(anker_teil).lower()
            # ★ QA-55: Reine Anker (``#abschnitt``) zeigen in die EIGENE Datei
            # und wurden bis hierhin komplett uebersprungen — dabei sind das
            # die Inhaltsverzeichnisse, also die Links, die am haeufigsten
            # benutzt werden.
            if not r and not anker_teil:
                continue
            total += 1
            eigene = md if md_dir == os.path.dirname(md) else os.path.join(REPO, "CHANGELOG.md")
            target = eigene if not r else os.path.normpath(os.path.join(md_dir, r))
            if not os.path.exists(target):
                dead.append((os.path.relpath(md, REPO).replace("\\", "/"),
                             ref, os.path.relpath(target, REPO).replace("\\", "/")))
            elif anker_teil and anker_teil not in _anker(target):
                # Die Datei gibt es, den Abschnitt nicht. Frueher galt das als
                # heiler Link — dabei landet der Leser oben auf der Seite und
                # sucht selbst.
                dead.append((os.path.relpath(md, REPO).replace("\\", "/"),
                             ref, os.path.relpath(target, REPO).replace("\\", "/")
                             + f"  (Abschnitt '#{anker_teil}' fehlt)"))
            else:
                ok += 1
        if ok:
            per_file_ok[os.path.relpath(md, REPO).replace("\\", "/")] = ok
    return total, dead, per_file_ok


def find_dead_links():
    return scan()[1]


def main() -> int:
    list_ok = "--list-ok" in sys.argv
    total, dead, per_file_ok = scan()
    print(f"[doc-links] {total} relative Querverweise geprueft, {len(dead)} tot, "
          f"in {len(per_file_ok)} Dateien mit Links.")
    if list_ok:
        for f, n in sorted(per_file_ok.items()):
            print(f"  ok {n:3d}  {f}")
    if dead:
        print("\n[doc-links] TOTE Querverweise:")
        for md_rel, ref, target in dead:
            print(f"  {md_rel}\n      link: {ref}\n      -> fehlt: {target}")
        return 1
    print("[doc-links] keine toten Querverweise.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
