"""VC-IMG: VC-Button-Hintergrundbild/GIF (Datenmodell + Rendering + Asset-ZIP).

Headless (offscreen) testbar: Feld-Defaults, to_dict/apply_dict-Roundtrip (inkl.
fehlend/None), Set/Clear, Paint-Safety (kein Crash bei winziger/normaler Groesse),
GIF-Construct-Safety (QMovie im offscreen evtl. nicht `isValid` -> Fallback, nie
Crash), sowie der ZIP-Embed/Extract-Roundtrip der Assets (Portabilitaet).

NICHT headless testbar: die tatsaechliche GIF-Animation (kein Kompositor/Plugin)
-> per Construct-/Paint-Safety abgedeckt + manueller/CU-Check in der App.
"""
import base64
import io
import os
import tempfile
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage

from src.ui.virtualconsole.vc_button import VCButton
from src.core.show import vc_assets

_app = QApplication.instance() or QApplication([])

# 1x1 transparentes GIF (gueltige GIF89a-Bytes) + ein winziges PNG generieren wir
# zur Laufzeit ueber QImage.
_GIF_1x1 = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


def _make_png(path):
    img = QImage(4, 4, QImage.Format.Format_ARGB32)
    img.fill(0xFF3366CC)
    img.save(path, "PNG")


class TestBgImageField(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="vcimg_")
        vc_assets.set_cache_dir_for_test(self._tmp)

    def tearDown(self):
        vc_assets.set_cache_dir_for_test(None)

    def test_default_empty(self):
        b = VCButton()
        self.assertEqual(b.bg_image, "")
        self.assertEqual(b.to_dict().get("bg_image"), "")

    def test_roundtrip_missing_and_none(self):
        b = VCButton()
        b.apply_dict(b.to_dict())          # leere Show
        self.assertEqual(b.bg_image, "")
        b.apply_dict({})                    # kein bg_image-Key (aeltere Show)
        self.assertEqual(b.bg_image, "")
        b.apply_dict({"bg_image": None})   # explizit None
        self.assertEqual(b.bg_image, "")

    def test_set_stores_and_resolves(self):
        png = os.path.join(self._tmp, "src.png")
        _make_png(png)
        b = VCButton()
        key = vc_assets.import_file(png)
        b.set_bg_image(key)
        self.assertTrue(vc_assets.is_valid_key(key))
        self.assertEqual(b.bg_image, key)
        self.assertTrue(os.path.isfile(vc_assets.resolve(key)))
        # Roundtrip erhaelt den Key
        b2 = VCButton()
        b2.apply_dict(b.to_dict())
        self.assertEqual(b2.bg_image, key)

    def test_clear(self):
        png = os.path.join(self._tmp, "src2.png")
        _make_png(png)
        b = VCButton()
        b.set_bg_image(vc_assets.import_file(png))
        b.clear_bg_image()
        self.assertEqual(b.bg_image, "")
        self.assertIsNone(b._bg_movie)
        self.assertIsNone(b._bg_pm)

    def test_paint_safe_with_static_image(self):
        png = os.path.join(self._tmp, "src3.png")
        _make_png(png)
        b = VCButton("Mit Bild")
        b.set_bg_image(vc_assets.import_file(png))
        for w, h in [(4, 4), (16, 12), (80, 60)]:
            b.resize(w, h)
            self.assertFalse(b.grab().toImage().isNull())   # kein Crash, Bild kommt

    def test_gif_constructs_and_paints_safely(self):
        gif = os.path.join(self._tmp, "anim.gif")
        with open(gif, "wb") as f:
            f.write(_GIF_1x1)
        b = VCButton("GIF")
        b.set_bg_image(vc_assets.import_file(gif))   # baut QMovie ODER Fallback
        b.resize(60, 40)
        # show()/hide() (echte Events) + paint duerfen NICHT werfen (isValid evtl.
        # False headless -> Fallback/None).
        b.show()
        self.assertFalse(b.grab().toImage().isNull())
        b.hide()


class TestVcAssets(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="vcassets_")
        vc_assets.set_cache_dir_for_test(self._tmp)

    def tearDown(self):
        vc_assets.set_cache_dir_for_test(None)

    def test_store_is_content_hash_and_dedups(self):
        k1 = vc_assets.store_bytes(b"HELLO", ".png")
        k2 = vc_assets.store_bytes(b"HELLO", ".png")
        self.assertEqual(k1, k2)                       # gleicher Inhalt -> ein Key
        self.assertNotEqual(k1, vc_assets.store_bytes(b"OTHER", ".png"))

    def test_invalid_key_rejected(self):
        # Pfad-Traversal / Muellkeys werden nicht abgelegt/aufgeloest
        self.assertFalse(vc_assets.is_valid_key("../evil.png"))
        self.assertFalse(vc_assets.is_valid_key("show.json"))
        self.assertEqual(vc_assets.resolve("../evil.png"), "")
        vc_assets.store_extracted("../../evil.png", b"x")
        self.assertFalse(os.path.exists(os.path.join(self._tmp, "..", "evil.png")))

    def test_collect_keys_recursive(self):
        key = vc_assets.store_bytes(b"IMG", ".gif")
        show = {"virtual_console": {"pages": [
            {"widgets": [{"type": "button", "bg_image": key},
                         {"type": "slider"}]},
        ]}, "layout": {"nested": [{"bg_image": "not_a_valid_key"}]}}
        found = vc_assets.collect_keys(show)
        self.assertIn(key, found)
        self.assertNotIn("not_a_valid_key", found)     # nur gueltige Keys

    def test_zip_embed_and_extract_roundtrip(self):
        # simuliert den Asset-Teil von save_show -> load_show ueber ZIP-Grenze
        key = vc_assets.store_bytes(b"PNGDATA-XYZ", ".png")
        show = {"virtual_console": {"widgets": [{"bg_image": key}]}}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("show.json", "{}")
            for k in vc_assets.collect_keys(show):
                data = vc_assets.bytes_for(k)
                if data is not None:
                    zf.writestr(vc_assets.zip_name(k), data)
        # frischer Cache (anderer PC) -> Asset muss aus dem ZIP wiederkommen
        vc_assets.set_cache_dir_for_test(tempfile.mkdtemp(prefix="vcassets2_"))
        self.assertEqual(vc_assets.resolve(key), "")   # noch nicht da
        buf.seek(0)
        with zipfile.ZipFile(buf, "r") as zf:
            for n in zf.namelist():
                if vc_assets.is_asset_entry(n):
                    vc_assets.store_extracted(vc_assets.key_from_entry(n), zf.read(n))
        self.assertTrue(vc_assets.resolve(key))         # jetzt entpackt
        self.assertEqual(vc_assets.bytes_for(key), b"PNGDATA-XYZ")


if __name__ == "__main__":
    unittest.main()
