"""Flow ITR's default home moved from a folder called flow to Flow/ITR. The
files move once, all or nothing, and only when the home is the default."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import paths, profiles

REAL_RENAME = os.rename


class HomeMove(unittest.TestCase):
    def setUp(self):
        self.user = Path(tempfile.mkdtemp(prefix="flow-user-"))
        self.addCleanup(shutil.rmtree, self.user, True)
        env = {k: v for k, v in os.environ.items() if k != paths.HOME_ENV}
        for p in (patch.dict(os.environ, env, clear=True),
                  patch("pathlib.Path.home", return_value=self.user),
                  patch.object(paths, "HOME_POINTER", self.user / "no-pointer.json")):
            p.start()
            self.addCleanup(p.stop)
        self.old = self.user / "flow"

    def legacy(self):
        """An old home, shaped like a real one."""
        (self.old / "Asha" / "documents").mkdir(parents=True)
        (self.old / "Asha" / "results").mkdir(parents=True)
        (self.old / "Asha" / "documents" / "form16.pdf").write_text("pdf", "utf-8")
        (self.old / "Asha" / "results" / "salary.json").write_text("{}", "utf-8")
        (self.old / ".state").mkdir()
        (self.old / ".state" / "token").write_text("secret-token", "utf-8")
        (self.old / ".state" / "server.log").write_text("log", "utf-8")
        (self.old / "fx_rates.json").write_text("{}", "utf-8")
        (self.old / "profiles.json").write_text(json.dumps({"active": "asha", "profiles": [{
            "id": "asha", "name": "Asha", "fy": "2025-26", "ay": "2026-27", "pan": "",
            "source_dir": "Asha/documents", "data_dir": "Asha/results", "settings": {}}]}), "utf-8")

    def test_until_it_moves_the_old_folder_is_the_home(self):
        self.legacy()
        self.assertEqual(paths.home(), self.old)
        self.assertIn("old default", paths.home_source())

    def test_the_files_move_once_and_the_returns_follow(self):
        self.legacy()
        moved = paths.move_legacy_home()
        new = self.user / "Flow" / "ITR"
        self.assertTrue(moved["moved"], moved)
        self.assertEqual(paths.home(), new)
        self.assertEqual(paths.home_source(), f"the default: Flow{os.sep}ITR in your user folder")
        self.assertEqual((new / ".state" / "token").read_text("utf-8"), "secret-token")
        self.assertTrue((new / "fx_rates.json").exists())
        # Folders are stored relative to the home, so they resolve in the new place.
        profile = profiles.active()
        self.assertEqual(profile["name"], "Asha")
        self.assertTrue((paths.resolve_dir(profile["source_dir"]) / "form16.pdf").exists())
        self.assertTrue((paths.resolve_dir(profile["data_dir"]) / "salary.json").exists())
        # The family folder now carries the family's name, and holds only the app.
        self.assertEqual(sorted(p.name for p in self.user.iterdir()), ["Flow"])
        self.assertEqual(sorted(p.name for p in (self.user / "Flow").iterdir()), ["ITR"])
        self.assertIsNone(paths.move_legacy_home())

    def test_one_file_held_open_puts_everything_back(self):
        self.legacy()

        def locked(src, dst):
            if Path(src).name == "Asha":
                raise PermissionError(13, "Access is denied", str(src))
            return REAL_RENAME(src, dst)

        with patch("os.rename", side_effect=locked):
            moved = paths.move_legacy_home()
        self.assertFalse(moved["moved"])
        self.assertIn("Access is denied", moved["error"])
        self.assertEqual(paths.home(), self.old)
        for name in ("profiles.json", "fx_rates.json", "Asha", ".state"):
            self.assertTrue((self.old / name).exists(), name)
        self.assertEqual((self.old / ".state" / "token").read_text("utf-8"), "secret-token")
        self.assertFalse((self.user / "Flow" / "ITR").exists())

    def test_a_working_file_held_open_does_not_stop_the_move(self):
        self.legacy()

        def log_open(src, dst):
            if Path(src).name in (".state", "server.log"):
                raise PermissionError(13, "Access is denied", str(src))
            return REAL_RENAME(src, dst)

        with patch("os.rename", side_effect=log_open):
            moved = paths.move_legacy_home()
        new = self.user / "Flow" / "ITR"
        self.assertTrue(moved["moved"], moved)
        self.assertEqual(moved["left_behind"], ["server.log"])
        self.assertEqual((new / ".state" / "token").read_text("utf-8"), "secret-token")
        self.assertTrue((new / "Asha" / "results" / "salary.json").exists())

    def test_a_home_someone_chose_stays_put(self):
        self.legacy()
        with patch.dict(os.environ, {paths.HOME_ENV: str(self.old)}):
            self.assertIsNone(paths.move_legacy_home())
            self.assertEqual(paths.home(), self.old)
        self.assertTrue((self.old / "profiles.json").exists())

    def test_a_new_machine_starts_in_the_new_place(self):
        self.assertEqual(paths.home(), self.user / "Flow" / "ITR")
        self.assertIsNone(paths.move_legacy_home())


if __name__ == "__main__":
    unittest.main()
