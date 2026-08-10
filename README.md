/storage/emulated/0/Download/1000089911.png

---

---
<parameter name="language">markdown</parameter>
# Arctus AI - Setup Commands Reference

## Project Structure

```
Arctus.ai/
├── setup.py                    # Package setup (FILE 1)
├── pyproject.toml              # Modern Python packaging
├── src/
│   └── arctus/
│       ├── __init__.py         # Package init (FILE 2)
│       ├── main.py             # CLI entry point (FILE 3)
│       ├── setup.py            # Provider presets (FILE 4)
│       ├── llm.py              # LLM client (FILE 5)
│       ├── config/
│       │   └── __init__.py     # Config management
│       ├── orchestrator/
│       │   └── __init__.py     # Agent orchestration
│       ├── agent/
│       │   └── __init__.py     # Agent definitions
│       └── dashboard/
│           └── __init__.py     # Web dashboard
├── venv/                       # Virtual environment
└── repos/                      # Cloned repositories
```

---

## macOS Setup Commands

```bash
# ============================================
# 1. CLONE AND ENTER PROJECT
# ============================================
git clone https://github.com/Dikhun/Arctus.ai.git
cd Arctus.ai

# ============================================
# 2. CREATE VIRTUAL ENVIRONMENT
# ============================================
python3 -m venv venv

# ============================================
# 3. ACTIVATE VIRTUAL ENVIRONMENT
# ============================================
source venv/bin/activate

# ============================================
# 4. UPGRADE PIP AND INSTALL DEPENDENCIES
# ============================================
python3 -m pip install --upgrade pip
pip install -r requirements.txt 2>/dev/null || echo "No requirements.txt, using setup.py"

# ============================================
# 5. INSTALL PACKAGE IN EDITABLE MODE
# ============================================
pip install -e .

# ============================================
# 6. VERIFY INSTALLATION
# ============================================
python3 -c "import arctus; print('OK:', arctus.__version__)"

# ============================================
# 7. SETUP PROVIDER (Choose one)
# ============================================

# --- OPTION A: Ollama (Local, Free) ---
# First install Ollama from https://ollama.com
# Then:
ollama serve &                    # Start Ollama server in background
ollama pull llama3.1              # Download a model
arctus setup ollama               # Configure Arctus for Ollama
arctus status                     # Verify

# --- OPTION B: OpenRouter (Cloud, API Key Required) ---
# Get key from https://openrouter.ai/keys
export OPENROUTER_API_KEY="sk-or-v1-YOUR-KEY-HERE"
arctus setup openrouter           # Configure for OpenRouter
arctus status                     # Verify

# --- OPTION C: OmniRoute (OpenRouter with Routing) ---
# OmniRoute uses OpenRouter backend with smart routing
export OMNIROUTE_API_KEY="sk-or-v1-YOUR-KEY-HERE"  # or reuse OPENROUTER_API_KEY
arctus setup omniroute            # Configure for OmniRoute
arctus status                     # Verify

# --- OPTION D: Hugging Face (Free Tier) ---
export HF_TOKEN="hf_YOUR_TOKEN_HERE"
arctus setup hf                   # Configure for HF Inference API
arctus status                     # Verify

# ============================================
# 8. LAUNCH DASHBOARD OR CLI
# ============================================

# Interactive REPL
arctus

# Run single task
arctus "refactor my parser"

# Launch web dashboard
arctus dashboard --port 8080

# Open dashboard in browser (macOS)
open http://localhost:8080
```

---

## Windows Setup Commands (PowerShell)

