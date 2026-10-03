"""A syntax sanity check for web/*.js, for a machine with no Node installed.

This is not a JavaScript parser. It is a scanner that catches the class of
damage that actually happens here: a string literal broken across a line, or an
unbalanced bracket, introduced while editing the file with a script. Either one
makes the browser refuse to parse the whole file, and the symptom is a page
that renders its static HTML and nothing else -- no error, no clue.

    python tools/check_js.py

Exits non-zero on failure, so it can go in a pre-commit hook.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAIRS = {")": "(", "]": "[", "}": "{"}


# After these, a "/" begins a regular expression rather than a division: you
# cannot divide by an operator or an opening bracket. This is the standard
# heuristic, and it is enough for hand-written code.
BEFORE_REGEX = set("(,=:[!&|?{};+-*%~^<>") | {""}


# ...and after these words, which end in a letter and so look like a value to
# divide: `return /[",]/.test(s)` is a regex, not `return` divided by something.
KEYWORDS_BEFORE_REGEX = {"return", "typeof", "case", "in", "of", "delete", "void", "throw",
                         "new", "else", "do", "instanceof", "yield", "await"}


def word_before(text: str, i: int) -> str:
    j = i - 1
    while j >= 0 and text[j] in " \t":
        j -= 1
    end = j + 1
    while j >= 0 and (text[j].isalnum() or text[j] in "_$"):
        j -= 1
    return text[j + 1:end]


def starts_regex(text: str, i: int, last: str) -> bool:
    if last not in BEFORE_REGEX and word_before(text, i) not in KEYWORDS_BEFORE_REGEX:
        return False
    # An empty // is a comment, handled earlier; a bare / at end of file is not
    # a regex either.
    return i + 1 < len(text) and text[i + 1] not in "/*"


def skip_regex(text: str, i: int, line: int) -> tuple[int, int]:
    """Past the closing '/', with the line count kept up to date."""
    i += 1
    in_class = False
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "\n":            # an unterminated regex; let the rest report
            return i, line
        if ch == "[":
            in_class = True
        elif ch == "]":
            in_class = False
        elif ch == "/" and not in_class:
            i += 1
            break
        i += 1
    while i < len(text) and text[i].isalpha():   # flags: g, i, m, s, u, y
        i += 1
    return i, line


# A `const` or `let` that repeats a name already bound in the same scope is a
# SyntaxError, and the browser then refuses to parse the WHOLE file -- the page
# renders its static HTML and nothing else, with no clue which line did it.
# The common case is a function that declares a variable named after one of its
# own parameters, so that is what this looks for.
DECL_RE = re.compile(r"^\s*(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=")
FUNC_RE = re.compile(r"^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)")


def redeclarations(path: Path) -> list[str]:
    """`const` names a function binds twice, which makes the file unparseable.

    Two shapes of the same fault, and both blank the page with no error in the
    console -- the browser refuses the whole file, so the static HTML renders
    and nothing else:

      * a body variable named after one of the function's own parameters;
      * the same `const` declared twice in one block, which is what happens
        when a second section is added to a long render function and reaches
        for the obvious name.

    Declarations are tracked per block rather than per function, because
    `const x` in two sibling `if` blocks is perfectly legal and flagging it
    would teach everyone to ignore this tool.
    """
    problems: list[str] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    params: set[str] = set()
    name, depth, start = "", 0, 0
    scopes: list[dict[str, int]] = []

    for i, line in enumerate(lines, 1):
        if depth == 0:
            m = FUNC_RE.match(line)
            if m:
                name = m.group(1)
                params = {
                    p.strip().split("=")[0].strip()
                    for p in m.group(2).split(",") if p.strip()
                }
                params = {p for p in params if p.isidentifier()}
                depth, start = line.count("{") - line.count("}"), i
                scopes = [{} for _ in range(max(1, depth))]
                continue
        else:
            decl = DECL_RE.match(line)
            if decl:
                bound = decl.group(1)
                if bound in params:
                    problems.append(
                        f"{path.name}:{i}: {name}() declares {bound!r}, which is already "
                        f"its parameter (line {start}) -- the file will not parse"
                    )
                elif scopes and bound in scopes[-1]:
                    problems.append(
                        f"{path.name}:{i}: {name}() declares {bound!r} again in the same "
                        f"block (first at line {scopes[-1][bound]}) -- the file will not parse"
                    )
                elif scopes:
                    scopes[-1][bound] = i

            delta = line.count("{") - line.count("}")
            for _ in range(max(0, delta)):
                scopes.append({})
            for _ in range(max(0, -delta)):
                if scopes:
                    scopes.pop()
            depth += delta
            if depth <= 0:
                depth, params, scopes = 0, set(), []
    return problems


def check(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    problems: list[str] = []
    stack: list[tuple[str, int]] = []

    i, line = 0, 1
    last = ""                     # last significant character, to spot regexes
    quote: str | None = None      # the open string delimiter, if inside one
    quote_line = 0
    mode: str | None = None       # 'line' or 'block' comment

    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if ch == "\n":
            line += 1
            if mode == "line":
                mode = None
            # A ' or " string may not contain a raw newline. A backtick may.
            if quote in ("'", '"'):
                problems.append(
                    f"{path.name}:{quote_line}: string opened with {quote} is not closed "
                    f"on the same line -- the file will not parse"
                )
                quote = None
            i += 1
            continue

        if mode == "line":
            i += 1
            continue
        if mode == "block":
            if ch == "*" and nxt == "/":
                mode, i = None, i + 2
            else:
                i += 1
            continue

        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue

        if ch == "/" and nxt == "/":
            mode, i = "line", i + 2
            continue
        if ch == "/" and nxt == "*":
            mode, i = "block", i + 2
            continue
        if ch == "/" and starts_regex(text, i, last):
            # A regular expression literal: its brackets are pattern syntax,
            # not code. /\((\d+)[^)]*\)/ would otherwise look like three
            # unbalanced brackets and drown a real fault in noise.
            i, line = skip_regex(text, i, line)
            continue
        if ch in "'\"`":
            quote, quote_line, i = ch, line, i + 1
            continue

        if not ch.isspace():
            last = ch

        if ch in "([{":
            stack.append((ch, line))
        elif ch in ")]}":
            if not stack:
                problems.append(f"{path.name}:{line}: unmatched closing {ch!r}")
            elif stack[-1][0] != PAIRS[ch]:
                opener, opened_at = stack[-1]
                problems.append(
                    f"{path.name}:{line}: {ch!r} closes {opener!r} opened at line {opened_at}"
                )
                stack.pop()
            else:
                stack.pop()
        i += 1

    problems.extend(redeclarations(path))

    if quote:
        problems.append(f"{path.name}:{quote_line}: unterminated {quote} string")
    for opener, opened_at in stack:
        problems.append(f"{path.name}:{opened_at}: {opener!r} is never closed")
    return problems


TOP_LEVEL_RE = re.compile(
    r"^(?:async\s+)?(?:function\s*\*?\s*|const\s+|let\s+|class\s+)([A-Za-z_$][\w$]*)")


def shared_names(paths: list[Path]) -> list[str]:
    """A name declared at the top of two scripts on the same page.

    The page loads its scripts one after another into one scope. A `const`,
    `let` or `class` that a second script declares again is a SyntaxError in
    that second script, and the browser then drops the whole file: every
    function in it is undefined, and the page fails somewhere unrelated.
    """
    problems: list[str] = []
    seen: dict[str, tuple[str, int, str]] = {}
    for path in paths:
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            m = TOP_LEVEL_RE.match(line)          # column 0 only: top level
            if not m:
                continue
            name, kind = m.group(1), line.split()[0]
            if name in seen and seen[name][0] != path.name:
                first_file, first_line, first_kind = seen[name]
                if "function" in (kind, first_kind) and kind == first_kind:
                    continue                      # two functions: the later one wins, legally
                problems.append(
                    f"{path.name}:{i}: {name!r} is already declared in {first_file}:{first_line} "
                    f"-- {path.name} will not parse"
                )
            seen.setdefault(name, (path.name, i, kind))
    return problems


def main() -> int:
    targets = [Path(a) for a in sys.argv[1:]] or sorted((ROOT / "web").glob("*.js"))
    if not targets:
        print("no web/*.js found")
        return 1

    failed = False
    for problem in shared_names(targets):
        failed = True
        print(f"  FAIL {problem}")
    for path in targets:
        problems = check(path)
        if problems:
            failed = True
            for p in problems:
                print(f"  FAIL {p}")
        else:
            print(f"  ok   {path.name} ({len(path.read_text(encoding='utf-8').splitlines())} lines)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
