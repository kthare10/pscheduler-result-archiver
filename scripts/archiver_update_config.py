#!/usr/bin/env python3
import argparse
import os
import secrets
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml  # PyYAML
except Exception:
    print("ERROR: PyYAML not installed. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            raise ValueError("Top-level YAML must be a mapping")
        return data


def dump_yaml(path: Path, data: dict) -> None:
    # Backup existing file
    if path.exists():
        backup = path.with_suffix(path.suffix + f".bak.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
        shutil.copy2(path, backup)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def run_compose(config_path: Path) -> None:
    workdir = config_path.parent
    # Prefer `docker compose`, fallback to `docker-compose`
    compose_cmd = None
    try:
        subprocess.run(["docker", "compose", "version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        compose_cmd = ["docker", "compose"]
    except Exception:
        if shutil.which("docker-compose"):
            compose_cmd = ["docker-compose"]
    if not compose_cmd:
        print("WARNING: docker compose not found; skipping compose up", file=sys.stderr)
        return

    subprocess.run(compose_cmd + ["up", "-d"], cwd=str(workdir), check=True)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Set runtime.bearer_token in YAML (use --token or auto-generate) and optionally docker compose up -d"
    )
    ap.add_argument("config_path", type=Path, help="Path to config.yml")
    ap.add_argument("--token", dest="token", default=None, help="Bearer token to set; if omitted, a new one is generated")
    ap.add_argument("--no-up", action="store_true", help="Do not run `docker compose up -d`")
    args = ap.parse_args()

    try:
        doc = load_yaml(args.config_path)
    except Exception as e:
        print(f"ERROR: Failed to load YAML: {e}", file=sys.stderr)
        return 2

    # Ensure runtime mapping exists
    runtime = doc.get("runtime")
    if runtime is None:
        runtime = {}
        doc["runtime"] = runtime
    elif not isinstance(runtime, dict):
        print("ERROR: `runtime` must be a mapping in YAML", file=sys.stderr)
        return 3

    # Decide token: use provided or generate new
    token = args.token if args.token else secrets.token_hex(32)
    runtime["bearer_token"] = token

    # Write YAML (with backup if file existed)
    try:
        dump_yaml(args.config_path, doc)
    except Exception as e:
        print(f"ERROR: Failed to write YAML: {e}", file=sys.stderr)
        return 4

    # Show runtime block and print token for capture
    print("--- runtime after update ---")
    for k, v in runtime.items():
        print(f"{k}: {v}")
    print("----------------------------")
    print(f"ARCHIVER_TOKEN={token}")

    if not args.no_up:
        try:
            run_compose(args.config_path)
        except subprocess.CalledProcessError as e:
            print(f"ERROR: compose up failed (exit {e.returncode})", file=sys.stderr)
            return e.returncode

    return 0


if __name__ == "__main__":
    sys.exit(main())
