import argparse
import asyncio
import json
import shlex
from pathlib import Path

from app.endpoint_manifest import get_endpoint_manifest, get_endpoint_spec
from app.endpoint_runner import EndpointRunner
from app.question_answering import FootballQuestionAnswerer
from app.analytics_presets import ANALYTICS_TEMPLATES, MANCHESTER_UNITED_PRESETS
from app.visual_templates import VISUAL_TEMPLATE_REGISTRY, VISUAL_TEMPLATE_STATUS_ORDER
from app.visualization_renderer import render_visualization_asset, render_visualization_asset_with_png, slugify_filename


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
        prog="understat-cli",
        description="Terminal-first Understat JSON client.",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("endpoints", help="List available endpoints.")

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

    subparsers.add_parser(
        "visual-templates",
        help="List visual templates by polish status.",
    )

    ask_parser = subparsers.add_parser(
        "ask",
        help="Ask a football question and let the planner choose data endpoints.",
    )
    ask_parser.add_argument("question", nargs="+")

    render_ask_parser = subparsers.add_parser(
        "render-ask",
        help="Ask a football question and render the visualization payload to an SVG file.",
    )
    render_ask_parser.add_argument("question", nargs="+")
    render_ask_parser.add_argument("--output", default=None)
    render_ask_parser.add_argument("--width", type=int, default=1080)
    render_ask_parser.add_argument("--height", type=int, default=1350)
    render_ask_parser.add_argument("--png", action="store_true", help="Also export a PNG next to the SVG output.")
    render_ask_parser.add_argument("--density", type=int, default=144, help="PNG render density for SVG conversion.")

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


async def render_ask_command(question: str, output_path: str | None = None, width: int = 1080, height: int = 1350, export_png: bool = False, density: int = 144):
    async with FootballQuestionAnswerer() as answerer:
        result = await answerer.answer(question)

    visualization_payload = result["answer"]["social_ready"]["visualizations"]
    default_output = Path("outputs") / f"{slugify_filename(question)}.svg"
    final_output = output_path or str(default_output)
    if export_png:
        return render_visualization_asset_with_png(visualization_payload, final_output, width=width, height=height, density=density)
    render_visualization_asset(visualization_payload, final_output, width=width, height=height)
    return final_output


async def interactive_shell():
    print("Understat shell")
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
            print("- render-ask <plain english football question>")
            print("- templates")
            print("- manutd-presets")
            print("- visual-templates")
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

        if raw_input_line == "visual-templates":
            print(render_visual_templates())
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

        if raw_input_line.startswith("render-ask "):
            try:
                _, question = raw_input_line.split(" ", 1)
                output = await render_ask_command(question)
                print(f"Rendered: {output}")
            except Exception as exc:
                print(f"Error: {exc}")
            continue

        print("Unknown command. Type 'help' for guidance.")


def main():
    parser = build_parser()
    args = parser.parse_args()

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

    if args.command == "visual-templates":
        print(render_visual_templates())
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

    if args.command == "render-ask":
        question = " ".join(args.question)
        output = asyncio.run(
            render_ask_command(
                question,
                output_path=args.output,
                width=args.width,
                height=args.height,
                export_png=args.png,
                density=args.density,
            )
        )
        print(output)
        return

    parser.print_help()


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


def render_visual_templates():
    lines = ["Visual templates:"]
    for status in VISUAL_TEMPLATE_STATUS_ORDER:
        entries = [
            (name, metadata)
            for name, metadata in VISUAL_TEMPLATE_REGISTRY.items()
            if metadata["status"] == status
        ]
        if not entries:
            continue

        lines.append(f"{status.replace('_', ' ').title()}:")
        for name, metadata in entries:
            lines.append(f"- {name}: {metadata['description']}")
            lines.append(f"  Use for: {', '.join(metadata['use_for'])}")
            lines.append(f"  Note: {metadata['notes']}")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
