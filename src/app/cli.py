"""Command line: run the app, sync data, inspect the cache."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import threading
import time
import webbrowser

from app import __version__
from app.config import Settings
from app.errors import AppError
from app.leagues import LEAGUES, current_season


def _apply_env(args: argparse.Namespace) -> None:
    if getattr(args, "demo", False):
        os.environ["PREM_DEMO"] = "1"
    if getattr(args, "offline", False):
        os.environ["PREM_OFFLINE"] = "1"
    if getattr(args, "data_dir", None):
        os.environ["PREM_DATA_DIR"] = args.data_dir
    if getattr(args, "today", None):
        os.environ["PREM_TODAY"] = args.today


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    _apply_env(args)
    settings = Settings.from_env()
    url = f"http://{args.host}:{args.port}/"
    mode = "DEMO data (synthetic)" if settings.demo else "offline cache" if settings.offline else "Understat (cached locally)"
    print(f"\n  Prem Lab {__version__}\n  {url}\n  data: {mode}\n  cache: {settings.db_path}\n  Ctrl+C to stop\n")
    if not args.no_open:
        threading.Thread(target=lambda: (time.sleep(0.8), webbrowser.open(url)), daemon=True).start()
    uvicorn.run("app.api:app", host=args.host, port=args.port, reload=args.reload, log_level="warning")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    _apply_env(args)
    from app.workbench import Workbench

    leagues = [l.strip() for l in args.leagues.split(",") if l.strip()]
    seasons = [int(s) for s in args.seasons.split(",") if s.strip()] if args.seasons else [current_season()]

    async def run() -> int:
        wb = Workbench()
        try:
            job = wb.start_sync(leagues, seasons, force=args.force)
            seen = 0
            while True:
                state = wb.jobs.get(job["id"])
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


def cmd_clear(args: argparse.Namespace) -> int:
    _apply_env(args)
    from app.data.store import Store

    settings = Settings.from_env()
    if not settings.db_path.exists():
        print("Nothing to clear.")
        return 0
    if not args.yes:
        print(f"This deletes cached match and player data at {settings.db_path} (your shortlist is kept). Re-run with --yes to confirm.")
        return 1
    store = Store(settings.db_path)
    store.clear()
    store.close()
    print("Cache cleared (shortlist kept).")
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

    status = sub.add_parser("status", help="show what is cached")
    common(status)
    status.set_defaults(func=cmd_status)

    clear = sub.add_parser("clear", help="delete cached data")
    common(clear)
    clear.add_argument("--yes", action="store_true")
    clear.set_defaults(func=cmd_clear)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        args = parser.parse_args(["serve", *(argv or [])])
    return args.func(args)


def serve_main() -> None:
    raise SystemExit(main(["serve"]))


if __name__ == "__main__":
    raise SystemExit(main())
