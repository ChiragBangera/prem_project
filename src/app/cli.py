"""Command line: run the app, sync data, inspect the cache."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import logging
import logging.handlers
import os
from pathlib import Path
import signal
import socket
import sys
import threading
import time
import webbrowser
from collections.abc import Callable

from app import __version__
from app.config import Settings
from app.errors import AppError
from app.leagues import LEAGUES, current_season

SHUTDOWN_GRACE = 15.0     # seconds a server that was asked to stop may take before the process exits anyway
OPEN_WAIT = 30.0          # seconds the browser is held back while the server is still starting


def _apply_env(args: argparse.Namespace) -> None:
    if getattr(args, "demo", False):
        os.environ["PREM_DEMO"] = "1"
    if getattr(args, "offline", False):
        os.environ["PREM_OFFLINE"] = "1"
    if getattr(args, "data_dir", None):
        os.environ["PREM_DATA_DIR"] = args.data_dir
    if getattr(args, "today", None):
        os.environ["PREM_TODAY"] = args.today


def configure_logging(data_dir: Path) -> Path | None:
    """Keep what the server says (what the updater did, what failed, any unexpected error with its traceback) in ``<data dir>/logs/server.log``.

    A server started in the background has no terminal, so a problem seen in the browser could otherwise not be traced. The file is rotated
    (2 MB, three copies); if it cannot be written the server simply carries on without it.
    """
    try:
        folder = data_dir / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(folder / "server.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    except OSError:
        return None
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    if root.level in (logging.NOTSET, logging.WARNING):
        root.setLevel(logging.INFO)
    root.addHandler(handler)
    return folder / "server.log"


def exit_after(grace: float, *, hard_exit: Callable[[int], object] = os._exit) -> threading.Timer:
    """Exit the process ``grace`` seconds from now, whatever is still running.

    A server that was asked to stop must stop. What can hold it up is a long job in a worker thread: nothing can interrupt one, and Python waits
    for them at exit. Everything the app writes is transactional and the updater picks up where it left off, so abandoning one loses nothing.
    """
    def fire() -> None:
        print(f"\n  Still busy {grace:.0f} s after the request to stop, so exiting now. Nothing is lost: the next start carries on.", file=sys.stderr, flush=True)
        logging.shutdown()
        hard_exit(0)

    timer = threading.Timer(grace, fire)
    timer.daemon = True
    timer.start()
    return timer


def _stoppable_server(config):
    """A uvicorn server that cannot hang on its way out: it starts the countdown of :func:`exit_after` as soon as it begins to stop."""
    import uvicorn

    class Server(uvicorn.Server):
        async def shutdown(self, *args, **kwargs) -> None:
            exit_after(SHUTDOWN_GRACE)
            await super().shutdown(*args, **kwargs)

    return Server(config)


def _utf8_output() -> None:
    """Write UTF-8 whatever the platform's default is. On Windows, output that is piped or redirected goes through a legacy code page that cannot hold
    every player's name (a "ć" would stop a command with an error), so switch to UTF-8 and never fail on a character."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):                     # not a stand-in such as the one a test captures into
            with contextlib.suppress(OSError, ValueError):
                stream.reconfigure(encoding="utf-8", errors="replace")


