#!/usr/bin/env python3
"""Arctus.ai CLI.

Usage:
    python main.py                       # interactive REPL
    python main.py "do something"        # one-shot task
    python main.py config                # show config
    python main.py config-set '{"strong":{"model":"gpt-4o"}}'
    python main.py setup ollama          # connect to local Ollama
    python main.py setup openrouter      # connect to OpenRouter
    python main.py setup hf              # use the free-tier model preset
    python main.py connect <hf-space-url>  # link to a remote HF-hosted instance
    python main.py show <session-id>
    python main.py reset <session-id> [--scope all|history]
    python main.py --help | -h

Everything runs locally. No tunnels, no header forwarding, no remote servers.
Keys come from your environment or ~/.config/arctus-ai/config.json.
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from arctus import Config, Tier, QueenAgent, RateLimitConfig, load_config, save_config
from arctus import session as session_store


HELP_TEXT = """\
Arctus.ai — local-first multi-agent orchestrator (Plan -> Route -> Execute -> Verify)

Runs entirely on YOUR machine. No tunnels, no remote servers, no credential
forwarding. Your API key stays in your environment.

Commands:
  arctus                            interactive REPL
  arctus "do something"             run a single task and exit
  arctus config                     print config + config file path
  arctus config-set '<json>'        merge JSON into config
  arctus setup ollama               connect fast tier to local Ollama (default)
  arctus setup openrouter           connect strong tier to OpenRouter
  arctus setup hf                   apply the free-tier model preset (HF Spaces)
  arctus connect <hf-space-url>     link this CLI to a remote HF-hosted instance
  arctus merge-repo <url> [--dest]  clone a repo into ./repos for agent access
  arctus show <session-id>          print a saved session
  arctus reset <session-id>         clear a session (--scope all|history)
  arctus --help | -h                this help

