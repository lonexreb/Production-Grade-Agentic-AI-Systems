"""Environment-driven configuration. Secrets come from env only, never source."""

import os

# docker-compose.yml maps postgres to host port 5433 to avoid clashing with a local install
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://openagentos:openagentos@localhost:5433/openagentos",
)
