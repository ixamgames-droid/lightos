"""STAB-WAL-NET: WAL auf lokalen Linux-Dateisystemen — Netz weiterhin nicht.

Bis 2026-08-01 gab ``_is_local_writable_path`` auf allem außer Windows ein
hartes ``False`` zurück, mit der Begründung, es gebe „keinen portablen
lokaler-vs-Netz-Check". Für POSIX allgemein stimmt das; **für Linux nicht** —
``/proc/self/mountinfo`` nennt den Dateisystem-Typ des tragenden Mounts, und
genau daran hängt die Frage.

Der Preis war real und traf ausgerechnet die Zielmaschine: Davids Show-DB liegt
auf lokalem ext4 und lief trotzdem im DELETE-Journal (nachgemessen:
``journal_mode=delete`` auf `current_show.db` **und** `fixtures.db`).

★ **Erlaubnisliste, keine Verbotsliste** — das ist die tragende Eigenschaft und
hat einen eigenen Test. Eine Verbotsliste müsste jedes künftige
Netz-Dateisystem kennen und wäre beim ersten unbekannten fail-open, also genau
in der gefährlichen Richtung.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A                                       # noqa: E402


def _mountinfo(*zeilen: str) -> str:
    """Schreibt eine gestellte mountinfo-Tabelle und liefert den Pfad."""
    fh = tempfile.NamedTemporaryFile("w", suffix=".mountinfo",
                                     delete=False, encoding="utf-8")
    fh.write("".join(z if z.endswith("\n") else z + "\n" for z in zeilen))
    fh.close()
    return fh.name


def _zeile(punkt: str, typ: str, optionale_felder: str = "shared:1") -> str:
    """Eine mountinfo-Zeile im echten Format.

    Die Zahl der optionalen Felder vor dem ``-`` ist im Kernel-Format variabel —
    deshalb ist sie hier einstellbar: genau daran scheitert jede Auswertung, die
    ein festes Feld zählt statt am ``-`` zu trennen.
    """
    rest = f" {optionale_felder}" if optionale_felder else ""
    return f"36 35 8:2 / {punkt} rw,relatime{rest} - {typ} /dev/sda2 rw"


class FstypeTest(unittest.TestCase):
    def setUp(self):
        self._dateien = []

    def tearDown(self):
        for f in self._dateien:
            try:
                os.unlink(f)
            except OSError:
                pass

    def _quelle(self, *zeilen):
        p = _mountinfo(*zeilen)
        self._dateien.append(p)
        return p

    def test_findet_den_typ_des_tragenden_mounts(self):
        q = self._quelle(_zeile("/", "ext4"))
        self.assertEqual(A._linux_fstype("/home/user/show.db", q), "ext4")

    def test_der_laengste_passende_mountpunkt_gewinnt(self):
        """★ Bei verschachtelten Mounts trägt den Pfad der speziellere. Ohne
        diese Regel meldete ein NFS-``/home`` unter einem ext4-``/`` fälschlich
        „lokal" — also WAL auf einem Netzlaufwerk."""
        q = self._quelle(_zeile("/", "ext4"), _zeile("/home", "nfs4"))
        self.assertEqual(A._linux_fstype("/home/user/show.db", q), "nfs4")
        self.assertEqual(A._linux_fstype("/opt/show.db", q), "ext4")

    def test_reihenfolge_der_zeilen_ist_egal(self):
        q = self._quelle(_zeile("/home", "nfs4"), _zeile("/", "ext4"))
        self.assertEqual(A._linux_fstype("/home/user/show.db", q), "nfs4")

    def test_praefix_darf_nicht_auf_halbem_namen_greifen(self):
        """``/home2`` ist kein Unterpfad von ``/home``."""
        q = self._quelle(_zeile("/", "ext4"), _zeile("/home", "nfs4"))
        self.assertEqual(A._linux_fstype("/home2/show.db", q), "ext4")

    def test_variable_zahl_optionaler_felder(self):
        """Der Kernel schreibt 0..n optionale Felder vor dem ``-``."""
        q = self._quelle(_zeile("/", "ext4", optionale_felder=""),
                         _zeile("/daten", "xfs", "shared:2 master:3 propagate_from:4"))
        self.assertEqual(A._linux_fstype("/x", q), "ext4")
        self.assertEqual(A._linux_fstype("/daten/show.db", q), "xfs")

    def test_leerzeichen_im_mountpunkt(self):
        """mountinfo kodiert Leerzeichen als ``\\040``."""
        q = self._quelle(_zeile("/", "ext4"), _zeile("/media/Meine\\040Platte", "ext4"))
        self.assertEqual(A._linux_fstype("/media/Meine Platte/show.db", q), "ext4")

    def test_kaputte_zeilen_werden_uebersprungen(self):
        q = self._quelle("völliger unsinn", "36 35 8:2 / /", _zeile("/", "ext4"))
        self.assertEqual(A._linux_fstype("/x", q), "ext4")

    def test_unlesbare_quelle_liefert_unbekannt(self):
        self.assertEqual(A._linux_fstype("/x", "/gibt/es/nicht"), "")


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux-Pfad")
class WalEntscheidungTest(unittest.TestCase):
    def setUp(self):
        self._orig = A._linux_fstype
        self._dateien = []

    def tearDown(self):
        A._linux_fstype = self._orig
        for f in self._dateien:
            try:
                os.unlink(f)
            except OSError:
                pass

    def _mit_fstype(self, typ):
        A._linux_fstype = lambda pfad, quelle=None: typ

    def test_lokale_dateisysteme_bekommen_wal(self):
        for typ in ("ext4", "btrfs", "xfs", "zfs", "f2fs", "tmpfs"):
            with self.subTest(typ=typ):
                self._mit_fstype(typ)
                self.assertTrue(A._is_local_writable_path("/daten/show.db"))

    def test_netz_dateisysteme_bekommen_kein_wal(self):
        for typ in ("nfs", "nfs4", "cifs", "smb3", "9p", "ceph", "glusterfs",
                    "fuse.sshfs", "fuse.rclone", "davfs"):
            with self.subTest(typ=typ):
                self._mit_fstype(typ)
                self.assertFalse(A._is_local_writable_path("/daten/show.db"))

    def test_unbekannter_typ_bekommt_kein_wal(self):
        """★ Die Erlaubnislisten-Eigenschaft: was niemand kennt, bleibt aus.

        Eine Verbotsliste wäre hier fail-open — beim ersten Dateisystem, das es
        beim Schreiben dieses Codes noch nicht gab."""
        for typ in ("ein_dateisystem_aus_der_zukunft", "", "overlay"):
            with self.subTest(typ=typ):
                self._mit_fstype(typ)
                self.assertFalse(A._is_local_writable_path("/daten/show.db"))

    def test_cloud_sync_ordner_schlaegt_lokales_dateisystem(self):
        """Ein Sync-Client fasst die -wal/-shm-Sidecars an, egal wie lokal die
        Platte darunter ist."""
        self._mit_fstype("ext4")
        for pfad in ("/home/user/Dropbox/show.db",
                     "/home/user/OneDrive/daten/show.db",
                     "/home/user/Nextcloud/show.db"):
            with self.subTest(pfad=pfad):
                self.assertFalse(A._is_local_writable_path(pfad))

    def test_unc_pfad_bekommt_kein_wal_auch_auf_linux(self):
        """★ Ein Fehler, den erst dieser Umbau freigelegt hat.

        Auf Linux ist ``\\\\server\\share\\…`` NICHT absolut — ``abspath()``
        stellt das Arbeitsverzeichnis davor und der ``\\\\``-Präfix
        verschwindet. Solange der Linux-Zweig pauschal ``False`` lieferte, war
        das folgenlos; mit dem fstype-Check wäre daraus WAL auf einem Netzpfad
        geworden. Der Bestandstest hat es gemeldet — dieser hier hält es fest.
        """
        self._mit_fstype("ext4")
        for pfad in (r"\\server\share\data\current_show.db",
                     r"\\?\UNC\server\share\show.db"):
            with self.subTest(pfad=pfad):
                self.assertFalse(A._is_local_writable_path(pfad))

    def test_echter_projektpfad_bekommt_jetzt_wal(self):
        """Der Anlass des Items: Davids Daten liegen auf lokalem ext4 und liefen
        trotzdem ohne WAL. Läuft der Test auf einem Netz-Dateisystem, ist das
        Ergebnis korrekt anders — dann wird er übersprungen."""
        pfad = os.path.abspath("data/current_show.db")
        typ = self._orig(pfad)
        if typ not in A._WAL_SICHERE_FSTYPES:
            self.skipTest(f"Arbeitskopie liegt auf '{typ}' — kein lokaler Fall")
        self.assertTrue(A._is_local_writable_path(pfad))


class ErlaubnislisteTest(unittest.TestCase):
    def test_kein_netz_dateisystem_steht_versehentlich_drin(self):
        """Wächter gegen ein unbedacht ergänztes Netz-Dateisystem."""
        verboten = {"nfs", "nfs4", "cifs", "smbfs", "smb3", "9p", "afs",
                    "ceph", "glusterfs", "lustre", "davfs", "overlay",
                    "fuse.sshfs", "fuse.rclone", "fuse.s3fs"}
        self.assertEqual(A._WAL_SICHERE_FSTYPES & verboten, set())


if __name__ == "__main__":
    unittest.main()
