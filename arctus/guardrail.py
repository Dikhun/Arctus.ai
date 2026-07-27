"""AST & Deterministic Static Analyzers (Pre-LLM Guardrail).

Runs BEFORE any agent-generated code is executed in the sandbox. This is a
deterministic, zero-dependency gate (Python stdlib `ast` only) that flags
dangerous operations without invoking an LLM. Findings are classified by
severity; high-severity findings block execution.

Use:
    from arctus.guardrail import analyze, GuardrailReport
    report = analyze(code_string)
    if report.blocked:
        # refuse to run — return findings to the agent for a retry
"""
from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger("arctus.guardrail")

# Severity levels
BLOCK = "block"   # refuse execution
WARN = "warn"     # log + allow, but flag for review
INFO = "info"     # informational only


@dataclass
class Finding:
    rule: str
    severity: str          # BLOCK | WARN | INFO
    message: str
    lineno: int = 0
    detail: str = ""


@dataclass
class GuardrailReport:
    findings: List[Finding] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(f.severity == BLOCK for f in self.findings)

    @property
    def has_warnings(self) -> bool:
        return any(f.severity == WARN for f in self.findings)

    def blockers(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == BLOCK]

    def to_dict(self) -> dict:
        return {
            "blocked": self.blocked,
            "has_warnings": self.has_warnings,
            "findings": [
                {"rule": f.rule, "severity": f.severity, "message": f.message,
                 "lineno": f.lineno, "detail": f.detail}
                for f in self.findings
            ],
        }


# ── Rule implementations ──────────────────────────────────────────────
# Each rule is a visitor method or a post-parse scan.

_DANGEROUS_NAMES = {
    "eval": "eval() executes arbitrary code from strings",
    "exec": "exec() executes arbitrary code from strings",
    "compile": "compile() can build code objects for dynamic execution",
    "__import__": "__import__ enables arbitrary module loading",
    "globals": "globals() exposes the runtime namespace",
    "locals": "locals() exposes the local namespace",
    "breakpoint": "breakpoint() drops into a debugger",
    "input": "input() may block on stdin in a sandbox",
}

_DANGEROUS_ATTRS = {
    # os module
    "system": ("os.system", BLOCK, "os.system() runs shell commands"),
    "popen": ("os.popen", BLOCK, "os.popen() runs shell commands"),
    "execv": ("os.execv", BLOCK, "os.execv* replaces the process"),
    "execve": ("os.execve", BLOCK, "os.execve replaces the process"),
    "fork": ("os.fork", BLOCK, "os.fork spawns processes"),
    "kill": ("os.kill", WARN, "os.kill sends signals to processes"),
    "remove": ("os.remove", WARN, "os.remove deletes files"),
    "unlink": ("os.unlink", WARN, "os.unlink deletes files"),
    "rmdir": ("os.rmdir", WARN, "os.rmdir deletes directories"),
    "removedirs": ("os.removedirs", WARN, "os.removedirs deletes directory trees"),
    # shutil
    "rmtree": ("shutil.rmtree", BLOCK, "shutil.rmtree deletes directory trees"),
    # subprocess
    "call": ("subprocess.call", WARN, "subprocess call — inspect shell= and args"),
    "run": ("subprocess.run", WARN, "subprocess run — inspect shell= and args"),
    "Popen": ("subprocess.Popen", WARN, "subprocess.Popen — inspect shell= and args"),
    "check_output": ("subprocess.check_output", WARN, "subprocess.check_output — inspect shell= and args"),
}


class _GuardrailVisitor(ast.NodeVisitor):
    """Walks the AST and collects findings."""

    def __init__(self) -> None:
        self.findings: List[Finding] = []

    # bare name calls: eval(...), exec(...), __import__(...)
    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        # Direct name call: eval(...)
        if isinstance(func, ast.Name) and func.id in _DANGEROUS_NAMES:
            msg = _DANGEROUS_NAMES[func.id]
            sev = BLOCK if func.id in ("eval", "exec", "__import__") else WARN
            self.findings.append(Finding(
                rule=f"dangerous-name:{func.id}", severity=sev,
                message=msg, lineno=getattr(node, "lineno", 0),
            ))
        # Attribute call: os.system(...), shutil.rmtree(...)
        if isinstance(func, ast.Attribute) and func.attr in _DANGEROUS_ATTRS:
            qual, sev, msg = _DANGEROUS_ATTRS[func.attr]
            # Special-case subprocess with shell=True → escalate to BLOCK.
            if func.attr in ("call", "run", "Popen", "check_output"):
                sev = self._subprocess_severity(node, sev)
            self.findings.append(Finding(
                rule=f"dangerous-attr:{qual}", severity=sev,
                message=msg, lineno=getattr(node, "lineno", 0),
            ))
        self.generic_visit(node)

    def _subprocess_severity(self, node: ast.Call, default: str) -> str:
        """shell=True on a subprocess call is a BLOCK."""
        for kw in node.keywords:
            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                return BLOCK
        return default

    # import os / import subprocess — info-level (not blocked, but tracked)
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name in ("os", "subprocess", "shutil", "socket", "ctypes"):
                self.findings.append(Finding(
                    rule=f"import:{alias.name}", severity=INFO,
                    message=f"imports {alias.name} (tracked)", lineno=node.lineno,
                ))
        self.generic_visit(node)

    # network: socket.socket(...)
    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr == "socket" and isinstance(node.value, ast.Name) and node.value.id == "socket":
            self.findings.append(Finding(
                rule="network:socket", severity=WARN,
                message="socket usage opens network connections",
                lineno=getattr(node, "lineno", 0),
            ))
        self.generic_visit(node)

    # open(..., "w"/"a"/"x") file writes — warn (could clobber files)
    def _check_open_writes(self, tree: ast.AST) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value[:1] in ("w", "a", "x"):
                        self.findings.append(Finding(
                            rule="file:write", severity=WARN,
                            message=f"open() with write mode {arg.value!r} may modify files",
                            lineno=getattr(node, "lineno", 0),
                        ))


def analyze(code: str) -> GuardrailReport:
    """Parse + statically analyze Python source. Never raises on bad syntax
    (returns a single BLOCK finding instead) so the caller can report cleanly.
    """
    report = GuardrailReport()
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        report.findings.append(Finding(
            rule="syntax-error", severity=BLOCK,
            message=f"code failed to parse: {e.msg}", lineno=e.lineno or 0,
            detail=f"line {e.lineno}: {e.text}",
        ))
        return report

    visitor = _GuardrailVisitor()
    visitor.visit(tree)
    visitor._check_open_writes(tree)
    report.findings = visitor.findings

    if report.blocked:
        logger.warning("Guardrail BLOCKED execution: %d blocker(s)", len(report.blockers()))
    elif report.has_warnings:
        logger.info("Guardrail: %d warning(s), allowing execution", len(report.findings))
    return report


def format_report(report: GuardrailReport) -> str:
    """Human-readable summary for returning to the agent."""
    lines = []
    if report.blocked:
        lines.append("❌ BLOCKED by static-analysis guardrail:")
        for f in report.blockers():
            lines.append(f"  - line {f.lineno}: {f.message} [{f.rule}]")
    elif report.has_warnings:
        lines.append("⚠ Warnings from static-analysis guardrail:")
        for f in report.findings:
            if f.severity == WARN:
                lines.append(f"  - line {f.lineno}: {f.message} [{f.rule}]")
    else:
        lines.append("✅ Static-analysis guardrail: clean")
    return "\n".join(lines)
