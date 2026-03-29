# Codex Token Balance

This plugin adds a local token-usage dashboard for Codex CLI.

## What it can show

- ChatGPT plan metadata that Codex stores in `~/.codex/auth.json`
- recent token usage aggregated from `~/.codex/sessions/**/*.jsonl`
- latest session totals and last-turn totals
- per-model breakdowns
- any `rate_limits`, `credits`, or related quota fields if Codex persists them locally

## What it cannot show

- a true remaining ChatGPT token balance when Codex does not persist one
- billing or credit data that is only available through remote APIs

## Commands

- `/token-balance`
- `/token-balance-json`

## Manual script usage

```powershell
python .\plugins\codex-token-balance\scripts\codex_token_balance.py --days 7
python .\plugins\codex-token-balance\scripts\codex_token_balance.py --days 30 --json
python .\plugins\codex-token-balance\scripts\codex_token_balance_watch.py
```

## Optional home-local install

```powershell
python .\plugins\codex-token-balance\scripts\install_home_plugin.py
```
