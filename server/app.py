"""The local agent: a static file server for web/ plus the API the page calls.

Binds 127.0.0.1 and nothing else. A token is minted at startup and injected
into index.html; every API call must present it, and the Origin header is
checked on writes. That is enough to stop a page open in another browser tab
from quietly driving your tax return.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import fxlookup
from . import reconcile as reconciler
from . import classify, excerpt, merge, notes, paths, profiles, runner, sources
from . import engines as engine_registry

def _token() -> str:
    """Stable across restarts.

    A token minted per startup means every restart silently invalidates the
    page you already have open, and the symptom -- "bad or missing token" --
    looks like a bug in whatever you just clicked. It lives with this machine's
    working files in the Flow home, outside the repository.
    """
    store = paths.state_dir() / "token"
    try:
        existing = store.read_text("utf-8").strip()
        if len(existing) >= 24:
            return existing
    except OSError:
        pass
    fresh = secrets.token_urlsafe(24)
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(fresh, encoding="utf-8")
    return fresh


TOKEN = _token()
HOST, PORT = "127.0.0.1", 8787
ORIGIN = f"http://{HOST}:{PORT}"


def _collect(ay: str):
    """Every resolved schedule, keyed by tab id, plus the tabs still empty."""
    docs, missing = {}, []
    for tab in paths.load_tabs()["tabs"]:
        if tab["kind"] != "extract":
            continue
        doc = paths.read_json(paths.resolved(ay, tab["id"]))
        if doc:
            docs[tab["id"]] = doc
        else:
            missing.append(tab["id"])
    return docs, missing


class Activity:
    """What is running right now, so parallel work stays safe.

    Different schedules extract in parallel: they read their own documents and
    write their own files. What is refused is the work that would collide --
    the same schedule twice, re-routing documents while extractions read the
    routing, and switching profile while a run will write into "the active
    profile" when it finishes.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.running: set[str] = set()
        self.classifying = False

    def start_run(self, tab_id: str) -> str | None:
        with self._lock:
            if self.classifying:
                return "documents are being re-routed; wait for that to finish"
            if tab_id in self.running:
                return f"{tab_id} is already being extracted"
            self.running.add(tab_id)
            return None

    def end_run(self, tab_id: str) -> None:
        with self._lock:
            self.running.discard(tab_id)

    def start_classify(self) -> str | None:
        with self._lock:
            if self.classifying:
                return "documents are already being re-routed"
            if self.running:
                return ("wait for these extractions to finish before re-routing: "
                        + ", ".join(sorted(self.running)))
            self.classifying = True
            return None

    def end_classify(self) -> None:
        with self._lock:
            self.classifying = False

    def busy(self) -> str | None:
        with self._lock:
            if self.classifying:
                return "documents are being re-routed"
            if self.running:
                return "extraction in progress: " + ", ".join(sorted(self.running))
            return None

    def snapshot(self) -> dict:
        with self._lock:
            return {"running": sorted(self.running), "classifying": self.classifying}


ACTIVITY = Activity()


def page_version() -> str:
    """A fingerprint of the page's own files.

    A tab left open keeps running the script it loaded, however often the
    server restarts, so a change can look as if it did nothing. The page
    compares this with the value it started with and offers a reload."""
    h = hashlib.sha256()
    # Every file the page is made of, found rather than listed: a script added
    # later and left off a list here would change the page without changing
    # this, which is the one case the check exists for.
    for path in sorted(paths.WEB.glob("*")):
        # A leading underscore marks a file that is not part of the page: the
        # test harness tools/probe_page.py puts there while it runs.
        if path.suffix.lower() not in (".html", ".js", ".css") or path.name.startswith("_"):
            continue
        try:
            h.update(path.name.encode())
            h.update(path.read_bytes())
        except OSError:
            pass
    return h.hexdigest()[:12]


# Windows reads a file's type from the registry, where .js is sometimes
# text/plain and .woff2 is usually missing. A script served as text is refused
# by the browser, so the types the page depends on are stated here.
CONTENT_TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".json": "application/json; charset=utf-8",
    ".pdf": "application/pdf",
    ".txt": "text/plain; charset=utf-8",
    ".csv": "text/plain; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def content_type(path) -> str:
    return (CONTENT_TYPES.get(path.suffix.lower())
            or mimetypes.guess_type(str(path))[0] or "application/octet-stream")