```powershell
# ============================================
# 1. CLONE AND ENTER PROJECT
# ============================================
git clone https://github.com/Dikhun/Arctus.ai.git
cd Arctus.ai

# ============================================
# 2. CREATE VIRTUAL ENVIRONMENT
# ============================================
python -m venv venv

# ============================================
# 3. ACTIVATE VIRTUAL ENVIRONMENT
# ============================================
.\venv\Scripts\Activate.ps1

# If execution policy blocks activation, run:
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# ============================================
# 4. UPGRADE PIP AND INSTALL
# ============================================
python -m pip install --upgrade pip
pip install -e .

# ============================================
# 5. VERIFY INSTALLATION
# ============================================
python -c "import arctus; print('OK:', arctus.__version__)"

# ============================================
# 6. SETUP PROVIDER (Choose one)
# ============================================

# --- OPTION A: Ollama (Local) ---
# Install Ollama from https://ollama.com/download/windows
# In separate PowerShell:
Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
ollama pull llama3.1
arctus setup ollama
arctus status

# --- OPTION B: OpenRouter ---
$env:OPENROUTER_API_KEY = "sk-or-v1-YOUR-KEY-HERE"
arctus setup openrouter
arctus status

# --- OPTION C: OmniRoute ---
$env:OMNIROUTE_API_KEY = "sk-or-v1-YOUR-KEY-HERE"
# or reuse OpenRouter key:
$env:OMNIROUTE_API_KEY = $env:OPENROUTER_API_KEY
arctus setup omniroute
arctus status

# --- OPTION D: Hugging Face ---
$env:HF_TOKEN = "hf_YOUR_TOKEN_HERE"
arctus setup hf
arctus status

# ============================================
# 7. LAUNCH
# ============================================

# Interactive mode
arctus

# Single task
arctus "analyze this code"

# Dashboard
arctus dashboard --port 8080
start http://localhost:8080
```

---

## Windows Setup Commands (CMD / Batch)

```cmd
:: ============================================
:: 1. CLONE AND ENTER
:: ============================================
git clone https://github.com/Dikhun/Arctus.ai.git
cd Arctus.ai

:: ============================================
:: 2. CREATE AND ACTIVATE VENV
:: ============================================
python -m venv venv
venv\Scripts\activate.bat

:: ============================================
:: 3. INSTALL
:: ============================================
python -m pip install --upgrade pip
pip install -e .

:: ============================================
:: 4. SETUP PROVIDER
:: ============================================

:: Ollama
set OLLAMA_HOST=http://localhost:11434
arctus setup ollama

:: OpenRouter
set OPENROUTER_API_KEY=sk-or-v1-YOUR-KEY
arctus setup openrouter

:: OmniRoute
set OMNIROUTE_API_KEY=sk-or-v1-YOUR-KEY
arctus setup omniroute

:: ============================================
:: 5. RUN
:: ============================================
arctus
arctus dashboard
```

---

## Cross-Platform Quick Start Script

Save as `setup.sh` (macOS/Linux) or `setup.ps1` (Windows):

### `setup.sh` (macOS/Linux)

```bash
#!/bin/bash
set -e

echo "=== Arctus AI Setup ==="

# Parse arguments
PROVIDER=${1:-ollama}
API_KEY=${2:-}

# Clone if needed
if [ ! -d "Arctus.ai" ]; then
    git clone https://github.com/Dikhun/Arctus.ai.git
fi
cd Arctus.ai

# Python setup
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -e .

# Configure provider
case $PROVIDER in
    ollama)
        which ollama >/dev/null || { echo "Install Ollama first: https://ollama.com"; exit 1; }
        ollama serve &
        sleep 2
        ollama pull llama3.1 2>/dev/null || true
        arctus setup ollama
        ;;
    openrouter)
        if [ -z "$API_KEY" ] && [ -z "$OPENROUTER_API_KEY" ]; then
            echo "ERROR: Set OPENROUTER_API_KEY or pass as argument"
            exit 1
        fi
        [ -n "$API_KEY" ] && export OPENROUTER_API_KEY="$API_KEY"
        arctus setup openrouter
        ;;
    omniroute)
        [ -n "$API_KEY" ] && export OMNIROUTE_API_KEY="$API_KEY"
        arctus setup omniroute
        ;;
    hf|huggingface)
        [ -n "$API_KEY" ] && export HF_TOKEN="$API_KEY"
        arctus setup hf
        ;;
    *)
        echo "Unknown provider: $PROVIDER"
        echo "Usage: $0 [ollama|openrouter|omniroute|hf] [api-key]"
        exit 1
        ;;
esac

arctus status
echo ""
echo "Setup complete! Run 'arctus' for interactive mode"
echo "Or 'arctus dashboard' for web interface"
```

