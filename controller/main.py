"""CLI entry point for the autonomous controller."""
import argparse
import sys
import time
from pathlib import Path

from controller.loop import Controller


def main():
    parser = argparse.ArgumentParser(description="Autonomous Outcome-First Controller")
    parser.add_argument("--url", default="http://127.0.0.1:8700", help="Simulator server URL")
    parser.add_argument("--db", default="controller.db", help="Path to SQLite audit database")
    parser.add_argument("--tick", type=int, default=60, help="Advance tick in minutes (default: 60)")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose logging")
    args = parser.parse_args()

    controller = Controller(
        sim_url=args.url,
        db_path=args.db,
        verbose=not args.quiet,
    )
    try:
        controller.run(tick_minutes=args.tick)
    except KeyboardInterrupt:
        print("\n[Controller] Interrupted by user. Exiting cleanly.")
        sys.exit(0)
    except Exception as e:
        print(f"\n[Controller ERROR] {e}", file=sys.stderr)
        raise e


if __name__ == "__main__":
    main()
