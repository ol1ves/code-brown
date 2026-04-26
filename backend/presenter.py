"""Terminal presenter for search responses."""

from __future__ import annotations

import sys

from backend.pipeline.context import RunContext
from shared.models import SearchResponse


def _money(value: float) -> str:
    return f"${round(value):,}"


def _pct(value: float) -> str:
    return f"{round(value)}%"


def _truncate(text: str, n: int) -> str:
    if len(text) <= n:
        return text
    return text[: n - 1] + "…"


def render_search_result(
    response: SearchResponse,
    ctx: RunContext,
    *,
    top_n: int = 20,
    use_color: bool | None = None,
) -> str:
    if use_color is None:
        use_color = sys.stdout.isatty()

    lines: list[str] = []
    lines.append("=" * 79)
    lines.append(f'SEARCH query="{response.metadata.query}" run_id={ctx.run_id} total={ctx.total_ms}ms')
    lines.append("=" * 79)
    lines.append("")
    lines.append("STAGE TIMINGS")
    for stage in ("scrape", "value", "rank", "persist"):
        if stage in ctx.timings_ms:
            lines.append(f"  {stage:<8} {ctx.timings_ms[stage]:>6} ms")
    lines.append(f"  {'total':<8} {ctx.total_ms:>6} ms")
    lines.append("")
    lines.append("-" * 79)
    lines.append(f"TOP {top_n} RESULTS ranked by p_sell × expected_profit_grailed")
    lines.append("-" * 79)
    lines.append(" #  listing                               buy    q50   profit   off   p_sell conf")

    for idx, item in enumerate(response.items[:top_n], start=1):
        label = _truncate(f"{item.live_listing.designer} / {item.live_listing.name} {item.live_listing.size}", 36)
        lines.append(
            f"{idx:>2}  {label:<36} "
            f"{_money(item.buy_cost):>6} "
            f"{_money(item.q50):>6} "
            f"{_money(item.expected_profit_grailed):>7} "
            f"{_money(item.expected_profit_off_grailed):>6} "
            f"{item.p_sell:>6.2f} "
            f"{_pct(item.confidence_pct):>4}"
        )

    lines.append("")
    lines.append("-" * 79)
    lines.append(f"WARNINGS ({len(ctx.warnings)})")
    lines.append("-" * 79)
    if not ctx.warnings:
        lines.append("none")
    else:
        visible = ctx.warnings[:6]
        lines.extend(visible)
        extra = len(ctx.warnings) - len(visible)
        if extra > 0:
            lines.append(f"({extra} more — pass --json for full list)")
    lines.append("")
    lines.append("=" * 79)
    return "\n".join(lines)
