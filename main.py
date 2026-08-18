import sys
import os
import json
import argparse
import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Any

# Ensure arctus package is discoverable when running as script
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))

# Internal imports with graceful fallback
try:
    from arctus.setup import setup_provider, PRESETS
    from arctus.config import Config, get_config_path
    from arctus.orchestrator import Orchestrator
    from arctus.llm import LLMClient, LLMError
    SETUP_AVAILABLE = True
except ImportError as e:
    SETUP_AVAILABLE = False
    _IMPORT_ERROR = str(e)
    # Define minimal stubs for help display
    PRESETS = {"ollama": {}, "openrouter": {}, "hf": {}}
    
    def setup_provider(*a, **k):
        raise ImportError(f"Setup module not available: {_IMPORT_ERROR}")
    
    def check_status():
        raise ImportError(f"Setup module not available: {_IMPORT_ERROR}")


# ============================================================================
# CONSTANTS
# ============================================================================

APP_NAME = "arctus"
VERSION = "1.0.0"
DESCRIPTION = "Local-first multi-agent orchestration framework"

# Fixed model mappings for OpenRouter (corrected endpoints)
OPENROUTER_MODELS = {
    "claude-sonnet": "anthropic/claude-3.5-sonnet-20241022",
    "claude-opus": "anthropic/claude-3-opus-20240229",
    "claude-haiku": "anthropic/claude-3-haiku-20240307",
    "gpt-4o": "openai/gpt-4o-2024-08-06",
    "gpt-4o-mini": "openai/gpt-4o-mini-2024-07-18",
    "deepseek-chat": "deepseek/deepseek-chat",
    "deepseek-coder": "deepseek/deepseek-coder",
    "llama-3-70b": "meta-llama/llama-3.1-70b-instruct",
    "llama-3-8b": "meta-llama/llama-3.1-8b-instruct",
}

OLLAMA_MODELS = {
    "llama3": "llama3",
    "llama3.1": "llama3.1",
    "mistral": "mistral",
    "codellama": "codellama",
    "phi3": "phi3",
    "gemma2": "gemma2",
}


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def print_error(msg: str) -> None:
    """Print error message to stderr."""
    print(f"[ERROR] {msg}", file=sys.stderr)


def print_success(msg: str) -> None:
    """Print success message."""
    print(f"[OK] {msg}")


def print_info(msg: str) -> None:
    """Print info message."""
    print(f"[INFO] {msg}")