### `setup.ps1` (Windows PowerShell)

```powershell
param(
    [string]$Provider = "ollama",
    [string]$ApiKey = ""
)

Write-Host "=== Arctus AI Setup ===" -ForegroundColor Cyan

# Clone
if (-not (Test-Path "Arctus.ai")) {
    git clone https://github.com/Dikhun/Arctus.ai.git
}
Set-Location Arctus.ai

# Python setup
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .

# Configure provider
switch ($Provider) {
    "ollama" {
        $ollama = Get-Command ollama -ErrorAction SilentlyContinue
        if (-not $ollama) {
            Write-Error "Install Ollama from https://ollama.com/download/windows"
            exit 1
        }
        Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep 2
        ollama pull llama3.1
        arctus setup ollama
    }
    "openrouter" {
        if ($ApiKey) { $env:OPENROUTER_API_KEY = $ApiKey }
        if (-not $env:OPENROUTER_API_KEY) {
            Write-Error "Set OPENROUTER_API_KEY environment variable or pass -ApiKey"
            exit 1
        }
        arctus setup openrouter
    }
    "omniroute" {
        if ($ApiKey) { $env:OMNIROUTE_API_KEY = $ApiKey }
        arctus setup omniroute
    }
    "hf" {
        if ($ApiKey) { $env:HF_TOKEN = $ApiKey }
        arctus setup hf
    }
    default {
        Write-Error "Unknown provider: $Provider"
        exit 1
    }
}

arctus status
Write-Host "`nSetup complete! Run 'arctus' for interactive mode" -ForegroundColor Green
```

---

## CLI Commands Reference

| Command | Description |
|---------|-------------|
| `arctus` | Start interactive REPL |
| `arctus "do something"` | Run single task |
| `arctus config` | Show configuration |
| `arctus config-set '{"key":"value"}'` | Update config |
| `arctus setup ollama` | Configure Ollama |
| `arctus setup openrouter` | Configure OpenRouter |
| `arctus setup omniroute` | Configure OmniRoute |
| `arctus setup hf` | Configure Hugging Face |
| `arctus status` | Check all providers |
| `arctus dashboard` | Launch web dashboard |
| `arctus show <session-id>` | View session |
| `arctus reset <session-id>` | Clear session |
| `arctus --help` | Show help |

---

## Environment Variables

| Variable | Used By | Example |
|----------|---------|---------|
| `OPENROUTER_API_KEY` | OpenRouter | `sk-or-v1-...` |
| `OMNIROUTE_API_KEY` | OmniRoute | `sk-or-v1-...` |
| `OLLAMA_HOST` | Ollama | `http://localhost:11434` |
| `HF_TOKEN` | Hugging Face | `hf_...` |

---

## Dashboard Access

After running `arctus dashboard`:

- **Local**: http://localhost:8080
- **Network**: http://YOUR_IP:8080

Connect other CLI tools via the API:
```bash
# Get status
curl http://localhost:8080/api/status

# The dashboard exposes REST endpoints for integration
```
---

## Provider presets

```bash
python -c "from arctus import presets; presets.apply_preset('openrouter')"
python -c "from arctus import presets; presets.apply_preset('omniroute_local')"
python -c "from arctus import presets; presets.apply_preset('ollama')"
python -c "from arctus import presets; presets.apply_preset('openai')"
```

Env vars (take precedence): `OPENROUTER_API_KEY`, `OMNIROUTE_API_KEY`,
`ARCTUS_OMNIROUTE_KEY`, `OPENAI_API_KEY`, `ARCTUS_FAST_*`, `ARCTUS_STRONG_*`.

---

## CLI usage

