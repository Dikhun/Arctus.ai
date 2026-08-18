from setuptools import setup, find_packages
import os

# Read requirements
requirements = [
    "requests>=2.31.0",
    "pydantic>=2.0.0",
    "rich>=13.0.0",
    "click>=8.1.0",
    "pyyaml>=6.0",
    "python-dotenv>=1.0.0",
    "httpx>=0.25.0",
    "aiohttp>=3.9.0",
    "websockets>=12.0",
    "fastapi>=0.104.0",
    "uvicorn>=0.24.0",
    "jinja2>=3.1.0",
]

setup(
    name="arctus-ai",
    version="1.0.0",
    description="Local-first multi-agent orchestration framework",
    author="Arctus Team",
    python_requires=">=3.9",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=requirements,
    extras_require={
        "dev": ["pytest>=7.0", "black>=23.0", "mypy>=1.0"],
        "ollama": ["ollama>=0.1.0"],
    },
    entry_points={
        "console_scripts": [
            "arctus=arctus.main:cli_main",
            "arctus-dashboard=arctus.dashboard:launch_dashboard",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
