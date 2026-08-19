#!/usr/bin/env python3
"""
Arctus AI — main.py
CLI entry point and application bootstrap.
Registered in pyproject.toml as:
    [project.scripts]
    arctus = "main:main"

Single source of truth for CLI argument parsing, subcommand dispatch,
and top-level exception handling.
"""

from __future__ import annotations

import os
import sys
import argparse
import asyncio
import logging
import json
from typing import Optional, List, Any

# ── Ensure arctus package is importable (editable install or PYTHONPATH) ──
try:
    from arctus import __version__, configure_logging, create_orchestrator
    from arctus.presets import print_diagnostics, detect_available_providers
    from arctus.llm import UnifiedLLMClient, Message, MessageRole
except ImportError as exc:
    # If running from source without install, add parent to path
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    _parent = os.path.dirname(_script_dir)
    if _parent not in sys.path:
        sys.path.insert(0, _parent)
    from arctus import __version__, configure_logging, create_orchestrator
    from arctus.presets import print_diagnostics, detect_available_providers
    from arctus.llm import UnifiedLLMClient, Message, MessageRole


logger = logging.getLogger("arctus.cli")


# ═══════════════════════════════════════════════════════════════════════════
# CLI CONFIG HELPER
# ═══════════════════════════════════════════════════════════════════════════

def _resolve_cli_config(args: argparse.Namespace) -> tuple[str, Optional[str], Optional[str]]:
    """
    Resolve provider / model / api_key from CLI args,
    falling back to saved config and then environment variables.
    """
    from arctus.config import ArctusConfig
    cfg = ArctusConfig.load().merge_env()
    provider = args.provider or cfg.llm_provider
    model = args.model or cfg.model
    api_key = getattr(args, "api_key", None) or cfg.api_key
    return provider, model, api_key


