# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Command-line interface for a single bounded agent invocation."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from urllib.parse import urlsplit

from . import __version__
from .engine import LLMAgentEngine
from .errors import ConfigurationError, GuardrailError, InputValidationError, SamsarixAgentError
from .providers import OpenAICompatibleProvider


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="samsarix-agent",
        description="Run a small, bounded prompt agent over echo or an OpenAI-compatible endpoint.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="run one agent invocation")
    run.add_argument("prompt", nargs="?", help="prompt text; reads stdin when omitted")
    run.add_argument("--provider", choices=("echo", "openai"), default="echo")
    run.add_argument("--model", help="model identifier (required for --provider openai)")
    run.add_argument("--name", default="assistant", help="agent name")
    run.add_argument("--system-prompt", default="You are a concise, helpful assistant.")
    run.add_argument(
        "--base-url",
        default=os.getenv("SAMSARIX_LLM_BASE_URL", "https://api.openai.com/v1"),
        help="OpenAI-compatible API base URL",
    )
    run.add_argument(
        "--api-key-env",
        default="OPENAI_API_KEY",
        help="environment variable containing the API key; keys are never accepted as arguments",
    )
    run.add_argument("--timeout", type=float, default=30.0)
    run.add_argument("--max-retries", type=int, default=2)
    run.add_argument("--max-input-chars", type=int, default=20_000)
    run.add_argument("--max-output-tokens", type=int, default=1_024)
    run.add_argument("--max-response-chars", type=int, default=200_000)
    output = run.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="emit a JSON result envelope")
    output.add_argument(
        "--stream",
        action="store_true",
        help="stream text deltas as they arrive (not available with --json)",
    )
    output.add_argument(
        "--expect-json",
        action="store_true",
        help="require the model response to be strict JSON and emit that value",
    )
    return parser


def _read_prompt(argument: str | None, max_input_chars: int) -> str:
    if argument is not None:
        return argument
    if sys.stdin.isatty():
        raise InputValidationError("prompt is required when stdin is interactive")
    prompt = sys.stdin.read(max_input_chars + 1)
    if len(prompt) > max_input_chars:
        raise InputValidationError(
            f"stdin exceeds the configured {max_input_chars}-character limit"
        )
    return prompt


def _safe_text_output(value: object) -> str:
    text = str(value)
    return "".join(
        character if character in {"\n", "\t"} or character.isprintable() else "�"
        for character in text
    )


async def _run(args: argparse.Namespace) -> dict[str, object]:
    engine = LLMAgentEngine(
        default_provider=args.provider,
        max_input_chars=args.max_input_chars,
        max_output_tokens=args.max_output_tokens,
        max_response_chars=args.max_response_chars,
        max_requests_per_session=1,
    )
    prompt = _read_prompt(args.prompt, args.max_input_chars)
    if args.provider == "openai":
        if not args.model:
            raise ConfigurationError("--model is required for --provider openai")
        api_key = os.getenv(args.api_key_env)
        hostname = urlsplit(args.base_url).hostname or ""
        if hostname.lower() == "api.openai.com" and not api_key:
            raise ConfigurationError(f"{args.api_key_env} is required for api.openai.com")
        engine.register_provider(
            "openai",
            OpenAICompatibleProvider(
                api_key=api_key,
                base_url=args.base_url,
                timeout=args.timeout,
                max_retries=args.max_retries,
            ),
        )
    model = args.model or "echo"
    try:
        agent = engine.create_agent(
            name=args.name,
            model=model,
            system_prompt=args.system_prompt,
        )
        if args.stream:
            chunks: list[str] = []
            async for delta in agent.stream(prompt):
                chunks.append(delta)
                print(_safe_text_output(delta), end="", flush=True)
            print()
            content: object = "".join(chunks)
        elif args.expect_json:
            content = await agent.invoke_json(prompt)
        else:
            content = await agent.invoke(prompt)
        return {
            "content": content,
            "provider": agent.provider_name,
            "model": agent.model,
            "metrics": agent.get_metrics(),
        }
    finally:
        await engine.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("cancelled", file=sys.stderr)
        return 130
    except (ConfigurationError, InputValidationError) as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    except GuardrailError as exc:
        print(f"guardrail error: {exc}", file=sys.stderr)
        return 4
    except SamsarixAgentError as exc:
        print(f"provider error: {exc}", file=sys.stderr)
        return 3

    if args.stream:
        return 0
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    elif args.expect_json:
        print(json.dumps(result["content"], ensure_ascii=False, sort_keys=True))
    else:
        print(_safe_text_output(result["content"]))
    return 0
