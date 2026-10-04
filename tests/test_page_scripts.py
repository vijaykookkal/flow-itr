"""The page's scripts share one global scope, so a name declared at the top of
two of them stops the second from loading at all -- and the page with it."""

from __future__ import annotations

import re
import unittest
from collections import defaultdict

from server import paths

DECLARATION = re.compile(r"^(?:async\s+)?(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)", re.M)


class PageScripts(unittest.TestCase):
    def test_no_top_level_name_is_declared_twice(self):
        seen = defaultdict(list)
        for script in sorted(paths.WEB.glob("*.js")):
            for name in DECLARATION.findall(script.read_text("utf-8")):
                seen[name].append(script.name)
        twice = {name: where for name, where in seen.items() if len(where) > 1}
        self.assertEqual(twice, {}, f"declared more than once at the top level: {twice}")


if __name__ == "__main__":
    unittest.main()
