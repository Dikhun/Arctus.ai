import shutil

if shutil.which("uv") is None:
    print("Installing uv...")
    # install automaticallyimport asyncio
from pathlib import Path
from typing import Optional


class ArctusAgentSupervisor:
    """
    Simple autonomous supervisor for the Digital Twin engine.
    """

    def __init__(self, script_path: str):
        self.script_path = Path(script_path)
        self.process: Optional[asyncio.subprocess.Process] = None
        self.running = True

    async def ensure_uv(self):
        try:
            proc = await asyncio.create_subprocess_exec(
                "uv",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            if proc.returncode != 0:
                raise FileNotFoundError

            print("[Supervisor] uv detected.")

        except FileNotFoundError:
            print("[ERROR] 'uv' is not installed.")
            raise SystemExit(1)

    async def start(self):
        await self.ensure_uv()

        if not self.script_path.exists():
            print(f"[ERROR] {self.script_path} not found.")
            raise SystemExit(1)

        print(f"[Supervisor] Starting {self.script_path}...")

        self.process = await asyncio.create_subprocess_exec(
            "uv",
            "run",
            str(self.script_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        print(f"[Supervisor] PID: {self.process.pid}")

        asyncio.create_task(self.log_output())

    async def log_output(self):
        while self.process and self.process.stdout:
            line = await self.process.stdout.readline()
            if not line:
                break
            print(line.decode().rstrip())

    async def monitor(self):
        while self.running:
            if self.process is None:
                await asyncio.sleep(2)
                continue

            code = self.process.returncode

            if code is not None:
                print(f"[Supervisor] Process exited ({code}). Restarting...")
                await asyncio.sleep(2)
                await self.start()

            await asyncio.sleep(2)

    async def shutdown(self):
        self.running = False

        if self.process and self.process.returncode is None:
            print("[Supervisor] Stopping process...")
            self.process.terminate()
            await self.process.wait()

        print("[Supervisor] Shutdown complete.")


async def main():
    supervisor = ArctusAgentSupervisor("digital_twin.py")

    await supervisor.start()

    monitor_task = asyncio.create_task(supervisor.monitor())

    try:
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping Arctus...")

    finally:
        monitor_task.cancel()
        await supervisor.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