def _open_when_up(url: str, host: str, port: int) -> None:
    """Open the browser once the server accepts connections. A browser that arrives first shows an error page, and starting takes seconds on a slower machine."""
    probe = "127.0.0.1" if host in ("", "0.0.0.0") else host
    deadline = time.monotonic() + OPEN_WAIT
    while time.monotonic() < deadline:
        try:
            socket.create_connection((probe, port), timeout=1).close()
            break
        except OSError:                                              # not listening yet
            time.sleep(0.1)
    webbrowser.open(url)                                             # also when the wait ran out: the browser then says what the matter is


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    _apply_env(args)
    settings = Settings.from_env()
    url = f"http://{args.host}:{args.port}/"
    mode = "DEMO data (synthetic)" if settings.demo else "offline cache" if settings.offline else "Understat (cached locally)"
    log_file = configure_logging(settings.data_dir)
    print(f"\n  Prem Lab {__version__}\n  {url}\n  data: {mode}\n  cache: {settings.db_path}\n  log: {log_file or 'not written'}\n  Ctrl+C to stop\n")
    if not args.no_open:
        threading.Thread(target=_open_when_up, args=(url, args.host, args.port), daemon=True).start()
    options = {"host": args.host, "port": args.port, "log_level": "warning", "timeout_graceful_shutdown": 5}   # 5 s for requests under way when it is stopped
    if args.reload:                                                  # a development aid, run by uvicorn's own supervisor
        uvicorn.run("app.api:app", reload=True, **options)
        return 0
    server = _stoppable_server(uvicorn.Config("app.api:app", **options))
    try:
        server.run()
    except SystemExit:                                               # uvicorn exits with 3 when it cannot start; the usual reason is a taken port
        if server.started:
            raise
    except KeyboardInterrupt:                                        # a second Ctrl+C while it is stopping
        pass
    if not server.started:
        print(f"\n  Prem Lab could not start: port {args.port} is probably in use by another program (perhaps Prem Lab itself, already running).\n"
              f"  Open {url} to see, or choose another port:  prem serve --port {args.port + 1}\n", file=sys.stderr)
        return 3
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    _apply_env(args)
    from app.workbench import Workbench

    leagues = [name.strip() for name in args.leagues.split(",") if name.strip()]
    seasons = [int(s) for s in args.seasons.split(",") if s.strip()] if args.seasons else [current_season()]

    async def run() -> int:
        wb = Workbench()
        try:
            job = wb.data.start_sync(leagues, seasons, force=args.force)
            seen = 0
            while True:
                state = wb.jobs.get(job["id"])
                if state is None:        # cannot happen: the job was created a line ago, and finished jobs are kept
                    raise RuntimeError("the sync job was lost")
                for line in state.log[seen:]:
                    print(" ", line)
                seen = len(state.log)
                if state.state != "running":
                    break
                await asyncio.sleep(0.25)
            print(f"\n{state.done}/{state.total} fetched, {state.failed} failed in {state.to_dict()['elapsed']}s")
            return 0 if state.failed == 0 else 1
        finally:
            await wb.close()

    try:
        return asyncio.run(run())
    except (AppError, ValueError) as exc:
        print(f"error: {getattr(exc, 'message', exc)}", file=sys.stderr)
        return 2


def cmd_doctor(args: argparse.Namespace) -> int:
    _apply_env(args)
    from app.workbench import Workbench

    async def run() -> dict:
        wb = Workbench()
        try:
            return await wb.diagnostics.check()
        finally:
            await wb.close()

    result = asyncio.run(run())
    where = "demo world" if result["mode"]["demo"] else "Understat"
    print(f"Checking the data path ({where}):")
    for step in result["steps"]:
        mark = "ok  " if step["ok"] else "FAIL"
        print(f"  [{mark}] {step['name']:<24s} {step['detail']}  ({step['ms']} ms)")
        if step.get("hint") and not step["ok"]:
            print(f"         {step['hint']}")
    print("\nAll good." if result["ok"] else "\nSomething is wrong: see the failing step above.")
    return 0 if result["ok"] else 1


def cmd_status(args: argparse.Namespace) -> int:
    _apply_env(args)
    from app.data.store import Store

    settings = Settings.from_env()
    if not settings.db_path.exists():
        print(f"No cache yet at {settings.db_path}. Run `prem sync` (or `prem serve --demo`).")
        return 0
    store = Store(settings.db_path)
    stats = store.stats()
    print(f"Cache: {settings.db_path}  ({stats['total_items']} items, {stats['total_bytes'] / 1e6:.1f} MB)")
    for kind, info in stats["kinds"].items():
        print(f"  {kind:8s} {info['count']:5d} items  {info['bytes'] / 1e3:8.0f} KB")
    print("Leagues:")
    for key, fetched, complete in store.keys("league"):
        age_h = (time.time() - fetched) / 3600
        print(f"  {key:16s} {'final' if complete else 'live '}  fetched {age_h:6.1f} h ago")
    store.close()
    return 0


