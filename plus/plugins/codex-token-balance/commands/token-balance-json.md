# /token-balance-json

Return the raw machine-readable token usage report from the local Codex data directory.

## Workflow

1. Locate `codex_token_balance.py` from this plugin.
2. Run:
   `python <plugin-root>/scripts/codex_token_balance.py --days 30 --json`
3. Return the JSON payload and a one-paragraph explanation of the most important fields.

## Output requirements

- Preserve the JSON exactly.
- Explain the difference between `recent_usage`, `latest_session`, and `latest_rate_limits`.
- Do not expose raw auth tokens.
