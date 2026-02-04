#!/usr/bin/env python3
"""Run the Cuttle Web API server."""

import uvicorn
from pathlib import Path


def main():
    """Run the server."""
    # Load .env file if it exists
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)
        print(f"Loaded environment from {env_file}")

    uvicorn.run(
        "web.api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="debug",
    )


if __name__ == "__main__":
    main()
