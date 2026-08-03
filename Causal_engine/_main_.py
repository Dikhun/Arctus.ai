import asyncio
import logging
from .bootstrap import CausalEngineBootstrap

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    bootstrap = CausalEngineBootstrap()
    asyncio.run(bootstrap.run())

if __name__ == "__main__":
    main()
