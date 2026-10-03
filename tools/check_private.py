"""Refuse to commit anything personal.

The repository holds the program and nothing else (see server/paths.py). This
is the check that keeps it that way: run as a git pre-commit hook, it looks at
every file being committed and stops the commit if one of them

  * is a document rather than program: a PDF, a spreadsheet, an archive, an
    image outside the page's own assets;
  * sits in a folder where returns used to live (source_data/, data/), or is
    a profile list or a looked-up rate file;
  * contains a PAN that is not one of the specimen PANs used in fixtures;
  * contains anything that identifies a return on this machine: the name,
    PAN, date of birth, e-mail, mobile or bank account numbers of any return in
    the Flow home. Those are read from the home each time, never written into
    the repository, so the check knows exactly what is private here without
    holding a copy of it.

    python tools/check_private.py            check the files staged for commit
    python tools/check_private.py --all      check every file the repository would publish
    python tools/check_private.py --install  install it as this clone's pre-commit hook

What it finds is printed masked, so the warning does not itself leak.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DOCUMENT_SUFFIXES = {".pdf", ".xlsx", ".xls", ".xlsm", ".csv", ".zip", ".7z", ".rar", ".docx", ".doc",
                     ".jpg", ".jpeg", ".png", ".heic", ".tif", ".tiff", ".json.bak", ".eml", ".msg"}
# The page's typefaces and icon are program, not documents.
ALLOWED_BINARY_DIRS = ("web/fonts/",)
FORBIDDEN_PREFIXES = ("source_data/", "data/", ".derived/", ".agent/")
FORBIDDEN_FILES = {"config/profiles.json", "config/fx_rates.json", "flow.local.json"}

PAN_RE = re.compile(r"\b[A-Z]{3}[ABCFGHJLPT][A-Z][0-9]{4}[A-Z]\b")
# Specimens: the form's own example, and the invented ones the fixtures use.
SPECIMEN_PANS = {"AAAAA9999A", "ABCDE1234F", "AAATA0000A"}


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def files_to_check(all_files: bool) -> list[str]:
    if all_files:
        listed = _git("ls-files") + _git("ls-files", "--others", "--exclude-standard")
    else:
        listed = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR")
    return sorted({line.strip() for line in listed.splitlines() if line.strip()})


def mask(text: str) -> str:
    text = str(text)
    return text[:2] + "*" * max(1, len(text) - 4) + text[-2:] if len(text) > 4 else "*" * len(text)


def private_terms() -> list[tuple[str, str]]:
    """(what, value) for everything that identifies a return on this machine."""
    try:
        from server import paths
        home = paths.home()
        store = json.loads((home / "profiles.json").read_text("utf-8"))
    except Exception:  # noqa: BLE001 -- no home yet means nothing private to protect
        return []
    terms: list[tuple[str, str]] = []

    def add(what: str, value, minimum: int = 4) -> None:
        value = str(value or "").strip()
        if len(value) >= minimum and value.upper() not in {"DEFAULT", "RETURN", "PROFILE"}:
            terms.append((what, value))

    for profile in store.get("profiles", []):
        add("a return's name", profile.get("name"), 5)
        add("a PAN", profile.get("pan"))
        dob = str((profile.get("settings") or {}).get("dob") or "")
        digits = re.sub(r"\D", "", dob)
        if len(digits) == 8:
            add("a date of birth", dob)
            y, m, d = (digits[:4], digits[4:6], digits[6:]) if re.match(r"^\d{4}", dob) else (digits[4:], digits[2:4], digits[:2])
            for form in (d + m + y, f"{d}/{m}/{y}", f"{d}-{m}-{y}", f"{d}.{m}.{y}"):
                add("a date of birth", form)
        # What was read about the person: kept with the return, outside the repo.
        try:
            general = json.loads((paths.resolve_dir(profile.get("data_dir", "")) / "resolved" / "general.json").read_text("utf-8"))
        except Exception:  # noqa: BLE001
            general = {}
        data = general.get("data") or {}
        who = data.get("assessee") or {}
        add("a name", who.get("name"), 5)
        for part in str(who.get("name") or "").split():
            add("a name", part, 5)
        add("an e-mail address", who.get("email"))
        add("a mobile number", re.sub(r"\D", "", str(who.get("mobile") or "")), 8)
        for account in data.get("bank_accounts") or []:
            add("a bank account number", account.get("account_number"), 6)
    # The copyright holder named in LICENSE is public by choice, so that name
    # (and only a name: never a PAN, date or number) may appear.
    try:
        holder = re.search(r"Copyright \(c\) \d{4}(?:-\d{4})? (.+)", (ROOT / "LICENSE").read_text("utf-8"))
    except OSError:
        holder = None
    public = {w.lower() for w in holder.group(1).split()} | {holder.group(1).strip().lower()} if holder else set()
    terms = [(what, v) for what, v in terms if not ("name" in what and v.lower() in public)]
    # Longest first, so a full name is reported rather than one part of it.
    return sorted(set(terms), key=lambda t: -len(t[1]))


def check(path: str, terms: list[tuple[str, str]]) -> list[str]:
    problems = []
    lower = path.lower()
    if lower in FORBIDDEN_FILES or any(lower.startswith(p) for p in FORBIDDEN_PREFIXES):
        return [f"{path}: is where personal files are kept, never in the repository"]
    if "input-docs/" in lower or "/results/" in lower:
        return [f"{path}: looks like a return's documents or results folder"]
    if any(lower.endswith(s) for s in DOCUMENT_SUFFIXES) and not lower.startswith(ALLOWED_BINARY_DIRS):
        return [f"{path}: is a document file; the repository holds no documents"]
    full = ROOT / path
    try:
        text = full.read_text("utf-8")
    except (OSError, UnicodeDecodeError):
        return []                       # a binary program asset, already allowed above
    for pan in sorted(set(PAN_RE.findall(text)) - SPECIMEN_PANS):
        problems.append(f"{path}: contains a PAN ({mask(pan)})")
    folded = text.lower()
    for what, value in terms:
        if what == "a PAN" and value.upper() in text:
            continue                    # already reported by the pattern above
        if value.lower() in folded:
            problems.append(f"{path}: contains {what} ({mask(value)})")
    return problems


def install() -> int:
    hook = ROOT / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\n# Installed by tools/check_private.py: nothing personal is committed.\n"
                    "exec python tools/check_private.py\n", "utf-8", newline="\n")
    try:
        hook.chmod(0o755)
    except OSError:
        pass
    print(f"installed {hook}")
    return 0


def main() -> int:
    if "--install" in sys.argv[1:]:
        return install()
    files = files_to_check("--all" in sys.argv[1:])
    terms = private_terms()
    problems = list(dict.fromkeys(p for f in files for p in check(f, terms)))
    if problems:
        print("Stopped: these would put personal information in the repository.\n")
        for p in problems:
            print("  " + p)
        print("\nRemove it, or unstage the file (git restore --staged <file>), and commit again.")
        return 1
    print(f"ok   {len(files)} file(s) checked; nothing personal found "
          f"({len(terms)} private value(s) from this machine's returns checked for)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
