"""Run with python -m gather."""

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "gather.app:app",
        host="127.0.0.1",
        port=int(os.environ.get("GATHER_PORT", "8010")),
    )
