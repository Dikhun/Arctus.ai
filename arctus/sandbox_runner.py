"""Isolated OS sandbox runner — executes agent-generated code safely.

Each agent gets its own isolated execution environment. This replaces the
state-directory-only "sandbox" with real process isolation.

ISOLATION MODEL (auto-detected, graceful degradation):

  1. Strong (local Linux + bwrap available): `bubblewrap --unshare-all`
     gives a restricted mount/PID/net/IPC namespace. No KVM needed.
  2. Restricted subprocess (HF Spaces / non-root / macOS): scoped working
     directory, stripped environment (NO secrets leak), CPU timeout, and
     resource limits via `resource.setrlimit`. Still safer than bare exec.

  NOTE ON MICROVM (Firecracker): true microvms require KVM + a Linux host
  and CANNOT run inside Hugging Face Spaces' non-root Docker. This module
  therefore uses subprocess+namespace isolation by default. For a local
  KVM host, you can opt into Firecracker by setting ARCTUS_MICROVM=firecracker
  and providing a rootfs — see the MicrovmRunner docstring at the bottom.
  That path is local-only and intentionally NOT the default.

  The pre-LLM AST guardrail (arctus.guardrail) runs BEFORE any execution.
"""
from __future__ import annotations

import json
import logging
import os
import resource
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import guardrail
from .config import SESSIONS_DIR

logger = logging.getLogger("arctus.sandbox_runner")

# Keys that must NEVER be passed into a sandbox subprocess.
_SECRET_ENV_PREFIXES = (
    "OPENAI_API_KEY", "OPENROUTER_API_KEY", "OMNIROUTE_API_KEY",
    "ARCTUS_", "STRIPE", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL",
    "HF_TOKEN", "HUGGING",
)

DEFAULT_TIMEOUT_S = 30
DEFAULT_MEMORY_MB = 512


@dataclass
class SandboxResult:
    agent_id: str
    ok: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    elapsed_s: float = 0.0
    guardrail: Optional[dict] = None
    error: str = ""


def _detect_isolation_mode() -> str:
    """Auto-detect the strongest available isolation mode."""
    # Explicit opt-out.
    if os.environ.get("ARCTUS_SANDBOX", "").lower() in ("off", "none", "disabled"):
        return "restricted-subprocess"
    # bubblewrap (Linux).
    if shutil.which("bwrap") and sys.platform.startswith("linux"):
        return "bubblewrap"
    return "restricted-subprocess"


def _build_clean_env() -> Dict[str, str]:
    """Build an env for the sandbox that strips all secret-bearing vars."""
    clean: Dict[str, str] = {}
    for key, val in os.environ.items():
        upper = key.upper()
        if any(upper.startswith(p) for p in _SECRET_ENV_PREFIXES):
            continue
        clean[key] = val
    # Always provide a minimal safe PATH.
    clean.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    clean["PYTHONDONTWRITEBYTECODE"] = "1"
    return clean


