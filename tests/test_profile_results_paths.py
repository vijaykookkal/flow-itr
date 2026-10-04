"""A return's folder follows its name: a rename moves it, and only when asked."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import paths, profiles


class ResultsPaths(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="flow-profile-test-"))
        self.home_env = patch.dict(os.environ, {"FLOW_HOME": str(self.home)})
        self.home_env.start()
        profiles.load_all()

    def tearDown(self):
        self.home_env.stop()
        shutil.rmtree(self.home)

    def create_return(self, name="Asha 2025-26", **kwargs):
        profiles.create(name, "2025-26", activate=False, **kwargs)
        return profiles.get(profiles.slug(name))

    def put(self, folder: str, name: str, text: str = "existing") -> Path:
        path = paths.resolve_dir(folder) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, "utf-8")
        return path

    def test_new_return_uses_name_based_results_path(self):
        profile = self.create_return()

        self.assertEqual(profile["data_dir"], "Asha 2025-26/results")
        described = profiles.describe(profile)
        self.assertEqual(described["conventional_data_path"],
                         str(self.home / "Asha 2025-26" / "results"))
        self.assertTrue(described["data_conventional"])
        self.assertTrue(described["source_conventional"])

    def test_describe_tolerates_no_return(self):
        self.assertNotIn("conventional_data_path", profiles.describe({}))

    def test_rename_moves_the_return_folder(self):
        profile = self.create_return()
        self.put(profile["data_dir"], "salary.json")
        self.put(profile["source_dir"], "form16.pdf")

        updated = profiles.update(profile["id"], {"name": "Asha renamed", "move_folder": True})

        self.assertEqual(updated["data_dir"], "Asha renamed/results")
        self.assertEqual(updated["source_dir"], "Asha renamed/documents")
        new = self.home / "Asha renamed"
        self.assertEqual((new / "results" / "salary.json").read_text("utf-8"), "existing")
        self.assertTrue((new / "documents" / "form16.pdf").exists())
        self.assertFalse((self.home / "Asha 2025-26").exists())

    def test_rename_leaves_documents_kept_elsewhere(self):
        elsewhere = Path(tempfile.mkdtemp(prefix="flow-docs-"))
        self.addCleanup(shutil.rmtree, elsewhere)
        profile = self.create_return(source_dir=str(elsewhere))
        self.put(profile["data_dir"], "salary.json")

        updated = profiles.update(profile["id"], {"name": "Asha renamed", "move_folder": True})

        self.assertEqual(updated["source_dir"], elsewhere.as_posix())
        self.assertTrue((self.home / "Asha renamed" / "results" / "salary.json").exists())

    def test_rename_moves_shared_documents_for_every_reader(self):
        profile = self.create_return()
        other = self.create_return("Asha old regime", source_dir=profile["source_dir"])
        self.put(profile["source_dir"], "form16.pdf")

        updated = profiles.update(profile["id"], {"name": "Asha renamed", "move_folder": True})

        self.assertEqual(updated["source_dir"], "Asha renamed/documents")
        self.assertEqual(profiles.get(other["id"])["source_dir"], "Asha renamed/documents")
        self.assertTrue((self.home / "Asha renamed" / "documents" / "form16.pdf").exists())

    def test_rename_needs_the_move_confirmed(self):
        profile = self.create_return()
        old = self.put(profile["data_dir"], "salary.json")

        with self.assertRaisesRegex(ValueError, "confirm the move"):
            profiles.update(profile["id"], {"name": "Asha renamed"})

        self.assertEqual(profiles.get(profile["id"])["name"], "Asha 2025-26")
        self.assertTrue(old.exists())

    def test_rename_of_an_empty_return_still_moves_its_folder(self):
        profile = self.create_return()

        updated = profiles.update(profile["id"], {"name": "Asha renamed", "move_folder": True})

        self.assertEqual(updated["data_dir"], "Asha renamed/results")
        self.assertTrue((self.home / "Asha renamed" / "documents" / "README.md").exists())
        self.assertFalse((self.home / "Asha 2025-26").exists())

    def test_same_folder_name_needs_no_move(self):
        profile = self.create_return()

        updated = profiles.update(profile["id"], {"name": "Asha 2025-26."})

        self.assertEqual(updated["data_dir"], "Asha 2025-26/results")

    def test_rename_refuses_a_nonempty_target(self):
        profile = self.create_return()
        self.put(profile["data_dir"], "salary.json")
        target = self.put("Asha renamed/results", "stale.json", "keep")

        with self.assertRaisesRegex(ValueError, "already has files"):
            profiles.update(profile["id"], {"name": "Asha renamed", "move_folder": True})

        self.assertEqual(profiles.get(profile["id"])["name"], "Asha 2025-26")
        self.assertEqual(target.read_text("utf-8"), "keep")
        self.assertTrue((self.home / "Asha 2025-26" / "results" / "salary.json").exists())

    def test_a_refused_rename_moves_nothing(self):
        profile = self.create_return()
        old = self.put(profile["data_dir"], "salary.json")

        with self.assertRaisesRegex(ValueError, "there is no folder"):
            profiles.update(profile["id"], {"name": "Asha renamed", "move_folder": True,
                                            "source_dir": str(self.home / "missing")})

        self.assertTrue(old.exists())
        self.assertEqual(profiles.get(profile["id"])["data_dir"], "Asha 2025-26/results")

    def test_a_failed_move_is_undone(self):
        profile = self.create_return()
        results = self.put(profile["data_dir"], "salary.json")
        self.put(profile["source_dir"], "form16.pdf")
        real = profiles._move_folder
        calls = []

        def documents_locked(old, new):
            calls.append(old)
            if old.name == "documents" and len(calls) == 2:
                raise PermissionError(13, "Access is denied", str(old))
            real(old, new)

        with patch.object(profiles, "_move_folder", documents_locked):
            with self.assertRaisesRegex(ValueError, "Nothing was changed"):
                profiles.update(profile["id"], {"name": "Asha renamed", "move_folder": True})

        self.assertTrue(results.exists())
        self.assertEqual(profiles.get(profile["id"])["data_dir"], "Asha 2025-26/results")

    @unittest.skipUnless(os.name == "nt", "only Windows refuses to rename a folder holding an open file")
    def test_an_open_file_stops_the_rename_cleanly(self):
        profile = self.create_return()
        results = self.put(profile["data_dir"], "salary.json")
        held = open(results.parent / "results.xlsx", "w")       # as Excel would hold it
        try:
            with self.assertRaisesRegex(ValueError, "Nothing was changed"):
                profiles.update(profile["id"], {"name": "Asha renamed", "move_folder": True})
        finally:
            held.close()
        # Nothing copied half-way: the old folder whole, nothing in the new one.
        self.assertEqual(sorted(p.name for p in results.parent.iterdir()), ["results.xlsx", "salary.json"])
        self.assertFalse((self.home / "Asha renamed" / "results").exists())
        self.assertEqual(profiles.get(profile["id"])["name"], "Asha 2025-26")

    def test_other_changes_leave_a_results_folder_kept_elsewhere(self):
        profile = self.create_return()
        store = profiles.load_all()
        next(p for p in store["profiles"] if p["id"] == profile["id"])["data_dir"] = "Elsewhere/results"
        profiles.save_all(store)

        updated = profiles.update(profile["id"], {"pan": "ABCDE1234F"})

        self.assertEqual(updated["data_dir"], "Elsewhere/results")
        self.assertFalse(profiles.describe(updated)["data_conventional"])

    def test_results_kept_elsewhere_can_join_the_return_folder(self):
        profile = self.create_return()
        store = profiles.load_all()
        next(p for p in store["profiles"] if p["id"] == profile["id"])["data_dir"] = "Elsewhere/results"
        profiles.save_all(store)
        shutil.rmtree(paths.resolve_dir(profile["data_dir"]))
        self.put("Elsewhere/results", "salary.json")

        profiles.use_conventional_results(profile["id"])

        self.assertEqual(profiles.get(profile["id"])["data_dir"], "Asha 2025-26/results")
        self.assertTrue((self.home / "Asha 2025-26" / "results" / "salary.json").exists())
        self.assertEqual(profiles.get(profile["id"])["source_dir"], "Asha 2025-26/documents")


if __name__ == "__main__":
    unittest.main()
