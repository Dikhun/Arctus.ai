"""
Arctus AI Setup Module

Contains installers and configuration utilities for supported providers.
"""

import shutil
import subprocess
import requests
import time

__version__ = "1.0.0"

OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5-coder:32b"


def is_ollama_installed():
    return shutil.which("ollama") is not None


def is_ollama_running():
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def start_ollama():
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("Starting Ollama server...")
        for _ in range(15):
            if is_ollama_running():
                print("✅ Ollama server is running.")
                return True
            time.sleep(1)
        print("❌ Ollama failed to start.")
        return False
    except Exception as e:
        print(f"❌ Failed to start Ollama: {e}")
        return False


def model_exists(model):
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            check=False,
        )
        return model in result.stdout
    except Exception:
        return False


def pull_model(model):
    print(f"Downloading model: {model}")
    result = subprocess.run(
        ["ollama", "pull", model],
        check=False,
    )
    return result.returncode == 0


def verify_connection():
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if response.status_code == 200:
            print("✅ Ollama connection verified.")
            return True
        print("❌ Ollama returned an unexpected response.")
        return False
    except Exception as e:
        print(f"❌ Cannot connect to Ollama: {e}")
        return False


def setup_ollama():
    print("========== Arctus Ollama Setup ==========")

    if not is_ollama_installed():
        print("❌ Ollama is not installed. Run 'brew install ollama' or download it from ollama.com")
        return False

    if not is_ollama_running():
        if not start_ollama():
            return False
    else:
        print("✅ Ollama server already running.")

    print("Checking local models...")

    if not model_exists(DEFAULT_MODEL):
        if not pull_model(DEFAULT_MODEL):
            print("❌ Failed to download model.")
            return False
    else:
        print(f"✅ {DEFAULT_MODEL} already installed.")

    if not verify_connection():
        return False

    print("=========================================")
    print("✅ Arctus is ready to use with Ollama.")
    print(f"Provider : Ollama")
    print(f"Endpoint : {OLLAMA_URL}")
    print(f"Model    : {DEFAULT_MODEL}")

    return True
  
