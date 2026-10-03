"""python -m server  ->  start the local agent and open the page."""

import argparse
import sys

if sys.version_info < (3, 10):
    raise SystemExit(f"Flow needs Python 3.10 or later; this is {sys.version.split()[0]}.")

from .app import serve  # noqa: E402

if __name__ == "__main__":
    p = argparse.ArgumentParser(prog="python -m server")
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args()
    serve(open_browser=not args.no_browser)