```bash
python main.py                       # interactive REPL
python main.py "do something"        # one-shot task
python main.py config                # show config
python main.py config-set '<json>'   # merge settings
python main.py setup ollama          # connect to local Ollama
python main.py setup openrouter      # connect to OpenRouter
python main.py setup hf              # apply free-tier preset
python main.py connect <hf-space-url>  # link to a remote HF instance
python main.py show <session-id>     # view saved session
python main.py reset <session-id> --scope all
python main.py -v "task"             # verbose logging
```

REPL keys: type a task + Enter · `:reset` to clear · `:quit` to exit.

---

## Programmatic use

```python
from arctus import Config, QueenAgent, build_roster, mcp, presets

presets.apply_preset("openrouter")          # strong tier -> OpenRouter
cfg = Config()
roster = build_roster()                      # 100 agents
print(len(roster), "agents available")

# Add an MCP connector (HTTP transport)
mcp.add_connector("github", {
    "transport": "http",
    "url": "https://mcp.example.com/jsonrpc",
    "tools": ["search", "read"],
})

queen = QueenAgent(cfg)
result = queen.run("refactor auth + add tests", session_id="job-1")
for w in result.work:
    print(w["step"], "->", w["result"][:80])
```

---

## The 80% handoff cycle

```
Agent A runs steps… crosses 80% of its context budget
   ├─ fires a small local-model call to summarize (done / next)
   ├─ writes the summary into the sandbox state file
   ├─ clears its OWN in-memory history (frees tokens)
   └─ WAITS
Agent B starts with a FRESH budget, reads the summary, continues.
   When B crosses 80%, the cycle repeats.
```

Only the summary crosses the boundary — never the full raw history. "Sandbox"
here = a state directory + memory clear, not an OS-level jail. For OS-level
isolation, run each agent in its own container.

---

## Agent infrastructure

### Parallel subtask execution (Queen pipeline)

For complex tasks the planner breaks the work into subtasks, then fans them
out to **parallel worker threads** — each with its own isolated context window.
Simple prompts bypass all sub-agents and return from a single LLM call.

- Workers per tier: free=1, tier1=2, tier2=4, tier3=6 (controlled by `config.max_workers`).
- **Per-step context**: each worker receives only its own step detail + the titles of
  dependency steps — never the full conversation history. This keeps token usage low.
- **Circuit breaker**: 3 consecutive failures on a step halts that worker and escalates
  to a higher-tier model once before failing gracefully.

```python
from arctus import QueenAgent, Config
queen = QueenAgent(Config())
result = queen.run("build a REST API with auth + tests", session_id="job-1")
# result.work is a list of parallel step results
```

### Isolated sandbox per agent (`arctus/sandbox_runner.py`)

Each agent executes generated code in its own isolated subprocess:

- **Bubblewrap** (Linux + `bwrap`): full namespace isolation (net/pid/mount/ipc).
- **Restricted subprocess** (HF Spaces / macOS, default): scoped working directory,
  stripped environment (NO secret keys leak), CPU/memory/timeout limits.
- Auto-detects the strongest available mode. Override with `ARCTUS_SANDBOX`.

```python
from arctus.sandbox_runner import SandboxRunner
runner = SandboxRunner(agent_id="w1", session_id="job-1")
result = runner.run_code("print('hello from sandbox')")
# result.ok, result.stdout, result.stderr, result.guardrail
```

