import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DEFAULTS, Config


class TestConfig(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._path = str(Path(self._tmpdir.name) / "sub" / "config.json")

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_defaults_loaded_when_file_missing(self):
        cfg = Config(self._path).load()
        self.assertEqual(cfg.data, DEFAULTS)

    def test_values_persist(self):
        cfg = Config(self._path).load()
        cfg.set("selected_band", "40m")
        cfg.save()

        cfg2 = Config(self._path).load()
        self.assertEqual(cfg2.get("selected_band"), "40m")

    def test_missing_keys_filled_with_defaults(self):
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        Path(self._path).write_text('{"selected_band": "15m"}', encoding="utf-8")

        cfg = Config(self._path).load()
        self.assertEqual(cfg.get("selected_band"), "15m")
        self.assertEqual(cfg.get("host"), DEFAULTS["host"])

    def test_corrupt_json_falls_back_to_defaults(self):
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        Path(self._path).write_text("{not valid json", encoding="utf-8")

        cfg = Config(self._path).load()
        self.assertEqual(cfg.data, DEFAULTS)


if __name__ == "__main__":
    unittest.main()
