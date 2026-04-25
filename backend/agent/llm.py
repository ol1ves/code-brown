from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncIterator

_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")


def _client():
    from anthropic import AsyncAnthropic

    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is required")
    return AsyncAnthropic(api_key=key)


def extract_json(text: str) -> dict:
    fenced = re.findall(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if fenced:
        return json.loads(fenced[-1])
    candidates = re.findall(r"(\{[\s\S]*\})", text)
    if not candidates:
        raise ValueError("No JSON object found in model output")
    return json.loads(candidates[-1])


async def complete_json(*, system: str, user: str) -> dict:
    client = _client()
    msg = await client.messages.create(
        model=_MODEL,
        max_tokens=1400,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
    return extract_json(text)


async def stream_text(*, system: str, user: str, max_tokens: int = 1800) -> AsyncIterator[str]:
    client = _client()
    async with client.messages.stream(
        model=_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        async for event in stream:
            if event.type == "content_block_delta" and getattr(event.delta, "type", "") == "text_delta":
                yield event.delta.text
