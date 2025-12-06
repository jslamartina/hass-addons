#!/usr/bin/env python3
"""Stream responses from Brave AI Grounding API to stdout.

Usage:
    brave-ai-grounding-cli "Your question here" [--research]
"""

import argparse
import asyncio
import json
import os
import signal
import sys
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import cast

import httpx

# Handle broken pipe gracefully (e.g., when output is piped to head)
_ = signal.signal(signal.SIGPIPE, signal.SIG_DFL)

type JsonObj = dict[str, object]
type ContentHandler = Callable[[str], Awaitable[None]]


def _parse_json_obj(text: str) -> JsonObj | None:
    parsed_obj: object
    try:
        parsed_obj = cast(object, json.loads(text))
    except json.JSONDecodeError:
        return None
    return cast(JsonObj, parsed_obj) if isinstance(parsed_obj, dict) else None


def get_api_key() -> str:
    """Get API key from .env file or environment."""
    # Try environment variable first
    api_key = os.environ.get("BRAVE_AI_GROUNDING_API_KEY")
    if api_key:
        return api_key

    # Try reading from .env file in package directory
    script_dir = Path(__file__).resolve().parent
    package_env = script_dir / ".env"
    if package_env.exists():
        try:
            with package_env.open() as env_file:
                for line in env_file:
                    stripped = line.strip()
                    if stripped.startswith("BRAVE_AI_GROUNDING_API_KEY="):
                        return stripped.split("=", 1)[1].strip()
        except Exception as exc:  # pragma: no cover - best-effort read
            _ = sys.stderr.write(f"Warning: failed reading {package_env}: {exc}\n")

    sys.exit(1)


def _build_payload(query: str, enable_research: bool, enable_citations: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "messages": [{"role": "user", "content": query}],
        "stream": True,
        "model": "brave",
        "enable_citations": enable_citations,
    }
    if enable_research:
        payload["enable_research"] = True
    return payload


def _extract_content(parsed: JsonObj) -> str | None:
    choices_obj: object = parsed.get("choices")
    choices_list: list[object] | None = cast(list[object], choices_obj) if isinstance(choices_obj, list) else None
    choices: list[JsonObj] | None = None
    if choices_list is not None:
        collected: list[JsonObj] = []
        for item in choices_list:
            if isinstance(item, dict):
                collected.append(cast(JsonObj, item))
        choices = collected
    if not choices:
        return None

    first_choice = choices[0]

    delta_obj = first_choice.get("delta", {})
    delta: JsonObj | None = cast(JsonObj, delta_obj) if isinstance(delta_obj, dict) else None
    if delta is None:
        return None

    content_obj = delta.get("content", "")
    content: str | None = content_obj if isinstance(content_obj, str) else None
    return content if content else None


async def _iter_content(response: httpx.Response, handle_content: ContentHandler) -> None:
    async for line in response.aiter_lines():
        if not line.startswith("data: "):
            continue
        data_str = line[6:]
        if data_str == "[DONE]":
            break
        parsed = _parse_json_obj(data_str)
        if parsed is None:
            continue

        content = _extract_content(parsed)
        if content:
            await handle_content(content)


async def _stream_chat(
    url: str,
    headers: dict[str, str],
    payload: dict[str, object],
    handle_content: ContentHandler,
) -> None:
    async with httpx.AsyncClient(timeout=300.0) as client:
        stream_ctx = cast(
            AbstractAsyncContextManager[httpx.Response],
            cast(
                object,
                client.stream(
                    "POST",
                    url,
                    json=payload,
                    headers=headers,
                ),
            ),
        )
        async with stream_ctx as response:
            response.raise_for_status()
            await _iter_content(response, handle_content)


def _print_footer(citations: list[dict[str, object]], usage_info: dict[str, object] | None) -> None:
    if citations:
        for idx, cite in enumerate(citations, 1):
            url = str(cite.get("url", "N/A"))
            _ = sys.stdout.write(f"\n[{idx}] {url}\n")
            snippet_val = cite.get("snippet")
            if isinstance(snippet_val, str):
                _ = sys.stdout.write(f"    {snippet_val[:200]}...\n")

    if usage_info:
        _ = sys.stdout.write("\n" + "=" * 60 + "\n")
        _ = sys.stdout.write("USAGE METRICS\n")
        _ = sys.stdout.write("=" * 60 + "\n")
        _ = sys.stdout.write(f"Requests: {usage_info.get('X-Request-Requests', 0)}\n")
        _ = sys.stdout.write(f"Queries: {usage_info.get('X-Request-Queries', 0)}\n")
        _ = sys.stdout.write(f"Tokens In: {usage_info.get('X-Request-Tokens-In', 0)}\n")
        _ = sys.stdout.write(f"Tokens Out: {usage_info.get('X-Request-Tokens-Out', 0)}\n")
        _ = sys.stdout.write(f"Total Cost: ${usage_info.get('X-Request-Total-Cost', 0):.4f}\n")
        _ = sys.stdout.write("=" * 60 + "\n")
        _ = sys.stdout.flush()


async def stream_brave_ai(
    query: str,
    enable_research: bool = False,
    enable_citations: bool = True,
) -> None:
    """Stream Brave AI Grounding response to stdout."""
    api_key = get_api_key()

    url = "https://api.search.brave.com/res/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = _build_payload(query, enable_research, enable_citations)

    citations: list[dict[str, object]] = []
    usage_info: dict[str, object] | None = None

    async def handle_content(content: str) -> None:
        nonlocal usage_info
        if content.startswith("<citation>"):
            citation_json = content.replace("<citation>", "").replace("</citation>", "")
            citation_data = _parse_json_obj(citation_json)
            if citation_data is not None:
                citations.append(citation_data)
            return

        if content.startswith("<usage>"):
            usage_json = content.replace("<usage>", "").replace("</usage>", "")
            loaded_usage = _parse_json_obj(usage_json)
            if loaded_usage is not None:
                usage_info = loaded_usage
            return

        _ = sys.stdout.write(content)
        _ = sys.stdout.flush()

    await _stream_chat(url, headers, payload, handle_content)
    _print_footer(citations, usage_info)


def main():
    """Command-line entry point for streaming Brave AI Grounding responses."""
    parser = argparse.ArgumentParser(description="Stream Brave AI Grounding responses")
    _ = parser.add_argument("query", help="Question to ask")
    _ = parser.add_argument("--research", action="store_true", help="Enable research mode")
    _ = parser.add_argument("--no-citations", action="store_true", help="Disable citations")

    args = parser.parse_args()
    query = cast(str, args.query)
    enable_research_flag = bool(cast(bool, args.research))
    enable_citations_flag = not bool(cast(bool, args.no_citations))

    asyncio.run(
        stream_brave_ai(
            query,
            enable_research=enable_research_flag,
            enable_citations=enable_citations_flag,
        ),
    )


if __name__ == "__main__":
    main()
