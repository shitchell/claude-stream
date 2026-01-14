"""Allow running as `python -m claude_stream`."""

import sys

from .cli import main

if __name__ == "__main__":
    exit_code: int = 0
    try:
        exit_code = main()
    except KeyboardInterrupt:
        print("\nexiting", end="")

    sys.exit(exit_code)
