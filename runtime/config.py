"""Environment-driven configuration. Secrets come from env only, never source.

A local `.env` file (gitignored) is loaded into os.environ at import — existing
environment always wins. # ponytail: 10-line stdlib parse over python-dotenv.
"""

import os
from pathlib import Path


def _load_dotenv() -> None:
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv()

# docker-compose.yml maps postgres to host port 5433 to avoid clashing with a local install
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://openagentos:openagentos@localhost:5433/openagentos",
)
