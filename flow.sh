#!/bin/sh
# Start Flow ITR and open it in the browser. Needs Python 3.10 or later; nothing to install.
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  exec python3 -m server "$@"
elif command -v python >/dev/null 2>&1; then
  exec python -m server "$@"
fi
echo "Python was not found. Install Python 3.10 or later and run this again." >&2
exit 1
