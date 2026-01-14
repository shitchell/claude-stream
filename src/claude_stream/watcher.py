"""File watching functionality for monitoring JSONL files.

This module provides FileWatcher for processing new lines in JSONL files,
and watch_path for setting up file system monitoring.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .blocks import DividerBlock, HeaderBlock, Style
from .formatters import ANSIFormatter, Formatter
from .models import RenderConfig, parse_message

if TYPE_CHECKING:
    from .stream import should_show_message

# Optional watchdog for --watch functionality
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = None  # type: ignore[misc, assignment]
    FileSystemEventHandler = object  # type: ignore[misc, assignment]


class FileWatcher:
    """Watch files/directories for changes and process new JSONL lines."""

    def __init__(
        self,
        config: RenderConfig,
        formatter: Formatter,
        show_filename: bool = True
    ):
        self.config = config
        self.formatter = formatter
        self.show_filename = show_filename
        self.file_positions: dict[Path, int] = {}
        self.current_file: Path | None = None

    def _print_file_header(self, path: Path) -> None:
        """Print a header when switching to a different file."""
        if not self.show_filename:
            return
        if self.current_file == path:
            return

        self.current_file = path
        header = DividerBlock(char="─", width=60)
        file_block = HeaderBlock(
            text=str(path),
            icon="📄",
            level=2,
            styles={Style.INFO}
        )
        print(self.formatter.format([header, file_block]))

    def _process_lines(self, lines: list[str]) -> None:
        """Parse JSON lines and output formatted messages."""
        # Import here to avoid circular dependency
        from .stream import should_show_message

        for line in lines:
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                msg = parse_message(data)

                if not should_show_message(msg, data, self.config):
                    continue

                blocks = msg.render(self.config)
                output = self.formatter.format(blocks)
                print(output, flush=True)

            except json.JSONDecodeError:
                print(f"warning: skipping invalid JSON: {line[:50]}...", file=sys.stderr)

    def process_new_lines(self, path: Path) -> None:
        """Read and process any new lines from a file."""
        if not path.exists() or not path.is_file():
            return

        # Get current position (0 if new file)
        position = self.file_positions.get(path, 0)

        try:
            with open(path, "r") as f:
                f.seek(position)
                new_content = f.read()
                new_position = f.tell()

            if new_content:
                self._print_file_header(path)
                self._process_lines(new_content.split("\n"))

            self.file_positions[path] = new_position

        except (IOError, OSError) as e:
            print(f"warning: file IO error for {path}: {e}", file=sys.stderr)

    def process_tail_lines(self, path: Path, n: int) -> None:
        """Read and process the last N lines from a file."""
        if not path.exists() or not path.is_file():
            return

        try:
            with open(path, "r") as f:
                # Read all lines and take last N
                lines = f.readlines()
                tail = lines[-n:] if n < len(lines) else lines

                # Set position to end of file for future watches
                self.file_positions[path] = f.tell()

            if tail:
                self._print_file_header(path)
                self._process_lines(tail)

        except (IOError, OSError) as e:
            print(f"warning: file IO error for {path}: {e}", file=sys.stderr)

    def get_initial_files(self, path: Path, recursive: bool = True) -> list[Path]:
        """Get all .jsonl files in a path."""
        if path.is_file():
            return [path]

        if recursive:
            return list(path.rglob("*.jsonl"))
        else:
            return list(path.glob("*.jsonl"))


if WATCHDOG_AVAILABLE:
    class JSONLEventHandler(FileSystemEventHandler):  # type: ignore[misc]
        """Watchdog event handler for JSONL files."""

        def __init__(self, watcher: FileWatcher):
            super().__init__()
            self.watcher = watcher

        def on_modified(self, event: FileModifiedEvent) -> None:
            if event.is_directory:
                return

            path = Path(event.src_path)
            if path.suffix == ".jsonl":
                self.watcher.process_new_lines(path)

        def on_created(self, event: FileCreatedEvent) -> None:
            if event.is_directory:
                return

            path = Path(event.src_path)
            if path.suffix == ".jsonl":
                # New file - start tracking from beginning
                self.watcher.file_positions[path] = 0
                self.watcher.process_new_lines(path)


def watch_path(
    path: Path,
    config: RenderConfig,
    formatter: Formatter,
    recursive: bool = True,
    tail_lines: int = 0
) -> None:
    """Watch a file or directory for changes."""

    if not WATCHDOG_AVAILABLE:
        print("error: watchdog not installed. Run: pip install watchdog", file=sys.stderr)
        sys.exit(1)

    watcher = FileWatcher(config, formatter, show_filename=path.is_dir())

    # Get all files to watch
    initial_files = watcher.get_initial_files(path, recursive)

    if tail_lines <= 0:
        # Skip existing content - just seek to end of all files
        for file_path in initial_files:
            if file_path.exists():
                watcher.file_positions[file_path] = file_path.stat().st_size
    else:
        # Show last N lines from each file (most recent files first)
        for file_path in sorted(initial_files, key=lambda p: p.stat().st_mtime, reverse=True):
            watcher.process_tail_lines(file_path, tail_lines)

    # Set up watchdog observer
    event_handler = JSONLEventHandler(watcher)
    observer = Observer()

    watch_path_resolved = path if path.is_dir() else path.parent
    observer.schedule(event_handler, str(watch_path_resolved), recursive=recursive)

    print(f"\n{ANSIFormatter.DIM}Watching for changes... (Ctrl+C to stop){ANSIFormatter.RESET}\n",
          file=sys.stderr, flush=True)

    observer.start()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        observer.stop()
        print("\nexiting", file=sys.stderr)

    observer.join()
