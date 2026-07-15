"""Run the FastAPI app on Windows with a SelectorEventLoop.

Python 3.14 ignores `set_event_loop_policy` for the default loop factory,
so we drive uvicorn programmatically via `asyncio.Runner(loop_factory=...)`
which is the sanctioned replacement.
"""
from __future__ import annotations

import asyncio
import selectors
import sys

import uvicorn


def _selector_loop_factory():
    return asyncio.SelectorEventLoop(selectors.SelectSelector())


async def _serve() -> None:
    config = uvicorn.Config(
        "backend.api.main:app",
        host="127.0.0.1",
        port=8001,
        log_level="warning",
        loop="asyncio",
        lifespan="on",
    )
    server = uvicorn.Server(config)
    await server.serve()


def main() -> None:
    if sys.platform == "win32":
        with asyncio.Runner(loop_factory=_selector_loop_factory) as runner:
            runner.run(_serve())
    else:
        asyncio.run(_serve())


if __name__ == "__main__":
    main()