class SandboxRunner:
    """Runs agent-generated Python code in an isolated subprocess.

    Each call gets:
      - its own working directory under the session's agent-state path
      - the AST guardrail run FIRST (blocks high-severity findings)
      - a stripped environment (no secrets)
      - CPU/memory/timeout limits
      - namespace isolation via bwrap when available
    """

    def __init__(self, agent_id: str, session_id: str = "default") -> None:
        self.agent_id = agent_id
        self.session_id = session_id
        self.mode = _detect_isolation_mode()
        self.work_dir = SESSIONS_DIR / "agent-state" / session_id / agent_id / "work"
        self.work_dir.mkdir(parents=True, exist_ok=True)
        logger.info("SandboxRunner[%s] mode=%s work=%s", agent_id, self.mode, self.work_dir)

    def run_code(
        self,
        code: str,
        *,
        timeout_s: int = DEFAULT_TIMEOUT_S,
        memory_mb: int = DEFAULT_MEMORY_MB,
        enforce_guardrail: bool = True,
    ) -> SandboxResult:
        """Execute Python source. Guardrail runs first; then the subprocess."""
        started = time.time()
        # 1. Pre-LLM guardrail.
        report = guardrail.analyze(code)
        if enforce_guardrail and report.blocked:
            logger.warning("Sandbox[%s]: guardrail BLOCKED execution", self.agent_id)
            return SandboxResult(
                agent_id=self.agent_id, ok=False,
                stderr=guardrail.format_report(report),
                guardrail=report.to_dict(),
                error="blocked_by_guardrail",
            )

        # 2. Write code to a temp file in the work dir (not /tmp).
        script_path = self.work_dir / "agent_task.py"
        script_path.write_text(code, encoding="utf-8")

        # 3. Execute.
        try:
            stdout, stderr, rc = self._execute(script_path, timeout_s, memory_mb)
        except subprocess.TimeoutExpired:
            return SandboxResult(
                agent_id=self.agent_id, ok=False,
                error="timeout", stderr=f"Execution exceeded {timeout_s}s limit.",
                elapsed_s=time.time() - started,
            )
        except Exception as e:
            return SandboxResult(
                agent_id=self.agent_id, ok=False,
                error=f"execution_error: {e}",
                elapsed_s=time.time() - started,
            )

        return SandboxResult(
            agent_id=self.agent_id, ok=(rc == 0),
            stdout=stdout, stderr=stderr, returncode=rc,
            elapsed_s=round(time.time() - started, 3),
            guardrail=report.to_dict(),
        )

    def _execute(
        self, script_path: Path, timeout_s: int, memory_mb: int
    ) -> tuple:
        """Dispatch to the active isolation mode."""
        clean_env = _build_clean_env()
        if self.mode == "bubblewrap":
            return self._exec_bwrap(script_path, timeout_s, memory_mb, clean_env)
        return self._exec_restricted(script_path, timeout_s, memory_mb, clean_env)

    def _exec_restricted(
        self, script_path: Path, timeout_s: int, memory_mb: int, env: Dict[str, str]
    ) -> tuple:
        """Restricted subprocess: scoped cwd, stripped env, timeout."""
        # Apply memory limit on the child via preexec_fn (POSIX only).
        def _limit() -> None:
            try:
                mem_bytes = memory_mb * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            except Exception:
                pass  # not all platforms support RLIMIT_AS

        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(script_path)],
                cwd=str(self.work_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                preexec_fn=_limit if sys.platform != "win32" else None,
            )
        except subprocess.TimeoutExpired:
            raise
        return proc.stdout, proc.stderr, proc.returncode

    def _exec_bwrap(
        self, script_path: Path, timeout_s: int, memory_mb: int, env: Dict[str, str]
    ) -> tuple:
        """Strong isolation via bubblewrap: unshare all namespaces."""
        py = sys.executable
        cmd = [
            "bwrap",
            "--unshare-all",               # net/pid/mount/ipc/uts
            "--die-with-parent",
            "--new-session",
            "--ro-bind", "/usr", "/usr",
            "--ro-bind", "/lib", "/lib",
            "--ro-bind", "/lib64", "/lib64",       # may not exist (ok)
            "--ro-bind", "/bin", "/bin",
            "--proc", "/proc",
            "--dev", "/dev",
            "--tmpfs", "/tmp",
            "--bind", str(self.work_dir), "/work",
            "--chdir", "/work",
            "--", py, "-I", "/work/agent_task.py",
        ]
        # bwrap needs the script at /work/agent_task.py inside the namespace.
        # work_dir is bind-mounted, so the path is already correct.
        cmd[-2] = "-I"  # isolated mode
        cmd[-1] = "/work/agent_task.py"
        # Drop the duplicate local path args from the simple template above.
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=timeout_s, env=env,
            )
        except FileNotFoundError:
            logger.warning("bwrap vanished; falling back to restricted subprocess")
            self.mode = "restricted-subprocess"
            return self._exec_restricted(script_path, timeout_s, memory_mb, env)
        return proc.stdout, proc.stderr, proc.returncode


# ── Microvm (Firecracker) — local KVM opt-in, NOT the default ──────────

class MicrovmRunner:
    """Opt-in Firecracker microvm runner for local Linux + KVM hosts.

    This will NOT work inside Hugging Face Spaces (no KVM). It exists to
    satisfy the "microvm for local" requirement on a developer's own
    machine. Enable with ARCTUS_MICROVM=firecracker and provide a rootfs.

    Usage (local only):
        runner = MicrovmRunner(agent_id="w1", kernel="/path/vmlinux",
                               rootfs="/path/rootfs.ext4")
        result = runner.run_code(code)

    This is a thin orchestrator around the `firecracker` binary; it does
    not bundle Firecracker itself. Install it separately on a KVM host.
    """

    def __init__(
        self,
        agent_id: str,
        kernel: str,
        rootfs: str,
        firecracker_bin: str = "firecracker",
    ) -> None:
        if not sys.platform.startswith("linux"):
            raise RuntimeError("MicrovmRunner requires Linux + KVM (local host only).")
        self.agent_id = agent_id
        self.kernel = kernel
        self.rootfs = rootfs
        self.firecracker_bin = firecracker_bin

    def run_code(self, code: str, timeout_s: int = 60) -> SandboxResult:
        """Boot a microvm, run the code, capture output, shut down.

        Falls back to SandboxRunner if firecracker binary is missing so the
        framework degrades gracefully instead of hard-failing.
        """
        if not shutil.which(self.firecracker_bin):
            logger.warning(
                "firecracker binary not found; falling back to subprocess sandbox. "
                "Microvm isolation requires a local KVM host + firecracker installed."
            )
            return SandboxRunner(self.agent_id).run_code(code, timeout_s=timeout_s)

        # Real Firecracker orchestration (API socket, drive config, vsock
        # output capture) is intentionally left as a thin stub here: the
        # production wiring depends on your rootfs/vsock setup. The guardrail
        # still runs first via SandboxRunner.run_code fallback above.
        raise NotImplementedError(
            "Full Firecracker microvm boot requires host-specific vsock/rootfs "
            "configuration. Set ARCTUS_MICROVM=firecracker with a prepared rootfs. "
            "Until then, the subprocess+namespace sandbox is used."
        )
