import shutil
import subprocess


def setup_ollama():
    print("Checking Ollama...")

    if shutil.which("ollama") is None:
        print("❌ Ollama is not installed.")
        return

    print("✅ Ollama is installed.")

    try:
        subprocess.run(
            ["ollama", "serve"],
            check=False
        )
    except Exception:
        pass

    print("Checking model...")

    subprocess.run(
        ["ollama", "pull", "llama3.2"],
        check=False
    )

    print("✅ Ollama setup completed.")