def _stop_like_ctrl_c(signum, frame) -> None:
    """The updater stops the event fetcher with SIGTERM: treat that as Ctrl+C, so the run saves its place and closes its browser instead of being cut off."""
    raise KeyboardInterrupt


def cmd_events_sync(args: argparse.Namespace) -> int:
    """Fetch event data (passes, duels, tackles) from WhoScored into the local store. Slow; safe to stop and resume."""
    _apply_env(args)
    from app.data.store import Store
    from app.events import ledger
    from app.events.fetch import FetchUnavailable, read_targets, sync_season
    from app.events.store import EventStore
    from app.sync.autosync import PREFS_KEY
    from app.sync.budget import Budget

    settings = Settings.from_env()
    seasons = [int(x) for x in args.seasons.split(",") if x.strip()] if args.seasons else [current_season()]
    store = Store(settings.db_path)
    events = EventStore(store)
    work = (settings.data_dir / "soccerdata").resolve()
    work.mkdir(parents=True, exist_ok=True)
    os.chdir(work)  # the browser tooling drops lock files in the working folder: keep them inside the data folder, not the project
    signal.signal(signal.SIGTERM, _stop_like_ctrl_c)
    run_started = time.time()
    only = {int(g) for g in str(args.game or "").split(",") if g.strip().isdigit()} or None
    budget = Budget(store, lambda: (store.kv_get(PREFS_KEY) or {}).get("limits") or {}) if args.budget else None

    def spent() -> None:
        if budget is not None:
            budget.spend("whoscored")

    try:
        if args.targets:   # the updater's matchday reads: these matches, now, at half time or full time
            targets = json.loads(args.targets)
            matchday = Budget(store)

            def read_one() -> None:
                matchday.spend("matchday")

            print(f"\n{args.league} {seasons[0]}: reading {len(targets)} match{'es' if len(targets) != 1 else ''} now")
            result = read_targets(events, args.league, seasons[0], targets, data_dir=settings.data_dir, browser=args.browser, headless=not args.visible,
                                  pause=args.pause, stop=lambda: ledger.stop_reason(store, run_started), on_fetched=read_one)
            print(f"{args.league} {seasons[0]}: {result['final']} at full time, {result['live']} still in play, {result['not_found']} not found, {result['failed']} failed.")
            return 0
        for season in seasons:
            print(f"\n{args.league} {season}: fetching event data from WhoScored (a match takes about 15 seconds; Ctrl+C is safe, run it again to carry on)")
            status = sync_season(events, args.league, season, data_dir=settings.data_dir, browser=args.browser, headless=not args.visible, limit=args.limit, pause=args.pause,
                                 only=only, stop=lambda: ledger.stop_reason(store, run_started),
                                 allowance=(lambda: budget.left("whoscored")) if budget else None, on_fetched=spent)
            print(f"{args.league} {season}: {len(events.match_ids(args.league, season))} matches stored ({status['done']} fetched now, {status['failed']} failed).")
    except FetchUnavailable as exc:
        print(f"\n{exc}")
        return 2
    finally:
        store.close()
    return 0


EVENT_KINDS = ("events", "ws_raw", "ws_silver", "ws_gold")  # "events" is the first version's summed rows; the rest are the layers that replaced it


def cmd_events_import(args: argparse.Namespace) -> int:
    """Store every event page the download cache holds that the app's own store lacks, then derive from it. Offline."""
    _apply_env(args)
    from app.data.store import Store
    from app.events import raw as R
    from app.events.store import EventStore

    settings = Settings.from_env()
    store = Store(settings.db_path)
    try:
        result = R.import_soccerdata_cache(store, settings.data_dir, log=print)
        print(f"{result['imported']} matches imported, {result['already']} already stored, {result['rejected']} unusable, {result['provisional']} read before full time (left to be read again), from {result['files']} cached pages.")
        rebuilt = EventStore(store).ensure_current(progress=lambda a, b: print(f"  derived {a} of {b}"))
        print(f"Derived layers: {rebuilt['rebuilt']} rebuilt, {rebuilt['skipped']} already current.")
        print(f"The download cache's copies can now be deleted to reclaim {R.reclaimable_bytes(store, settings.data_dir) / 1e6:.0f} MB (prem events reclaim --yes).")
    finally:
        store.close()
    return 0


