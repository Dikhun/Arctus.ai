#!/usr/bin/env python3
"""
Arctus AI — Setup Script
Enterprise build entry point with fallback for legacy environments.
Aligns with pyproject.toml [build-system] and [project] metadata.
"""

import sys
from pathlib import Path

# Minimum Python enforcement (matches pyproject.toml requires-python >= 3.8)
if sys.version_info < (3, 8):
    raise RuntimeError("Arctus AI requires Python 3.8 or newer.")

try:
    from setuptools import setup
except ImportError:
    raise RuntimeError(
        "setuptools is required to build Arctus AI. "
        "Install it via: pip install 'setuptools>=61'"
    ) from None

# ── Read README for long description ──────────────────────────────────────
README_PATH = Path(__file__).parent / "README.md"
long_description = README_PATH.read_text(encoding="utf-8") if README_PATH.exists() else ""

# ── Core Dependencies ──────────────────────────────────────────────────────
CORE_DEPENDENCIES: list[str] = []

OPTIONAL_DEPENDENCIES = {
    "server": ["fastapi>=0.100.0", "uvicorn[standard]>=0.23.0"],
    "yaml": ["pyyaml>=6.0"],
    "all": [
        "fastapi>=0.100.0",
        "uvicorn[standard]>=0.23.0",
        "pyyaml>=6.0",
        "httpx>=0.25.0",
        "aiohttp>=3.9.0",
        "pydantic>=2.0.0",
    ],
}

# ── Setup Invocation ───────────────────────────────────────────────────────
def main() -> None:
    """
    Legacy setup() call for environments that cannot use PEP 517/660 builds.
    Modern builds use pyproject.toml exclusively via setuptools.build_meta.
    """
    setup(
        name="arctus-ai",
        version="1.0.0",
        description=(
            "Local-first multi-agent orchestrator with MCP consortium, "
            "100-agent roster, 80% handoff cycle. "
            "Plan -> Validate -> Execute -> Verify."
        ),
        long_description=long_description,
        long_description_content_type="text/markdown",
        author="Arctus.ai",
        python_requires=">=3.8",
        license="MIT",
        packages=["arctus", "server"],
        py_modules=["main"],
        entry_points={
            "console_scripts": [
                "arctus=main:main",
            ],
        },
        install_requires=CORE_DEPENDENCIES,
        extras_require=OPTIONAL_DEPENDENCIES,
        classifiers=[
            "Programming Language :: Python :: 3",
            "Programming Language :: Python :: 3.8",
            "Programming Language :: Python :: 3.9",
            "Programming Language :: Python :: 3.10",
            "Programming Language :: Python :: 3.11",
            "Programming Language :: Python :: 3.12",
            "License :: OSI Approved :: MIT License",
            "Operating System :: OS Independent",
            "Intended Audience :: Developers",
            "Topic :: Software Development :: Libraries :: Application Frameworks",
        ],
        keywords=(
            "multi-agent orchestrator llm openai-compatible ollama "
            "openrouter omniroute runpod mcp model-context-protocol cli "
            "consortium swarm"
        ),
        zip_safe=False,
    )


if __name__ == "__main__":
    main()
