import shutil
import subprocess
import requests

def is_ollama_running():
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
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
        print("✅ Ollama server started.")
    except Exception as e:
        print(f"❌ Failed to start Ollama: {e}")


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
    print(f"Downloading {model}...")
    subprocess.run(
        ["ollama", "pull", model],
        check=False,
    )


def verify_connection():
    pass

def setup_ollama():
    print("Checking Ollama...")

    if shutil.which("ollama") is None:
        print("❌ Ollama is not installed.")
        return

    print("✅ Ollama is installed.")

    if not is_ollama_running():
    start_ollama()

    print("Checking model...")

    if not model_exists("qwen2.5-coder:32b"):
    pull_model("qwen2.5-coder:32b")
    )
    )

    print("✅ Ollama setup completed.")