def cmd_events_reclaim(args: argparse.Namespace) -> int:
    """Delete the download cache's copy of every event page that is safely in the app's own store."""
    _apply_env(args)
    from app.data.store import Store
    from app.events import raw as R

    settings = Settings.from_env()
    store = Store(settings.db_path)
    try:
        size = R.reclaimable_bytes(store, settings.data_dir)
        if not args.yes:
            print(f"This deletes {size / 1e6:.0f} MB of duplicate event pages from {settings.data_dir / 'soccerdata'} (the app's own store keeps every match). Re-run with --yes to confirm.")
            return 1
        freed = R.reclaim(store, settings.data_dir)
        print(f"Deleted {freed['deleted']} pages, freed {freed['bytes'] / 1e6:.0f} MB.")
    finally:
        store.close()
    return 0


def cmd_rebuild(args: argparse.Namespace) -> int:
    """Bring every derived event layer up to date with the current definitions, from the stored raw pages, with no network."""
    _apply_env(args)
    from app.data.store import Store
    from app.events.store import EventStore

    settings = Settings.from_env()
    store = Store(settings.db_path)
    try:
        events = EventStore(store)
        pending = events.pending_rebuild()
        print(f"{pending} matches need rebuilding." if pending else "Everything is up to date.")
        if pending:
            result = events.ensure_current(progress=lambda a, b: print(f"  {a} of {b}"))
            print(f"Rebuilt {result['rebuilt']}, {result['failed']} failed.")
    finally:
        store.close()
    return 0


def cmd_events_status(args: argparse.Namespace) -> int:
    _apply_env(args)
    from app.data.store import Store
    from app.events.store import EventStore

    settings = Settings.from_env()
    if not settings.db_path.exists():
        print("No data yet.")
        return 0
    store = Store(settings.db_path)
    events = EventStore(store)
    found = events.seasons()
    if not found:
        print("No event data yet. Fetch some with: uv run --extra events prem events sync --league EPL --seasons 2025")
    for league, season, n in found:
        status = events.status(league, season) or {}
        state = "running" if status.get("running") else "stalled" if status.get("stalled") else "idle"
        total = status.get("finished_matches")
        print(f"  {league} {season}: {n}{f' of {total}' if total else ''} matches stored ({state}{', last error: ' + status['last_error'] if status.get('last_error') else ''})")
    store.close()
    return 0


def cmd_events(args: argparse.Namespace) -> int:
    handler = {"sync": cmd_events_sync, "status": cmd_events_status, "import": cmd_events_import, "reclaim": cmd_events_reclaim}.get(getattr(args, "events_command", ""))
    if handler is None:
        print("Use `prem events sync` to fetch event data, `prem events status` to see what is stored, or `prem events import` to adopt pages already downloaded.")
        return 1
    return handler(args)