Config:  ~/.config/arctus-ai/config.json
Sessions: ~/.config/arctus-ai/sessions/*.json

Tier defaults:
  fast   -> http://localhost:11434/v1   model llama3.2  (Ollama, local)
  strong -> https://api.openai.com/v1   model gpt-4o-mini (set ARCTUS_STRONG_API_KEY)
"""


def _stamp(msg: str) -> str:
    import datetime
    return f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}"


def _run_task(prompt: str, cfg: Config, session_id: str) -> None:
    print(_stamp(f"Task: {prompt!r}"))
    queen = QueenAgent(cfg)
    result = queen.run(prompt, session_id=session_id)
    print(_stamp(f"Complexity: {result.complexity} | mode: {result.mode}"))

    if result.error:
        print(_stamp(f"Error: {result.error}"))
        return

    sess = session_store.load(session_id)
    sess["steps"] = [asdict(s) if hasattr(s, "__dataclass_fields__") else s for s in result.steps]
    sess["log"].append({
        "prompt": prompt,
        "complexity": result.complexity,
        "mode": result.mode,
        "work": result.work,
        "verification": result.verification,
        "handoffs": result.handoffs,
    })
    sess["history"].append({"role": "user", "content": prompt})
    for w in result.work:
        sess["history"].append({"role": "assistant", "content": w.get("result", "")})
    session_store.save(sess)

    for w in result.work:
        print(_stamp(f"  [{w.get('tier')}] {w.get('step')} ({w.get('tokens_used', 0)} tok)"))
    if result.verification:
        print(_stamp(f"Verify: done={result.verification.get('done')} — {result.verification.get('notes')}"))
    print("\n=== RESULT ===")
    print("\n\n".join(w.get("result", "") for w in result.work))
    print("==============\n")


def _repl(cfg: Config) -> None:
    print("Arctus.ai REPL. Type a task, or :quit to exit.\n")
    session_id = f"repl-{int(__import__('time').time())}"
    while True:
        try:
            line = input("arctus> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye.")
            return
        if not line:
            continue
        if line in (":quit", ":q"):
            print("bye.")
            return
        if line == ":reset":
            session_store.reset(session_id, scope="all")
            print(_stamp("session reset"))
            continue
        try:
            _run_task(line, cfg, session_id)
        except Exception as e:
            print(_stamp(f"Error: {e}"))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="arctus",
        description="Local-first multi-agent orchestrator.",
        add_help=False,
    )
    parser.add_argument("command", nargs="?", default=None)
    parser.add_argument("rest", nargs=argparse.REMAINDER)
    parser.add_argument("-h", "--help", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.help or args.command in (None, "-h", "--help"):
        print(HELP_TEXT)
        return 0

    cfg = load_config()

    if args.command == "config":
        from arctus.config import CONFIG_FILE
        print(f"Config file: {CONFIG_FILE}")
        print(json.dumps(asdict(cfg), indent=2))
        return 0

    if args.command == "config-set":
        if not args.rest:
            print("usage: arctus config-set '<json>'", file=sys.stderr)
            return 2
        try:
            patch = json.loads(" ".join(args.rest))
        except json.JSONDecodeError as e:
            print(f"invalid JSON: {e}", file=sys.stderr)
            return 2
        merged = asdict(cfg)
        for k, v in patch.items():
            if k in ("fast", "strong") and isinstance(v, dict):
                merged[k].update(v)
            else:
                merged[k] = v
        # Re-build dataclasses from merged dict.
        new_cfg = Config(
            fast=Tier(**merged["fast"]),
            strong=Tier(**merged["strong"]),
            **{k: v for k, v in merged.items() if k not in ("fast", "strong")},
        )
        path = save_config(new_cfg)
        print(f"Saved to {path}")
        return 0

    if args.command == "setup":
        from arctus import presets
        target = args.rest[0] if args.rest else "ollama"
        valid = ("ollama", "openrouter", "openai", "hf",
                 "omniroute_local", "omniroute_remote",
                 "anthropic_via_openrouter", "openrouter_free")
        if target not in valid:
            print(f"Unknown setup target {target!r}. Valid: {', '.join(valid)}",
                  file=sys.stderr)
            return 2
        # 'hf' maps to the free-tier preset for hosted deployments.
        preset_name = "openrouter_free" if target == "hf" else target
        try:
            cfg = presets.apply_preset(preset_name, cfg=cfg)
        except KeyError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(_stamp(f"Setup complete: applied '{preset_name}' preset."))
        print(f"  {preset_name} -> see ~/.config/arctus-ai/config.json")
        if preset_name == "ollama":
            print("  Make sure Ollama is running:  ollama serve")
            print("  Pull the model once:         ollama pull llama3.2")
        elif preset_name in ("openrouter", "openrouter_free"):
            key_set = bool(__import__("os").environ.get("OPENROUTER_API_KEY"))
            print(f"  OPENROUTER_API_KEY env: {'set' if key_set else 'NOT SET — export OPENROUTER_API_KEY=sk-or-...'}")
        return 0

    if args.command == "connect":
        if not args.rest:
            print("usage: arctus connect <hf-space-url> [--key KEY]",
                  file=sys.stderr)
            print("Link this CLI to a remote Hugging Face-hosted Arctus instance.",
                  file=sys.stderr)
            return 2
        url = args.rest[0].rstrip("/")
        key = ""
        if "--key" in args.rest:
            i = args.rest.index("--key")
            key = args.rest[i + 1] if i + 1 < len(args.rest) else ""
        # Point both tiers at the remote HF instance so external CLIs can
        # drive the hosted agent without cloning or pip-installing the repo.
        base = url + "/v1" if not url.endswith("/v1") else url
        cfg.fast = Tier(base_url=base, model=cfg.fast.model,
                        api_key=key or cfg.fast.api_key, temperature=0.2)
        cfg.strong = Tier(base_url=base, model=cfg.strong.model,
                          api_key=key or cfg.strong.api_key, temperature=0.4)
        save_config(cfg)
        print(_stamp(f"Linked to remote instance: {url}"))
        print(f"  Both tiers now point at {base}")
        print(f"  Tasks run on the HF-hosted agent — no local clone needed.")
        if not key:
            print("  (No API key set. Add --key <token> if the instance requires one.)")
        return 0

    if args.command == "merge-repo":
        if not args.rest:
            print("usage: arctus merge-repo <git-url> [--dest <name>]", file=sys.stderr)
            print("Shallow-clones a repo into ./repos/<name> for agent access.", file=sys.stderr)
            return 2
        url = args.rest[0]
        dest_name = ""
        if "--dest" in args.rest:
            i = args.rest.index("--dest")
            dest_name = args.rest[i + 1] if i + 1 < len(args.rest) else ""
        if not dest_name:
            # Derive name from URL: last path segment, strip .git
            dest_name = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
        target = Path("repos") / dest_name
        if target.exists():
            print(_stamp(f"merge-repo: {dest_name} already exists at {target} (skipped)"))
            return 0
        print(_stamp(f"merge-repo: cloning {url} -> {target} (shallow, depth=1)"))
        target.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", url, str(target)],
                check=True, capture_output=True,
            )
            print(_stamp(f"merge-repo: cloned {dest_name} into {target}"))
            print(f"  Agents can now read files from {target}")
        except FileNotFoundError:
            print("  git not installed — merge-repo requires git.", file=sys.stderr)
            return 2
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode(errors="ignore").strip()
            print(f"  FAILED: {stderr}", file=sys.stderr)
            if target.exists():
                import shutil; shutil.rmtree(target, ignore_errors=True)
            return 2
        return 0

    if args.command == "show":
        if not args.rest:
            print("usage: arctus show <session-id>", file=sys.stderr)
            return 2
        print(json.dumps(session_store.load(args.rest[0]), indent=2))
        return 0

    if args.command == "reset":
        if not args.rest:
            print("usage: arctus reset <session-id> [--scope all|history]", file=sys.stderr)
            return 2
        sid = args.rest[0]
        scope = "all"
        if "--scope" in args.rest:
            i = args.rest.index("--scope")
            scope = args.rest[i + 1] if i + 1 < len(args.rest) else "all"
        print(json.dumps(session_store.reset(sid, scope=scope), indent=2))
        return 0

    if args.command == "repl":
        _repl(cfg)
        return 0

    # Anything else = one-shot task (joined).
    prompt = " ".join([args.command] + args.rest).strip()
    _run_task(prompt, cfg, session_id=f"task-{int(__import__('time').time())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
