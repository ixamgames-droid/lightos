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

TOP_LEVEL = ("README.md", "BACKLOG.md", "ROADMAP.md", "CHANGELOG.md")


def _iter_md_files():
    for base, dirs, files in os.walk(os.path.join(REPO, "docs")):
        # Archiv-Ordner (``_archiv``/``_archive``) sind bewusst nicht gepflegt und
        # von Graph/Lint/Changelog ausgenommen -> nicht auf tote Links pruefen.
        dirs[:] = [d for d in dirs if not d.startswith("_arch")]
        for fn in files:
            if fn.lower().endswith(".md"):
                yield os.path.join(base, fn)
    for fn in TOP_LEVEL:
        p = os.path.join(REPO, fn)
        if os.path.exists(p):
            yield p


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
        md_dir = os.path.dirname(md)
        ok = 0
        for m in MD_LINK.finditer(text):
            ref = m.group(1).strip()
            if ref.startswith(("http://", "https://", "data:", "#", "mailto:", "tel:")):
                continue
            r = urllib.parse.unquote(ref.split("#", 1)[0])   # Anker abtrennen
            if not r:
                continue
            total += 1
            target = os.path.normpath(os.path.join(md_dir, r))
            if os.path.exists(target):
                ok += 1
            else:
                dead.append((os.path.relpath(md, REPO).replace("\\", "/"),
                             ref, os.path.relpath(target, REPO).replace("\\", "/")))
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