def is_ollama_running() -> bool:
    """Check if Ollama server is responding."""
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://localhost:11434/api/tags",
            method="GET",
            headers={"Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def get_ollama_models() -> List[str]:
    """List available Ollama models."""
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://localhost:11434/api/tags",
            headers={"Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return [m["name"] for m in data.get("models", [])]
    except Exception as e:
        print_error(f"Cannot reach Ollama: {e}")
        return []


# ============================================================================
# COMMAND HANDLERS
# ============================================================================

def cmd_repl(args: argparse.Namespace) -> int:
    """Start interactive REPL session."""
    print(f"\n{'='*50}")
    print(f"  {APP_NAME} v{VERSION} - Interactive Mode")
    print(f"  Type 'exit' or 'quit' to leave")
    print(f"  Type 'help' for commands")
    print(f"{'='*50}\n")
    
    session_id = f"repl-{os.getpid()}"
    history: List[Dict[str, Any]] = []
    
    orch = None
    try:
        orch = Orchestrator(session_id=session_id)
        print_success("Orchestrator initialized")
    except Exception as e:
        print_error(f"Orchestrator init failed: {e}")
        print_info("Running in fallback mode (no LLM access)")
    
    while True:
        try:
            user_input = input("arctus> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            return 0
        
        if not user_input:
            continue
        
        cmd_lower = user_input.lower()
        if cmd_lower in ("exit", "quit", "q"):
            print("Goodbye!")
            return 0
        
        if cmd_lower == "help":
            print_repl_help()
            continue
        
        if cmd_lower.startswith("config"):
            handle_config_command(user_input)
            continue
        
        if orch:
            try:
                result = orch.run_task(user_input, history=history)
                print(f"\n{result}\n")
                history.append({"role": "user", "content": user_input})
                history.append({"role": "assistant", "content": result})
            except LLMError as e:
                print_error(f"LLM Error: {e}")
            except Exception as e:
                print_error(f"Task failed: {e}")
        else:
            print_info(f"Would execute: {user_input}")
            print_info("(Orchestrator not available - check setup)")
    
    return 0


def print_repl_help() -> None:
    """Print REPL help text."""
    help_text = """
Available commands:
  <any text>      Send message to agent orchestrator
  config          Show current configuration
  config <key>    Show specific config value
  exit, quit, q   Leave the REPL
  help            Show this help
"""
    print(help_text)


def handle_config_command(raw: str) -> None:
    """Handle config subcommand in REPL."""
    parts = raw.split(None, 1)
    if len(parts) == 1:
        try:
            cfg = Config.load()
            print(json.dumps(cfg.to_dict(), indent=2))
        except Exception as e:
            print_error(f"Cannot load config: {e}")
    else:
        print_info(f"Config key: {parts[1]}")


def cmd_do(task: str, args: argparse.Namespace) -> int:
    """Execute a single task and exit."""
    print_info(f"Executing: {task}")
    
    try:
        orch = Orchestrator()
        result = orch.run_task(task)
        print(result)
        return 0
    except LLMError as e:
        print_error(f"LLM failed: {e}")
        return 1
    except Exception as e:
        print_error(f"Execution failed: {e}")
        return 1


def cmd_config(args: argparse.Namespace) -> int:
    """Print current configuration."""
    config_path = get_config_path() if 'get_config_path' in globals() else Path.home() / ".config" / "arctus" / "config.json"
    
    print(f"{APP_NAME} configuration")
    print(f"Config file: {config_path}")
    
    if config_path.exists():
        try:
            with open(config_path) as f:
                cfg = json.load(f)
            print(json.dumps(cfg, indent=2))
        except json.JSONDecodeError:
            print_error("Config file is corrupted JSON")
            return 1
    else:
        print_info("No config file found. Run 'arctus setup <provider>' to create one.")
    
    env_vars = ["OPENROUTER_API_KEY", "OLLAMA_HOST", "HF_TOKEN", "ARCTUS_TIER"]
    print("\nEnvironment variables:")
    for var in env_vars:
        val = os.environ.get(var, "")
        masked = val[:4] + "..." + val[-4:] if len(val) > 8 else "(not set)"
        print(f"  {var}={masked}")
    
    return 0


def cmd_config_set(args: argparse.Namespace) -> int:
    """Merge JSON into configuration."""
    try:
        updates = json.loads(args.json)
    except json.JSONDecodeError as e:
        print_error(f"Invalid JSON: {e}")
        return 1
    
    config_path = get_config_path() if 'get_config_path' in globals() else Path.home() / ".config" / "arctus" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    cfg = {}
    if config_path.exists():
        with open(config_path) as f:
            cfg = json.load(f)
    
    cfg.update(updates)
    
    with open(config_path, "w") as f:
        json.dump(cfg, f, indent=2)
    
    print_success(f"Config updated at {config_path}")
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    """Setup a provider preset."""
    if not SETUP_AVAILABLE:
        print_error(f"Setup module unavailable: {_IMPORT_ERROR}")
        print_info("Ensure arctus is properly installed: pip install -e .")
        return 1
    
    provider = args.provider.lower().strip()
    valid = {"ollama", "openrouter", "hf", "omniroute"}
    
    if provider not in valid:
        print_error(f"Unknown provider: {provider}")
        print_info(f"Valid providers: {', '.join(sorted(valid))}")
        return 1
    
    if provider == "omniroute":
        provider = "openrouter"
    
    try:
        kwargs = {}
        if provider == "openrouter":
            key = os.environ.get("OPENROUTER_API_KEY", "")
            if not key:
                print_info("Set OPENROUTER_API_KEY environment variable for OpenRouter")
                print_info("Example: export OPENROUTER_API_KEY=sk-or-v1-...")
        
        result = setup_provider(provider, **kwargs)
        print_success(f"Applied '{provider}' preset")
        print(f"Config written to: {result}")
        return 0
        
    except Exception as e:
        print_error(f"Setup failed: {e}")
        return 1


def cmd_status(args: argparse.Namespace) -> int:
    """Check provider health status."""
    print(f"{APP_NAME} - Provider Health Check")
    print("-" * 40)
    
    print("Ollama (local):")
    if is_ollama_running():
        models = get_ollama_models()
        print_success(f"Running - {len(models)} models available")
        for m in models[:5]:
            print(f"  - {m}")
        if len(models) > 5:
            print(f"  ... and {len(models)-5} more")
    else:
        print_error("Not running")
        print_info("Start with: ollama serve")
    
    print("\nOpenRouter (cloud):")
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if key:
        print_success("API key configured")
    else:
        print_info("No API key configured")
    
    print("\nHugging Face (free tier):")
    hf_token = os.environ.get("HF_TOKEN", "")
    if hf_token:
        print_success("Token configured")
    else:
        print_info("No token (limited access)")
    
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """Display a saved session."""
    print_info(f"Session: {args.session_id}")
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    """Reset/clear a session."""
    scope = getattr(args, "scope", "history")
    print_info(f"Reset session {args.session_id} (scope: {scope})")
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    """Launch the web dashboard."""
    try:
        from arctus.dashboard import launch_dashboard
        port = getattr(args, "port", 8080)
        launch_dashboard(port=port)
        return 0
    except ImportError:
        print_error("Dashboard module not available")
        print_info("Install with: pip install arctus-ai[dashboard]")
        return 1


# ============================================================================
# CLI PARSER SETUP
# ============================================================================

def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description=DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("--tier", "-t", choices=["fast", "strong", "free", "auto"], default="auto")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    config_parser = subparsers.add_parser("config", help="Show configuration")
    config_parser.set_defaults(func=cmd_config)
    
    config_set_parser = subparsers.add_parser("config-set", help="Set configuration JSON")
    config_set_parser.add_argument("json", help="JSON string to merge")
    config_set_parser.set_defaults(func=cmd_config_set)
    
    setup_parser = subparsers.add_parser("setup", help="Configure provider preset")
    setup_parser.add_argument("provider", choices=["ollama", "openrouter", "hf", "omniroute"])
    setup_parser.set_defaults(func=cmd_setup)
    
    status_parser = subparsers.add_parser("status", help="Check provider health")
    status_parser.set_defaults(func=cmd_status)
    
    show_parser = subparsers.add_parser("show", help="Display session")
    show_parser.add_argument("session_id", help="Session identifier")
    show_parser.set_defaults(func=cmd_show)
    
    reset_parser = subparsers.add_parser("reset", help="Clear session")
    reset_parser.add_argument("session_id", help="Session identifier")
    reset_parser.add_argument("--scope", choices=["all", "history"], default="history")
    reset_parser.set_defaults(func=cmd_reset)
    
    dash_parser = subparsers.add_parser("dashboard", help="Launch web dashboard")
    dash_parser.add_argument("--port", type=int, default=8080)
    dash_parser.set_defaults(func=cmd_dashboard)
    
    return parser


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    parser = build_parser()
    return parser.parse_args(args)


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def cli_main(args: Optional[List[str]] = None) -> int:
    raw_args = args or sys.argv[1:]
    
    if not raw_args:
        return cmd_repl(argparse.Namespace())
    
    known_commands = {
        "config", "config-set", "setup", "status",
        "show", "reset", "dashboard", "help", "-h", "--help",
        "-v", "--version"
    }
    
    first_arg = raw_args[0].lower()
    
    if first_arg in known_commands:
        parsed = parse_args(raw_args)
        if hasattr(parsed, "func"):
            return parsed.func(parsed)
        return 0
    
    task = " ".join(raw_args)
    return cmd_do(task, argparse.Namespace())


def main() -> int:
    try:
        return cli_main()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 130
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
        
