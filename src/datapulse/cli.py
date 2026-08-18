"""DataPulse CLI — entry point for commands."""

import argparse
import sys
from pathlib import Path


def cmd_demo(args):
    """Run the Phase 1 demo."""
    from datapulse.demo import run_demo

    run_demo()


def cmd_serve(args):
    """Start the API server."""
    import uvicorn

    uvicorn.run("datapulse.api.app:app", host=args.host, port=args.port, reload=args.reload)


def cmd_test(args):
    """Run the test suite."""
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
        cwd=Path(__file__).resolve().parent.parent.parent,
    )
    sys.exit(result.returncode)


def main():
    parser = argparse.ArgumentParser(
        prog="datapulse",
        description="DataPulse — data contract and pipeline observability platform",
    )
    subparsers = parser.add_subparsers(dest="command")

    # demo
    subparsers.add_parser("demo", help="Run the Phase 1 demo")

    # serve
    serve_parser = subparsers.add_parser("serve", help="Start the API server")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--reload", action="store_true")

    # test
    subparsers.add_parser("test", help="Run the test suite")

    args = parser.parse_args()

    if args.command == "demo":
        cmd_demo(args)
    elif args.command == "serve":
        cmd_serve(args)
    elif args.command == "test":
        cmd_test(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
