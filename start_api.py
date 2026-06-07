#!/usr/bin/env python3
"""
Start the FastAPI server for the Financial News Platform.

Usage:
    python start_api.py              # Run with defaults (localhost:8000)
    python start_api.py --host 0.0.0.0 --port 8001  # Custom host/port
"""
import uvicorn
import sys
from pathlib import Path

# Add project root to path
root = Path(__file__).parent
sys.path.insert(0, str(root))

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv(root / ".env", override=True)

import argparse

# ──────────────────────────────────────────────────────────────────────────
# Parse arguments
# ──────────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(
    description="Start the Financial News Platform API server"
)
parser.add_argument(
    "--host",
    default="127.0.0.1",
    help="Host to bind to (default: 127.0.0.1)"
)
parser.add_argument(
    "--port",
    type=int,
    default=8000,
    help="Port to bind to (default: 8000)"
)
parser.add_argument(
    "--reload",
    action="store_true",
    default=True,
    help="Enable auto-reload on code changes (default: True)"
)
parser.add_argument(
    "--no-reload",
    action="store_true",
    help="Disable auto-reload"
)
parser.add_argument(
    "--log-level",
    default="info",
    choices=["critical", "error", "warning", "info", "debug", "trace"],
    help="Log level (default: info)"
)

args = parser.parse_args()

# ──────────────────────────────────────────────────────────────────────────
# Run server
# ──────────────────────────────────────────────────────────────────────────

if args.no_reload:
    reload = False
else:
    reload = args.reload

print(f"""
╔════════════════════════════════════════════════════════════════════════╗
║       Financial News Platform API                                      ║
╠════════════════════════════════════════════════════════════════════════╣
║  Starting Uvicorn server...                                            ║
║  Host:      {args.host:<54}║
║  Port:      {args.port:<54}║
║  Reload:    {str(reload):<54}║
║  Log Level: {args.log_level:<54}║
║                                                                        ║
║  API Docs:  http://{args.host}:{args.port}/docs                           ║
║  OpenAPI:   http://{args.host}:{args.port}/openapi.json                   ║
║  Health:    http://{args.host}:{args.port}/health                         ║
╚════════════════════════════════════════════════════════════════════════╝
""")

uvicorn.run(
    "api.app:app",
    host=args.host,
    port=args.port,
    reload=reload,
    log_level=args.log_level,
)