# ═══════════════════════════════════════════════════════════════════════════
# CLI PARSER BUILDERS
# ═══════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="arctus",
        description=(
            "Arctus AI — Local-first multi-agent orchestrator with MCP consortium, "
            "100-agent roster, 80%% handoff cycle.\n"
            "Plan -> Validate -> Execute -> Verify."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  arctus run --prompt "Analyze this codebase" --provider ollama
  arctus chat --provider openrouter --model claude-3.5-sonnet
  arctus diagnose
  arctus setup ollama
  arctus mcp list
  arctus agent roster --max 50
        """.strip(),
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--verbose", "-V",
        action="store_true",
        help="Enable debug-level logging.",
    )
    parser.add_argument(
        "--provider", "-p",
        choices=["ollama", "openrouter", "openai", "runpod", "huggingface", "omniroute"],
        default=os.getenv("ARCTUS_PROVIDER", "ollama"),
        help="LLM provider backend (default: ollama, or ARCTUS_PROVIDER env).",
    )
    parser.add_argument(
        "--model", "-m",
        default=os.getenv("ARCTUS_MODEL"),
        help="Model identifier (default: provider default, or ARCTUS_MODEL env).",
    )
    parser.add_argument(
        "--api-key", "-k",
        default=os.getenv("ARCTUS_API_KEY"),
        help="Override API key (default: provider-specific env var).",
    )
    
    subparsers = parser.add_subparsers(dest="command", title="Commands", metavar="<command>")
    
    # ── run: Execute a single prompt ──────────────────────────────────────
    run_parser = subparsers.add_parser("run", help="Run a single prompt through the orchestrator.")
    run_parser.add_argument("--prompt", "-P", required=True, help="User prompt text.")
    run_parser.add_argument("--file", "-f", help="Read prompt from file path.")
    run_parser.add_argument("--output", "-o", help="Write response to file.")
    run_parser.add_argument("--stream", "-s", action="store_true", help="Stream tokens.")
    run_parser.add_argument("--temperature", "-t", type=float, default=0.7)
    run_parser.add_argument("--max-tokens", type=int, default=2048)
    run_parser.add_argument("--tools", nargs="*", help="Enable tool names.")
    run_parser.add_argument("--agents", "-a", type=int, default=1, help="Number of agents.")
    run_parser.add_argument("--mcp", nargs="*", help="MCP server endpoints.")
    
    # ── chat: Interactive REPL ────────────────────────────────────────────
    chat_parser = subparsers.add_parser("chat", help="Start interactive chat session.")
    chat_parser.add_argument("--system", "-S", help="System prompt.")
    chat_parser.add_argument("--history", help="Load conversation history JSON.")
    
    # ── setup: Provider configuration ─────────────────────────────────────    setup_parser = subparsers.add_parser("setup", help="Configure providers and credentials.")
    setup_parser.add_argument(
        "provider_setup",
        nargs="?",
        choices=["ollama", "openrouter", "huggingface", "runpod", "omniroute", "status"],
        help="Provider to configure, or 'status' to audit configuration.",
    )
    
    # ── diagnose: Environment check ──────────────────────────────────────
    subparsers.add_parser("diagnose", help="Print environment diagnostics.")
    
    # ── mcp: MCP server management ───────────────────────────────────────
    mcp_parser = subparsers.add_parser("mcp", help="MCP consortium commands.")
    mcp_sub = mcp_parser.add_subparsers(dest="mcp_command", metavar="<mcp-command>")
    mcp_sub.add_parser("list", help="List configured MCP servers.")
    mcp_sub.add_parser("add", help="Add an MCP server.")
    mcp_sub.add_parser("remove", help="Remove an MCP server.")
    
    # ── agent: Agent roster management ────────────────────────────────────
    agent_parser = subparsers.add_parser("agent", help="Agent roster commands.")
    agent_sub = agent_parser.add_subparsers(dest="agent_command", metavar="<agent-command>")
    roster_parser = agent_sub.add_parser("roster", help="Show agent roster.")
    roster_parser.add_argument("--max", type=int, default=100)
    spawn_parser = agent_sub.add_parser("spawn", help="Spawn a new agent.")
    spawn_parser.add_argument("--role", required=True, help="Agent role template.")
    spawn_parser.add_argument("--name", help="Custom agent name.")
    
    # ── serve: FastAPI server mode ───────────────────────────────────────
    serve_parser = subparsers.add_parser("serve", help="Start API server.")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--workers", type=int, default=1)
    
    return parser


# ═══════════════════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════════════

async def cmd_run(args: argparse.Namespace) -> int:
    """Execute a single prompt with optional multi-agent orchestration."""
    prompt_text = args.prompt
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            prompt_text = f.read()
    
    provider, model, api_key = _resolve_cli_config(args)
    client = UnifiedLLMClient(provider=provider, model=model, api_key=api_key)
    
    messages = [Message(role=MessageRole.USER, content=prompt_text)]
    
    try:
        if args.stream:
            stream = await client.chat(
                messages=messages,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                stream=True,
            )
            full_text = ""
            print("\n\033[36m╭─ Arctus Response ─────────────────────────────╮\033[0m")
            async for chunk in stream:
                print(chunk.content, end="", flush=True)
                full_text += chunk.content
            print("\n\033[36m╰────────────────────────────────────────────────╯\033[0m\n")
        else:
            response = await client.chat(
                messages=messages,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )
            full_text = response.text
            print("\n\033[36m╭─ Arctus Response ─────────────────────────────╮\033[0m")
            print(full_text)
            print("\033[36m╰────────────────────────────────────────────────╯\033[0m")
            print(f"\n[Model: {response.model} | Provider: {response.provider} | "
                  f"Tokens: {response.usage.get('total_tokens', 'N/A')}]")
        
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(full_text)
            print(f"Saved to: {args.output}")
        
        return 0
    finally:
        await client.close()


async def cmd_chat(args: argparse.Namespace) -> int:
    """Interactive chat REPL."""
    provider, model, api_key = _resolve_cli_config(args)
    client = UnifiedLLMClient(provider=provider, model=model, api_key=api_key)
    messages: List[Message] = []
    
    if args.system:
        messages.append(Message(role=MessageRole.SYSTEM, content=args.system))
    
    print("\n\033[36m╔════════════════════════════════════════════════╗\033[0m")
    print("\033[36m║         Arctus AI — Interactive Chat            ║\033[0m")
    print(f"\033[36m║   Provider:\033[0m {provider:18} \033[36m║\033[0m")
    print("\033[36m╚════════════════════════════════════════════════╝\033[0m")
    print("Type 'exit', 'quit', or press Ctrl+C to leave.\n")
    
    try:
        while True:
            try:
                user_input = input("\033[33mYou:\033[0m ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            
            if user_input.lower() in ("exit", "quit", "q"):
                break
            
            if not user_input:
                continue
            
            messages.append(Message(role=MessageRole.USER, content=user_input))
            
            try:
                response = await client.chat(messages=messages)
                print(f"\033[32mArctus:\033[0m {response.text}\n")
                messages.append(Message(role=MessageRole.ASSISTANT, content=response.text))
            except Exception as exc:
                logger.error("Chat error: %s", exc)
                print(f"\033[31mError: {exc}\033[0m")
        
        return 0
    finally:
        await client.close()


async def cmd_diagnose(_args: argparse.Namespace) -> int:
    """Print environment diagnostics."""
    print_diagnostics()
    print(f"\nPython: {sys.version}")
    print(f"Platform: {sys.platform}")
    return 0


# ═══════════════════════════════════════════════════════════════════════════
# SETUP COMMAND & HELPERS
# ═══════════════════════════════════════════════════════════════════════════

async def cmd_setup(args: argparse.Namespace) -> int:
    """Interactive or targeted provider setup."""
    from arctus.config import ArctusConfig    config = ArctusConfig.load()

    if args.provider_setup == "ollama":
        return await _setup_ollama(config)
    elif args.provider_setup == "openrouter":
        return _setup_openrouter(config)
    elif args.provider_setup == "huggingface":
        return _setup_huggingface(config)
    elif args.provider_setup == "status":
        return _setup_status(config)
    else:
        # General interactive flow
        print("\n\033[36m╔════════════════════════════════════════════════╗\033[0m")
        print("\033[36m║         Arctus AI — Provider Setup              ║\033[0m")
        print("\033[36m╚════════════════════════════════════════════════╝\033[0m")
        print("Available providers: ollama, openrouter, huggingface, runpod, omniroute, openai")
        choice = input("Which provider do you want to configure? [ollama]: ").strip().lower() or "ollama"
        if choice == "ollama":
            return await _setup_ollama(config)
        elif choice == "openrouter":
            return _setup_openrouter(config)
        elif choice == "huggingface":
            return _setup_huggingface(config)
        else:
            print(f"Interactive setup for '{choice}' is not yet implemented.")
            print("Use environment variables or edit ~/.arctus/config.json directly.")
            return 1


class _OllamaSetupAdapter:
    """Clean adapter to existing setup_module.ollama_setup if present."""
    def __init__(self, host: str):
        self.host = host
        self._native = None
        try:
            import setup_module.ollama_setup as _mod
            self._native = _mod
        except ImportError:
            pass

    async def discover_models(self) -> list[str]:
        if self._native:
            for attr in ("list_models", "get_models", "discover_models"):
                fn = getattr(self._native, attr, None)
                if callable(fn):
                    try:
                        result = fn(self.host)
                        if isinstance(result, list):
                            return cast(list[str], result)
 except Exception:
                        pass
        # Fallback: direct httpx discovery
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.host}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return [m.get("name") for m in data.get("models", []) if m.get("name")]


async def _setup_ollama(config: "ArctusConfig") -> int:
    from arctus.config import CONFIG_FILE

    print("\n\033[36m─ Ollama Setup ──────────────────────────────────\033[0m")
    default_host = config.base_url or os.getenv("OLLAMA_HOST", "http://localhost:11434")
    host = input(f"Ollama host [{default_host}]: ").strip() or default_host

    adapter = _OllamaSetupAdapter(host)
    try:
        models = await adapter.discover_models()
    except Exception as exc:
        print(f"\033[33mWarning:\033[0m Could not reach Ollama at {host}: {exc}")
        models = []

    if models:
        print(f"\nDetected models ({len(models)}):")
        for i, m in enumerate(models[:20], 1):
            print(f"  {i}. {m}")
        if len(models) > 20:
            print(f"  ... and {len(models) - 20} more")
        default_model = models[0]
    else:
        default_model = "llama3.2"

    selected = input(f"\nSelect default model [{default_model}]: ").strip() or default_model

    config.llm_provider = "ollama"
    config.model = selected
    config.base_url = host
    config.save()

    print(f"\nSaved Ollama config → {CONFIG_FILE}")
    print(f"  provider: ollama")
    print(f"  model:    {selected}")
    print(f"  host:     {host}")

    # Verify with a minimal chat
    print("\nVerifying with a test chat...")
    try:
        client = UnifiedLLMClient(provider="ollama", model=selected)
        resp = await client.chat(
            [Message(role=MessageRole.USER, content="Say 'OK' and nothing else.")],
            max_tokens=10,
        )
        print(f"Response: {resp.text.strip()}")
        await client.close()
        print("\033[32mOllama setup verified successfully.\033[0m")
    except Exception as exc:
        print(f"\033[33mVerification chat failed:\033[0m {exc}")
        print("Config saved anyway. Ensure Ollama is running and the model is pulled.")
    return 0


def _setup_openrouter(config: "ArctusConfig") -> int:
    import getpass
    from arctus.config import CONFIG_FILE
    from arctus.presets import PROVIDER_REGISTRY

    preset = PROVIDER_REGISTRY["openrouter"]
    env_key = os.getenv(preset.api_key_env)
    cfg_key = config.api_key if config.llm_provider == "openrouter" else None
    existing = env_key or cfg_key

    print("\n\033[36m─ OpenRouter Setup ──────────────────────────────\033[0m")
    print(f"API key env var: {preset.api_key_env}")

    if existing:
        masked = existing[:4] + "•••" + existing[-4:] if len(existing) > 8 else "••••"
        print(f"Existing key found: {masked}")
        use = input("Use existing key? [Y/n]: ").strip().lower() or "y"
        if use != "y":
            existing = None

    if not existing:
        key = getpass.getpass("Enter OpenRouter API key (hidden): ").strip()
        if not key:
            print("No key provided. Aborting.")
            return 1
        existing = key

    default_model = "openai/gpt-4o-mini"
    model = input(f"Default model [{default_model}]: ").strip() or default_model

    config.llm_provider = "openrouter"
    config.model = model
    config.api_key = existing
    config.save()

    print(f"\nSaved OpenRouter config → {CONFIG_FILE}")
    print(f"  provider: openrouter")
    print(f"  model:    {model}")
    print("  api_key:  •••• (masked)")
    print("\033[32mOpenRouter setup complete.\033[0m")
    return 0


def _setup_huggingface(config: "ArctusConfig") -> int:
    import getpass
    from arctus.config import CONFIG_FILE
    from arctus.presets import PROVIDER_REGISTRY

    preset = PROVIDER_REGISTRY["huggingface"]
    env_key = os.getenv(preset.api_key_env)
    cfg_key = config.api_key if config.llm_provider == "huggingface" else None
    existing = env_key or cfg_key

    print("\n\033[36m─ HuggingFace Setup ─────────────────────────────\033[0m")
    print(f"Token env var: {preset.api_key_env}")

    if existing:
        masked = existing[:4] + "•••" + existing[-4:] if len(existing) > 8 else "••••"
        print(f"Existing token found: {masked}")
        use = input("Use existing token? [Y/n]: ").strip().lower() or "y"
        if use != "y":
            existing = None

    if not existing:
        token = getpass.getpass("Enter HuggingFace token (hidden): ").strip()
        if not token:
            print("No token provided. Aborting.")
            return 1
        existing = token

    default_model = "meta-llama/Llama-3.2-3B-Instruct"
    model = input(f"Default model [{default_model}]: ").strip() or default_model

    config.llm_provider = "huggingface"
    config.model = model
    config.api_key = existing
    config.save()

    print(f"\nSaved HuggingFace config → {CONFIG_FILE}")
    print(f"  provider: huggingface")
    print(f"  model:    {model}")
    print("  token:    •••• (masked)")
    print("\033[32mHuggingFace setup complete.\033[0m")
    return 0


def _setup_status(config: "ArctusConfig") -> int:
    from arctus.config import CONFIG_FILE
    from arctus.presets import detect_available_providers, PROVIDER_REGISTRY, get_api_key

    print("\n" + "═" * 50)
    print("  Arctus AI — Provider Setup Status")
    print("═" * 50)

    env_providers = detect_available_providers()
    print(f"\nEnvironment-ready providers: {', '.join(env_providers) or 'None'}")

    print(f"\nActive configuration ({CONFIG_FILE}):")
    print(f"  provider: {config.llm_provider}")
    print(f"  model:    {config.model or 'Not set'}")
    print(f"  base_url: {config.base_url or 'Default'}")

    print("\nCredential audit (secrets are masked):")
    for name, preset in PROVIDER_REGISTRY.items():
        key = get_api_key(preset)
        if key:
            masked = key[:4] + "•••" + key[-4:] if len(key) > 8 else "••••"
            print(f"  {name:15} \033[32m[OK]\033[0m     env key: {masked}")
        else:
            print(f"  {name:15} \033[90m[unset]\033[0m  env var {preset.api_key_env}")

    if config.api_key:
        masked = config.api_key[:4] + "•••" + config.api_key[-4:] if len(config.api_key) > 8 else "••••"
        print(f"\nConfig file key: {masked} (provider={config.llm_provider})")
    else:
        print(f"\nConfig file key: No