def cmd_clear(args: argparse.Namespace) -> int:
    _apply_env(args)
    from app.data.store import Store

    settings = Settings.from_env()
    if not settings.db_path.exists():
        print("Nothing to clear.")
        return 0
    keep = () if getattr(args, "events", False) else EVENT_KINDS  # hours of fetching: only deleted when asked for
    if not args.yes:
        kept = "" if not keep else " Event data is kept (add --events to delete it too)."
        print(f"This deletes cached match and player data at {settings.db_path} (your shortlist is kept).{kept} Re-run with --yes to confirm.")
        return 1
    store = Store(settings.db_path)
    store.clear(keep=keep)
    store.close()
    print("Cache cleared (shortlist kept" + ("; event data kept)." if keep else "; event data deleted too)."))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prem", description="Prem Lab: personal football analytics on Understat data.")
    parser.add_argument("--version", action="version", version=f"prem-lab {__version__}")
    sub = parser.add_subparsers(dest="command")

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--demo", action="store_true", help="use the synthetic demo world instead of Understat")
        p.add_argument("--offline", action="store_true", help="never touch the network; serve the cache")
        p.add_argument("--data-dir", help="where the cache lives (default: <repo>/.prem-data)")
        p.add_argument("--today", help="pretend today is YYYY-MM-DD (demo/testing)")

    serve = sub.add_parser("serve", help="run the web app")
    common(serve)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--no-open", action="store_true", help="do not open a browser")
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(func=cmd_serve)

    sync = sub.add_parser("sync", help="fetch league seasons into the local cache")
    common(sync)
    sync.add_argument("--leagues", default="EPL", help=f"comma-separated: {', '.join(LEAGUES)}")
    sync.add_argument("--seasons", default="", help="comma-separated start years (default: current season)")
    sync.add_argument("--force", action="store_true", help="refetch even finished seasons")
    sync.set_defaults(func=cmd_sync)

    doctor = sub.add_parser("doctor", help="check that Understat (and Wikidata) can be reached and read")
    common(doctor)
    doctor.set_defaults(func=cmd_doctor)

    status = sub.add_parser("status", help="show what is cached")
    common(status)
    status.set_defaults(func=cmd_status)

    clear = sub.add_parser("clear", help="delete cached data")
    common(clear)
    clear.add_argument("--yes", action="store_true")
    clear.add_argument("--events", action="store_true", help="also delete event data (it takes hours to fetch again)")
    clear.set_defaults(func=cmd_clear)

    events = sub.add_parser("events", help="optional event data (passes, duels, tackles) from WhoScored")
    events.set_defaults(func=cmd_events)
    esub = events.add_subparsers(dest="events_command")
    esync = esub.add_parser("sync", help="fetch event data into the local store (slow, resumable)")
    esync.add_argument("--data-dir", help="where the cache lives (default: <repo>/.prem-data)")
    esync.add_argument("--league", default="EPL", help=f"one of: {', '.join(LEAGUES)}")
    esync.add_argument("--seasons", default="", help="comma-separated start years (default: current season)")
    esync.add_argument("--limit", type=int, help="fetch at most this many matches (to try it out)")
    esync.add_argument("--pause", type=float, default=10.0, help="wait this to twice this many seconds between matches (default 10)")
    esync.add_argument("--game", help="only these WhoScored match ids, comma-separated (to try a failed match again)")
    esync.add_argument("--budget", action="store_true", help="stop at today's limit for WhoScored, as the background updater does")
    esync.add_argument("--targets", help=argparse.SUPPRESS)   # the updater's matchday reads, as JSON: [{"fixture", "kickoff", "home", "away", "moment"}]
    esync.add_argument("--browser", help="path to Chrome, Chromium or Brave (found automatically if omitted; Edge does not work)")
    esync.add_argument("--visible", action="store_true", help="show the browser window; can help if the site blocks the hidden one")
    estatus = esub.add_parser("status", help="show what event data is stored")
    estatus.add_argument("--data-dir", help="where the cache lives (default: <repo>/.prem-data)")
    eimport = esub.add_parser("import", help="store event pages the download cache already holds (offline) and derive from them")
    eimport.add_argument("--data-dir", help="where the cache lives (default: <repo>/.prem-data)")
    ereclaim = esub.add_parser("reclaim", help="delete the download cache's duplicate event pages (the store keeps every match)")
    ereclaim.add_argument("--data-dir", help="where the cache lives (default: <repo>/.prem-data)")
    ereclaim.add_argument("--yes", action="store_true")

    rebuild = sub.add_parser("rebuild", help="rebuild derived event data from the stored raw pages (offline)")
    common(rebuild)
    rebuild.set_defaults(func=cmd_rebuild)
    return parser


def main(argv: list[str] | None = None) -> int:
    _utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        args = parser.parse_args(["serve", *(argv or [])])
    return args.func(args)


def serve_main() -> None:
    raise SystemExit(main(["serve"]))


if __name__ == "__main__":
    raise SystemExit(main())
