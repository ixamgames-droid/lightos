"""QA-105: Der Tafel-Klon wurde unter Windows nie erkannt, wenn ``origin`` ein
lokaler Pfad mit Backslashes ist (``C:\\Users\\x\\lightos-intern.git``) — die
ARM-CI meldete dadurch rund 40 rote Tafel-Tests (26.10.2026). Ursache:
``_url_kern`` wandelte Backslashes nicht um, der Repo-Name wurde nie gefunden."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import session_claim as sc  # noqa: E402


def test_windows_pfad_ergibt_den_repo_namen():
    kern = sc._url_kern(r"C:\Users\x\AppData\Local\Temp\pytest-1\lightos-intern.git")
    assert kern.rsplit("/", 1)[-1] == sc.TAFEL_ORDNER


def test_windows_pfad_mit_schraegstrich_am_ende():
    kern = sc._url_kern("C:\\tmp\\lightos-intern\\")
    assert kern.rsplit("/", 1)[-1] == sc.TAFEL_ORDNER


def test_gleiche_repos_in_beiden_schreibweisen_gleich():
    assert sc._url_kern(r"C:\a\b\lightos.git") == sc._url_kern("C:/a/b/lightos.git")


def test_bisherige_formen_unveraendert():
    assert sc._url_kern("https://github.com/ixamgames-droid/lightos-intern.git") \
        == "github.com/ixamgames-droid/lightos-intern"
    assert sc._url_kern("git@github.com:ixamgames-droid/lightos-intern.git") \
        == "github.com/ixamgames-droid/lightos-intern"
    assert sc._url_kern("/tmp/x/lightos-intern.git").endswith("/lightos-intern")


def test_fremdes_repo_bleibt_abgelehnt_auch_mit_backslash():
    kern = sc._url_kern(r"C:\Users\x\lightos.git")
    assert kern.rsplit("/", 1)[-1] != sc.TAFEL_ORDNER
