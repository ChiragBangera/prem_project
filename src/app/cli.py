import argparse
import asyncio
import json
import shlex
import sys

from app.endpoint_manifest import get_endpoint_manifest, get_endpoint_spec
from app.endpoint_runner import EndpointRunner
from app.errors import AnalyticsError
from app.question_answering import FootballQuestionAnswerer
from app.analytics_presets import ANALYTICS_TEMPLATES, MANCHESTER_UNITED_PRESETS


def parse_param_value(raw_value: str):
    normalized = raw_value.strip()
    lowered = normalized.lower()

    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None

    try:
        return json.loads(normalized)
    except json.JSONDecodeError:
        pass

    if "," in normalized and not normalized.startswith(("http://", "https://")):
        return [parse_param_value(value) for value in normalized.split(",")]

    try:
        return int(normalized)
    except ValueError:
        pass

    try:
        return float(normalized)
    except ValueError:
        pass

    return normalized


def parse_key_value_pairs(pairs):
    params = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(
                f"Invalid parameter '{pair}'. Use key=value format."
            )

        key, value = pair.split("=", 1)
        params[key] = parse_param_value(value)

    return params


def format_json(data):
    return json.dumps(data, indent=2, ensure_ascii=False)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="prem-analytics",
        description="Explore Understat data and run football analytics questions.",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("endpoints", help="List available endpoints.")

    serve_parser = subparsers.add_parser(
        "serve",
        help="Start the Premier League Analytics web dashboard and API server.",
    )
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1).")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000).")
    serve_parser.add_argument("--no-open", action="store_true", help="Do not automatically open browser.")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload.")

    app_parser = subparsers.add_parser(
        "app",
        help="Alias for serve: start server and open the dashboard in browser.",
    )
    app_parser.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1).")
    app_parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000).")
    app_parser.add_argument("--no-open", action="store_true", help="Do not automatically open browser.")
    app_parser.add_argument("--reload", action="store_true", help="Enable auto-reload.")

    describe_parser = subparsers.add_parser(
        "describe",
        help="Show endpoint details.",
    )
    describe_parser.add_argument("endpoint_name")

    run_parser = subparsers.add_parser(
        "run",
        help="Run an endpoint using key=value parameters.",
    )
    run_parser.add_argument("endpoint_name")
    run_parser.add_argument("params", nargs="*")

    subparsers.add_parser(
        "shell",
        help="Open an interactive shell for exploring endpoints.",
    )

    subparsers.add_parser(
        "templates",
        help="List reusable analytics templates.",
    )

    subparsers.add_parser(
        "manutd-presets",
        help="List Manchester United-focused analytical preset questions.",
    )

    ask_parser = subparsers.add_parser(
        "ask",
        help="Ask a football question and let the planner choose data endpoints.",
    )
    ask_parser.add_argument("question", nargs="+")

    return parser


def render_endpoint_list():
    manifest = get_endpoint_manifest()
    lines = ["Available endpoints:"]
    for name in sorted(manifest):
        spec = manifest[name]
        lines.append(f"- {name} [{spec.category}]")
    return "\n".join(lines)


def render_endpoint_details(endpoint_name: str):
    spec = get_endpoint_spec(endpoint_name)
    lines = [
        f"Endpoint: {spec.name}",
        f"Category: {spec.category}",
        f"Method: {spec.method_name}",
        f"Description: {spec.description}",
        f"Required params: {', '.join(spec.required_params) or 'none'}",
        f"Optional params: {', '.join(spec.optional_params) or 'none'}",
    ]

    if spec.example:
        lines.append(f"Example: {spec.example}")

    return "\n".join(lines)


async def run_endpoint_command(endpoint_name: str, params):
    async with EndpointRunner() as runner:
        result = await runner.run(endpoint_name, **params)
        print(format_json(result))


async def interactive_shell():
    print("Premier League Analytics shell")
    print("Type 'help' for commands, 'exit' to leave.")

    while True:
        try:
            raw_input_line = input("understat> ").strip()
        except EOFError:
            print()
            break

        if not raw_input_line:
            continue

        if raw_input_line in {"exit", "quit"}:
            break

        if raw_input_line == "help":
            print("Commands:")
            print("- endpoints")
            print("- describe <endpoint_name>")
            print("- run <endpoint_name> key=value key=value")
            print("- ask <plain english football question>")
            print("- templates")
            print("- manutd-presets")
            print("- exit")
            continue

        if raw_input_line == "endpoints":
            print(render_endpoint_list())
            continue

        if raw_input_line == "templates":
            print(render_templates())
            continue

        if raw_input_line == "manutd-presets":
            print(render_manchester_united_presets())
            continue

        if raw_input_line.startswith("describe "):
            _, endpoint_name = raw_input_line.split(" ", 1)
            print(render_endpoint_details(endpoint_name.strip()))
            continue

        if raw_input_line.startswith("run "):
            try:
                parts = shlex.split(raw_input_line)
                _, endpoint_name, *param_pairs = parts
                params = parse_key_value_pairs(param_pairs)
                await run_endpoint_command(endpoint_name, params)
            except Exception as exc:
                print(f"Error: {exc}")
            continue

        if raw_input_line.startswith("ask "):
            try:
                _, question = raw_input_line.split(" ", 1)
                async with FootballQuestionAnswerer() as answerer:
                    result = await answerer.answer(question)
                    print(format_json(result))
            except Exception as exc:
                print(f"Error: {exc}")
            continue

        print("Unknown command. Type 'help' for guidance.")


def run_serve(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = True, reload: bool = False):
    import threading
    import time
    import webbrowser
    import uvicorn

    url = f"http://{host}:{port}/dashboard/"
    print(f"\n⚽ Premier League Analytics Lab")
    print(f"📡 API docs:  http://{host}:{port}/docs")
    print(f"📊 Dashboard: {url}")
    print(f"Press Ctrl+C to stop.\n")

    if open_browser:
        def _open():
            time.sleep(0.6)
            try:
                webbrowser.open(url)
            except Exception:
                pass

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run("app.api:app", host=host, port=port, reload=reload)


def serve_main():
    run_serve(host="127.0.0.1", port=8000, open_browser=True, reload=False)


def _main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command in ("serve", "app"):
        run_serve(
            host=args.host,
            port=args.port,
            open_browser=not args.no_open,
            reload=args.reload,
        )
        return

    if args.command is None or args.command == "shell":
        asyncio.run(interactive_shell())
        return

    if args.command == "endpoints":
        print(render_endpoint_list())
        return

    if args.command == "templates":
        print(render_templates())
        return

    if args.command == "manutd-presets":
        print(render_manchester_united_presets())
        return

    if args.command == "describe":
        print(render_endpoint_details(args.endpoint_name))
        return

    if args.command == "run":
        params = parse_key_value_pairs(args.params)
        asyncio.run(run_endpoint_command(args.endpoint_name, params))
        return

    if args.command == "ask":
        question = " ".join(args.question)

        async def _run():
            async with FootballQuestionAnswerer() as answerer:
                result = await answerer.answer(question)
                print(format_json(result))

        asyncio.run(_run())
        return

    parser.print_help()


def main():
    try:
        _main()
    except (AnalyticsError, KeyError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def render_templates():
    lines = ["Analytics templates:"]
    for name, payload in ANALYTICS_TEMPLATES.items():
        lines.append(f"- {name}: {payload['description']}")
    return "\n".join(lines)


def render_manchester_united_presets():
    lines = ["Manchester United presets:"]
    for preset in MANCHESTER_UNITED_PRESETS:
        lines.append(f"- {preset['name']}: {preset['question']}")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
