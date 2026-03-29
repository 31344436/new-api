#!/usr/bin/env python3
"""Summarize token usage and visible balance metadata from local Codex files."""

from __future__ import annotations

import argparse
import base64
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


USAGE_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report token usage and visible balance metadata from ~/.codex."
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
        help="Only include sessions updated within the last N days.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit raw JSON instead of a formatted text report.",
    )
    return parser.parse_args()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def normalize_path_string(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(Path(value).resolve()).casefold()
    except OSError:
        return str(Path(value)).casefold()


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def format_timestamp(value: datetime | None) -> str:
    if value is None:
        return "unavailable"
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def format_unix_timestamp(value: Any) -> str:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return "unavailable"
    return format_timestamp(datetime.fromtimestamp(numeric, tz=timezone.utc))


def decode_jwt_payload(token: str | None) -> dict[str, Any]:
    if not token or token.count(".") < 2:
        return {}
    payload_segment = token.split(".")[1]
    padding = "=" * (-len(payload_segment) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload_segment + padding)
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def normalize_usage(payload: dict[str, Any] | None) -> dict[str, int]:
    payload = payload or {}
    return {field: int(payload.get(field, 0) or 0) for field in USAGE_FIELDS}


def add_usage(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    return {field: left.get(field, 0) + right.get(field, 0) for field in USAGE_FIELDS}


def compact_dict(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    cleaned = {key: value for key, value in payload.items() if value not in (None, "", [], {})}
    return cleaned or None


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def gather_account_summary(codex_home: Path) -> dict[str, Any]:
    auth_path = codex_home / "auth.json"
    if not auth_path.exists():
        return {
            "codex_home": str(codex_home),
            "auth_found": False,
        }

    auth_payload = load_json(auth_path)
    tokens = auth_payload.get("tokens") or {}
    id_claims = decode_jwt_payload(tokens.get("id_token"))
    access_claims = decode_jwt_payload(tokens.get("access_token"))
    auth_claims = (
        id_claims.get("https://api.openai.com/auth")
        or access_claims.get("https://api.openai.com/auth")
        or {}
    )
    profile_claims = access_claims.get("https://api.openai.com/profile") or {}

    organizations = []
    for org in auth_claims.get("organizations", []) or []:
        if not isinstance(org, dict):
            continue
        organizations.append(
            {
                "id": org.get("id"),
                "title": org.get("title"),
                "role": org.get("role"),
                "is_default": bool(org.get("is_default")),
            }
        )

    return {
        "codex_home": str(codex_home),
        "auth_found": True,
        "auth_mode": auth_payload.get("auth_mode"),
        "last_refresh": auth_payload.get("last_refresh"),
        "account_id": tokens.get("account_id"),
        "openai_api_key_present": bool(auth_payload.get("OPENAI_API_KEY")),
        "plan_type": auth_claims.get("chatgpt_plan_type"),
        "subscription_active_start": auth_claims.get("chatgpt_subscription_active_start"),
        "subscription_active_until": auth_claims.get("chatgpt_subscription_active_until"),
        "subscription_last_checked": auth_claims.get("chatgpt_subscription_last_checked"),
        "chatgpt_account_id": auth_claims.get("chatgpt_account_id"),
        "chatgpt_user_id": auth_claims.get("chatgpt_user_id"),
        "email": profile_claims.get("email") or id_claims.get("email"),
        "email_verified": profile_claims.get("email_verified", id_claims.get("email_verified")),
        "organizations": organizations,
    }


@dataclass
class SessionSummary:
    path: str
    ended_at: datetime
    model: str | None
    cwd: str | None
    total_usage: dict[str, int]
    last_usage: dict[str, int]
    model_context_window: int | None
    rate_limits: dict[str, Any]


def read_session_summary(path: Path) -> SessionSummary | None:
    ended_at: datetime | None = None
    model: str | None = None
    cwd: str | None = None
    total_usage: dict[str, int] | None = None
    last_usage: dict[str, int] | None = None
    model_context_window: int | None = None
    rate_limits: dict[str, Any] = {}

    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            timestamp = parse_timestamp(payload.get("timestamp"))
            if timestamp:
                ended_at = timestamp

            event_type = payload.get("type")
            body = payload.get("payload") or {}

            if event_type == "turn_context":
                model = body.get("model") or model
                cwd = body.get("cwd") or cwd
                continue

            if event_type != "event_msg" or body.get("type") != "token_count":
                continue

            info = body.get("info") or {}
            total_usage = normalize_usage(info.get("total_token_usage"))
            last_usage = normalize_usage(info.get("last_token_usage"))
            model_context_window = info.get("model_context_window") or model_context_window
            rate_limits = body.get("rate_limits") or rate_limits

    if ended_at is None:
        ended_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

    if total_usage is None and last_usage is None and not rate_limits:
        return None

    return SessionSummary(
        path=str(path),
        ended_at=ended_at,
        model=model,
        cwd=cwd,
        total_usage=total_usage or normalize_usage({}),
        last_usage=last_usage or normalize_usage({}),
        model_context_window=model_context_window,
        rate_limits=rate_limits,
    )


def gather_session_summaries(codex_home: Path, days: int) -> list[SessionSummary]:
    sessions_root = codex_home / "sessions"
    if not sessions_root.exists():
        return []

    cutoff = now_utc() - timedelta(days=max(days, 0))
    summaries: list[SessionSummary] = []

    for path in sorted(sessions_root.rglob("*.jsonl")):
        summary = read_session_summary(path)
        if summary is None:
            continue
        if summary.ended_at < cutoff:
            continue
        summaries.append(summary)

    summaries.sort(key=lambda item: item.ended_at)
    return summaries


def select_latest_session(
    sessions: list[SessionSummary], target_cwd: str | None = None
) -> SessionSummary | None:
    if not sessions:
        return None
    if not target_cwd:
        return sessions[-1]

    normalized_target = normalize_path_string(target_cwd)
    matching = [
        session
        for session in sessions
        if normalize_path_string(session.cwd) == normalized_target
    ]
    if matching:
        return matching[-1]
    return sessions[-1]


def build_report(codex_home: Path, days: int) -> dict[str, Any]:
    account = gather_account_summary(codex_home)
    sessions = gather_session_summaries(codex_home, days)

    aggregate_usage = normalize_usage({})
    model_totals: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "sessions": 0,
            "usage": normalize_usage({}),
        }
    )

    for session in sessions:
        aggregate_usage = add_usage(aggregate_usage, session.total_usage)
        model_key = session.model or "unknown"
        model_totals[model_key]["sessions"] += 1
        model_totals[model_key]["usage"] = add_usage(
            model_totals[model_key]["usage"], session.total_usage
        )

    latest_session = sessions[-1] if sessions else None
    latest_rate_limits = None
    for session in reversed(sessions):
        cleaned = compact_dict(session.rate_limits)
        if cleaned:
            latest_rate_limits = cleaned
            break

    report = {
        "generated_at": now_utc().isoformat(),
        "account": account,
        "window_days": days,
        "recent_usage": {
            "session_count": len(sessions),
            "usage": aggregate_usage,
            "models": {
                model: {
                    "sessions": payload["sessions"],
                    "usage": payload["usage"],
                }
                for model, payload in sorted(model_totals.items())
            },
        },
        "latest_session": None,
        "latest_rate_limits": latest_rate_limits,
        "notes": [
            "This report is built from local Codex auth metadata and session logs under ~/.codex.",
            "It can show observed usage totals, plan metadata, and any rate-limit fields the CLI persisted locally.",
            "It cannot infer a true remaining ChatGPT token balance unless Codex exposes one in local rate-limit fields.",
        ],
    }

    if latest_session is not None:
        report["latest_session"] = {
            "path": latest_session.path,
            "ended_at": latest_session.ended_at.isoformat(),
            "model": latest_session.model,
            "cwd": latest_session.cwd,
            "model_context_window": latest_session.model_context_window,
            "total_usage": latest_session.total_usage,
            "last_usage": latest_session.last_usage,
            "rate_limits": latest_session.rate_limits,
        }

    return report


def format_usage_line(label: str, usage: dict[str, int]) -> str:
    return (
        f"{label}: total {usage['total_tokens']:,} | "
        f"input {usage['input_tokens']:,} | "
        f"cached {usage['cached_input_tokens']:,} | "
        f"output {usage['output_tokens']:,} | "
        f"reasoning {usage['reasoning_output_tokens']:,}"
    )


def format_organizations(organizations: list[dict[str, Any]]) -> str:
    if not organizations:
        return "unavailable"
    parts = []
    for org in organizations:
        title = org.get("title") or org.get("id") or "unknown"
        role = org.get("role") or "unknown-role"
        default_suffix = " default" if org.get("is_default") else ""
        parts.append(f"{title} ({role}{default_suffix})")
    return "; ".join(parts)


def format_rate_limit_window(name: str, payload: dict[str, Any] | None) -> str:
    if not payload:
        return f"- {name}: unavailable"
    used_percent = payload.get("used_percent")
    window_minutes = payload.get("window_minutes")
    resets_at = format_unix_timestamp(payload.get("resets_at"))
    return (
        f"- {name}: {used_percent if used_percent is not None else 'unavailable'}% used | "
        f"window {window_minutes if window_minutes is not None else 'unavailable'} min | "
        f"resets {resets_at}"
    )


def render_text_report(report: dict[str, Any]) -> str:
    account = report["account"]
    recent_usage = report["recent_usage"]
    latest_session = report.get("latest_session")
    latest_rate_limits = report.get("latest_rate_limits") or {}

    lines = [
        "Codex Token Balance Report",
        f"Generated: {format_timestamp(parse_timestamp(report.get('generated_at')))}",
        f"Data source: {account.get('codex_home', 'unavailable')}",
        "",
        "Account",
        f"- Auth metadata found: {'yes' if account.get('auth_found') else 'no'}",
        f"- Plan type: {account.get('plan_type') or 'unavailable'}",
        f"- Account id: {account.get('account_id') or 'unavailable'}",
        f"- ChatGPT account id: {account.get('chatgpt_account_id') or 'unavailable'}",
        f"- Email: {account.get('email') or 'unavailable'}",
        f"- Auth mode: {account.get('auth_mode') or 'unavailable'}",
        f"- API key stored in auth.json: {'yes' if account.get('openai_api_key_present') else 'no'}",
        f"- Subscription window: {account.get('subscription_active_start') or 'unavailable'} -> "
        f"{account.get('subscription_active_until') or 'unavailable'}",
        f"- Organizations: {format_organizations(account.get('organizations') or [])}",
        "",
        f"Recent Usage ({report['window_days']} days)",
        f"- Sessions observed: {recent_usage['session_count']}",
        f"- {format_usage_line('Aggregate', recent_usage['usage'])}",
    ]

    if latest_session:
        lines.extend(
            [
                "",
                "Latest Session",
                f"- Ended: {format_timestamp(parse_timestamp(latest_session.get('ended_at')))}",
                f"- Model: {latest_session.get('model') or 'unavailable'}",
                f"- Working dir: {latest_session.get('cwd') or 'unavailable'}",
                f"- Context window: {latest_session.get('model_context_window') or 'unavailable'}",
                f"- {format_usage_line('Session total', latest_session['total_usage'])}",
                f"- {format_usage_line('Last turn', latest_session['last_usage'])}",
            ]
        )

    if recent_usage["models"]:
        lines.extend(["", "By Model"])
        for model, payload in recent_usage["models"].items():
            lines.append(
                f"- {model}: {payload['sessions']} sessions | "
                f"{format_usage_line('usage', payload['usage'])}"
            )

    lines.extend(
        [
            "",
            "Observed Rate Limits",
            f"- limit_id: {latest_rate_limits.get('limit_id') or 'unavailable'}",
            f"- limit_name: {latest_rate_limits.get('limit_name') or 'unavailable'}",
            f"- plan_type: {latest_rate_limits.get('plan_type') or 'unavailable'}",
            f"- credits: {latest_rate_limits.get('credits') if latest_rate_limits.get('credits') is not None else 'unavailable'}",
            format_rate_limit_window("primary", latest_rate_limits.get("primary")),
            format_rate_limit_window("secondary", latest_rate_limits.get("secondary")),
            "",
            "Limitations",
            "- This report can show local token usage and whatever Codex persisted under rate_limits.",
            "- It does not prove a remaining ChatGPT token balance unless credits or similar fields are actually present.",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    report = build_report(Path(args.codex_home).expanduser(), args.days)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return
    print(render_text_report(report))


if __name__ == "__main__":
    main()
