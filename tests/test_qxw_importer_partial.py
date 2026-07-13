"""FIMP-04: Ein QXW-Fixture mit einem defekten Zahlenfeld darf nicht mehr
STILL das ganze Fixture verwerfen und die Erfolgsmeldung überzählen. Der
Importer sammelt übersprungene Fixtures (mit Grund) und koppelt Zählung +
Meldung an die tatsächlich importierten."""
import os
import tempfile

from src.core.show.qxw_importer import import_qxw


_QXW = """<?xml version="1.0" encoding="UTF-8"?>
<Workspace>
 <Engine>
  <Fixture>
   <Manufacturer>Generic</Manufacturer>
   <Model>Dimmer</Model>
   <Mode>Default</Mode>
   <ID>0</ID>
   <Name>Good A</Name>
   <Universe>0</Universe>
   <Address>0</Address>
   <Channels>1</Channels>
  </Fixture>
  <Fixture>
   <Manufacturer>Generic</Manufacturer>
   <Model>RGB</Model>
   <Mode>Default</Mode>
   <ID>1</ID>
   <Name>Broken B</Name>
   <Universe>0</Universe>
   <Address>notanumber</Address>
   <Channels>3</Channels>
  </Fixture>
  <Fixture>
   <Manufacturer>Generic</Manufacturer>
   <Model>Moving</Model>
   <Mode>Default</Mode>
   <ID>2</ID>
   <Name>Good C</Name>
   <Universe>0</Universe>
   <Address>10</Address>
   <Channels>8</Channels>
  </Fixture>
 </Engine>
</Workspace>
"""


def _write_tmp(text: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".qxw")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def test_partial_import_counts_only_valid_fixtures():
    path = _write_tmp(_QXW)
    try:
        res = import_qxw(path)
    finally:
        os.unlink(path)

    assert res["ok"] is True
    # Genau 2 importiert (Good A + Good C), das defekte B fehlt.
    assert len(res["fixtures"]) == 2
    labels = {fx["label"] for fx in res["fixtures"]}
    assert labels == {"Good A", "Good C"}

    # Das defekte Fixture ist als übersprungen mit Grund vermerkt.
    assert len(res["skipped_fixtures"]) == 1
    skipped = res["skipped_fixtures"][0]
    assert skipped["label"] == "Broken B"
    assert "Address" in skipped["reason"]
    assert "notanumber" in skipped["reason"]

    # Meldung nennt die TATSÄCHLICH importierten (2), nicht 3, und meldet
    # das übersprungene Fixture.
    msg = res["message"]
    assert "Importiert: 2 Fixtures" in msg
    assert "3 Fixtures" not in msg
    assert "übersprungen" in msg
    assert "Broken B" in msg


def test_clean_import_success_case_unchanged():
    """Erfolgsfall ohne Defekte: keine übersprungenen Fixtures, Meldung wie
    bisher (keine Skip-Zeile)."""
    clean = _QXW.replace("notanumber", "5")
    path = _write_tmp(clean)
    try:
        res = import_qxw(path)
    finally:
        os.unlink(path)

    assert res["ok"] is True
    assert len(res["fixtures"]) == 3
    assert res["skipped_fixtures"] == []
    assert res["message"] == (
        "Importiert: 3 Fixtures, 0 Funktionen, 0 VC-Widgets"
    )
