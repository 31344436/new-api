# /token-balance

Summarize the token usage and visible quota metadata that Codex CLI stores locally.

## Workflow

1. Locate the plugin script `codex_token_balance.py`.
   Search the current workspace for `plugins/codex-token-balance/scripts/codex_token_balance.py`.
   If the plugin has been installed into `~/plugins/`, use that copy instead.
2. Run the script with Python.
   Default command:
   `python <plugin-root>/scripts/codex_token_balance.py --days 7`
3. Present the output as a short dashboard:
   account and plan metadata, recent aggregate usage, latest session totals, model breakdown, and any visible rate-limit fields.
4. Be explicit about limitations.
   If the report says credits or balance are unavailable, state that Codex local files do not expose a true remaining ChatGPT token balance.

## Output requirements

- Distinguish local usage totals from a true account balance.
- If `rate_limits.credits` or related fields are null, say so directly.
- Do not print raw auth tokens or secrets from `~/.codex/auth.json`.
