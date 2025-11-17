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

import httpx

# Handle broken pipe gracefully (e.g., when output is piped to head)
signal.signal(signal.SIGPIPE, signal.SIG_DFL)


def get_api_key() -> str:
    """Get API key from .env file or environment."""
    # Try environment variable first
    api_key = os.environ.get("BRAVE_AI_GROUNDING_API_KEY")
    if api_key:
        return api_key

    # Try reading from .env file in package directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    package_env = os.path.join(script_dir, ".env")
    if os.path.exists(package_env):
        try:
            with open(package_env) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("BRAVE_AI_GROUNDING_API_KEY="):
                        return line.split("=", 1)[1].strip()
        except Exception as e:
            print(f"Error reading {package_env}: {e}", file=sys.stderr)

    print("Error: BRAVE_AI_GROUNDING_API_KEY not found", file=sys.stderr)
    print("  - Not set in environment", file=sys.stderr)
    print(f"  - Not found in {package_env}", file=sys.stderr)
    print("", file=sys.stderr)
    print(
        "To set up credentials, copy .env.example to .env and add your API key:",
        file=sys.stderr,
    )
    print(
        f"  cp {os.path.join(script_dir, '.env.example')} {package_env}",
        file=sys.stderr,
    )
    sys.exit(1)


async def stream_brave_ai(
    query: str, enable_research: bool = False, enable_citations: bool = True
):
    """Stream Brave AI Grounding response to stdout."""
    api_key = get_api_key()

    url = "https://api.search.brave.com/res/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "messages": [{"role": "user", "content": query}],
        "stream": True,
        "model": "brave",
        "enable_citations": enable_citations,
    }

    if enable_research:
        payload["enable_research"] = True

    citations = []
    usage_info = None

    async with httpx.AsyncClient(timeout=300.0) as client:
        async with client.stream(
            "POST", url, json=payload, headers=headers
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break

                    try:
                        data = json.loads(data_str)
                        if "choices" in data and len(data["choices"]) > 0:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                # Check if content contains markup
                                if content.startswith("<citation>"):
                                    # Extract citation JSON
                                    citation_json = content.replace(
                                        "<citation>", ""
                                    ).replace("</citation>", "")
                                    try:
                                        citation = json.loads(citation_json)
                                        citations.append(citation)
                                    except json.JSONDecodeError:
                                        pass
                                elif content.startswith("<usage>"):
                                    # Extract usage JSON
                                    usage_json = content.replace("<usage>", "").replace(
                                        "</usage>", ""
                                    )
                                    try:
                                        usage_info = json.loads(usage_json)
                                    except json.JSONDecodeError:
                                        pass
                                else:
                                    # Regular content - print it
                                    print(content, end="", flush=True)
                    except json.JSONDecodeError:
                        pass

    print("\n")  # Final newlines

    # Print footer with citations and usage
    if citations:
        print("\n" + "=" * 60)
        print("SOURCES")
        print("=" * 60)
        for i, cite in enumerate(citations, 1):
            print(f"\n[{i}] {cite.get('url', 'N/A')}")  # type: ignore[union-attr]
            if "snippet" in cite:
                snippet = cite["snippet"]  # type: ignore[typeddict-item]
                # Snippet might be JSON string, try to parse it
                try:
                    snippet_data = json.loads(snippet)  # type: ignore[arg-type]
                    if isinstance(snippet_data, dict):
                        # Print structured snippet
                        for key, value in snippet_data.items():
                            if key not in ["@context", "@type"] and value:
                                print(f"    {key}: {str(value)[:100]}...")
                except (json.JSONDecodeError, TypeError):
                    # Print as plain text
                    print(f"    {snippet[:200]}...")

    if usage_info:
        print("\n" + "=" * 60)
        print("USAGE METRICS")
        print("=" * 60)
        print(f"Requests: {usage_info.get('X-Request-Requests', 0)}")
        print(f"Queries: {usage_info.get('X-Request-Queries', 0)}")
        print(f"Tokens In: {usage_info.get('X-Request-Tokens-In', 0)}")
        print(f"Tokens Out: {usage_info.get('X-Request-Tokens-Out', 0)}")
        print(f"Total Cost: ${usage_info.get('X-Request-Total-Cost', 0):.4f}")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Stream Brave AI Grounding responses")
    parser.add_argument("query", help="Question to ask")
    parser.add_argument("--research", action="store_true", help="Enable research mode")
    parser.add_argument("--no-citations", action="store_true", help="Disable citations")

    args = parser.parse_args()

    asyncio.run(
        stream_brave_ai(
            args.query,
            enable_research=args.research,
            enable_citations=not args.no_citations,
        )
    )


if __name__ == "__main__":
    main()
