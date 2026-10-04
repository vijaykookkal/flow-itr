"""Routing sees inside a zip, and knows a copy of the folder for what it is."""

from __future__ import annotations

import os
import tempfile
import unittest
import zipfile
from pathlib import Path

os.environ.setdefault("FLOW_HOME", tempfile.mkdtemp(prefix="flow-test-home-"))

from server import classify  # noqa: E402


def listing(folder: Path) -> list[dict]:
    return [{"path": p.name, "abs": str(p), "bytes": p.stat().st_size, "is_archive": p.suffix == ".zip"}
            for p in sorted(folder.iterdir())]


class ArchiveContents(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="flow-test-docs-"))
        (self.folder / "Form16.txt").write_text("FORM NO. 16 Part B salary certificate", "utf-8")
        with zipfile.ZipFile(self.folder / "invoices.zip", "w") as zf:
            zf.writestr("Airtel_Apr2025.txt", "Airtel postpaid bill for April 2025, total 1,118.64")
            zf.writestr("Laptop_invoice.txt", "Tax invoice: laptop, Rs 69,500 including GST")
        with zipfile.ZipFile(self.folder / "whole_folder_download.zip", "w") as zf:
            zf.write(self.folder / "Form16.txt", "My docs/Form16.txt")

    def test_members_and_their_text_are_listed(self):
        contents, dirs = classify.archive_contents("2026-27", listing(self.folder))
        inv = contents["invoices.zip"]
        self.assertIn("contains 2 file(s)", inv)
        self.assertIn("Airtel_Apr2025.txt", inv)
        self.assertIn("Laptop_invoice.txt", inv)
        self.assertIn("begins: Tax invoice: laptop", inv)
        self.assertTrue(dirs)

    def test_a_download_of_the_folder_shows_itself_as_a_duplicate(self):
        contents, _ = classify.archive_contents("2026-27", listing(self.folder))
        dup = contents["whole_folder_download.zip"]
        self.assertIn("1 of them the same as documents already in this listing", dup)
        self.assertIn("(the same file as Form16.txt)", dup)

    def test_the_prompt_carries_the_contents(self):
        docs = listing(self.folder)
        contents, _ = classify.archive_contents("2026-27", docs)
        prompt = classify.build_prompt("2026-27", docs, contents)
        self.assertIn("Laptop_invoice.txt", prompt)
        self.assertIn("routed by what is inside it", prompt)


if __name__ == "__main__":
    unittest.main()
