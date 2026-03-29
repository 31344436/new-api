#!/usr/bin/env python3
"""Install the workspace plugin into the user's home-local Codex marketplace."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


PLUGIN_NAME = "codex-token-balance"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def install_windows_launchers(dest_root: Path) -> list[Path]:
    appdata = Path.home() / "AppData" / "Roaming"
    npm_bin = appdata / "npm"
    watch_script = dest_root / "scripts" / "codex_token_balance_watch.py"

    ps1_content = "\n".join(
        [
            "#!/usr/bin/env pwsh",
            "$script = Join-Path $HOME 'plugins\\codex-token-balance\\scripts\\codex_token_balance_watch.py'",
            "if (-not (Test-Path $script)) {",
            "  Write-Error \"Missing watch script at $script\"",
            "  exit 1",
            "}",
            "& python $script @args",
            "exit $LASTEXITCODE",
            "",
        ]
    )
    cmd_content = "\r\n".join(
        [
            "@ECHO off",
            "SET \"SCRIPT=%USERPROFILE%\\plugins\\codex-token-balance\\scripts\\codex_token_balance_watch.py\"",
            "IF NOT EXIST \"%SCRIPT%\" (",
            "  ECHO Missing watch script at %SCRIPT%",
            "  EXIT /b 1",
            ")",
            "python \"%SCRIPT%\" %*",
            "",
        ]
    )

    ps1_path = npm_bin / "codex-balance-watch.ps1"
    cmd_path = npm_bin / "codex-balance-watch.cmd"
    write_text(ps1_path, ps1_content)
    write_text(cmd_path, cmd_content)
    return [ps1_path, cmd_path, watch_script]


def main() -> None:
    plugin_root = Path(__file__).resolve().parents[1]
    home = Path.home()
    dest_root = home / "plugins" / PLUGIN_NAME
    marketplace_path = home / ".agents" / "plugins" / "marketplace.json"

    if dest_root.exists():
        shutil.rmtree(dest_root)
    shutil.copytree(
        plugin_root,
        dest_root,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )

    if marketplace_path.exists():
        with marketplace_path.open("r", encoding="utf-8") as handle:
            marketplace = json.load(handle)
    else:
        marketplace = {
            "name": "local-home",
            "interface": {"displayName": "Local Home Plugins"},
            "plugins": [],
        }

    plugins = marketplace.setdefault("plugins", [])
    entry = {
        "name": PLUGIN_NAME,
        "source": {"source": "local", "path": f"./plugins/{PLUGIN_NAME}"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": "Productivity",
    }

    for index, current in enumerate(plugins):
        if isinstance(current, dict) and current.get("name") == PLUGIN_NAME:
            plugins[index] = entry
            break
    else:
        plugins.append(entry)

    write_json(marketplace_path, marketplace)
    launcher_paths = install_windows_launchers(dest_root)
    print(f"Installed plugin to {dest_root}")
    print(f"Updated marketplace {marketplace_path}")
    print(f"Installed launchers: {', '.join(str(path) for path in launcher_paths[:2])}")


if __name__ == "__main__":
    main()