def _rates_needed(summary: dict) -> list[dict]:
    """Every (currency, date) any schedule still lacks a rate for.

    Foreign amounts turn up in more than capital gains -- a dividend from a
    foreign company is converted under the same rule, on its own date -- so
    every schedule that reports what it is missing is collected here."""
    seen = {}

    def take(entries):
        for n in entries or []:
            if n.get("date"):
                seen[(n["currency"], n["date"])] = {"currency": n["currency"], "date": n["date"]}

    for regime in (summary.get("regimes") or {}).values():
        take((regime.get("capital_gains") or {}).get("rates_needed"))
        take((regime.get("foreign_assets") or {}).get("rates_needed"))
        for head in (regime.get("heads") or {}).values():
            if isinstance(head, dict):
                take((head.get("form") or {}).get("rates_needed"))
    return list(seen.values())
SUMMARY_LOCK = threading.Lock()


def compute_summary(ay: str) -> dict:
    from engine import compute

    # Serialised: two runs finishing together would otherwise each compute
    # from a different mix of old and new schedules and race to write.
    with SUMMARY_LOCK:
        docs, missing = _collect(ay)
        summary = compute.summarise(ay, docs, missing, profiles.settings_for())
        paths.write_json(paths.data_root(ay) / "resolved" / "summary.json", summary)

        # A derived schedule is a document like any other: written where the
        # extracted ones are written, so its tab, a reconciliation and a future
        # run all read it the same way instead of digging inside the summary.
        chosen = (summary.get("regimes") or {}).get(summary.get("recommended_regime")) or {}
        if chosen.get("business"):
            paths.write_json(paths.resolved(ay, "business_computation"), {
                "schema_version": "1.0.0", "ay": ay, "schedule": "business_computation",
                "status": "computed", "derived_from": ["books", "depreciation"],
                "generated_at": summary.get("computed_at"),
                "data": chosen["business"],
            })
            schedule_dep = chosen["business"].get("depreciation_schedule")
            if schedule_dep:
                paths.write_json(paths.resolved(ay, "depreciation"), {
                    "schema_version": "1.0.0", "ay": ay, "schedule": "depreciation",
                    "status": "computed", "derived_from": ["books"],
                    "generated_at": summary.get("computed_at"),
                    "data": schedule_dep,
                })

        # Schedule 112A is the section 112A rows of the capital gains ledger in
        # that schedule's own columns: written like the other derived schedules.
        if chosen.get("schedule_112a") is not None:
            paths.write_json(paths.resolved(ay, "scrip_112a"), {
                "schema_version": "1.0.0", "ay": ay, "schedule": "scrip_112a",
                "status": "computed", "derived_from": ["capital_gains"],
                "generated_at": summary.get("computed_at"),
                "data": chosen["schedule_112a"],
            })

        # A comparison with the department's record is arithmetic between what
        # was reported and what this return computes. The second half has just
        # been recomputed, so the arithmetic is done again: a verdict must
        # never be left standing on a figure that has since moved.
        reconciler.refresh_all(ay)
        # The workbook follows the figures, when the profile asks for that.
        from . import export
        export.after_compute(ay)
        return summary


class Server(ThreadingHTTPServer):
    # Python defaults this to True. On Windows SO_REUSEADDR lets a SECOND
    # process bind a port the first one is still listening on, and the OS then
    # hands connections to whichever it likes. The symptom is brutal: you
    # restart to pick up a code change, the old process keeps serving, and you
    # debug a fix that is already on disk. Fail to start instead.
    allow_reuse_address = False


