#!/usr/bin/env python3
"""Watch the latest Codex session and render a compact live dashboard."""

from __future__ import annotations

import argparse
import os
import socket
import time
from datetime import datetime, timezone
from pathlib import Path

from codex_token_balance import (
    compact_dict,
    format_timestamp,
    format_unix_timestamp,
    gather_account_summary,
    gather_session_summaries,
    select_latest_session,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Watch local Codex token usage in a compact terminal dashboard."
    )
    parser.add_argument(
        "--codex-home",
        default=str(Path.home() / ".codex"),
        help="Codex home directory. Defaults to ~/.codex.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Only consider sessions updated within the last N days.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=15,
        help="Refresh interval in seconds.",
    )
    parser.add_argument(
        "--cwd",
        default=os.getcwd(),
        help="Prefer sessions whose recorded cwd matches this path. Defaults to the current cwd.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Render one frame and exit.",
    )
    return parser.parse_args()


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def usage_percent(used_percent: object) -> str:
    if used_percent is None:
        return "unavailable"
    try:
        return f"{float(used_percent):.1f}%"
    except (TypeError, ValueError):
        return "unavailable"


def fmt_int(value: object) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "unavailable"


def pick_primary_rate_limits(session_rate_limits: dict | None, latest_rate_limits: dict | None) -> dict:
    return compact_dict(session_rate_limits) or compact_dict(latest_rate_limits) or {}


def render_dashboard(codex_home: Path, days: int, target_cwd: str) -> str:
    account = gather_account_summary(codex_home)
    sessions = gather_session_summaries(codex_home, days)
    session = select_latest_session(sessions, target_cwd)
    latest_rate_limits = {}
    for item in reversed(sessions):
        latest_rate_limits = compact_dict(item.rate_limits) or latest_rate_limits
        if latest_rate_limits:
            break

    lines = [
        "Codex Balance Watch",
        f"host: {socket.gethostname()}",
        f"watch cwd: {target_cwd}",
        f"data: {codex_home}",
        f"updated: {format_timestamp(datetime.now(timezone.utc))}",
        "",
        f"plan: {account.get('plan_type') or 'unavailable'}",
        f"account: {account.get('email') or account.get('account_id') or 'unavailable'}",
        f"recent sessions ({days}d): {len(sessions)}",
    ]

    if session is None:
        lines.extend(
            [
                "",
                "No matching Codex session found yet.",
                "Start Codex in this directory, or rerun with --cwd pointing at that workspace.",
                "",
                "Press Ctrl+C to exit.",
            ]
        )
        return "\n".join(lines)

    rate_limits = pick_primary_rate_limits(session.rate_limits, latest_rate_limits)
    primary = rate_limits.get("primary") or {}
    secondary = rate_limits.get("secondary") or {}

    lines.extend(
        [
            "",
            f"session model: {session.model or 'unavailable'}",
            f"session ended: {format_timestamp(session.ended_at)}",
            f"session cwd: {session.cwd or 'unavailable'}",
            f"context window: {session.model_context_window or 'unavailable'}",
            "",
            f"session total: {fmt_int(session.total_usage.get('total_tokens'))}",
            f"input: {fmt_int(session.total_usage.get('input_tokens'))}",
            f"cached input: {fmt_int(session.total_usage.get('cached_input_tokens'))}",
            f"output: {fmt_int(session.total_usage.get('output_tokens'))}",
            f"reasoning: {fmt_int(session.total_usage.get('reasoning_output_tokens'))}",
            "",
            f"last turn total: {fmt_int(session.last_usage.get('total_tokens'))}",
            f"last turn input: {fmt_int(session.last_usage.get('input_tokens'))}",
            f"last turn output: {fmt_int(session.last_usage.get('output_tokens'))}",
            "",
            f"5h window: {usage_percent(primary.get('used_percent'))}",
            f"5h reset: {format_unix_timestamp(primary.get('resets_at'))}",
            f"7d window: {usage_percent(secondary.get('used_percent'))}",
            f"7d reset: {format_unix_timestamp(secondary.get('resets_at'))}",
            f"credits: {rate_limits.get('credits') if rate_limits.get('credits') is not None else 'unavailable'}",
            "",
            "Press Ctrl+C to exit.",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    codex_home = Path(args.codex_home).expanduser()
    if args.once:
        print(render_dashboard(codex_home, args.days, args.cwd))
        return
    try:
        while True:
            clear_screen()
            print(render_dashboard(codex_home, args.days, args.cwd))
            time.sleep(max(args.interval, 0.2))
    except KeyboardInterrupt:
        print("\nStopped codex-balance-watch.")


if __name__ == "__main__":
    main()
