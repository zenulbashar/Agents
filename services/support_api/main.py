"""Entrypoint: python3 -m services.support_api.main (or the Docker CMD)."""
from __future__ import annotations

import logging

import uvicorn

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from .app import create_app
from .settings import Settings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    settings = Settings.from_env()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