class Handler(BaseHTTPRequestHandler):
    server_version = "itr-agent/0.1"

    # ---- plumbing -------------------------------------------------------
    def log_message(self, fmt, *args):
        # send_error() calls this with an int status as args[0], so this cannot
        # assume a string. Errors are always worth logging.
        first = args[0] if args else ""
        if not isinstance(first, str) or "/api/" in first:
            # A dead stderr must never take a request down with it. When the
            # server is started from a shell that later goes away, this write
            # is the first thing to fail -- and because it happens inside
            # send_response, before any byte reaches the client, the browser
            # sees "Failed to fetch" on every API call while static files
            # carry on serving. That is a very confusing way to lose a page.
            try:
                super().log_message(fmt, *args)
            except (OSError, ValueError):
                pass

    def _json(self, payload, code=200):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorised(self) -> bool:
        if self.headers.get("X-ITR-Token") == TOKEN:
            return True
        self._json({"error": "bad or missing token"}, 403)
        return False

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        # localhost and 127.0.0.1 are the same server but different origins,
        # and people type either one.
        if origin in (None, ORIGIN, f"http://localhost:{PORT}"):
            return True
        self._json({"error": f"origin {origin} not allowed"}, 403)
        return False

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    # ---- routing --------------------------------------------------------
    def do_GET(self):
        url = urlparse(self.path)
        if url.path.startswith("/api/"):
            if not self._authorised():
                return
            return self._api_get(url)
        return self._static(url.path)

    def do_POST(self):
        url = urlparse(self.path)
        if not url.path.startswith("/api/"):
            return self._json({"error": "not found"}, 404)
        if not self._authorised() or not self._origin_ok():
            return
        try:
            if url.path == "/api/run":
                return self._run()
            if url.path == "/api/profiles":
                return self._profiles()
            if url.path == "/api/classify":
                return self._classify()
            if url.path == "/api/assign":
                body = self._body()
                entry = classify.assign(body.get("ay") or self._ay(), body["path"],
                                        body["tabs"], body.get("why", ""))
                return self._json({"assigned": entry})
            if url.path == "/api/override":
                return self._override()
            if url.path == "/api/reconcile":
                return self._reconcile()
            if url.path == "/api/fx/lookup":
                return self._fx_lookup()
            if url.path == "/api/fx":
                from engine import fx
                body = self._body()
                saved = fx.save_rate(body.get("currency"), body.get("date"), body.get("rate"))
                return self._json({"saved": saved,
                                   "summary": compute_summary(body.get("ay") or self._ay())})
            if url.path == "/api/compute":
                body = self._body()
                return self._json(compute_summary(body.get("ay") or self._ay()))
            if url.path == "/api/open-folder":
                # Opens the active return's documents folder in the file
                # manager, so a download can be dropped straight into it. No
                # path is taken from the request: only that one folder opens.
                import os
                import subprocess
                import sys
                folder = paths.source_root(self._ay())
                folder.mkdir(parents=True, exist_ok=True)
                if sys.platform.startswith("win"):
                    os.startfile(str(folder))  # noqa: S606
                else:
                    subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(folder)])
                return self._json({"opened": str(folder)})
            if url.path == "/api/export":
                from . import export
                body = self._body()
                result = export.write(body.get("ay") or self._ay())
                return self._json(result, 409 if result.get("error") else 200)
            if url.path == "/api/decisions":
                body = self._body()
                ay = body.get("ay") or self._ay()
                try:
                    if body.get("action") == "reopen":
                        notes.reopen(ay, body.get("id", ""), body.get("reason", ""))
                    else:
                        notes.settle(ay, body.get("item") or {}, body.get("choice", ""),
                                     body.get("reason", ""))
                except ValueError as exc:
                    return self._json({"error": str(exc)}, 400)
                return self._json({"decisions": notes.load_decisions(ay)})
            if url.path == "/api/handoff":
                body = self._body()
                ay = body.get("ay") or self._ay()
                marks = notes.mark_entered(ay, body.get("rows") or [],
                                           bool(body.get("entered", True)))
                return self._json({"entered": marks})
        except Exception as exc:  # noqa: BLE001 - surfaced to the page
            return self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)
        return self._json({"error": "not found"}, 404)

    def _ay(self) -> str:
        """The active profile's year. Everything the page does is scoped to it."""
        return profiles.active_ay()

    def _profiles(self):
        """One endpoint, an explicit action, because these are CRUD verbs and
        guessing intent from which keys are present ages badly."""
        body = self._body()
        action = body.get("action", "list")
        # A run writes to "the active profile's data folder", looked up when it
        # finishes. Changing which profile that is, or where its folders are,
        # mid-run would put one person's results in another's return.
        redirects = (action in ("activate", "move", "delete")
                     or (action == "update" and any(
                         k in (body.get("patch") or {}) for k in ("source_dir", "data_dir", "fy"))))
        busy = ACTIVITY.busy() if redirects else None
        if busy:
            return self._json({"error": f"not while work is running ({busy})"}, 409)
        try:
            if action == "create":
                # The folders typed on the form are passed through: a profile
                # can be made straight onto a synced or external folder.
                profiles.create(body.get("name", ""), ay=body.get("ay", ""), fy=body.get("fy", ""),
                                pan=body.get("pan", ""), settings=body.get("settings"),
                                source_dir=body.get("source_dir", ""),
                                data_dir=body.get("data_dir", ""))
            elif action == "update":
                profiles.update(body["id"], body.get("patch", {}))
            elif action == "move":
                profiles.move_dir(body["id"], body["field"], body["target"])
            elif action == "activate":
                profiles.set_active(body["id"])
            elif action == "delete":
                result = profiles.delete(body["id"])
                return self._json({"store": profiles.load_all(), **result})
            elif action != "list":
                return self._json({"error": f"unknown action {action!r}"}, 400)
        except ValueError as exc:
            # A refusal with a reason (a shared results folder, a name already
            # taken) is the person's to read, not a fault of the server.
            return self._json({"error": str(exc)}, 400)
        except OSError as exc:
            return self._json({"error": f"that folder could not be used: {exc.strerror or exc}"}, 400)

        ay = self._ay()
        if action in ("create", "update", "activate", "move"):
            compute_summary(ay)
        return self._json({"store": profiles.load_all(), "active": profiles.active()})

    # ---- API ------------------------------------------------------------
    def _api_get(self, url):
        q = parse_qs(url.query)
        ay = (q.get("ay") or [self._ay()])[0]

        if url.path == "/api/version":
            return self._json({"page_version": page_version()})

        if url.path == "/api/state":
            config = paths.load_tabs()
            out = []
            for tab in config["tabs"]:
                doc = paths.read_json(paths.resolved(ay, tab["id"]))
                if tab["id"] == "summary":
                    doc = paths.read_json(paths.data_root(ay) / "resolved" / "summary.json")
                # The page shows the documents themselves, not the glob
                # patterns that matched them: "9 documents from 3 sources"
                # tells you nothing about whether the right nine were read.
                from engine import measures as measure_set
                mapped = set(classify.paths_for_tab(ay, tab["id"]))
                files = sources.scan(ay, tab["id"])
                read_paths = {s_.get("path") for s_ in (doc or {}).get("sources", [])}
                documents = [{
                    "path": f["path"],
                    "name": f["path"].rsplit("/", 1)[-1],
                    "folder": f["path"].rsplit("/", 2)[-2] if "/" in f["path"] else "",
                    "bytes": f["bytes"],
                    "via": "classifier" if f["path"] in mapped else "tabs.json rule",
                    "read_last_run": f["path"] in read_paths,
                    "duplicates": f.get("duplicates", []),
                } for f in files]
                out.append({
                    **tab,
                    "document": doc,
                    "source_count": len(files),
                    "documents": documents,
                    "resolved_sources": sources.tab_specs(tab["id"]),
                    "archives": sources.archives(ay, tab["id"]),
                    # A schedule can be reconciled once it has named figures to
                    # compare against; the last comparison travels with the tab.
                    "reconcilable": bool(measure_set.BY_SCHEDULE.get(tab["id"])),
                    "reconciliation": paths.read_json(reconciler.stored(ay, tab["id"])),
                })
            # The figures once more, as sheets to copy from, with which rows
            # have already been entered -- and what a person has settled.
            from engine import handoff as handoff_engine
            by_id = {t["id"]: t["document"] for t in out}
            return self._json({
                "ay": ay,
                "tabs": out,
                "handoff": {"sheets": handoff_engine.build(by_id.get("summary"), by_id),
                            "entered": notes.load_entered(ay)},
                "decisions": notes.load_decisions(ay),
                "decision_choices": notes.CHOICES,
                # Where the usual documents come from and how to download
                # them: program configuration, the same for everyone.
                "document_sources": paths.read_json(paths.CONFIG / "document_sources.json", {}),
                "unassigned": sources.unassigned(ay),
                "document_map": classify.load_map(ay),
                "profiles": {**profiles.load_all(),
                             "profiles": [profiles.describe(p) for p in profiles.load_all()["profiles"]]},
                "active_profile": profiles.describe(profiles.active() or {}),
                # Where everything personal is kept on this machine, and any
                # synced cloud folder a profile could be pointed at.
                "home": {"path": str(paths.home()), "source": paths.home_source(),
                         "input_folder": paths.INPUT_FOLDER, "output_folder": paths.OUTPUT_FOLDER,
                         "cloud": paths.cloud_roots()},
                "export": __import__("server.export", fromlist=["status"]).status(ay),
                "profile_fields": profiles.describe_fields(),
                "fy": (profiles.active() or {}).get("fy", ""),
                "engines": engine_registry.describe(),
                "activity": ACTIVITY.snapshot(),
                "page_version": page_version(),
                "default_engine": config.get("default_engine", "claude"),
                # The engine the active profile reads with, after its own
                # choice and what is installed have been taken into account.
                "engine": profiles.engine_for(),
            })

        if url.path == "/api/schema":
            # The UI lays a schedule out from its schema, so the ITR field
            # structure is defined in one place and rendered from it.
            from . import jsonschema_lite as jsl

            tab_id = q["tab"][0]
            try:
                return self._json(jsl.compose(tab_id))
            except FileNotFoundError:
                return self._json({"error": f"no schema for {tab_id}"}, 404)

        if url.path == "/api/excerpt":
            # The printed line behind a figure, from the same text the engine
            # read. Read-only, and it never follows the citation as a path.
            return self._json(excerpt.find(
                ay, (q.get("cite") or [""])[0], (q.get("amount") or [None])[0],
                (q.get("source") or [""])[0]))

        if url.path == "/api/file":
            # One of this return's own documents, for opening beside a figure.
            target = excerpt.original(ay, (q.get("path") or [""])[0])
            if target is None:
                return self._json({"error": "that is not one of this return's documents"}, 404)
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type(target))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if url.path == "/api/sources":
            tab_id = q["tab"][0]
            files = sources.scan(ay, tab_id)
            return self._json({
                "tab": tab_id,
                "files": [{k: f[k] for k in ("path", "sha256", "bytes")} for f in files],
                "fingerprint": sources.fingerprint(files, runner.prompt_version(tab_id),
                                                   paths.load_tabs().get("default_engine", "claude")),
            })

        return self._json({"error": "not found"}, 404)

    def _run(self):
        """Streams newline-delimited JSON events while the run proceeds."""
        body = self._body()
        ay = body.get("ay") or self._ay()
        refused = ACTIVITY.start_run(body.get("tab", ""))
        if refused:
            return self._json({"error": refused}, 409)
        try:
            self._run_claimed(body, ay)
        finally:
            ACTIVITY.end_run(body.get("tab", ""))

    def _run_claimed(self, body: dict, ay: str):

        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        lock = threading.Lock()

        def emit(event):
            with lock:
                try:
                    self.wfile.write((json.dumps(event) + "\n").encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionAbortedError):
                    pass  # the page navigated away mid-run; the run still finishes

        try:
            result = runner.run(
                ay, body["tab"],
                engine_name=body.get("engine", "mock"),
                force=bool(body.get("force")),
                on_event=emit,
            )
            # Derived tabs depend on extracted ones, so a successful run
            # invalidates the summary. Recompute rather than let it go stale.
            if result["status"] in ("ok", "cached"):
                summary = compute_summary(ay)
                # A foreign amount needs a published rate no document holds.
                # Look it up now, as part of the same run, rather than leave
                # the disposal out of every total until someone notices.
                needs = _rates_needed(summary)
                if needs:
                    try:
                        fxlookup.run(needs, body.get("engine", "claude"), emit)
                        compute_summary(ay)
                    except Exception as exc:  # noqa: BLE001 - the extraction itself succeeded
                        emit({"phase": "note",
                              "detail": f"rate lookup failed, enter the rate by hand: {type(exc).__name__}: {exc}"})
            emit({"phase": "done", "result": result})
        except Exception as exc:  # noqa: BLE001
            emit({"phase": "error", "detail": f"{type(exc).__name__}: {exc}"})

    def _reconcile(self):
        """Streams like a run: it reads the same documents, to a different end."""
        body = self._body()
        ay = body.get("ay") or self._ay()
        tab_id = body.get("tab", "")
        # Claimed like an extraction of the same tab, because it reads the same
        # documents and writes beside them; two at once would be wasteful.
        refused = ACTIVITY.start_run(f"{tab_id}:reconcile")
        if refused:
            return self._json({"error": refused}, 409)
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        lock = threading.Lock()

        def emit(event):
            with lock:
                try:
                    self.wfile.write((json.dumps(event) + "\n").encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionAbortedError):
                    pass

        try:
            document = reconciler.run(ay, tab_id, body.get("engine")
                                      or paths.load_tabs().get("default_engine", "claude"), emit)
            emit({"phase": "done", "result": {"status": "ok", "counts": document["counts"],
                                              "lines": len(document["lines"])}})
        except Exception as exc:  # noqa: BLE001
            emit({"phase": "error", "detail": f"{type(exc).__name__}: {exc}"})
        finally:
            ACTIVITY.end_run(f"{tab_id}:reconcile")

    def _fx_lookup(self):
        """Stream a rate lookup on its own, for the button on the rate card."""
        body = self._body()
        ay = body.get("ay") or self._ay()
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        lock = threading.Lock()

        def emit(event):
            with lock:
                try:
                    self.wfile.write((json.dumps(event) + "\n").encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionAbortedError):
                    pass

        try:
            needs = _rates_needed(compute_summary(ay))
            result = fxlookup.run(needs, body.get("engine", "claude"), emit)
            compute_summary(ay)
            emit({"phase": "done", "result": {"status": "ok", "saved": len(result["saved"]),
                                              "rejected": result["rejected"],
                                              "questions": result["questions"]}})
        except Exception as exc:  # noqa: BLE001
            emit({"phase": "error", "detail": f"{type(exc).__name__}: {exc}"})

    def _classify(self):
        """Streams like a run: it is one, just routing rather than extracting."""
        body = self._body()
        ay = body.get("ay") or self._ay()
        refused = ACTIVITY.start_classify()
        if refused:
            return self._json({"error": refused}, 409)
        try:
            self._classify_claimed(body, ay)
        finally:
            ACTIVITY.end_classify()

    def _classify_claimed(self, body: dict, ay: str):
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        lock = threading.Lock()

        def emit(event):
            with lock:
                try:
                    self.wfile.write((json.dumps(event) + "\n").encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionAbortedError):
                    pass

        try:
            result = classify.run(ay, engine_name=body.get("engine") or paths.load_tabs().get("default_engine", "claude"),
                                  on_event=emit)
            emit({"phase": "done", "result": {"status": "ok", "documents": len(result["documents"])}})
        except Exception as exc:  # noqa: BLE001
            emit({"phase": "error", "detail": f"{type(exc).__name__}: {exc}"})

    def _override(self):
        body = self._body()
        ay = body.get("ay") or self._ay()
        entry = merge.add_override(
            ay, body["tab"], body["pointer"], body["value"],
            body.get("reason", ""), body.get("by", "user"),
        )
        resolved = merge.resolve(ay, body["tab"])
        compute_summary(ay)
        return self._json({"override": entry, "document": resolved})

    # ---- static ---------------------------------------------------------
    def _static(self, path: str):
        if path in ("/", "/index.html"):
            html = (paths.WEB / "index.html").read_text("utf-8")
            html = html.replace("__ITR_TOKEN__", TOKEN)
            body = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        target = (paths.WEB / path.lstrip("/")).resolve()
        if not str(target).startswith(str(paths.WEB.resolve())) or not target.is_file():
            self.send_error(404)
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type(target))
        self.send_header("Content-Length", str(len(body)))
        # These files change constantly while the tool is being worked on, and
        # a browser caching app.js means you are looking at behaviour that no
        # longer exists on disk -- which reads as "the feature is broken", not
        # "your copy is stale". Never cache them. A typeface is the exception:
        # it does not change, and fetching it again on every page load makes
        # the text reflow each time.
        self.send_header("Cache-Control",
                         "public, max-age=604800, immutable" if target.suffix.lower() == ".woff2"
                         else "no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)


def serve(open_browser: bool = True):
    try:
        httpd = Server((HOST, PORT), Handler)
    except OSError as exc:
        raise SystemExit(
            f"Port {PORT} is already in use: {exc}\n"
            f"Another agent is still running. Stop it first — on Windows:\n"
            f'  netstat -ano | findstr ":{PORT}"   then   taskkill /F /PID <pid>'
        ) from exc
    url = f"{ORIGIN}/"
    print(f"Flow, an ITR-3 assistant, on {url}")
    # First run on a machine: this makes the home, a profile called DEFAULT
    # and its two folders, so there is somewhere to put documents.
    profile = profiles.describe(profiles.active() or {})
    print(f"  home      {paths.home()}   ({paths.home_source()})")
    if profile.get("name"):
        print(f"  return    {profile['name']}")
        print(f"  documents {profile['source_path']}")
        print(f"  results   {profile['data_path']}")
    found = False
    for e in engine_registry.describe():
        mark = "available" if e["available"] else "NOT FOUND"
        found = found or (e["available"] and e["id"] != "mock")
        print(f"  engine {e['id']:<8} {mark}")
    if not found:
        print("  No reading engine was found. Install the Claude Code or Codex command-line tool "
              "and sign in;\n  until then documents cannot be read, though everything else works.")
    print("Ctrl-C to stop.")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