For **local KVM hosts** wanting true microvm isolation (Firecracker), see
`MicrovmRunner` — opt-in, local-only (cannot run inside HF Spaces' non-root Docker).

### AST static-analysis guardrail (`arctus/guardrail.py`)

A deterministic pre-execution gate that flags dangerous code before it runs
(no LLM needed, stdlib `ast` only). Blocks `eval`/`exec`/`os.system`/`shutil.rmtree`,
warns on `subprocess`/file-writes/network. Runs inside every sandbox.

```python
from arctus.guardrail import analyze, format_report
report = analyze(agent_generated_code)
if report.blocked:
    print(format_report(report))  # return findings to the agent for a retry
```

### Context Offload Protocol (`arctus/context.py`)

When an agent hits ~80% of its context budget, it executes the formal offload
protocol: stops generation, compiles a structured handoff document
(task status / progress / pending steps / blockers), writes it to the sandbox
state file, and notifies the supervisor for a clean handoff to the next agent.

### Computer-use: display + browser automation (`arctus/computer_use.py`)

Agents can interact with a local display (mouse/keyboard/screenshots) and a
headless browser. The screenshot-reason-act loop captures state, feeds it to
the LLM, executes the returned tool call, and repeats. Use `tier: "computer-use"`
in a planned step to dispatch to this loop.

```python
from arctus.computer_use import agent_execution_loop, take_screenshot
result = agent_execution_loop("open the calculator and compute 2+2", llm_client)
```

Requires (installed automatically in the Docker image): `xvfb`, `pyautogui`,
`playwright`, `pillow`, Chromium.

---

## Consortium

```python
from arctus.consortium import ConsortiumHub, Peer, ConsortiumTask
import time

hub = ConsortiumHub()
# https only (or http://localhost). No plain http over the internet.
hub.add_peer(Peer(
    name="lab-box",
    base_url="https://lab.example.com",
    shared_secret="long-random-secret",
))
hub.push_to_peer("lab-box", ConsortiumTask(
    task_id="t1", prompt="summarize this repo", origin="me",
    submitted_at=time.time(),
))
```

---

## Layout

```
arctus.ai/
├── arctus/
│   ├── __init__.py        # public API
│   ├── config.py          # Config, Tier (env + JSON)
│   ├── llm.py             # OpenAI-compatible client (stdlib urllib)
│   ├── orchestrator.py    # QueenAgent: Plan -> Validate -> Execute -> Verify
│   ├── agents.py          # 100-agent roster
│   ├── mcp.py             # up to 200 MCP connectors
│   ├── dcr.py             # Dynamic Context Router (tool/agent ranking)
│   ├── consortium.py      # peer-to-peer task sharing
│   ├── sandbox.py         # 80% handoff cycle with summarization
│   ├── sandbox_runner.py  # isolated subprocess sandbox + microvm support
│   ├── guardrail.py       # AST static-analysis guardrail (pre-execution)
│   ├── computer_use.py    # display + browser automation (screenshot-reason-act)
│   ├── context.py         # IsolatedContextWindow, StateDir, Context Offload Protocol
│   ├── session.py         # file-backed sessions
│   ├── rate_limit.py      # per-session rolling 60s window
│   └── presets.py         # OpenRouter / OmniRoute / Ollama / OpenAI
├── server/
│   └── app.py             # FastAPI on :7860, MCP + consortium endpoints
├── web/
│   ├── index.html         # glassmorphism dashboard
│   ├── style.css
│   └── app.js
├── scripts/
│   └── clone_repos.py     # opt-in fetch of the 12 reference repos
├── repos.yaml             # the 12 third-party repos (opt-in)
├── Dockerfile             # public non-root container (port 7860)
├── docker-compose.yml     # user compose with reference repo volume
├── main.py                # CLI + REPL
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## Reference repos (opt-in)

30+ third-party repos are listed in `repos.yaml`. They are NOT cloned
automatically. Run once:

```bash
python scripts/clone_repos.py
```

They land in `./repos/` and are mounted **read-only** into the Docker container
so agents can read them as grounding material. You are responsible for
respecting each repo's license.

---

## Safety

- No network listener is opened by the CLI. The CLI only makes **outbound**
  calls to the model endpoints you configured.
- The FastAPI server listens on port 7860 (you opted into it by running it).
- Provider keys come from your env (or HF Spaces Secrets). No client-supplied
  key headers are read or forwarded.
- MCP stdio connectors run commands YOU listed in config — never commands
  derived from HTTP request bodies.
- Consortium peers must be explicitly added by URL (https or localhost only)
  with a shared secret. No anonymous discovery.

---

## License

MIT.
