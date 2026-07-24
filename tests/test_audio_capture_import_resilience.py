"""Linux-Audio: ein beim Import nicht erreichbarer PulseAudio-Server ist soft."""
from pathlib import Path


def test_capture_import_catches_non_importerror():
    source = Path("src/core/audio/capture.py").read_text(encoding="utf-8")
    assert "except Exception as exc:" in source
    assert "HAS_SOUNDCARD = False" in source
