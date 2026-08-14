"""HR approval API: serve the runtime approval endpoints for the HR agent.

Run:  python -m apps.hr.api      (then GET /runs/{id}, POST /runs/{id}/approve)
"""

import uvicorn

from apps.hr.agent import build_graph
from runtime.api import create_app

app = create_app(build_graph)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
