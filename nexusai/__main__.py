"""Module entry point: ``python -m nexusai``.

Subcommands:

    python -m nexusai --help
    python -m nexusai version
    python -m nexusai status
    python -m nexusai init-db
    python -m nexusai serve [--host HOST] [--port PORT] [--reload]

This is the Day 1 CLI surface. Subcommands for agents, RAG, tool execution
and experimentation are scheduled for Days 2-7.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nexusai",
        description="NexusAI — AI-Powered Personal Task Automation",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("version", help="print version and exit")
    sub.add_parser("status", help="print configuration and dependency status")
    sub.add_parser("init-db", help="create the SQLite database schema")

    serve = sub.add_parser("serve", help="start the FastAPI server with uvicorn")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument(
        "--reload",
        action="store_true",
        help="enable auto-reload (development only)",
    )
    return parser


def _cmd_version() -> int:
    from nexusai import __title__, __version__

    print(f"{__title__} v{__version__}")
    return 0


def _cmd_status() -> int:
    from nexusai.app.config import Settings

    try:
        settings = Settings()
    except Exception as exc:  # pragma: no cover - configuration errors
        print(f"configuration error: {exc}", file=sys.stderr)
        return 1
    deps = [
        ("fastapi", "fastapi"),
        ("sqlalchemy", "sqlalchemy"),
        ("streamlit", "streamlit"),
        ("pytest", "pytest"),
        ("ruff", "ruff"),
    ]
    print(f"{settings.app_name} v{settings.app_version} ({settings.environment})")
    print(f"database: {settings.database_url}")
    print("dependencies:")
    ok = True
    for label, module in deps:
        try:
            __import__(module)
            print(f"  - {label}: available")
        except ImportError:
            ok = False
            print(f"  - {label}: NOT INSTALLED", file=sys.stderr)
    if not ok:
        print("run: pip install -e .[dev]", file=sys.stderr)
        return 1
    return 0


def _cmd_init_db() -> int:
    from nexusai.app.config import Settings
    from nexusai.app.db.session import init_db

    settings = Settings()
    engine = init_db(settings)
    print(f"database initialised: {settings.database_url}")
    engine.dispose()
    return 0


def _cmd_serve(host: str, port: int, reload: bool) -> int:
    try:
        import uvicorn  # type: ignore
    except ImportError:
        print("uvicorn is not installed", file=sys.stderr)
        return 1
    from nexusai.app.main import create_app

    app = create_app()
    uvicorn.run(app, host=host, port=port, reload=reload, log_level="info")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    command = args.command

    if command == "version":
        return _cmd_version()
    if command == "status":
        return _cmd_status()
    if command == "init-db":
        return _cmd_init_db()
    if command == "serve":
        return _cmd_serve(
            host=args.host,
            port=args.port,
            reload=bool(getattr(args, "reload", False)),
        )
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
