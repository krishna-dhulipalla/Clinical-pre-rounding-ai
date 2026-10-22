"""Run v2 without requiring a PYTHONPATH setting."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["serve", "worker", "migrate", "evaluate", "purge"])
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args, remaining = parser.parse_known_args()
    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "workbench.api:create_app", factory=True, host=args.host, port=args.port, access_log=False
        )
    elif args.command == "worker":
        from workbench.worker import main as worker

        worker()
    elif args.command == "migrate":
        from workbench.config import Settings
        from workbench.persistence import Database

        Database(Settings.from_env().database_url).migrate()
        print("Workbench schema is at head")
    elif args.command == "evaluate":
        from workbench.evaluation import main as evaluate

        sys.argv = [sys.argv[0], *remaining]
        evaluate()
    elif args.command == "purge":
        from workbench.maintenance import main as purge

        sys.argv = [sys.argv[0], *remaining]
        purge()


if __name__ == "__main__":
    main()
