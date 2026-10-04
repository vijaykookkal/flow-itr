"""The page is told when the server's own code has changed since it started."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from server import app


class CodeVersion(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="flow-code-test-"))
        self.addCleanup(shutil.rmtree, self.root)
        for rel in ("server/app.py", "engine/rates/ay2026_27.py"):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text("x = 1\n", "utf-8")

    def test_a_changed_file_changes_it(self):
        before = app.code_version(self.root)
        (self.root / "engine/rates/ay2026_27.py").write_text("x = 22\n", "utf-8")
        self.assertNotEqual(app.code_version(self.root), before)

    def test_a_new_file_changes_it(self):
        before = app.code_version(self.root)
        (self.root / "engine/planning.py").write_text("x = 1\n", "utf-8")
        self.assertNotEqual(app.code_version(self.root), before)

    def test_compiled_files_do_not(self):
        before = app.code_version(self.root)
        cache = self.root / "server/__pycache__"
        cache.mkdir()
        (cache / "app.cpython-313.pyc").write_bytes(b"\0" * 64)
        self.assertEqual(app.code_version(self.root), before)

    def test_touched_file_is_noticed(self):
        path = self.root / "server/app.py"
        before = app.code_version(self.root)
        st = path.stat()
        os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
        self.assertNotEqual(app.code_version(self.root), before)

    def test_running_server_is_current_at_start(self):
        self.assertFalse(app.server_stale())


if __name__ == "__main__":
    unittest.main()
